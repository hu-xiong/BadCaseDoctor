/*---------------------------------------------------------------------------------------------
 *  Dark theme CSS variables — values aligned with VS Code default dark / panel terminal.
 *  Keys mirror workbench color ids used in:
 *  third_party/vscode-src/workbench/contrib/terminal/browser/media/terminal.css
 *--------------------------------------------------------------------------------------------*/

/** Inline style object for :root / container (Vue `:style` binding). */
export function integratedTerminalWorkbenchDarkVars(): Record<string, string> {
  return {
    '--vscode-panel-background': '#181818',
    '--vscode-panel-border': '#2b2b2b',
    '--vscode-panelTitle-background': '#252526',
    '--vscode-sideBar-background': '#252526',
    '--vscode-sideBarTitle-background': '#252526',
    '--vscode-terminal-background': '#181818',
    '--vscode-terminal-border': '#2b2b2b',
    '--vscode-terminal-tab-activeBorder': '#007fd4',
    '--vscode-terminal-dropBackground': 'rgba(83, 89, 93, 0.25)',
    '--vscode-list-activeSelectionBackground': '#094771',
    '--vscode-list-activeSelectionForeground': '#ffffff',
    '--vscode-list-hoverBackground': '#2a2d2e',
    '--vscode-list-inactiveSelectionBackground': '#37373d',
    '--vscode-list-dropBackground': 'rgba(83, 89, 93, 0.35)',
    '--vscode-toolbar-hoverBackground': 'rgba(255, 255, 255, 0.1)',
    '--vscode-icon-foreground': '#c5c5c5',
    '--vscode-menu-background': '#252526',
    '--vscode-menu-foreground': '#cccccc',
    '--vscode-menu-border': '#3c3c3c',
    '--vscode-widget-border': '#3c3c3c',
    '--vscode-focusBorder': '#007fd4'
  }
}
