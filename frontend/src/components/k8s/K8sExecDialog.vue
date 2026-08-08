<template>
  <el-dialog
    v-model="visible"
    :title="'Pod Terminal - ' + form.pod_name"
    width="92%"
    style="max-width:1100px;"
    top="4vh"
    append-to-body
    destroy-on-close
  >
    <div class="filter-bar" style="margin-bottom:8px;">
      <el-tag size="large" type="info">{{ form.namespace }}</el-tag>
      <el-select
        v-if="containers.length > 1"
        v-model="form.container"
        size="small"
        style="width:180px"
        @change="reconnect"
      >
        <el-option v-for="name in containers" :key="name" :label="name" :value="name" />
      </el-select>
      <el-tag v-else-if="form.container" size="large">容器: {{ form.container }}</el-tag>
      <el-tag :type="statusTagType" size="large">{{ statusText }}</el-tag>
      <el-button size="small" plain :disabled="!visible" @click="reconnect">
        <el-icon><RefreshRight /></el-icon> 重连
      </el-button>
      <el-button size="small" plain :disabled="!sessionLog" @click="downloadSessionLog">下载会话日志</el-button>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
      <el-button v-for="preset in PRESET_COMMANDS" :key="preset.command" size="small" plain @click="runPreset(preset.command)">
        {{ preset.label }}
      </el-button>
    </div>
    <div ref="terminalRef" style="height:420px;background:#0f172a;border-radius:12px;overflow:hidden;padding:8px;"></div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useK8sStore } from '@/stores/k8s'

const SESSION_LOG_LIMIT = 200000
const PRESET_COMMANDS = [
  { label: 'pwd', command: 'pwd' },
  { label: 'env', command: 'env' },
  { label: 'ps aux', command: 'ps aux' },
  { label: 'df -h', command: 'df -h' },
  { label: 'kubectl get pods', command: 'kubectl get pods' },
]

const k8sStore = useK8sStore()

const visible = ref(false)
const form = ref({ pod_name: '', namespace: 'default', container: '' })
const containers = ref([])
const terminalRef = ref(null)
const sessionLog = ref('')
const wsStatus = ref('disconnected')

const statusText = computed(() => ({
  connecting: '连接中',
  connected: '已连接',
  error: '异常',
  disconnected: '未连接',
}[wsStatus.value] || '未连接'))

const statusTagType = computed(() => ({
  connecting: 'warning',
  connected: 'success',
  error: 'danger',
  disconnected: 'info',
}[wsStatus.value] || 'info'))

let terminal = null
let fitAddon = null
let socket = null
let resizeObserver = null
let closingByClient = false

function open(row, containerNames) {
  containers.value = containerNames || []
  form.value = {
    pod_name: row.name,
    namespace: row.namespace || 'default',
    container: containers.value[0] || '',
  }
  sessionLog.value = ''
  visible.value = true
}

function appendSessionLog(chunk) {
  if (!chunk) return
  sessionLog.value += chunk
  if (sessionLog.value.length > SESSION_LOG_LIMIT) {
    sessionLog.value = sessionLog.value.slice(-SESSION_LOG_LIMIT)
  }
}

function appendSystemLine(message) {
  appendSessionLog(`[${new Date().toLocaleTimeString()}] ${message}\n`)
}

function sendInput(data) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    ElMessage.warning('终端未连接')
    return false
  }
  socket.send(JSON.stringify({ type: 'input', data }))
  return true
}

function runPreset(command) {
  if (sendInput(`${command}\r`) && terminal) {
    terminal.focus()
  }
}

function downloadSessionLog() {
  if (!sessionLog.value) return
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const blob = new Blob([sessionLog.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `k8s-exec-${form.value.pod_name || 'session'}-${stamp}.log`
  link.click()
  URL.revokeObjectURL(url)
}

function initTerminal() {
  dispose()
  if (!terminalRef.value) return

  terminal = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
    theme: {
      background: '#0f172a',
      foreground: '#e2e8f0',
      cursor: '#22c55e',
      selectionBackground: '#22c55e33',
    },
    scrollback: 5000,
  })
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalRef.value)
  fitAddon.fit()
  terminal.writeln('\x1b[1;36mHYSDevOps Pod Terminal\x1b[0m')
  terminal.writeln('\x1b[2mConnecting to pod...\x1b[0m')
  terminal.writeln('')

  terminal.onData((data) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'input', data }))
    }
  })

  resizeObserver = new ResizeObserver(() => {
    if (fitAddon) {
      fitAddon.fit()
      sendResize()
    }
  })
  resizeObserver.observe(terminalRef.value)
}

function sendResize() {
  if (!terminal || !socket || socket.readyState !== WebSocket.OPEN) return
  socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }))
}

function connect() {
  const clusterId = k8sStore.selectedClusterId
  if (!clusterId || !form.value.pod_name || !terminal) return
  disconnectSocket()

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams({
    token: localStorage.getItem('sxdevops_token') || '',
    pod_name: form.value.pod_name,
    namespace: form.value.namespace || 'default',
  })
  if (form.value.container) {
    params.set('container', form.value.container)
  }

  closingByClient = false
  wsStatus.value = 'connecting'
  appendSystemLine(`connecting to ${form.value.pod_name}`)
  socket = new WebSocket(`${protocol}//${window.location.host}/ws/k8s/exec/${clusterId}/?${params.toString()}`)

  socket.onopen = () => {
    wsStatus.value = 'connected'
    appendSystemLine(`connected to ${form.value.pod_name}`)
    sendResize()
  }

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'output') {
        if (terminal) terminal.write(payload.data || '')
        appendSessionLog(payload.data || '')
      } else if (payload.type === 'connected') {
        if (terminal) terminal.writeln(`\x1b[1;32m${payload.message}\x1b[0m`)
        appendSystemLine(payload.message || 'terminal connected')
      } else if (payload.type === 'error') {
        wsStatus.value = 'error'
        if (terminal) terminal.writeln(`\x1b[1;31m${payload.message}\x1b[0m`)
        appendSystemLine(payload.message || 'terminal error')
      }
    } catch {
      if (terminal) terminal.write(event.data)
      appendSessionLog(event.data || '')
    }
  }

  socket.onclose = () => {
    if (closingByClient) {
      closingByClient = false
      return
    }
    if (wsStatus.value !== 'error') {
      wsStatus.value = 'disconnected'
    }
    appendSystemLine('terminal disconnected')
  }

  socket.onerror = () => {
    wsStatus.value = 'error'
    appendSystemLine('terminal websocket error')
  }
}

function disconnectSocket() {
  if (socket) {
    closingByClient = true
    socket.close()
    socket = null
  }
}

function dispose() {
  disconnectSocket()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (terminal) {
    terminal.dispose()
    terminal = null
  }
  fitAddon = null
  wsStatus.value = 'disconnected'
}

function reconnect() {
  if (!visible.value) return
  nextTick(() => {
    initTerminal()
    connect()
  })
}

watch(visible, (open) => {
  if (open) reconnect()
  else dispose()
})

onBeforeUnmount(dispose)

defineExpose({ open })
</script>
