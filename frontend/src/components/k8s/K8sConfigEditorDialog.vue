<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="90%" style="max-width:980px;" top="3vh" append-to-body destroy-on-close>
    <div class="filter-bar" style="margin-bottom:8px;">
      <el-tag type="info">{{ form.namespace }}</el-tag>
      <el-tag>{{ form.type }}</el-tag>
      <el-tag v-if="form.rollback_available" type="warning">可回滚</el-tag>
      <el-tag v-if="form.revision_count" type="success">历史 {{ form.revision_count }}</el-tag>
      <span class="config-editor-note">仅编辑 data/stringData，保存前建议先预览差异。</span>
    </div>
    <el-input v-model="form.content" type="textarea" :rows="18" placeholder="key: value" style="font-family:'Cascadia Code','Consolas',monospace;" />

    <div class="config-history-panel">
      <div class="config-history-head">
        <div class="config-history-title">
          <strong class="config-history-heading">历史版本</strong>
          <span class="config-history-note">每次保存前和回滚前都会自动留档，可随时预览差异并回滚到指定版本。</span>
        </div>
        <el-button size="small" plain :loading="revisionLoading" @click="fetchRevisions">刷新历史</el-button>
      </div>
      <el-table :data="revisions" size="small" stripe v-loading="revisionLoading" max-height="220" empty-text="暂无历史版本">
        <el-table-column prop="created_at" label="时间" min-width="180" show-overflow-tooltip />
        <el-table-column prop="action" label="动作" width="110">
          <template #default="{ row }">
            <el-tag :type="row.action === 'rollback' ? 'warning' : 'info'" size="small">
              {{ row.action === 'rollback' ? '回滚前快照' : '更新前快照' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-button link type="primary" @click="previewRevision(row)">预览</el-button>
              <el-button v-if="canManage" link type="warning" @click="rollbackToRevision(row)">回滚</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div style="display:flex;justify-content:space-between;gap:8px;margin-top:8px;flex-wrap:wrap;">
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <el-button @click="visible = false">关闭</el-button>
        <el-button type="info" plain :loading="previewLoading" @click="previewChange">预览本次变更</el-button>
        <el-button type="warning" plain :disabled="!form.rollback_available" :loading="previewLoading" @click="previewRollback">预览最近一次回滚</el-button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <el-button v-if="form.rollback_available" type="warning" :loading="saving" @click="applyRollback">回滚到上一版本</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </div>
    </div>
  </el-dialog>

  <el-dialog v-model="diffVisible" :title="diffTitle" width="90%" style="max-width:980px;" top="4vh" append-to-body destroy-on-close>
    <pre class="log-output terminal-log" style="min-height:320px;">{{ diffContent || '暂无差异' }}</pre>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useK8sStore } from '@/stores/k8s'
import {
  getK8sConfigResourceDetail, getK8sConfigRevisionPreview, getK8sConfigRevisions,
  getK8sConfigRollbackPreview, previewK8sConfigResource, rollbackK8sConfigResource,
  rollbackK8sConfigResourceToRevision, updateK8sConfigResource,
} from '@/api/modules/container'

const emit = defineEmits(['saved'])

const authStore = useAuthStore()
const k8sStore = useK8sStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))

const visible = ref(false)
const previewLoading = ref(false)
const saving = ref(false)
const revisionLoading = ref(false)
const revisions = ref([])
const diffVisible = ref(false)
const diffTitle = ref('差异预览')
const diffContent = ref('')
const form = ref({
  type: 'configmap',
  name: '',
  namespace: 'default',
  content: '',
  rollback_available: false,
  revision_count: 0,
})

const dialogTitle = computed(() => `${form.value.type} 配置 - ${form.value.name}`)

function syncRevisionState(detail = {}) {
  if (typeof detail.rollback_available === 'boolean') {
    form.value.rollback_available = detail.rollback_available
  }
  form.value.revision_count = typeof detail.revision_count === 'number'
    ? detail.revision_count
    : revisions.value.length
}

async function open(type, row) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  previewLoading.value = true
  try {
    const detail = await getK8sConfigResourceDetail(clusterId, type, row.name, row.namespace, k8sStore.selectedProjectId)
    form.value = {
      type,
      name: row.name,
      namespace: row.namespace || 'default',
      content: detail.text || '',
      rollback_available: detail.rollback_available || false,
      revision_count: detail.revision_count || 0,
    }
    revisions.value = []
    visible.value = true
    await fetchRevisions()
  } catch {
    ElMessage.error('加载配置详情失败')
  }
  previewLoading.value = false
}

async function fetchRevisions() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId || !form.value.name) return
  revisionLoading.value = true
  try {
    const res = await getK8sConfigRevisions(clusterId, form.value.type, form.value.name, form.value.namespace)
    revisions.value = res.items || []
    syncRevisionState({ revision_count: revisions.value.length, rollback_available: revisions.value.length > 0 })
  } catch {
    revisions.value = []
    ElMessage.error('加载配置历史失败')
  }
  revisionLoading.value = false
}

function showDiff(title, diff, fallback) {
  diffTitle.value = title
  diffContent.value = diff || fallback
  diffVisible.value = true
}

async function previewChange() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  previewLoading.value = true
  try {
    const res = await previewK8sConfigResource(clusterId, { ...form.value })
    showDiff(`保存前预览 - ${form.value.name}`, res.diff, '暂无差异')
  } catch {
    ElMessage.error('配置预览失败')
  }
  previewLoading.value = false
}

async function previewRollback() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  previewLoading.value = true
  try {
    const res = await getK8sConfigRollbackPreview(clusterId, form.value.type, form.value.name, form.value.namespace)
    showDiff(`最近回滚预览 - ${form.value.name}`, res.diff, '当前版本与最近一次回滚没有差异')
  } catch {
    ElMessage.error('回滚预览失败')
  }
  previewLoading.value = false
}

async function previewRevision(row) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  previewLoading.value = true
  try {
    const res = await getK8sConfigRevisionPreview(clusterId, form.value.type, form.value.name, form.value.namespace, row.id)
    showDiff(`历史版本预览 - #${row.id}`, res.diff, '暂无差异')
  } catch {
    ElMessage.error('加载历史版本预览失败')
  }
  previewLoading.value = false
}

/** 保存与两种回滚的收尾动作一致：刷新历史、让概览失效、通知页面重新取列表。 */
async function afterMutation(resource, message, fallbackMessage) {
  form.value.content = resource?.text || form.value.content
  syncRevisionState(resource)
  ElMessage.success(message || fallbackMessage)
  await fetchRevisions()
  k8sStore.invalidateSummary(k8sStore.selectedClusterId)
  emit('saved')
}

async function save() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  saving.value = true
  try {
    const res = await updateK8sConfigResource(clusterId, { ...form.value })
    await afterMutation(res.resource, res.message, '配置已更新')
  } catch {
    ElMessage.error('保存配置失败')
  }
  saving.value = false
}

async function applyRollback() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  saving.value = true
  try {
    const res = await rollbackK8sConfigResource(clusterId, {
      type: form.value.type,
      name: form.value.name,
      namespace: form.value.namespace,
    })
    await afterMutation(res.resource, res.message, '配置已回滚')
  } catch {
    ElMessage.error('回滚失败')
  }
  saving.value = false
}

async function rollbackToRevision(row) {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId) return
  saving.value = true
  try {
    const res = await rollbackK8sConfigResourceToRevision(clusterId, {
      type: form.value.type,
      name: form.value.name,
      namespace: form.value.namespace,
      revision_id: row.id,
    })
    await afterMutation(res.resource, res.message, '已回滚到指定历史版本')
  } catch {
    ElMessage.error('回滚到指定历史版本失败')
  }
  saving.value = false
}

defineExpose({ open })
</script>
