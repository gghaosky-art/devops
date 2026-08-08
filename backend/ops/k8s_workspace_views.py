"""
Kubernetes 企业空间 / 项目 API。

可见性模型：
  - 持有 ops.k8s.manage → 平台级视角，可见并可管全部；
  - 其余用户（无论持有 *.view 还是 *.manage）→ 只能看到自己是成员的企业空间与项目；
  - 非成员访问他人对象 → 404（不暴露对象是否存在）。

两道判定是正交的，缺一不可：
  - 「能不能做」由全局 RBAC 的 *.manage / *.view 决定；
  - 「能对谁做」由成员关系决定，落在 get_queryset 上，越界对象取不到即 404。
因此 ops.k8s.project.manage 只是「有权删项目」，不等于「有权删任何项目」。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from rbac.permissions import RBACPermissionMixin

from . import k8s_provision
from .k8s_provision import ProvisionError
from .k8s_scope import visible_projects, visible_workspaces
from .models import (
    K8S_PROJECT_LABEL, K8sCluster, K8sProject, K8sProjectMember, K8sWorkspace, K8sWorkspaceMember,
)
from .serializers import (
    K8sMemberSerializer, K8sProjectMemberSerializer, K8sProjectSerializer, K8sWorkspaceSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class _MemberMixin:
    """企业空间与项目的成员管理逻辑一致，抽出来复用。"""

    member_model = None
    member_serializer = None
    member_owner_field = None

    def _member_queryset(self, owner):
        return self.member_model.objects.filter(**{self.member_owner_field: owner}).select_related('user')

    @action(detail=True, methods=['get', 'post'])
    def members(self, request, pk=None):
        owner = self.get_object()
        if request.method.upper() == 'GET':
            return Response(self.member_serializer(self._member_queryset(owner), many=True).data)

        user_id = request.data.get('user')
        role = request.data.get('role') or 'regular'
        if not user_id:
            return Response({'detail': '缺少 user 参数。'}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return Response({'detail': '用户不存在。'}, status=status.HTTP_400_BAD_REQUEST)

        member, created = self.member_model.objects.get_or_create(
            defaults={'role': role},
            **{self.member_owner_field: owner, 'user': user},
        )
        if not created and member.role != role:
            member.role = role
            member.save(update_fields=['role'])
        return Response(
            self.member_serializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['delete'], url_path='members/(?P<user_id>[^/]+)')
    def remove_member(self, request, pk=None, user_id=None):
        owner = self.get_object()
        deleted, _ = self._member_queryset(owner).filter(user_id=user_id).delete()
        if not deleted:
            return Response({'detail': '该成员不存在。'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class K8sWorkspaceViewSet(_MemberMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    """企业空间：绑定单一集群的逻辑租户。"""

    queryset = K8sWorkspace.objects.select_related('cluster')
    serializer_class = K8sWorkspaceSerializer
    pagination_class = None
    member_model = K8sWorkspaceMember
    member_serializer = K8sMemberSerializer
    member_owner_field = 'workspace'
    rbac_permissions = {
        'list': ['ops.k8s.workspace.view'],
        'retrieve': ['ops.k8s.workspace.view'],
        'members': ['ops.k8s.workspace.view'],
        'create': ['ops.k8s.workspace.manage'],
        'update': ['ops.k8s.workspace.manage'],
        'partial_update': ['ops.k8s.workspace.manage'],
        'destroy': ['ops.k8s.workspace.manage'],
        'remove_member': ['ops.k8s.workspace.manage'],
    }

    def get_queryset(self):
        return visible_workspaces(self.request.user)

    def get_permissions(self):
        # members 既是读也是写入口，POST 时需要 manage 权限
        if self.action == 'members' and self.request.method.upper() == 'POST':
            self.rbac_permissions = {**self.rbac_permissions, 'members': ['ops.k8s.workspace.manage']}
        return super().get_permissions()

    def perform_create(self, serializer):
        workspace = serializer.save(created_by=self.request.user.username)
        # 作用域收敛到成员关系后，非平台管理员建完空间会立刻从自己的列表里消失，
        # 所以把创建者直接登记成管理员成员
        K8sWorkspaceMember.objects.get_or_create(
            workspace=workspace, user=self.request.user, defaults={'role': 'admin'},
        )

    def perform_destroy(self, instance):
        if instance.projects.exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': '该企业空间下仍有项目，请先删除或解绑项目。'})
        instance.delete()

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        workspace = self.get_object()
        projects = workspace.projects.all()
        return Response({
            'id': workspace.pk,
            'name': workspace.name,
            'cluster': workspace.cluster_id,
            'cluster_name': workspace.cluster.name,
            'project_count': projects.count(),
            'member_count': workspace.members.count(),
            'enforced_project_count': projects.filter(quota_enforced=True).count(),
            'quota': workspace.quota or {},
        })


class K8sProjectViewSet(_MemberMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    """项目：企业空间下绑定到某个命名空间的资源边界。"""

    queryset = K8sProject.objects.select_related('workspace', 'cluster')
    serializer_class = K8sProjectSerializer
    pagination_class = None
    member_model = K8sProjectMember
    member_serializer = K8sProjectMemberSerializer
    member_owner_field = 'project'
    rbac_permissions = {
        'list': ['ops.k8s.project.view'],
        'retrieve': ['ops.k8s.project.view'],
        'members': ['ops.k8s.project.view'],
        'usage': ['ops.k8s.project.view'],
        'create': ['ops.k8s.project.manage'],
        'update': ['ops.k8s.project.manage'],
        'partial_update': ['ops.k8s.project.manage'],
        'destroy': ['ops.k8s.project.manage'],
        'remove_member': ['ops.k8s.project.manage'],
        'sync_quota': ['ops.k8s.project.manage'],
    }

    def get_queryset(self):
        queryset = visible_projects(self.request.user)
        workspace_id = self.request.query_params.get('workspace')
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)
        cluster_id = self.request.query_params.get('cluster')
        if cluster_id:
            queryset = queryset.filter(cluster_id=cluster_id)
        return queryset

    def get_permissions(self):
        if self.action == 'members' and self.request.method.upper() == 'POST':
            self.rbac_permissions = {**self.rbac_permissions, 'members': ['ops.k8s.project.manage']}
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace = serializer.validated_data['workspace']
        # 用户只能在自己可见的企业空间下建项目
        if not visible_workspaces(request.user).filter(pk=workspace.pk).exists():
            return Response({'detail': '无权在该企业空间下创建项目。'}, status=status.HTTP_403_FORBIDDEN)

        namespace = serializer.validated_data['namespace']
        mode = serializer.validated_data.get('provision_mode', 'create')
        cluster = workspace.cluster

        try:
            error = self._validate_namespace(cluster, namespace, mode)
        except ProvisionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            project = serializer.save(created_by=request.user.username)
            try:
                if mode == 'create':
                    k8s_provision.create_namespace(cluster, project)
                else:
                    k8s_provision.label_namespace(cluster, project)
                if project.quota_enforced:
                    k8s_provision.apply_quota(cluster, project)
            except ProvisionError as exc:
                # 集群侧失败就整体回滚，避免留下没有对应命名空间的空项目
                transaction.set_rollback(True)
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = self.get_serializer(project).data
        payload['warnings'] = self._quota_warnings(project)
        return Response(payload, status=status.HTTP_201_CREATED)

    def _validate_namespace(self, cluster, namespace, mode):
        """返回错误文案，None 表示校验通过。"""
        if namespace in k8s_provision.SYSTEM_NAMESPACES:
            return f'{namespace} 是集群系统命名空间，不能纳管为项目。'
        if K8sProject.objects.filter(cluster=cluster, namespace=namespace).exists():
            return f'命名空间 {namespace} 已被其他项目绑定。'

        existing = k8s_provision.find_namespace(cluster, namespace)
        if mode == 'create':
            if existing:
                return f'命名空间 {namespace} 在集群中已存在，如需接管请改用「纳管已有」。'
            return None

        if not existing:
            return f'命名空间 {namespace} 在集群中不存在，无法纳管。'
        bound = (existing.get('labels') or {}).get(K8S_PROJECT_LABEL)
        if bound and self._project_exists(bound):
            return f'命名空间 {namespace} 已被项目 #{bound} 占用。'
        return None

    @staticmethod
    def _project_exists(project_id):
        """
        detach 删除后标签会留在命名空间上，指向一个已不存在的项目。
        这种残留不该永久挡住重新纳管，所以按标签指向的项目是否还在来判断。
        """
        try:
            return K8sProject.objects.filter(pk=int(project_id)).exists()
        except (TypeError, ValueError):
            # 标签被人手工改成了非数字，无从判断归属，保守视为已占用
            return True

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        project = self.get_object()
        try:
            if project.quota_enforced:
                k8s_provision.apply_quota(project.cluster, project)
            else:
                k8s_provision.delete_quota(project.cluster, project)
        except ProvisionError as exc:
            # 平台侧已经保存成功，这里只把集群侧的失败如实带回，不再回滚
            response.data['warnings'] = [f'配额下发失败: {exc}']
            return response
        response.data['warnings'] = self._quota_warnings(project)
        return response

    # 删除项目时对集群的介入程度，由弱到强
    DELETE_MODES = ('detach', 'release', 'purge')

    def destroy(self, request, *args, **kwargs):
        """
        三种模式，默认 detach：

          detach  只删平台侧记录，对集群不发出任何写请求；
          release 额外清掉归属标签与平台下发的配额对象，命名空间与工作负载保留；
          purge   连命名空间一起删，仅限平台创建（provision_mode=create）的项目。

        detach 会把 sxdevops.io/* 标签留在命名空间上，重新纳管时按标签指向的项目
        是否仍存在来判断占用，见 _validate_namespace。
        """
        project = self.get_object()
        mode = self._delete_mode(request)
        if mode not in self.DELETE_MODES:
            return Response(
                {'detail': f'未知的删除模式 {mode}，可选 {"、".join(self.DELETE_MODES)}。'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mode == 'purge' and project.provision_mode != 'create':
            return Response(
                {'detail': '纳管而来的命名空间不允许通过平台删除，请改用解绑。'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mode != 'detach':
            cluster = project.cluster
            try:
                k8s_provision.delete_quota(cluster, project)
                if mode == 'purge':
                    k8s_provision.delete_namespace(cluster, project)
                else:
                    k8s_provision.unlabel_namespace(cluster, project)
            except ProvisionError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _delete_mode(request):
        """purge=1 是旧前端与既有脚本在用的参数，继续兼容。"""
        mode = str(request.query_params.get('mode', '')).strip().lower()
        if mode:
            return mode
        if str(request.query_params.get('purge', '')).strip().lower() in ('1', 'true', 'yes'):
            return 'purge'
        return 'detach'

    @action(detail=True, methods=['post'])
    def sync_quota(self, request, pk=None):
        """把平台侧配置的配额重新下发一次（或在关闭开关后撤销）。"""
        project = self.get_object()
        try:
            if project.quota_enforced:
                k8s_provision.apply_quota(project.cluster, project)
                message = '配额已下发到集群'
            else:
                k8s_provision.delete_quota(project.cluster, project)
                message = '已撤销集群侧配额，配额仅在平台展示'
        except ProvisionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': message, 'warnings': self._quota_warnings(project)})

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        project = self.get_object()
        usage = k8s_provision.collect_usage(project.cluster, project)
        return Response({
            'project': project.pk,
            'namespace': project.namespace,
            'quota': project.quota or {},
            'quota_enforced': project.quota_enforced,
            'usage': usage,
        })

    def _quota_warnings(self, project):
        """开启下发但没配默认值时给出提示，这类问题会延迟到下次滚动更新才暴露。"""
        warnings = []
        if project.quota_enforced and project.quota and not project.limit_range:
            warnings.append(
                '已开启配额下发但未设置默认资源限制：命名空间内未声明 requests/limits 的 Pod '
                '将被集群拒绝创建，建议同时配置 LimitRange 默认值。'
            )
        return warnings
