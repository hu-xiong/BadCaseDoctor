/**
 * 无 Workbench 时的终端编辑动作，语义对齐 VS Code 终端命令（见 terminalActions / terminalMenus）。
 * 使用 xterm 公开 API；粘贴走 `Terminal.paste`，以触发 bracketed paste 与 onData → PTY。
 */
import type { SerializeAddon } from '@xterm/addon-serialize'
import type { Terminal } from '@xterm/xterm'

async function writeClipboardHtmlAndPlain(html: string, plain: string): Promise<void> {
  try {
    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' })
        })
      ])
      return
    }
  } catch {
    /* fall through */
  }
  const listener = (e: ClipboardEvent) => {
    try {
      if (!e.clipboardData) return
      if (!e.clipboardData.types.includes('text/plain')) {
        e.clipboardData.setData('text/plain', plain)
      }
      e.clipboardData.setData('text/html', html)
      e.preventDefault()
    } catch {
      /* ignore */
    }
  }
  document.addEventListener('copy', listener, true)
  try {
    document.execCommand('copy')
  } finally {
    document.removeEventListener('copy', listener, true)
  }
}

export async function integratedTerminalCopySelection(term: Terminal | null | undefined): Promise<void> {
  if (!term?.getSelection) return
  const text = term.getSelection()
  if (!text) return
  try {
    await navigator.clipboard?.writeText?.(text)
  } catch {
    /* ignore */
  }
}

export async function integratedTerminalPasteFromClipboard(term: Terminal | null | undefined): Promise<void> {
  if (!term?.paste) return
  try {
    const text = await navigator.clipboard?.readText?.()
    if (text == null || text === '') return
    term.paste(text)
  } catch {
    /* ignore */
  }
}

export function integratedTerminalSelectAll(term: Terminal | null | undefined): void {
  term?.selectAll?.()
}

/** 对齐 TerminalCommandId.Clear：清空仿真器缓冲（非向 shell 发送 clear/cls）。 */
export function integratedTerminalClearViewport(term: Terminal | null | undefined): void {
  term?.clear?.()
}

/** 对齐 `XtermTerminal.getSelectionAsHtml` + `copySelection(asHtml)`（SerializeAddon）。 */
export async function integratedTerminalCopySelectionAsHtml(
  term: Terminal | null | undefined,
  serializeAddon: SerializeAddon | null | undefined
): Promise<void> {
  if (!term?.getSelection || !serializeAddon?.serializeAsHTML) return
  if (!term.hasSelection?.()) return
  const plain = term.getSelection()
  const html = serializeAddon.serializeAsHTML({ onlySelection: true })
  await writeClipboardHtmlAndPlain(html, plain)
}
