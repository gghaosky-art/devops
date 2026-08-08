<template>
  <!-- 集群列表回来之前不下结论，否则会先闪一下「未连接」再跳到正常列表。 -->
  <div v-if="!clustersLoaded" v-loading="true" class="workbench-card" style="min-height:220px;"></div>

  <div v-else-if="!selectedClusterId" class="empty-state">
    <div class="empty-icon">⚙</div>
    <div class="empty-text">还没有可用集群，请先在集群管理中接入。</div>
    <div style="display:flex;gap:8px;margin-top:8px;">
      <el-button type="primary" @click="goToClusters">前往集群管理</el-button>
      <el-button @click="emit('refresh')">重新加载</el-button>
    </div>
  </div>

  <div v-else-if="!selectedClusterConnected" class="empty-state">
    <div class="empty-icon">⚙</div>
    <div class="empty-text">当前集群未连接，请先测试连接或切换到已连接集群。</div>
    <div style="display:flex;gap:8px;margin-top:8px;">
      <el-button type="primary" @click="goToClusters">前往集群管理</el-button>
      <el-button @click="emit('refresh')">重新加载</el-button>
    </div>
  </div>

  <div v-else-if="requiresProject && !k8sStore.selectedProjectId" class="empty-state">
    <div class="empty-icon">🔒</div>
    <div class="empty-text">你在当前集群下还没有可访问的项目。</div>
    <div style="margin-top:6px;font-size:12px;color:#94a3b8;line-height:1.6;">
      这些资源按项目隔离，需要由管理员把你加入某个企业空间或项目后才能查看。
    </div>
  </div>

  <div v-else class="workbench-card k8s-resource-card">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">{{ title }}</span>
        <span class="toolbar-desc">{{ desc }}</span>
      </div>
      <div class="workbench-card-actions">
        <el-button @click="emit('refresh')"><el-icon><RefreshRight /></el-icon>刷新</el-button>
      </div>
    </div>

    <div v-if="$slots['sub-tabs']" class="neo-sub-tabs theme-blue k8s-resource-sub-tabs">
      <slot name="sub-tabs" />
    </div>

    <K8sScopeBar
      :show-namespace="showNamespace"
      @cluster-change="emit('cluster-change', $event)"
      @namespace-change="emit('namespace-change', $event)"
      @project-change="emit('project-change', $event)"
    >
      <template #left>
        <el-input
          :model-value="modelValue"
          clearable
          :placeholder="searchPlaceholder"
          style="width: 320px"
          @update:model-value="emit('update:modelValue', $event)"
        />
      </template>
      <template #right>
        <slot name="toolbar-right" />
      </template>
    </K8sScopeBar>

    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useK8sStore } from '@/stores/k8s'
import { K8S_TAB_PATHS } from '@/router/k8sTabs'
import K8sScopeBar from '@/components/k8s/K8sScopeBar.vue'

defineProps({
  title: { type: String, required: true },
  desc: { type: String, default: '' },
  showNamespace: { type: Boolean, default: true },
  modelValue: { type: String, default: '' },
  searchPlaceholder: { type: String, default: '搜索当前列表名称、镜像、IP 或描述' },
})

const emit = defineEmits(['refresh', 'cluster-change', 'namespace-change', 'project-change', 'update:modelValue'])

const router = useRouter()
const k8sStore = useK8sStore()
const authStore = useAuthStore()
// 没有 ops.k8s.manage 就拿不到裸集群视角，必须落在某个项目里
const requiresProject = computed(() => !authStore.hasPermission('ops.k8s.manage'))

const selectedClusterId = computed(() => k8sStore.selectedClusterId)
const selectedClusterConnected = computed(() => k8sStore.selectedClusterConnected)
const clustersLoaded = computed(() => k8sStore.clustersLoaded)

function goToClusters() {
  router.push(K8S_TAB_PATHS.clusters)
}
</script>
