"""
Kubernetes 集群管理。

原先是单个 ops/k8s_views.py（约 2600 行），按领域拆成本包。
对外接口不变：ops/k8s_views.py 作为兼容入口再导出这里的符号。
"""
