import { snowflakeIdStr } from './snowflakeId.js'

/**
 * 新建/编辑页负责人展示：优先姓名，避免主标题整段邮箱；name 为空或与 email 相同时做降级。
 */
export function personPrimaryLabel(u) {
  if (u == null) return ''
  const nameRaw = String(u.name ?? '').trim()
  const emailRaw = String(u.email ?? '').trim()
  const email = emailRaw.toLowerCase()
  if (nameRaw) {
    if (email && nameRaw.toLowerCase() === email) {
      const at = nameRaw.indexOf('@')
      return at > 0 ? nameRaw.slice(0, at) : nameRaw
    }
    return nameRaw
  }
  const nick = String(u.nickname ?? '').trim()
  if (nick) return nick
  if (emailRaw) {
    const at = emailRaw.indexOf('@')
    return at > 0 ? emailRaw.slice(0, at) : emailRaw
  }
  if (u.id != null && u.id !== '') return `用户#${u.id}`
  return '未知用户'
}

/** 副行：优先邮箱（便于辨认账号）；无邮箱时显示部门 */
export function personSecondaryLabel(u) {
  if (u == null) return ''
  const email = String(u.email ?? '').trim()
  if (email) {
    const primary = personPrimaryLabel(u)
    if (primary.toLowerCase() !== email.toLowerCase()) {
      return email
    }
    return ''
  }
  return String(u.department ?? '').trim()
}

export function assigneeIdFromUser(u) {
  if (u == null) return null
  return snowflakeIdStr(u.id) || (u.id != null && u.id !== '' ? String(u.id).trim() : null)
}

/** 新建时无负责人则默认当前登录用户 */
export function applyDefaultAssigneeOnCreate(form, userLike, { isEdit = false } = {}) {
  if (isEdit || !form) return
  const cur = form.assignee
  if (Array.isArray(cur) && cur.length > 0) return
  if (cur != null && !Array.isArray(cur) && String(cur).trim() !== '') return
  const uid = assigneeIdFromUser(userLike)
  if (!uid) return
  form.assignee = [uid]
  if ('assignee_id' in form) {
    form.assignee_id = uid
  }
}
