/**
 * ReAct SSE：`lane=engine` 映射后的 legacy stepEvent（非 THINK 流）统一写入 aiMessage。
 * THINK 类仍由 `applyReactThinkSSEStepEvent` 处理。
 */
import {
  mergeMessageThinkDraftsIntoReactStepZero,
  maybeRevealPlanMemoAfterThink
} from './applyReactThinkSSEStepEvent.js'
import { mergeBuiltStepsPreservingPlaceholderThinkClock } from './agentReactV1Ui.js'
import {
  applyReactObservationLegacyStepEvent,
  ensureReactStepsForStreamIndex
} from './reactObservationStream.js'
import { i18n } from '../i18n/index.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'

const toolExecutingLabel = () => i18n.global.t('chat.toolExecuting')

/** @returns {{ breakChunkLoop?: boolean }} */
export function applyReactEngineLaneLegacyStepEvent(aiMessage, stepEvent, ctx) {
  const flushReasoningTypewriter = ctx.flushReasoningTypewriter
  const cancelTodosStreamTypewriter = ctx.cancelTodosStreamTypewriter
  const buildReactStepsFromTodoStrings = ctx.buildReactStepsFromTodoStrings
  const resolveStreamStepIndex = ctx.resolveStreamStepIndex
  const appendStepDetailLine = ctx.appendStepDetailLine
  const scrollAgentStepLogIntoView = ctx.scrollAgentStepLogIntoView
  const handleShowGroupInList = ctx.handleShowGroupInList
  const projectId = ctx.projectId
  const handleNavigation = ctx.handleNavigation
  const nextTick = ctx.nextTick

  if (stepEvent.event === 'immutable_field_rejection') {
    flushReasoningTypewriter(aiMessage)
    const msg =
      stepEvent.message ||
      '该字段不可修改。可修改的字段包括：状态、期望结果、标题、优先级、复现步骤、负责人等。'
    aiMessage.agentResult.findings = [msg]
    aiMessage.finalResponse = `⚠️ ${msg}`
    aiMessage.agentResult.status = 'success'
    aiMessage.steps.forEach((s) => {
      s.status = 'skipped'
      s.description = '已跳过（该字段不可修改）'
    })
    return {}
  }
  if (stepEvent.event === 'intent_clarification') {
    flushReasoningTypewriter(aiMessage)
    const msg = stepEvent.message || '请说明是要修改已有记录，还是要新建一条。'
    const kind = stepEvent.kind || ''
    // step_failed：保留已渲染的 steps（思考/工具/观察），仅追加提示；勿与 llm_chat_only 一样整段清空
    if (kind === 'step_failed') {
      aiMessage.reactDirectChatReply = false
      const findings = Array.isArray(aiMessage.agentResult?.findings) ? aiMessage.agentResult.findings : []
      if (msg && !findings.includes(msg)) {
        if (!aiMessage.agentResult) aiMessage.agentResult = { findings: [], status: 'success' }
        aiMessage.agentResult.findings = [...findings, msg]
      }
      return {}
    }
    // 拆掉 hello/phase 挂的占位 step，避免出现无正文的 Thought +「本步未收到 Agent 行动说明」
    aiMessage.steps = []
    aiMessage._placeholderSteps = false
    aiMessage.reactPlanPanelSuppressed = false
    aiMessage.understanding = ''
    if (kind === 'llm_chat_only') {
      aiMessage.reactDirectChatReply = true
      aiMessage.agentResult.findings = []
      aiMessage.agentResult.status = 'success'
      aiMessage.finalResponse = ''
      aiMessage.hadAgentThinkPhase = false
      aiMessage._reasoningPhaseLive = false
      aiMessage.reasoningContent = ''
      aiMessage.thinkReasoningDraft = ''
      aiMessage.thinkContentDraft = ''
      aiMessage.todosStreamDraft = ''
      aiMessage.todosStreamVisible = ''
    } else {
      aiMessage.reactDirectChatReply = false
      aiMessage.agentResult.findings = [msg]
      aiMessage.finalResponse = kind === 'low_signal' ? msg : `💬 ${msg}`
      aiMessage.agentResult.status = 'success'
    }
    return {}
  }
  if (stepEvent.event === 'unified_summary_loading') {
    aiMessage.unifiedSummaryLoading = stepEvent.active === true
    return {}
  }
  if (stepEvent.event === 'direct_reply_prepare') {
    if (stepEvent.active === true) {
      aiMessage.reactDirectChatReply = true
      aiMessage.finalResponse = ''
      aiMessage.summaryStreamDraft = ''
    }
    return {}
  }
  if (stepEvent.event === 'summary_stream') {
    const piece = stepEvent.delta
    if (typeof piece === 'string' && piece) {
      aiMessage.unifiedSummaryLoading = false
      if (aiMessage.reactDirectChatReply) {
        aiMessage.finalResponse = (aiMessage.finalResponse || '') + piece
      } else {
        aiMessage.summaryStreamDraft = (aiMessage.summaryStreamDraft || '') + piece
      }
    }
    return {}
  }
  if (stepEvent.event === 'summary_stream_reset') {
    aiMessage.summaryStreamDraft = ''
    return {}
  }
  if (stepEvent.event === 'running_summary_stream') {
    const piece = stepEvent.delta
    if (typeof piece === 'string' && piece) {
      aiMessage.unifiedSummaryLoading = false
      aiMessage.runningSummaryDraft = (aiMessage.runningSummaryDraft || '') + piece
    }
    if (stepEvent.version != null) aiMessage.runningSummaryVersion = stepEvent.version
    return {}
  }
  if (stepEvent.event === 'running_summary_stream_reset') {
    aiMessage.runningSummaryDraft = ''
    if (stepEvent.version != null) aiMessage.runningSummaryVersion = stepEvent.version
    return {}
  }
  if (stepEvent.event === 'running_summary_done') {
    aiMessage.unifiedSummaryLoading = false
    if (stepEvent.version != null) aiMessage.runningSummaryVersion = stepEvent.version
    // 后端在切片重放后附带全文；仅靠 stream delta 可能丢尾包或中断，必须以 full_text 收口
    const ft =
      typeof stepEvent.full_text === 'string'
        ? stepEvent.full_text.trim()
        : ''
    if (ft) {
      aiMessage.runningSummaryDraft = ft
    }
    return {}
  }
  if (stepEvent.event === 'llm_text_stream') {
    const piece = stepEvent.delta
    const _li = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    if (typeof piece === 'string' && piece && _li != null) {
      const st = aiMessage.steps[_li]
      if (st) {
        st.llmDraft = (st.llmDraft || '') + piece
      }
    }
    return {}
  }
  if (stepEvent.event === 'react_ui_stream') {
    const piece = stepEvent.delta
    const _ri = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    if (typeof piece === 'string' && piece && _ri != null) {
      const st = aiMessage.steps[_ri]
      if (st) {
        if (stepEvent.channel === 'params') {
          st.paramsSummaryDraft = (st.paramsSummaryDraft || '') + piece
        } else {
          st.llmDraft = (st.llmDraft || '') + piece
        }
      }
    }
    return {}
  }
  if (stepEvent.event === 'todos_partial') {
    console.log('[CHAT-STREAM] 收到 todos_partial:', stepEvent.data)
    flushReasoningTypewriter(aiMessage)
    cancelTodosStreamTypewriter(aiMessage)
    aiMessage.todosStreamDraft = ''
    aiMessage.todosStreamVisible = ''
    const _td = stepEvent.data
    const hadPh = !!aiMessage._placeholderSteps
    const prevSteps = aiMessage.steps
    const built = buildReactStepsFromTodoStrings(stepEvent.data || [])
    if (aiMessage._terminalMergeContinue && Array.isArray(prevSteps) && prevSteps.length > 0) {
      aiMessage.reactPlanSteps = [
        ...(Array.isArray(aiMessage.reactPlanSteps) ? aiMessage.reactPlanSteps : []),
        ...(Array.isArray(_td) ? _td : [])
      ]
      aiMessage.steps = [...prevSteps, ...built]
      mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps, aiMessage.steps, hadPh)
    } else {
      aiMessage.reactPlanSteps = Array.isArray(_td) ? [..._td] : []
      aiMessage.steps = built
      mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps, aiMessage.steps, hadPh)
    }
    mergeMessageThinkDraftsIntoReactStepZero(aiMessage)
    maybeRevealPlanMemoAfterThink(aiMessage)
    if (!aiMessage._planMemoRevealReady && !aiMessage._deferPlanMemoUntilThink) {
      aiMessage._planMemoRevealReady = true
    }
    aiMessage.thoughtCollapsed = true
    return {}
  }
  if (stepEvent.event === 'todos') {
    console.log('[CHAT-STREAM] 收到 todos 数据:', stepEvent.data)
    flushReasoningTypewriter(aiMessage)
    cancelTodosStreamTypewriter(aiMessage)
    aiMessage.todosStreamDraft = ''
    aiMessage.todosStreamVisible = ''
    const _td2 = stepEvent.data
    const hadPh2 = !!aiMessage._placeholderSteps
    const prevSteps2 = aiMessage.steps
    const built2 = buildReactStepsFromTodoStrings(stepEvent.data || [])
    if (aiMessage._terminalMergeContinue && Array.isArray(prevSteps2) && prevSteps2.length > 0) {
      aiMessage.reactPlanSteps = [
        ...(Array.isArray(aiMessage.reactPlanSteps) ? aiMessage.reactPlanSteps : []),
        ...(Array.isArray(_td2) ? _td2 : [])
      ]
      aiMessage.steps = [...prevSteps2, ...built2]
      mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps2, aiMessage.steps, hadPh2)
    } else {
      aiMessage.reactPlanSteps = Array.isArray(_td2) ? [..._td2] : []
      aiMessage.steps = built2
      mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps2, aiMessage.steps, hadPh2)
    }
    mergeMessageThinkDraftsIntoReactStepZero(aiMessage)
    maybeRevealPlanMemoAfterThink(aiMessage)
    if (!aiMessage._planMemoRevealReady && !aiMessage._deferPlanMemoUntilThink) {
      aiMessage._planMemoRevealReady = true
    }
    console.log('[CHAT-STREAM] 处理后的 steps:', aiMessage.steps)
    aiMessage.thoughtCollapsed = true
    return {}
  }
  if (stepEvent.event === 'step_status') {
    const _ssi = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    const st = _ssi != null ? aiMessage.steps[_ssi] : null
    if (st && stepEvent.status) {
      if (stepEvent.status === 'running') st.status = 'running'
      else if (stepEvent.status === 'failed') {
        freezeThoughtSnapshotForStep(st)
        st.status = 'failed'
        st.description = st.description || '未成功'
      } else if (stepEvent.status === 'done') {
        freezeThoughtSnapshotForStep(st)
        st.status = 'completed'
      } else if (stepEvent.status === 'pending') st.status = 'pending'
    }
    return {}
  }
  if (stepEvent.event === 'todo_start') {
    const _ix = stepEvent.index
    const _base = Number(aiMessage._reactStreamStepBase || 0)
    const _absIx =
      _ix != null && Number.isFinite(Number(_ix)) ? _base + Number(_ix) : null
    if (stepEvent.react_phase) {
      aiMessage.lastReactPhase = stepEvent.react_phase
    }
    // 统一流每轮 think 前会发 todo_skip:true，仅为索引对齐；勿揭 AgentTaskRun、勿写「── 开始 ──」，否则无工具也出「步骤 1」
    const thinkOnlyTodoStart = stepEvent.todo_skip === true
    if (!thinkOnlyTodoStart) {
      aiMessage._placeholderSteps = false
    }
    ensureReactStepsForStreamIndex(aiMessage, _ix, buildReactStepsFromTodoStrings)
    // 规划备忘扩行：显式 todo_skip / expand_plan 优先于仅看 planned（与统一流引擎约定对齐）
    const skipMemo =
      stepEvent.todo_skip === true ||
      stepEvent.expand_plan === false ||
      stepEvent.planned === false
    const expandMemo = !skipMemo
    if (
      aiMessage.steps &&
      _absIx != null &&
      Number.isFinite(_absIx) &&
      _absIx >= aiMessage.steps.length &&
      expandMemo
    ) {
      const todoText = (typeof stepEvent.todo === 'string' && stepEvent.todo) || '（动态步骤）'
      const pad = _absIx + 1 - aiMessage.steps.length
      for (let pi = 0; pi < pad; pi++) {
        const row = buildReactStepsFromTodoStrings([todoText])[0]
        aiMessage.steps.push(row)
      }
    }
    const _tsi = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    const st = _tsi != null ? aiMessage.steps[_tsi] : null
    if (st) {
      st.status = 'running'
      if (st.stepStartedAt == null) {
        st.stepStartedAt = Date.now()
      }
      // 勿清空 thoughtPhaseEndAtMs：THINK/XML 尾已冻结眉标，清空会让秒数在工具阶段继续跟墙钟涨
      st.phaseWait = null
      if (!thinkOnlyTodoStart) {
        appendStepDetailLine(st, `── 开始 ──`)
      }
    }
    scrollAgentStepLogIntoView(aiMessage.id, _tsi)
    return {}
  }
  if (stepEvent.event === 'step_log') {
    const _sli = resolveStreamStepIndex(stepEvent.stepIndex ?? stepEvent.index, aiMessage.steps)
    let st = _sli != null ? aiMessage.steps[_sli] : null
    if (!st) {
      st =
        aiMessage.steps.find((s) => s.status === 'running') ||
        aiMessage.steps[aiMessage.steps.length - 1]
    }
    if (!st) return { breakChunkLoop: true }
    if (stepEvent.type === 'start') {
      st.status = 'running'
      if (st.stepStartedAt == null) {
        st.stepStartedAt = Date.now()
      }
      if (stepEvent.params) st.inputParams = stepEvent.params
      appendStepDetailLine(st, `── 开始：${stepEvent.title || ''} ──`.trim())
    } else if (stepEvent.type === 'output' && stepEvent.content) {
      appendStepDetailLine(st, stepEvent.content)
    } else if (stepEvent.type === 'end') {
      if (stepEvent.duration != null) st.stepDurationMs = Math.round(Number(stepEvent.duration) * 1000)
      if (stepEvent.result) {
        try {
          st.resultSummary =
            typeof stepEvent.result === 'string'
              ? stepEvent.result
              : JSON.stringify(stepEvent.result)
        } catch {
          st.resultSummary = '步骤结束'
        }
      }
      freezeThoughtSnapshotForStep(st)
      st.status = 'completed'
    }
    return {}
  }
  if (stepEvent.event === 'batch_preview_row') {
    aiMessage._placeholderSteps = false
    ensureReactStepsForStreamIndex(aiMessage, stepEvent.index, buildReactStepsFromTodoStrings)
    const _bpi = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    let runningStep =
      _bpi != null ? aiMessage.steps[_bpi] : aiMessage.steps.find((s) => s.status === 'running')
    if (runningStep) {
      if (runningStep.phaseWait) runningStep.phaseWait = null
      const row = stepEvent.row && typeof stepEvent.row === 'object' ? stepEvent.row : {}
      if (!runningStep.batchPreviewRows) runningStep.batchPreviewRows = []
      runningStep.batchPreviewRows = [...runningStep.batchPreviewRows, row]
      const n1 = row.index != null ? Number(row.index) + 1 : ''
      const n2 = row.total != null ? Number(row.total) : ''
      const head = n1 && n2 ? `预览 ${n1}/${n2}` : '预览'
      const line = `${head} · #${row.target_id ?? ''} ${row.record_title != null ? String(row.record_title) : ''}`.trim()
      if (!runningStep.progressLog) runningStep.progressLog = []
      runningStep.progressLog.push(line)
      if (runningStep.progressLog.length > 40) runningStep.progressLog.shift()
      runningStep.progressLog = [...runningStep.progressLog]
      appendStepDetailLine(runningStep, line)
    }
    return {}
  }
  if (stepEvent.event === 'tool_error') {
    ensureReactStepsForStreamIndex(aiMessage, stepEvent.index, buildReactStepsFromTodoStrings)
    const _ei = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    let st =
      _ei != null ? aiMessage.steps[_ei] : aiMessage.steps.find((s) => s.status === 'running')
    const msg = (stepEvent.message && String(stepEvent.message).trim()) || '工具执行失败'
    if (st) {
      if (st.phaseWait) st.phaseWait = null
      appendStepDetailLine(st, `❌ ${msg}`)
      st.status = 'failed'
      st.description = msg.slice(0, 200)
    }
    return {}
  }
  if (stepEvent.event === 'executing') {
    aiMessage._placeholderSteps = false
    ensureReactStepsForStreamIndex(aiMessage, stepEvent.index, buildReactStepsFromTodoStrings)
    const _exi = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    let runningStep =
      _exi != null ? aiMessage.steps[_exi] : aiMessage.steps.find((s) => s.status === 'running')
    if (runningStep) {
      // 进入 executing 代表已离开等待阶段，避免 Thought 区残留“加载中”三点
      if (runningStep.phaseWait) runningStep.phaseWait = null
      if (runningStep.thoughtPhaseEndAtMs == null) {
        runningStep.thoughtPhaseEndAtMs = Date.now()
      }
      if (!runningStep.progressLog) runningStep.progressLog = []
      if (!runningStep.inputParams && (stepEvent.params || stepEvent.tool || stepEvent.reason)) {
        runningStep.inputParams = {
          tool: stepEvent.tool,
          reason: stepEvent.reason,
          ...(stepEvent.params && typeof stepEvent.params === 'object' ? stepEvent.params : {})
        }
      }
      if (stepEvent.message) {
        runningStep.description = stepEvent.message
        runningStep.progressLog.push(stepEvent.message)
        if (runningStep.progressLog.length > 25) runningStep.progressLog.shift()
        runningStep.progressLog = [...runningStep.progressLog]
        appendStepDetailLine(runningStep, stepEvent.message)
      }
      if (stepEvent.tool === 'create' && stepEvent.params && typeof stepEvent.params === 'object') {
        const p = stepEvent.params
        const pid = p.project_id
        const fld = p.fields
        const fldKeys = fld && typeof fld === 'object' && !Array.isArray(fld) ? Object.keys(fld) : []
        const emptyObj = Boolean(fld && typeof fld === 'object' && !Array.isArray(fld) && fldKeys.length === 0)
        console.info('[CREATE][executing] 入参诊断（对照后端 [CREATE] 校验失败 日志）', {
          project_id: pid,
          project_id_missing: pid == null || pid === '',
          fields_key_count: fldKeys.length,
          fields_keys: fldKeys.slice(0, 24),
          fields_is_empty_object: emptyObj,
          has_natural_query: !!(p.natural_query && String(p.natural_query).trim()),
          target: p.target
        })
      }
      if (stepEvent.tool === 'modify' && Array.isArray(stepEvent.fields) && stepEvent.fields.length > 0) {
        const fieldText = stepEvent.fields.join('、')
        if (!stepEvent.message) runningStep.description = `正在执行: modify（字段：${fieldText}）`
        runningStep.toolCall = { name: `modify: ${fieldText}`, output: toolExecutingLabel() }
      } else {
        const t = stepEvent.tool || '工具'
        if (!stepEvent.message) runningStep.description = `正在执行: ${t}`
        runningStep.toolCall = { name: t, output: toolExecutingLabel() }
      }
    }
    return {}
  }
  if (stepEvent.event === 'observation') {
    aiMessage._placeholderSteps = false
    applyReactObservationLegacyStepEvent(aiMessage, stepEvent, {
      resolveStreamStepIndex,
      appendStepDetailLine,
      nextTick,
      handleShowGroupInList,
      projectId,
      handleNavigation,
      buildReactStepsFromTodoStrings
    })
    return {}
  }
  if (stepEvent.event === 'evidence') {
    console.log('[CHAT-STREAM] 收到 evidence 数据:', stepEvent.data, typeof stepEvent.data)
    if (stepEvent.data) {
      let evidenceData = stepEvent.data
      if (typeof evidenceData === 'string') {
        try {
          let cleanData = evidenceData.replace(/^[✅❌⏳🔧]\s*/, '')
          cleanData = cleanData
            .replace(/'/g, '"')
            .replace(/None/g, 'null')
            .replace(/True/g, 'true')
            .replace(/False/g, 'false')
          evidenceData = JSON.parse(cleanData)
          console.log('[CHAT-STREAM] 解析后的 evidence:', evidenceData)
        } catch (e) {
          console.error('[CHAT-STREAM] evidence 解析失败:', e, evidenceData)
          evidenceData = {
            tool_used: '未知工具',
            status: 'completed',
            raw_data: evidenceData
          }
        }
      }
      aiMessage.evidences.push({
        tool: evidenceData.tool_used,
        data: evidenceData
      })
    }
    return {}
  }
  if (stepEvent.event === 'finding') {
    if (aiMessage.agentResult && !aiMessage.agentResult.findings.includes(stepEvent.data)) {
      aiMessage.agentResult.findings.push(stepEvent.data)
    }
    return {}
  }
  if (stepEvent.event === 'todo_end') {
    const _tei = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
    if (_tei != null) {
      const st = aiMessage.steps[_tei]
      freezeThoughtSnapshotForStep(st)
      if (st.status !== 'failed' && st.status !== 'error') {
        st.status = 'completed'
        st.description = '已完成'
      }
      if (st.stepDurationMs == null && st.stepStartedAt != null) {
        st.stepDurationMs = Date.now() - st.stepStartedAt
      }
    }
    return {}
  }
  if (stepEvent.event === 'skip') {
    const runningStep = aiMessage.steps.find((s) => s.status === 'running')
    if (runningStep) {
      runningStep.status = 'skipped'
      runningStep.description = '已跳过'
    }
    return {}
  }
  if (stepEvent.event === 'finished') {
    aiMessage.reactMainLoopFinished = true
    if (aiMessage.understanding === '...') {
      aiMessage.understanding = ''
    }
    return {}
  }
  if (stepEvent.event === 'done') {
    applyReactDoneLegacyStepEvent(aiMessage, stepEvent, flushReasoningTypewriter)
    return {}
  }
  if (stepEvent.event === 'error') {
    aiMessage.finalResponse = `❌ 错误: ${stepEvent.message}`
    aiMessage.agentResult.status = 'failed'
    return {}
  }
  return {}
}

function formatObjectToSummary(obj) {
  if (!obj || typeof obj !== 'object') return ''

  if (obj.plan_tree) {
    const planCount = obj.plan_tree.total_plans || 0
    const rootCount = obj.plan_tree.root_plans?.length || 0
    return `📋 解析计划树：共 ${planCount} 个计划，${rootCount} 个根计划`
  }

  if (obj.badcase_analysis && Array.isArray(obj.badcase_analysis)) {
    const count = obj.badcase_analysis.length
    const keywords = obj.badcase_analysis[0]?.extracted_keywords?.join(', ') || ''
    return `🔍 定位 ${count} 条BadCase${keywords ? `（关键词：${keywords}）` : ''}`
  }

  if (obj.bug_location && Array.isArray(obj.bug_location)) {
    const count = obj.bug_location.length
    return `🐛 定位Bug：${count} 条`
  }

  if (obj.plan_attribution && Array.isArray(obj.plan_attribution)) {
    const count = obj.plan_attribution.length
    return `🎯 计划归属分析：${count} 条建议`
  }

  if (obj.comparison_report) {
    return `📊 生成对比报告`
  }

  if (obj.bugs && Array.isArray(obj.bugs)) {
    const count = obj.bugs.length
    const priorities = obj.bugs.reduce((acc, bug) => {
      acc[bug.priority] = (acc[bug.priority] || 0) + 1
      return acc
    }, {})
    const priorityStr = Object.entries(priorities)
      .map(([p, c]) => `${p}优先级${c}条`)
      .join('、')
    return `🐛 查询到 ${count} 个Bug（${priorityStr}）`
  }

  if (obj.summary && typeof obj.summary === 'string') {
    return obj.summary
  }

  const keys = Object.keys(obj)
  if (keys.length > 0) {
    return `📝 包含字段：${keys.slice(0, 3).join('、')}${keys.length > 3 ? '等' : ''}`
  }

  return ''
}

function applyReactDoneLegacyStepEvent(aiMessage, stepEvent, flushReasoningTypewriter) {
  flushReasoningTypewriter(aiMessage)
  aiMessage.unifiedSummaryLoading = false

  const stepsCountResolved =
    stepEvent.steps_count != null && stepEvent.steps_count !== ''
      ? Number(stepEvent.steps_count)
      : null
  const findingsFromEvent = Array.isArray(stepEvent.findings) ? stepEvent.findings : []
  const noFindingsOnDone = findingsFromEvent.length === 0
  /** 统一流 todo_start 会留「步骤 1 + ──开始──」，但无真实工具步：与 direct_reply 同样拆掉步骤壳 */
  const collapseNoToolShell =
    stepEvent.status !== 'error' &&
    (stepEvent.direct_reply === true ||
      (stepsCountResolved === 0 && noFindingsOnDone))

  if (collapseNoToolShell) {
    aiMessage.reactDirectChatReply = true
    aiMessage.runningSummaryDraft = ''
    aiMessage.agentResult.status = 'success'
    // 勿写 execution_time：否则 hasUnifiedSummary 为真，刷新前也会进「总结」壳；耗时对纯对话无意义
    aiMessage.agentResult.execution_time = null
    aiMessage.agentResult.steps_count = 0
    if (stepEvent.thinking_time != null && stepEvent.thinking_time >= 0) {
      aiMessage.agentResult.thinking_time = stepEvent.thinking_time
    } else {
      aiMessage.agentResult.thinking_time = null
    }
    aiMessage.agentResult.findings = []
    aiMessage.agentResult.summaryText = ''
    const streamed = String(aiMessage.finalResponse || '').trim()
    const summary =
      typeof stepEvent.summary === 'string' ? String(stepEvent.summary).trim() : ''
    aiMessage.finalResponse = streamed || summary
    aiMessage.summaryStreamDraft = ''
    aiMessage.thoughtCollapsed = true
    aiMessage.understanding = ''
    aiMessage.steps = []
    aiMessage._placeholderSteps = false
    return
  }

  const _doneSt = stepEvent.status
  aiMessage.agentResult.status =
    _doneSt === 'error'
      ? 'error'
      : _doneSt === 'cancelled'
        ? 'cancelled'
        : _doneSt === 'partial'
          ? 'partial'
          : 'success'
  aiMessage.agentResult.execution_time = stepEvent.duration
  aiMessage.agentResult.steps_count = stepEvent.steps_count || 0
  if (stepEvent.thinking_time != null && stepEvent.thinking_time >= 0) {
    aiMessage.agentResult.thinking_time = stepEvent.thinking_time
  }
  if (stepEvent.summary && typeof stepEvent.summary === 'string') {
    aiMessage.agentResult.summaryText = stepEvent.summary.trim()
  }
  // 勿在 done 时清空 summaryStreamDraft / runningSummaryDraft：
  // 统一总结与增量运行总览已靠 SSE 流式拼字，清空会导致界面立刻改以 summaryText 整块重绘，观感「一下子出来」。
  // getUnifiedSummaryBody 仍优先草稿；summaryText 已写入 agentResult 供落库与刷新后展示。
  aiMessage.thoughtCollapsed = true

  aiMessage.steps.forEach((step) => {
    if (step.status === 'failed' || step.status === 'error') return
    if (step.status !== 'completed') {
      freezeThoughtSnapshotForStep(step)
      step.status = 'completed'
      step.description = '已完成'
    }
  })

  const allFindings =
    stepEvent.findings && stepEvent.findings.length > 0
      ? stepEvent.findings
      : aiMessage.agentResult.findings

  const displayFindings = allFindings.length > 0 ? allFindings : []
  if (displayFindings.length === 0 && aiMessage.allObservations.length > 0) {
    for (const obs of aiMessage.allObservations) {
      if (typeof obs === 'object' && obs !== null) {
        if (obs.summary && typeof obs.summary === 'string') {
          const summaryLines = obs.summary.split('\n').filter((line) => line.trim())
          for (const line of summaryLines) {
            if (!displayFindings.includes(line)) {
              displayFindings.push(line)
            }
          }
          continue
        }

        const priorityKeys = [
          'bugs_found',
          'elements_found',
          'issues_found',
          'errors_found',
          'elements',
          'output',
          'findings',
          'page_content',
          'text',
          'content',
          'message'
        ]
        for (const key of priorityKeys) {
          if (key in obs && obs[key]) {
            const value = obs[key]
            if (typeof value === 'string') {
              if (value.trim() && !displayFindings.includes(value.trim())) {
                displayFindings.push(value.trim())
              }
            } else if (Array.isArray(value)) {
              for (const item of value) {
                const itemStr =
                  typeof item === 'string'
                    ? item
                    : item.title || item.name || item.description || JSON.stringify(item)
                if (itemStr && !displayFindings.includes(itemStr)) {
                  displayFindings.push(itemStr)
                }
              }
            } else if (typeof value === 'object') {
              const summary = formatObjectToSummary(value)
              if (summary && !displayFindings.includes(summary)) {
                displayFindings.push(summary)
              }
            }
          }
        }
      } else if (typeof obs === 'string') {
        if (obs.trim() && !displayFindings.includes(obs.trim())) {
          displayFindings.push(obs.trim())
        }
      }
    }
  }

  if (displayFindings.length > 0) {
    aiMessage.agentResult.findings = displayFindings
  }

  if ((stepEvent.steps_count === 0 || !stepEvent.steps_count) && displayFindings.length > 0) {
    aiMessage.finalResponse = '⚠️ ' + displayFindings[0]
  } else {
    // 有统一总结块时正文走 runningSummaryDraft / summaryText / findings，勿再塞「执行统计」到 finalResponse
    aiMessage.finalResponse = ''
  }

  if (stepsCountResolved === 0) {
    aiMessage.steps = []
    aiMessage._placeholderSteps = false
  }
}
