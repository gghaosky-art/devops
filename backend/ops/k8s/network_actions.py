"""
K8sClusterViewSet 的 network 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache

from .demo import DEMO_INGRESSES, DEMO_SERVICES, _get_demo_state
from .items import _filter_by_ns
from . import client as _client_mod


class NetworkActionsMixin:
    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        """获取 Service 列表"""
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'services', DEMO_SERVICES), namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                if namespace == '_all':
                    svc_list = v1.list_service_for_all_namespaces()
                else:
                    svc_list = v1.list_namespaced_service(namespace=namespace)

                return [{
                    'name': svc.metadata.name,
                    'namespace': svc.metadata.namespace,
                    'type': svc.spec.type,
                    'cluster_ip': svc.spec.cluster_ip or '',
                    'external_ip': ','.join(svc.spec.external_i_ps or []) if svc.spec.external_i_ps else '',
                    'ports': ', '.join([
                        f"{p.port}{'→'+str(p.node_port) if p.node_port else ''}/{p.protocol}"
                        for p in (svc.spec.ports or [])
                    ]),
                    'created': svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else '',
                } for svc in svc_list.items]

            data = _get_or_set_resource_cache(cluster, 'services', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Service 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def ingresses(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_INGRESSES, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                net_v1 = k8s.NetworkingV1Api()
                items = (net_v1.list_ingress_for_all_namespaces() if namespace == '_all'
                         else net_v1.list_namespaced_ingress(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'class': i.spec.ingress_class_name or '',
                         'hosts': ', '.join([r.host for r in (i.spec.rules or []) if r.host]),
                         'address': ', '.join([lb.ip or lb.hostname or '' for lb in (i.status.load_balancer.ingress or [])]) if i.status.load_balancer and i.status.load_balancer.ingress else '',
                         'ports': '80, 443' if i.spec.tls else '80',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'ingresses', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
