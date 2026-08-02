<template>
  <div
    v-if="!isElectronShell() && localGoProxyOk !== null"
    class="wlgp-anchor"
  >
    <span
      class="wlgp-pill wlgp-pill-clickable"
      :class="{
        'wlgp-pill--ok': localGoProxyOk,
        'wlgp-pill--down': !localGoProxyOk,
        'wlgp-pill--busy': proxyActionBusy
      }"
      role="button"
      tabindex="0"
      @click="onLocalProxyPillClick"
      @keydown.enter.prevent="onLocalProxyPillClick"
      @keydown.space.prevent="onLocalProxyPillClick"
    >
      {{ proxyPillLabel }}
    </span>
    <div class="wlgp-popover" @click.stop>
      <div
        v-if="proxyShowProgressUi"
        class="wlgp-progress-wrap"
        :aria-busy="proxyActionBusy ? 'true' : 'false'"
      >
        <div class="wlgp-progress-track">
          <div
            v-if="proxyProgressIndeterminate"
            class="wlgp-progress-fill wlgp-progress-fill--indeterminate"
          />
          <div
            v-else
            class="wlgp-progress-fill"
            :style="{ width: Math.min(100, Math.max(0, proxyDownloadPct)) + '%' }"
          />
        </div>
        <span class="wlgp-progress-label">{{ proxyProgressLabel }}</span>
      </div>
      <p v-if="proxyInlineError" class="wlgp-popover-err">{{ proxyInlineError }}</p>
      <p
        v-else-if="!proxyActionBusy && localGoProxyOk === false && localGoProxyLastError"
        class="wlgp-popover-body wlgp-popover-muted wlgp-popover-body--compact"
      >
        {{ localGoProxyLastError }}
      </p>
      <p
        v-else-if="!proxyActionBusy && proxyManagedByBackend"
        class="wlgp-popover-body wlgp-popover-body--compact"
      >
        {{ t('embeddedTerminal.localProxyManagedByBackend') }}
      </p>
      <p v-else-if="!proxyActionBusy && proxyPopoverBodyShort" class="wlgp-popover-body wlgp-popover-body--compact">
        {{ proxyPopoverBodyShort }}
      </p>
      <p v-else-if="!proxyActionBusy" class="wlgp-popover-body wlgp-popover-muted">
        {{ t('embeddedTerminal.localProxyPopoverIdleShort') }}
      </p>
      <div v-if="!proxyActionBusy && localGoProxyOk === true" class="wlgp-win32-section">
        <label class="wlgp-win32-label">
          <input
            type="checkbox"
            :checked="win32InputModeEnabled"
            @change="handleWin32Toggle"
          />
          <span>{{ t('embeddedTerminal.localProxyWin32InputMode') }}</span>
        </label>
        <span class="wlgp-win32-desc">{{ t('embeddedTerminal.localProxyWin32InputModeDesc') }}</span>
      </div>
      <button type="button" class="wlgp-recheck wlgp-recheck--solo" @click="onProxyRecheck">
        {{ t('embeddedTerminal.localProxyRecheck') }}
      </button>
    </div>

    <LocalProxyInstallModal
      v-model="showLocalProxyInstallModal"
      :default-path="installModalDefaultPath"
      :saving="proxyInstallSaveBusy"
      :ready="proxyBlobReady"
      :downloaded="proxyInstallDownloaded"
      :save-error="proxyInstallModalError"
      @download="onLocalProxyInstallDownload"
      @confirm="onLocalProxyInstallConfirm"
    />
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import LocalProxyInstallModal from './LocalProxyInstallModal.vue'
import { isElectronShell } from '../utils/electronPtySocketAdapter.js'
import {
  localGoProxyOk as sharedLocalGoProxyRef,
  localGoProxyLastError as sharedLocalGoProxyLastError,
  pingLocalGoProxy as sharedPingLocalGoProxy,
  win32InputModeEnabled,
  setWin32InputMode
} from '../composables/useLocalGoProxyStatus'
import {
  detectClientOS,
  detectClientArch,
  fetchLocalProxyManifest,
  pickArtifactForOs,
  fetchLocalProxyBinaryBlob,
  saveLocalProxyBlobWithoutFetch,
  readProxyInstallRecord,
  readExplicitProxyExePath,
  getDefaultLocalProxyPathPlaceholder,
  persistExplicitProxyExePath
} from '../utils/localProxyInstall.js'
import { tryWakeThenPing } from '../utils/localProxyWake.js'
import {
  tryStartInstalledLocalProxy,
  resolveInstalledLocalProxyPath,
  EVT_OPEN_LOCAL_PROXY_INSTALL,
  dispatchLocalProxyBecameOk
} from '../utils/localProxyStartAndResume.js'

const { t } = useI18n()

const props = defineProps({
  workingDirectory: { type: String, default: '' },
  projectId: { type: [Number, String], default: null }
})

const localGoProxyOk = inject('localGoProxyOk', sharedLocalGoProxyRef)
const localGoProxyLastError = inject('localGoProxyLastError', sharedLocalGoProxyLastError)
const pingLocalGoProxy = inject('pingLocalGoProxy', sharedPingLocalGoProxy)
const terminalCtl = inject('terminalCtl', null)
const ensureBottomTerminalVisible = inject('ensureBottomTerminalVisible', null)

const proxyActionBusy = ref(false)
const proxyDownloadPct = ref(null)
const proxyProgressIndeterminate = ref(false)
const proxyDownloadPhase = ref('idle')
const proxyInlineError = ref('')
const proxyManagedByBackend = ref(false)

const showLocalProxyInstallModal = ref(false)
const pendingProxyBlob = ref(null)
const pendingProxyFilename = ref('')
const proxyInstallSaveBusy = ref(false)
const proxyInstallModalError = ref('')
const proxyInstallDownloaded = ref(false)
const proxyInstallGen = ref(0)

/** 安装记录或显式路径变化时递增，驱动默认路径 computed 刷新 */
const proxyInstallSnapshotTick = ref(0)

const installModalDefaultPath = computed(() => {
  void proxyInstallSnapshotTick.value
  const explicit = readExplicitProxyExePath()
  if (explicit) return explicit
  const rec = readProxyInstallRecord()
  const inferred = rec && typeof rec.inferredFullPath === 'string' ? rec.inferredFullPath.trim() : ''
  if (inferred) return inferred
  return getDefaultLocalProxyPathPlaceholder()
})
const proxyBlobReady = computed(() => !!pendingProxyBlob.value && !!String(pendingProxyFilename.value || '').trim())

watch(showLocalProxyInstallModal, (open) => {
  if (open) {
    proxyInstallModalError.value = ''
    proxyInstallDownloaded.value = false
  } else {
    pendingProxyBlob.value = null
    pendingProxyFilename.value = ''
    proxyInstallGen.value += 1
  }
})

function refreshProxyInstallSnapshot() {
  proxyInstallSnapshotTick.value += 1
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('badcase-local-proxy-install-updated'))
  }
}

const proxyShowProgressUi = computed(
  () =>
    proxyActionBusy.value &&
    proxyDownloadPhase.value !== 'idle' &&
    (proxyProgressIndeterminate.value || proxyDownloadPct.value != null || proxyDownloadPhase.value === 'pick_save')
)

const proxyProgressLabel = computed(() => {
  const ph = proxyDownloadPhase.value
  if (ph === 'pick_save') return t('embeddedTerminal.localProxyProgressPickSave')
  if (ph === 'write') return t('embeddedTerminal.localProxyProgressWriting')
  if (ph === 'done') return t('embeddedTerminal.localProxyProgressDone')
  if (ph === 'fetch') {
    if (proxyProgressIndeterminate.value) return t('embeddedTerminal.localProxyProgressUnknown')
    const p = proxyDownloadPct.value
    if (p == null) return t('embeddedTerminal.localProxyProgressUnknown')
    if (p >= 100) return t('embeddedTerminal.localProxyProgressFetchDone')
    return t('embeddedTerminal.localProxyProgressDownloadPct', { n: Math.round(p) })
  }
  return ''
})

const proxyPopoverBodyShort = computed(() => t('embeddedTerminal.localProxyRecheckHelpShort'))

const proxyPillLabel = computed(() => {
  if (proxyActionBusy.value) {
    if (proxyDownloadPhase.value === 'pick_save') return t('embeddedTerminal.localProxyPillPickSave')
    if (proxyDownloadPhase.value === 'write') return t('embeddedTerminal.localProxyPillWriting')
    return t('embeddedTerminal.localProxyDownloading')
  }
  if (localGoProxyOk.value === true) return t('embeddedTerminal.localGoProxyOk')
  return t('embeddedTerminal.localProxyBtnInstall')
})

function onProxyRecheck() {
  proxyInlineError.value = ''
  pingLocalGoProxy()
}

function handleWin32Toggle() {
  setWin32InputMode(!win32InputModeEnabled.value)
}

function onProxyDownloadProgress(pct, phase) {
  proxyDownloadPhase.value = phase
  if (phase === 'pick_save' || phase === 'write') {
    proxyProgressIndeterminate.value = true
    proxyDownloadPct.value = null
    return
  }
  if (phase === 'done') {
    proxyProgressIndeterminate.value = false
    proxyDownloadPct.value = 100
    return
  }
  if (phase === 'fetch') {
    if (pct < 0) {
      proxyProgressIndeterminate.value = true
      proxyDownloadPct.value = null
      return
    }
    proxyProgressIndeterminate.value = false
    if (pct >= 85) {
      proxyDownloadPct.value = 100
      return
    }
    proxyDownloadPct.value = Math.min(99, Math.round((pct / 84) * 99))
  }
}

async function startProxyAfterInstall(preferredPath = '') {
  const path = String(preferredPath || resolveInstalledLocalProxyPath() || '').trim()
  if (path) persistExplicitProxyExePath(path)
  refreshProxyInstallSnapshot()
  const ctl =
    terminalCtl && typeof terminalCtl === 'object' && 'value' in terminalCtl
      ? terminalCtl.value
      : terminalCtl
  const ok = await tryStartInstalledLocalProxy({
    ping: pingLocalGoProxy,
    exePath: path,
    injectCommand: (cmd) => ctl?.injectCommand?.(cmd),
    ensureTerminalVisible: async () => {
      if (typeof ensureBottomTerminalVisible === 'function') {
        await ensureBottomTerminalVisible()
      }
    },
    retries: 12,
    delayMs: 800
  })
  if (ok) {
    dispatchLocalProxyBecameOk({ path })
    showLocalProxyInstallModal.value = false
  }
  return ok
}

async function onLocalProxyInstallConfirm(payload) {
  const targetPath = String(payload?.targetPath || '').trim()
  try {
    if (!proxyInstallDownloaded.value) return
    if (!targetPath) return
    persistExplicitProxyExePath(targetPath)
    refreshProxyInstallSnapshot()
    proxyInstallSaveBusy.value = true
    proxyInstallModalError.value = ''
    const ok = await startProxyAfterInstall(targetPath)
    if (!ok) {
      proxyInstallModalError.value = t('embeddedTerminal.localProxyStartAfterInstallHint')
    }
  } catch (e) {
    proxyInstallModalError.value = String(e?.message || e)
  } finally {
    proxyInstallSaveBusy.value = false
  }
}

async function onLocalProxyInstallDownload() {
  const blob = pendingProxyBlob.value
  const fn = pendingProxyFilename.value
  if (!blob || !fn) return
  proxyInstallSaveBusy.value = true
  proxyInstallModalError.value = ''
  proxyInlineError.value = ''
  proxyDownloadPhase.value = 'pick_save'
  proxyProgressIndeterminate.value = false
  proxyDownloadPct.value = null
  try {
    const saved = await saveLocalProxyBlobWithoutFetch(blob, fn, {
      terminalCwd: String(props.workingDirectory || '').trim(),
      projectId: props.projectId,
      tryReuseDir: false,
      onProgress: onProxyDownloadProgress
    })
    refreshProxyInstallSnapshot()
    proxyInstallDownloaded.value = true
    // 保存成功后尽量立刻启动：有推断/显式路径则唤醒；否则仍留在弹窗让用户确认路径
    const pathGuess =
      String(readExplicitProxyExePath() || '').trim() ||
      String(readProxyInstallRecord()?.inferredFullPath || '').trim()
    if (pathGuess || (saved && saved.mode && saved.mode !== 'download')) {
      if (pathGuess) persistExplicitProxyExePath(pathGuess)
      await startProxyAfterInstall(pathGuess)
    }
  } catch (e) {
    if (e && e.name === 'AbortError') {
      return
    }
    proxyInstallModalError.value = String(e?.message || e)
  } finally {
    proxyInstallSaveBusy.value = false
    proxyDownloadPhase.value = 'idle'
    proxyProgressIndeterminate.value = false
    proxyDownloadPct.value = null
  }
}

async function onLocalProxyPillClick() {
  if (isElectronShell()) return
  if (proxyActionBusy.value) return
  if (localGoProxyOk.value === true) {
    await pingLocalGoProxy()
    return
  }
  if (localGoProxyOk.value !== true) {
    await tryWakeThenPing({ retries: 1, delayMs: 450, ping: pingLocalGoProxy })
    if (localGoProxyOk.value === true) {
      refreshProxyInstallSnapshot()
      return
    }
  }

  proxyInlineError.value = ''
  pendingProxyBlob.value = null
  pendingProxyFilename.value = ''
  proxyInstallGen.value += 1
  const installGen = proxyInstallGen.value
  showLocalProxyInstallModal.value = true
  await nextTick()

  proxyActionBusy.value = true
  proxyDownloadPhase.value = 'fetch'
  proxyProgressIndeterminate.value = true
  proxyDownloadPct.value = null
  try {
    const os = detectClientOS()
    const arch = detectClientArch()
    const manifest = await fetchLocalProxyManifest()
    if (installGen !== proxyInstallGen.value) return
    const art = pickArtifactForOs(manifest?.artifacts, os, arch)
    if (!art) {
      showLocalProxyInstallModal.value = false
      proxyInlineError.value = t('embeddedTerminal.localProxyNoArtifact')
      return
    }
    if (art.available === false) {
      showLocalProxyInstallModal.value = false
      proxyInlineError.value = t('embeddedTerminal.localProxyBinaryMissingServer')
      return
    }
    pendingProxyFilename.value = String(art?.filename || '').trim()

    const { blob, filename } = await fetchLocalProxyBinaryBlob(art, onProxyDownloadProgress)
    if (installGen !== proxyInstallGen.value) return
    pendingProxyBlob.value = blob
    pendingProxyFilename.value = filename
  } catch (e) {
    if (e && e.name === 'AbortError') {
      return
    }
    showLocalProxyInstallModal.value = false
    proxyInlineError.value = String(e?.message || e)
  } finally {
    proxyActionBusy.value = false
    proxyDownloadPhase.value = 'idle'
    proxyProgressIndeterminate.value = false
    window.setTimeout(() => {
      proxyDownloadPct.value = null
    }, 900)
  }
}

function onExternalOpenInstall() {
  void onLocalProxyPillClick()
}

async function refreshSupervisorHint() {
  try {
    const { api } = await import('../api.js')
    const { data } = await api.get('/api/client-scripts/local-proxy/supervisor')
    proxyManagedByBackend.value = !!(data && data.ok && data.owned && data.running_child)
  } catch {
    proxyManagedByBackend.value = false
  }
}

onMounted(() => {
  refreshProxyInstallSnapshot()
  void refreshSupervisorHint()
  if (typeof window !== 'undefined') {
    window.addEventListener(EVT_OPEN_LOCAL_PROXY_INSTALL, onExternalOpenInstall)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener(EVT_OPEN_LOCAL_PROXY_INSTALL, onExternalOpenInstall)
  }
})
</script>

<style scoped>
.wlgp-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
}

.wlgp-anchor::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  height: 8px;
}

.wlgp-pill {
  font-size: 12px;
  color: #ffe082;
  border: 1px solid rgba(255, 193, 7, 0.35);
  background: rgba(255, 193, 7, 0.08);
  padding: 2px 6px;
  border-radius: 999px;
  white-space: nowrap;
}

.wlgp-pill--ok {
  color: #b9f6ca;
  border-color: rgba(76, 175, 80, 0.45);
  background: rgba(76, 175, 80, 0.12);
}

.wlgp-pill--down {
  color: #ffccbc;
  border-color: rgba(255, 112, 67, 0.4);
  background: rgba(255, 112, 67, 0.1);
}

.wlgp-pill-clickable {
  cursor: pointer;
  user-select: none;
}

.wlgp-pill-clickable:hover {
  filter: brightness(1.06);
}

.wlgp-pill--busy {
  opacity: 0.85;
  cursor: wait;
}

.wlgp-popover {
  position: absolute;
  left: 0;
  top: calc(100% + 4px);
  z-index: 80;
  min-width: 280px;
  max-width: min(480px, 94vw);
  padding: 10px 12px;
  background: #2d2d30;
  border: 1px solid #3c3c3c;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.12s ease, visibility 0.12s ease;
}

.wlgp-anchor:hover .wlgp-popover,
.wlgp-anchor:focus-within .wlgp-popover {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

.wlgp-progress-wrap {
  margin-bottom: 8px;
}

.wlgp-progress-track {
  height: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.wlgp-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #42a5f5, #66bb6a);
  transition: width 0.15s ease-out;
}

.wlgp-progress-fill--indeterminate {
  position: relative;
  width: 36%;
  animation: wlgp-indet 1.1s ease-in-out infinite;
}

@keyframes wlgp-indet {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(350%);
  }
}

.wlgp-progress-label {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #aaa;
}

.wlgp-popover-body {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.45;
  color: #ccc;
  white-space: pre-wrap;
  word-break: break-word;
}

.wlgp-popover-body--compact {
  white-space: normal;
}

.wlgp-popover-muted {
  color: #888;
}

.wlgp-popover-err {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.45;
  color: #ffab91;
  white-space: pre-wrap;
  word-break: break-word;
}

.wlgp-win32-section {
  margin: 8px 0;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
}

.wlgp-win32-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #e0e0e0;
  cursor: pointer;
}

.wlgp-win32-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.wlgp-win32-desc {
  display: block;
  margin-top: 4px;
  margin-left: 22px;
  font-size: 10px;
  color: #888;
  line-height: 1.4;
}

.wlgp-recheck {
  display: inline-block;
  margin: 0;
  padding: 4px 10px;
  font-size: 11px;
  color: #e0e0e0;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid #444;
  border-radius: 6px;
  cursor: pointer;
}

.wlgp-recheck:hover {
  background: rgba(255, 255, 255, 0.12);
}

.wlgp-recheck--solo {
  margin-top: 4px;
}
</style>
