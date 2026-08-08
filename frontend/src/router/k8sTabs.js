/**
 * K8s 主视图从单页 Tab 拆成了独立路由，这里保存 Tab key 与路径的映射。
 * 单独成模块是为了让 router 与视图都能引用而不产生循环依赖。
 */
export const K8S_TAB_PATHS = {
  clusters: '/containers/k8s/clusters',
  nodes: '/containers/k8s/nodes',
  namespaces: '/containers/k8s/namespaces',
  workloads: '/containers/k8s/workloads',
  pods: '/containers/k8s/pods',
  network: '/containers/k8s/network',
  storage: '/containers/k8s/storage',
  config: '/containers/k8s/configs',
}

export const K8S_DEFAULT_TAB = 'clusters'

/** 兼容旧地址 /containers/k8s?tab=xxx，未知 tab 回落到集群管理。 */
export function resolveLegacyK8sTab(tab) {
  const key = typeof tab === 'string' ? tab : ''
  return K8S_TAB_PATHS[key] || K8S_TAB_PATHS[K8S_DEFAULT_TAB]
}
