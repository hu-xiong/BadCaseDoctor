/*---------------------------------------------------------------------------------------------
 *  Ported from Microsoft VS Code (MIT):
 *  third_party/vscode-src/workbench/contrib/terminal/browser/terminalTabsList.ts
 *  — TerminalTabsListSizes (TabHeight, list width constants)
 *--------------------------------------------------------------------------------------------*/

/** @see TerminalTabsListSizes in terminalTabsList.ts */
export const TerminalTabsListSizes = {
  TabHeight: 22,
  NarrowViewWidth: 46,
  WideViewMinimumWidth: 80,
  DefaultWidth: 120,
  MidpointViewWidth: (46 + 80) / 2,
  ActionbarMinimumWidth: 105,
  MaximumWidth: 500
} as const

export type TerminalTabsListSizesKey = keyof typeof TerminalTabsListSizes
