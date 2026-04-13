/**
 * 与 VS Code `MenuId.TerminalInstanceContext` 注册项中的 command id 对齐
 * （见 third_party/vscode-src/.../terminal/browser/terminalMenus.ts）。
 */
export const VSCODE_TERMINAL_INSTANCE_CMD = {
  CopySelection: 'workbench.action.terminal.copySelection',
  CopySelectionAsHtml: 'workbench.action.terminal.copySelectionAsHtml',
  Paste: 'workbench.action.terminal.paste',
  SelectAll: 'workbench.action.terminal.selectAll',
  Clear: 'workbench.action.terminal.clear',
  SizeToContentWidth: 'workbench.action.terminal.sizeToContentWidth',
  FindFocus: 'workbench.action.terminal.focusFind'
} as const
