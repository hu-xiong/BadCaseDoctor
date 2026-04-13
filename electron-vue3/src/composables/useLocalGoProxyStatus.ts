/**
 * 本机 go-local-proxy /health 探测（纯浏览器；Electron 壳不走此轮询）。
 * 行为对齐「集成终端」类产品的连接感知：可见时刷新、失败时更频繁重试、带超时避免挂死。
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { getLocalShellProxyHealthUrl } from '../utils/localShellProxyClient.js'
import { isElectronShell } from '../utils/electronPtySocketAdapter.js'

export const localGoProxyOk = ref<boolean | null>(null)
export const localGoProxyLastCheckAt = ref<number | null>(null)
export const localGoProxyLastError = ref<string | null>(null)

const POLL_OK_MS = 20_000
const POLL_DOWN_MS = 5_000
const FETCH_TIMEOUT_MS = 3_000

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollConsumers = 0

function scheduleNextPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (pollConsumers <= 0) return
  const ms = localGoProxyOk.value === true ? POLL_OK_MS : POLL_DOWN_MS
  pollTimer = window.setInterval(() => {
    void pingLocalGoProxy()
  }, ms)
}

export async function pingLocalGoProxy(): Promise<void> {
  if (typeof fetch === 'undefined') return
  localGoProxyLastError.value = null
  const ac = new AbortController()
  const to = window.setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS)
  try {
    const r = await fetch(getLocalShellProxyHealthUrl(), {
      method: 'GET',
      cache: 'no-store',
      signal: ac.signal
    })
    const text = await r.text()
    const ok = r.ok && text.trim() === 'ok'
    localGoProxyOk.value = ok
    if (!ok) {
      localGoProxyLastError.value = !r.ok ? `HTTP ${r.status}` : 'health body not ok'
    }
  } catch (e: unknown) {
    localGoProxyOk.value = false
    localGoProxyLastError.value = e instanceof Error ? e.message : String(e)
  } finally {
    window.clearTimeout(to)
    localGoProxyLastCheckAt.value = Date.now()
    scheduleNextPoll()
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    void pingLocalGoProxy()
  }
}

/**
 * 在 ProjectDetail（或唯一根组件）调用一次，负责轮询；子组件 inject 共享状态。
 */
export function useLocalGoProxyStatus() {
  onMounted(() => {
    if (isElectronShell()) return
    pollConsumers += 1
    if (pollConsumers === 1) {
      void pingLocalGoProxy()
      scheduleNextPoll()
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
  })

  onBeforeUnmount(() => {
    if (isElectronShell()) return
    pollConsumers = Math.max(0, pollConsumers - 1)
    if (pollConsumers === 0) {
      if (pollTimer != null) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  })

  return { localGoProxyOk, localGoProxyLastCheckAt, localGoProxyLastError, pingLocalGoProxy }
}
