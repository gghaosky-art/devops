"""
K8sClusterViewSet 的 node 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

from ops.k8s_scope import require_cluster_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache

from .demo import DEMO_NODES
from . import client as _client_mod


class NodeActionsMixin:
    @action(detail=True, methods=['get'])
    def nodes(self, request, pk=None):
        """Get node list."""
        cluster = self.get_object()
        scope_error = require_cluster_scope(request)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(DEMO_NODES)
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                node_list = v1.list_node()
                data = []
                for node in node_list.items:
                    conditions = {c.type: c.status for c in (node.status.conditions or [])}
                    roles = ','.join([l.replace('node-role.kubernetes.io/', '') for l in (node.metadata.labels or {}) if l.startswith('node-role.kubernetes.io/')])
                    capacity = node.status.capacity or {}
                    data.append({
                        'name': node.metadata.name,
                        'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
                        'roles': roles or 'worker',
                        'version': node.status.node_info.kubelet_version if node.status.node_info else '',
                        'internal_ip': next((a.address for a in (node.status.addresses or []) if a.type == 'InternalIP'), ''),
                        'os_image': node.status.node_info.os_image if node.status.node_info else '',
                        'cpu': capacity.get('cpu', ''),
                        'memory': capacity.get('memory', ''),
                        'pods_count': 0,
                        'age': '',
                        'created': node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else '',
                    })
                return data

            data = _get_or_set_resource_cache(cluster, 'nodes', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'Failed to load nodes: {str(e)}'}, status=400)
