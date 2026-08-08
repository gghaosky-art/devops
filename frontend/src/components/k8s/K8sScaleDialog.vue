<template>
  <el-dialog v-model="visible" :title="'弹性伸缩 - ' + form.name" width="90%" style="max-width:420px;" top="8vh" append-to-body destroy-on-close>
    <el-form label-width="100px">
      <el-form-item label="工作负载">
        <el-tag>{{ form.workload_type }}</el-tag>
      </el-form-item>
      <el-form-item label="命名空间">
        <el-tag type="info">{{ form.namespace }}</el-tag>
      </el-form-item>
      <el-form-item label="副本数">
        <el-input-number v-model="form.replicas" :min="0" :max="200" controls-position="right" style="width:180px;" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">应用</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useK8sStore } from '@/stores/k8s'
import { scaleK8sWorkload } from '@/api/modules/container'

const emit = defineEmits(['scaled'])

const k8sStore = useK8sStore()

const visible = ref(false)
const saving = ref(false)
const form = ref({ workload_type: 'deployment', name: '', namespace: 'default', replicas: 1 })

function open(workloadType, row) {
  form.value = {
    workload_type: workloadType,
    name: row.name,
    namespace: row.namespace || 'default',
    replicas: Number(row.replicas || 0),
  }
  visible.value = true
}

async function submit() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  saving.value = true
  try {
    const res = await scaleK8sWorkload(clusterId, { ...form.value })
    ElMessage.success(res.message || '伸缩指令已提交')
    visible.value = false
    k8sStore.invalidateSummary(clusterId)
    emit('scaled')
  } catch {
    ElMessage.error('伸缩失败')
  }
  saving.value = false
}

defineExpose({ open })
</script>
