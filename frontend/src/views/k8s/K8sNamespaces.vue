<template>
  <K8sPageShell title="命名空间" desc="查看集群命名空间状态与元数据。" icon="FolderOpened" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="命名空间列表"
      desc="统一承接命名空间状态和元数据视图，保持工作台式筛选与浏览节奏。"
      search-placeholder="搜索命名空间名称或状态"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <el-table :data="filterRows(namespaceOptions, ['name', 'status', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="命名空间名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Active' ? 'running' : 'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'Active' ? 'success' : 'danger'" size="small">{{ row.status === 'Active' ? '活跃' : '终止' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('namespace', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </K8sResourcePanel>

    <K8sYamlDialog ref="yamlDialog" />
  </K8sPageShell>
</template>

<script setup>
import { ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'

const yamlDialog = ref(null)

// 命名空间列表就是 store 里已加载的那一份，无需额外请求。
const {
  loading, keyword, summaryCards, namespaceOptions,
  filterRows, refresh, onClusterChange, onNamespaceChange, onProjectChange,
} = useK8sResourcePage({
  needsNamespace: true,
  fetch: async () => {},
})
</script>
