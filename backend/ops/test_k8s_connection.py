"""
集群连接测试的容错行为。

背景：KubeSphere 等发行版的 /version 响应缺少 buildDate 等字段，
官方客户端反序列化成 VersionInfo 时会抛
"Invalid value for `build_date`, must not be `None`"。
版本号只用于提示文案，不能因此判定连接失败。
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import K8sCluster
from rbac.services import ensure_builtin_rbac


def make_client(version_obj=None, version_exc=None, raw_payload=None):
    """构造一个假的 K8s 客户端代理，模拟不同发行版的 /version 行为。"""
    k8s = MagicMock()
    k8s.CoreV1Api.return_value.get_api_resources.return_value = MagicMock()

    version_api = MagicMock()
    if version_exc is not None:
        version_api.get_code.side_effect = version_exc
    else:
        version_api.get_code.return_value = version_obj

    if raw_payload is None:
        del version_api.get_code_without_preload_content
    else:
        raw = MagicMock()
        raw.data = json.dumps(raw_payload)
        version_api.get_code_without_preload_content.return_value = raw

    k8s.VersionApi.return_value = version_api
    return k8s


class K8sTestConnectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_superuser(
            'conn-admin', 'conn@example.com', 'Admin@123456',
        )
        self.client.force_authenticate(user=self.admin)
        self.cluster = K8sCluster.objects.create(
            name='kubesphere', kubeconfig='apiVersion: v1\nkind: Config\n', status='disconnected',
        )

    def url(self):
        return f'/api/k8s/clusters/{self.cluster.pk}/test_connection/'

    def test_reports_version_when_model_parses(self):
        version = MagicMock()
        version.git_version = 'v1.29.3'
        with patch('ops.k8s.client._get_k8s_client', return_value=make_client(version_obj=version)):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('v1.29.3', payload['message'])
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, 'connected')

    def test_falls_back_to_raw_payload_when_version_model_rejects_response(self):
        """这就是 KubeSphere 报的那个错，应当降级取原始 JSON 而不是判失败。"""
        k8s = make_client(
            version_exc=ValueError('Invalid value for `build_date`, must not be `None`'),
            raw_payload={'gitVersion': 'v1.28.9'},
        )
        with patch('ops.k8s.client._get_k8s_client', return_value=k8s):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('v1.28.9', payload['message'])
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, 'connected')

    def test_connection_succeeds_without_version_when_both_paths_fail(self):
        k8s = make_client(
            version_exc=ValueError('Invalid value for `build_date`, must not be `None`'),
            raw_payload=None,
        )
        with patch('ops.k8s.client._get_k8s_client', return_value=k8s):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['message'], '连接成功')
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, 'connected')

    def test_real_api_failure_still_reports_disconnected(self):
        """版本号可以取不到，但 API 调不通必须如实报失败。"""
        k8s = MagicMock()
        k8s.CoreV1Api.return_value.get_api_resources.side_effect = Exception('connection refused')

        with patch('ops.k8s.client._get_k8s_client', return_value=k8s):
            response = self.client.post(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['success'])
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, 'error')


CLIENT_CERT_KUBECONFIG = (
    'apiVersion: v1\nkind: Config\n'
    'users:\n- name: admin\n  user:\n    client-certificate-data: QUJD\n    client-key-data: QUJD\n'
)


class K8sClusterApiServerValidationTests(TestCase):
    """http 是合法配置，但要如实提示风险；缺协议前缀则连不上，必须拦。"""

    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_superuser(
            'api-admin', 'api@example.com', 'Admin@123456',
        )
        self.client.force_authenticate(user=self.admin)

    def create(self, api_server, kubeconfig='apiVersion: v1\nkind: Config\n'):
        return self.client.post(
            '/api/k8s/clusters/',
            {
                'name': f'cluster-{abs(hash(api_server + kubeconfig)) % 100000}',
                'api_server': api_server,
                'kubeconfig': kubeconfig,
            },
            format='json',
        )

    def test_http_api_server_is_accepted_with_warning(self):
        """老集群的明文端口、本地代理都是合法场景，不该阻断保存。"""
        response = self.create('http://127.0.0.1:8080')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()['warnings'])

    def test_http_with_client_cert_kubeconfig_warns_about_anonymous(self):
        response = self.create('http://192.168.199.160:30880', CLIENT_CERT_KUBECONFIG)
        self.assertEqual(response.status_code, 201, response.content)
        warning = response.json()['warnings'][0]
        self.assertIn('system:anonymous', warning)
        self.assertIn('6443', warning)

    def test_scheme_less_api_server_is_rejected(self):
        """没有协议前缀客户端根本连不上，这是硬约束不是偏好。"""
        response = self.create('192.168.199.160:6443')
        self.assertEqual(response.status_code, 400)

    def test_https_api_server_has_no_warning(self):
        response = self.create('https://192.168.199.160:6443', CLIENT_CERT_KUBECONFIG)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['warnings'], [])

    def test_empty_api_server_is_accepted(self):
        """留空表示沿用 kubeconfig 里的 server，是合法用法。"""
        response = self.create('')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['warnings'], [])


class K8sAnonymousHintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_superuser(
            'anon-admin', 'anon@example.com', 'Admin@123456',
        )
        self.client.force_authenticate(user=self.admin)
        self.cluster = K8sCluster.objects.create(
            name='anon-cluster', kubeconfig='apiVersion: v1\nkind: Config\n',
        )

    def test_anonymous_403_gets_actionable_hint(self):
        k8s = MagicMock()
        k8s.CoreV1Api.return_value.get_api_resources.side_effect = Exception(
            '(403) Reason: Forbidden ... forbidden: User "system:anonymous" cannot GET path "/api/v1/"'
        )
        with patch('ops.k8s.client._get_k8s_client', return_value=k8s):
            response = self.client.post(f'/api/k8s/clusters/{self.cluster.pk}/test_connection/')

        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('system:anonymous', payload['message'])
        self.assertIn('6443', payload['message'])
