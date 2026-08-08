<template>
  <K8sPageShell title="项目管理" desc="项目对应集群中的命名空间，支持平台新建与纳管已有命名空间。" icon="Files" :cards="cards">
    <div class="workbench-card k8s-cluster-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">项目列表</span>
          <span class="toolbar-desc">每个项目绑定所属企业空间集群中的一个命名空间。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn" @click="load"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          <el-button
            v-if="canManage"
            class="filter-refresh-btn"
            :disabled="!workspaces.length"
            @click="openCreate"
          >
            <el-icon><Plus /></el-icon>新增项目
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history k8s-cluster-toolbar">
        <div class="workbench-toolbar-left">
          <el-input v-model="keyword" clearable placeholder="搜索项目名称、命名空间或描述" style="width: 300px" />
          <el-select v-model="workspaceFilter" clearable placeholder="全部企业空间" style="width:200px;margin-left:8px">
            <el-option v-for="ws in workspaces" :key="ws.id" :label="ws.display_name" :value="ws.id" />
          </el-select>
        </div>
        <div class="workbench-toolbar-right">
          <el-tag size="large" type="info">项目总数 {{ projects.length }}</el-tag>
          <el-tag size="large" type="warning">已下发配额 {{ enforcedCount }}</el-tag>
        </div>
      </div>

      <el-alert
        v-if="canManage && !workspaces.length"
        type="warning"
        :closable="false"
        show-icon
        title="还没有企业空间"
        description="项目必须归属于某个企业空间，请先在「企业空间」中创建。"
        style="margin-bottom:8px;"
      />

      <el-table :data="filtered" stripe v-loading="loading" style="width:100%" empty-text="还没有项目">
        <el-table-column label="项目" min-width="220">
          <template #default="{ row }">
            <div class="proj-name-cell">
              <span class="state-pulse running"></span>
              <div class="proj-name-text">
                <span class="proj-display">{{ row.display_name }}</span>
                <span class="proj-ns">{{ row.namespace }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="workspace_name" label="企业空间" min-width="150" />
        <el-table-column prop="cluster_name" label="集群" min-width="140" />
        <el-table-column label="创建方式" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.provision_mode === 'adopt' ? 'warning' : 'success'">
              {{ row.provision_mode === 'adopt' ? '纳管已有' : '平台创建' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配额" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <el-tag size="small" :type="row.quota_enforced ? 'danger' : 'info'">
                {{ row.quota_enforced ? '已下发集群' : '仅平台展示' }}
              </el-tag>
              <span v-if="quotaSummary(row.quota)" style="font-family:'Cascadia Code','Consolas',monospace;font-size:11px;color:#64748b">
                {{ quotaSummary(row.quota) }}
              </span>
              <span v-else style="color:#94a3b8;font-size:12px">未设置</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="member_count" label="成员" width="80" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openUsage(row)">用量</el-button>
            <el-button link type="primary" size="small" @click="memberDialog.open(row)">成员</el-button>
            <template v-if="canManage">
              <el-button link type="info" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="openDelete(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ============ 新建 / 编辑 ============ -->
    <el-dialog
      v-model="formVisible"
      :title="editingId ? '编辑项目' : '新增项目'"
      width="90%"
      style="max-width:720px;"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form :model="form" label-width="120px">
        <el-form-item label="所属企业空间">
          <el-select v-model="form.workspace" :disabled="!!editingId" style="width:100%" @change="onWorkspaceChange">
            <el-option v-for="ws in workspaces" :key="ws.id" :label="`${ws.display_name}（${ws.cluster_name}）`" :value="ws.id" />
          </el-select>
          <div class="form-hint">项目落在企业空间绑定的集群里，创建后不可更换。</div>
        </el-form-item>

        <el-form-item v-if="!editingId" label="命名空间来源">
          <el-radio-group v-model="form.provision_mode" @change="onModeChange">
            <el-radio value="create">平台创建</el-radio>
            <el-radio value="adopt">纳管已有</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="命名空间">
          <el-input v-if="editingId || form.provision_mode === 'create'" v-model="form.namespace" :disabled="!!editingId" placeholder="小写字母、数字与中划线，例如 team-a-prod" />
          <el-select
            v-else
            v-model="form.namespace"
            filterable
            :loading="adoptableLoading"
            placeholder="选择要纳管的命名空间"
            style="width:100%"
          >
            <template #empty>
              <div style="padding:16px;text-align:center;color:#94a3b8;font-size:12px;">
                {{ adoptableLoading ? '加载中…' : '该集群没有可纳管的命名空间' }}
              </div>
            </template>
            <el-option v-for="ns in adoptable" :key="ns.name" :label="ns.name" :value="ns.name">
              <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                <span>{{ ns.name }}</span>
                <el-tag v-if="ns.warning" size="small" type="warning">{{ ns.warning }}</el-tag>
              </div>
            </el-option>
          </el-select>
          <div v-if="!editingId" class="form-hint">
            {{ form.provision_mode === 'create'
              ? '平台会在集群中创建该命名空间并打上归属标签。'
              : '仅接管已存在且未被占用的命名空间，其中的工作负载不受影响。' }}
          </div>
        </el-form-item>

        <el-form-item label="项目名称">
          <el-input v-model="form.display_name" placeholder="用于展示，例如 A 团队生产" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="用途说明" />
        </el-form-item>

        <el-form-item label="配额">
          <K8sQuotaEditor v-model:quota="form.quota" v-model:limit-range="form.limit_range" />
        </el-form-item>

        <el-form-item label="下发到集群">
          <el-switch v-model="form.quota_enforced" />
          <div class="form-hint">
            关闭时配额只在平台侧统计展示，集群中不会创建 ResourceQuota。
          </div>
        </el-form-item>

        <el-alert
          v-if="enforceWarning"
          type="warning"
          :closable="false"
          show-icon
          title="开启下发会影响命名空间内的所有工作负载"
          style="margin-left:120px;width:calc(100% - 120px);"
        >
          <template #default>
            ResourceQuota 一旦限制 requests/limits，该命名空间内<strong>未显式声明资源的 Pod 将被集群拒绝创建</strong>。
            已运行的 Pod 不受影响，但下次滚动更新会失败。建议同时填写上方的「默认资源限制」作为兜底。
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 删除 ============ -->
    <el-dialog v-model="deleteVisible" title="删除项目" width="90%" style="max-width:600px;" top="8vh" append-to-body destroy-on-close>
      <p style="margin:0 0 12px;color:#475569;">
        项目 <strong>{{ deleteTarget?.display_name }}</strong>
        绑定命名空间 <code>{{ deleteTarget?.namespace }}</code>。
      </p>
      <el-radio-group v-model="deleteMode" class="delete-modes">
        <el-radio value="detach">
          <span class="delete-mode-title">仅移出平台（推荐）</span>
          <span class="delete-mode-desc">
            只删除平台侧记录，不对集群发出任何写请求。归属标签与配额对象会原样留在命名空间上。
          </span>
        </el-radio>
        <el-radio value="release">
          <span class="delete-mode-title">解绑并清理集群标记</span>
          <span class="delete-mode-desc">额外移除归属标签与平台下发的配额对象，命名空间及其中的工作负载全部保留。</span>
        </el-radio>
        <el-radio value="purge" :disabled="deleteTarget?.provision_mode === 'adopt'">
          <span class="delete-mode-title">删除命名空间</span>
          <span class="delete-mode-desc">
            {{ deleteTarget?.provision_mode === 'adopt'
              ? '纳管而来的命名空间不允许通过平台删除。'
              : '连同命名空间内的全部资源一并删除，不可恢复。' }}
          </span>
        </el-radio>
      </el-radio-group>

      <div v-if="deleteMode === 'purge'" style="margin-top:12px;">
        <div class="form-hint" style="margin-bottom:6px;">请输入命名空间名称 <code>{{ deleteTarget?.namespace }}</code> 以确认：</div>
        <el-input v-model="purgeConfirm" placeholder="输入命名空间名称" />
      </div>

      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="deleting"
          :disabled="deleteMode === 'purge' && purgeConfirm !== deleteTarget?.namespace"
          @click="confirmDelete"
        >
          {{ DELETE_MODE_LABELS[deleteMode] }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 用量 ============ -->
    <el-dialog v-model="usageVisible" :title="`资源用量 - ${usageTarget?.display_name || ''}`" width="90%" style="max-width:720px;" top="6vh" append-to-body destroy-on-close>
      <div v-loading="usageLoading" style="min-height:180px;">
        <div class="usage-head">
          <el-tag type="info">{{ usageTarget?.namespace }}</el-tag>
          <el-tag :type="usageTarget?.quota_enforced ? 'danger' : 'info'">
            {{ usageTarget?.quota_enforced ? '配额已下发集群' : '配额仅平台展示' }}
          </el-tag>
          <el-tag>Pod {{ usage?.usage?.pods ?? 0 }}</el-tag>
        </div>

        <el-table :data="usageRows" size="small" stripe empty-text="暂无数据" style="width:100%;margin-top:10px;">
          <el-table-column prop="label" label="指标" min-width="140" />
          <el-table-column prop="requested" label="已申请" min-width="120" />
          <el-table-column prop="quota" label="配额" min-width="120">
            <template #default="{ row }">
              <span v-if="row.quota">{{ row.quota }}</span>
              <span v-else style="color:#94a3b8">未设置</span>
            </template>
          </el-table-column>
          <el-table-column v-if="usage?.usage?.metrics_available" prop="live" label="实时用量" min-width="120" />
        </el-table>

        <el-alert
          v-if="usage && !usage.usage?.metrics_available"
          type="info"
          :closable="false"
          show-icon
          title="实时用量不可用"
          description="集群未安装 metrics-server，只能展示由 Pod spec 累加得到的「已申请量」。"
          style="margin-top:10px;"
        />
      </div>
      <template #footer>
        <el-button v-if="canManage" :loading="syncing" @click="syncQuota">重新下发配额</el-button>
        <el-button @click="usageVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <K8sMemberDialog
      ref="memberDialog"
      :can-manage="canManage"
      :fetch-members="getK8sProjectMembers"
      :add-member="addK8sProjectMember"
      :remove-member="removeK8sProjectMember"
      @changed="load"
    />
  </K8sPageShell>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sMemberDialog from '@/components/k8s/K8sMemberDialog.vue'
import K8sQuotaEditor from '@/components/k8s/K8sQuotaEditor.vue'
import {
  addK8sProjectMember, createK8sProject, deleteK8sProject, getK8sAdoptableNamespaces,
  getK8sProjectMembers, getK8sProjectUsage, getK8sProjects, getK8sWorkspaces,
  removeK8sProjectMember, syncK8sProjectQuota, updateK8sProject,
} from '@/api/modules/container'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.project.manage'))

const DELETE_MODE_LABELS = {
  detach: '移出平台',
  release: '解绑',
  purge: '删除命名空间',
}
const DELETE_MODE_DONE = {
  detach: '项目已移出平台，集群未做改动',
  release: '项目已解绑',
  purge: '命名空间已删除',
}

const projects = ref([])
const workspaces = ref([])
const loading = ref(false)
const keyword = ref('')
const workspaceFilter = ref(null)

const formVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = ref(emptyForm())
const adoptable = ref([])
const adoptableLoading = ref(false)

const deleteVisible = ref(false)
const deleteTarget = ref(null)
const deleteMode = ref('detach')
const purgeConfirm = ref('')
const deleting = ref(false)

const usageVisible = ref(false)
const usageTarget = ref(null)
const usage = ref(null)
const usageLoading = ref(false)
const syncing = ref(false)

const memberDialog = ref(null)

function emptyForm() {
  return {
    workspace: null,
    namespace: '',
    display_name: '',
    description: '',
    provision_mode: 'create',
    quota: {},
    limit_range: {},
    quota_enforced: false,
  }
}

const filtered = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  return projects.value.filter((item) => {
    if (workspaceFilter.value && item.workspace !== workspaceFilter.value) return false
    if (!text) return true
    return [item.display_name, item.namespace, item.description, item.workspace_name]
      .some(field => String(field || '').toLowerCase().includes(text))
  })
})

const enforcedCount = computed(() => projects.value.filter(item => item.quota_enforced).length)

const cards = computed(() => [
  { label: '项目总数', value: projects.value.length, tone: '' },
  { label: '平台创建', value: projects.value.filter(item => item.provision_mode === 'create').length, tone: 'success-card' },
  { label: '纳管已有', value: projects.value.filter(item => item.provision_mode === 'adopt').length, tone: 'warning-card' },
  { label: '已下发配额', value: enforcedCount.value, tone: 'danger-card' },
])

/** 开了下发、设了配额、却没有默认值 —— 正是会导致 Pod 被拒绝创建的组合。 */
const enforceWarning = computed(() => {
  const hasQuota = Object.keys(form.value.quota || {}).length > 0
  const hasLimits = Object.keys(form.value.limit_range || {}).length > 0
  return form.value.quota_enforced && hasQuota && !hasLimits
})

const usageRows = computed(() => {
  const data = usage.value?.usage
  if (!data) return []
  const quota = usage.value?.quota || {}
  const live = data.live || {}
  return [
    {
      label: 'CPU（核）',
      requested: formatCpu(data.requests?.cpu),
      quota: quota['requests.cpu'] || '',
      live: data.metrics_available ? formatCpu(live.cpu) : '-',
    },
    {
      label: '内存',
      requested: formatBytes(data.requests?.memory),
      quota: quota['requests.memory'] || '',
      live: data.metrics_available ? formatBytes(live.memory) : '-',
    },
    {
      label: 'CPU 限制（核）',
      requested: formatCpu(data.limits?.cpu),
      quota: quota['limits.cpu'] || '',
      live: '-',
    },
    {
      label: '内存限制',
      requested: formatBytes(data.limits?.memory),
      quota: quota['limits.memory'] || '',
      live: '-',
    },
  ]
})

function formatCpu(value) {
  return `${Number(value || 0).toFixed(2)}`
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!bytes) return '0'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let index = 0
  let result = bytes
  while (result >= 1024 && index < units.length - 1) {
    result /= 1024
    index += 1
  }
  return `${result.toFixed(index ? 2 : 0)} ${units[index]}`
}

function quotaSummary(quota) {
  const entries = Object.entries(quota || {}).filter(([, value]) => value)
  if (!entries.length) return ''
  return entries.slice(0, 2).map(([key, value]) => `${key}=${value}`).join('  ')
    + (entries.length > 2 ? ` +${entries.length - 2}` : '')
}

async function load() {
  loading.value = true
  try {
    const [projectRes, workspaceRes] = await Promise.all([getK8sProjects(), getK8sWorkspaces()])
    projects.value = projectRes.results || projectRes || []
    workspaces.value = workspaceRes.results || workspaceRes || []
  } catch {
    projects.value = []
  }
  loading.value = false
}

function selectedWorkspace() {
  return workspaces.value.find(item => item.id === form.value.workspace) || null
}

async function loadAdoptable() {
  const workspace = selectedWorkspace()
  if (!workspace) {
    adoptable.value = []
    return
  }
  adoptableLoading.value = true
  try {
    adoptable.value = await getK8sAdoptableNamespaces(workspace.cluster)
  } catch {
    // 错误详情已由请求拦截器统一提示，这里只需清空候选列表
    adoptable.value = []
  }
  adoptableLoading.value = false
}

function onWorkspaceChange() {
  form.value.namespace = ''
  if (form.value.provision_mode === 'adopt') loadAdoptable()
}

function onModeChange() {
  form.value.namespace = ''
  if (form.value.provision_mode === 'adopt') loadAdoptable()
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  form.value.workspace = workspaceFilter.value || workspaces.value[0]?.id || null
  adoptable.value = []
  formVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  form.value = {
    workspace: row.workspace,
    namespace: row.namespace,
    display_name: row.display_name,
    description: row.description,
    provision_mode: row.provision_mode,
    quota: { ...(row.quota || {}) },
    limit_range: JSON.parse(JSON.stringify(row.limit_range || {})),
    quota_enforced: row.quota_enforced,
  }
  formVisible.value = true
}

async function save() {
  if (!form.value.workspace) return ElMessage.warning('请选择所属企业空间')
  if (!form.value.namespace) return ElMessage.warning('请填写或选择命名空间')
  if (!form.value.display_name) return ElMessage.warning('请填写项目名称')

  saving.value = true
  try {
    if (editingId.value) {
      // workspace / namespace / provision_mode 创建后不可改，不提交
      const { workspace, namespace, provision_mode, ...payload } = form.value
      const res = await updateK8sProject(editingId.value, payload)
      ElMessage.success('项目已更新')
      notifyWarnings(res?.warnings)
    } else {
      const res = await createK8sProject(form.value)
      ElMessage.success('项目已创建')
      notifyWarnings(res?.warnings)
    }
    formVisible.value = false
    await load()
  } catch {
    // 错误详情已由请求拦截器统一提示
  }
  saving.value = false
}

function notifyWarnings(warnings) {
  for (const text of warnings || []) {
    ElMessage({ type: 'warning', message: text, duration: 8000, showClose: true })
  }
}

function openDelete(row) {
  deleteTarget.value = row
  deleteMode.value = 'detach'
  purgeConfirm.value = ''
  deleteVisible.value = true
}

async function confirmDelete() {
  deleting.value = true
  try {
    await deleteK8sProject(deleteTarget.value.id, deleteMode.value)
    ElMessage.success(DELETE_MODE_DONE[deleteMode.value])
    deleteVisible.value = false
    await load()
  } catch {
    // 错误详情已由请求拦截器统一提示
  }
  deleting.value = false
}

async function openUsage(row) {
  usageTarget.value = row
  usage.value = null
  usageVisible.value = true
  usageLoading.value = true
  try {
    usage.value = await getK8sProjectUsage(row.id)
  } catch {
    ElMessage.error('读取用量失败')
  }
  usageLoading.value = false
}

async function syncQuota() {
  syncing.value = true
  try {
    const res = await syncK8sProjectQuota(usageTarget.value.id)
    ElMessage.success(res.message || '已同步')
    notifyWarnings(res?.warnings)
  } catch {
    // 错误详情已由请求拦截器统一提示
  }
  syncing.value = false
}

// 编辑态下切到纳管模式不需要候选列表，仅新建时按需加载
watch(() => form.value.provision_mode, (mode) => {
  if (!editingId.value && mode === 'adopt' && !adoptable.value.length) loadAdoptable()
})

onMounted(load)
</script>

<style scoped>
.proj-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.proj-name-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.4;
}

.proj-display {
  font-weight: 600;
  color: #0f172a;
}

.proj-ns {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  color: #94a3b8;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}

.delete-modes {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}

.delete-modes :deep(.el-radio) {
  height: auto;
  align-items: flex-start;
  margin-right: 0;
}

.delete-modes :deep(.el-radio__label) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  white-space: normal;
  line-height: 1.5;
}

.delete-mode-title {
  font-weight: 600;
  color: #0f172a;
}

.delete-mode-desc {
  font-size: 12px;
  color: #94a3b8;
}

.usage-head {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
