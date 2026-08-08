import { computed, onMounted, ref, unref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useK8sStore } from '@/stores/k8s'

function resolve(value) {
  return typeof value === 'function' ? value() : unref(value)
}

function normalizeSearchValue(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeSearchValue).join(' ')
  }
  if (value && typeof value === 'object') {
    return Object.values(value).map(normalizeSearchValue).join(' ')
  }
  return String(value || '').toLowerCase()
}

/**
 * K8s 资源页面的公共骨架：集群选中、命名空间同步、概览拉取、列表搜索。
 * 每个页面只需要提供自己的 fetch 逻辑，其余流程由这里统一编排。
 *
 * @param {object}   options
 * @param {boolean|Function} options.needsNamespace 该页面是否依赖命名空间
 * @param {Function} options.fetch                  ({ clusterId, namespace }) => Promise
 * @param {Function} [options.reloadKey]            返回值变化时重新 fetch（用于子 Tab）
 */
export function useK8sResourcePage(options = {}) {
  const { needsNamespace = false, fetch: fetchData, reloadKey, summaryPatch } = options

  const k8sStore = useK8sStore()
  const authStore = useAuthStore()
  const { clusters, namespaces } = storeToRefs(k8sStore)
  // 无 ops.k8s.manage 的用户只能按项目访问，必须先选定项目才能取数
  const requiresProject = computed(() => !authStore.hasPermission('ops.k8s.manage'))

  const loading = ref(false)
  const keyword = ref('')

  const selectedClusterId = computed(() => k8sStore.selectedClusterId)
  const selectedCluster = computed(() => k8sStore.selectedCluster)
  const selectedClusterConnected = computed(() => k8sStore.selectedClusterConnected)
  const selectedNamespace = computed(() => k8sStore.selectedNamespace)
  const selectedProjectId = computed(() => k8sStore.selectedProjectId)
  const effectiveNamespace = computed(() => k8sStore.effectiveNamespace)
  const namespaceOptions = computed(() => k8sStore.namespaceOptions)
  const summary = computed(() => k8sStore.summary)
  const withNamespace = computed(() => Boolean(resolve(needsNamespace)))

  /**
   * 顶部四张概览卡。概览接口滞后于列表时，用页面自己已加载的数量兜底取大值，
   * 避免出现「列表有 20 个 Pod、卡片显示 0」的割裂感。
   */
  const summaryCards = computed(() => {
    const base = { ...summary.value, ...(summaryPatch ? resolve(summaryPatch) : {}) }
    const pick = (key) => Math.max(Number(summary.value?.[key] || 0), Number(base[key] || 0))
    return [
      { label: 'Ready 节点', value: `${pick('nodes_ready')}/${pick('nodes_total')}`, tone: '' },
      { label: 'Pod 总数', value: pick('pods_total'), tone: 'success-card' },
      { label: '异常 Pod', value: pick('pods_abnormal'), tone: 'warning-card' },
      { label: '工作负载', value: pick('workloads_total'), tone: 'danger-card' },
    ]
  })

  function filterRows(rows, fields = []) {
    const text = keyword.value.trim().toLowerCase()
    if (!text) return rows
    return rows.filter(row => fields.some((field) => {
      const value = typeof field === 'function' ? field(row) : row?.[field]
      return normalizeSearchValue(value).includes(text)
    }))
  }

  async function runFetch() {
    if (!fetchData) return
    if (!selectedClusterId.value || !selectedClusterConnected.value) return
    // 租户用户没选项目时不发请求，否则必然 403
    if (requiresProject.value && !selectedProjectId.value) return
    loading.value = true
    try {
      await fetchData({
        clusterId: selectedClusterId.value,
        namespace: effectiveNamespace.value,
        projectId: selectedProjectId.value,
      })
    } catch {
      ElMessage.error('获取数据失败')
    }
    loading.value = false
  }

  /**
   * 集群上下文就绪后再取列表：命名空间与概览并行拉，
   * 概览探测失败说明集群不可用，直接跳过列表请求。
   */
  async function refreshContext(options = {}) {
    const { force = false } = options
    const clusterId = selectedClusterId.value
    if (!clusterId) return

    const previousNamespace = selectedNamespace.value
    await k8sStore.loadProjects({ force })
    ensureSelectedProject()

    const namespaceTask = withNamespace.value
      ? k8sStore.loadNamespaces(clusterId, { force })
      : Promise.resolve([])
    const [available] = await Promise.all([
      k8sStore.loadSummary(clusterId, { force, probe: true }),
      namespaceTask,
    ])
    if (!available) return

    // 项目锁定了命名空间时不要再回落成「全部」
    if (!k8sStore.selectedProject) {
      k8sStore.syncSelectedNamespace(previousNamespace)
    }
    await runFetch()
  }

  /** 页面右上角刷新按钮：强制绕过所有缓存。 */
  async function refresh() {
    loading.value = true
    try {
      await k8sStore.loadClusters({ force: true })
    } catch {
      /* 集群列表拉取失败不阻断后续流程 */
    }
    loading.value = false
    await refreshContext({ force: true })
  }

  /** 用户切换集群：命名空间已由 store 重置成「全部」，这里只需重新取数。 */
  async function onClusterChange() {
    await refreshContext({ force: false })
  }

  async function onNamespaceChange() {
    await runFetch()
  }

  /** 切换项目会改变命名空间，需要连带刷新概览与列表。 */
  async function onProjectChange() {
    await refreshContext({ force: false })
  }

  /** 首次进入时若没有有效选中集群，自动挑一个已连接的。 */
  function ensureSelectedCluster() {
    const current = clusters.value.find(item => item.id === selectedClusterId.value)
    if (current) return
    const connected = clusters.value.find(item => item.status === 'connected')
    k8sStore.setCluster(connected?.id || clusters.value[0]?.id || null)
  }

  /** 租户用户必须落在某个项目里；选中项目失效时自动挑第一个可用的。 */
  function ensureSelectedProject() {
    const available = k8sStore.clusterProjects
    if (k8sStore.selectedProjectId && available.some(item => item.id === k8sStore.selectedProjectId)) return
    if (requiresProject.value) {
      k8sStore.setProject(available[0]?.id || null)
    } else if (k8sStore.selectedProjectId) {
      // 管理员切换集群后原项目可能不在当前集群，清掉回到全集群视角
      k8sStore.setProject(null)
    }
  }

  if (reloadKey) {
    // 走 refreshContext 而不是直接 runFetch：子 Tab 可能把页面从集群级资源
    // 切换到命名空间级资源（存储页的 PV → PVC），此时需要补拉命名空间列表。
    // 概览与命名空间都有 TTL 缓存，重复调用不会产生额外请求。
    watch(() => resolve(reloadKey), (next, prev) => {
      if (next === prev) return
      refreshContext({ force: false })
    })
  }

  onMounted(async () => {
    loading.value = true
    try {
      await k8sStore.loadClusters()
    } catch {
      /* 由下方空态提示接管 */
    }
    loading.value = false
    ensureSelectedCluster()
    await refreshContext({ force: false })
  })

  return {
    k8sStore,
    clusters,
    namespaces,
    loading,
    keyword,
    selectedClusterId,
    selectedCluster,
    selectedClusterConnected,
    selectedNamespace,
    selectedProjectId,
    effectiveNamespace,
    requiresProject,
    namespaceOptions,
    summary,
    summaryCards,
    filterRows,
    runFetch,
    refresh,
    refreshContext,
    onClusterChange,
    onNamespaceChange,
    onProjectChange,
  }
}
