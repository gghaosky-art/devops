<template>
  <K8sPageShell title="企业空间" desc="按企业空间划分集群资源归属与成员可见范围。" icon="Grid" :cards="cards">
    <div class="workbench-card k8s-cluster-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">企业空间列表</span>
          <span class="toolbar-desc">每个企业空间绑定单一集群，下辖的项目都落在该集群里。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn" @click="load">
            <el-icon><RefreshRight /></el-icon>刷新
          </el-button>
          <el-button v-if="canManage" class="filter-refresh-btn" @click="openDialog()">
            <el-icon><Plus /></el-icon>新增企业空间
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history k8s-cluster-toolbar">
        <div class="workbench-toolbar-left">
          <el-input v-model="keyword" clearable placeholder="搜索标识、名称、集群或描述" style="width: 320px" />
        </div>
        <div class="workbench-toolbar-right">
          <el-tag size="large" type="info">空间总数 {{ workspaces.length }}</el-tag>
        </div>
      </div>

      <el-table :data="filtered" stripe v-loading="loading" style="width:100%" empty-text="还没有企业空间">
        <el-table-column label="企业空间" min-width="220">
          <template #default="{ row }">
            <div class="ws-name-cell">
              <span class="state-pulse" :class="row.status === 'active' ? 'running' : 'exited'"></span>
              <div class="ws-name-text">
                <span class="ws-display">{{ row.display_name }}</span>
                <span class="ws-slug">{{ row.name }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="所属集群" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="state-pulse" :class="row.cluster_status === 'connected' ? 'running' : 'exited'"></span>
              <span>{{ row.cluster_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="project_count" label="项目数" width="90" />
        <el-table-column prop="member_count" label="成员数" width="90" />
        <el-table-column label="配额" min-width="200">
          <template #default="{ row }">
            <span v-if="!quotaSummary(row.quota)" style="color:#94a3b8">未设置</span>
            <span v-else style="font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ quotaSummary(row.quota) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_by" label="创建人" width="120" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="memberDialog.open(row)">成员</el-button>
            <template v-if="canManage">
              <el-button link type="info" size="small" @click="openDialog(row)">编辑</el-button>
              <el-popconfirm
                title="确定删除该企业空间？下辖项目需先删除。"
                @confirm="remove(row)"
              >
                <template #reference><el-button link type="danger" size="small">删除</el-button></template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑企业空间' : '新增企业空间'"
      width="90%"
      style="max-width:640px;"
      top="6vh"
      append-to-body
      destroy-on-close
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="标识">
          <el-input v-model="form.name" :disabled="!!editingId" placeholder="小写字母、数字与中划线，例如 team-a" />
          <div class="form-hint">
            {{ editingId
              ? '标识已写入集群命名空间标签，创建后不可修改。'
              : '会作为 sxdevops.io/workspace 标签写入下辖项目的命名空间。' }}
          </div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.display_name" placeholder="用于展示，例如 A 团队" />
        </el-form-item>
        <el-form-item label="所属集群">
          <el-select v-model="form.cluster" :disabled="!!editingId" placeholder="选择集群" style="width:100%">
            <el-option v-for="c in clusters" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <div class="form-hint">企业空间绑定单一集群，创建后不可更换。</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="用途说明" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="空间配额">
          <K8sQuotaEditor v-model:quota="form.quota" :show-limit-range="false" />
          <div class="form-hint">空间配额目前仅用于平台侧汇总展示，实际下发以项目为单位。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <K8sMemberDialog
      ref="memberDialog"
      :can-manage="canManage"
      :fetch-members="getK8sWorkspaceMembers"
      :add-member="addK8sWorkspaceMember"
      :remove-member="removeK8sWorkspaceMember"
      @changed="load"
    />
  </K8sPageShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Plus, RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useK8sStore } from '@/stores/k8s'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sMemberDialog from '@/components/k8s/K8sMemberDialog.vue'
import K8sQuotaEditor from '@/components/k8s/K8sQuotaEditor.vue'
import {
  addK8sWorkspaceMember, createK8sWorkspace, deleteK8sWorkspace, getK8sWorkspaceMembers,
  getK8sWorkspaces, removeK8sWorkspaceMember, updateK8sWorkspace,
} from '@/api/modules/container'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.workspace.manage'))

const k8sStore = useK8sStore()
const { clusters } = storeToRefs(k8sStore)

const workspaces = ref([])
const loading = ref(false)
const keyword = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const memberDialog = ref(null)
const form = ref(emptyForm())

function emptyForm() {
  return { name: '', display_name: '', cluster: null, description: '', status: 'active', quota: {} }
}

const filtered = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return workspaces.value
  return workspaces.value.filter(item => [item.name, item.display_name, item.cluster_name, item.description]
    .some(field => String(field || '').toLowerCase().includes(text)))
})

const cards = computed(() => [
  { label: '企业空间', value: workspaces.value.length, tone: '' },
  { label: '项目总数', value: workspaces.value.reduce((sum, item) => sum + (item.project_count || 0), 0), tone: 'success-card' },
  { label: '成员总数', value: workspaces.value.reduce((sum, item) => sum + (item.member_count || 0), 0), tone: 'warning-card' },
  { label: '覆盖集群', value: new Set(workspaces.value.map(item => item.cluster)).size, tone: 'context-card' },
])

function quotaSummary(quota) {
  const entries = Object.entries(quota || {}).filter(([, value]) => value)
  if (!entries.length) return ''
  return entries.slice(0, 2).map(([key, value]) => `${key}=${value}`).join('  ')
    + (entries.length > 2 ? ` +${entries.length - 2}` : '')
}

async function load() {
  loading.value = true
  try {
    const res = await getK8sWorkspaces()
    workspaces.value = res.results || res || []
  } catch {
    workspaces.value = []
  }
  loading.value = false
}

function openDialog(row) {
  if (!canManage.value) return
  if (row) {
    editingId.value = row.id
    form.value = {
      name: row.name,
      display_name: row.display_name,
      cluster: row.cluster,
      description: row.description,
      status: row.status,
      quota: { ...(row.quota || {}) },
    }
  } else {
    editingId.value = null
    form.value = emptyForm()
    // 默认选中当前上下文集群，减少一次选择
    form.value.cluster = k8sStore.selectedClusterId || clusters.value[0]?.id || null
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.name) return ElMessage.warning('请填写企业空间标识')
  if (!form.value.display_name) return ElMessage.warning('请填写企业空间名称')
  if (!form.value.cluster) return ElMessage.warning('请选择所属集群')

  saving.value = true
  try {
    if (editingId.value) {
      // 标识与集群不可变，不提交这两个字段
      const { name, cluster, ...payload } = form.value
      await updateK8sWorkspace(editingId.value, payload)
      ElMessage.success('企业空间已更新')
    } else {
      await createK8sWorkspace(form.value)
      ElMessage.success('企业空间已创建')
    }
    dialogVisible.value = false
    await load()
  } catch {
    // 错误详情已由请求拦截器统一提示
  }
  saving.value = false
}

async function remove(row) {
  try {
    await deleteK8sWorkspace(row.id)
    ElMessage.success('企业空间已删除')
    await load()
  } catch {
    // 错误详情已由请求拦截器统一提示
  }
}

onMounted(async () => {
  await Promise.all([load(), k8sStore.loadClusters()])
})
</script>

<style scoped>
.ws-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ws-name-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.4;
}

.ws-display {
  font-weight: 600;
  color: #0f172a;
}

.ws-slug {
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
</style>
