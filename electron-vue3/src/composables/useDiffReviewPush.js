import { ref, watch, onUnmounted, unref } from 'vue'
import { BACKEND_BASE_URL } from '../api.js'

let _sharedPid = null
let _refCount = 0
let _timer = null
let _etag = ''
let _inFlight = null
let _lastPollAt = 0
let _lastVersion = ''
let _failCount = 0

const BASE_INTERVAL_MS = 15000
const HIDDEN_INTERVAL_MS = 60000
const ERROR_MAX_BACKOFF_MS = 120000

export const diffReviewPushShared = {
  connected: ref(false),
  lastEventAt: ref(0)
}

const dispatch = (type, payload) => {
  diffReviewPushShared.lastEventAt.value = Date.now()
  window.dispatchEvent(
    new CustomEvent('diff-review-push', {
      bubbles: true,
      detail: { type, payload }
    })
  )
}

const clearTimer = () => {
  if (_timer) {
    clearTimeout(_timer)
    _timer = null
  }
}

const resetState = () => {
  clearTimer()
  _etag = ''
  _inFlight = null
  _lastPollAt = 0
  _lastVersion = ''
  _failCount = 0
  diffReviewPushShared.connected.value = false
}

const pollIntervalMs = () => {
  if (document.visibilityState === 'hidden') return HIDDEN_INTERVAL_MS
  if (_failCount <= 0) return BASE_INTERVAL_MS
  return Math.min(ERROR_MAX_BACKOFF_MS, BASE_INTERVAL_MS * Math.pow(2, _failCount))
}

const schedulePoll = (delay = pollIntervalMs()) => {
  clearTimer()
  if (!_sharedPid || _refCount <= 0) return
  _timer = setTimeout(() => {
    _timer = null
    void pollOnce(false)
  }, Math.max(1000, delay))
}

const pollOnce = async (force = false) => {
  const pid = _sharedPid
  if (!pid || _refCount <= 0) return
  const now = Date.now()
  const minGap = force ? 3000 : pollIntervalMs()
  if (!force && now - _lastPollAt < minGap) {
    schedulePoll(minGap - (now - _lastPollAt))
    return
  }
  if (_inFlight) return _inFlight

  _lastPollAt = now
  _inFlight = (async () => {
    try {
      const headers = {}
      if (_etag) headers['If-None-Match'] = _etag
      const resp = await fetch(
        `${BACKEND_BASE_URL}/api/projects/${encodeURIComponent(pid)}/diff-reviews?status=pending`,
        { credentials: 'include', headers }
      )
      if (resp.status === 304) {
        _failCount = 0
        diffReviewPushShared.connected.value = true
        diffReviewPushShared.lastEventAt.value = Date.now()
        return
      }
      if (!resp.ok) throw new Error(`diff review poll ${resp.status}`)

      const et = resp.headers.get('ETag')
      if (et) _etag = et.replace(/^"|"$/g, '')
      const data = await resp.json().catch(() => ({}))
      const version = String(data?.version || _etag || '')
      _failCount = 0
      diffReviewPushShared.connected.value = true
      if (force || version !== _lastVersion) {
        _lastVersion = version
        dispatch('snapshot', { items: Array.isArray(data?.items) ? data.items : [] })
      } else {
        diffReviewPushShared.lastEventAt.value = Date.now()
      }
    } catch (e) {
      _failCount += 1
      diffReviewPushShared.connected.value = false
      console.warn('[DIFF-SYNC] poll failed:', e)
    } finally {
      _inFlight = null
      schedulePoll()
    }
  })()
  return _inFlight
}

const switchProject = (pid) => {
  const pidStr = pid ? String(pid) : ''
  if (!pidStr) {
    resetState()
    _sharedPid = null
    return
  }
  if (_sharedPid === pidStr) {
    schedulePoll(1000)
    return
  }
  resetState()
  _sharedPid = pidStr
  void pollOnce(true)
}

const onVisibilityChange = () => {
  if (document.visibilityState === 'visible') {
    void pollOnce(true)
  } else {
    schedulePoll()
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibilityChange)
}

export function useDiffReviewPush(projectIdRef) {
  const stop = watch(
    () => unref(projectIdRef),
    (pid) => switchProject(pid),
    { immediate: true }
  )

  _refCount += 1
  onUnmounted(() => {
    stop()
    _refCount = Math.max(0, _refCount - 1)
    if (_refCount === 0) {
      resetState()
      _sharedPid = null
    }
  })

  return {
    connected: diffReviewPushShared.connected,
    lastEventAt: diffReviewPushShared.lastEventAt,
    reconnect: () => pollOnce(true)
  }
}
