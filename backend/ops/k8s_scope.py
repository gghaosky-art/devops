"""
K8s 资源请求的租户边界解析。

单独成模块是为了让 k8s_views 与 k8s_workspace_views 都能引用而不产生循环依赖。

两种访问姿态：
  - 带 ?project=<id>：只能看到该项目绑定的命名空间，且项目必须对请求者可见；
  - 不带 project：属于跨命名空间的全集群视角，要求 ops.k8s.manage。

注意这道边界只对**不持有 ops.k8s.manage** 的用户生效。持有该权限即平台级视角，
可访问任意集群任意命名空间——这是产品上有意的定位，不是安全边界。

ops.k8s.workspace.manage / ops.k8s.project.manage 只回答「能做什么」，不放大
「能看到谁的」：它们的作用域一律由成员关系收敛，详见 has_platform_scope。
"""
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from rbac.services import user_has_permissions

from .models import K8sProject, K8sWorkspace


def has_platform_scope(user):
    """
    平台级视角只认 ops.k8s.manage。

    这里刻意不把 *.manage 计入：管理权限一旦同时放大可见范围，给某个业务负责人
    ops.k8s.project.manage 就等于交出了全平台所有企业空间下项目的删除权
    （包括 purge 掉别人的命名空间）。管理权限只决定动词，作用域交给成员关系。
    """
    return user_has_permissions(user, ['ops.k8s.manage'])


def visible_workspaces(user):
    """可见的企业空间：平台管理员看全部，其余人只看自己是成员的。"""
    queryset = K8sWorkspace.objects.select_related('cluster')
    if has_platform_scope(user):
        return queryset
    return queryset.filter(members__user=user).distinct()


def visible_projects(user):
    """
    可见的项目：平台管理员看全部，其余人看自己有份的。

    写操作也走这个 queryset（ModelViewSet.get_object 取自 get_queryset），
    因此越界的增删改会在取对象阶段就变成 404，无需在每个 action 里重复判定。
    """
    queryset = K8sProject.objects.select_related('workspace', 'cluster')
    if has_platform_scope(user):
        return queryset
    # 项目成员，或所属企业空间的成员，都能看到该项目
    return queryset.filter(
        Q(members__user=user) | Q(workspace__members__user=user)
    ).distinct()


def _read_param(request, key):
    value = request.query_params.get(key)
    if value:
        return value
    data = getattr(request, 'data', None)
    if isinstance(data, dict):
        return data.get(key)
    return None


def resolve_scope(request, cluster, fallback_namespace='default'):
    """
    解析本次请求允许访问的命名空间，返回 (namespace, error_response)。

    error_response 不为 None 时调用方应直接返回它。越权统一用 404 而不是 403，
    避免通过状态码探测出某个项目 ID 是否存在。
    """
    project_id = _read_param(request, 'project')

    if project_id:
        project = visible_projects(request.user).filter(pk=project_id, cluster=cluster).first()
        if not project:
            return None, Response(
                {'detail': '项目不存在或无权访问。'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return project.namespace, None

    if not user_has_permissions(request.user, ['ops.k8s.manage']):
        return None, Response(
            {'detail': '缺少集群级访问权限，请通过 project 参数指定要访问的项目。'},
            status=status.HTTP_403_FORBIDDEN,
        )

    return _read_param(request, 'namespace') or fallback_namespace, None


def require_cluster_scope(request):
    """
    集群级资源（节点、PV、StorageClass、集群概览）没有命名空间维度，
    无法按项目收敛，因此一律要求 ops.k8s.manage。返回 None 表示放行。
    """
    if user_has_permissions(request.user, ['ops.k8s.manage']):
        return None
    return Response(
        {'detail': '集群级资源需要 ops.k8s.manage 权限。'},
        status=status.HTTP_403_FORBIDDEN,
    )
