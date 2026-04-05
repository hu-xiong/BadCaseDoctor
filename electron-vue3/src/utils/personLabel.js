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

/** 副行：角色、部门等，不包含邮箱 */
export function personSecondaryLabel(u) {
  if (u == null) return ''
  const role = String(u.role ?? '').trim()
  const dept = String(u.department ?? '').trim()
  const src = String(u.source ?? '').trim()
  const parts = [role, dept, src].filter(Boolean)
  return parts.join(' · ')
}
