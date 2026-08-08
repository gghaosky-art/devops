<template>
  <el-dialog v-model="visible" :title="'Pod 列表 - ' + workloadName" width="95%" style="max-width:1200px;" top="3vh" append-to-body destroy-on-close>
    <el-table :data="pods" stripe v-loading="loading" style="width:100%" size="small">
      <el-table-column prop="name" label="Pod 名称" min-width="280">
        <template #default="{ row }">
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="state-pulse" :class="row.status === 'Running' ? 'running' : row.status === 'Pending' ? 'restarting' : 'exited'"></span>
            <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'Running' ? 'success' : row.status === 'Pending' ? 'warning' : 'danger'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="restarts" label="重启" width="70">
        <template #default="{ row }">
          <span :style="{ color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600 }">{{ row.restarts }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="node" label="节点" width="120" show-overflow-tooltip />
      <el-table-column label="IP 地址" width="160">
        <template #default="{ row }">
          <div style="font-size:11px;line-height:1.6">
            <div>Pod: <b style="color:#3b82f6">{{ row.pod_ip || '-' }}</b></div>
            <div>Host: <span style="color:#64748b">{{ row.host_ip || '-' }}</span></div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="资源" width="150">
        <template #default="{ row }">
          <div style="font-size:11px;line-height:1.6">
            <div>CPU: <el-tag size="small" type="info" style="font-size:11px">{{ row.cpu_request }}</el-tag></div>
            <div>Mem: <el-tag size="small" type="info" style="font-size:11px">{{ row.memory_request }}</el-tag></div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="age" label="运行时间" width="90">
        <template #default="{ row }">
          <span style="font-family:monospace;font-size:12px;color:#64748b">{{ row.age }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="176" fixed="right">
        <template #default="{ row }">
          <div style="display:flex;gap:6px;">
            <el-popconfirm v-if="canManage" title="确定重启该 Pod？" @confirm="restart(row)">
              <template #reference>
                <el-tooltip content="重启 Pod" placement="top" :show-after="500">
                  <button class="pod-op-btn pod-op-event"><el-icon :size="14"><RefreshRight /></el-icon></button>
                </el-tooltip>
              </template>
            </el-popconfirm>
            <el-tooltip content="查看日志" placement="top" :show-after="500">
              <button class="pod-op-btn pod-op-log" @click="emit('show-logs', row)"><el-icon :size="14"><Monitor /></el-icon></button>
            </el-tooltip>
            <el-tooltip content="查看 YAML" placement="top" :show-after="500">
              <button class="pod-op-btn pod-op-yaml" @click="emit('show-yaml', row)"><el-icon :size="14"><Document /></el-icon></button>
            </el-tooltip>
            <el-tooltip content="查看事件" placement="top" :show-after="500">
              <button class="pod-op-btn pod-op-event" @click="emit('show-events', row)"><el-icon :size="14"><Bell /></el-icon></button>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Document, Monitor, RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useK8sStore } from '@/stores/k8s'
import { getK8sWorkloadPods, restartK8sPod } from '@/api/modules/container'

const emit = defineEmits(['show-logs', 'show-yaml', 'show-events'])

const authStore = useAuthStore()
const k8sStore = useK8sStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))

const visible = ref(false)
const loading = ref(false)
const pods = ref([])
const workloadName = ref('')
const workloadType = ref('')
const workloadNamespace = ref('default')

async function open(type, name, namespace) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return ElMessage.warning('请先选择集群')
  workloadType.value = type
  workloadName.value = name
  workloadNamespace.value = namespace || k8sStore.effectiveNamespace || 'default'
  pods.value = []
  visible.value = true
  loading.value = true
  try {
    pods.value = await getK8sWorkloadPods(clusterId, type, name, workloadNamespace.value, k8sStore.selectedProjectId)
  } catch {
    ElMessage.error('获取 Pod 列表失败')
  }
  loading.value = false
}

async function restart(row) {
  if (!canManage.value) return
  try {
    const res = await restartK8sPod(k8sStore.selectedClusterId, row.name, row.namespace, k8sStore.selectedProjectId)
    ElMessage.success(res.message || 'Pod 正在重启')
    k8sStore.invalidateSummary(k8sStore.selectedClusterId)
    await open(workloadType.value, workloadName.value, workloadNamespace.value)
  } catch {
    ElMessage.error('Pod 重启失败')
  }
}

defineExpose({ open })
</script>
