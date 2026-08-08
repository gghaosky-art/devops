"""
兼容入口。

实现已按领域拆分到 ops/k8s/ 包，这里只做再导出，让既有的
`from ops.k8s_views import ...` 与函数内的延迟导入保持可用。
新代码请直接从 ops.k8s.<模块> 导入。

注意：测试若要 mock _get_k8s_client / _build_*_summary，应 patch 定义处
（ops.k8s.client / ops.k8s.summary）；patch 本模块的同名属性不会影响包内已绑定的引用。
"""
from .k8s.cache import (  # noqa: F401
    _bump_resource_cache_version, _clear_summary_cache, _get_or_set_resource_cache,
    _get_resource_cache_version, _invalidate_cluster_runtime_cache, _resource_cache_key,
    _resource_stale_cache_key, _summary_cache_key, _summary_stale_cache_key,
)
from .k8s.client import (  # noqa: F401
    K8S_API_CONNECT_TIMEOUT, K8S_API_READ_TIMEOUT, K8S_DEMO_STATE_CACHE_TTL,
    K8S_RESOURCE_CACHE_TTL, K8S_STALE_RESOURCE_CACHE_TTL, K8S_STALE_SUMMARY_CACHE_TTL,
    K8S_SUMMARY_CACHE_TTL, _get_k8s_client, _is_demo, _K8sApiProxy, _K8sClientProxy,
    _prepare_kubeconfig,
)
from .k8s.demo import (  # noqa: F401
    DEMO_CONFIGMAPS, DEMO_CRONJOBS, DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_INGRESSES,
    DEMO_JOBS, DEMO_NAMESPACES, DEMO_NODES, DEMO_PODS, DEMO_PVCS, DEMO_PVS, DEMO_SECRETS,
    DEMO_SERVICES, DEMO_STATEFULSETS, DEMO_STORAGECLASSES, _get_demo_state, _set_demo_state,
)
from .k8s.items import _filter_by_ns, _limit_namespaces  # noqa: F401
from .k8s.snapshots import (  # noqa: F401
    get_k8s_nodes_snapshot, get_k8s_pods_snapshot, get_k8s_resource_snapshot,
    get_k8s_summary_snapshot,
)
from .k8s.summary import _build_demo_summary, _build_live_summary, _build_summary_alerts  # noqa: F401
from .k8s.views import K8sClusterViewSet  # noqa: F401
