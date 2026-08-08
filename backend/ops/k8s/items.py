"""
单条资源的序列化与命名空间过滤。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import logging
from .cache import _get_or_set_resource_cache
from . import client as _client_mod


logger = logging.getLogger(__name__)


def _serialize_pod_item(pod):
    containers = [{
        'name': container.name,
        'image': container.image,
        'ready': False,
    } for container in (pod.spec.containers or [])]
    if pod.status.container_statuses:
        for container_status in pod.status.container_statuses:
            for container in containers:
                if container['name'] == container_status.name:
                    container['ready'] = container_status.ready or False
                    container['restart_count'] = container_status.restart_count or 0
    return {
        'name': pod.metadata.name,
        'namespace': pod.metadata.namespace,
        'status': pod.status.phase,
        'node': pod.spec.node_name or '',
        'ip': pod.status.pod_ip or '',
        'containers': containers,
        'restarts': sum(container.get('restart_count', 0) for container in containers),
        'created': pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else '',
    }


def _serialize_service_item(svc):
    return {
        'name': svc.metadata.name,
        'namespace': svc.metadata.namespace,
        'type': svc.spec.type,
        'cluster_ip': svc.spec.cluster_ip or '',
        'external_ip': ','.join(svc.spec.external_i_ps or []) if svc.spec.external_i_ps else '',
        'ports': ', '.join([
            f"{port.port}{'->'+str(port.node_port) if port.node_port else ''}/{port.protocol}"
            for port in (svc.spec.ports or [])
        ]),
        'created': svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else '',
    }


def _serialize_deployment_item(dep):
    return {
        'name': dep.metadata.name,
        'namespace': dep.metadata.namespace,
        'replicas': dep.spec.replicas or 0,
        'ready_replicas': dep.status.ready_replicas or 0,
        'available_replicas': dep.status.available_replicas or 0,
        'images': ', '.join([container.image for container in dep.spec.template.spec.containers]),
        'created': dep.metadata.creation_timestamp.isoformat() if dep.metadata.creation_timestamp else '',
    }


def _serialize_node_item(node):
    conditions = {condition.type: condition.status for condition in (node.status.conditions or [])}
    roles = ','.join([
        label.replace('node-role.kubernetes.io/', '')
        for label in (node.metadata.labels or {})
        if label.startswith('node-role.kubernetes.io/')
    ])
    capacity = node.status.capacity or {}
    return {
        'name': node.metadata.name,
        'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
        'roles': roles or 'worker',
        'version': node.status.node_info.kubelet_version if node.status.node_info else '',
        'internal_ip': next((address.address for address in (node.status.addresses or []) if address.type == 'InternalIP'), ''),
        'os_image': node.status.node_info.os_image if node.status.node_info else '',
        'cpu': capacity.get('cpu', ''),
        'memory': capacity.get('memory', ''),
        'pods_count': 0,
        'age': '',
        'created': node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else '',
    }


def _filter_by_ns(data, namespace):
    if namespace == '_all':
        return data
    return [d for d in data if d['namespace'] == namespace]


def _limit_namespaces(items, namespace):
    """按项目范围收敛命名空间列表，'_all' 表示不收敛（全集群视角）。"""
    if not namespace or namespace == '_all':
        return items
    return [item for item in items if item.get('name') == namespace]


def _selected_namespaces(namespaces):
    return [str(item).strip() for item in (namespaces or []) if str(item).strip() and str(item).strip() != '_all']


def _collect_namespaced_resource(cluster, resource, namespaces, demo_items, live_loader, default=None):
    selected = _selected_namespaces(namespaces)
    if _client_mod._is_demo(cluster):
        data = list(demo_items)
        if not selected:
            return data
        return [item for item in data if item.get('namespace') in selected]
    if selected:
        data = []
        for namespace in selected:
            data.extend(_get_or_set_resource_cache(cluster, resource, namespace, lambda ns=namespace: live_loader(ns), default=default or []))
        return data
    return _get_or_set_resource_cache(cluster, resource, '_all', lambda: live_loader('_all'), default=default or [])


def _safe_collection(label, loader, default=None, issues=None):
    fallback = [] if default is None else default
    try:
        return loader()
    except Exception as exc:
        if issues is not None:
            issues.append(label)
        logger.warning('K8s summary skipped %s: %s', label, exc)
        return fallback
