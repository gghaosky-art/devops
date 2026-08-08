"""
配置资源的版本快照与文本 diff。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import difflib
import yaml
from ops.models import K8sConfigRevision
from rest_framework.decorators import action


def _config_backup_key(cluster_id, resource_type, namespace, name):
    return f'ops:k8s:config:backup:{cluster_id}:{resource_type}:{namespace}:{name}'


def _config_revision_queryset(cluster, resource_type, namespace, name):
    return K8sConfigRevision.objects.filter(
        cluster=cluster,
        resource_type=resource_type,
        namespace=namespace,
        resource_name=name,
    )


def _serialize_revision(revision):
    return {
        'id': revision.id,
        'resource_type': revision.resource_type,
        'namespace': revision.namespace,
        'name': revision.resource_name,
        'secret_type': revision.secret_type,
        'operator': revision.operator,
        'action': revision.action,
        'content': revision.content,
        'created_at': revision.created_at.isoformat() if revision.created_at else '',
    }


def _build_text_diff(current_text, target_text, from_label='current', to_label='target'):
    diff = difflib.unified_diff(
        (current_text or '').splitlines(),
        (target_text or '').splitlines(),
        fromfile=from_label,
        tofile=to_label,
        lineterm='',
    )
    return '\n'.join(diff) or 'No changes.'


def _normalize_config_text(content):
    parsed = yaml.safe_load(content or '{}')
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError('配置内容必须是对象映射')
    return {str(key): '' if value is None else str(value) for key, value in parsed.items()}


def _dump_config_text(data):
    return yaml.dump(data or {}, default_flow_style=False, allow_unicode=True, sort_keys=True)


def _create_config_revision(cluster, resource_type, namespace, name, detail, username, action):
    return K8sConfigRevision.objects.create(
        cluster=cluster,
        resource_type=resource_type,
        namespace=namespace,
        resource_name=name,
        secret_type=detail.get('secret_type', ''),
        content=detail.get('text', ''),
        operator=username or '',
        action=action,
    )
