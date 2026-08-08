"""
资源接口的租户边界测试。

覆盖 P4 的核心断言：不持有 ops.k8s.manage 的用户，
只能通过 ?project= 访问自己有份的命名空间，拿不到裸集群视角。
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import K8sCluster, K8sProject, K8sProjectMember, K8sWorkspace, K8sWorkspaceMember
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

# 命名空间级只读接口，全部应受 project 边界约束
NAMESPACED_ACTIONS = [
    'pods', 'services', 'deployments', 'statefulsets', 'daemonsets',
    'jobs', 'cronjobs', 'ingresses', 'pvcs', 'configmaps', 'secrets',
]

# 集群级接口没有命名空间维度，一律要求 ops.k8s.manage
CLUSTER_ACTIONS = ['nodes', 'pvs', 'storageclasses', 'summary']


def grant(user, *codes):
    role = Role.objects.create(code=f'scope-{user.username}', name=f'scope-{user.username}')
    role.permissions.set(PermissionDefinition.objects.filter(code__in=codes))
    role.users.add(user)
    return role


class K8sResourceScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.tenant = User.objects.create_user('scope-tenant', 'tenant@example.com', 'Tenant@123456')
        self.outsider = User.objects.create_user('scope-outsider', 'outsider@example.com', 'Outsider@123456')
        self.operator = User.objects.create_user('scope-operator', 'operator@example.com', 'Operator@123456')
        # 租户用户：只有查看权限，没有 ops.k8s.manage
        grant(self.tenant, 'ops.k8s.view', 'ops.k8s.project.view', 'ops.k8s.workspace.view')
        grant(self.outsider, 'ops.k8s.view', 'ops.k8s.project.view', 'ops.k8s.workspace.view')
        grant(self.operator, 'ops.k8s.view', 'ops.k8s.manage')

        self.cluster = K8sCluster.objects.create(name='scope-cluster', kubeconfig='demo', status='connected')
        self.workspace = K8sWorkspace.objects.create(
            name='scope-team', display_name='范围团队', cluster=self.cluster,
        )
        K8sWorkspaceMember.objects.create(workspace=self.workspace, user=self.tenant, role='regular')
        self.project = K8sProject.objects.create(
            workspace=self.workspace, namespace='monitoring', display_name='监控项目',
        )

        other_workspace = K8sWorkspace.objects.create(
            name='other-team', display_name='其他团队', cluster=self.cluster,
        )
        self.other_project = K8sProject.objects.create(
            workspace=other_workspace, namespace='default', display_name='其他项目',
        )

    def url(self, action):
        return f'/api/k8s/clusters/{self.cluster.pk}/{action}/'

    # ====== 裸集群视角 ======

    def test_tenant_cannot_list_namespaced_resources_without_project(self):
        self.client.force_authenticate(user=self.tenant)
        for action in NAMESPACED_ACTIONS:
            with self.subTest(action=action):
                response = self.client.get(self.url(action))
                self.assertEqual(response.status_code, 403, f'{action} 不应放行裸集群访问')
                self.assertIn('project', response.json()['detail'])

    def test_tenant_cannot_bypass_with_explicit_namespace(self):
        """直接指定别人的命名空间同样要被拦住，否则边界形同虚设。"""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('pods'), {'namespace': 'default'})
        self.assertEqual(response.status_code, 403)

    def test_operator_keeps_cluster_wide_access(self):
        self.client.force_authenticate(user=self.operator)
        for action in NAMESPACED_ACTIONS:
            with self.subTest(action=action):
                response = self.client.get(self.url(action), {'namespace': '_all'})
                self.assertEqual(response.status_code, 200, f'{action} 应对管理员保持可用')

    # ====== 按项目访问 ======

    def test_tenant_can_read_own_project(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('pods'), {'project': self.project.pk})
        self.assertEqual(response.status_code, 200)
        namespaces = {row['namespace'] for row in response.json()}
        self.assertTrue(namespaces <= {'monitoring'}, f'越界返回了 {namespaces}')

    def test_tenant_cannot_read_other_project(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('pods'), {'project': self.other_project.pk})
        self.assertEqual(response.status_code, 404)

    def test_outsider_cannot_read_any_project(self):
        self.client.force_authenticate(user=self.outsider)
        for project in (self.project, self.other_project):
            with self.subTest(project=project.pk):
                response = self.client.get(self.url('pods'), {'project': project.pk})
                self.assertEqual(response.status_code, 404)

    def test_unknown_project_returns_404_not_403(self):
        """用 404 而不是 403，避免通过状态码探测项目是否存在。"""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('pods'), {'project': 999999})
        self.assertEqual(response.status_code, 404)

    def test_project_from_another_cluster_is_rejected(self):
        other_cluster = K8sCluster.objects.create(name='scope-cluster-2', kubeconfig='demo', status='connected')
        other_ws = K8sWorkspace.objects.create(name='cross-team', display_name='跨集群', cluster=other_cluster)
        K8sWorkspaceMember.objects.create(workspace=other_ws, user=self.tenant, role='regular')
        cross_project = K8sProject.objects.create(
            workspace=other_ws, namespace='monitoring', display_name='跨集群项目',
        )

        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('pods'), {'project': cross_project.pk})
        self.assertEqual(response.status_code, 404)

    def test_project_membership_alone_grants_access(self):
        """不是企业空间成员，但被直接加进项目，也应该能访问。"""
        K8sProjectMember.objects.create(project=self.other_project, user=self.outsider, role='regular')

        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.url('pods'), {'project': self.other_project.pk})
        self.assertEqual(response.status_code, 200)

    # ====== 命名空间列表 ======

    def test_namespace_list_is_limited_to_project(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('namespaces'), {'project': self.project.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['name'] for item in response.json()], ['monitoring'])

    def test_namespace_list_without_project_is_blocked(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(self.url('namespaces'))
        self.assertEqual(response.status_code, 403)

    def test_operator_sees_all_namespaces(self):
        self.client.force_authenticate(user=self.operator)
        response = self.client.get(self.url('namespaces'))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()), 1)

    # ====== 集群级资源 ======

    def test_cluster_scoped_actions_require_manage(self):
        self.client.force_authenticate(user=self.tenant)
        for action in CLUSTER_ACTIONS:
            with self.subTest(action=action):
                response = self.client.get(self.url(action))
                self.assertEqual(response.status_code, 403, f'{action} 不应对租户用户开放')

    def test_cluster_scoped_actions_allowed_for_operator(self):
        self.client.force_authenticate(user=self.operator)
        for action in CLUSTER_ACTIONS:
            with self.subTest(action=action):
                response = self.client.get(self.url(action))
                self.assertEqual(response.status_code, 200)

    # ====== 写操作 ======

    def test_tenant_cannot_mutate_even_inside_own_project(self):
        """
        成员关系只放开可见性。写操作（重启 Pod）要求 ops.k8s.manage，
        因此租户用户即便在自己的项目里也应被 RBAC 层拦下。
        """
        self.client.force_authenticate(user=self.tenant)
        response = self.client.post(
            f'/api/k8s/clusters/{self.cluster.pk}/pods/some-pod/restart/',
            {'project': self.project.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    @patch('ops.k8s.cache._invalidate_cluster_runtime_cache')
    def test_demo_shortcut_does_not_bypass_scope(self, _mock):
        """
        demo 集群的早返回分支必须排在边界校验之后。
        用持有 manage 的账号验证：项目不属于该集群时仍要被拒，
        而不是被 demo 分支直接返回成功。
        """
        other_cluster = K8sCluster.objects.create(name='scope-cluster-3', kubeconfig='demo', status='connected')
        other_ws = K8sWorkspace.objects.create(name='elsewhere', display_name='别处', cluster=other_cluster)
        elsewhere_project = K8sProject.objects.create(
            workspace=other_ws, namespace='monitoring', display_name='别处项目',
        )

        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            f'/api/k8s/clusters/{self.cluster.pk}/pods/some-pod/restart/',
            {'project': elsewhere_project.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_pod_logs_respects_project_scope(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(
            self.url('pod_logs'),
            {'pod_name': 'x', 'project': self.other_project.pk},
        )
        self.assertEqual(response.status_code, 404)

    def test_resource_yaml_respects_project_scope(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(
            self.url('resource_yaml'),
            {'type': 'pod', 'name': 'x', 'project': self.other_project.pk},
        )
        self.assertEqual(response.status_code, 404)
