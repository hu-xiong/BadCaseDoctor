/**
 * MinIO 直链在浏览器中常因私有桶/跨域无法加载；统一转为后端代理路径。
 * vue3-tiptap-editor 的 Uploader 为块级且不上写 attrs.src，需转为行内 <img> 才能跟在文字后并持久化。
 */

function encodeObjectKey(key) {
  return String(key || '')
    .split('/')
    .filter((p) => p.length > 0)
    .map(encodeURIComponent)
    .join('/')
}

/** @param {string} url */
export function normalizeUploadImageUrl(url) {
  const s = String(url || '').trim()
  if (!s || s.startsWith('/api/uploads/image/') || s.startsWith('data:') || s.startsWith('blob:')) {
    return s
  }

  const markers = ['/saas_qa_file/', 'saas_qa_file/']
  for (const marker of markers) {
    const idx = s.indexOf(marker)
    if (idx < 0) continue
    const start = marker.startsWith('/') ? idx + 1 : idx
    const key = s.slice(start).split('?')[0].split('#')[0]
    if (key) return `/api/uploads/image/${encodeObjectKey(key)}`
  }

  const bucketMarkers = ['/apaas-root/']
  for (const marker of bucketMarkers) {
    const idx = s.indexOf(marker)
    if (idx < 0) continue
    const key = s.slice(idx + marker.length).split('?')[0].split('#')[0]
    if (key) return `/api/uploads/image/${encodeObjectKey(key)}`
  }

  return s
}

/** 从 uploader 标签属性串中取出 src */
function srcFromUploaderAttrs(attrs) {
  const m = String(attrs || '').match(/\bsrc=["']([^"']+)["']/i)
  return m ? normalizeUploadImageUrl(m[1]) : ''
}

const INLINE_IMG_HTML =
  '<img class="rte-inline-img" src="{src}" alt="" style="display:inline-block;vertical-align:middle;max-width:280px;height:auto;margin:0 2px" />'

/**
 * 将历史/库生成的 <uploader src="..."> 转为行内 img，去掉无 src 的占位块。
 * @param {string} html
 */
export function convertUploaderTagsToImages(html) {
  if (!html || typeof html !== 'string') return html || ''

  let out = html.replace(/<uploader\b([^>]*?)(?:\/>|>(?:\s*<\/uploader>)?)/gi, (_m, attrs) => {
    const src = srcFromUploaderAttrs(attrs)
    if (!src) return ''
    return INLINE_IMG_HTML.replace('{src}', src)
  })

  out = out.replace(/<\/uploader>/gi, '')
  return out
}

/** @param {string} html */
export function rewriteHtmlUploadImageUrls(html) {
  if (!html || typeof html !== 'string') return html || ''
  return html.replace(
    /(<img\b[^>]*\bsrc=["'])([^"']+)(["'])/gi,
    (_m, prefix, src, suffix) => `${prefix}${normalizeUploadImageUrl(src)}${suffix}`
  )
}

/** 写入 DB / v-model 前 */
export function normalizeRichTextHtmlForStorage(html) {
  return rewriteHtmlUploadImageUrls(convertUploaderTagsToImages(html))
}

/**
 * Agent 采纳常为纯文本；TipTap 需要块级 HTML，否则编辑器看起来是「空白」。
 */
export function ensureEditorHtmlContent(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  if (!/<[a-z][\s\S]*>/i.test(s)) {
    const esc = s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<p>${esc.replace(/\n/g, '<br>')}</p>`
  }
  return s
}

/** 灌入编辑器前 */
export function prepareRichTextHtmlForEditor(html) {
  return normalizeRichTextHtmlForStorage(ensureEditorHtmlContent(html))
}

/** 上传返回 URL 后立刻预加载，减少 100% 后等待首帧 */
export function preloadUploadImage(url) {
  const src = String(url || '').trim()
  if (!src || src.startsWith('blob:') || src.startsWith('data:')) {
    return Promise.resolve(src)
  }
  return new Promise((resolve) => {
    const img = new Image()
    const done = () => resolve(src)
    img.onload = done
    img.onerror = done
    img.src = src
    fetch(src, { credentials: 'include', cache: 'force-cache' }).catch(() => {})
  })
}

/** @param {unknown} rs 上传接口 JSON */
export function uploadResponseToImageUrl(rs) {
  if (!rs) return ''
  const d = rs.data !== undefined ? rs.data : rs
  if (d && d.success === false) return ''
  const url = d?.url || d?.filelink || d?.fileurl
  if (url) return normalizeUploadImageUrl(String(url).trim())
  if (typeof d === 'string') return normalizeUploadImageUrl(d.trim())
  return ''
}

/**
 * 将 Uploader 节点替换为行内 Image（优先追加到前一段文字末尾）。
 * @param {import('@tiptap/core').Editor | null | undefined} editor
 */
export function convertUploaderNodesToImages(editor) {
  if (!editor?.state?.doc) return false

  const imageType = editor.state.schema.nodes.image
  if (!imageType) return false

  /** @type {{ uploaderPos: number, uploaderSize: number, src: string, inlineAppend: boolean }[]} */
  const jobs = []

  editor.state.doc.descendants((node, pos) => {
    if (node.type.name !== 'Uploader') return

    let src = String(node.attrs?.src || '').trim()
    if (!src || src.startsWith('blob:')) {
      const dom = editor.view.nodeDOM(pos)
      const imgEl = dom?.querySelector?.('.image-wrappe img, img.image, img[src]')
      src = String(imgEl?.getAttribute?.('src') || '').trim()
    }

    src = normalizeUploadImageUrl(src)
    if (!src || src.startsWith('blob:')) return

    const $pos = editor.state.doc.resolve(pos)
    const nodeBefore = $pos.nodeBefore
    const inlineAppend =
      nodeBefore?.type?.name === 'paragraph' &&
      nodeBefore.content.size > 0 &&
      nodeBefore.textContent.trim().length > 0

    jobs.push({
      uploaderPos: pos,
      uploaderSize: node.nodeSize,
      src,
      inlineAppend
    })
  })

  if (!jobs.length) return false

  let tr = editor.state.tr
  for (let i = jobs.length - 1; i >= 0; i--) {
    const { uploaderPos, uploaderSize, src, inlineAppend } = jobs[i]
    const img = imageType.create({
      src,
      class: 'rte-inline-img'
    })

    if (inlineAppend) {
      tr = tr.delete(uploaderPos, uploaderPos + uploaderSize)
      tr = tr.insert(uploaderPos - 1, img)
    } else {
      tr = tr.replaceWith(uploaderPos, uploaderPos + uploaderSize, img)
    }
  }

  editor.view.dispatch(tr)
  return true
}
