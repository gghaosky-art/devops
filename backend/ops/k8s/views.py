"""
K8s 集群 ViewSet 的组装。

各领域的 action 拆在同目录的 *_actions.py 中，这里只负责组合、
声明权限映射和集群自身的增删改。URL 注册路径保持不变。
"""

from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from rbac.permissions import RBACPermissionMixin

from ops.models import K8sCluster
from ops.serializers import K8sClusterSerializer
from .client import api_server_warnings
from .cluster_actions import ClusterActionsMixin
from .config_actions import ConfigActionsMixin
from .network_actions import NetworkActionsMixin
from .node_actions import NodeActionsMixin
from .pod_actions import PodActionsMixin
from .resource_actions import ResourceActionsMixin
from .storage_actions import StorageActionsMixin
from .workload_actions import WorkloadActionsMixin
from . import cache as _cache_mod


class K8sClusterViewSet(
    ClusterActionsMixin,
    NodeActionsMixin,
    PodActionsMixin,
    WorkloadActionsMixin,
    NetworkActionsMixin,
    StorageActionsMixin,
    ConfigActionsMixin,
    ResourceActionsMixin,
    RBACPermissionMixin,
    viewsets.ModelViewSet,
):
    """K8s 集群连接管理"""
    queryset = K8sCluster.objects.all()
    serializer_class = K8sClusterSerializer
    pagination_class = None
    rbac_permissions = {
        'list': ['ops.k8s.view'],
        'retrieve': ['ops.k8s.view'],
        'create': ['ops.k8s.manage'],
        'update': ['ops.k8s.manage'],
        'partial_update': ['ops.k8s.manage'],
        'destroy': ['ops.k8s.manage'],
        'test_connection': ['ops.k8s.manage'],
        'summary': ['ops.k8s.view'],
        'namespaces': ['ops.k8s.view'],
        'pods': ['ops.k8s.view'],
        'services': ['ops.k8s.view'],
        'deployments': ['ops.k8s.view'],
        'restart_pod': ['ops.k8s.manage'],
        'pod_exec': ['ops.k8s.exec'],
        'scale_workload': ['ops.k8s.manage'],
        'nodes': ['ops.k8s.view'],
        'statefulsets': ['ops.k8s.view'],
        'daemonsets': ['ops.k8s.view'],
        'jobs': ['ops.k8s.view'],
        'cronjobs': ['ops.k8s.view'],
        'ingresses': ['ops.k8s.view'],
        'pvs': ['ops.k8s.view'],
        'pvcs': ['ops.k8s.view'],
        'storageclasses': ['ops.k8s.view'],
        'configmaps': ['ops.k8s.view'],
        'secrets': ['ops.k8s.view'],
        'resource_yaml': ['ops.k8s.view'],
        'config_resource_detail': ['ops.k8s.view'],
        'config_resource_preview': ['ops.k8s.manage'],
        'config_resource_update': ['ops.k8s.manage'],
        'config_resource_revisions': ['ops.k8s.view'],
        'config_resource_revision_preview': ['ops.k8s.view'],
        'config_resource_rollback_preview': ['ops.k8s.manage'],
        'config_resource_rollback': ['ops.k8s.manage'],
        'config_resource_rollback_to_revision': ['ops.k8s.manage'],
        'workload_pods': ['ops.k8s.view'],
        'pod_logs': ['ops.k8s.view'],
        'resource_events': ['ops.k8s.view'],
        'adoptable_namespaces': ['ops.k8s.project.manage'],
    }

    # perform_create / perform_update 里赋值，供 create / update 组装 warnings
    _saved_instance = None

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data['warnings'] = self._api_server_warnings()
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response.data['warnings'] = self._api_server_warnings()
        return response

    def _api_server_warnings(self):
        """http 地址等风险不阻断保存，作为提示随响应返回。"""
        instance = self._saved_instance
        if instance is None:
            return []
        return api_server_warnings(instance.api_server, instance.kubeconfig)

    def perform_create(self, serializer):
        instance = serializer.save()
        self._saved_instance = instance
        _cache_mod._invalidate_cluster_runtime_cache(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._saved_instance = instance
        _cache_mod._invalidate_cluster_runtime_cache(instance)

    def perform_destroy(self, instance):
        _cache_mod._invalidate_cluster_runtime_cache(instance)
        try:
            instance.delete()
        except ProtectedError:
            # 企业空间与项目通过 PROTECT 引用集群，直接删会抛 500，这里转成可读提示
            raise ValidationError({
                'detail': '该集群下仍有企业空间或项目，请先删除它们再删除集群。',
            })
