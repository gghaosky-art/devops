<template>
  <el-dialog v-model="visible" :title="`成员管理 - ${ownerName}`" width="90%" style="max-width:720px;" top="6vh" append-to-body destroy-on-close>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="成员关系只决定可见范围"
      description="加入成员后该用户能在列表中看到此对象；能否创建、修改、删除仍由全局角色权限决定。"
      style="margin-bottom:12px;"
    />

    <div v-if="canManage" class="member-add-bar">
      <el-select
        v-model="newUserId"
        filterable
        clearable
        placeholder="选择要加入的用户"
        style="width:260px"
        :loading="userLoading"
      >
        <el-option
          v-for="user in candidates"
          :key="user.id"
          :label="userLabel(user)"
          :value="user.id"
        />
      </el-select>
      <el-select v-model="newRole" style="width:140px">
        <el-option v-for="role in ROLES" :key="role.value" :label="role.label" :value="role.value" />
      </el-select>
      <el-button type="primary" :loading="saving" :disabled="!newUserId" @click="add">加入成员</el-button>
    </div>

    <el-table :data="members" stripe v-loading="loading" size="small" empty-text="暂无成员" style="width:100%">
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column prop="display_name" label="姓名" min-width="140" />
      <el-table-column prop="role" label="角色" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role === 'admin' ? 'warning' : row.role === 'viewer' ? 'info' : ''">
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="加入时间" min-width="180" show-overflow-tooltip />
      <el-table-column v-if="canManage" label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确定移除该成员？" @confirm="remove(row)">
            <template #reference><el-button link type="danger" size="small">移除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getUsers } from '@/api/modules/rbac'

const ROLES = [
  { value: 'admin', label: '空间管理员' },
  { value: 'regular', label: '普通成员' },
  { value: 'viewer', label: '只读成员' },
]

const props = defineProps({
  // 由父页面注入的三个接口，企业空间与项目共用这套交互
  fetchMembers: { type: Function, required: true },
  addMember: { type: Function, required: true },
  removeMember: { type: Function, required: true },
  canManage: { type: Boolean, default: false },
})

const emit = defineEmits(['changed'])

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const userLoading = ref(false)
const members = ref([])
const users = ref([])
const ownerId = ref(null)
const ownerName = ref('')
const newUserId = ref(null)
const newRole = ref('regular')

/** 已经是成员的用户不再出现在候选列表里。 */
const candidates = computed(() => {
  const joined = new Set(members.value.map(item => item.user))
  return users.value.filter(user => !joined.has(user.id))
})

function userLabel(user) {
  const name = (user.display_name || user.first_name || '').trim()
  return name ? `${user.username}（${name}）` : user.username
}

function roleLabel(value) {
  return ROLES.find(item => item.value === value)?.label || value
}

async function open(owner) {
  ownerId.value = owner.id
  ownerName.value = owner.display_name || owner.name || ''
  members.value = []
  newUserId.value = null
  newRole.value = 'regular'
  visible.value = true
  await Promise.all([load(), loadUsers()])
}

async function load() {
  loading.value = true
  try {
    members.value = await props.fetchMembers(ownerId.value)
  } catch {
    members.value = []
    ElMessage.error('加载成员失败')
  }
  loading.value = false
}

async function loadUsers() {
  if (!props.canManage || users.value.length) return
  userLoading.value = true
  try {
    const res = await getUsers()
    users.value = res.results || res || []
  } catch {
    users.value = []
  }
  userLoading.value = false
}

async function add() {
  saving.value = true
  try {
    await props.addMember(ownerId.value, { user: newUserId.value, role: newRole.value })
    ElMessage.success('成员已加入')
    newUserId.value = null
    await load()
    emit('changed')
  } catch {
    ElMessage.error('加入成员失败')
  }
  saving.value = false
}

async function remove(row) {
  try {
    await props.removeMember(ownerId.value, row.user)
    ElMessage.success('成员已移除')
    await load()
    emit('changed')
  } catch {
    ElMessage.error('移除成员失败')
  }
}

defineExpose({ open })
</script>

<style scoped>
.member-add-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
</style>
