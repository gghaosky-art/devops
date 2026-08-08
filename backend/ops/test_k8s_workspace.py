from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from ops.k8s_provision import ProvisionError
from ops.models import (
    K8S_PROJECT_LABEL, K8S_WORKSPACE_LABEL, K8sCluster, K8sProject, K8sWorkspace, K8sWorkspaceMember,
)
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac


def grant(user, *codes):
    """给用户单独建一个只含指定权限的角色，用来精确构造越权场景。"""
    role = Role.objects.create(code=f'test-{user.username}', name=f'test-{user.username}')
    role.permissions.set(PermissionDefinition.objects.filter(code__in=codes))
    role.users.add(user)
    return role


class K8sWorkspaceProjectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_superuser('k8s-admin', 'k8s-admin@example.com', 'Admin@123456')
        self.member = User.objects.create_user('k8s-member', 'member@example.com', 'Member@123456')
        self.outsider = User.objects.create_user('k8s-outsider', 'outsider@example.com', 'Outsider@123456')
        grant(self.member, 'ops.k8s.workspace.view', 'ops.k8s.project.view')
        grant(self.outsider, 'ops.k8s.workspace.view', 'ops.k8s.project.view')

        # kubeconfig 为 'demo' 时不会触碰真实集群
        self.cluster = K8sCluster.objects.create(name='test-cluster', kubeconfig='demo', status='connected')
        self.workspace = K8sWorkspace.objects.create(
            name='team-a', display_name='A 团队', cluster=self.cluster, created_by='k8s-admin',
        )
        K8sWorkspaceMember.objects.create(workspace=self.workspace, user=self.member, role='regular')

    # ====== 可见性隔离 ======

    def test_member_only_sees_own_workspace(self):
        other = K8sWorkspace.objects.create(name='team-b', display_name='B 团队', cluster=self.cluster)

        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/k8s/workspaces/')
        self.assertEqual(response.status_code, 200)
        names = {item['name'] for item in response.json()}
        self.assertEqual(names, {'team-a'})

        detail = self.client.get(f'/api/k8s/workspaces/{other.pk}/')
        self.assertEqual(detail.status_code, 404)

    def test_outsider_sees_empty_workspace_list(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get('/api/k8s/workspaces/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_platform_admin_sees_all_workspaces(self):
        K8sWorkspace.objects.create(name='team-b', display_name='B 团队', cluster=self.cluster)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/k8s/workspaces/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_view_only_member_cannot_create_workspace(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            '/api/k8s/workspaces/',
            {'name': 'team-c', 'display_name': 'C 团队', 'cluster': self.cluster.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_project_visible_through_workspace_membership(self):
        project = K8sProject.objects.create(
            workspace=self.workspace, namespace='team-a-prod', display_name='A 生产',
        )
        other_workspace = K8sWorkspace.objects.create(name='team-b', display_name='B 团队', cluster=self.cluster)
        K8sProject.objects.create(workspace=other_workspace, namespace='team-b-prod', display_name='B 生产')

        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/k8s/projects/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item['id'] for item in payload], [project.pk])

    def test_workspace_name_is_immutable(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/k8s/workspaces/{self.workspace.pk}/',
            {'name': 'team-renamed'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, 'team-a')

    def test_workspace_display_name_can_be_updated(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/k8s/workspaces/{self.workspace.pk}/',
            {'display_name': 'A 团队（新）'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.display_name, 'A 团队（新）')

    def test_workspace_cluster_is_immutable(self):
        other_cluster = K8sCluster.objects.create(name='other-cluster', kubeconfig='demo')

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/k8s/workspaces/{self.workspace.pk}/',
            {'cluster': other_cluster.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.cluster_id, self.cluster.pk)

    # ====== 模型约束 ======

    def test_project_inherits_cluster_from_workspace(self):
        project = K8sProject.objects.create(
            workspace=self.workspace, namespace='team-a-dev', display_name='A 开发',
        )
        self.assertEqual(project.cluster_id, self.cluster.pk)

    def test_cluster_delete_is_protected_by_workspace(self):
        with self.assertRaises(ProtectedError):
            self.cluster.delete()

    def test_cluster_delete_api_returns_readable_error(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/clusters/{self.cluster.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('企业空间', response.json()['detail'])
        self.assertTrue(K8sCluster.objects.filter(pk=self.cluster.pk).exists())

    # ====== 创建与纳管 ======

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    @patch('ops.k8s_provision.create_namespace')
    def test_create_project_provisions_namespace(self, mock_create, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'team-a-prod',
                'display_name': 'A 生产',
                'provision_mode': 'create',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['cluster'], self.cluster.pk)
        mock_create.assert_called_once()

    @patch('ops.k8s_provision.list_namespaces', return_value=[{'name': 'legacy', 'labels': {}}])
    def test_create_mode_rejects_existing_namespace(self, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'legacy',
                'display_name': '遗留应用',
                'provision_mode': 'create',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('已存在', response.json()['detail'])
        self.assertFalse(K8sProject.objects.filter(namespace='legacy').exists())

    @patch('ops.k8s_provision.list_namespaces', return_value=[{'name': 'legacy', 'labels': {}}])
    @patch('ops.k8s_provision.label_namespace')
    def test_adopt_existing_namespace(self, mock_label, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'legacy',
                'display_name': '遗留应用',
                'provision_mode': 'adopt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        mock_label.assert_called_once()

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    def test_adopt_mode_rejects_missing_namespace(self, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'ghost',
                'display_name': '不存在',
                'provision_mode': 'adopt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('不存在', response.json()['detail'])

    @patch('ops.k8s_provision.list_namespaces')
    def test_adopt_mode_rejects_namespace_owned_by_other_project(self, mock_list):
        # 标签指向的项目必须真实存在才算占用；这里让它绑在另一个集群上，
        # 以便绕开 (cluster, namespace) 唯一约束那道更靠前的校验，单独覆盖标签分支。
        other_cluster = K8sCluster.objects.create(name='other-cluster', kubeconfig='demo', status='connected')
        other_workspace = K8sWorkspace.objects.create(
            name='team-c', display_name='C 团队', cluster=other_cluster,
        )
        owner = K8sProject.objects.create(
            workspace=other_workspace, namespace='taken', display_name='占用方', provision_mode='adopt',
        )
        mock_list.return_value = [{'name': 'taken', 'labels': {K8S_PROJECT_LABEL: str(owner.pk)}}]

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'taken',
                'display_name': '已占用',
                'provision_mode': 'adopt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('占用', response.json()['detail'])

    @patch('ops.k8s_provision.list_namespaces', return_value=[{'name': 'kube-system', 'labels': {}}])
    def test_system_namespace_cannot_be_adopted(self, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'kube-system',
                'display_name': '系统',
                'provision_mode': 'adopt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('系统命名空间', response.json()['detail'])

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    def test_same_namespace_cannot_be_bound_twice(self, _mock_list):
        K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'team-a-prod',
                'display_name': '重复',
                'provision_mode': 'create',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('已被其他项目绑定', response.json()['detail'])

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    @patch('ops.k8s_provision.create_namespace', side_effect=Exception('boom'))
    def test_provision_failure_does_not_leave_orphan_project(self, _mock_create, _mock_list):
        self.client.force_authenticate(user=self.admin)
        with self.assertRaises(Exception):
            self.client.post(
                '/api/k8s/projects/',
                {
                    'workspace': self.workspace.pk,
                    'namespace': 'team-a-prod',
                    'display_name': 'A 生产',
                    'provision_mode': 'create',
                },
                format='json',
            )
        self.assertFalse(K8sProject.objects.filter(namespace='team-a-prod').exists())

    # ====== 配额 ======

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    @patch('ops.k8s_provision.create_namespace')
    @patch('ops.k8s_provision.apply_quota')
    def test_quota_not_pushed_when_enforcement_disabled(self, mock_apply, _mock_create, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'team-a-prod',
                'display_name': 'A 生产',
                'provision_mode': 'create',
                'quota': {'requests.cpu': '4'},
                'quota_enforced': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        mock_apply.assert_not_called()

    @patch('ops.k8s_provision.list_namespaces', return_value=[])
    @patch('ops.k8s_provision.create_namespace')
    @patch('ops.k8s_provision.apply_quota')
    def test_enforced_quota_without_limit_range_returns_warning(self, mock_apply, _mock_create, _mock_list):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            '/api/k8s/projects/',
            {
                'workspace': self.workspace.pk,
                'namespace': 'team-a-prod',
                'display_name': 'A 生产',
                'provision_mode': 'create',
                'quota': {'requests.cpu': '4'},
                'quota_enforced': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        mock_apply.assert_called_once()
        self.assertTrue(response.json()['warnings'])

    @patch('ops.k8s_provision.apply_quota', side_effect=ProvisionError('集群不可达'))
    def test_update_reports_quota_push_failure_without_500(self, _mock_apply):
        project = K8sProject.objects.create(
            workspace=self.workspace, namespace='team-a-prod', display_name='A 生产',
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/k8s/projects/{project.pk}/',
            {'quota': {'requests.cpu': '4'}, 'quota_enforced': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('配额下发失败', response.json()['warnings'][0])
        project.refresh_from_db()
        self.assertTrue(project.quota_enforced)

    @patch('ops.k8s_provision.delete_quota')
    def test_disabling_enforcement_revokes_cluster_quota(self, mock_delete):
        project = K8sProject.objects.create(
            workspace=self.workspace, namespace='team-a-prod', display_name='A 生产',
            quota={'requests.cpu': '4'}, quota_enforced=True,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/k8s/projects/{project.pk}/',
            {'quota_enforced': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        mock_delete.assert_called_once()

    # ====== 解绑与删除 ======

    @patch('ops.k8s_provision.unlabel_namespace')
    @patch('ops.k8s_provision.delete_namespace')
    @patch('ops.k8s_provision.delete_quota')
    def test_destroy_defaults_to_detach_and_never_touches_cluster(self, mock_quota, mock_delete_ns, mock_unlabel):
        """默认删除必须是纯平台侧动作，集群一个写请求都不能发。"""
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/')
        self.assertEqual(response.status_code, 204)
        mock_quota.assert_not_called()
        mock_unlabel.assert_not_called()
        mock_delete_ns.assert_not_called()
        self.assertFalse(K8sProject.objects.filter(pk=project.pk).exists())

    @patch('ops.k8s_provision.unlabel_namespace')
    @patch('ops.k8s_provision.delete_namespace')
    @patch('ops.k8s_provision.delete_quota')
    def test_release_mode_clears_labels_and_quota(self, mock_quota, mock_delete_ns, mock_unlabel):
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/?mode=release')
        self.assertEqual(response.status_code, 204)
        mock_quota.assert_called_once()
        mock_unlabel.assert_called_once()
        mock_delete_ns.assert_not_called()

    @patch('ops.k8s_provision.unlabel_namespace')
    @patch('ops.k8s_provision.delete_namespace')
    @patch('ops.k8s_provision.delete_quota')
    def test_purge_mode_deletes_namespace(self, _mock_quota, mock_delete_ns, mock_unlabel):
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/?mode=purge')
        self.assertEqual(response.status_code, 204)
        mock_delete_ns.assert_called_once()
        mock_unlabel.assert_not_called()

    @patch('ops.k8s_provision.delete_namespace')
    @patch('ops.k8s_provision.delete_quota')
    def test_legacy_purge_param_still_works(self, _mock_quota, mock_delete_ns):
        """旧前端与既有脚本用的是 ?purge=1，不能因为引入 mode 就静默降级成 detach。"""
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/?purge=1')
        self.assertEqual(response.status_code, 204)
        mock_delete_ns.assert_called_once()

    def test_unknown_delete_mode_is_rejected(self):
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/?mode=nuke')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(K8sProject.objects.filter(pk=project.pk).exists())

    @patch('ops.k8s_provision.label_namespace')
    @patch('ops.k8s_provision.list_namespaces')
    def test_stale_label_does_not_block_readoption(self, mock_list, _mock_label):
        """detach 会把标签留在命名空间上，指向的项目没了就不该再算占用。"""
        project = K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')
        stale_id = project.pk
        project.delete()
        mock_list.return_value = [{
            'name': 'team-a-prod',
            'labels': {K8S_PROJECT_LABEL: str(stale_id), K8S_WORKSPACE_LABEL: 'team-a'},
        }]

        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/k8s/projects/', {
            'workspace': self.workspace.pk,
            'namespace': 'team-a-prod',
            'display_name': '重新纳管',
            'provision_mode': 'adopt',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)

    @patch('ops.k8s_provision.delete_quota')
    def test_adopted_project_cannot_be_purged(self, _mock_quota):
        project = K8sProject.objects.create(
            workspace=self.workspace, namespace='legacy', display_name='遗留', provision_mode='adopt',
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/projects/{project.pk}/?purge=1')
        self.assertEqual(response.status_code, 400)
        self.assertIn('不允许通过平台删除', response.json()['detail'])
        self.assertTrue(K8sProject.objects.filter(pk=project.pk).exists())

    def test_workspace_with_projects_cannot_be_deleted(self):
        K8sProject.objects.create(workspace=self.workspace, namespace='team-a-prod', display_name='A 生产')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/k8s/workspaces/{self.workspace.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(K8sWorkspace.objects.filter(pk=self.workspace.pk).exists())

    # ====== 成员管理 ======

    def test_member_list_and_add(self):
        self.client.force_authenticate(user=self.admin)

        listed = self.client.get(f'/api/k8s/workspaces/{self.workspace.pk}/members/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item['username'] for item in listed.json()], ['k8s-member'])

        added = self.client.post(
            f'/api/k8s/workspaces/{self.workspace.pk}/members/',
            {'user': self.outsider.pk, 'role': 'viewer'},
            format='json',
        )
        self.assertEqual(added.status_code, 201, added.content)
        self.assertEqual(K8sWorkspaceMember.objects.filter(workspace=self.workspace).count(), 2)

    def test_view_only_member_cannot_add_member(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            f'/api/k8s/workspaces/{self.workspace.pk}/members/',
            {'user': self.outsider.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 403)


class K8sManageScopeTests(TestCase):
    """
    *.manage 只放大动词，不放大作用域。

    这里盯的是一类具体越权：给业务负责人 ops.k8s.project.manage 让他管自己的项目，
    他不能因此获得删除别人企业空间下项目的能力。
    """

    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.cluster = K8sCluster.objects.create(name='scoped-cluster', kubeconfig='demo', status='connected')
        self.mine = K8sWorkspace.objects.create(name='team-mine', display_name='我的团队', cluster=self.cluster)
        self.theirs = K8sWorkspace.objects.create(name='team-theirs', display_name='别人团队', cluster=self.cluster)

        # 业务负责人：有项目管理权，但没有 ops.k8s.manage，只属于 team-mine
        self.lead = User.objects.create_user('scoped-lead', 'lead@example.com', 'Lead@123456')
        grant(self.lead, 'ops.k8s.project.view', 'ops.k8s.project.manage',
              'ops.k8s.workspace.view', 'ops.k8s.workspace.manage')
        K8sWorkspaceMember.objects.create(workspace=self.mine, user=self.lead, role='admin')

        # 平台管理员：持有 ops.k8s.manage，作用域不受成员关系约束
        self.platform = User.objects.create_user('scoped-platform', 'platform@example.com', 'Platform@123456')
        grant(self.platform, 'ops.k8s.manage', 'ops.k8s.project.view', 'ops.k8s.project.manage',
              'ops.k8s.workspace.view', 'ops.k8s.workspace.manage')

        self.my_project = K8sProject.objects.create(
            workspace=self.mine, namespace='mine-prod', display_name='我的生产',
        )
        self.their_project = K8sProject.objects.create(
            workspace=self.theirs, namespace='theirs-prod', display_name='别人的生产',
        )

    def test_project_manage_does_not_widen_visibility(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.get('/api/k8s/projects/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['namespace'] for item in response.json()], ['mine-prod'])

    def test_project_manage_cannot_delete_other_workspace_project(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.delete(f'/api/k8s/projects/{self.their_project.pk}/')
        # 越界统一 404，不暴露该项目是否存在
        self.assertEqual(response.status_code, 404)
        self.assertTrue(K8sProject.objects.filter(pk=self.their_project.pk).exists())

    def test_project_manage_cannot_purge_other_workspace_namespace(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.delete(f'/api/k8s/projects/{self.their_project.pk}/?mode=purge')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(K8sProject.objects.filter(pk=self.their_project.pk).exists())

    def test_project_manage_cannot_edit_other_workspace_project(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.patch(
            f'/api/k8s/projects/{self.their_project.pk}/', {'display_name': '改掉'}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_project_manage_still_works_inside_own_workspace(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.delete(f'/api/k8s/projects/{self.my_project.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(K8sProject.objects.filter(pk=self.my_project.pk).exists())

    def test_workspace_manage_cannot_delete_other_workspace(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.delete(f'/api/k8s/workspaces/{self.theirs.pk}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(K8sWorkspace.objects.filter(pk=self.theirs.pk).exists())

    def test_platform_manage_keeps_full_scope(self):
        self.client.force_authenticate(user=self.platform)
        listed = self.client.get('/api/k8s/projects/')
        self.assertEqual(
            sorted(item['namespace'] for item in listed.json()), ['mine-prod', 'theirs-prod'],
        )
        response = self.client.delete(f'/api/k8s/projects/{self.their_project.pk}/')
        self.assertEqual(response.status_code, 204)

    def test_creator_becomes_member_of_new_workspace(self):
        """作用域收敛后，创建者若不自动入组会立刻看不见自己刚建的空间。"""
        self.client.force_authenticate(user=self.lead)
        created = self.client.post('/api/k8s/workspaces/', {
            'name': 'team-new', 'display_name': '新团队', 'cluster': self.cluster.pk,
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)

        new_id = created.json()['id']
        self.assertTrue(
            K8sWorkspaceMember.objects.filter(workspace_id=new_id, user=self.lead, role='admin').exists()
        )
        listed = self.client.get('/api/k8s/workspaces/')
        self.assertIn('team-new', [item['name'] for item in listed.json()])


class K8sQuantityParsingTests(TestCase):
    def test_parse_cpu(self):
        from ops.k8s_provision import parse_cpu

        self.assertEqual(parse_cpu('100m'), 0.1)
        self.assertEqual(parse_cpu('2'), 2.0)
        self.assertEqual(parse_cpu(''), 0.0)
        self.assertEqual(parse_cpu('bogus'), 0.0)

    def test_parse_memory(self):
        from ops.k8s_provision import parse_memory

        self.assertEqual(parse_memory('128Mi'), 128 * 1024 ** 2)
        self.assertEqual(parse_memory('1Gi'), 1024 ** 3)
        self.assertEqual(parse_memory('1000'), 1000)
        self.assertEqual(parse_memory(''), 0)
