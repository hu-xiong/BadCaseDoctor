/** 富文本是否有实质内容（纯文本或有效图片/视频） */

function meaningfulMediaSrc(src) {
  const s = String(src || '').trim()
  return Boolean(s && s !== 'about:blank')
}

function countTagsWithSrc(html, tagName) {
  const raw = String(html || '')
  const re = new RegExp(`<${tagName}\\b[^>]*>`, 'gi')
  let count = 0
  let m
  while ((m = re.exec(raw))) {
    const srcM = m[0].match(/\bsrc\s*=\s*["']([^"']*)["']/i)
    if (srcM && meaningfulMediaSrc(srcM[1])) count++
  }
  return count
}

/** @param {string} html */
export function htmlToPlainText(html) {
  if (!html) return ''
  if (typeof document !== 'undefined') {
    const d = document.createElement('div')
    d.innerHTML = html
    return (d.textContent || d.innerText || '').trim()
  }
  return String(html)
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function countRichTextMedia(html) {
  return (
    countTagsWithSrc(html, 'img') +
    countTagsWithSrc(html, 'uploader') +
    countTagsWithSrc(html, 'video')
  )
}

/** 是否视为「已填写」（含仅图片/视频） */
export function richTextHtmlHasContent(html) {
  if (!String(html || '').trim()) return false
  if (countRichTextMedia(html) > 0) return true
  return Boolean(htmlToPlainText(html))
}

/** 字数展示：无文字但有图时按图片张数计，避免显示 0 */
export function richTextHtmlDisplayLength(html) {
  const plainLen = htmlToPlainText(html).length
  const mediaCount = countRichTextMedia(html)
  if (plainLen > 0) return plainLen
  return mediaCount
}
