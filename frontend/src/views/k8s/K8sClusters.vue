<template>
  <K8sPageShell title="集群管理" desc="统一接入并维护 Kubernetes 集群连接。" icon="OfficeBuilding" :cards="cards">
    <div class="workbench-card k8s-cluster-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">集群列表</span>
          <span class="toolbar-desc">统一管理已接入的 K8s 集群。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn" @click="refresh">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button v-if="canManage" class="filter-refresh-btn" @click="openDialog()">
            <el-icon><Plus /></el-icon>
            新增集群
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history k8s-cluster-toolbar">
        <div class="workbench-toolbar-left">
          <el-input v-model="keyword" clearable placeholder="搜索集群名称 / API Server / 描述" style="width: 320px" />
        </div>
        <div class="workbench-toolbar-right">
          <el-tag size="large" type="info">集群总数 {{ clusters.length }}</el-tag>
          <el-tag size="large" type="success">运行中 {{ connectedCount }}</el-tag>
        </div>
      </div>

      <el-table
        :data="filterRows(clusters, ['name', 'api_server', 'status', 'description'])"
        stripe
        v-loading="loading"
        style="width:100%"
        class="k8s-cluster-table"
      >
        <el-table-column prop="name" label="集群名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'connected' ? 'running' : 'exited'"></span>
              <span style="font-weight:600">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="api_server" label="API Server" min-width="260" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'connected' ? 'success' : 'danger'" size="small">
              {{ row.status === 'connected' ? '运行中' : '未连接' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column v-if="canManage" label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="testConnection(row)">测试连接</el-button>
            <el-button link type="info" size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该集群？" @confirm="remove(row)">
              <template #reference><el-button link type="danger" size="small">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑集群' : '新增 K8s 集群'"
      width="90%"
      style="max-width:600px;"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="集群名称"><el-input v-model="form.name" placeholder="例如 prod-cluster" /></el-form-item>
        <el-form-item label="API Server">
          <el-input v-model="form.api_server" placeholder="例如 https://k8s.example.com:6443，留空则沿用 kubeconfig 中的地址" />
          <div class="form-hint">留空表示使用 kubeconfig 里的 server；填写时需要带 http:// 或 https:// 前缀。</div>
          <el-alert
            v-if="httpApiServer"
            type="warning"
            :closable="false"
            show-icon
            title="使用明文 HTTP"
            style="margin-top:6px;"
          >
            <template #default>
              客户端证书只在 TLS 握手时发送，明文连接下不会携带，服务端可能识别为
              <code>system:anonymous</code> 并返回 403。
              kube-apiserver 通常是 <code>https://&lt;节点IP&gt;:6443</code>，注意不要填 KubeSphere 控制台或 ks-apiserver 的地址。
            </template>
          </el-alert>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" placeholder="集群用途描述" /></el-form-item>
        <el-form-item label="KubeConfig">
          <el-input v-model="form.kubeconfig" type="textarea" :rows="12" placeholder="粘贴 kubeconfig YAML 内容" style="font-family:monospace;font-size:12px;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
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
import { createK8sCluster, deleteK8sCluster, testK8sConnection, updateK8sCluster } from '@/api/modules/container'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))

const k8sStore = useK8sStore()
const { clusters } = storeToRefs(k8sStore)

const loading = ref(false)
const keyword = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = ref({ name: '', api_server: '', description: '', kubeconfig: '' })

const httpApiServer = computed(() => String(form.value.api_server || '').trim().toLowerCase().startsWith('http://'))

const connectedCount = computed(() => clusters.value.filter(item => item.status === 'connected').length)

const cards = computed(() => [
  { label: '集群数', value: clusters.value.length, tone: '' },
  { label: '已连接', value: connectedCount.value, tone: 'success-card' },
  { label: '离线集群', value: Math.max(clusters.value.length - connectedCount.value, 0), tone: 'warning-card' },
  { label: '当前集群', value: k8sStore.selectedCluster?.name || '未选择', tone: 'context-card' },
])

function filterRows(rows, fields) {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return rows
  return rows.filter(row => fields.some(field => String(row?.[field] || '').toLowerCase().includes(text)))
}

async function load(force = true) {
  loading.value = true
  try {
    await k8sStore.loadClusters({ force })
    if (!clusters.value.some(item => item.id === k8sStore.selectedClusterId)) {
      const connected = clusters.value.find(item => item.status === 'connected')
      k8sStore.setCluster(connected?.id || clusters.value[0]?.id || null)
    }
  } catch {
    /* 列表为空时由表格空态呈现 */
  }
  loading.value = false
}

function refresh() {
  load(true)
}

/** 后端对 http 地址等风险只提示不阻断，这里长驻展示，避免被一闪而过的成功提示盖过。 */
function notifyWarnings(warnings) {
  for (const text of warnings || []) {
    ElMessage({ type: 'warning', message: text, duration: 0, showClose: true })
  }
}

function openDialog(cluster) {
  if (!canManage.value) return
  if (cluster) {
    editingId.value = cluster.id
    // kubeconfig 不回显，留空表示沿用原有内容
    form.value = { name: cluster.name, api_server: cluster.api_server, description: cluster.description, kubeconfig: '' }
  } else {
    editingId.value = null
    form.value = { name: '', api_server: '', description: '', kubeconfig: '' }
  }
  dialogVisible.value = true
}

async function save() {
  if (!canManage.value) return
  if (!form.value.name) return ElMessage.warning('请填写集群名称')
  if (!form.value.kubeconfig && !editingId.value) return ElMessage.warning('请粘贴 KubeConfig')
  saving.value = true
  try {
    const data = { ...form.value }
    if (!data.kubeconfig) delete data.kubeconfig
    const res = editingId.value
      ? await updateK8sCluster(editingId.value, data)
      : await createK8sCluster(data)
    ElMessage.success(editingId.value ? '集群已更新' : '集群已添加')
    notifyWarnings(res?.warnings)
    dialogVisible.value = false
    await load(true)
  } catch {
    /* 请求层已提示 */
  }
  saving.value = false
}

async function testConnection(row) {
  if (!canManage.value) return
  try {
    const res = await testK8sConnection(row.id)
    if (res.success) ElMessage.success(res.message)
    else ElMessage.error(res.message)
    k8sStore.invalidateSummary(row.id)
    await load(true)
  } catch {
    ElMessage.error('连接测试失败')
  }
}

async function remove(row) {
  if (!canManage.value) return
  try {
    await deleteK8sCluster(row.id)
    ElMessage.success('集群已删除')
    k8sStore.invalidateSummary(row.id)
    k8sStore.invalidateNamespaces(row.id)
    await load(true)
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(() => load(false))
</script>

<style scoped>
.form-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}
</style>
