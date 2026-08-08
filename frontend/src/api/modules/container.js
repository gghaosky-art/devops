import request from '@/api/request'

// ====== Docker 环境主机 ======
export const getDockerHosts = () => request.get('/docker/hosts/')
export const createDockerHost = (data) => request.post('/docker/hosts/', data)
export const updateDockerHost = (id, data) => request.put(`/docker/hosts/${id}/`, data)
export const deleteDockerHost = (id) => request.delete(`/docker/hosts/${id}/`)
export const testDockerConnection = (id) => request.post(`/docker/hosts/${id}/test_connection/`)

// ====== Docker 容器 ======
export const getDockerContainers = (hostId) => request.get('/docker/containers/', { params: { host_id: hostId } })
export const getDockerImages = (hostId) => request.get('/docker/images/', { params: { host_id: hostId } })
export const dockerContainerAction = (containerId, hostId, action) =>
  request.post(`/docker/containers/${containerId}/action/`, { host_id: hostId, action })
export const dockerContainerRemove = (containerId, hostId) =>
  request.delete(`/docker/containers/${containerId}/remove/`, { params: { host_id: hostId } })
export const getDockerContainerLogs = (containerId, hostId, tail = 200) =>
  request.get(`/docker/containers/${containerId}/logs/`, { params: { host_id: hostId, tail } })
export const getDockerContainerInspect = (containerId, hostId) =>
  request.get(`/docker/containers/${containerId}/inspect/`, { params: { host_id: hostId } })
export const dockerRemoveImages = (hostId, imageIds) =>
  request.delete('/docker/images/remove/', { data: { host_id: hostId, image_ids: imageIds } })
export const dockerPruneDanglingImages = (hostId) =>
  request.post('/docker/images/prune/', { host_id: hostId })

// 命名空间级接口统一带上租户范围：选中项目时后端按项目解析命名空间，
// 未选项目则退回集群视角（需要 ops.k8s.manage）。
const nsParams = (namespace, project, extra = {}) => ({
  namespace,
  ...(project ? { project } : {}),
  ...extra,
})

// ====== K8s 集群 ======
export const getK8sClusters = () => request.get('/k8s/clusters/')
export const createK8sCluster = (data) => request.post('/k8s/clusters/', data)
export const updateK8sCluster = (id, data) => request.put(`/k8s/clusters/${id}/`, data)
export const deleteK8sCluster = (id) => request.delete(`/k8s/clusters/${id}/`)
export const testK8sConnection = (id) => request.post(`/k8s/clusters/${id}/test_connection/`)
export const getK8sSummary = (id) => request.get(`/k8s/clusters/${id}/summary/`)
export const getK8sNamespaces = (id, project) => request.get(`/k8s/clusters/${id}/namespaces/`, { params: project ? { project } : {} })
export const getK8sPods = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/pods/`, { params: nsParams(ns, project) })
export const getK8sServices = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/services/`, { params: nsParams(ns, project) })
export const getK8sDeployments = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/deployments/`, { params: nsParams(ns, project) })
export const restartK8sPod = (clusterId, podName, ns, project) => request.post(`/k8s/clusters/${clusterId}/pods/${podName}/restart/`, nsParams(ns, project))

// ====== K8s 扩展资源 ======
export const getK8sNodes = (id) => request.get(`/k8s/clusters/${id}/nodes/`)
export const getK8sStatefulSets = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/statefulsets/`, { params: nsParams(ns, project) })
export const getK8sDaemonSets = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/daemonsets/`, { params: nsParams(ns, project) })
export const getK8sJobs = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/jobs/`, { params: nsParams(ns, project) })
export const getK8sCronJobs = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/cronjobs/`, { params: nsParams(ns, project) })
export const getK8sIngresses = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/ingresses/`, { params: nsParams(ns, project) })
export const getK8sPVs = (id) => request.get(`/k8s/clusters/${id}/pvs/`)
export const getK8sPVCs = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/pvcs/`, { params: nsParams(ns, project) })
export const getK8sStorageClasses = (id) => request.get(`/k8s/clusters/${id}/storageclasses/`)
export const getK8sConfigMaps = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/configmaps/`, { params: nsParams(ns, project) })
export const getK8sSecrets = (id, ns = 'default', project) => request.get(`/k8s/clusters/${id}/secrets/`, { params: nsParams(ns, project) })
export const getK8sResourceYaml = (id, type, name, ns = 'default', project) => request.get(`/k8s/clusters/${id}/resource_yaml/`, { params: nsParams(ns, project, { type, name }) })
export const getK8sWorkloadPods = (id, workloadType, name, ns = 'default', project) => request.get(`/k8s/clusters/${id}/workload_pods/`, { params: nsParams(ns, project, { workload_type: workloadType, name }) })
export const getK8sPodLogs = (id, podName, ns = 'default', container = '', tailLines = 200, project) => request.get(`/k8s/clusters/${id}/pod_logs/`, { params: nsParams(ns, project, { pod_name: podName, container, tail_lines: tailLines }) })
export const getK8sResourceEvents = (id, type, name, ns = 'default', project) => request.get(`/k8s/clusters/${id}/resource_events/`, { params: nsParams(ns, project, { type, name }) })
export const execK8sPod = (id, payload) => request.post(`/k8s/clusters/${id}/pod_exec/`, payload)
export const scaleK8sWorkload = (id, payload) => request.post(`/k8s/clusters/${id}/scale_workload/`, payload)
export const getK8sConfigResourceDetail = (id, type, name, ns = 'default', project) =>
  request.get(`/k8s/clusters/${id}/config_resource_detail/`, { params: nsParams(ns, project, { type, name }) })
export const previewK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_preview/`, payload)
export const updateK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_update/`, payload)
export const getK8sConfigRevisions = (id, type, name, ns = 'default') =>
  request.get(`/k8s/clusters/${id}/config_resource_revisions/`, { params: { type, name, namespace: ns } })
export const getK8sConfigRevisionPreview = (id, type, name, ns = 'default', revisionId) =>
  request.get(`/k8s/clusters/${id}/config_resource_revision_preview/`, { params: { type, name, namespace: ns, revision_id: revisionId } })
export const getK8sConfigRollbackPreview = (id, type, name, ns = 'default') =>
  request.get(`/k8s/clusters/${id}/config_resource_rollback_preview/`, { params: { type, name, namespace: ns } })
export const rollbackK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_rollback/`, payload)
export const rollbackK8sConfigResourceToRevision = (id, payload) =>
  request.post(`/k8s/clusters/${id}/config_resource_rollback_to_revision/`, payload)

// ====== K8s 企业空间 ======
export const getK8sWorkspaces = (params) => request.get('/k8s/workspaces/', { params })
export const createK8sWorkspace = (data) => request.post('/k8s/workspaces/', data)
export const updateK8sWorkspace = (id, data) => request.patch(`/k8s/workspaces/${id}/`, data)
export const deleteK8sWorkspace = (id) => request.delete(`/k8s/workspaces/${id}/`)
export const getK8sWorkspaceMembers = (id) => request.get(`/k8s/workspaces/${id}/members/`)
export const addK8sWorkspaceMember = (id, data) => request.post(`/k8s/workspaces/${id}/members/`, data)
export const removeK8sWorkspaceMember = (id, userId) => request.delete(`/k8s/workspaces/${id}/members/${userId}/`)

// ====== K8s 项目 ======
export const getK8sProjects = (params, config = {}) => request.get('/k8s/projects/', { params, ...config })
export const createK8sProject = (data) => request.post('/k8s/projects/', data)
export const updateK8sProject = (id, data) => request.patch(`/k8s/projects/${id}/`, data)
// purge=true 才会真正删除命名空间，默认仅解绑
// mode: detach 只删平台记录 | release 额外清理集群侧标签与配额 | purge 连命名空间一并删除
export const deleteK8sProject = (id, mode = 'detach') =>
  request.delete(`/k8s/projects/${id}/`, { params: { mode } })
export const getK8sProjectMembers = (id) => request.get(`/k8s/projects/${id}/members/`)
export const addK8sProjectMember = (id, data) => request.post(`/k8s/projects/${id}/members/`, data)
export const removeK8sProjectMember = (id, userId) => request.delete(`/k8s/projects/${id}/members/${userId}/`)
export const getK8sProjectUsage = (id) => request.get(`/k8s/projects/${id}/usage/`)
export const syncK8sProjectQuota = (id) => request.post(`/k8s/projects/${id}/sync_quota/`)
export const getK8sAdoptableNamespaces = (clusterId) =>
  request.get(`/k8s/clusters/${clusterId}/adoptable_namespaces/`)
