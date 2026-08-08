<template>
  <el-dialog v-model="visible" :title="'YAML - ' + resourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
    <div class="yaml-viewer-toolbar">
      <span class="yaml-viewer-badge">{{ resourceType }}</span>
      <el-button size="small" type="primary" plain @click="copyYaml"><el-icon><DocumentCopy /></el-icon> 复制</el-button>
    </div>
    <div class="yaml-viewer-container" v-loading="loading">
      <pre class="yaml-viewer-code"><code>{{ content }}</code></pre>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy } from '@element-plus/icons-vue'
import { useK8sStore } from '@/stores/k8s'
import { getK8sResourceYaml } from '@/api/modules/container'

const k8sStore = useK8sStore()

const visible = ref(false)
const loading = ref(false)
const content = ref('')
const resourceName = ref('')
const resourceType = ref('')

async function open(type, name, namespace) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return ElMessage.warning('请先选择集群')
  resourceType.value = type
  resourceName.value = name
  content.value = ''
  visible.value = true
  loading.value = true
  try {
    const ns = namespace || k8sStore.effectiveNamespace || 'default'
    const res = await getK8sResourceYaml(clusterId, type, name, ns, k8sStore.selectedProjectId)
    content.value = res.yaml || res
  } catch {
    content.value = '# 获取 YAML 失败'
    ElMessage.error('获取 YAML 失败')
  }
  loading.value = false
}

function copyYaml() {
  navigator.clipboard.writeText(content.value)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

defineExpose({ open })
</script>
