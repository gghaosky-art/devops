"""
集群资源与概览的缓存键、读写与失效。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import logging
from django.core.cache import cache
from .client import K8S_DEMO_STATE_CACHE_TTL, K8S_RESOURCE_CACHE_TTL, K8S_STALE_RESOURCE_CACHE_TTL

logger = logging.getLogger(__name__)


def _summary_cache_key(cluster_id):
    return f'ops:k8s:summary:{cluster_id}'


def _summary_stale_cache_key(cluster_id):
    return f'ops:k8s:summary-stale:{cluster_id}'


def _clear_summary_cache(cluster_or_id):
    cluster_id = cluster_or_id.pk if hasattr(cluster_or_id, 'pk') else cluster_or_id
    if cluster_id:
        cache.delete(_summary_cache_key(cluster_id))


def _resource_cache_version_key(cluster_id):
    return f'ops:k8s:list-version:{cluster_id}'


def _get_resource_cache_version(cluster_id):
    cache_key = _resource_cache_version_key(cluster_id)
    version = cache.get(cache_key)
    if version is None:
        version = 1
        cache.set(cache_key, version, K8S_DEMO_STATE_CACHE_TTL)
    return version


def _bump_resource_cache_version(cluster_or_id):
    cluster_id = cluster_or_id.pk if hasattr(cluster_or_id, 'pk') else cluster_or_id
    if not cluster_id:
        return
    cache_key = _resource_cache_version_key(cluster_id)
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 2, K8S_DEMO_STATE_CACHE_TTL)
        return
    try:
        cache.incr(cache_key)
    except Exception:
        cache.set(cache_key, int(current) + 1, K8S_DEMO_STATE_CACHE_TTL)


def _resource_cache_key(cluster_id, resource, namespace=''):
    version = _get_resource_cache_version(cluster_id)
    scope = namespace or '_cluster'
    return f'ops:k8s:list:{cluster_id}:{version}:{resource}:{scope}'


def _resource_stale_cache_key(cluster_id, resource, namespace=''):
    scope = namespace or '_cluster'
    return f'ops:k8s:list-stale:{cluster_id}:{resource}:{scope}'


def _get_or_set_resource_cache(cluster, resource, namespace, loader, default=None):
    cache_key = _resource_cache_key(cluster.id, resource, namespace)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    stale_key = _resource_stale_cache_key(cluster.id, resource, namespace)
    fallback = [] if default is None else default
    try:
        data = loader()
    except Exception as exc:
        stale = cache.get(stale_key)
        if stale is not None:
            logger.warning(
                'K8s resource fallback to stale cache for cluster=%s resource=%s namespace=%s: %s',
                cluster.id,
                resource,
                namespace or '_cluster',
                exc,
            )
            return stale
        logger.warning(
            'K8s resource fallback to default for cluster=%s resource=%s namespace=%s: %s',
            cluster.id,
            resource,
            namespace or '_cluster',
            exc,
        )
        return fallback

    cache.set(cache_key, data, K8S_RESOURCE_CACHE_TTL)
    cache.set(stale_key, data, K8S_STALE_RESOURCE_CACHE_TTL)
    return data


def _invalidate_cluster_runtime_cache(cluster_or_id):
    _clear_summary_cache(cluster_or_id)
    _bump_resource_cache_version(cluster_or_id)
