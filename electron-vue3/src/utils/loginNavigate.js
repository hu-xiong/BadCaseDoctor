import { ensureDefaultProject, getProjects } from '../api.js'
import { setLastProjectId, getLastProjectId } from './lastProject.js'

function goProjectDetail(router, id) {
  const s = String(id).trim()
  if (!s) return false
  setLastProjectId(s)
  router.push(`/project-detail/${encodeURIComponent(s)}`)
  return true
}

async function tryEnsureDefaultProject() {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const res = await ensureDefaultProject()
      const data = res.data
      if (data?.success && data.project_id != null) {
        return String(data.project_id).trim()
      }
    } catch (e) {
      if (attempt === 0) {
        await new Promise((r) => setTimeout(r, 250))
        continue
      }
      console.warn('[navigateAfterAuth] ensure-default 失败', e)
    }
  }
  return null
}

async function pickProjectFromList() {
  try {
    const res = await getProjects()
    const list = res.data?.projects
    if (!Array.isArray(list) || list.length === 0) return null
    const pick = list.find((p) => p?.is_default) || list[0]
    const id = pick?.id
    return id != null && String(id).trim() !== '' ? String(id).trim() : null
  } catch (e) {
    console.warn('[navigateAfterAuth] getProjects 失败', e)
    return null
  }
}

/**
 * 登录/注册成功后进入工作台：
 * 上次操作项目 → 接口返回 project_id → ensure-default → 项目列表首项 → 项目管理页兜底。
 */
export async function navigateAfterAuth(router, { projectId } = {}) {
  const lastId = getLastProjectId()
  if (lastId && goProjectDetail(router, lastId)) {
    return
  }

  if (projectId != null && String(projectId).trim() !== '') {
    if (goProjectDetail(router, projectId)) {
      return
    }
  }

  const ensured = await tryEnsureDefaultProject()
  if (ensured && goProjectDetail(router, ensured)) {
    return
  }

  const fromList = await pickProjectFromList()
  if (fromList && goProjectDetail(router, fromList)) {
    return
  }

  router.push('/project-manage')
}
