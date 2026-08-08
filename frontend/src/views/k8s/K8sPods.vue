<template>
  <K8sPageShell title="Pod 管理" desc="检索 Pod 并完成日志、终端、重启与事件排查。" icon="Box" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="Pod 列表"
      desc="在同一工作台容器中完成检索、日志、重启和事件查看。"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <el-table :data="filterRows(pods, podSearchFields)" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="Pod 名称" min-width="260">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Running' ? 'running' : row.status === 'Pending' ? 'restarting' : 'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'Running' ? 'success' : row.status === 'Pending' ? 'warning' : 'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="restarts" label="重启次数" width="80">
          <template #default="{ row }">
            <span :style="{ color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600 }">{{ row.restarts }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="node" label="节点" width="140" show-overflow-tooltip />
        <el-table-column prop="ip" label="Pod 地址" width="150" show-overflow-tooltip />
        <el-table-column label="容器" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ containerNames(row.containers).join(', ') || '-' }}</template>
        </el-table-column>
        <el-table-column label="镜像" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ containerImages(row.containers).join(', ') || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-popconfirm v-if="canManage" title="确定重启该 Pod？" @confirm="restart(row)">
                <template #reference>
                  <el-tooltip content="重启 Pod" placement="top" :show-after="500">
                    <button class="pod-op-btn pod-op-event"><el-icon :size="14"><RefreshRight /></el-icon></button>
                  </el-tooltip>
                </template>
              </el-popconfirm>
              <el-tooltip v-if="canExec" content="Pod Exec" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="execDialog.open(row, containerNames(row.containers))"><el-icon :size="14"><Monitor /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看日志" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" @click="logDialog.open(row.name, row.namespace, containerNames(row.containers))"><el-icon :size="14"><Monitor /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('pod', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('pod', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </K8sResourcePanel>

    <K8sYamlDialog ref="yamlDialog" />
    <K8sEventsDialog ref="eventsDialog" />
    <K8sLogDialog ref="logDialog" />
    <K8sExecDialog ref="execDialog" />
  </K8sPageShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Document, Monitor, RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import K8sEventsDialog from '@/components/k8s/K8sEventsDialog.vue'
import K8sLogDialog from '@/components/k8s/K8sLogDialog.vue'
import K8sExecDialog from '@/components/k8s/K8sExecDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'
import { getK8sPods, restartK8sPod } from '@/api/modules/container'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))
const canExec = computed(() => authStore.hasPermission('ops.k8s.exec'))

const pods = ref([])
const yamlDialog = ref(null)
const eventsDialog = ref(null)
const logDialog = ref(null)
const execDialog = ref(null)

function containerNames(containers) {
  return (containers || []).map(item => (typeof item === 'string' ? item : item?.name)).filter(Boolean)
}

function containerImages(containers) {
  return (containers || []).map(item => (typeof item === 'string' ? item : item?.image)).filter(Boolean)
}

const podSearchFields = ['name', 'namespace', 'status', 'node', 'ip', row => containerNames(row.containers), row => containerImages(row.containers)]

const {
  k8sStore, loading, keyword, summaryCards, selectedClusterId, selectedProjectId,
  filterRows, refresh, runFetch, onClusterChange, onNamespaceChange, onProjectChange,
} = useK8sResourcePage({
  needsNamespace: true,
  fetch: async ({ clusterId, namespace, projectId }) => {
    pods.value = await getK8sPods(clusterId, namespace, projectId)
  },
  summaryPatch: () => ({
    pods_total: pods.value.length,
    pods_abnormal: pods.value.filter(row => !['Running', 'Succeeded'].includes(String(row?.status || ''))).length,
  }),
})

async function restart(row) {
  if (!canManage.value) return
  try {
    const res = await restartK8sPod(selectedClusterId.value, row.name, row.namespace, selectedProjectId.value)
    ElMessage.success(res.message || 'Pod 正在重启')
    k8sStore.invalidateSummary(selectedClusterId.value)
    await runFetch()
  } catch {
    ElMessage.error('Pod 重启失败')
  }
}
</script>
