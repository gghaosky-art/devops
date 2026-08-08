<template>
  <K8sPageShell title="存储管理" desc="查看 PV、PVC 与存储类的容量、绑定与回收策略。" icon="Coin" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="存储资源列表"
      desc="聚合 PV、PVC 与存储类资源，用一张卡片承接筛选与列表。"
      :show-namespace="subTab === 'PVC'"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <template #sub-tabs>
        <button v-for="st in SUB_TABS" :key="st" class="neo-sub-tab-btn" :class="{ active: subTab === st }" @click="subTab = st">{{ st }}</button>
      </template>
      <template #toolbar-right>
        <el-tag v-if="summary.pvcs_pending" size="large" type="warning">PVC Pending {{ summary.pvcs_pending }}</el-tag>
      </template>

      <el-table v-if="subTab === 'PV'" :data="filterRows(pvs, ['name', 'capacity', 'access_modes', 'status', 'claim', 'storage_class'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Bound' || row.status === 'Available' ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'Bound' ? 'success' : row.status === 'Available' ? 'info' : 'warning'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="claim" label="绑定声明" min-width="250" show-overflow-tooltip />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('pv', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'PVC'" :data="filterRows(pvcs, ['name', 'namespace', 'status', 'capacity', 'storage_class', 'volume'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="240">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Bound' ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.status === 'Bound' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column prop="volume" label="PV" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('pvc', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('pvc', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'StorageClass'" :data="filterRows(storageclasses, ['name', 'provisioner', 'reclaim_policy', 'binding_mode'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse running"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
              <el-tag v-if="row.is_default" type="primary" size="small" style="margin-left:6px">默认</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="provisioner" label="Provisioner" min-width="220" show-overflow-tooltip />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="binding_mode" label="绑定模式" width="180" />
        <el-table-column label="允许扩展" width="90">
          <template #default="{ row }"><el-tag :type="row.allow_expansion ? 'success' : 'info'" size="small">{{ row.allow_expansion ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('storageclass', row.name)"><el-icon :size="14"><Document /></el-icon></button>
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
import { useRouteTabState } from '@/composables/useRouteTabState'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import K8sEventsDialog from '@/components/k8s/K8sEventsDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'
import { getK8sPVCs, getK8sPVs, getK8sStorageClasses } from '@/api/modules/container'

const SUB_TABS = ['PV', 'PVC', 'StorageClass']

const pvs = ref([])
const pvcs = ref([])
const storageclasses = ref([])
const yamlDialog = ref(null)
const eventsDialog = ref(null)

const subTab = useRouteTabState({
  tabs: () => SUB_TABS,
  defaultTab: 'PV',
  queryKey: 'storageSub',
}).activeTab

// 只有 PVC 是命名空间级资源，PV 与 StorageClass 是集群级的。
const { loading, keyword, summary, summaryCards, filterRows, refresh, onClusterChange, onNamespaceChange, onProjectChange } = useK8sResourcePage({
  needsNamespace: () => subTab.value === 'PVC',
  reloadKey: () => subTab.value,
  fetch: async ({ clusterId, namespace, projectId }) => {
    if (subTab.value === 'PV') pvs.value = await getK8sPVs(clusterId)
    else if (subTab.value === 'PVC') pvcs.value = await getK8sPVCs(clusterId, namespace, projectId)
    else storageclasses.value = await getK8sStorageClasses(clusterId)
  },
})
</script>
