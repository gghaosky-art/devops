"""
Kubernetes 企业空间 / 项目在集群侧的落地操作。

项目对应集群中的一个命名空间，平台通过标签把两者关联起来：
    sxdevops.io/workspace  = 企业空间标识
    sxdevops.io/project-id = 项目主键

配额默认只在平台侧展示（quota_enforced=False），开启后才会下发 ResourceQuota。
demo 集群（kubeconfig 为 'demo'）不触碰真实 API，走内存模拟，保证演示环境可用。
"""
import logging
import re

from .k8s_views import _get_k8s_client, _is_demo, DEMO_NAMESPACES
from .models import K8S_PROJECT_LABEL, K8S_WORKSPACE_LABEL

logger = logging.getLogger(__name__)

QUOTA_OBJECT_NAME = 'sxdevops-project-quota'
LIMIT_RANGE_OBJECT_NAME = 'sxdevops-project-limits'

# 这些命名空间承载集群自身组件，不允许纳管成业务项目
SYSTEM_NAMESPACES = {'kube-system', 'kube-public', 'kube-node-lease'}

_MEMORY_UNITS = {
    'Ki': 1024, 'Mi': 1024 ** 2, 'Gi': 1024 ** 3,
    'Ti': 1024 ** 4, 'Pi': 1024 ** 5, 'Ei': 1024 ** 6,
    'k': 1000, 'K': 1000, 'M': 1000 ** 2, 'G': 1000 ** 3,
    'T': 1000 ** 4, 'P': 1000 ** 5, 'E': 1000 ** 6,
}


class ProvisionError(Exception):
    """集群侧操作失败，调用方转成 400 返回给前端。"""


def parse_cpu(value):
    """K8s CPU 数量转成核数，'100m' -> 0.1。"""
    text = str(value or '').strip()
    if not text:
        return 0.0
    try:
        if text.endswith('m'):
            return float(text[:-1]) / 1000
        if text.endswith('n'):
            return float(text[:-1]) / 1_000_000_000
        return float(text)
    except ValueError:
        return 0.0


def parse_memory(value):
    """K8s 内存数量转成字节，'128Mi' -> 134217728。"""
    text = str(value or '').strip()
    if not text:
        return 0
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([A-Za-z]*)', text)
    if not match:
        return 0
    number, unit = match.groups()
    try:
        amount = float(number)
    except ValueError:
        return 0
    if not unit:
        return int(amount)
    return int(amount * _MEMORY_UNITS.get(unit, 1))


def list_namespaces(cluster):
    """返回 [{name, labels}]，供纳管候选与占用校验使用。"""
    if _is_demo(cluster):
        return [{'name': item['name'], 'labels': dict(item.get('labels') or {})} for item in DEMO_NAMESPACES]

    try:
        k8s = _get_k8s_client(cluster)
        items = k8s.CoreV1Api().list_namespace().items
    except Exception as exc:
        logger.warning('list namespaces failed on cluster %s: %s', cluster.pk, exc)
        raise ProvisionError(f'读取集群命名空间失败: {exc}') from exc

    return [
        {'name': item.metadata.name, 'labels': dict(item.metadata.labels or {})}
        for item in items
    ]


def find_namespace(cluster, namespace):
    for item in list_namespaces(cluster):
        if item['name'] == namespace:
            return item
    return None


def _project_labels(project):
    return {
        K8S_WORKSPACE_LABEL: project.workspace.name,
        K8S_PROJECT_LABEL: str(project.pk),
    }


def create_namespace(cluster, project):
    if _is_demo(cluster):
        return

    try:
        k8s = _get_k8s_client(cluster)
        body = k8s.V1Namespace(metadata=k8s.V1ObjectMeta(name=project.namespace, labels=_project_labels(project)))
        k8s.CoreV1Api().create_namespace(body=body)
    except Exception as exc:
        logger.warning('create namespace %s failed: %s', project.namespace, exc)
        raise ProvisionError(f'创建命名空间失败: {exc}') from exc


def label_namespace(cluster, project):
    """给已有命名空间打上归属标签（纳管路径）。"""
    if _is_demo(cluster):
        return

    try:
        k8s = _get_k8s_client(cluster)
        k8s.CoreV1Api().patch_namespace(
            name=project.namespace,
            body={'metadata': {'labels': _project_labels(project)}},
        )
    except Exception as exc:
        logger.warning('label namespace %s failed: %s', project.namespace, exc)
        raise ProvisionError(f'标记命名空间失败: {exc}') from exc


def unlabel_namespace(cluster, project):
    """解绑时把标签置空，K8s 中 null 表示删除该标签键。"""
    if _is_demo(cluster):
        return

    try:
        k8s = _get_k8s_client(cluster)
        k8s.CoreV1Api().patch_namespace(
            name=project.namespace,
            body={'metadata': {'labels': {K8S_WORKSPACE_LABEL: None, K8S_PROJECT_LABEL: None}}},
        )
    except Exception as exc:
        # 命名空间可能已被集群侧删除，解绑不该因此失败
        logger.warning('unlabel namespace %s failed: %s', project.namespace, exc)


def delete_namespace(cluster, project):
    if _is_demo(cluster):
        return

    try:
        k8s = _get_k8s_client(cluster)
        k8s.CoreV1Api().delete_namespace(name=project.namespace)
    except Exception as exc:
        logger.warning('delete namespace %s failed: %s', project.namespace, exc)
        raise ProvisionError(f'删除命名空间失败: {exc}') from exc


def apply_quota(cluster, project):
    """下发 ResourceQuota 与 LimitRange；配额为空时等同于撤销。"""
    if _is_demo(cluster):
        return
    if not project.quota:
        delete_quota(cluster, project)
        return

    k8s = _get_k8s_client(cluster)
    core = k8s.CoreV1Api()
    hard = {str(key): str(value) for key, value in (project.quota or {}).items() if value not in (None, '')}

    quota_body = {
        'apiVersion': 'v1',
        'kind': 'ResourceQuota',
        'metadata': {'name': QUOTA_OBJECT_NAME, 'labels': _project_labels(project)},
        'spec': {'hard': hard},
    }
    try:
        core.replace_namespaced_resource_quota(
            name=QUOTA_OBJECT_NAME, namespace=project.namespace, body=quota_body,
        )
    except Exception:
        try:
            core.create_namespaced_resource_quota(namespace=project.namespace, body=quota_body)
        except Exception as exc:
            logger.warning('apply resource quota on %s failed: %s', project.namespace, exc)
            raise ProvisionError(f'下发配额失败: {exc}') from exc

    _apply_limit_range(core, project)


def _apply_limit_range(core, project):
    """
    ResourceQuota 一旦限制了 requests/limits，未声明资源的 Pod 会被 API Server 拒绝。
    配套下发 LimitRange 提供默认值，避免既有工作负载在下次滚动更新时创建失败。
    """
    limit_range = project.limit_range or {}
    if not limit_range:
        return

    item = {'type': 'Container'}
    if limit_range.get('defaultRequest'):
        item['defaultRequest'] = {k: str(v) for k, v in limit_range['defaultRequest'].items()}
    if limit_range.get('default'):
        item['default'] = {k: str(v) for k, v in limit_range['default'].items()}
    if len(item) == 1:
        return

    body = {
        'apiVersion': 'v1',
        'kind': 'LimitRange',
        'metadata': {'name': LIMIT_RANGE_OBJECT_NAME, 'labels': _project_labels(project)},
        'spec': {'limits': [item]},
    }
    try:
        core.replace_namespaced_limit_range(name=LIMIT_RANGE_OBJECT_NAME, namespace=project.namespace, body=body)
    except Exception:
        try:
            core.create_namespaced_limit_range(namespace=project.namespace, body=body)
        except Exception as exc:
            logger.warning('apply limit range on %s failed: %s', project.namespace, exc)
            raise ProvisionError(f'下发默认资源限制失败: {exc}') from exc


def delete_quota(cluster, project):
    """撤销下发，命名空间本身保留。"""
    if _is_demo(cluster):
        return

    try:
        k8s = _get_k8s_client(cluster)
        core = k8s.CoreV1Api()
    except Exception as exc:
        logger.warning('connect cluster %s failed while deleting quota: %s', cluster.pk, exc)
        return

    for deleter, name in (
        (core.delete_namespaced_resource_quota, QUOTA_OBJECT_NAME),
        (core.delete_namespaced_limit_range, LIMIT_RANGE_OBJECT_NAME),
    ):
        try:
            deleter(name=name, namespace=project.namespace)
        except Exception:
            # 对象本来就不存在是正常情况
            pass


def collect_usage(cluster, project):
    """
    统计命名空间的资源占用。

    「已申请量」由 Pod spec 的 requests/limits 累加得到，任何集群都能算；
    「实时用量」依赖 metrics-server，取不到时返回 None 而不是 0，前端据此隐藏该列。
    """
    empty = {
        'requests': {'cpu': 0.0, 'memory': 0},
        'limits': {'cpu': 0.0, 'memory': 0},
        'pods': 0,
        'live': None,
        'metrics_available': False,
    }
    if _is_demo(cluster):
        return empty

    try:
        k8s = _get_k8s_client(cluster)
        pods = k8s.CoreV1Api().list_namespaced_pod(namespace=project.namespace).items
    except Exception as exc:
        logger.warning('collect usage on %s failed: %s', project.namespace, exc)
        return empty

    usage = {
        'requests': {'cpu': 0.0, 'memory': 0},
        'limits': {'cpu': 0.0, 'memory': 0},
        'pods': len(pods),
        'live': None,
        'metrics_available': False,
    }
    for pod in pods:
        for container in (pod.spec.containers or []):
            resources = container.resources
            if not resources:
                continue
            for bucket, source in (('requests', resources.requests), ('limits', resources.limits)):
                if not source:
                    continue
                usage[bucket]['cpu'] += parse_cpu(source.get('cpu'))
                usage[bucket]['memory'] += parse_memory(source.get('memory'))

    usage['requests']['cpu'] = round(usage['requests']['cpu'], 3)
    usage['limits']['cpu'] = round(usage['limits']['cpu'], 3)
    usage.update(_collect_live_usage(cluster, project))
    return usage


def _collect_live_usage(cluster, project):
    """metrics-server 不一定装了，取不到就明确标记为不可用。"""
    try:
        k8s = _get_k8s_client(cluster)
        metrics = k8s.CustomObjectsApi().list_namespaced_custom_object(
            group='metrics.k8s.io', version='v1beta1',
            namespace=project.namespace, plural='pods',
        )
    except Exception:
        return {'live': None, 'metrics_available': False}

    cpu = 0.0
    memory = 0
    for item in metrics.get('items', []):
        for container in item.get('containers', []):
            container_usage = container.get('usage') or {}
            cpu += parse_cpu(container_usage.get('cpu'))
            memory += parse_memory(container_usage.get('memory'))

    return {'live': {'cpu': round(cpu, 3), 'memory': memory}, 'metrics_available': True}
