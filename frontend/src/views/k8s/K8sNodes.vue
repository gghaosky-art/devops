<template>
  <K8sPageShell title="节点管理" desc="查看集群节点状态、版本与基础资源。" icon="Monitor" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="节点列表"
      desc="延续任务工作台的列表密度，集中查看节点状态、版本与基础资源。"
      :show-namespace="false"
      search-placeholder="搜索节点名称、IP、角色或系统"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @project-change="onProjectChange"
    >
      <el-table :data="filterRows(nodes, ['name', 'internal_ip', 'roles', 'version', 'os_image'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="节点名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Ready' ? 'running' : 'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'Ready' ? 'success' : 'danger'" size="small">{{ row.status === 'Ready' ? '就绪' : '未就绪' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="roles" label="角色" width="120">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.roles }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="version" label="Kubelet 版本" width="120" />
        <el-table-column prop="internal_ip" label="内部 IP" width="140" />
        <el-table-column label="CPU/内存" width="150">
          <template #default="{ row }">
            <div style="font-size:12px">CPU: <b>{{ row.cpu }}</b></div>
            <div style="font-size:12px">Memory: <b>{{ row.memory }}</b></div>
          </template>
        </el-table-column>
        <el-table-column prop="os_image" label="系统" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('node', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('node', row.name)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </K8sResourcePanel>

    <K8sYamlDialog ref="yamlDialog" />
    <K8sEventsDialog ref="eventsDialog" />
  </K8sPageShell>
</template>

<script setup>
import { ref } from 'vue'
import { Bell, Document } from '@element-plus/icons-vue'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import K8sEventsDialog from '@/components/k8s/K8sEventsDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'
import { getK8sNodes } from '@/api/modules/container'

const nodes = ref([])
const yamlDialog = ref(null)
const eventsDialog = ref(null)

const { loading, keyword, summaryCards, filterRows, refresh, onClusterChange, onProjectChange } = useK8sResourcePage({
  needsNamespace: false,
  fetch: async ({ clusterId }) => {
    nodes.value = await getK8sNodes(clusterId)
  },
  summaryPatch: () => ({
    nodes_total: nodes.value.length,
    nodes_ready: nodes.value.filter(item => item.status === 'Ready').length,
  }),
})
</script>
