/**
 * 消费 SSE 下发的 pendingTerminalExecQueue：经本机代理 / Electron 执行，并回写卡片状态。
 */
import {
  createTerminalAgent,
  runTerminalQueueItem
} from '../utils/terminalSubAgent.js'
import {
  getTerminalAutoRunMode,
  canRunUnderTerminalAllowlist
} from '../utils/terminalAutoRunPrefs.js'

/**
 * @param {object} card
 * @returns {string}
 */
export function terminalExecStatusLabelKey(card) {
  const s = String(card?.status || 'queued')
  const map = {
    queued: 'chat.terminalExecQueued',
    running: 'chat.terminalExecRunning',
    done: 'chat.terminalExecDone',
    error: 'chat.terminalExecError',
    cancelled: 'chat.terminalExecCancelled',
    proxy_down: 'chat.terminalExecProxyDown',
    skipped: 'chat.terminalExecSkipped'
  }
  return map[s] || 'chat.terminalExecQueued'
}

/**
 * 流结束后是否应对该命令自动执行（否则仅展示卡片，等用户点「执行」）。
 * @param {string} command
 * @param {{ forceAsk?: boolean }} [opts]
 */
export function shouldAutoRunTerminalCommand(command, opts = {}) {
  if (opts.forceAsk) return false
  const mode = getTerminalAutoRunMode()
  if (mode === 'everything') return true
  if (mode === 'allowlist') return canRunUnderTerminalAllowlist(command)
  return false
}

/**
 * @param {object} aiMessage
 * @param {number} cardIndex
 * @param {Partial<{ status: string, resultText: string, exitCode: number }>} patch
 */
export function patchTerminalExecCard(aiMessage, cardIndex, patch) {
  const cards = aiMessage?.clientTerminalExecCards
  if (!Array.isArray(cards) || cardIndex < 0 || cardIndex >= cards.length) return
  const cur = cards[cardIndex] || {}
  cards[cardIndex] = { ...cur, ...patch }
}

/**
 * 执行单条卡片（手动点「执行」或队列项）。
 * @param {object} aiMessage
 * @param {number} cardIndex
 * @param {{
 *   localProxyOkRef?: { value?: boolean } | (() => boolean),
 *   abortSignal?: AbortSignal,
 *   confirmFn?: (msg: string) => boolean,
 *   onAfter?: () => void
 * }} [opts]
 */
export async function runOneTerminalExecCard(aiMessage, cardIndex, opts = {}) {
  const cards = aiMessage?.clientTerminalExecCards
  if (!Array.isArray(cards) || !cards[cardIndex]) return null
  const card = cards[cardIndex]
  if (card.status === 'running' || card.status === 'done') return null

  const agent = createTerminalAgent(opts.localProxyOkRef)
  patchTerminalExecCard(aiMessage, cardIndex, { status: 'running', resultText: '' })
  opts.onAfter?.()

  const outcome = await runTerminalQueueItem(
    agent,
    {
      command: card.command,
      cwd: card.cwd,
      timeout: card.timeout,
      stop_on_error: card.stop_on_error
    },
    { confirmFn: opts.confirmFn, abortSignal: opts.abortSignal }
  )

  if (!outcome) {
    patchTerminalExecCard(aiMessage, cardIndex, { status: 'skipped' })
    opts.onAfter?.()
    return null
  }

  let status = 'done'
  if (outcome.cancelled) status = 'cancelled'
  else if (outcome.proxyDown) status = 'proxy_down'
  else if (!outcome.ok) status = 'error'

  patchTerminalExecCard(aiMessage, cardIndex, {
    status,
    resultText: outcome.text || '',
    ok: outcome.ok
  })
  opts.onAfter?.()
  return outcome
}

/**
 * 消费 pending 队列（与卡片按下标对齐），按 Auto-Run 策略决定是否自动跑。
 * @param {object} aiMessage
 * @param {{
 *   localProxyOkRef?: { value?: boolean } | (() => boolean),
 *   abortSignal?: AbortSignal,
 *   confirmFn?: (msg: string) => boolean,
 *   askConfirmAuto?: (cmd: string) => boolean,
 *   t?: (key: string, params?: object) => string,
 *   onAfter?: () => void
 * }} [opts]
 * @returns {Promise<{ ran: boolean, followUpText: string }>}
 */
export async function flushPendingTerminalExecQueue(aiMessage, opts = {}) {
  const queue = Array.isArray(aiMessage?.pendingTerminalExecQueue)
    ? aiMessage.pendingTerminalExecQueue
    : []
  if (!queue.length) {
    return { ran: false, followUpText: '' }
  }

  const cards = Array.isArray(aiMessage.clientTerminalExecCards)
    ? aiMessage.clientTerminalExecCards
    : []
  const results = []
  let ranAny = false
  let stopRest = false

  for (let i = 0; i < queue.length; i++) {
    if (opts.abortSignal?.aborted) break
    const item = queue[i]
    const cardIndex = cards.findIndex(
      (c) =>
        c &&
        c.status === 'queued' &&
        String(c.command || '') === String(item.command || '') &&
        String(c.cwd || '') === String(item.cwd || '')
    )
    const idx = cardIndex >= 0 ? cardIndex : i

    if (stopRest) {
      patchTerminalExecCard(aiMessage, idx, { status: 'skipped' })
      opts.onAfter?.()
      continue
    }

    const cmd = String(item.command || '').trim()
    let auto = shouldAutoRunTerminalCommand(cmd)
    if (!auto && typeof opts.askConfirmAuto === 'function') {
      auto = !!opts.askConfirmAuto(cmd)
    } else if (!auto && getTerminalAutoRunMode() === 'ask') {
      // ask：留在 queued，等用户点卡片「执行」
      continue
    } else if (!auto && getTerminalAutoRunMode() === 'allowlist') {
      // 白名单未命中：询问一次
      const msg =
        typeof opts.t === 'function'
          ? opts.t('chat.terminalExecConfirmRun', { cmd: cmd.slice(0, 500) })
          : `是否执行？\n\n${cmd.slice(0, 500)}`
      const ok =
        typeof opts.confirmFn === 'function'
          ? opts.confirmFn(msg)
          : typeof window !== 'undefined' && window.confirm(msg)
      if (!ok) {
        patchTerminalExecCard(aiMessage, idx, { status: 'skipped' })
        opts.onAfter?.()
        continue
      }
      auto = true
    }

    if (!auto) continue

    const outcome = await runOneTerminalExecCard(aiMessage, idx, opts)
    // 从 pending 去掉已处理项（按引用）
    const qPos = aiMessage.pendingTerminalExecQueue.indexOf(item)
    if (qPos >= 0) aiMessage.pendingTerminalExecQueue.splice(qPos, 1)

    if (outcome) {
      ranAny = true
      results.push(outcome.text)
      if (item.stop_on_error === true && !outcome.ok) {
        stopRest = true
      }
    }
  }

  // 清空已处理完的排队引用（仍 queued 的保留，对应未自动跑的卡片）
  if (Array.isArray(aiMessage.pendingTerminalExecQueue)) {
    const stillQueuedCmds = new Set(
      (aiMessage.clientTerminalExecCards || [])
        .filter((c) => c && c.status === 'queued')
        .map((c) => `${c.command}\0${c.cwd || ''}`)
    )
    aiMessage.pendingTerminalExecQueue = aiMessage.pendingTerminalExecQueue.filter((it) =>
      stillQueuedCmds.has(`${it.command}\0${it.cwd || ''}`)
    )
  }

  const followUpText = results.length
    ? `【本机终端执行结果】\n\n${results.join('\n\n---\n\n')}`
    : ''

  return { ran: ranAny, followUpText }
}
