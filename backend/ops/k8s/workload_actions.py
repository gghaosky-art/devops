"""
K8sClusterViewSet 的 workload 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import logging
from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache

from .demo import DEMO_CRONJOBS, DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_JOBS, DEMO_NODES, DEMO_PODS, DEMO_STATEFULSETS, _get_demo_state, _set_demo_state
from .items import _filter_by_ns
from . import cache as _cache_mod
from . import client as _client_mod

logger = logging.getLogger(__name__)


class WorkloadActionsMixin:
    @action(detail=True, methods=['get'])
    def deployments(self, request, pk=None):
        """获取 Deployment 列表"""
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                if namespace == '_all':
                    dep_list = apps_v1.list_deployment_for_all_namespaces()
                else:
                    dep_list = apps_v1.list_namespaced_deployment(namespace=namespace)

                return [{
                    'name': dep.metadata.name,
                    'namespace': dep.metadata.namespace,
                    'replicas': dep.spec.replicas or 0,
                    'ready_replicas': dep.status.ready_replicas or 0,
                    'available_replicas': dep.status.available_replicas or 0,
                    'images': ', '.join([c.image for c in dep.spec.template.spec.containers]),
                    'created': dep.metadata.creation_timestamp.isoformat() if dep.metadata.creation_timestamp else '',
                } for dep in dep_list.items]

            data = _get_or_set_resource_cache(cluster, 'deployments', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Deployment 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def statefulsets(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                items = (apps_v1.list_stateful_set_for_all_namespaces() if namespace == '_all'
                         else apps_v1.list_namespaced_stateful_set(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'replicas': i.spec.replicas or 0, 'ready_replicas': i.status.ready_replicas or 0,
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'statefulsets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def daemonsets(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_DAEMONSETS, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                items = (apps_v1.list_daemon_set_for_all_namespaces() if namespace == '_all'
                         else apps_v1.list_namespaced_daemon_set(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'desired': i.status.desired_number_scheduled or 0, 'current': i.status.current_number_scheduled or 0,
                         'ready': i.status.number_ready or 0,
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'node_selector': str(i.spec.template.spec.node_selector or ''),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'daemonsets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def jobs(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_JOBS, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                batch_v1 = k8s.BatchV1Api()
                items = (batch_v1.list_job_for_all_namespaces() if namespace == '_all'
                         else batch_v1.list_namespaced_job(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'completions': f'{i.status.succeeded or 0}/{i.spec.completions or 1}',
                         'duration': '', 'status': 'Complete' if (i.status.succeeded or 0) >= (i.spec.completions or 1) else 'Running',
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'jobs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def cronjobs(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            return Response(_filter_by_ns(DEMO_CRONJOBS, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                batch_v1 = k8s.BatchV1Api()
                items = (batch_v1.list_cron_job_for_all_namespaces() if namespace == '_all'
                         else batch_v1.list_namespaced_cron_job(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'schedule': i.spec.schedule, 'suspend': i.spec.suspend or False,
                         'active': len(i.status.active or []),
                         'last_schedule': i.status.last_schedule_time.isoformat() if i.status.last_schedule_time else '',
                         'images': ', '.join([c.image for c in i.spec.job_template.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'cronjobs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='scale_workload')
    def scale_workload(self, request, pk=None):
        cluster = self.get_object()
        workload_type = request.data.get('workload_type', '')
        name = request.data.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        replicas = request.data.get('replicas')
        if workload_type not in ('deployment', 'statefulset'):
            return Response({'detail': 'Only Deployment and StatefulSet scaling is supported'}, status=400)
        if not name:
            return Response({'detail': 'Missing name parameter'}, status=400)
        try:
            replicas = int(replicas)
        except (TypeError, ValueError):
            return Response({'detail': 'replicas must be an integer'}, status=400)
        if replicas < 0:
            return Response({'detail': 'replicas must be greater than or equal to 0'}, status=400)

        if _client_mod._is_demo(cluster):
            cache_name = 'deployments' if workload_type == 'deployment' else 'statefulsets'
            defaults = DEMO_DEPLOYMENTS if workload_type == 'deployment' else DEMO_STATEFULSETS
            items = _get_demo_state(cluster.id, cache_name, defaults)
            for item in items:
                if item.get('name') == name and item.get('namespace') == namespace:
                    item['replicas'] = replicas
                    item['ready_replicas'] = min(item.get('ready_replicas', 0), replicas)
                    if workload_type == 'deployment':
                        item['available_replicas'] = min(item.get('available_replicas', item.get('ready_replicas', 0)), replicas)
                    _set_demo_state(cluster.id, cache_name, items)
                    _cache_mod._invalidate_cluster_runtime_cache(cluster)
                    return Response({'success': True, 'message': f'{name} scaled to {replicas} replicas'})
            return Response({'detail': f'Resource not found: {workload_type}/{namespace}/{name}'}, status=404)

        try:
            k8s = _client_mod._get_k8s_client(cluster)
            apps_v1 = k8s.AppsV1Api()
            body = {'spec': {'replicas': replicas}}
            if workload_type == 'deployment':
                apps_v1.patch_namespaced_deployment_scale(name, namespace, body)
            else:
                apps_v1.patch_namespaced_stateful_set_scale(name, namespace, body)
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'{name} scaled to {replicas} replicas'})
        except Exception as e:
            return Response({'detail': f'Scale failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def workload_pods(self, request, pk=None):
        cluster = self.get_object()
        workload_type = request.query_params.get('workload_type', '')
        workload_name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error

        if _client_mod._is_demo(cluster):
            # Demo: match pods whose name starts with the workload name
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            prefix = workload_name
            pods = []
            for p in DEMO_PODS:
                if p['name'].startswith(prefix) and (namespace == '_all' or p['namespace'] == namespace):
                    created = _dt.datetime.fromisoformat(p['created'])
                    age_delta = now - created
                    days = age_delta.days
                    hours = age_delta.seconds // 3600
                    age_str = f'{days}d' if days > 0 else f'{hours}h'
                    host_ip = ''
                    for n in DEMO_NODES:
                        if n['name'] == p.get('node', ''):
                            host_ip = n['internal_ip']
                            break
                    containers = p.get('containers', [])
                    cpu_req = '100m'
                    mem_req = '128Mi'
                    if containers:
                        img = containers[0].get('image', '')
                        if 'mysql' in img: cpu_req, mem_req = '500m', '1Gi'
                        elif 'redis' in img: cpu_req, mem_req = '250m', '256Mi'
                        elif 'prometheus' in img: cpu_req, mem_req = '500m', '512Mi'
                        elif 'nginx' in img: cpu_req, mem_req = '100m', '128Mi'
                    pods.append({
                        'name': p['name'],
                        'namespace': p['namespace'],
                        'status': p['status'],
                        'node': p.get('node', ''),
                        'pod_ip': p.get('ip', ''),
                        'host_ip': host_ip,
                        'containers': [c['name'] for c in containers],
                        'restarts': p.get('restarts', 0),
                        'cpu_request': cpu_req,
                        'memory_request': mem_req,
                        'age': age_str,
                        'created': p['created'],
                    })
            return Response(pods)

        try:
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            apps_v1 = k8s.AppsV1Api()
            batch_v1 = k8s.BatchV1Api()

            # Get label selector from the workload
            label_selector = ''
            if workload_type == 'deployment':
                obj = apps_v1.read_namespaced_deployment(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'statefulset':
                obj = apps_v1.read_namespaced_stateful_set(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'daemonset':
                obj = apps_v1.read_namespaced_daemon_set(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'job':
                label_selector = f'job-name={workload_name}'
            elif workload_type == 'cronjob':
                job_list = batch_v1.list_namespaced_job(namespace)
                job_names = {
                    job.metadata.name
                    for job in job_list.items
                    if any(
                        ref.kind == 'CronJob' and ref.name == workload_name
                        for ref in (job.metadata.owner_references or [])
                    )
                }
                if not job_names:
                    return Response([])
                pod_items = v1.list_namespaced_pod(namespace).items
                pod_list_items = [
                    pod for pod in pod_items
                    if (pod.metadata.labels or {}).get('job-name') in job_names
                ]
            if workload_type != 'cronjob':
                pod_list_items = v1.list_namespaced_pod(namespace, label_selector=label_selector).items
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            pods = []
            for p in pod_list_items:
                age_delta = now - p.metadata.creation_timestamp.replace(tzinfo=_dt.timezone.utc)
                days = age_delta.days
                hours = age_delta.seconds // 3600
                age_str = f'{days}d' if days > 0 else f'{hours}h'
                restarts = sum(cs.restart_count for cs in (p.status.container_statuses or []))
                containers = [c.name for c in p.spec.containers]
                cpu_req = '0m'
                mem_req = '0Mi'
                if p.spec.containers:
                    res = p.spec.containers[0].resources
                    if res and res.requests:
                        cpu_req = res.requests.get('cpu', '0m')
                        mem_req = res.requests.get('memory', '0Mi')
                pods.append({
                    'name': p.metadata.name,
                    'namespace': p.metadata.namespace,
                    'status': p.status.phase,
                    'node': p.spec.node_name or '',
                    'pod_ip': p.status.pod_ip or '',
                    'host_ip': p.status.host_ip or '',
                    'containers': containers,
                    'restarts': restarts,
                    'cpu_request': cpu_req,
                    'memory_request': mem_req,
                    'age': age_str,
                    'created': p.metadata.creation_timestamp.isoformat(),
                })
            return Response(pods)
        except Exception as e:
            logger.warning('K8s workload pods degraded for cluster=%s workload=%s/%s: %s', cluster.id, workload_type, workload_name, e)
            return Response([])
