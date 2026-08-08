<template>
  <el-dialog v-model="visible" :title="'日志 - ' + podName" width="90%" style="max-width:900px;" top="3vh" append-to-body destroy-on-close>
    <div class="log-viewer-toolbar">
      <div style="display:flex;align-items:center;gap:10px;">
        <span class="yaml-viewer-badge" style="background:linear-gradient(135deg,#10b981,#059669)">{{ container }}</span>
        <el-select v-if="containers.length > 1" v-model="container" size="small" style="width:140px" @change="fetchLog">
          <el-option v-for="c in containers" :key="c" :label="c" :value="c" />
        </el-select>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:12px;color:#94a3b8">行数:</span>
        <el-select v-model="tailLines" size="small" style="width:80px" @change="fetchLog">
          <el-option :value="50" label="50" />
          <el-option :value="100" label="100" />
          <el-option :value="200" label="200" />
          <el-option :value="500" label="500" />
        </el-select>
        <el-button size="small" type="primary" plain @click="copyLog"><el-icon><DocumentCopy /></el-icon> 复制</el-button>
      </div>
    </div>
    <div class="log-viewer-container" v-loading="loading" ref="containerRef">
      <pre class="log-viewer-code">{{ content }}</pre>
    </div>
  </el-dialog>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy } from '@element-plus/icons-vue'
import { useK8sStore } from '@/stores/k8s'
import { getK8sPodLogs } from '@/api/modules/container'

const k8sStore = useK8sStore()

const visible = ref(false)
const loading = ref(false)
const content = ref('')
const podName = ref('')
const podNamespace = ref('default')
const container = ref('')
const containers = ref([])
const tailLines = ref(200)
const containerRef = ref(null)

function open(name, namespace, containerNames) {
  podName.value = name
  podNamespace.value = namespace || 'default'
  containers.value = containerNames?.length ? containerNames : ['main']
  container.value = containers.value[0]
  content.value = ''
  visible.value = true
  fetchLog()
}

async function fetchLog() {
  loading.value = true
  try {
    const res = await getK8sPodLogs(
      k8sStore.selectedClusterId,
      podName.value,
      podNamespace.value,
      container.value,
      tailLines.value,
      k8sStore.selectedProjectId,
    )
    content.value = res.logs || ''
    await nextTick()
    if (containerRef.value) {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
  } catch {
    content.value = '# 获取日志失败'
    ElMessage.error('获取日志失败')
  }
  loading.value = false
}

function copyLog() {
  navigator.clipboard.writeText(content.value)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

defineExpose({ open })
</script>
