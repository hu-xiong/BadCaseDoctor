/** delete 工具 confirm=false 预览（含 preview.record），与 create 的 preview 区分 */

import { snowflakeIdStr } from './snowflakeId.js'

const DELETE_TARGETS = new Set(['bug', 'badcase', 'testcase', 'card', 'plan'])

export function looksLikeDeleteToolPreview(toolData) {
  if (!toolData || typeof toolData !== 'object') return false
  if (toolData.success === false) return false
  if (toolData.created_id != null && String(toolData.created_id).trim() !== '') return false
  if (toolData.confirmation_required !== true && toolData.confirmation_required !== 'true') {
    return false
  }
  if (Array.isArray(toolData.diff) && toolData.diff.length > 0) return false
  if (toolData.batch_modify === true) return false
  const pv = toolData.preview
  if (!pv || typeof pv !== 'object') return false
  const rec = pv.record
  if (!rec || typeof rec !== 'object') return false
  const tgt = String(toolData.target || pv.target || '').trim().toLowerCase()
  if (tgt && DELETE_TARGETS.has(tgt)) return true
  return rec.id != null && (rec.title != null || rec.name != null)
}

export function deletePreviewRecordLabel(nav) {
  const rec = nav?.preview?.record && typeof nav.preview.record === 'object' ? nav.preview.record : {}
  const nm = rec.name ?? rec.title
  if (nm != null && String(nm).trim()) return String(nm).trim()
  const id = nav?.target_id ?? rec.id
  return id != null ? `#${id}` : '—'
}

export function deletePreviewFieldRows(nav, t) {
  const rec = nav?.preview?.record && typeof nav.preview.record === 'object' ? nav.preview.record : {}
  const tgt = String(nav?.target || nav?.preview?.target || '').toLowerCase()
  const rows = []
  const push = (key, label, val) => {
    if (val == null || val === '') return
    rows.push({ key, label, value: val })
  }
  const idRaw = nav?.target_id ?? rec.id
  const idDisplay = snowflakeIdStr(idRaw) || (idRaw != null ? String(idRaw) : '')
  push('id', t('chat.deletePreviewFieldId'), idDisplay || null)
  if (tgt === 'plan') {
    push('name', t('chat.deletePreviewFieldName'), rec.name)
    if (rec.is_default != null) {
      push(
        'is_default',
        t('chat.deletePreviewFieldDefaultPlan'),
        rec.is_default ? t('chat.deletePreviewBoolYes') : t('chat.deletePreviewBoolNo')
      )
    }
  } else {
    push('title', t('chat.deletePreviewFieldTitle'), rec.title ?? rec.name)
    push('type', t('chat.deletePreviewFieldType'), rec.type)
    push('status', t('chat.deletePreviewFieldStatus'), rec.status)
  }
  push('project_id', t('chat.deletePreviewFieldProject'), rec.project_id)
  if (tgt !== 'plan') {
    push('plan_id', t('chat.deletePreviewFieldPlan'), rec.plan_id)
  }
  return rows
}

/** 删除沙箱底部按钮（勿复用 tempCard 的「创建/不创建」） */
export function deleteSandboxConfirmLabel(nav, t) {
  const tgt = String(nav?.target || nav?.preview?.target || '').toLowerCase()
  if (tgt === 'plan') return t('chat.deleteSandboxConfirmPlan')
  if (tgt === 'card') return t('chat.deleteSandboxConfirmCard')
  return t('chat.deleteSandboxConfirm')
}

export function deleteSandboxCancelLabel(_nav, t) {
  return t('chat.deleteSandboxCancel')
}
