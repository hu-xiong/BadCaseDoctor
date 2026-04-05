<template>
  <div class="embedded-pty-root">
    <div v-if="statusText" class="embedded-pty-status">{{ statusText }}</div>
    <div ref="termHost" class="embedded-pty-xterm"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, inject, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { io } from 'socket.io-client'
import { BACKEND_BASE_URL } from '../api.js'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const props = defineProps({
  clientSessionId: { type: String, default: 'default' },
  /** local | ssh */
  mode: { type: String, default: 'local' },
  sshConfig: { type: Object, default: () => ({}) },
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null }
})

const { t } = useI18n()
const termHost = ref(null)
const statusText = ref('')

const ptySocketRef = inject('ptySocket', null)
const terminalPasteRef = inject('terminalPaste', null)
const selectionRegistry = inject('terminalSelectionRegistry', null)
const onTermSelectionChange = inject('onTermSelectionChange', null)

let term = null
let fit = null
let socket = null
let ownSocket = false
let resizeObserver = null
let handlersBound = false

function stringToUtf8B64(str) {
  const u8 = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < u8.length; i += 1) binary += String.fromCharCode(u8[i])
  return btoa(binary)
}

function b64ToUint8Array(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i)
  return out
}

function emitResize() {
  if (!socket || !term || !socket.connected) return
  socket.emit('term_resize', {
    cols: term.cols,
    rows: term.rows,
    client_session_id: props.clientSessionId
  })
}

function requestTermStart() {
  if (!socket || !term || !socket.connected) return
  const pid = props.projectId != null && props.projectId !== '' ? Number(props.projectId) : undefined
  const base = {
    client_session_id: props.clientSessionId,
    cols: term.cols,
    rows: term.rows,
    cwd: (props.workingDirectory || '').trim() || undefined,
    mode: props.mode,
    project_id: Number.isFinite(pid) ? pid : undefined
  }
  if (props.mode === 'ssh') {
    const c = props.sshConfig || {}
    base.ssh = {
      host: (c.host || '').trim(),
      port: Number(c.port) || 22,
      username: (c.username || '').trim(),
      password: c.password || '',
      key_text: (c.key_text || '').trim() || undefined
    }
  }
  socket.emit('term_start', base)
}

/** 具名回调，卸载时必须 socket.off，否则 Vue Strict Mode / 多实例会重复绑定，disconnect 会刷屏且状态异常 */
function scheduleTermStart() {
  requestTermStart()
  setTimeout(() => requestTermStart(), 120)
  setTimeout(() => requestTermStart(), 400)
}

function onPtyConnect() {
  console.log('[EmbeddedPtyTerminal] onPtyConnect, sid:', socket?.id)
  statusText.value = ''
  nextTick(() => {
    if (fit && term) fit.fit()
    requestAnimationFrame(() => {
      if (fit && term) fit.fit()
      scheduleTermStart()
    })
  })
}

function onPtyConnectError(err) {
  console.error('[EmbeddedPtyTerminal] onPtyConnectError:', err)
  statusText.value = t('embeddedTerminal.connectError')
}

function onPtyDisconnect() {
  statusText.value = t('embeddedTerminal.disconnected')
  if (term) {
    term.write(`\r\n\x1b[33m${t('embeddedTerminal.disconnected')}\x1b[0m\r\n`)
  }
}

function onPtyTermStarted(payload) {
  if (payload && payload.client_session_id && payload.client_session_id !== props.clientSessionId) return
  emitResize()
}

function onPtyTermOutput(payload) {
  if (!payload || payload.client_session_id !== props.clientSessionId) return
  const b64 = payload.b64
  if (!b64 || !term) return
  try {
    term.write(b64ToUint8Array(b64))
  } catch (_) {
    /* ignore */
  }
}

function onPtyTermError(payload) {
  if (!payload || payload.client_session_id !== props.clientSessionId) return
  const msg = payload.message || t('embeddedTerminal.ptyError')
  statusText.value = msg
  if (term) term.write(`\r\n\x1b[31m${msg}\x1b[0m\r\n`)
}

function onPtyTermExit(payload) {
  if (payload && payload.client_session_id && payload.client_session_id !== props.clientSessionId) return
  if (term) term.write(`\r\n\x1b[90m[exit]\x1b[0m\r\n`)
}

function bindSocketHandlers() {
  if (handlersBound || !socket) return
  handlersBound = true
  socket.on('connect', onPtyConnect)
  socket.on('connect_error', onPtyConnectError)
  socket.on('disconnect', onPtyDisconnect)
  socket.on('term_started', onPtyTermStarted)
  socket.on('term_output', onPtyTermOutput)
  socket.on('term_error', onPtyTermError)
  socket.on('term_exit', onPtyTermExit)
}

function unbindSocketHandlers() {
  if (!handlersBound || !socket) return
  socket.off('connect', onPtyConnect)
  socket.off('connect_error', onPtyConnectError)
  socket.off('disconnect', onPtyDisconnect)
  socket.off('term_started', onPtyTermStarted)
  socket.off('term_output', onPtyTermOutput)
  socket.off('term_error', onPtyTermError)
  socket.off('term_exit', onPtyTermExit)
  handlersBound = false
}

function setupTerminal() {
  term = new Terminal({
    cursorBlink: true,
    scrollback: 3000,
    fontSize: 14,
    theme: {
      background: '#1e1e1e',
      foreground: '#cccccc',
      cursor: '#aeafad'
    }
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termHost.value)
  fit.fit()

  term.onData((data) => {
    if (socket && socket.connected) {
      socket.emit('term_input', {
        b64: stringToUtf8B64(data),
        client_session_id: props.clientSessionId
      })
    }
  })

  if (onTermSelectionChange) {
    term.onSelectionChange(() => {
      try {
        onTermSelectionChange()
      } catch (_) {
        /* ignore */
      }
    })
  }
}

function resolveSocket() {
  if (ptySocketRef && ptySocketRef.value) {
    socket = ptySocketRef.value
    ownSocket = false
    return
  }
  ownSocket = true
  socket = io(BACKEND_BASE_URL || undefined, {
    path: '/socket.io/',
    transports: ['polling'], // 只用 polling，避免 Vite 代理 WebSocket 升级失败
    withCredentials: true,
    timeout: 60000,
    reconnection: true,
    reconnectionAttempts: 20,
    reconnectionDelay: 800
  })
}

function connectFlow() {
  statusText.value = t('embeddedTerminal.connecting')
  resolveSocket()
  bindSocketHandlers()
  if (socket.connected) scheduleTermStart()
}

let onWinResize = null

onMounted(() => {
  setupTerminal()

  if (selectionRegistry && typeof selectionRegistry.register === 'function') {
    selectionRegistry.register(props.clientSessionId, () =>
      term && typeof term.getSelection === 'function' ? term.getSelection() : ''
    )
  }

  if (ptySocketRef) {
    watch(
      () => ptySocketRef.value,
      (s, prev) => {
        if (prev && prev !== s) {
          unbindSocketHandlers()
          socket = null
        }
        if (!s) return
        socket = s
        ownSocket = false
        bindSocketHandlers()
        if (socket.connected) scheduleTermStart()
      },
      { immediate: true }
    )
  } else {
    connectFlow()
  }

  if (terminalPasteRef) {
    watch(
      terminalPasteRef,
      (sig) => {
        if (!sig || !socket || !socket.connected || sig.csid !== props.clientSessionId) return
        const line = String(sig.text || '')
        if (!line) return
        const nl = line.endsWith('\n') ? line : `${line}\r`
        socket.emit('term_input', {
          b64: stringToUtf8B64(nl),
          client_session_id: props.clientSessionId
        })
      },
      { deep: true }
    )
  }

  onWinResize = () => {
    if (fit && term) {
      fit.fit()
      emitResize()
    }
  }
  window.addEventListener('resize', onWinResize)

  if (typeof ResizeObserver !== 'undefined' && termHost.value) {
    resizeObserver = new ResizeObserver(() => {
      if (fit && term) {
        fit.fit()
        emitResize()
      }
    })
    resizeObserver.observe(termHost.value)
  }
})

onBeforeUnmount(() => {
  unbindSocketHandlers()
  if (selectionRegistry && typeof selectionRegistry.unregister === 'function') {
    selectionRegistry.unregister(props.clientSessionId)
  }
  if (onWinResize) window.removeEventListener('resize', onWinResize)
  if (resizeObserver && termHost.value) {
    try {
      resizeObserver.unobserve(termHost.value)
    } catch (_) {
      /* ignore */
    }
    resizeObserver = null
  }
  if (socket && socket.connected) {
    try {
      socket.emit('term_close', { client_session_id: props.clientSessionId })
    } catch (_) {
      /* ignore */
    }
  }
  if (ownSocket && socket) {
    socket.close()
    socket = null
  }
  if (term) {
    term.dispose()
    term = null
  }
})
</script>

<style scoped>
.embedded-pty-root {
  width: 100%;
  height: 100%;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  border-radius: 4px;
  overflow: hidden;
}

.embedded-pty-status {
  flex: 0 0 auto;
  padding: 6px 10px;
  font-size: 12px;
  color: #f0c674;
  background: rgba(0, 0, 0, 0.35);
}

.embedded-pty-xterm {
  flex: 1 1 auto;
  min-height: 0;
  padding: 6px 8px 8px;
}

.embedded-pty-xterm :deep(.xterm) {
  height: 100%;
}

.embedded-pty-xterm :deep(.xterm-viewport) {
  overflow-y: auto;
}
</style>
