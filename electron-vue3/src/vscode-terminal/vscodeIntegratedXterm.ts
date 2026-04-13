/**
 * Integrated Terminal — 本文件是「能在 Vue+Vite 里跑起来的抽取层」，不是把 VS Code 整文件粘贴进来。
 *
 * 【体量事实】（以仓库内 third_party 拷贝为准，行数为近似 wc）：
 * - xterm/xtermTerminal.ts ≈ 999 行：`XtermTerminal` 类，其中 **L218–267** 才是 `new xtermCtor({...})` 的配置对象；
 *   其余大量代码是 IConfigurationService / IThemeService / IInstantiationService、配置监听、
 *   DecorationAddon / ShellIntegrationAddon / MarkNavigationAddon / Find / 无障碍 / 遥测 等与 Workbench 绑死的逻辑。
 * - terminalInstance.ts ≈ 2500+ 行：PTY 生命周期、布局、标题、环境变量、链接检测等，同样依赖整套服务注入。
 *
 * 【本仓库里「VS Code 目录」并没有只剩一百行】：`third_party/vscode-src/.../terminal/browser/` 是整树 MIT 拷贝，
 * 仅 **未在构建时 import**（Vite 无法解析其 `../../../../platform/...` 依赖图）。
 *
 * 【本文件在抄什么】：只抄 **不依赖 DI、且对渲染/输入行为有影响** 的部分：
 * - 与 xtermTerminal.ts 构造函数块对齐的 `ITerminalOptions`（见 buildVscodeIntegratedTerminalOptions）；
 * - 与 getXtermTheme 对齐的暗色 ITheme 字面量；
 * - wordSeparators 默认值（terminalConfiguration.ts）；
 * - Unicode11 / WebGL / Clipboard / Serialize / Search addon 的加载路径（实例层常用能力）。
 *
 * 【刻意未搬的内容】：DecorationAddon、ShellIntegrationAddon、ImageAddon、Progress、完整 updateConfig 热更新等，
 * 若要 1:1 只能引入 VS Code 的 instantiation 与 contribution，或自行重写无 DI 版本（工作量是另一个项目）。
 */
import { Terminal, type ITerminalOptions, type ITheme } from '@xterm/xterm'

/** VS Code `terminal.integrated.wordSeparators` default (terminalConfiguration.ts L502). */
export const VSCODE_TERMINAL_WORD_SEPARATORS_DEFAULT =
  " ()[]{}'\",\u2500\u2018\u2019\u201c\u201d|"

/**
 * Dark theme: same keys as `XtermTerminal.getXtermTheme` (xtermTerminal.ts),
 * values = VS Code default dark / ansiColorMap.dark / editor selection.
 */
export function vscodeDarkIntegratedTheme(): ITheme {
  return {
    background: '#1e1e1e',
    foreground: '#cccccc',
    cursor: '#cccccc',
    cursorAccent: '#1e1e1e',
    selectionBackground: '#264f78',
    selectionInactiveBackground: '#3a3d41',
    overviewRulerBorder: '#444444',
    scrollbarSliderActiveBackground: '#5a5d5e80',
    scrollbarSliderBackground: '#79797966',
    scrollbarSliderHoverBackground: '#646464b3',
    black: '#000000',
    red: '#cd3131',
    green: '#0dbc79',
    yellow: '#e5e510',
    blue: '#2472c8',
    magenta: '#bc3fbc',
    cyan: '#11a8cd',
    white: '#e5e5e5',
    brightBlack: '#666666',
    brightRed: '#f14c4c',
    brightGreen: '#23d18b',
    brightYellow: '#f5f543',
    brightBlue: '#3b8eea',
    brightMagenta: '#d670d6',
    brightCyan: '#29b8db',
    brightWhite: '#e5e5e5'
  }
}

/** 本地 ConPTY：构造时打开 win32 输入（方向键/退格删字）；须与二进制 stdin（Electron Uint8Array）配合 */
export type BuildIntegratedXtermEx = { win32InputMode?: boolean }

/**
 * Options object: field-for-field with VS Code `xtermTerminal` ctor (static defaults
 * where VS Code would read settings / services).
 */
export function buildVscodeIntegratedTerminalOptions(
  cols: number,
  rows: number,
  ex?: BuildIntegratedXtermEx
): ITerminalOptions {
  const win32 = !!ex?.win32InputMode
  return {
    allowProposedApi: true,
    cols,
    rows,
    documentOverride: typeof document !== 'undefined' ? document : undefined,
    altClickMovesCursor: true,
    scrollback: 1000,
    theme: vscodeDarkIntegratedTheme(),
    drawBoldTextInBrightColors: true,
    fontFamily: "Consolas, 'Courier New', monospace",
    fontWeight: 'normal',
    fontWeightBold: 'bold',
    fontSize: 14,
    letterSpacing: 0,
    lineHeight: 1,
    logLevel: 'off',
    /** PowerShell 等常发 30m（黑前景）；背景 #1e1e1e 时肉眼即「全黑」。VS Code 默认可读性会拉高对比。 */
    minimumContrastRatio: 4.5,
    tabStopWidth: 8,
    cursorBlink: true,
    blinkIntervalDuration: 600,
    cursorStyle: 'block',
    cursorInactiveStyle: 'outline',
    cursorWidth: 1,
    macOptionIsMeta: true,
    macOptionClickForcesSelection: false,
    rightClickSelectsWord: true,
    fastScrollSensitivity: 5,
    scrollSensitivity: 1,
    scrollOnEraseInDisplay: true,
    wordSeparators: VSCODE_TERMINAL_WORD_SEPARATORS_DEFAULT,
    scrollbar: {
      width: 14,
      overviewRuler: {
        showTopBorder: true
      }
    },
    ignoreBracketedPasteMode: false,
    rescaleOverlappingGlyphs: false,
    vtExtensions: {
      kittyKeyboard: false,
      win32InputMode: win32
    },
    allowTransparency: false,
    windowOptions: {
      getWinSizePixels: true,
      getCellSizePixels: true,
      getWinSizeChars: true
    }
  } as ITerminalOptions
}

export function createVscodeIntegratedXterm(cols = 80, rows = 24, ex?: BuildIntegratedXtermEx): Terminal {
  return new Terminal(buildVscodeIntegratedTerminalOptions(cols, rows, ex))
}

export function isXtermWin32InputMode(term: Terminal | null | undefined): boolean {
  try {
    const ve = (term?.options as { vtExtensions?: { win32InputMode?: boolean } } | undefined)?.vtExtensions
    return !!ve?.win32InputMode
  } catch {
    return false
  }
}

/** 与 VS Code terminalInstance 对齐：ConPTY 下启用 xterm `reflowCursorLine`，列宽变化时重排当前提示符行。 */
export type WindowsPtyWireHint = { backend?: string; build_number?: number }

type XtermWindowsCompatOptions = {
  windowsPty?: { backend: string; buildNumber?: number }
  reflowCursorLine?: boolean
  vtExtensions?: { kittyKeyboard?: boolean; win32InputMode?: boolean }
}

export function applyXtermWindowsConptyCursorReflow(
  term: Terminal | null | undefined,
  wpty: WindowsPtyWireHint | null | undefined
): void {
  if (!term || !wpty || String(wpty.backend || '').toLowerCase() !== 'conpty') return
  const bn = Number(wpty.build_number)
  const opts = term.options as unknown as XtermWindowsCompatOptions
  try {
    opts.windowsPty = Number.isFinite(bn) && bn > 0 ? { backend: 'conpty', buildNumber: Math.floor(bn) } : { backend: 'conpty' }
    opts.reflowCursorLine = true
    // Mac 浏览器连 Windows go-proxy 时构造阶段未开 win32；term_started 后补上，方向键/退格删字依赖此
    opts.vtExtensions = {
      ...(opts.vtExtensions || {}),
      win32InputMode: true
    }
  } catch {
    /* ignore */
  }
}

/**
 * Matches VS Code `attachToElement` GPU path: load WebGL after `open()` when supported.
 */
export async function vscodeLoadWebglIfPossible(term: Terminal): Promise<void> {
  try {
    const { WebglAddon } = await import('@xterm/addon-webgl')
    const addon = new WebglAddon()
    term.loadAddon(addon)
  } catch {
    /* DOM renderer */
  }
}

/** VS Code default `terminal.integrated.unicodeVersion` is `'11'`. */
export async function vscodeLoadUnicode11(term: Terminal): Promise<void> {
  try {
    const { Unicode11Addon } = await import('@xterm/addon-unicode11')
    const addon = new Unicode11Addon()
    term.loadAddon(addon)
    term.unicode.activeVersion = '11'
  } catch {
    /* ignore */
  }
}

type ClipboardSelectionType = 'c' | 'p'

/**
 * 对齐 VS Code `xtermTerminal.ts` 对 ClipboardAddon 的接入（IClipboardService → 浏览器 clipboard）。
 */
export async function vscodeLoadClipboardAddon(term: Terminal): Promise<void> {
  try {
    const { ClipboardAddon } = await import('@xterm/addon-clipboard')
    const handlers = {
      async readText(type: ClipboardSelectionType) {
        const kind = type === 'p' ? 'selection' : 'clipboard'
        try {
          if (kind === 'clipboard' && navigator.clipboard?.readText) {
            return await navigator.clipboard.readText()
          }
        } catch {
          /* ignore */
        }
        return ''
      },
      async writeText(_type: ClipboardSelectionType, text: string) {
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text)
          }
        } catch {
          /* ignore */
        }
      }
    }
    const addon = new ClipboardAddon(undefined, handlers)
    term.loadAddon(addon)
  } catch {
    /* ignore */
  }
}

/** 对齐 VS Code `getSelectionAsHtml` 所用 SerializeAddon（xtermTerminal.ts）。 */
export async function vscodeLoadSerializeAddon(term: Terminal): Promise<import('@xterm/addon-serialize').SerializeAddon | null> {
  try {
    const { SerializeAddon } = await import('@xterm/addon-serialize')
    const addon = new SerializeAddon()
    term.loadAddon(addon)
    return addon
  } catch {
    return null
  }
}

/** 终端内查找高亮（SearchAddon + decorations）。 */
export async function vscodeLoadSearchAddon(term: Terminal): Promise<import('@xterm/addon-search').SearchAddon | null> {
  try {
    const { SearchAddon } = await import('@xterm/addon-search')
    const addon = new SearchAddon({ highlightLimit: 1000 })
    term.loadAddon(addon)
    return addon
  } catch {
    return null
  }
}
