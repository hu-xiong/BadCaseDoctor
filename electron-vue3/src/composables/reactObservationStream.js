/**
 * ReAct SSE：observation（v1 tool end/error → legacy stepEvent）大段 UI 状态写入。
 * 从 SimpleChatPanel 迁入，便于单测与继续收敛解析路径。
 */
import { nextTick } from 'vue'
import { snowflakeIdStr } from '../utils/snowflakeId.js'
import { getStableCreatedId } from '../utils/createPreviewKeys.js'
import { i18n } from '../i18n/index.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'
import {
  normalizeTestcaseModifyFieldKey,
  isTestcaseDetailModifyField
} from '../utils/testcaseModifyFields.js'
import { looksLikeDeleteToolPreview } from '../utils/deletePreviewUtils.js'

/** 计划/实体主键：禁止 parseInt/Number，避免雪花 ID 精度丢失 */
function normalizePlanIdStr(raw) {
  if (raw == null || raw === '') return null
  const s = snowflakeIdStr(raw) || String(raw).trim()
  return s && /^\d+$/.test(s) ? s : null
}

/** delete 预览主键：plan 优先 plan_id，其余优先 target_id */
function pickDeletePreviewTargetId(tgt, rec, flat, toolData) {
  const t = String(tgt || '').toLowerCase()
  const fromWire =
    normalizePlanIdStr(flat.target_id ?? toolData?.target_id) ||
    normalizePlanIdStr(flat.plan_id ?? toolData?.plan_id)
  if (fromWire) return fromWire
  if (t === 'plan') {
    if (typeof rec?.id === 'string') return normalizePlanIdStr(rec.id)
    // 数字 id 可能已被 JS 截断；仍写入占位，由 show-delete-in-list 按名称纠正
    return normalizePlanIdStr(rec?.id)
  }
  return (
    normalizePlanIdStr(rec?.id ?? flat.target_id ?? toolData?.target_id) ||
    String(rec?.id ?? flat.target_id ?? toolData?.target_id ?? '').trim() ||
    null
  )
}

/** modify 预览：从工具结果或 before 快照取关联 Card.id，供列表跳转（与 Bug 源表 id 区分） */
function pickModifyNavCardId(rr, r, toolData) {
  const top =
    rr?.card_id ??
    r?.card_id ??
    rr?.cardId ??
    r?.cardId ??
    toolData?.card_id ??
    toolData?.cardId
  if (top != null && String(top).trim() !== '') {
    return snowflakeIdStr(top) || String(top).trim()
  }
  const b = rr?.before || r?.before
  if (b && typeof b === 'object') {
    const c = b.card_id ?? b.cardId
    if (c != null && String(c).trim() !== '') return snowflakeIdStr(c) || String(c).trim()
  }
  const a = rr?.after || r?.after
  if (a && typeof a === 'object') {
    const c = a.card_id ?? a.cardId
    if (c != null && String(c).trim() !== '') return snowflakeIdStr(c) || String(c).trim()
  }
  return null
}

/**
 * modify 预览缺少 before.card_id 时：从本轮或上一步 grep 的 navigation / grepNavigation 补 card_id
 *（合并为 target=card 时用 legacy_row_id + merged_from_legacy 对齐源表 id）
 */
function pickModifyNavCardIdFromGrepNav(aiMessage, toolData) {
  const tgt = String(toolData?.target || '')
    .trim()
    .toLowerCase()
  if (!['bug', 'badcase', 'testcase'].includes(tgt)) return null
  const tidRaw = toolData?.target_id ?? toolData?.targetId
  if (tidRaw == null || tidRaw === '') return null
  const tidStr = snowflakeIdStr(tidRaw) || String(tidRaw).trim()
  if (!tidStr) return null

  const cardIdFromNavItem = (it) => {
    if (!it || typeof it !== 'object') return null
    const t = String(it.target || '')
      .trim()
      .toLowerCase()
    const cidRaw = it.card_id ?? it.cardId
    if (t === 'card') {
      const legRaw = it.legacy_row_id
      const leg =
        legRaw != null && legRaw !== '' ? snowflakeIdStr(legRaw) || String(legRaw).trim() : ''
      const mf = String(it.merged_from_legacy || '')
        .trim()
        .toLowerCase()
      if (mf === tgt && leg === tidStr && cidRaw != null && String(cidRaw).trim() !== '') {
        return snowflakeIdStr(cidRaw) || String(cidRaw).trim()
      }
      return null
    }
    const ridRaw = it.record_id
    const rid = ridRaw != null && ridRaw !== '' ? snowflakeIdStr(ridRaw) || String(ridRaw).trim() : ''
    if (t === tgt && rid === tidStr && cidRaw != null && String(cidRaw).trim() !== '') {
      return snowflakeIdStr(cidRaw) || String(cidRaw).trim()
    }
    return null
  }

  const scanNav = (nav) => {
    if (!nav || nav.type !== 'multiple' || !Array.isArray(nav.items)) return null
    for (const it of nav.items) {
      const x = cardIdFromNavItem(it)
      if (x) return x
    }
    return null
  }

  let found = scanNav(aiMessage?.navigation)
  if (found) return found
  const steps = aiMessage?.steps || []
  for (let i = steps.length - 1; i >= 0; i--) {
    found = scanNav(steps[i]?.grepNavigation)
    if (found) return found
  }
  return null
}

/** 详情字段列表（不在列表中显示的字段，用于沙箱预览分组） */
export const DETAIL_FIELDS = [
  'base_problem',
  'reproduction_steps',
  'answer',
  'correct_answer',
  'badcase_result',
  'solution',
  'problem_reason',
  'steps_to_reproduce',
  'expected_result',
  'actual_result',
  'preconditions',
  'steps',
  'reproduce_steps',
  /** 列表列不展示或仅详情表单项确认的字段（沙箱点击应可直达详情） */
  'priority',
  'severity',
  'case_category',
  'case_type',
  'test_type',
  'execution_result',
  'related_defects',
  'append_comment',
  'plan_id',
  'project_id'
]

/** 与后端 modify 沙箱 before 形状一致：模型常传 target=badcase 实为 Bug 行 */
function inferModifyTargetFromSourceRowShape(before, after) {
  const row =
    before && typeof before === 'object'
      ? before
      : after && typeof after === 'object'
        ? after
        : null
  if (!row) return null
  if (
    Object.prototype.hasOwnProperty.call(row, 'steps_to_reproduce') ||
    Object.prototype.hasOwnProperty.call(row, 'severity')
  ) {
    return 'bug'
  }
  if (
    Object.prototype.hasOwnProperty.call(row, 'reproduction_steps') ||
    Object.prototype.hasOwnProperty.call(row, 'badcase_result')
  ) {
    return 'badcase'
  }
  if (
    Object.prototype.hasOwnProperty.call(row, 'preconditions') ||
    Object.prototype.hasOwnProperty.call(row, 'test_type') ||
    Object.prototype.hasOwnProperty.call(row, 'execution_result') ||
    Object.prototype.hasOwnProperty.call(row, 'related_defects')
  ) {
    return 'testcase'
  }
  return null
}

/** 单条 modify 工具结果：优先按 before 推断，避免沙箱跳转误用 BadCase */
function resolveModifyNavigationTarget(toolData) {
  if (!toolData || typeof toolData !== 'object') return 'bug'
  const inferred = inferModifyTargetFromSourceRowShape(toolData.before, toolData.after)
  if (inferred) return inferred
  const raw = String(toolData.target || '').trim().toLowerCase()
  if (['bug', 'badcase', 'testcase', 'card', 'plan'].includes(raw)) return raw
  return 'bug'
}

function resolveBatchModifyItemTarget(rr, r, toolData) {
  const inferred = inferModifyTargetFromSourceRowShape(rr?.before || r?.before, rr?.after || r?.after)
  if (inferred) return inferred
  const raw = String(rr?.target || r?.target || toolData?.target || '').trim().toLowerCase()
  if (['bug', 'badcase', 'testcase', 'card', 'plan'].includes(raw)) return raw
  return 'bug'
}

const stableModifyModsKey = (m) => {
  if (!m || typeof m !== 'object') return ''
  const o = {}
  Object.keys(m)
    .sort()
    .forEach((k) => {
      o[k] = m[k]
    })
  return JSON.stringify(o)
}

/**
 * 与上一条是否应合并为一组（沙箱卡片 / 跳转派发）
 */
export const shouldMergeModifyPreviewItems = (prevItem, item) => {
  if (!prevItem || !item) return false
  if (prevItem.target_id === item.target_id) return true
  const idDiff = item.target_id - prevItem.target_id
  if (idDiff === 1 || idDiff === -1) return true
  const modsKey = stableModifyModsKey(prevItem.modifications)
  if (
    modsKey &&
    modsKey !== '{}' &&
    prevItem.target === item.target &&
    modsKey === stableModifyModsKey(item.modifications)
  ) {
    return true
  }
  return false
}

// 从标题中提取工具名称（不区分大小写）
export const extractToolName = (title) => {
  if (!title) return ''
  const t = String(title).toLowerCase()
  if (t.includes('database_query')) return 'database_query'
  if (t.includes('grep')) return 'grep'
  if (t.includes('modify')) return 'modify'
  if (t.includes('delete') || t.includes('删除')) return 'delete'
  if (t.includes('create')) return 'create'
  if (t.includes('cdp') || t.includes('browser_test')) return 'cdp'
  if (t.includes('log_analyzer')) return 'log_analyzer'
  if (t.includes('search')) return 'search'
  return ''
}

/** 从 observation 生成人类可读的一行结果摘要 */
export const buildStepResultSummary = (outputData, toolName, toolData) => {
  const t = i18n.global.t.bind(i18n.global)
  const outer = outputData && typeof outputData === 'object' ? outputData : {}
  const d = toolData && typeof toolData === 'object' ? toolData : {}
  const tool = toolName || outer.tool || ''
  const listSep = i18n.global.locale.value === 'en' ? ', ' : '，'
  const combinedErr =
    (typeof d.error === 'string' && d.error.trim()) ||
    (typeof outer.error === 'string' && outer.error.trim()) ||
    ''
  if (combinedErr) return t('chat.stepErr', { msg: combinedErr })
  if (tool === 'grep' || d.testcase_location || d.bug_location || d.badcase_analysis || d.card_location || d.plan_tree) {
    const tc = d.testcase_location?.length ?? 0
    const bugs = d.bug_location?.length ?? 0
    const bc = d.badcase_analysis?.length ?? 0
    const cards = d.card_location?.length ?? 0
    if (d.summary && typeof d.summary === 'string') return d.summary.slice(0, 400)
    const parts = []
    if (tc) parts.push(t('chat.stepNTestcases', { n: tc }))
    if (bugs) parts.push(t('chat.stepNBugs', { n: bugs }))
    if (bc) parts.push(t('chat.stepNBadcases', { n: bc }))
    if (cards) parts.push(t('chat.stepNCards', { n: cards }))
    if (d.plan_tree?.total_plans) parts.push(t('chat.stepNPlans', { n: d.plan_tree.total_plans }))
    return parts.length ? `${t('chat.stepLocatePrefix')}${parts.join(listSep)}` : t('chat.stepLocateDone')
  }
  if (tool === 'modify' || d.batch_modify || (d.diff && (d.target_id != null || d.batch_results))) {
    if (d.batch_modify && d.batch_results?.length) {
      return t('chat.stepBatchModify', { n: d.batch_results.length })
    }
    if (d.diff?.length) return t('chat.stepModifyPreview', { n: d.diff.length })
    if (d.success === false) return t('chat.stepModifyFail', { msg: d.error || t('chat.stepUnknownErr') })
    return d.message || t('chat.stepModifyDone')
  }
  if (tool === 'delete' || (d.preview?.record && d.confirmation_required)) {
    if (d.success === false || outer.success === false) {
      return combinedErr || t('chat.stepFailed')
    }
    if (d.deleted_id != null && d.confirmation_required !== true) {
      return d.message || t('chat.stepDeleteDone', { id: d.deleted_id })
    }
    const pr = d.preview?.record
    const nm = pr?.title ?? pr?.name ?? pr?.id
    if (nm != null) return t('chat.stepDeletePreview', { label: String(nm).slice(0, 80) })
    return d.message || t('chat.stepDeletePreviewShort')
  }
  if (tool === 'create' || (d.preview && typeof d.preview === 'object' && d.target)) {
    if (d.success === false || outer.success === false) {
      return combinedErr || t('chat.stepFailed')
    }
    const title = d.preview?.title
    if (title) return t('chat.stepCreatePreview', { title })
    return d.message || t('chat.stepCreateReady')
  }
  if (d.message) return String(d.message).slice(0, 400)
  if (outer.success === false) return t('chat.stepFailed')
  return t('chat.stepDone')
}

/** 流式 ensureReactStepsForStreamIndex 占位标题（不用「步骤 N」数字） */
export const STREAM_STEP_INDEX_PLACEHOLDER_TITLE = '…'

/** 尾部仅占位（… 或历史「步骤 N」）且无实质产出：用于裁剪空壳面板 */
export const isPhantomTailAgentStep = (s) => {
  if (!s || typeof s !== 'object') return false
  const title = String(s.title || '').trim()
  const isWaitingTitle =
    title === STREAM_STEP_INDEX_PLACEHOLDER_TITLE ||
    /^(\.\s*){3,}\s*$/u.test(title) ||
    /^\.{2,}\s*$/u.test(title) ||
    /^步骤\s*\d+\s*$/u.test(title)
  if (!isWaitingTitle) return false
  const tn = extractToolName(title)
  if (tn && tn !== '') return false
  if (s.grepNavigation?.items?.length) return false
  if (s.resultSummary != null && String(s.resultSummary).trim()) return false
  // 有思考/观察流式内容时不当作幽灵步骤，否则 todo_skip step 积累的 thoughtReasoningDraft 不可见
  const _hasMeaningful = (t) => {
    const v = String(t || '').replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
    return v.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(v)
  }
  if (_hasMeaningful(s.thoughtReasoningDraft) || _hasMeaningful(s.agentThoughtDraft)) return false
  const exec = [...(s.detailLog || []), ...(s.progressLog || [])].join('\n').trim()
  if (/结果|失败|成功|error|preview|定位|修改|缺少|创建|grep|modify|create|参数|project/i.test(exec)) {
    return false
  }
  if (exec.replace(/─/g, '-').replace(/\s/g, '').length > 40) return false
  if (s.status === 'failed' || s.status === 'error') return false
  return true
}

export const pruneTrailingPhantomAgentSteps = (steps) => {
  if (!Array.isArray(steps) || steps.length === 0) return steps
  const out = [...steps]
  while (out.length > 0 && isPhantomTailAgentStep(out[out.length - 1])) {
    out.pop()
  }
  return out
}

/**
 * ``resolveStreamStepIndex`` 要求 ``steps[n]`` 已存在；若未收到 todos/todo_start 扩行，工具事件会绑不到 UI 步骤。
 * 按 SSE 的 0-based index 补齐占位行：中间隙标已完成，目标行为 running。
 */
export function ensureReactStepsForStreamIndex(aiMessage, raw, buildReactStepsFromTodoStrings) {
  if (!aiMessage || raw === null || raw === undefined) return
  if (typeof raw === 'string' && raw.trim() === '') return
  const base = Number(aiMessage._reactStreamStepBase || 0)
  const rel = Number(raw)
  if (!Number.isFinite(rel) || rel < 0) return
  const n = base + rel
  if (!Number.isFinite(n) || n < 0) return
  if (typeof buildReactStepsFromTodoStrings !== 'function') return
  if (!Array.isArray(aiMessage.steps)) aiMessage.steps = []
  while (aiMessage.steps.length <= n) {
    const i = aiMessage.steps.length
    const label = STREAM_STEP_INDEX_PLACEHOLDER_TITLE
    const rows = buildReactStepsFromTodoStrings([label])
    const row = rows && rows[0]
    if (!row) break
    if (i < n) {
      row.status = 'completed'
      row.description = row.description || '…'
    } else {
      row.status = 'running'
      if (row.stepStartedAt == null) row.stepStartedAt = Date.now()
    }
    aiMessage.steps.push(row)
  }
}

/**
 * @param {object} aiMessage
 * @param {object} stepEvent event === 'observation'
 * @param {object} ctx
 * @param {function} ctx.resolveStreamStepIndex
 * @param {function} ctx.appendStepDetailLine
 * @param {function} [ctx.nextTick] 默认使用 vue.nextTick
 * @param {function} ctx.handleShowGroupInList
 * @param {function} [ctx.handleShowModifyInList]
 * @param {number|null|undefined} ctx.projectId
 * @param {function} ctx.handleNavigation
 * @param {function} [ctx.buildReactStepsFromTodoStrings]
 */
export function applyReactObservationLegacyStepEvent(aiMessage, stepEvent, ctx) {
  const resolveStreamStepIndex = ctx.resolveStreamStepIndex
  const appendStepDetailLine = ctx.appendStepDetailLine
  const buildReactStepsFromTodoStrings = ctx.buildReactStepsFromTodoStrings
  const tick = ctx.nextTick || nextTick
  const handleShowGroupInList = ctx.handleShowGroupInList
  const handleShowModifyInList = ctx.handleShowModifyInList
  const projectId = ctx.projectId
  const handleNavigation = ctx.handleNavigation

  console.log('[CHAT-STREAM] === 触发 observation 事件 ===')
  ensureReactStepsForStreamIndex(
    aiMessage,
    stepEvent.stepIndex ?? stepEvent.index,
    buildReactStepsFromTodoStrings
  )
  const outputData = stepEvent.data
  const observationTool = (stepEvent.tool || '').toString().trim() || ''
  try {
    console.log(
      '[CHAT-STREAM] 收到 observation 数据:',
      JSON.stringify(outputData, null, 2).substring(0, 500)
    )
  } catch {
    console.log('[CHAT-STREAM] 收到 observation 数据: [无法 JSON 序列化，已省略]')
  }
  console.log('[CHAT-STREAM] outputData 类型:', typeof outputData)
  console.log('[CHAT-STREAM] outputData.keys:', outputData ? Object.keys(outputData) : 'null')

  aiMessage.allObservations.push(outputData)

  const _obsIdx = resolveStreamStepIndex(stepEvent.stepIndex ?? stepEvent.index, aiMessage.steps)
  let runningStep = null
  if (_obsIdx != null) {
    runningStep = aiMessage.steps[_obsIdx]
    console.log('[CHAT-STREAM] observation 绑定步骤 stepIndex=', _obsIdx)
  } else {
    runningStep = aiMessage.steps.find((s) => s.status === 'running')
  }
  if (!runningStep) {
    const ot =
      observationTool || (outputData && typeof outputData === 'object' ? outputData.tool : '')
    if (ot && ['grep', 'create', 'modify', 'delete'].includes(String(ot))) {
      runningStep = [...aiMessage.steps]
        .reverse()
        .find((s) => s.title === ot || (s.title && s.title.includes(ot)))
    }
    runningStep =
      runningStep ||
      aiMessage.steps.slice().reverse().find(
        (s) =>
          s.title &&
          (s.title.includes('create') ||
            s.title.includes('modify') ||
            s.title.includes('delete') ||
            s.title === 'grep' ||
            s.title.includes('grep'))
      ) ||
      aiMessage.steps[aiMessage.steps.length - 1]
    console.log('[CHAT-STREAM] 没有找到 running 步骤，使用:', runningStep?.title)
  }
  if (_obsIdx != null && runningStep) {
    const tn = observationTool || (outputData && typeof outputData === 'object' ? outputData.tool : '')
    if (tn && ['grep', 'create', 'modify', 'delete', 'search', 'database_query'].includes(String(tn))) {
      runningStep.title = String(tn)
    }
  }

  if (!runningStep) return

  runningStep.toolCall = runningStep.toolCall || { name: '', output: '' }
  if (typeof outputData === 'string') {
    runningStep.toolCall.output = outputData
  } else {
    try {
      runningStep.toolCall.output = JSON.stringify(outputData, null, 2)
    } catch {
      runningStep.toolCall.output = '[observation 过大或含循环引用，无法完整序列化]'
    }
  }

  if (runningStep.thoughtPhaseEndAtMs == null) {
    if (runningStep.thoughtTiming?.durationMs != null && runningStep.stepStartedAt != null) {
      runningStep.thoughtPhaseEndAtMs =
        runningStep.stepStartedAt + Number(runningStep.thoughtTiming.durationMs)
    } else if (runningStep.stepStartedAt != null) {
      runningStep.thoughtPhaseEndAtMs = Date.now()
    }
  }
  if (stepEvent.tool_duration_ms != null && Number.isFinite(Number(stepEvent.tool_duration_ms))) {
    runningStep.toolExecDurationMs = Math.max(0, Number(stepEvent.tool_duration_ms))
  } else if (runningStep.toolExecStartedAt != null) {
    runningStep.toolExecDurationMs = Math.max(0, Date.now() - runningStep.toolExecStartedAt)
  } else {
    const flat =
      outputData && typeof outputData === 'object' && outputData.data && typeof outputData.data === 'object'
        ? outputData.data
        : outputData
    const perf = flat && (flat.grep_perf_ms ?? flat.tool_duration_ms)
    if (perf != null && Number.isFinite(Number(perf))) {
      runningStep.toolExecDurationMs = Math.max(0, Number(perf))
    }
  }
  if (runningStep.stepStartedAt != null) {
    runningStep.stepDurationMs = Date.now() - runningStep.stepStartedAt
  }

  freezeThoughtSnapshotForStep(runningStep)
  const od = typeof outputData === 'object' && outputData !== null ? outputData : {}
  runningStep.status = od.success === false ? 'failed' : 'completed'
  const humanMsg = od.message || od.summary || (od.data && (od.data.message || od.data.summary))
  runningStep.description =
    humanMsg && String(humanMsg).trim() ? String(humanMsg).trim().slice(0, 200) : '已完成'

  let isSearchResult = false
  if (outputData && typeof outputData === 'object') {
    if (outputData.results && Array.isArray(outputData.results) && outputData.engine) {
      aiMessage.searchResults = outputData.results
      isSearchResult = true
      console.log('[CHAT-STREAM] ✅ 提取搜索结果:', outputData.results.length, '条')
      console.log('[CHAT-STREAM] 搜索引擎:', outputData.engine, '查询:', outputData.query)
    } else if (outputData.query && outputData.engine && Array.isArray(outputData.results)) {
      aiMessage.searchResults = outputData.results
      isSearchResult = true
      console.log('[CHAT-STREAM] ✅ 提取搜索结果(格式2):', outputData.results.length, '条')
    }
  }

  if (!isSearchResult) {
    let resolvedTool =
      observationTool || (outputData && outputData.tool) || extractToolName(runningStep.title)
    if (!resolvedTool && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      if (
        flat &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        flat.preview.record &&
        flat.confirmation_required
      ) {
        resolvedTool = 'delete'
      }
    }
    if (!resolvedTool && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      const looksModifySummary =
        flat &&
        (flat.batch_modify === true ||
          (Array.isArray(flat.batch_results) && flat.batch_results.length > 0) ||
          (snowflakeIdStr(flat.target_id) &&
            Array.isArray(flat.diff) &&
            flat.diff.length > 0 &&
            (flat.before != null || flat.after != null || flat.confirmation_required === true)))
      if (
        flat &&
        !looksModifySummary &&
        !flat.created_id &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        Object.keys(flat.preview).length > 0 &&
        ['testcase', 'bug', 'badcase', 'plan', 'card'].includes(String(flat.target || '').toLowerCase())
      ) {
        resolvedTool = 'create'
      }
    }
    const td0 = outputData?.data || outputData
    if (typeof td0 === 'object' && td0 !== null) {
      runningStep.resultSummary = buildStepResultSummary(outputData, resolvedTool, td0)
      appendStepDetailLine(runningStep, `── 结果 ──\n${runningStep.resultSummary}`)
      const sumDraft = String(runningStep.thoughtSummaryDraft || '').replace(/\s+/g, ' ').trim()
      if (sumDraft.length < 2 && runningStep.resultSummary) {
        const rs = String(runningStep.resultSummary).replace(/\s+/g, ' ').trim().slice(0, 40)
        if (rs.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(rs)) {
          runningStep.thoughtSummaryDraft = rs
        }
      }
    }
  }

  if (!isSearchResult && runningStep.title) {
    let toolName =
      observationTool || (outputData && outputData.tool) || extractToolName(runningStep.title)
    if (!toolName && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      if (
        flat &&
        (flat.batch_modify === true ||
          (Array.isArray(flat.batch_results) && flat.batch_results.length > 0) ||
          (Array.isArray(flat.results) &&
            flat.results.length > 0 &&
            flat.results[0] &&
            typeof flat.results[0] === 'object' &&
            'result' in flat.results[0]))
      ) {
        toolName = 'modify'
      }
    }
    if (!toolName && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      if (
        flat &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        flat.preview.record &&
        flat.confirmation_required
      ) {
        toolName = 'delete'
      }
    }
    if (!toolName && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      const looksModify =
        flat &&
        (flat.batch_modify === true ||
          (Array.isArray(flat.batch_results) && flat.batch_results.length > 0) ||
          (snowflakeIdStr(flat.target_id) &&
            flat.target_id !== 'new' &&
            Array.isArray(flat.diff) &&
            flat.diff.length > 0 &&
            (flat.before != null || flat.after != null || flat.confirmation_required === true)))
      if (
        flat &&
        !looksModify &&
        !flat.created_id &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        Object.keys(flat.preview).length > 0 &&
        ['testcase', 'bug', 'badcase', 'plan', 'card'].includes(String(flat.target || '').toLowerCase())
      ) {
        toolName = 'create'
      }
    }
    console.log('[TOOL-DEBUG] runningStep.title:', runningStep.title)
    console.log('[TOOL-DEBUG] toolName:', toolName)
    console.log('[TOOL-DEBUG] outputData:', outputData)

    const toolData = outputData.data || outputData
    console.log('[MODIFY-DEBUG] toolName:', toolName)
    console.log('[MODIFY-DEBUG] toolData:', JSON.stringify(toolData, null, 2).substring(0, 800))
    console.log('[MODIFY-DEBUG] toolData.batch_modify:', toolData.batch_modify)
    console.log(
      '[MODIFY-DEBUG] toolData.batch_results:',
      toolData.batch_results ? 'exists, length=' + toolData.batch_results.length : 'not exists'
    )
    console.log(
      '[MODIFY-DEBUG] toolData.results:',
      toolData.results ? 'exists, length=' + toolData.results.length : 'not exists'
    )

    if (toolName === 'modify' && toolData && typeof toolData === 'object') {
      // 防重复更新：如果已有 modifyNavigation 且 batch_results 相同，跳过更新避免闪烁
      const existingNav = aiMessage.modifyNavigation
      const existingCount = existingNav?.batch_results?.length || 0
      const newCount = (toolData.batch_results || toolData.results || []).length
      const resolvedToolTarget = resolveModifyNavigationTarget(toolData)
      if (
        existingCount > 0 &&
        existingCount === newCount &&
        existingNav?.target === resolvedToolTarget
      ) {
        console.log('[MODIFY] 跳过重复 modifyNavigation 更新，避免闪烁')
        return
      }
      
      const resultsArray = toolData.batch_results || toolData.results
      console.log(
        '[MODIFY] 检测批量修改数据: batch_modify=',
        toolData.batch_modify,
        'results=',
        resultsArray ? resultsArray.length : 0
      )
      if (resultsArray && Array.isArray(resultsArray) && resultsArray.length > 0) {
        try {
          const allItems = []
          let batchOrderSeq = 0
          resultsArray.forEach((r) => {
            const rr =
              r && typeof r === 'object' && r.result && typeof r.result === 'object' ? r.result : r
            const itemIdRaw = rr?.target_id ?? r?.target_id ?? rr?.id ?? r?.id
            const itemId = snowflakeIdStr(itemIdRaw)
            const praw = rr?.plan_id ?? r?.plan_id
            const itemPlanId =
              praw != null && praw !== '' ? snowflakeIdStr(praw) || String(praw).trim() : null

            if (!itemId) {
              console.warn('[MODIFY] 跳过无效 ID:', itemIdRaw)
              return
            }

            const rawDiff = rr?.diff || r?.diff || []
            console.log('[MODIFY-DEBUG] rawDiff:', rawDiff)
            console.log('[MODIFY-DEBUG] r.modifications:', rr?.modifications ?? r?.modifications)

            const listFieldDiff = []
            const detailFieldDiff = []
            rawDiff.forEach((fieldDiff) => {
              const fname = fieldDiff && (fieldDiff.field || fieldDiff.field_label)
              if (!fieldDiff || !fname) return
              const nk = normalizeTestcaseModifyFieldKey(
                fieldDiff.field,
                fieldDiff.field_label
              )
              const isDetail =
                DETAIL_FIELDS.includes(nk) ||
                isTestcaseDetailModifyField(nk, fieldDiff.field_label)
              console.log(
                '[MODIFY-DEBUG] fieldDiff.field:',
                fname,
                'normalized:',
                nk,
                'isDetail:',
                isDetail
              )
              if (isDetail) {
                detailFieldDiff.push(fieldDiff)
              } else {
                listFieldDiff.push(fieldDiff)
              }
            })
            console.log(
              '[MODIFY-DEBUG] detailFieldDiff:',
              detailFieldDiff.length,
              'listFieldDiff:',
              listFieldDiff.length
            )

            const baseItemInfo = {
              target_id: itemId,
              plan_id: itemPlanId,
              target: resolveBatchModifyItemTarget(rr, r, toolData),
              modifications: rr?.modifications || r?.modifications || {},
              confirmation_required: (rr?.confirmation_required ?? r?.confirmation_required) !== false,
              success: (rr?.success ?? r?.success) === true,
              before: rr?.before || r?.before || null,
              after: rr?.after || r?.after || null,
              record_title:
                rr?.record_title ||
                r?.record_title ||
                (rr?.before && rr.before.title) ||
                (r?.before && r.before.title) ||
                null,
              batchOrder: batchOrderSeq++
            }
            const navCid =
              pickModifyNavCardId(rr, r, toolData) ||
              pickModifyNavCardIdFromGrepNav(aiMessage, {
                target: resolveBatchModifyItemTarget(rr, r, toolData),
                target_id: itemIdRaw
              })
            if (navCid) baseItemInfo.card_id = navCid

            if (listFieldDiff.length === 0 && detailFieldDiff.length === 0 && rawDiff.length > 0) {
              allItems.push({
                ...baseItemInfo,
                diff: rawDiff
              })
            } else {
              if (listFieldDiff.length > 0) {
                allItems.push({
                  ...baseItemInfo,
                  diff: listFieldDiff
                })
              }
              if (detailFieldDiff.length > 0) {
                allItems.push({
                  ...baseItemInfo,
                  diff: detailFieldDiff
                })
              }
            }
          })

          if (allItems.length === 0) {
            console.warn('[MODIFY] 没有有效的 diff 行，仍保留批量预览导航')
            aiMessage.modifyNavigation = {
              batch_modify: true,
              batch_results: [...resultsArray],
              batch_count: resultsArray.length,
              target: resolvedToolTarget
            }
          } else {
            const planGroups = {}
            allItems.forEach((item) => {
              const planKey =
              item.plan_id !== null && item.plan_id !== undefined && item.plan_id !== ''
                ? String(item.plan_id)
                : 'unplanned'
              if (!planGroups[planKey]) {
                planGroups[planKey] = []
              }
              planGroups[planKey].push(item)
            })

            const modifyGroups = []
            Object.entries(planGroups).forEach(([planId, items]) => {
              items.sort((a, b) => (a.batchOrder ?? 0) - (b.batchOrder ?? 0))

              let currentGroup = []

              items.forEach((item, idx) => {
                if (idx === 0) {
                  currentGroup.push(item)
                } else {
                  const prevItem = items[idx - 1]
                  if (shouldMergeModifyPreviewItems(prevItem, item)) {
                    currentGroup.push(item)
                  } else {
                    if (currentGroup.length > 0) {
                      modifyGroups.push({
                        plan_id:
                          planId === 'unplanned'
                            ? null
                            : /^\d+$/.test(String(planId))
                              ? String(planId)
                              : null,
                        target: currentGroup[0]?.target || resolvedToolTarget,
                        items: [...currentGroup]
                      })
                    }
                    currentGroup = [item]
                  }
                }
              })

              if (currentGroup.length > 0) {
                modifyGroups.push({
                  plan_id:
                    planId === 'unplanned'
                      ? null
                      : /^\d+$/.test(String(planId))
                        ? String(planId)
                        : null,
                  target: currentGroup[0]?.target || resolvedToolTarget,
                  items: [...currentGroup]
                })
              }
            })

            aiMessage.modifyGroups = Object.freeze([...modifyGroups])
            aiMessage.modifyNavigation = {
              batch_modify: true,
              batch_results: [...allItems],
              batch_count: allItems.length,
              target: allItems[0]?.target || resolvedToolTarget
            }
            console.log(
              '[MODIFY] 生成 modifyGroups:',
              modifyGroups.length,
              '个分组, 共',
              allItems.length,
              '项'
            )
            tick(() => {
              modifyGroups.forEach((grp) => {
                if (grp.items && grp.items.length > 0) {
                  handleShowGroupInList(grp, aiMessage.id)
                }
              })
            })
          }
        } catch (err) {
          console.error('[MODIFY] 分组处理异常:', err)
        }
      } else if (toolData.confirmation_required && toolData.diff) {
        const navCid =
          pickModifyNavCardId(toolData, toolData, toolData) ||
          pickModifyNavCardIdFromGrepNav(aiMessage, toolData)
        aiMessage.modifyNavigation = {
          target: resolveModifyNavigationTarget(toolData),
          target_id: snowflakeIdStr(toolData.target_id) || toolData.target_id,
          ...(navCid ? { card_id: navCid } : {}),
          diff: toolData.diff,
          modifications: toolData.modifications,
          confirmation_required: true,
          before: toolData.before ?? null,
          after: toolData.after ?? null
        }
        console.log('[MODIFY] 存储沙箱预览导航:', aiMessage.modifyNavigation)
      } else if (toolData.diff && toolData.before && toolData.after) {
        const navCid2 =
          pickModifyNavCardId(toolData, toolData, toolData) ||
          pickModifyNavCardIdFromGrepNav(aiMessage, toolData)
        aiMessage.modifyNavigation = {
          target: resolveModifyNavigationTarget(toolData),
          target_id: snowflakeIdStr(toolData.target_id) || toolData.target_id,
          ...(navCid2 ? { card_id: navCid2 } : {}),
          diff: toolData.diff,
          modifications: toolData.modifications,
          before: toolData.before,
          after: toolData.after,
          plan_id: toolData.before?.plan_id,
          success: toolData.success,
          message: toolData.message
        }
        console.log('[MODIFY] 存储单个修改导航:', aiMessage.modifyNavigation)
      }
      if (toolData.confirmation_required || aiMessage.modifyNavigation) {
        aiMessage.understanding = ''
        const hint = toolData.message || toolData.summary
        if (hint && String(hint).trim() && !String(aiMessage.finalResponse || '').trim()) {
          aiMessage.finalResponse = String(hint).trim()
        }
      }
    }

    if (toolName === 'create' && toolData && typeof toolData === 'object') {
      if (!looksLikeDeleteToolPreview(toolData)) {
      const hasDiff = Array.isArray(toolData.diff) && toolData.diff.length > 0
      const hasPreview = toolData.preview && typeof toolData.preview === 'object' && Object.keys(toolData.preview).length > 0
      const looksLikePreview =
        toolData.success !== false && !toolData.created_id && (hasDiff || hasPreview)
      if (looksLikePreview) {
        const pv = toolData.preview && typeof toolData.preview === 'object' ? toolData.preview : {}
        const inferCreateTarget = () => {
          const ex = toolData.target && String(toolData.target).trim().toLowerCase()
          if (ex === 'card') return 'card'
          if (pv.copy_from_card_id != null && String(pv.copy_from_card_id).trim() !== '') return 'card'
          if (pv.source_card_id != null && String(pv.source_card_id).trim() !== '') return 'card'
          if (pv.copy_from_bug_id != null && String(pv.copy_from_bug_id).trim() !== '') return 'bug'
          if (pv.source_bug_id != null && String(pv.source_bug_id).trim() !== '') return 'bug'
          if (pv.copy_from_badcase_id != null || pv.source_badcase_id != null) return 'badcase'
          if (pv.copy_from_testcase_id != null || pv.source_testcase_id != null) return 'testcase'
          if (ex && ['bug', 'badcase', 'testcase', 'plan', 'card'].includes(ex)) return ex
          if (
            pv.severity != null ||
            pv.bug_type != null ||
            (pv.steps_to_reproduce != null && String(pv.steps_to_reproduce).trim() !== '') ||
            (pv.reproduce_steps != null && String(pv.reproduce_steps).trim() !== '')
          ) {
            return 'bug'
          }
          if (pv.case_category != null || (pv.base_problem != null && String(pv.base_problem).trim() !== '')) {
            return 'badcase'
          }
          if (pv.steps != null || (pv.case_type != null && String(pv.case_type).trim() !== '')) {
            return 'testcase'
          }
          return 'bug'
        }
        const resolvedTarget = inferCreateTarget()
        const adoptedPlanHint =
          projectId != null && resolvedTarget === 'plan'
            ? getStableCreatedId(projectId, resolvedTarget, pv)
            : null
        const adoptedId =
          projectId != null && resolvedTarget !== 'plan'
            ? getStableCreatedId(projectId, resolvedTarget, pv)
            : null
        if (resolvedTarget === 'plan' && projectId != null) {
          aiMessage.modifyNavigation = {
            target: resolvedTarget,
            target_id: 'new',
            diff: hasDiff ? toolData.diff : [],
            preview: toolData.preview,
            modifications: toolData.preview || {},
            confirmation_required: true,
            is_create: true,
            _awaitStableVerify: true
          }
          tick(() => {
            window.dispatchEvent(
              new CustomEvent('verify-stable-create-id', {
                detail: {
                  messageId: aiMessage.id,
                  projectId,
                  target: resolvedTarget,
                  preview: pv,
                  adoptedId: adoptedPlanHint,
                  toolPreview: toolData.preview,
                  diff: hasDiff ? toolData.diff : []
                },
                bubbles: true
              })
            )
          })
        } else if (adoptedId != null) {
          const planIdNav = pv.plan_id ?? pv.planId
          aiMessage.modifyNavigation = {
            target: resolvedTarget,
            target_id: adoptedId,
            preview: toolData.preview,
            plan_id: planIdNav,
            confirmation_required: false,
            navigate_to_existing: true,
            created_id: adoptedId,
            is_create: false,
            diff: hasDiff ? toolData.diff : []
          }
          const cidStable = pv.card_id ?? pv.cardId
          window.dispatchEvent(
            new CustomEvent('grep-navigate', {
              detail: {
                planId: planIdNav,
                bugId: adoptedId,
                recordId: adoptedId,
                target: resolvedTarget,
                ...(cidStable != null && cidStable !== '' ? { card_id: cidStable } : {})
              },
              bubbles: true
            })
          )
          console.log('[CREATE] 稳定键已采纳，改为定位已存在行:', adoptedId)
        } else {
          aiMessage.modifyNavigation = {
            target: resolvedTarget,
            target_id: 'new',
            diff: hasDiff ? toolData.diff : [],
            preview: toolData.preview,
            modifications: toolData.preview || {},
            confirmation_required: true,
            is_create: true
          }
        }
        console.log('[CREATE] 存储新建预览（modifyNavigation）:', aiMessage.modifyNavigation)
        const navCreate = aiMessage.modifyNavigation
        if (
          handleShowModifyInList &&
          navCreate?.is_create === true &&
          !navCreate._awaitStableVerify &&
          navCreate.confirmation_required !== false &&
          !navCreate.navigate_to_existing
        ) {
          tick(() => {
            handleShowModifyInList(navCreate, aiMessage.id)
          })
        }
      } else if (toolData.success === false || toolData.error) {
        const errText = toolData.error || toolData.message || '新建预览失败'
        aiMessage.executionResults.push({
          step: runningStep.title,
          text: `create：${errText}`,
          success: false
        })
        const hint =
          /fields|project_id/i.test(String(errText))
            ? '缺 project_id 多为会话未带项目；fields 为空对象 {} 在 Python 里视为无 fields。请对照上一条 [CREATE][executing] 入参诊断 与终端 [CREATE] 校验失败'
            : ''
        console.warn('[CREATE] 工具返回失败，未生成预览', {
          errText,
          success: toolData.success,
          chatProjectId: projectId,
          toolDataKeys: Object.keys(toolData),
          hint
        })
      }
      }
    }

    if (toolName === 'delete' && toolData && typeof toolData === 'object') {
      const flat = toolData.data && typeof toolData.data === 'object' ? toolData.data : toolData
      const okSuccess = flat.success !== false && flat.success !== 'false'
      const needConfirm =
        flat.confirmation_required === true ||
        flat.confirmation_required === 'true' ||
        flat.confirmation_required === 1
      const pvRaw = flat.preview && typeof flat.preview === 'object' ? flat.preview : null
      const recRaw =
        pvRaw?.record && typeof pvRaw.record === 'object'
          ? pvRaw.record
          : flat.record && typeof flat.record === 'object'
            ? flat.record
            : null

      const doneDelete =
        okSuccess &&
        flat.deleted_id != null &&
        flat.confirmation_required !== true &&
        flat.confirmation_required !== 'true'

      if (doneDelete) {
        const delId = snowflakeIdStr(flat.deleted_id) || String(flat.deleted_id ?? '').trim()
        const prevNav = aiMessage.deleteNavigation
        if (prevNav && typeof prevNav === 'object' && delId && /^\d+$/.test(delId)) {
          aiMessage.deleteNavigation = {
            ...prevNav,
            confirmation_required: false,
            success: true,
            deleted_id: flat.deleted_id
          }
        } else if (recRaw && delId && /^\d+$/.test(delId)) {
          let pv =
            pvRaw && pvRaw.record && typeof pvRaw.record === 'object'
              ? pvRaw
              : pvRaw
                ? { ...pvRaw, record: recRaw }
                : { target: flat.target || toolData.target || 'bug', record: recRaw }
          const tgt = String(pv.target || flat.target || toolData.target || '').toLowerCase()
          let planId = normalizePlanIdStr(recRaw.plan_id ?? flat.plan_id ?? toolData.plan_id)
          aiMessage.deleteNavigation = {
            target: tgt || 'bug',
            target_id: delId,
            plan_id: planId,
            preview: pv,
            confirmation_required: false,
            success: true,
            deleted_id: flat.deleted_id
          }
        } else {
          aiMessage.deleteNavigation = null
        }
        if (delId && /^\d+$/.test(delId)) {
          const dt = String(flat.target || '').toLowerCase()
          tick(() => {
            window.dispatchEvent(
              new CustomEvent('modify-confirmed', {
                detail: { targetId: delId, deletedTargetType: dt },
                bubbles: true
              })
            )
          })
        }
      } else if (okSuccess && needConfirm && recRaw) {
        let pv =
          pvRaw && pvRaw.record && typeof pvRaw.record === 'object'
            ? pvRaw
            : pvRaw
              ? { ...pvRaw, record: recRaw }
              : { target: flat.target || toolData.target || 'bug', record: recRaw }
        const rec = recRaw
        const tgt = String(pv.target || flat.target || toolData.target || '').toLowerCase()
        const rid = pickDeletePreviewTargetId(tgt, rec, flat, toolData)
        let planId = normalizePlanIdStr(rec.plan_id ?? flat.plan_id ?? toolData.plan_id)
        if (tgt === 'plan' && rid) planId = rid
        if (rid && /^\d+$/.test(rid)) {
          aiMessage.deleteNavigation = {
            target: tgt || 'bug',
            target_id: rid,
            plan_id: planId,
            preview: { ...pv, record: { ...rec, id: rid } },
            confirmation_required: true
          }
          console.log('[DELETE] 已写入 deleteNavigation', aiMessage.deleteNavigation)
          if (
            aiMessage.modifyNavigation?.is_create === true &&
            looksLikeDeleteToolPreview(flat)
          ) {
            aiMessage.modifyNavigation = null
          }
          tick(() => {
            window.dispatchEvent(
              new CustomEvent('show-delete-in-list', {
                detail: {
                  target: tgt || 'bug',
                  target_id: rid,
                  plan_id: planId,
                  preview: {
                    ...pv,
                    record: { ...rec, id: rid }
                  },
                  messageId: aiMessage.id
                },
                bubbles: true
              })
            )
          })
        } else {
          console.warn('[DELETE] 预览缺少有效 record.id', { flat, pvRaw })
        }
      }
    }

    if (toolName === 'grep' && toolData && typeof toolData === 'object') {
      console.log('[GREP-DEBUG] 进入grep处理分支')
      console.log('[GREP-DEBUG] outputData:', outputData)
      console.log('[GREP-DEBUG] toolData:', toolData)
      console.log('[GREP-DEBUG] toolData keys:', Object.keys(toolData))

      let summaryText = ''

      const summary = toolData.summary || toolData.data?.summary
      if (summary) {
        summaryText = summary
      } else {
        const parts = []
        if (toolData.plan_tree) {
          parts.push(`📊 计划树: ${toolData.plan_tree.total_plans || 0}个计划`)
        }
        if (toolData.badcase_analysis) {
          parts.push(`🐛 BadCase: ${toolData.badcase_analysis.length || 0}条`)
        }
        if (toolData.bug_location) {
          parts.push(`🔍 Bug: ${toolData.bug_location.length || 0}条`)
        }
        if (toolData.testcase_location?.length) {
          parts.push(`📋 用例: ${toolData.testcase_location.length}条`)
        }
        if (toolData.card_location?.length) {
          parts.push(`🗂️ 卡片: ${toolData.card_location.length}条`)
        }
        summaryText = parts.join(' | ')
      }

      aiMessage.executionResults.push({
        step: runningStep.title,
        text: summaryText,
        success: outputData.success || toolData.success
      })

      console.log('[GREP-NAV] outputData:', outputData)
      console.log('[GREP-NAV] toolData:', toolData)

      const navigationData = outputData.navigation || toolData.navigation || toolData.data?.navigation
      console.log('[GREP-NAV] navigationData:', navigationData)

      if (navigationData) {
        console.log('[GREP-NAV] 收到导航指令:', navigationData)

        aiMessage.navigation = navigationData
        console.log('[GREP-NAV] 已存储navigation到aiMessage:', aiMessage.navigation)
        if (navigationData.type === 'multiple') {
          const _gi = resolveStreamStepIndex(stepEvent.stepIndex ?? stepEvent.index, aiMessage.steps)
          let grepStep =
            _gi != null
              ? aiMessage.steps[_gi]
              : [...(aiMessage.steps || [])].reverse().find(
                  (s) => s && (s.title === 'grep' || (s.title && String(s.title).includes('grep')))
                )
          if (!grepStep && runningStep) grepStep = runningStep
          if (grepStep) {
            try {
              grepStep.grepNavigation = JSON.parse(JSON.stringify(navigationData))
            } catch {
              grepStep.grepNavigation = navigationData
            }
          }
        }

        const createPending =
          aiMessage.modifyNavigation?.is_create === true &&
          aiMessage.modifyNavigation?.confirmation_required !== false
        if (createPending) {
          console.log('[GREP-NAV] 新建待澄清卡片，仅保存导航不自动跳转')
        } else {
          handleNavigation(navigationData)
        }
      } else {
        console.log('[GREP-NAV] 未找到navigation字段')
      }
    } else {
      const resultStr =
        typeof outputData === 'string' ? outputData : JSON.stringify(outputData, null, 2)
      aiMessage.executionResults.push({
        step: runningStep.title,
        text: resultStr
      })
    }
  }
}
