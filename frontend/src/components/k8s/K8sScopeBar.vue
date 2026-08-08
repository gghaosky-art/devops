<template>
  <div class="workbench-toolbar workbench-toolbar--history filter-bar--context">
    <div class="workbench-toolbar-left">
      <slot name="left" />
    </div>
    <div class="workbench-toolbar-right k8s-context-toolbar-right">
      <div class="filter-inline-group filter-inline-group--nowrap">
        <div class="filter-inline-context">
          <span class="filter-inline-label">当前集群</span>
          <el-select
            :model-value="k8sStore.selectedClusterId"
            placeholder="选择集群"
            class="industrial-select toolbar-filter-select filter-inline-select"
            popper-class="k8s-context-popper k8s-context-popper--cluster"
            @change="onClusterChange"
          >
            <el-option v-for="c in k8sStore.clusters" :key="c.id" :label="c.name" :value="c.id">
              <div class="context-option-row">
                <div class="context-option-main">
                  <div class="context-option-head">
                    <div class="context-option-main context-option-main--cluster">
                      <span class="state-pulse" :class="c.status === 'connected' ? 'running' : 'exited'"></span>
                      <span class="context-option-title">{{ c.name }}</span>
                    </div>
                    <span
                      class="context-status-pill"
                      :class="c.status === 'connected' ? 'context-status-pill--success' : 'context-status-pill--info'"
                    >
                      {{ c.status === 'connected' ? '在线' : '离线' }}
                    </span>
                  </div>
                  <span class="context-option-subtitle">{{ clusterOptionMeta(c) }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>

        <div v-if="k8sStore.clusterProjects.length || !canViewCluster" class="filter-inline-context">
          <span class="filter-inline-label">当前项目</span>
          <el-select
            :model-value="k8sStore.selectedProjectId"
            :clearable="canViewCluster"
            placeholder="选择项目"
            class="industrial-select toolbar-filter-select filter-inline-select"
            popper-class="k8s-context-popper k8s-context-popper--cluster"
            @change="onProjectChange"
          >
            <template #empty>
              <div class="context-dropdown-empty">当前集群下没有你可访问的项目</div>
            </template>
            <el-option
              v-for="project in k8sStore.clusterProjects"
              :key="project.id"
              :label="project.display_name"
              :value="project.id"
            >
              <div class="context-option-row">
                <div class="context-option-main">
                  <div class="context-option-head">
                    <span class="context-option-title">{{ project.display_name }}</span>
                    <span class="context-status-pill context-status-pill--info">{{ project.workspace_name }}</span>
                  </div>
                  <span class="context-option-subtitle">{{ project.namespace }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>

        <div v-if="showNamespace" class="filter-inline-context">
          <span class="filter-inline-label">当前命名空间</span>
          <el-select
            :model-value="k8sStore.selectedNamespace"
            :disabled="Boolean(k8sStore.selectedProject)"
            :placeholder="k8sStore.selectedProject ? k8sStore.selectedProject.namespace : '选择命名空间'"
            class="industrial-select toolbar-filter-select filter-inline-select filter-inline-select--namespace"
            popper-class="k8s-context-popper k8s-context-popper--namespace"
            :popper-style="NAMESPACE_POPPER_STYLE"
            @change="onNamespaceChange"
          >
            <template #empty>
              <div class="context-dropdown-empty">当前集群未返回命名空间</div>
            </template>
            <el-option label="全部命名空间" :value="ALL_NAMESPACES">
              <div class="context-option-row context-option-row--all">
                <div class="context-option-main">
                  <div class="context-option-head">
                    <span class="context-option-title">全部命名空间</span>
                    <span class="context-status-pill context-status-pill--info">ALL</span>
                  </div>
                  <span class="context-option-subtitle">跨命名空间聚合视图</span>
                </div>
              </div>
            </el-option>
            <el-option
              v-for="ns in k8sStore.namespaceOptions"
              :key="ns.name"
              :label="ns.name"
              :value="ns.name"
            >
              <div class="context-option-row">
                <div class="context-option-main">
                  <div class="context-option-head">
                    <span class="context-option-title">{{ ns.name }}</span>
                    <span class="context-status-pill" :class="namespaceStatusTagClass(ns.status)">
                      {{ namespaceStatusText(ns.status) }}
                    </span>
                  </div>
                  <span class="context-option-subtitle">{{ namespaceOptionMeta(ns) }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>
      </div>
      <slot name="right" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ALL_NAMESPACES, useK8sStore } from '@/stores/k8s'
import { useAuthStore } from '@/stores/auth'

defineProps({
  showNamespace: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['cluster-change', 'namespace-change', 'project-change'])

const k8sStore = useK8sStore()
const authStore = useAuthStore()
// 没有 ops.k8s.manage 的用户拿不到裸集群视角，必须锁定在某个项目里
const canViewCluster = computed(() => authStore.hasPermission('ops.k8s.manage'))

const NAMESPACE_POPPER_STYLE = {
  width: '220px',
  minWidth: '220px',
  maxWidth: '220px',
}

function onClusterChange(clusterId) {
  k8sStore.setCluster(clusterId)
  emit('cluster-change', clusterId)
}

function onProjectChange(projectId) {
  k8sStore.setProject(projectId)
  emit('project-change', projectId)
}

function onNamespaceChange(namespace) {
  k8sStore.setNamespace(namespace)
  emit('namespace-change', namespace)
}

function namespaceStatusText(status) {
  const value = String(status || '').trim()
  if (!value) return '可用'
  if (value === 'Active') return '活跃'
  if (value === 'Terminating') return '终止中'
  return value
}

function namespaceStatusTagClass(status) {
  const value = String(status || '').trim()
  if (!value || value === 'Active') return 'context-status-pill--success'
  if (value === 'Terminating') return 'context-status-pill--warning'
  return 'context-status-pill--info'
}

function namespaceOptionMeta(namespace) {
  const created = String(namespace?.created || '').trim()
  const meta = []
  if (created) meta.push(`创建于 ${created.replace('T', ' ').slice(0, 16)}`)
  if (namespace?.labelCount) meta.push(`${namespace.labelCount} 个标签`)
  return meta.length ? meta.join(' · ') : '命名空间资源视图'
}

function clusterOptionMeta(cluster) {
  const endpoint = String(cluster?.api_server || '').trim()
  const description = String(cluster?.description || '').trim()
  const meta = []
  if (endpoint) {
    try {
      meta.push(new URL(endpoint).host || endpoint)
    } catch {
      meta.push(endpoint)
    }
  }
  if (description) meta.push(description)
  return meta.join(' · ') || 'Kubernetes 集群连接'
}
</script>
