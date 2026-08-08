"""
集群概览的构建、降级与告警。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

from django.core.cache import cache
from rest_framework import status
from .cache import _summary_cache_key, _summary_stale_cache_key
from .client import K8S_STALE_SUMMARY_CACHE_TTL, K8S_SUMMARY_CACHE_TTL
from .demo import DEMO_CONFIGMAPS, DEMO_CRONJOBS, DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_INGRESSES, DEMO_JOBS, DEMO_NAMESPACES, DEMO_NODES, DEMO_PODS, DEMO_PVCS, DEMO_SECRETS, DEMO_SERVICES, DEMO_STATEFULSETS
from .items import _safe_collection
from . import client as _client_mod


def _count_ready_nodes(nodes):
    ready = 0
    for node in nodes:
        if isinstance(node, dict):
            if node.get('status') == 'Ready':
                ready += 1
            continue
        conditions = {c.type: c.status for c in (node.status.conditions or [])}
        if conditions.get('Ready') == 'True':
            ready += 1
    return ready


def _pod_status_summary(pods):
    abnormal = 0
    restarting = 0
    restarts = 0
    for pod in pods:
        if isinstance(pod, dict):
            status = pod.get('status', '')
            pod_restarts = int(pod.get('restarts', 0) or 0)
        else:
            status = pod.status.phase
            pod_restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))

        if status not in ('Running', 'Succeeded'):
            abnormal += 1
        if pod_restarts > 0:
            restarting += 1
        restarts += pod_restarts
    return abnormal, restarting, restarts


def _build_summary_alerts(ready_nodes, total_nodes, abnormal_pods, restarting_pods, total_restarts, degraded_workloads, pending_pvcs):
    alerts = []
    if total_nodes and ready_nodes < total_nodes:
        alerts.append({'level': 'warning', 'message': f'节点健康不足：{ready_nodes}/{total_nodes} Ready'})
    if abnormal_pods:
        alerts.append({'level': 'danger', 'message': f'存在 {abnormal_pods} 个异常 Pod，需要排查调度或探针'})
    if restarting_pods:
        alerts.append({'level': 'warning', 'message': f'{restarting_pods} 个 Pod 发生重启，总次数 {total_restarts}'})
    if degraded_workloads:
        alerts.append({'level': 'warning', 'message': f'{degraded_workloads} 个工作负载副本未就绪'})
    if pending_pvcs:
        alerts.append({'level': 'warning', 'message': f'{pending_pvcs} 个 PVC 尚未绑定存储'})
    if not alerts:
        alerts.append({'level': 'success', 'message': '集群核心资源状态正常'})
    return alerts


def _build_degraded_summary_alerts(
    ready_nodes,
    total_nodes,
    abnormal_pods,
    restarting_pods,
    total_restarts,
    degraded_workloads,
    pending_pvcs,
    unavailable_resources=None,
):
    alerts = []
    unavailable_resources = unavailable_resources or []
    if unavailable_resources:
        visible = ', '.join(unavailable_resources[:4])
        if len(unavailable_resources) > 4:
            visible = f'{visible} 等 {len(unavailable_resources)} 项'
        alerts.append({'level': 'warning', 'message': f'部分 K8s 资源采集超时，已自动降级：{visible}'})
    alerts.extend(
        _build_summary_alerts(
            ready_nodes,
            total_nodes,
            abnormal_pods,
            restarting_pods,
            total_restarts,
            degraded_workloads,
            pending_pvcs,
        )
    )
    if unavailable_resources:
        alerts = [item for item in alerts if item.get('level') != 'success']
    return alerts or [{'level': 'warning', 'message': '部分 K8s 资源采集超时，已自动降级'}]


def _build_unavailable_summary(cluster, reason=''):
    message = '当前 K8s API 不可用，已返回降级结果'
    if reason:
        message = f'{message}：{reason}'
    return {
        'cluster_name': cluster.name,
        'status': cluster.status or 'error',
        'namespaces_total': 0,
        'nodes_total': 0,
        'nodes_ready': 0,
        'pods_total': 0,
        'pods_abnormal': 0,
        'pods_restarting': 0,
        'total_restarts': 0,
        'services_total': 0,
        'ingresses_total': 0,
        'workloads_total': 0,
        'workloads_degraded': 0,
        'pvcs_total': 0,
        'pvcs_pending': 0,
        'configmaps_total': 0,
        'secrets_total': 0,
        'degraded': True,
        'unavailable_resources': ['cluster'],
        'alerts': [{'level': 'warning', 'message': message}],
    }


def _summary_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _summary_runtime_total(summary):
    return sum(
        _summary_int(summary.get(key))
        for key in (
            'nodes_total',
            'pods_total',
            'services_total',
            'ingresses_total',
            'workloads_total',
            'pvcs_total',
            'configmaps_total',
            'secrets_total',
        )
    )


def _is_unreliable_zero_summary(summary):
    if not isinstance(summary, dict):
        return False
    if not summary.get('degraded'):
        return False
    if _summary_runtime_total(summary) > 0:
        return False
    return bool(summary.get('unavailable_resources'))


def _summary_stale_payload(cluster, fallback):
    return {
        **fallback,
        'degraded': True,
        'status': fallback.get('status') or 'connected',
        'alerts': [{'level': 'warning', 'message': 'K8s API is temporarily unavailable; returning the latest cached snapshot'}],
    }


def _fallback_for_unreliable_zero_summary(cluster, summary):
    fallback = cache.get(_summary_stale_cache_key(cluster.id))
    if fallback is not None:
        return _summary_stale_payload(cluster, fallback)
    return summary


def _cache_summary_snapshot(cluster, summary, *, update_stale=True):
    payload = _fallback_for_unreliable_zero_summary(cluster, summary)
    if _is_unreliable_zero_summary(payload):
        return payload
    cache.set(_summary_cache_key(cluster.id), payload, K8S_SUMMARY_CACHE_TTL)
    if update_stale:
        cache.set(_summary_stale_cache_key(cluster.id), payload, K8S_STALE_SUMMARY_CACHE_TTL)
    return payload


def _build_demo_summary(cluster):
    ready_nodes = _count_ready_nodes(DEMO_NODES)
    abnormal_pods, restarting_pods, total_restarts = _pod_status_summary(DEMO_PODS)
    degraded_workloads = (
        sum(1 for item in DEMO_DEPLOYMENTS if item.get('ready_replicas', 0) < item.get('replicas', 0))
        + sum(1 for item in DEMO_STATEFULSETS if item.get('ready_replicas', 0) < item.get('replicas', 0))
        + sum(1 for item in DEMO_DAEMONSETS if item.get('ready', 0) < item.get('desired', 0))
    )
    pending_pvcs = sum(1 for pvc in DEMO_PVCS if pvc.get('status') != 'Bound')
    return {
        'cluster_name': cluster.name,
        'status': cluster.status or 'connected',
        'namespaces_total': len(DEMO_NAMESPACES),
        'nodes_total': len(DEMO_NODES),
        'nodes_ready': ready_nodes,
        'pods_total': len(DEMO_PODS),
        'pods_abnormal': abnormal_pods,
        'pods_restarting': restarting_pods,
        'total_restarts': total_restarts,
        'services_total': len(DEMO_SERVICES),
        'ingresses_total': len(DEMO_INGRESSES),
        'workloads_total': len(DEMO_DEPLOYMENTS) + len(DEMO_STATEFULSETS) + len(DEMO_DAEMONSETS) + len(DEMO_JOBS) + len(DEMO_CRONJOBS),
        'workloads_degraded': degraded_workloads,
        'pvcs_total': len(DEMO_PVCS),
        'pvcs_pending': pending_pvcs,
        'configmaps_total': len(DEMO_CONFIGMAPS),
        'secrets_total': len(DEMO_SECRETS),
        'alerts': _build_summary_alerts(ready_nodes, len(DEMO_NODES), abnormal_pods, restarting_pods, total_restarts, degraded_workloads, pending_pvcs),
    }


def _build_live_summary(cluster):
    k8s = _client_mod._get_k8s_client(cluster)
    v1 = k8s.CoreV1Api()
    apps_v1 = k8s.AppsV1Api()
    batch_v1 = k8s.BatchV1Api()
    net_v1 = k8s.NetworkingV1Api()
    unavailable_resources = []

    namespaces = _safe_collection('namespaces', lambda: v1.list_namespace().items, issues=unavailable_resources)
    nodes = _safe_collection('nodes', lambda: v1.list_node().items, issues=unavailable_resources)
    pods = _safe_collection('pods', lambda: v1.list_pod_for_all_namespaces().items, issues=unavailable_resources)
    services = _safe_collection('services', lambda: v1.list_service_for_all_namespaces().items, issues=unavailable_resources)
    ingresses = _safe_collection('ingresses', lambda: net_v1.list_ingress_for_all_namespaces().items, issues=unavailable_resources)
    pvcs = _safe_collection('pvcs', lambda: v1.list_persistent_volume_claim_for_all_namespaces().items, issues=unavailable_resources)
    configmaps = _safe_collection('configmaps', lambda: v1.list_config_map_for_all_namespaces().items, issues=unavailable_resources)
    secrets = _safe_collection('secrets', lambda: v1.list_secret_for_all_namespaces().items, issues=unavailable_resources)
    deployments = _safe_collection('deployments', lambda: apps_v1.list_deployment_for_all_namespaces().items, issues=unavailable_resources)
    statefulsets = _safe_collection('statefulsets', lambda: apps_v1.list_stateful_set_for_all_namespaces().items, issues=unavailable_resources)
    daemonsets = _safe_collection('daemonsets', lambda: apps_v1.list_daemon_set_for_all_namespaces().items, issues=unavailable_resources)
    jobs = _safe_collection('jobs', lambda: batch_v1.list_job_for_all_namespaces().items, issues=unavailable_resources)
    cronjobs = _safe_collection('cronjobs', lambda: batch_v1.list_cron_job_for_all_namespaces().items, issues=unavailable_resources)

    ready_nodes = _count_ready_nodes(nodes)
    abnormal_pods, restarting_pods, total_restarts = _pod_status_summary(pods)
    degraded_workloads = (
        sum(1 for item in deployments if (item.status.ready_replicas or 0) < (item.spec.replicas or 0))
        + sum(1 for item in statefulsets if (item.status.ready_replicas or 0) < (item.spec.replicas or 0))
        + sum(1 for item in daemonsets if (item.status.number_ready or 0) < (item.status.desired_number_scheduled or 0))
    )
    pending_pvcs = sum(1 for pvc in pvcs if (pvc.status.phase or '') != 'Bound')

    summary = {
        'cluster_name': cluster.name,
        'status': cluster.status or 'connected',
        'namespaces_total': len(namespaces),
        'nodes_total': len(nodes),
        'nodes_ready': ready_nodes,
        'pods_total': len(pods),
        'pods_abnormal': abnormal_pods,
        'pods_restarting': restarting_pods,
        'total_restarts': total_restarts,
        'services_total': len(services),
        'ingresses_total': len(ingresses),
        'workloads_total': len(deployments) + len(statefulsets) + len(daemonsets) + len(jobs) + len(cronjobs),
        'workloads_degraded': degraded_workloads,
        'pvcs_total': len(pvcs),
        'pvcs_pending': pending_pvcs,
        'configmaps_total': len(configmaps),
        'secrets_total': len(secrets),
        'alerts': _build_degraded_summary_alerts(
            ready_nodes,
            len(nodes),
            abnormal_pods,
            restarting_pods,
            total_restarts,
            degraded_workloads,
            pending_pvcs,
            unavailable_resources=unavailable_resources,
        ),
    }
    if unavailable_resources:
        summary['degraded'] = True
        summary['unavailable_resources'] = unavailable_resources
    return summary
