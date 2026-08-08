"""
供平台其他模块读取的只读快照。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

from django.core.cache import cache
from .cache import _clear_summary_cache, _get_or_set_resource_cache, _summary_cache_key, _summary_stale_cache_key

from .demo import DEMO_CONFIGMAPS, DEMO_CRONJOBS, DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_INGRESSES, DEMO_JOBS, DEMO_NODES, DEMO_PODS, DEMO_PVCS, DEMO_SECRETS, DEMO_SERVICES, DEMO_STATEFULSETS, _get_demo_state
from .items import _collect_namespaced_resource, _serialize_deployment_item, _serialize_node_item, _serialize_pod_item, _serialize_service_item
from .summary import _build_unavailable_summary, _cache_summary_snapshot, _is_unreliable_zero_summary
from . import client as _client_mod
from . import summary as _summary_mod


def get_k8s_summary_snapshot(cluster):
    cache_key = _summary_cache_key(cluster.id)
    cached = cache.get(cache_key)
    if cached:
        if _is_unreliable_zero_summary(cached):
            cache.delete(cache_key)
        else:
            return cached
    try:
        summary = _summary_mod._build_demo_summary(cluster) if _client_mod._is_demo(cluster) else _summary_mod._build_live_summary(cluster)
        if cluster.status != 'connected':
            cluster.status = 'connected'
            cluster.save(update_fields=['status'])
            summary['status'] = cluster.status
        return _cache_summary_snapshot(cluster, summary)
    except Exception as exc:
        if cluster.status != 'error':
            cluster.status = 'error'
            cluster.save(update_fields=['status'])
        _clear_summary_cache(cluster)
        fallback = cache.get(_summary_stale_cache_key(cluster.id))
        if fallback is not None:
            return {
                **fallback,
                'degraded': True,
                'status': cluster.status or 'error',
                'alerts': [{'level': 'warning', 'message': 'K8s API is temporarily unavailable; returning the latest cached snapshot'}],
            }
        return _build_unavailable_summary(cluster, str(exc))


def get_k8s_pods_snapshot(cluster, namespaces=None):
    def loader(namespace):
        k8s = _client_mod._get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        pod_list = v1.list_pod_for_all_namespaces() if namespace == '_all' else v1.list_namespaced_pod(namespace=namespace)
        return [_serialize_pod_item(item) for item in pod_list.items]

    return _collect_namespaced_resource(cluster, 'pods', namespaces, DEMO_PODS, loader)


def get_k8s_nodes_snapshot(cluster):
    if _client_mod._is_demo(cluster):
        return list(DEMO_NODES)

    def loader():
        k8s = _client_mod._get_k8s_client(cluster)
        return [_serialize_node_item(item) for item in k8s.CoreV1Api().list_node().items]

    return _get_or_set_resource_cache(cluster, 'nodes', '_all', loader, default=[])


def get_k8s_resource_snapshot(cluster, resource_type, namespaces=None):
    resource_type = str(resource_type or '').strip().lower()
    if resource_type == 'pods':
        return get_k8s_pods_snapshot(cluster, namespaces)
    if resource_type == 'nodes':
        return get_k8s_nodes_snapshot(cluster)

    if resource_type == 'deployments':
        def loader(namespace):
            k8s = _client_mod._get_k8s_client(cluster)
            apps_v1 = k8s.AppsV1Api()
            items = apps_v1.list_deployment_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_deployment(namespace=namespace).items
            return [_serialize_deployment_item(item) for item in items]

        return _collect_namespaced_resource(cluster, 'deployments', namespaces, _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS), loader)

    if resource_type == 'services':
        def loader(namespace):
            k8s = _client_mod._get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            items = v1.list_service_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_service(namespace=namespace).items
            return [_serialize_service_item(item) for item in items]

        return _collect_namespaced_resource(cluster, 'services', namespaces, _get_demo_state(cluster.id, 'services', DEMO_SERVICES), loader)

    namespaced_resources = {
        'statefulsets': (
            _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS),
            lambda apps_v1, namespace: apps_v1.list_stateful_set_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_stateful_set(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'replicas': item.spec.replicas or 0,
                'ready_replicas': item.status.ready_replicas or 0,
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'apps',
        ),
        'daemonsets': (
            DEMO_DAEMONSETS,
            lambda apps_v1, namespace: apps_v1.list_daemon_set_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_daemon_set(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'desired': item.status.desired_number_scheduled or 0,
                'current': item.status.current_number_scheduled or 0,
                'ready': item.status.number_ready or 0,
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'node_selector': str(item.spec.template.spec.node_selector or ''),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'apps',
        ),
        'jobs': (
            DEMO_JOBS,
            lambda batch_v1, namespace: batch_v1.list_job_for_all_namespaces().items if namespace == '_all' else batch_v1.list_namespaced_job(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'completions': f'{item.status.succeeded or 0}/{item.spec.completions or 1}',
                'duration': '',
                'status': 'Complete' if (item.status.succeeded or 0) >= (item.spec.completions or 1) else 'Running',
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'batch',
        ),
        'cronjobs': (
            DEMO_CRONJOBS,
            lambda batch_v1, namespace: batch_v1.list_cron_job_for_all_namespaces().items if namespace == '_all' else batch_v1.list_namespaced_cron_job(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'schedule': item.spec.schedule,
                'suspend': item.spec.suspend or False,
                'active': len(item.status.active or []),
                'last_schedule': item.status.last_schedule_time.isoformat() if item.status.last_schedule_time else '',
                'images': ', '.join([container.image for container in item.spec.job_template.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'batch',
        ),
        'ingresses': (
            DEMO_INGRESSES,
            lambda net_v1, namespace: net_v1.list_ingress_for_all_namespaces().items if namespace == '_all' else net_v1.list_namespaced_ingress(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'class': item.spec.ingress_class_name or '',
                'hosts': ', '.join([rule.host for rule in (item.spec.rules or []) if rule.host]),
                'address': ', '.join([target.ip or target.hostname or '' for target in (item.status.load_balancer.ingress or [])]) if item.status.load_balancer and item.status.load_balancer.ingress else '',
                'ports': '80, 443' if item.spec.tls else '80',
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'networking',
        ),
        'pvcs': (
            DEMO_PVCS,
            lambda v1, namespace: v1.list_persistent_volume_claim_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_persistent_volume_claim(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'status': item.status.phase,
                'volume': item.spec.volume_name or '',
                'capacity': (item.status.capacity or {}).get('storage', ''),
                'access_modes': ','.join(item.spec.access_modes or []),
                'storage_class': item.spec.storage_class_name or '',
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'core',
        ),
        'configmaps': (
            DEMO_CONFIGMAPS,
            lambda v1, namespace: v1.list_config_map_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_config_map(namespace=namespace).items,
            lambda item: {'name': item.metadata.name, 'namespace': item.metadata.namespace, 'data_count': len(item.data or {}), 'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else ''},
            'core',
        ),
        'secrets': (
            DEMO_SECRETS,
            lambda v1, namespace: v1.list_secret_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_secret(namespace=namespace).items,
            lambda item: {'name': item.metadata.name, 'namespace': item.metadata.namespace, 'type': item.type or '', 'data_count': len(item.data or {}), 'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else ''},
            'core',
        ),
    }
    if resource_type not in namespaced_resources:
        raise ValueError(f'Unsupported K8s resource type: {resource_type}')

    demo_items, loader_fn, serializer, api_kind = namespaced_resources[resource_type]

    def loader(namespace):
        k8s = _client_mod._get_k8s_client(cluster)
        if api_kind == 'apps':
            api = k8s.AppsV1Api()
        elif api_kind == 'batch':
            api = k8s.BatchV1Api()
        elif api_kind == 'networking':
            api = k8s.NetworkingV1Api()
        else:
            api = k8s.CoreV1Api()
        return [serializer(item) for item in loader_fn(api, namespace)]

    return _collect_namespaced_resource(cluster, resource_type, namespaces, demo_items, loader)
