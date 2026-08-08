"""
K8sClusterViewSet 的 pod 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import logging
from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache

from .demo import DEMO_PODS
from .items import _filter_by_ns
from . import cache as _cache_mod
from . import client as _client_mod

logger = logging.getLogger(__name__)


class PodActionsMixin:
    @action(detail=True, methods=['get'])
    def pods(self, request, pk=None):
        """获取 Pod 列表"""
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_PODS, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                if namespace == '_all':
                    pod_list = v1.list_pod_for_all_namespaces()
                else:
                    pod_list = v1.list_namespaced_pod(namespace=namespace)

                data = []
                for pod in pod_list.items:
                    containers = [{
                        'name': c.name,
                        'image': c.image,
                        'ready': False,
                    } for c in (pod.spec.containers or [])]

                    if pod.status.container_statuses:
                        for cs in pod.status.container_statuses:
                            for c in containers:
                                if c['name'] == cs.name:
                                    c['ready'] = cs.ready or False
                                    c['restart_count'] = cs.restart_count or 0

                    data.append({
                        'name': pod.metadata.name,
                        'namespace': pod.metadata.namespace,
                        'status': pod.status.phase,
                        'node': pod.spec.node_name or '',
                        'ip': pod.status.pod_ip or '',
                        'containers': containers,
                        'restarts': sum(c.get('restart_count', 0) for c in containers),
                        'created': pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else '',
                    })
                return data

            data = _get_or_set_resource_cache(cluster, 'pods', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Pod 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='pods/(?P<pod_name>[^/]+)/restart')
    def restart_pod(self, request, pk=None, pod_name=None):
        """删除 Pod 以触发重启"""
        cluster = self.get_object()
        # 租户边界要先于 demo 分支判定，否则演示集群上的越权请求会被放行
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'Pod {pod_name} 正在重启 [演示模式]'})
        try:
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'Pod {pod_name} 正在重启'})
        except Exception as e:
            return Response({'success': False, 'message': f'重启失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='pod_exec')
    def pod_exec(self, request, pk=None):
        cluster = self.get_object()
        pod_name = request.data.get('pod_name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        container = request.data.get('container', '')
        command = request.data.get('command', 'pwd')
        if not pod_name:
            return Response({'detail': 'Missing pod_name parameter'}, status=400)
        if not command:
            return Response({'detail': 'Missing command parameter'}, status=400)

        if _client_mod._is_demo(cluster):
            output = '\n'.join([
                f'$ {command}',
                f'demo-exec on {pod_name} ({namespace})',
                'uid=1000 gid=1000 groups=1000',
                '/app',
            ])
            return Response({
                'success': True,
                'pod_name': pod_name,
                'namespace': namespace,
                'container': container or 'main',
                'command': command,
                'output': output,
            })

        try:
            from kubernetes.stream import stream

            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kwargs = {
                'name': pod_name,
                'namespace': namespace,
                'command': ['/bin/sh', '-lc', command],
                'stderr': True,
                'stdin': False,
                'stdout': True,
                'tty': False,
            }
            if container:
                kwargs['container'] = container
            output = stream(v1.connect_get_namespaced_pod_exec, **kwargs)
            return Response({
                'success': True,
                'pod_name': pod_name,
                'namespace': namespace,
                'container': container or '',
                'command': command,
                'output': output or '',
            })
        except Exception as e:
            return Response({'detail': f'Pod exec failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def pod_logs(self, request, pk=None):
        cluster = self.get_object()
        pod_name = request.query_params.get('pod_name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        container = request.query_params.get('container', '')
        tail_lines = int(request.query_params.get('tail_lines', 200))

        if _client_mod._is_demo(cluster):
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            lines = []
            for i in range(min(tail_lines, 50)):
                ts = (now - _dt.timedelta(minutes=50 - i)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                if 'nginx' in pod_name:
                    msgs = [
                        f'{ts} 10.244.1.1 - - [GET /api/health HTTP/1.1] 200 15 "-" "kube-probe/1.29"',
                        f'{ts} 10.244.2.5 - - [GET / HTTP/1.1] 200 612 "-" "Mozilla/5.0"',
                        f'{ts} 10.244.1.8 - - [GET /static/css/main.css HTTP/1.1] 304 0',
                        f'{ts} 10.244.3.2 - - [POST /api/data HTTP/1.1] 201 89 "-" "curl/7.88"',
                    ]
                elif 'api' in pod_name:
                    msgs = [
                        f'{ts} INFO  [main] Application started on port 8080',
                        f'{ts} DEBUG [http] GET /api/users -> 200 (12ms)',
                        f'{ts} INFO  [db] Connection pool: active=5, idle=15, total=20',
                        f'{ts} WARN  [cache] Cache miss rate: 15.2%',
                    ]
                elif 'redis' in pod_name:
                    msgs = [
                        f'{ts} # Server initialized',
                        f'{ts} * Ready to accept connections tcp',
                        f'{ts} # 1 changes in 900 seconds. Saving...',
                        f'{ts} * Background saving started by pid 42',
                    ]
                elif 'mysql' in pod_name:
                    msgs = [
                        f'{ts} [Note] [MY-010131] [Server] mysqld: ready for connections. Version: 8.0.36',
                        f'{ts} [Note] [MY-012487] [InnoDB] DDL log recovery: begin',
                        f'{ts} [Note] [MY-012488] [InnoDB] DDL log recovery: end',
                        f"{ts} [Note] [MY-010747] [Server] Plugin 'mysql_native_password' is marked as deprecated",
                    ]
                else:
                    msgs = [
                        f'{ts} level=info msg="Starting process"',
                        f'{ts} level=info msg="Health check passed"',
                        f'{ts} level=debug msg="Processing request" duration=5ms',
                        f'{ts} level=info msg="Metrics collected" count=42',
                    ]
                lines.append(msgs[i % len(msgs)])
            return Response({'logs': '\n'.join(lines), 'container': container or 'main'})

        try:
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kwargs = {'name': pod_name, 'namespace': namespace, 'tail_lines': tail_lines}
            if container:
                kwargs['container'] = container
            log_content = v1.read_namespaced_pod_log(**kwargs)
            return Response({'logs': log_content, 'container': container or ''})
        except Exception as e:
            logger.warning('K8s pod logs degraded for cluster=%s pod=%s namespace=%s: %s', cluster.id, pod_name, namespace, e)
            return Response({'logs': '', 'container': container or '', 'degraded': True})
