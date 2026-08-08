<template>
  <K8sPageShell title="网络管理" desc="查看 Service 与 Ingress 的暴露方式和路由配置。" icon="Connection" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="网络资源列表"
      desc="统一查看 Service 与 Ingress，保持与任务工作台一致的承载层级。"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <template #sub-tabs>
        <button v-for="st in SUB_TABS" :key="st" class="neo-sub-tab-btn" :class="{ active: subTab === st }" @click="subTab = st">{{ st }}</button>
      </template>

      <el-table v-if="subTab === 'Service'" :data="filterRows(services, ['name', 'namespace', 'type', 'cluster_ip', 'ports'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse running"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'LoadBalancer' ? 'warning' : row.type === 'NodePort' ? 'success' : 'info'">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cluster_ip" label="Cluster IP" width="140" />
        <el-table-column prop="ports" label="端口" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('service', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('service', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'Ingress'" :data="filterRows(ingresses, ['name', 'namespace', 'class', 'hosts', 'address'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse running"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="class" label="Ingress Class" width="120" />
        <el-table-column prop="hosts" label="域名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="address" label="地址" width="140" />
        <el-table-column prop="ports" label="端口" width="100" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('ingress', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('ingress', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
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
import { getK8sIngresses, getK8sServices } from '@/api/modules/container'

const SUB_TABS = ['Service', 'Ingress']

const services = ref([])
const ingresses = ref([])
const yamlDialog = ref(null)
const eventsDialog = ref(null)

const subTab = useRouteTabState({
  tabs: () => SUB_TABS,
  defaultTab: 'Service',
  queryKey: 'networkSub',
}).activeTab

const { loading, keyword, summaryCards, filterRows, refresh, onClusterChange, onNamespaceChange, onProjectChange } = useK8sResourcePage({
  needsNamespace: true,
  reloadKey: () => subTab.value,
  fetch: async ({ clusterId, namespace, projectId }) => {
    if (subTab.value === 'Service') services.value = await getK8sServices(clusterId, namespace, projectId)
    else ingresses.value = await getK8sIngresses(clusterId, namespace, projectId)
  },
})
</script>
