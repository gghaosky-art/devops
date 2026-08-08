<template>
  <div class="quota-editor">
    <div class="quota-grid">
      <div v-for="field in QUOTA_FIELDS" :key="field.key" class="quota-field">
        <span class="quota-label">
          {{ field.label }}
          <el-tooltip :content="field.hint" placement="top"><span class="quota-key">{{ field.key }}</span></el-tooltip>
        </span>
        <el-input
          :model-value="quota[field.key] || ''"
          :placeholder="field.placeholder"
          clearable
          @update:model-value="value => setQuota(field.key, value)"
        />
      </div>
    </div>

    <template v-if="showLimitRange">
    <div class="quota-section-head">
      <span class="quota-section-title">默认资源限制（LimitRange）</span>
      <span class="quota-section-note">为未声明 requests/limits 的容器提供默认值</span>
    </div>
    <div class="quota-grid">
      <div v-for="field in LIMIT_FIELDS" :key="field.path" class="quota-field">
        <span class="quota-label">{{ field.label }}</span>
        <el-input
          :model-value="readLimit(field)"
          :placeholder="field.placeholder"
          clearable
          @update:model-value="value => setLimit(field, value)"
        />
      </div>
    </div>
    </template>
  </div>
</template>

<script setup>
// 直接使用 ResourceQuota 的 hard 键名，不做映射层，便于和 kubectl 对照
const QUOTA_FIELDS = [
  { key: 'requests.cpu', label: 'CPU 申请上限', placeholder: '例如 8', hint: 'ResourceQuota hard.requests.cpu' },
  { key: 'requests.memory', label: '内存申请上限', placeholder: '例如 16Gi', hint: 'ResourceQuota hard.requests.memory' },
  { key: 'limits.cpu', label: 'CPU 限制上限', placeholder: '例如 16', hint: 'ResourceQuota hard.limits.cpu' },
  { key: 'limits.memory', label: '内存限制上限', placeholder: '例如 32Gi', hint: 'ResourceQuota hard.limits.memory' },
  { key: 'requests.storage', label: '存储申请上限', placeholder: '例如 500Gi', hint: 'ResourceQuota hard.requests.storage' },
  { key: 'pods', label: 'Pod 数量上限', placeholder: '例如 100', hint: 'ResourceQuota hard.pods' },
]

const LIMIT_FIELDS = [
  { path: ['defaultRequest', 'cpu'], label: '默认 CPU 申请', placeholder: '例如 100m' },
  { path: ['defaultRequest', 'memory'], label: '默认内存申请', placeholder: '例如 128Mi' },
  { path: ['default', 'cpu'], label: '默认 CPU 限制', placeholder: '例如 500m' },
  { path: ['default', 'memory'], label: '默认内存限制', placeholder: '例如 512Mi' },
]

const props = defineProps({
  quota: { type: Object, default: () => ({}) },
  limitRange: { type: Object, default: () => ({}) },
  showLimitRange: { type: Boolean, default: true },
})

const emit = defineEmits(['update:quota', 'update:limitRange'])

/** 空值直接从对象里删掉，避免给后端下发空字符串。 */
function setQuota(key, value) {
  const next = { ...props.quota }
  if (String(value || '').trim()) next[key] = String(value).trim()
  else delete next[key]
  emit('update:quota', next)
}

function readLimit(field) {
  const [group, key] = field.path
  return props.limitRange?.[group]?.[key] || ''
}

function setLimit(field, value) {
  const [group, key] = field.path
  const next = { ...props.limitRange, [group]: { ...(props.limitRange?.[group] || {}) } }
  if (String(value || '').trim()) next[group][key] = String(value).trim()
  else delete next[group][key]
  if (!Object.keys(next[group]).length) delete next[group]
  emit('update:limitRange', next)
}
</script>

<style scoped>
.quota-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.quota-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.quota-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.quota-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.quota-key {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  font-weight: 400;
  color: #94a3b8;
  cursor: help;
}

.quota-section-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px dashed rgba(148, 163, 184, 0.4);
}

.quota-section-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}

.quota-section-note {
  font-size: 12px;
  color: #94a3b8;
}
</style>
