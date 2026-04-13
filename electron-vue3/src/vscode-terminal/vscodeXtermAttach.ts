/**
 * 对齐 VS Code `XtermTerminal` 构造后加载顺序：open → Unicode11 → Clipboard → Serialize（实例层）。
 * WebGL 不在此处加载：open 后尚未 fit 时 WebGL 画布尺寸为 0，常见整屏黑、有输入无显示；由 EmbeddedPtyTerminal 在首次 onSyncedDimensions(cols>=2) 后再加载。
 */
import { FitAddon } from '@xterm/addon-fit'
import type { SearchAddon } from '@xterm/addon-search'
import type { SerializeAddon } from '@xterm/addon-serialize'
import type { Terminal } from '@xterm/xterm'
import {
  createVscodeIntegratedXterm,
  vscodeLoadClipboardAddon,
  vscodeLoadSerializeAddon,
  vscodeLoadUnicode11,
  type BuildIntegratedXtermEx
} from './vscodeIntegratedXterm'

export interface MountedVscodeXterm {
  term: Terminal
  fit: FitAddon
  serializeAddon: SerializeAddon | null
  searchAddon: SearchAddon | null
}

/**
 * 在容器上挂载 VS Code 同款 xterm 栈（不含 shellIntegration / decoration 等 Workbench 专用 addon）。
 *
 * SearchAddon / WebGL 不在此处加载：open 后尚未 `fit()` 时 dimensions / WebGL 画布未就绪。
 * 由 EmbeddedPtyTerminal 在首次 onSyncedDimensions(cols>=2) 后再调用 `vscodeLoadSearchAddon` 与 `vscodeLoadWebglIfPossible`。
 */
export async function mountVscodeIntegratedTerminal(
  host: HTMLElement,
  opts?: BuildIntegratedXtermEx
): Promise<MountedVscodeXterm> {
  const term = createVscodeIntegratedXterm(80, 24, opts)
  const fit = new FitAddon()
  term.loadAddon(fit)
  term.open(host)
  await vscodeLoadUnicode11(term)
  await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())))
  await vscodeLoadClipboardAddon(term)
  const serializeAddon = await vscodeLoadSerializeAddon(term)
  return { term, fit, serializeAddon, searchAddon: null }
}
