"""
demo 集群的模拟数据与状态。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import copy
from django.core.cache import cache
from .client import K8S_DEMO_STATE_CACHE_TTL


DEMO_NAMESPACES = [
    {'name': 'default', 'status': 'Active', 'created': '2026-01-15T08:00:00+08:00', 'labels': {}},
    {'name': 'kube-system', 'status': 'Active', 'created': '2026-01-15T08:00:00+08:00', 'labels': {}},
    {'name': 'monitoring', 'status': 'Active', 'created': '2026-02-01T10:30:00+08:00', 'labels': {}},
    {'name': 'production', 'status': 'Active', 'created': '2026-02-10T14:00:00+08:00', 'labels': {'env': 'prod'}},
    {'name': 'staging', 'status': 'Active', 'created': '2026-02-10T14:00:00+08:00', 'labels': {'env': 'staging'}},
]


DEMO_PODS = [
    {'name': 'nginx-deployment-7c5b4f9d8-x2k9p', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.15', 'containers': [{'name': 'nginx', 'image': 'nginx:1.25', 'ready': True}], 'restarts': 0, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'nginx-deployment-7c5b4f9d8-m3h7q', 'namespace': 'production', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.22', 'containers': [{'name': 'nginx', 'image': 'nginx:1.25', 'ready': True}], 'restarts': 0, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-server-5f8b7c6d4-r9p2w', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.18', 'containers': [{'name': 'api', 'image': 'myapp/api:v2.1.0', 'ready': True}], 'restarts': 1, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'api-server-5f8b7c6d4-t4n8k', 'namespace': 'production', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.10', 'containers': [{'name': 'api', 'image': 'myapp/api:v2.1.0', 'ready': True}], 'restarts': 0, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'redis-master-0', 'namespace': 'production', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.30', 'containers': [{'name': 'redis', 'image': 'redis:7.2-alpine', 'ready': True}], 'restarts': 0, 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary-0', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.25', 'containers': [{'name': 'mysql', 'image': 'mysql:8.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'web-frontend-6d9f8b7c5-j2m4n', 'namespace': 'staging', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.15', 'containers': [{'name': 'frontend', 'image': 'myapp/web:v2.2.0-rc1', 'ready': True}], 'restarts': 0, 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'web-frontend-6d9f8b7c5-k7p3q', 'namespace': 'staging', 'status': 'Pending', 'node': '', 'ip': '', 'containers': [{'name': 'frontend', 'image': 'myapp/web:v2.2.0-rc1', 'ready': False}], 'restarts': 0, 'created': '2026-03-08T16:05:00+08:00'},
    {'name': 'prometheus-server-0', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.40', 'containers': [{'name': 'prometheus', 'image': 'prom/prometheus:v2.51.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana-7f8c9d6b5-w3x2y', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.35', 'containers': [{'name': 'grafana', 'image': 'grafana/grafana:10.4.0', 'ready': True}], 'restarts': 2, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'alertmanager-0', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.42', 'containers': [{'name': 'alertmanager', 'image': 'prom/alertmanager:v0.27.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-01T10:40:00+08:00'},
    {'name': 'coredns-5d78c9689-b8k4m', 'namespace': 'kube-system', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.3', 'containers': [{'name': 'coredns', 'image': 'registry.k8s.io/coredns:v1.11.1', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'etcd-master', 'namespace': 'kube-system', 'status': 'Running', 'node': 'master', 'ip': '10.0.0.1', 'containers': [{'name': 'etcd', 'image': 'registry.k8s.io/etcd:3.5.12', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-proxy-n7x2k', 'namespace': 'kube-system', 'status': 'Running', 'node': 'node-01', 'ip': '192.168.1.21', 'containers': [{'name': 'kube-proxy', 'image': 'registry.k8s.io/kube-proxy:v1.29.3', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'debug-pod-manual', 'namespace': 'default', 'status': 'Failed', 'node': 'node-02', 'ip': '10.244.2.99', 'containers': [{'name': 'debug', 'image': 'busybox:latest', 'ready': False}], 'restarts': 5, 'created': '2026-03-07T20:00:00+08:00'},
]


DEMO_SERVICES = [
    {'name': 'nginx-service', 'namespace': 'production', 'type': 'LoadBalancer', 'cluster_ip': '10.96.10.50', 'external_ip': '203.0.113.100', 'ports': '80→30080/TCP, 443→30443/TCP', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-service', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.20.100', 'external_ip': '', 'ports': '8080/TCP', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'redis-master', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.30.10', 'external_ip': '', 'ports': '6379/TCP', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.30.20', 'external_ip': '', 'ports': '3306/TCP', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'web-frontend', 'namespace': 'staging', 'type': 'NodePort', 'cluster_ip': '10.96.50.10', 'external_ip': '', 'ports': '3000→31000/TCP', 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'prometheus', 'namespace': 'monitoring', 'type': 'NodePort', 'cluster_ip': '10.96.60.10', 'external_ip': '', 'ports': '9090→30090/TCP', 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana', 'namespace': 'monitoring', 'type': 'NodePort', 'cluster_ip': '10.96.60.20', 'external_ip': '', 'ports': '3000→30300/TCP', 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'kubernetes', 'namespace': 'default', 'type': 'ClusterIP', 'cluster_ip': '10.96.0.1', 'external_ip': '', 'ports': '443/TCP', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-dns', 'namespace': 'kube-system', 'type': 'ClusterIP', 'cluster_ip': '10.96.0.10', 'external_ip': '', 'ports': '53/UDP, 53/TCP, 9153/TCP', 'created': '2026-01-15T08:00:00+08:00'},
]


DEMO_DEPLOYMENTS = [
    {'name': 'nginx-deployment', 'namespace': 'production', 'replicas': 2, 'ready_replicas': 2, 'available_replicas': 2, 'images': 'nginx:1.25', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-server', 'namespace': 'production', 'replicas': 2, 'ready_replicas': 2, 'available_replicas': 2, 'images': 'myapp/api:v2.1.0', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'web-frontend', 'namespace': 'staging', 'replicas': 2, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'myapp/web:v2.2.0-rc1', 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'grafana', 'namespace': 'monitoring', 'replicas': 1, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'grafana/grafana:10.4.0', 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'coredns', 'namespace': 'kube-system', 'replicas': 1, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'registry.k8s.io/coredns:v1.11.1', 'created': '2026-01-15T08:00:00+08:00'},
]


DEMO_NODES = [
    {'name': 'master-01', 'status': 'Ready', 'roles': 'control-plane', 'version': 'v1.29.3', 'internal_ip': '192.168.1.10', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '16Gi', 'pods_count': 12, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-01', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.21', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 8, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-02', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.22', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 6, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-03', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.23', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 5, 'age': '30d', 'created': '2026-02-07T10:00:00+08:00'},
]


DEMO_STATEFULSETS = [
    {'name': 'redis-master', 'namespace': 'production', 'replicas': 1, 'ready_replicas': 1, 'images': 'redis:7.2-alpine', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary', 'namespace': 'production', 'replicas': 1, 'ready_replicas': 1, 'images': 'mysql:8.0', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'prometheus-server', 'namespace': 'monitoring', 'replicas': 1, 'ready_replicas': 1, 'images': 'prom/prometheus:v2.51.0', 'created': '2026-02-01T10:30:00+08:00'},
]


DEMO_DAEMONSETS = [
    {'name': 'kube-proxy', 'namespace': 'kube-system', 'desired': 4, 'current': 4, 'ready': 4, 'images': 'registry.k8s.io/kube-proxy:v1.29.3', 'node_selector': '', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'calico-node', 'namespace': 'kube-system', 'desired': 4, 'current': 4, 'ready': 4, 'images': 'calico/node:v3.27.0', 'node_selector': '', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-exporter', 'namespace': 'monitoring', 'desired': 3, 'current': 3, 'ready': 3, 'images': 'prom/node-exporter:v1.7.0', 'node_selector': 'worker', 'created': '2026-02-01T10:30:00+08:00'},
]


DEMO_JOBS = [
    {'name': 'db-backup-20260309', 'namespace': 'production', 'completions': '1/1', 'duration': '45s', 'status': 'Complete', 'images': 'mysql:8.0', 'created': '2026-03-09T02:00:00+08:00'},
    {'name': 'data-migration-v2', 'namespace': 'production', 'completions': '3/3', 'duration': '12m', 'status': 'Complete', 'images': 'myapp/migrator:v2.1', 'created': '2026-03-08T10:00:00+08:00'},
]


DEMO_CRONJOBS = [
    {'name': 'db-backup', 'namespace': 'production', 'schedule': '0 2 * * *', 'suspend': False, 'active': 0, 'last_schedule': '2026-03-09T02:00:00+08:00', 'images': 'mysql:8.0', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'log-cleanup', 'namespace': 'kube-system', 'schedule': '0 3 * * 0', 'suspend': False, 'active': 0, 'last_schedule': '2026-03-09T03:00:00+08:00', 'images': 'busybox:latest', 'created': '2026-01-20T08:00:00+08:00'},
    {'name': 'cert-renew', 'namespace': 'default', 'schedule': '0 0 1 * *', 'suspend': True, 'active': 0, 'last_schedule': '2026-03-01T00:00:00+08:00', 'images': 'certbot:latest', 'created': '2026-02-01T08:00:00+08:00'},
]


DEMO_INGRESSES = [
    {'name': 'web-ingress', 'namespace': 'production', 'class': 'nginx', 'hosts': 'app.example.com', 'address': '203.0.113.100', 'ports': '80, 443', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-ingress', 'namespace': 'production', 'class': 'nginx', 'hosts': 'api.example.com', 'address': '203.0.113.100', 'ports': '80, 443', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'grafana-ingress', 'namespace': 'monitoring', 'class': 'nginx', 'hosts': 'grafana.example.com', 'address': '203.0.113.100', 'ports': '80, 443', 'created': '2026-02-01T10:35:00+08:00'},
]


DEMO_PVS = [
    {'name': 'pv-mysql-data', 'capacity': '50Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Retain', 'status': 'Bound', 'claim': 'production/mysql-data-mysql-primary-0', 'storage_class': 'local-path', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'pv-redis-data', 'capacity': '10Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Retain', 'status': 'Bound', 'claim': 'production/redis-data-redis-master-0', 'storage_class': 'local-path', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'pv-prometheus', 'capacity': '100Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Delete', 'status': 'Bound', 'claim': 'monitoring/prometheus-data', 'storage_class': 'nfs', 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'pv-available-01', 'capacity': '20Gi', 'access_modes': 'RWX', 'reclaim_policy': 'Retain', 'status': 'Available', 'claim': '', 'storage_class': 'nfs', 'created': '2026-03-01T08:00:00+08:00'},
]


DEMO_PVCS = [
    {'name': 'mysql-data-mysql-primary-0', 'namespace': 'production', 'status': 'Bound', 'volume': 'pv-mysql-data', 'capacity': '50Gi', 'access_modes': 'RWO', 'storage_class': 'local-path', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'redis-data-redis-master-0', 'namespace': 'production', 'status': 'Bound', 'volume': 'pv-redis-data', 'capacity': '10Gi', 'access_modes': 'RWO', 'storage_class': 'local-path', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'prometheus-data', 'namespace': 'monitoring', 'status': 'Bound', 'volume': 'pv-prometheus', 'capacity': '100Gi', 'access_modes': 'RWO', 'storage_class': 'nfs', 'created': '2026-02-01T10:30:00+08:00'},
]


DEMO_STORAGECLASSES = [
    {'name': 'local-path', 'provisioner': 'rancher.io/local-path', 'reclaim_policy': 'Delete', 'binding_mode': 'WaitForFirstConsumer', 'allow_expansion': True, 'is_default': True, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'nfs', 'provisioner': 'nfs.csi.k8s.io', 'reclaim_policy': 'Delete', 'binding_mode': 'Immediate', 'allow_expansion': True, 'is_default': False, 'created': '2026-01-20T08:00:00+08:00'},
]


DEMO_CONFIGMAPS = [
    {'name': 'nginx-config', 'namespace': 'production', 'data_count': 3, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-config', 'namespace': 'production', 'data_count': 5, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'prometheus-config', 'namespace': 'monitoring', 'data_count': 2, 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana-dashboards', 'namespace': 'monitoring', 'data_count': 8, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'coredns', 'namespace': 'kube-system', 'data_count': 1, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-proxy', 'namespace': 'kube-system', 'data_count': 2, 'created': '2026-01-15T08:00:00+08:00'},
]


DEMO_SECRETS = [
    {'name': 'mysql-credentials', 'namespace': 'production', 'type': 'Opaque', 'data_count': 2, 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'tls-cert-production', 'namespace': 'production', 'type': 'kubernetes.io/tls', 'data_count': 2, 'created': '2026-03-01T08:00:00+08:00'},
    {'name': 'registry-credentials', 'namespace': 'production', 'type': 'kubernetes.io/dockerconfigjson', 'data_count': 1, 'created': '2026-02-15T08:00:00+08:00'},
    {'name': 'grafana-admin', 'namespace': 'monitoring', 'type': 'Opaque', 'data_count': 2, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'default-token', 'namespace': 'default', 'type': 'kubernetes.io/service-account-token', 'data_count': 3, 'created': '2026-01-15T08:00:00+08:00'},
]


def _demo_state_key(cluster_id, resource):
    return f'ops:k8s:demo:{cluster_id}:{resource}'


def _get_demo_state(cluster_id, resource, default):
    cache_key = _demo_state_key(cluster_id, resource)
    cached = cache.get(cache_key)
    if cached is None:
        cached = copy.deepcopy(default)
        cache.set(cache_key, cached, K8S_DEMO_STATE_CACHE_TTL)
    return cached


def _set_demo_state(cluster_id, resource, value):
    cache.set(_demo_state_key(cluster_id, resource), value, K8S_DEMO_STATE_CACHE_TTL)


def _demo_config_backup_key(cluster_id, resource_type, namespace, name):
    return f'ops:k8s:demo:backup:{cluster_id}:{resource_type}:{namespace}:{name}'
