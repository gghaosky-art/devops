import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { getK8sClusters, getK8sNamespaces, getK8sProjects, getK8sSummary } from '@/api/modules/container'

export const ALL_NAMESPACES = '_all'

const SCOPE_STORAGE_KEY = 'sxdevops_k8s_scope'
const CLUSTER_TTL = 30 * 1000
const NAMESPACE_TTL = 60 * 1000
const SUMMARY_TTL = 30 * 1000

const SUMMARY_TOTAL_KEYS = [
  'nodes_total',
  'pods_total',
  'services_total',
  'ingresses_total',
  'workloads_total',
  'pvcs_total',
  'configmaps_total',
  'secrets_total',
]

export function createEmptySummary() {
  return {
    status: 'disconnected',
    nodes_total: 0,
    nodes_ready: 0,
    pods_total: 0,
    pods_abnormal: 0,
    total_restarts: 0,
    workloads_total: 0,
    pvcs_pending: 0,
    alerts: [],
  }
}

function safeInt(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number : 0
}

function runtimeSummaryTotal(payload) {
  return SUMMARY_TOTAL_KEYS.reduce((total, key) => total + safeInt(payload?.[key]), 0)
}

/** 集群降级时后端会返回一份全 0 的 summary，用它覆盖缓存会让面板突然清零。 */
function isZeroRuntimeSummary(payload) {
  return Boolean(payload?.degraded) && runtimeSummaryTotal(payload) === 0
}

function loadStoredScope() {
  try {
    const raw = localStorage.getItem(SCOPE_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    localStorage.removeItem(SCOPE_STORAGE_KEY)
    return {}
  }
}

export function normalizeNamespaceItem(item) {
  if (typeof item === 'string') {
    const name = item.trim()
    return name ? { name, status: '', created: '', labels: {}, labelCount: 0 } : null
  }
  if (!item || typeof item !== 'object') return null
  const name = String(item.name || item.namespace || item.metadata?.name || '').trim()
  if (!name) return null
  const labels = item.labels && typeof item.labels === 'object'
    ? item.labels
    : (item.metadata?.labels && typeof item.metadata.labels === 'object' ? item.metadata.labels : {})
  return {
    ...item,
    name,
    status: String(item.status || item.phase || item.status?.phase || '').trim(),
    created: String(item.created || item.creation_timestamp || item.creationTimestamp || item.metadata?.creationTimestamp || '').trim(),
    labels,
    labelCount: Object.keys(labels).length,
  }
}

export function normalizeNamespaceItems(items) {
  const uniqueMap = new Map()
  for (const item of Array.isArray(items) ? items : []) {
    const normalized = normalizeNamespaceItem(item)
    if (normalized?.name) uniqueMap.set(normalized.name, normalized)
  }
  return Array.from(uniqueMap.values()).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
}

/**
 * K8s 页面共享作用域：集群 / 命名空间 / 项目。
 * 容器管理下的 K8s 菜单已拆成多个独立路由，选择状态必须跨页面保持，
 * 因此集中放在这里，并对集群与命名空间列表做 TTL 缓存与并发去重。
 */
export const useK8sStore = defineStore('k8s', () => {
  const stored = loadStoredScope()

  const clusters = ref([])
  const namespaces = ref([])
  const projects = ref([])
  const projectsLoadedAt = ref(0)
  const selectedClusterId = ref(stored.clusterId ?? null)
  const selectedNamespace = ref(stored.namespace || ALL_NAMESPACES)
  const selectedProjectId = ref(stored.projectId ?? null)

  const clustersLoadedAt = ref(0)
  const namespaceCache = ref({})
  const summaryCache = ref({})
  const lastUsableSummary = ref({})
  let clustersInflight = null
  const namespaceInflight = new Map()

  const selectedCluster = computed(
    () => clusters.value.find(item => item.id === selectedClusterId.value) || null
  )
  const selectedClusterConnected = computed(() => selectedCluster.value?.status === 'connected')
  const namespaceOptions = computed(() => normalizeNamespaceItems(namespaces.value))
  /** 集群列表是否至少成功加载过一次，用于区分「还没加载」和「确实没有集群」。 */
  const clustersLoaded = computed(() => clustersLoadedAt.value > 0)

  /** 当前集群下可选的项目。 */
  const clusterProjects = computed(
    () => projects.value.filter(item => item.cluster === selectedClusterId.value)
  )
  const selectedProject = computed(
    () => clusterProjects.value.find(item => item.id === selectedProjectId.value) || null
  )
  /**
   * 实际用于查询的命名空间：选中项目时由项目决定，命名空间选择器随之锁定；
   * 未选项目时沿用用户自己选的命名空间。
   */
  const effectiveNamespace = computed(
    () => selectedProject.value?.namespace || selectedNamespace.value
  )

  /** 当前集群的 summary，降级返回全 0 时回落到最近一次有效值并标记 degraded。 */
  const summary = computed(() => {
    const clusterId = selectedClusterId.value
    const payload = summaryCache.value[clusterId]?.payload
    if (!payload) return createEmptySummary()
    const fallback = lastUsableSummary.value[clusterId]
    if (isZeroRuntimeSummary(payload) && fallback) {
      return { ...fallback, degraded: true, alerts: payload.alerts || fallback.alerts || [] }
    }
    return payload
  })

  watch(
    [selectedClusterId, selectedNamespace, selectedProjectId],
    () => {
      try {
        localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify({
          clusterId: selectedClusterId.value,
          namespace: selectedNamespace.value,
          projectId: selectedProjectId.value,
        }))
      } catch {
        /* 隐私模式或配额耗尽时忽略持久化失败 */
      }
    }
  )

  async function loadClusters(options = {}) {
    const { force = false } = options
    if (!force && clustersLoadedAt.value && Date.now() - clustersLoadedAt.value < CLUSTER_TTL) {
      return clusters.value
    }
    if (clustersInflight) return clustersInflight

    clustersInflight = (async () => {
      try {
        const res = await getK8sClusters()
        clusters.value = res.results || res || []
        clustersLoadedAt.value = Date.now()
        return clusters.value
      } finally {
        clustersInflight = null
      }
    })()
    return clustersInflight
  }

  async function loadNamespaces(clusterId, options = {}) {
    const { force = false } = options
    if (!clusterId) {
      namespaces.value = []
      return []
    }

    const cached = namespaceCache.value[clusterId]
    if (!force && cached?.items?.length && Date.now() - cached.loadedAt < NAMESPACE_TTL) {
      namespaces.value = cached.items
      return cached.items
    }
    if (namespaceInflight.has(clusterId)) return namespaceInflight.get(clusterId)

    const task = (async () => {
      try {
        // 选中项目时必须带上，否则租户用户拿不到命名空间列表（后端 403）
        const items = normalizeNamespaceItems(await getK8sNamespaces(clusterId, selectedProjectId.value))
        namespaceCache.value = {
          ...namespaceCache.value,
          [clusterId]: { items, loadedAt: Date.now() },
        }
        if (selectedClusterId.value === clusterId) {
          namespaces.value = items
        }
        return items
      } catch {
        if (selectedClusterId.value === clusterId) {
          namespaces.value = []
        }
        return []
      } finally {
        namespaceInflight.delete(clusterId)
      }
    })()
    namespaceInflight.set(clusterId, task)
    return task
  }

  /**
   * 拉取集群概览。probe=true 时即使集群标记为未连接也尝试探测一次，
   * 用来在页面加载时自动纠正过期的 disconnected 状态。
   * 返回值表示「集群当前可用」，调用方据此决定要不要继续加载资源列表。
   */
  async function loadSummary(clusterId, options = {}) {
    const { force = false, probe = false } = options
    if (!clusterId) return false

    const cluster = clusters.value.find(item => item.id === clusterId)
    if (!probe && cluster && cluster.status !== 'connected') {
      return false
    }

    const cached = summaryCache.value[clusterId]
    if (!force && cached && Date.now() - cached.loadedAt < SUMMARY_TTL) {
      return true
    }

    try {
      const payload = await getK8sSummary(clusterId)
      summaryCache.value = {
        ...summaryCache.value,
        [clusterId]: { payload, loadedAt: Date.now() },
      }
      if (!isZeroRuntimeSummary(payload) && runtimeSummaryTotal(payload) > 0) {
        lastUsableSummary.value = { ...lastUsableSummary.value, [clusterId]: { ...payload } }
      }
      setClusterStatus(clusterId, payload.status || 'connected')
      return true
    } catch {
      if (lastUsableSummary.value[clusterId]) {
        // 有历史值就继续展示，只标记降级，不把面板清零。
        summaryCache.value = {
          ...summaryCache.value,
          [clusterId]: { payload: { ...lastUsableSummary.value[clusterId], degraded: true }, loadedAt: Date.now() },
        }
        return true
      }
      summaryCache.value = {
        ...summaryCache.value,
        [clusterId]: { payload: createEmptySummary(), loadedAt: Date.now() },
      }
      setClusterStatus(clusterId, 'error')
      return false
    }
  }

  function invalidateSummary(clusterId) {
    if (!clusterId) {
      summaryCache.value = {}
      return
    }
    const next = { ...summaryCache.value }
    delete next[clusterId]
    summaryCache.value = next
  }

  function setCluster(clusterId) {
    if (selectedClusterId.value === clusterId) return
    selectedClusterId.value = clusterId
    selectedNamespace.value = ALL_NAMESPACES
    selectedProjectId.value = null
    namespaces.value = namespaceCache.value[clusterId]?.items || []
  }

  function setNamespace(name) {
    selectedNamespace.value = name || ALL_NAMESPACES
  }

  async function loadProjects(options = {}) {
    const { force = false } = options
    if (!force && projectsLoadedAt.value && Date.now() - projectsLoadedAt.value < CLUSTER_TTL) {
      return projects.value
    }
    try {
      // 无项目查看权限时接口会 403，这里当作「没有可选项目」，不弹错误提示
      const res = await getK8sProjects(undefined, { skipErrorMessage: true })
      projects.value = res.results || res || []
      projectsLoadedAt.value = Date.now()
    } catch {
      projects.value = []
      projectsLoadedAt.value = Date.now()
    }
    return projects.value
  }

  function setProject(projectId) {
    selectedProjectId.value = projectId ?? null
    // 项目决定命名空间，切换后把选择器同步过去，避免显示上不一致
    const project = projects.value.find(item => item.id === selectedProjectId.value)
    if (project) selectedNamespace.value = project.namespace
  }

  /** 命名空间可能已被删除，回落到「全部命名空间」而不是留下失效选中值。 */
  function syncSelectedNamespace(preferred = selectedNamespace.value) {
    if (!preferred || preferred === ALL_NAMESPACES) {
      selectedNamespace.value = ALL_NAMESPACES
      return
    }
    selectedNamespace.value = namespaceOptions.value.some(item => item.name === preferred)
      ? preferred
      : ALL_NAMESPACES
  }

  function setClusterStatus(clusterId, status) {
    const cluster = clusters.value.find(item => item.id === clusterId)
    if (cluster) cluster.status = status
  }

  function invalidateNamespaces(clusterId) {
    if (!clusterId) {
      namespaceCache.value = {}
      return
    }
    const next = { ...namespaceCache.value }
    delete next[clusterId]
    namespaceCache.value = next
  }

  function invalidateClusters() {
    clustersLoadedAt.value = 0
  }

  return {
    clusters,
    namespaces,
    selectedClusterId,
    selectedNamespace,
    selectedProjectId,
    selectedCluster,
    selectedClusterConnected,
    clustersLoaded,
    namespaceOptions,
    projects,
    clusterProjects,
    selectedProject,
    effectiveNamespace,
    summary,
    loadClusters,
    loadNamespaces,
    loadProjects,
    loadSummary,
    invalidateSummary,
    setCluster,
    setNamespace,
    setProject,
    syncSelectedNamespace,
    setClusterStatus,
    invalidateNamespaces,
    invalidateClusters,
  }
})
