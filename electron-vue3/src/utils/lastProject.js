const STORAGE_KEY = 'lastProjectId'

/** 上次进入的项目 id（雪花 id 用字符串存，避免 Number 精度丢失） */
export function getLastProjectId() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw == null || String(raw).trim() === '') return null
    return String(raw).trim()
  } catch {
    return null
  }
}

export function setLastProjectId(id) {
  if (id == null || String(id).trim() === '') return
  try {
    localStorage.setItem(STORAGE_KEY, String(id).trim())
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearLastProjectId() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
