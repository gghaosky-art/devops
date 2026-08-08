"""
K8sClusterViewSet 的 storage 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

from ops.k8s_scope import require_cluster_scope
from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache

from .demo import DEMO_PVCS, DEMO_PVS, DEMO_STORAGECLASSES
from .items import _filter_by_ns
from . import client as _client_mod


class StorageActionsMixin:
    @action(detail=True, methods=['get'])
    def pvs(self, request, pk=None):
        cluster = self.get_object()
        scope_error = require_cluster_scope(request)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(DEMO_PVS)
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = v1.list_persistent_volume().items
                return [{'name': i.metadata.name, 'capacity': (i.spec.capacity or {}).get('storage', ''),
                         'access_modes': ','.join(i.spec.access_modes or []),
                         'reclaim_policy': i.spec.persistent_volume_reclaim_policy or '',
                         'status': i.status.phase, 'claim': f'{i.spec.claim_ref.namespace}/{i.spec.claim_ref.name}' if i.spec.claim_ref else '',
                         'storage_class': i.spec.storage_class_name or '',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'pvs', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def pvcs(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_PVCS, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_persistent_volume_claim_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_persistent_volume_claim(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'status': i.status.phase, 'volume': i.spec.volume_name or '',
                         'capacity': (i.status.capacity or {}).get('storage', ''),
                         'access_modes': ','.join(i.spec.access_modes or []),
                         'storage_class': i.spec.storage_class_name or '',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'pvcs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def storageclasses(self, request, pk=None):
        cluster = self.get_object()
        scope_error = require_cluster_scope(request)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(DEMO_STORAGECLASSES)
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                storage_v1 = k8s.StorageV1Api()
                items = storage_v1.list_storage_class().items
                return [{'name': i.metadata.name, 'provisioner': i.provisioner,
                         'reclaim_policy': i.reclaim_policy or 'Delete',
                         'binding_mode': i.volume_binding_mode or 'Immediate',
                         'allow_expansion': i.allow_volume_expansion or False,
                         'is_default': (i.metadata.annotations or {}).get('storageclass.kubernetes.io/is-default-class') == 'true',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'storageclasses', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
