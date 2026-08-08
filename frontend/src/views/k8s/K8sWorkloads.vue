<template>
  <K8sPageShell title="工作负载" desc="管理 Deployment、StatefulSet、DaemonSet、Job 与 CronJob。" icon="Cpu" :cards="summaryCards">
    <K8sResourcePanel
      v-model="keyword"
      title="工作负载列表"
      desc="将 Deployment、StatefulSet 等资源收拢到同一工作台卡片内浏览和操作。"
      @refresh="refresh"
      @cluster-change="onClusterChange"
      @namespace-change="onNamespaceChange"
      @project-change="onProjectChange"
    >
      <template #sub-tabs>
        <button
          v-for="st in SUB_TABS"
          :key="st"
          class="neo-sub-tab-btn"
          :class="{ active: subTab === st }"
          @click="subTab = st"
        >{{ st }}</button>
      </template>

      <el-table v-if="subTab === 'Deployment'" :data="filterRows(deployments, ['name', 'namespace', 'images'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas === row.replicas ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.ready_replicas === row.replicas ? '#10b981' : '#f59e0b', fontWeight: 600 }">{{ row.ready_replicas }}/{{ row.replicas }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="176" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManage" content="弹性伸缩" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);" @click="scaleDialog.open('deployment', row)"><el-icon :size="14"><RefreshRight /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 Pod" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="podsDialog.open('deployment', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('deployment', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('deployment', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'StatefulSet'" :data="filterRows(statefulsets, ['name', 'namespace', 'images'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas === row.replicas ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.ready_replicas === row.replicas ? '#10b981' : '#f59e0b', fontWeight: 600 }">{{ row.ready_replicas }}/{{ row.replicas }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="176" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManage" content="弹性伸缩" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);" @click="scaleDialog.open('statefulset', row)"><el-icon :size="14"><RefreshRight /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 Pod" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="podsDialog.open('statefulset', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('statefulset', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('statefulset', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'DaemonSet'" :data="filterRows(daemonsets, ['name', 'namespace', 'images', 'node_selector'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready === row.desired ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="就绪数" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.ready === row.desired ? '#10b981' : '#f59e0b', fontWeight: 600 }">{{ row.ready }}/{{ row.desired }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 Pod" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="podsDialog.open('daemonset', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('daemonset', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('daemonset', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'Job'" :data="filterRows(jobs, ['name', 'namespace', 'images', 'status'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status === 'Complete' ? 'running' : 'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="completions" label="完成数" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.status === 'Complete' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="images" label="镜像" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 Pod" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="podsDialog.open('job', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('job', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('job', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-if="subTab === 'CronJob'" :data="filterRows(cronjobs, ['name', 'namespace', 'images', 'schedule'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.suspend ? 'exited' : 'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="schedule" label="调度策略" width="140">
          <template #default="{ row }"><code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:3px">{{ row.schedule }}</code></template>
        </el-table-column>
        <el-table-column label="是否暂停" width="88">
          <template #default="{ row }"><el-tag :type="row.suspend ? 'danger' : 'success'" size="small">{{ row.suspend ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="last_schedule" label="最近调度" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 Pod" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="podsDialog.open('cronjob', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="yamlDialog.open('cronjob', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="eventsDialog.open('cronjob', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </K8sResourcePanel>

    <K8sYamlDialog ref="yamlDialog" />
    <K8sEventsDialog ref="eventsDialog" />
    <K8sLogDialog ref="logDialog" />
    <K8sScaleDialog ref="scaleDialog" @scaled="runFetch" />
    <K8sWorkloadPodsDialog
      ref="podsDialog"
      @show-logs="row => logDialog.open(row.name, row.namespace, row.containers)"
      @show-yaml="row => yamlDialog.open('pod', row.name, row.namespace)"
      @show-events="row => eventsDialog.open('pod', row.name, row.namespace)"
    />
  </K8sPageShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Bell, Document, Menu, RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'
import K8sPageShell from '@/components/k8s/K8sPageShell.vue'
import K8sResourcePanel from '@/components/k8s/K8sResourcePanel.vue'
import K8sYamlDialog from '@/components/k8s/K8sYamlDialog.vue'
import K8sEventsDialog from '@/components/k8s/K8sEventsDialog.vue'
import K8sLogDialog from '@/components/k8s/K8sLogDialog.vue'
import K8sScaleDialog from '@/components/k8s/K8sScaleDialog.vue'
import K8sWorkloadPodsDialog from '@/components/k8s/K8sWorkloadPodsDialog.vue'
import { useK8sResourcePage } from '@/composables/useK8sResourcePage'
import {
  getK8sCronJobs, getK8sDaemonSets, getK8sDeployments, getK8sJobs, getK8sStatefulSets,
} from '@/api/modules/container'

const SUB_TABS = ['Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob']

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.k8s.manage'))

const deployments = ref([])
const statefulsets = ref([])
const daemonsets = ref([])
const jobs = ref([])
const cronjobs = ref([])

const yamlDialog = ref(null)
const eventsDialog = ref(null)
const logDialog = ref(null)
const scaleDialog = ref(null)
const podsDialog = ref(null)

const subTab = useRouteTabState({
  tabs: () => SUB_TABS,
  defaultTab: 'Deployment',
  queryKey: 'workloadSub',
}).activeTab

const LOADERS = {
  Deployment: (id, ns, project) => getK8sDeployments(id, ns, project).then(res => { deployments.value = res }),
  StatefulSet: (id, ns, project) => getK8sStatefulSets(id, ns, project).then(res => { statefulsets.value = res }),
  DaemonSet: (id, ns, project) => getK8sDaemonSets(id, ns, project).then(res => { daemonsets.value = res }),
  Job: (id, ns, project) => getK8sJobs(id, ns, project).then(res => { jobs.value = res }),
  CronJob: (id, ns, project) => getK8sCronJobs(id, ns, project).then(res => { cronjobs.value = res }),
}

const { loading, keyword, summaryCards, filterRows, refresh, runFetch, onClusterChange, onNamespaceChange, onProjectChange } = useK8sResourcePage({
  needsNamespace: true,
  reloadKey: () => subTab.value,
  fetch: async ({ clusterId, namespace, projectId }) => {
    await LOADERS[subTab.value]?.(clusterId, namespace, projectId)
  },
  summaryPatch: () => ({
    workloads_total: deployments.value.length + statefulsets.value.length + daemonsets.value.length + jobs.value.length + cronjobs.value.length,
  }),
})
</script>
