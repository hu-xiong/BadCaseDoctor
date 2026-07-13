import { ensureDefaultProject } from '../api.js'
import { setLastProjectId } from './lastProject.js'

let _inflight = null

/**
 * 进入工作台后异步确保用户有关联的默认项目（从系统模板克隆）。
 * 若当前路由项目 id 与 ensure-default 返回不一致，则 replace 到正确项目。
 */
export function ensureUserDefaultProject(router, { currentProjectId } = {}) {
  if (_inflight) return _inflight

  _inflight = (async () => {
    try {
      const res = await ensureDefaultProject()
      const data = res.data
      if (!data?.success || data.project_id == null) return data

      const target = String(data.project_id).trim()
      setLastProjectId(target)

      const cur =
        currentProjectId != null && String(currentProjectId).trim() !== ''
          ? String(currentProjectId).trim()
          : ''

      if (cur === target) return data

      const route = router.currentRoute.value
      const onDetail =
        route?.name === 'ProjectDetail' ||
        String(route?.path || '').includes('project-detail')
      const onManage =
        route?.name === 'ProjectManage' ||
        String(route?.path || '').includes('project-manage')

      // 在详情页若 URL 项目 id 与本人默认项目不一致，必须纠正（避免误操作系统模板等）
      const shouldGoDetail = onDetail || data.created || !cur || onManage
      if (shouldGoDetail) {
        await router.replace(`/project-detail/${encodeURIComponent(target)}`)
      }
      return data
    } catch (e) {
      console.warn('[ensureUserDefaultProject]', e)
      return null
    } finally {
      _inflight = null
    }
  })()

  return _inflight
}
