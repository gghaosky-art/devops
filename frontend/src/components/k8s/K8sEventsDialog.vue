<template>
  <el-dialog v-model="visible" :title="'事件 - ' + resourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
    <div v-loading="loading" style="min-height:120px;">
      <div v-if="events.length === 0 && !loading" style="text-align:center;padding:40px;color:#94a3b8;">
        <el-icon :size="48" style="margin-bottom:8px;opacity:0.4"><Bell /></el-icon>
        <div>暂无事件</div>
      </div>
      <div v-else class="events-timeline">
        <div
          v-for="(ev, i) in events"
          :key="i"
          class="event-item"
          :class="ev.type === 'Warning' ? 'event-warning' : 'event-normal'"
        >
          <div class="event-indicator"></div>
          <div class="event-body">
            <div class="event-header">
              <el-tag :type="ev.type === 'Warning' ? 'warning' : ''" size="small" effect="dark" style="font-size:11px">{{ ev.type }}</el-tag>
              <span class="event-reason">{{ ev.reason }}</span>
              <span v-if="ev.count > 1" class="event-count">×{{ ev.count }}</span>
              <span class="event-time">{{ formatEventTime(ev.last_time) }}</span>
            </div>
            <div class="event-message">{{ ev.message }}</div>
            <div class="event-source" v-if="ev.source">{{ ev.source }}</div>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import { useK8sStore } from '@/stores/k8s'
import { getK8sResourceEvents } from '@/api/modules/container'

const k8sStore = useK8sStore()

const visible = ref(false)
const loading = ref(false)
const events = ref([])
const resourceName = ref('')

async function open(type, name, namespace) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return ElMessage.warning('请先选择集群')
  resourceName.value = `${type}/${name}`
  events.value = []
  visible.value = true
  loading.value = true
  try {
    const ns = namespace || k8sStore.effectiveNamespace || 'default'
    events.value = await getK8sResourceEvents(clusterId, type, name, ns, k8sStore.selectedProjectId)
  } catch {
    ElMessage.error('获取事件失败')
  }
  loading.value = false
}

function formatEventTime(iso) {
  if (!iso) return '-'
  try {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch {
    return iso
  }
}

defineExpose({ open })
</script>
