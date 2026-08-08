"""
Kubernetes 客户端构造与 kubeconfig 处理。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import json
import logging
import os
import tempfile
import yaml

logger = logging.getLogger(__name__)


K8S_SUMMARY_CACHE_TTL = 15


K8S_RESOURCE_CACHE_TTL = 8


K8S_DEMO_STATE_CACHE_TTL = 86400


K8S_STALE_SUMMARY_CACHE_TTL = 300


K8S_STALE_RESOURCE_CACHE_TTL = 300


K8S_API_CONNECT_TIMEOUT = 1.5


K8S_API_READ_TIMEOUT = 3


class _K8sApiProxy:
    def __init__(self, api):
        self._api = api

    def __getattr__(self, name):
        attr = getattr(self._api, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            kwargs.setdefault('_request_timeout', (K8S_API_CONNECT_TIMEOUT, K8S_API_READ_TIMEOUT))
            return attr(*args, **kwargs)

        method_owner = getattr(attr, '__self__', None)
        if method_owner is not None:
            wrapped.__self__ = method_owner
            wrapped.self = method_owner

        return wrapped


class _K8sClientProxy:
    def __init__(self, client_module, api_client):
        self._client_module = client_module
        self._api_client = api_client

    def __getattr__(self, name):
        if name == 'ApiClient':
            return lambda *args, **kwargs: self._api_client

        attr = getattr(self._client_module, name)
        if name.endswith('Api') and isinstance(attr, type):
            return lambda *args, _attr=attr, **kwargs: _K8sApiProxy(_attr(self._api_client, *args, **kwargs))
        return attr


def _is_demo(cluster):
    return cluster.kubeconfig.strip() == 'demo'


def _prepare_kubeconfig(cluster):
    kubeconfig_text = cluster.kubeconfig or ''
    api_server = (cluster.api_server or '').strip()
    if not api_server:
        return kubeconfig_text

    try:
        kubeconfig = yaml.safe_load(kubeconfig_text) or {}
    except Exception:
        return kubeconfig_text

    if not isinstance(kubeconfig, dict):
        return kubeconfig_text

    current_context_name = kubeconfig.get('current-context')
    contexts = kubeconfig.get('contexts') or []
    clusters = kubeconfig.get('clusters') or []
    context_cluster_name = ''

    for context in contexts:
        if not isinstance(context, dict):
            continue
        if context.get('name') != current_context_name:
            continue
        context_data = context.get('context') or {}
        context_cluster_name = context_data.get('cluster') or ''
        break

    if not context_cluster_name and clusters:
        first_cluster = clusters[0] if isinstance(clusters[0], dict) else {}
        context_cluster_name = first_cluster.get('name') or ''

    if not context_cluster_name:
        return kubeconfig_text

    for cluster_item in clusters:
        if not isinstance(cluster_item, dict):
            continue
        if cluster_item.get('name') != context_cluster_name:
            continue
        cluster_data = cluster_item.setdefault('cluster', {})
        if isinstance(cluster_data, dict):
            cluster_data['server'] = api_server
            return yaml.safe_dump(kubeconfig, sort_keys=False, allow_unicode=True)

    return kubeconfig_text


def _get_k8s_client(cluster):
    """根据 kubeconfig 创建 K8s API 客户端"""
    from kubernetes import client, config

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    tmp.write(_prepare_kubeconfig(cluster))
    tmp.flush()
    tmp.close()

    try:
        api_client = config.new_client_from_config(config_file=tmp.name)
        return _K8sClientProxy(client, api_client)
    finally:
        os.unlink(tmp.name)


def probe_server_version(k8s):
    """
    尽力取集群版本号，取不到返回空串。

    官方客户端把 /version 反序列化成 VersionInfo 模型，该模型要求 build_date
    等字段非空。KubeSphere 等发行版（或经过网关代理的 API）返回的 /version
    缺少这些字段，会抛 "Invalid value for `build_date`, must not be `None`"。
    版本号只用于连接成功后的提示文案，不该因此判定整个连接失败，
    因此这里降级到读原始 JSON，再失败就放弃。
    """
    try:
        return getattr(k8s.VersionApi().get_code(), 'git_version', '') or ''
    except Exception as exc:
        logger.info('version model parse failed, falling back to raw payload: %s', exc)

    try:
        # 新版生成的客户端提供不做模型校验的变体，正好绕开上面的字段约束
        raw_getter = getattr(k8s.VersionApi(), 'get_code_without_preload_content', None)
        if raw_getter is None:
            return ''
        payload = json.loads(raw_getter().data)
        return payload.get('gitVersion') or payload.get('git_version') or ''
    except Exception as exc:
        logger.info('raw /version fetch failed: %s', exc)
        return ''


def kubeconfig_uses_client_cert(kubeconfig_text):
    """判断 kubeconfig 是否依赖客户端证书认证。"""
    try:
        parsed = yaml.safe_load(kubeconfig_text or '')
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    for entry in parsed.get('users') or []:
        user = (entry or {}).get('user') or {}
        if 'client-certificate-data' in user or 'client-certificate' in user:
            return True
    return False


def api_server_warnings(api_server, kubeconfig_text=''):
    """
    返回该 API Server 配置的风险提示。只提示，不阻断保存——
    老集群的明文端口、或链路上已终止 TLS 的本地代理都是合法场景。
    """
    endpoint = (api_server or '').strip().lower()
    if not endpoint.startswith('http://'):
        return []

    if kubeconfig_uses_client_cert(kubeconfig_text):
        return [
            '当前 API Server 使用明文 HTTP，而 kubeconfig 依赖客户端证书认证。'
            '客户端证书只在 TLS 握手时发送，明文连接下不会携带，'
            '服务端会把调用方识别成 system:anonymous 并返回 403。'
            '除非链路上另有代理完成鉴权，否则请改用 https 地址（kube-apiserver 通常是 6443 端口）。'
        ]
    return [
        '当前 API Server 使用明文 HTTP，凭据与集群数据将不加密传输。'
        '仅建议在本机代理等可信链路上使用。'
    ]
