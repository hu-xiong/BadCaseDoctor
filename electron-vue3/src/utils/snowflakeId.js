/**
 * 将工具/API 返回的主键统一为十进制数字字符串，供列表跳转与请求路径使用。
 * 后端应对大整数以 JSON 字符串下发；若已是被 JS 截断的 Number，无法还原，仅作字符串化。
 */
export function snowflakeIdStr(v) {
  if (v == null || v === '') return ''
  if (typeof v === 'string') {
    const s = v.trim()
    return /^\d+$/.test(s) ? s : ''
  }
  if (typeof v === 'number' && Number.isFinite(v)) {
    return String(Math.trunc(v))
  }
  if (typeof v === 'bigint') return String(v)
  const s = String(v).trim()
  return /^\d+$/.test(s) ? s : ''
}
