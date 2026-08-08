"""
K8sClusterViewSet 的 cluster 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import ssl
from django.core.cache import cache
from ops.k8s_scope import require_cluster_scope
from ops.k8s_scope import resolve_scope
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _clear_summary_cache, _get_or_set_resource_cache, _summary_cache_key, _summary_stale_cache_key
from .client import K8S_SUMMARY_CACHE_TTL
from .demo import DEMO_NAMESPACES
from .items import _limit_namespaces
from .summary import _build_unavailable_summary, _cache_summary_snapshot, _is_unreliable_zero_summary, _summary_stale_payload
from . import cache as _cache_mod
from . import client as _client_mod
from . import summary as _summary_mod


class ClusterActionsMixin:
    @action(detail=True, methods=['get'], url_path='adoptable_namespaces')
    def adoptable_namespaces(self, request, pk=None):
        """列出可被纳管为项目的命名空间：排除系统命名空间与已被占用的。"""
        from ops import k8s_provision
        from ops.models import K8S_PROJECT_LABEL, K8sProject

        cluster = self.get_object()
        try:
            namespaces = k8s_provision.list_namespaces(cluster)
        except k8s_provision.ProvisionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        bound = set(K8sProject.objects.filter(cluster=cluster).values_list('namespace', flat=True))
        items = []
        for item in namespaces:
            name = item['name']
            if name in k8s_provision.SYSTEM_NAMESPACES or name in bound:
                continue
            if (item.get('labels') or {}).get(K8S_PROJECT_LABEL):
                continue
            items.append({
                'name': name,
                'labels': item.get('labels') or {},
                # default 可以纳管，但它承载集群默认工作负载，前端应给出提示
                'warning': '该命名空间是集群默认命名空间' if name == 'default' else '',
            })
        return Response(items)

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试集群连接"""
        cluster = self.get_object()
        if _client_mod._is_demo(cluster):
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': '连接成功 (Kubernetes v1.29.3) [演示模式]'})
        try:
            k8s = _client_mod._get_k8s_client(cluster)
            # 用一次真实的 API 调用确认可达性与鉴权。
            # 这里不能只取 /version：取到版本号不代表能读集群资源，
            # 而且部分发行版的 /version 响应会让客户端模型校验失败。
            k8s.CoreV1Api().get_api_resources()
            version_text = _client_mod.probe_server_version(k8s)
            cluster.status = 'connected'
            cluster.save(update_fields=['status'])
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            return Response({
                'success': True,
                'message': f'连接成功 (Kubernetes {version_text})' if version_text else '连接成功',
            })
        except Exception as e:
            cluster.status = 'error'
            cluster.save(update_fields=['status'])
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            error_text = str(e)
            if 'system:anonymous' in error_text:
                # 服务端一个凭据都没收到，几乎都是地址填错导致的，直接给出排查方向
                error_text = (
                    '服务端未收到任何凭据，把调用方识别成了 system:anonymous。常见原因：\n'
                    '1) API Server 填成了 http://，客户端证书只在 TLS 握手时发送，明文 HTTP 下不会携带；\n'
                    '2) 填的不是 kube-apiserver，而是 KubeSphere 控制台或 ks-apiserver（如 30880 端口）；\n'
                    '3) kubeconfig 里的用户没有配置任何认证方式。\n'
                    '请填写 kube-apiserver 的 https 地址（通常是 6443 端口）。'
                )
            elif isinstance(e, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in error_text or 'certificate verify failed' in error_text.lower():
                error_text = (
                    '证书校验失败：当前 API Server 地址与 kubeconfig 证书不匹配。'
                    '请改用证书 SAN 中的域名或 IP，'
                    '或者在 apiserver 证书中加入该 IP 的 SAN，'
                    '也可以在 kubeconfig 中启用 insecure-skip-tls-verify。'
                )
            return Response({'success': False, 'message': f'连接失败: {error_text}'})

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get cluster summary."""
        cluster = self.get_object()
        scope_error = require_cluster_scope(request)
        if scope_error:
            return scope_error
        cache_key = _summary_cache_key(cluster.id)
        cached = cache.get(cache_key)
        if cached:
            if _is_unreliable_zero_summary(cached):
                cache.delete(cache_key)
            else:
                return Response(cached)
        try:
            summary = _summary_mod._build_demo_summary(cluster) if _client_mod._is_demo(cluster) else _summary_mod._build_live_summary(cluster)
            if cluster.status != 'connected':
                cluster.status = 'connected'
                cluster.save(update_fields=['status'])
                summary['status'] = cluster.status
            return Response(_cache_summary_snapshot(cluster, summary))
        except Exception as e:
            if cluster.status != 'error':
                cluster.status = 'error'
                cluster.save(update_fields=['status'])
            _clear_summary_cache(cluster)
            fallback = cache.get(_summary_stale_cache_key(cluster.id))
            if fallback is not None:
                payload = _summary_stale_payload(cluster, fallback)
            else:
                payload = _build_unavailable_summary(cluster, str(e))
            if not _is_unreliable_zero_summary(payload):
                cache.set(cache_key, payload, K8S_SUMMARY_CACHE_TTL)
            return Response(payload)

    @action(detail=True, methods=['get'])
    def namespaces(self, request, pk=None):
        """
        获取命名空间列表。

        带 project 参数时只返回该项目绑定的那一个命名空间；
        不带 project 属于全集群视角，需要 ops.k8s.manage。
        """
        cluster = self.get_object()
        scoped_namespace, scope_error = resolve_scope(request, cluster, fallback_namespace='_all')
        if scope_error:
            return scope_error

        if _client_mod._is_demo(cluster):
            return Response(_limit_namespaces(DEMO_NAMESPACES, scoped_namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                ns_list = v1.list_namespace()
                return [{
                    'name': ns.metadata.name,
                    'status': ns.status.phase,
                    'created': ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else '',
                    'labels': ns.metadata.labels or {},
                } for ns in ns_list.items]

            data = _get_or_set_resource_cache(cluster, 'namespaces', '_all', loader)
            return Response(_limit_namespaces(data, scoped_namespace))
        except Exception as e:
            return Response({'detail': f'获取命名空间失败: {str(e)}'}, status=400)
