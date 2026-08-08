"""
K8sClusterViewSet 的 resource 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import logging
import yaml
from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response

from .demo import DEMO_CONFIGMAPS, DEMO_CRONJOBS, DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_INGRESSES, DEMO_JOBS, DEMO_NAMESPACES, DEMO_NODES, DEMO_PODS, DEMO_PVCS, DEMO_PVS, DEMO_SECRETS, DEMO_SERVICES, DEMO_STATEFULSETS, DEMO_STORAGECLASSES, _get_demo_state
from . import client as _client_mod

logger = logging.getLogger(__name__)


class ResourceActionsMixin:
    def _build_demo_yaml(self, resource_type, name, namespace, demo_list):
        """从 demo 数据生成模拟的 YAML"""
        item = None
        for d in demo_list:
            if d.get('name') == name:
                if namespace and namespace != '_all' and d.get('namespace') and d['namespace'] != namespace:
                    continue
                item = d
                break

        if not item:
            item = demo_list[0] if demo_list else {'name': name}

        # 构建一个类似真实 K8s YAML 的结构
        api_version_map = {
            'pod': 'v1', 'service': 'v1', 'namespace': 'v1', 'node': 'v1',
            'configmap': 'v1', 'secret': 'v1', 'pv': 'v1', 'pvc': 'v1',
            'deployment': 'apps/v1', 'statefulset': 'apps/v1', 'daemonset': 'apps/v1',
            'job': 'batch/v1', 'cronjob': 'batch/v1',
            'ingress': 'networking.k8s.io/v1', 'storageclass': 'storage.k8s.io/v1',
        }
        kind_map = {
            'pod': 'Pod', 'service': 'Service', 'namespace': 'Namespace', 'node': 'Node',
            'configmap': 'ConfigMap', 'secret': 'Secret', 'pv': 'PersistentVolume',
            'pvc': 'PersistentVolumeClaim', 'deployment': 'Deployment',
            'statefulset': 'StatefulSet', 'daemonset': 'DaemonSet',
            'job': 'Job', 'cronjob': 'CronJob', 'ingress': 'Ingress',
            'storageclass': 'StorageClass',
        }

        metadata = {'name': item.get('name', name)}
        if item.get('namespace'):
            metadata['namespace'] = item['namespace']
        if item.get('labels'):
            metadata['labels'] = item['labels']
        if item.get('created'):
            metadata['creationTimestamp'] = item['created']

        result = {
            'apiVersion': api_version_map.get(resource_type, 'v1'),
            'kind': kind_map.get(resource_type, resource_type.capitalize()),
            'metadata': metadata,
        }

        # 根据资源类型添加 spec
        if resource_type == 'deployment':
            result['spec'] = {
                'replicas': item.get('replicas', 1),
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', 'nginx:latest'), 'ports': [{'containerPort': 80}]}]},
                },
            }
            result['status'] = {'replicas': item.get('replicas', 1), 'readyReplicas': item.get('ready_replicas', 0), 'availableReplicas': item.get('available_replicas', 0)}
        elif resource_type == 'pod':
            result['spec'] = {
                'containers': [{'name': c.get('name', 'main'), 'image': c.get('image', 'nginx:latest')} for c in item.get('containers', [{'name': 'main', 'image': 'nginx'}])],
                'nodeName': item.get('node', ''),
            }
            result['status'] = {'phase': item.get('status', 'Running'), 'podIP': item.get('ip', '')}
        elif resource_type == 'service':
            result['spec'] = {
                'type': item.get('type', 'ClusterIP'),
                'clusterIP': item.get('cluster_ip', ''),
                'ports': [{'port': 80, 'protocol': 'TCP'}],
                'selector': {'app': item.get('name', name)},
            }
        elif resource_type == 'node':
            result['spec'] = {}
            result['status'] = {
                'conditions': [{'type': 'Ready', 'status': 'True' if item.get('status') == 'Ready' else 'False'}],
                'nodeInfo': {'kubeletVersion': item.get('version', ''), 'osImage': item.get('os_image', '')},
                'addresses': [{'type': 'InternalIP', 'address': item.get('internal_ip', '')}],
                'capacity': {'cpu': item.get('cpu', ''), 'memory': item.get('memory', '')},
            }
        elif resource_type == 'namespace':
            result['status'] = {'phase': item.get('status', 'Active')}
        elif resource_type == 'statefulset':
            result['spec'] = {
                'replicas': item.get('replicas', 1),
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', 'nginx:latest')}]},
                },
            }
            result['status'] = {'replicas': item.get('replicas', 1), 'readyReplicas': item.get('ready_replicas', 0)}
        elif resource_type == 'daemonset':
            result['spec'] = {
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', '')}]},
                },
            }
            result['status'] = {'desiredNumberScheduled': item.get('desired', 0), 'currentNumberScheduled': item.get('current', 0), 'numberReady': item.get('ready', 0)}
        elif resource_type == 'job':
            result['spec'] = {
                'template': {'spec': {'containers': [{'name': 'job', 'image': item.get('images', '')}], 'restartPolicy': 'Never'}},
            }
            result['status'] = {'succeeded': 1 if item.get('status') == 'Complete' else 0}
        elif resource_type == 'cronjob':
            result['spec'] = {
                'schedule': item.get('schedule', ''),
                'suspend': item.get('suspend', False),
                'jobTemplate': {
                    'spec': {'template': {'spec': {'containers': [{'name': 'job', 'image': item.get('images', '')}], 'restartPolicy': 'Never'}}},
                },
            }
        elif resource_type == 'ingress':
            result['spec'] = {
                'ingressClassName': item.get('class', 'nginx'),
                'rules': [{'host': h.strip(), 'http': {'paths': [{'path': '/', 'pathType': 'Prefix', 'backend': {'service': {'name': item.get('name', ''), 'port': {'number': 80}}}}]}} for h in item.get('hosts', '').split(',') if h.strip()],
            }
        elif resource_type == 'pv':
            result['spec'] = {
                'capacity': {'storage': item.get('capacity', '')},
                'accessModes': [item.get('access_modes', 'ReadWriteOnce')],
                'persistentVolumeReclaimPolicy': item.get('reclaim_policy', 'Retain'),
                'storageClassName': item.get('storage_class', ''),
            }
            if item.get('claim'):
                parts = item['claim'].split('/')
                result['spec']['claimRef'] = {'namespace': parts[0] if len(parts) > 1 else '', 'name': parts[-1]}
            result['status'] = {'phase': item.get('status', '')}
        elif resource_type == 'pvc':
            result['spec'] = {
                'accessModes': [item.get('access_modes', 'ReadWriteOnce')],
                'storageClassName': item.get('storage_class', ''),
                'resources': {'requests': {'storage': item.get('capacity', '')}},
                'volumeName': item.get('volume', ''),
            }
            result['status'] = {'phase': item.get('status', '')}
        elif resource_type == 'storageclass':
            result['provisioner'] = item.get('provisioner', '')
            result['reclaimPolicy'] = item.get('reclaim_policy', 'Delete')
            result['volumeBindingMode'] = item.get('binding_mode', 'Immediate')
            result['allowVolumeExpansion'] = item.get('allow_expansion', False)
        elif resource_type == 'configmap':
            payload = item.get('data_payload') or {f'key{i+1}': f'value{i+1}' for i in range(item.get('data_count', 1))}
            result['data'] = payload
        elif resource_type == 'secret':
            payload = item.get('data_payload') or {f'key{i+1}': f'value{i+1}' for i in range(item.get('data_count', 1))}
            result['type'] = item.get('type', 'Opaque')
            result['stringData'] = payload

        return yaml.dump(result, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @action(detail=True, methods=['get'], url_path='resource_yaml')
    def resource_yaml(self, request, pk=None):
        """获取指定资源的 YAML 定义"""
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error

        if not resource_type or not name:
            return Response({'detail': '缺少 type 或 name 参数'}, status=400)

        if _client_mod._is_demo(cluster):
            demo_map = {
                'node': DEMO_NODES, 'namespace': DEMO_NAMESPACES, 'pod': DEMO_PODS,
                'deployment': _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS), 'statefulset': _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS),
                'daemonset': DEMO_DAEMONSETS, 'job': DEMO_JOBS, 'cronjob': DEMO_CRONJOBS,
                'service': DEMO_SERVICES, 'ingress': DEMO_INGRESSES,
                'pv': DEMO_PVS, 'pvc': DEMO_PVCS, 'storageclass': DEMO_STORAGECLASSES,
                'configmap': _get_demo_state(cluster.id, 'configmaps', DEMO_CONFIGMAPS), 'secret': _get_demo_state(cluster.id, 'secrets', DEMO_SECRETS),
            }
            demo_list = demo_map.get(resource_type, [])
            yaml_content = self._build_demo_yaml(resource_type, name, namespace, demo_list)
            return Response({'yaml': yaml_content})

        try:
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            apps_v1 = k8s.AppsV1Api()
            batch_v1 = k8s.BatchV1Api()
            net_v1 = k8s.NetworkingV1Api()
            storage_v1 = k8s.StorageV1Api()

            read_funcs = {
                'node': lambda: v1.read_node(name),
                'namespace': lambda: v1.read_namespace(name),
                'pod': lambda: v1.read_namespaced_pod(name, namespace),
                'service': lambda: v1.read_namespaced_service(name, namespace),
                'deployment': lambda: apps_v1.read_namespaced_deployment(name, namespace),
                'statefulset': lambda: apps_v1.read_namespaced_stateful_set(name, namespace),
                'daemonset': lambda: apps_v1.read_namespaced_daemon_set(name, namespace),
                'job': lambda: batch_v1.read_namespaced_job(name, namespace),
                'cronjob': lambda: batch_v1.read_namespaced_cron_job(name, namespace),
                'ingress': lambda: net_v1.read_namespaced_ingress(name, namespace),
                'pv': lambda: v1.read_persistent_volume(name),
                'pvc': lambda: v1.read_namespaced_persistent_volume_claim(name, namespace),
                'storageclass': lambda: storage_v1.read_storage_class(name),
                'configmap': lambda: v1.read_namespaced_config_map(name, namespace),
                'secret': lambda: v1.read_namespaced_secret(name, namespace),
            }

            read_func = read_funcs.get(resource_type)
            if not read_func:
                return Response({'detail': f'不支持的资源类型: {resource_type}'}, status=400)

            resource_obj = read_func()
            api_client = k8s.ApiClient()
            resource_dict = api_client.sanitize_for_serialization(resource_obj)
            yaml_content = yaml.dump(resource_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return Response({'yaml': yaml_content})
        except Exception as e:
            return Response({'detail': f'获取 YAML 失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def resource_events(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        resource_name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error

        if _client_mod._is_demo(cluster):
            import datetime as _dt, random as _rand
            now = _dt.datetime.now(_dt.timezone.utc)
            events = []
            # Generate plausible events
            normal_events = [
                ('Scheduled', f'Successfully assigned {namespace}/{resource_name} to node-01'),
                ('Pulling', f'Pulling image for {resource_name}'),
                ('Pulled', f'Successfully pulled image'),
                ('Created', f'Created container for {resource_name}'),
                ('Started', f'Started container for {resource_name}'),
                ('ScalingReplicaSet', f'Scaled up replica set {resource_name}-7c5b4f9d8 to 2'),
            ]
            warning_events = [
                ('BackOff', f'Back-off restarting failed container in pod {resource_name}'),
                ('Unhealthy', f'Readiness probe failed: connection refused'),
                ('FailedScheduling', f'0/4 nodes are available: insufficient memory'),
            ]

            # Add 3-6 normal events
            for i, (reason, msg) in enumerate(normal_events[:_rand.randint(3, 5)]):
                t = (now - _dt.timedelta(hours=_rand.randint(1, 48))).isoformat()
                events.append({
                    'type': 'Normal',
                    'reason': reason,
                    'message': msg,
                    'first_time': t,
                    'last_time': t,
                    'count': 1,
                    'source': 'kubelet, node-01',
                })

            # Maybe add 1 warning for some resources
            if resource_name in ('web-frontend', 'debug-pod-manual') or 'pending' in resource_name.lower():
                warn = warning_events[_rand.randint(0, len(warning_events) - 1)]
                t = (now - _dt.timedelta(minutes=_rand.randint(5, 120))).isoformat()
                events.append({
                    'type': 'Warning',
                    'reason': warn[0],
                    'message': warn[1],
                    'first_time': t,
                    'last_time': t,
                    'count': _rand.randint(1, 8),
                    'source': 'kubelet, node-02',
                })

            # Sort by last_time desc
            events.sort(key=lambda e: e['last_time'], reverse=True)
            return Response(events)

        try:
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kind_map = {
                'pod': 'Pod', 'node': 'Node', 'deployment': 'Deployment',
                'statefulset': 'StatefulSet', 'daemonset': 'DaemonSet',
                'job': 'Job', 'cronjob': 'CronJob', 'service': 'Service',
                'ingress': 'Ingress', 'pvc': 'PersistentVolumeClaim',
                'pv': 'PersistentVolume', 'configmap': 'ConfigMap', 'secret': 'Secret',
            }
            kind = kind_map.get(resource_type, resource_type)

            # Cluster-scoped resources (Node, PV)
            if resource_type in ('node', 'pv'):
                event_list = v1.list_event_for_all_namespaces(
                    field_selector=f'involvedObject.name={resource_name},involvedObject.kind={kind}'
                )
            else:
                event_list = v1.list_namespaced_event(
                    namespace,
                    field_selector=f'involvedObject.name={resource_name},involvedObject.kind={kind}'
                )
            events = []
            for e in event_list.items:
                events.append({
                    'type': e.type or 'Normal',
                    'reason': e.reason or '',
                    'message': e.message or '',
                    'first_time': e.first_timestamp.isoformat() if e.first_timestamp else '',
                    'last_time': e.last_timestamp.isoformat() if e.last_timestamp else '',
                    'count': e.count or 1,
                    'source': f'{e.source.component}, {e.source.host}' if e.source else '',
                })
            events.sort(key=lambda ev: ev['last_time'], reverse=True)
            return Response(events)
        except Exception as e:
            logger.warning('K8s resource events degraded for cluster=%s resource=%s/%s: %s', cluster.id, resource_type, resource_name, e)
            return Response([])
