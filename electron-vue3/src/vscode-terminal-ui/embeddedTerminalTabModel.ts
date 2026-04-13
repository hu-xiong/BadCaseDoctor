/*---------------------------------------------------------------------------------------------
 *  Tab row + toolbar helpers for EmbeddedTerminalWorkspace (VS Code terminal tab metaphors).
 *--------------------------------------------------------------------------------------------*/

export type EmbeddedTerminalTabKind = 'local' | 'agent'

export interface EmbeddedTerminalTabShape {
  id: string
  kind?: EmbeddedTerminalTabKind
  label?: string
  mode?: string
}

/** @see terminalTabsList / Codicon usage for shell sessions */
export function embeddedTerminalTabCodicon(tab: EmbeddedTerminalTabShape): string {
  if (tab.kind === 'agent') return 'codicon-hubot'
  return 'codicon-terminal'
}
