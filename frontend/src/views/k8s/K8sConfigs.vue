<template>
  <K8sPageShell title="配置管理" desc="编辑 ConfigMap 与 Secret，并保留版本快照与回滚能力。" icon="Setting" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="配置资源列表"
      desc="统一承接 ConfigMap 与 Secret 的检索、编辑和 YAML 查看。"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <template #sub-tabs>
        <button v-for="st in SUB_TABS" :key="st" class="neo-sub-tab-btn" :class="{ active: subTab === st }" @click="subTab = st">{{ st }}</button>
      </template>

      <el-table v-if="subTab === 'ConfigMap'" :data="filterRows(configmaps, ['name', 'namespace', 'data_count', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse running"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManage" content="编辑配置" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="editorDialog.open('configmap', row)"><el-icon :size="14"><Setting /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('configmap', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'Secret'" :data="filterRows(secrets, ['name', 'namespace', 'type', 'data_count', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse running"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" min-width="240">
          <template #default="{ row }"><code style="font-size:11px;background:#f1f5f9;padding:2px 6px;border-radius:3px">{{ row.type }}</code></template>
        </el-table-column>
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManage" content="编辑配置" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="editorDialog.open('secret', row)"><el-icon :size="14"><Setting /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('secret', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </K8sResourcePanel>

    <K8sYamlDialog ref="yamlDialog" />
    <K8sConfigEditorDialog ref="editorDialog" @saved="runFetch" />
  </K8sPageShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Document, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import K8sConfigEditorDialog from '@/components/k8s/K8sConfigEditorDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'
import { getK8sConfigMaps, getK8sSecrets } from '@/api/modules/container'

const SUB_TABS = ['ConfigMap', 'Secret']

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))

const configmaps = ref([])
const secrets = ref([])
const yamlDialog = ref(null)
const editorDialog = ref(null)

const subTab = useRouteTabState({
  tabs: () => SUB_TABS,
  defaultTab: 'ConfigMap',
  queryKey: 'configSub',
}).activeTab

const { loading, keyword, summaryCards, filterRows, refresh, runFetch, onClusterChange, onNamespaceChange, onProjectChange } = useK8sResourcePage({
  needsNamespace: true,
  reloadKey: () => subTab.value,
  fetch: async ({ clusterId, namespace, projectId }) => {
    if (subTab.value === 'ConfigMap') configmaps.value = await getK8sConfigMaps(clusterId, namespace, projectId)
    else secrets.value = await getK8sSecrets(clusterId, namespace, projectId)
  },
})
</script>
