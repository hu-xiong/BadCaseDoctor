/**
 * ReAct SSE：observation（v1 tool end/error → legacy stepEvent）大段 UI 状态写入。
 * 从 SimpleChatPanel 迁入，便于单测与继续收敛解析路径。
 */
import { nextTick } from 'vue'
import { getStableCreatedId } from '../utils/createPreviewKeys.js'
import { i18n } from '../i18n/index.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'

/** 详情字段列表（不在列表中显示的字段，用于沙箱预览分组） */
export const DETAIL_FIELDS = [
  'base_problem',
  'reproduction_steps',
  'answer',
  'correct_answer',
  'badcase_result',
  'solution',
  'problem_reason',
  'description',
  'steps_to_reproduce',
  'expected_result',
  'actual_result',
  'preconditions',
  'steps',
  'remark',
  'baseline',
  'reproduce_steps'
]

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
  if (t.includes('create')) return 'create'
  if (t.includes('browser_test')) return 'browser_test'
  if (t.includes('log_analyzer')) return 'log_analyzer'
  if (t.includes('search')) return 'search'
  return ''
}

/** 从 observation 生成人类可读的一行结果摘要 */
export const buildStepResultSummary = (outputData, toolName, toolData) => {
  const t = i18n.global.t.bind(i18n.global)
  const d = toolData && typeof toolData === 'object' ? toolData : {}
  const tool = toolName || outputData?.tool || ''
  const listSep = i18n.global.locale.value === 'en' ? ', ' : '，'
  if (d.error) return t('chat.stepErr', { msg: d.error })
  if (tool === 'grep' || d.testcase_location || d.bug_location || d.badcase_analysis || d.plan_tree) {
    const tc = d.testcase_location?.length ?? 0
    const bugs = d.bug_location?.length ?? 0
    const bc = d.badcase_analysis?.length ?? 0
    if (d.summary && typeof d.summary === 'string') return d.summary.slice(0, 400)
    const parts = []
    if (tc) parts.push(t('chat.stepNTestcases', { n: tc }))
    if (bugs) parts.push(t('chat.stepNBugs', { n: bugs }))
    if (bc) parts.push(t('chat.stepNBadcases', { n: bc }))
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
  if (tool === 'create' || (d.preview && typeof d.preview === 'object' && d.target)) {
    const title = d.preview?.title
    if (title) return t('chat.stepCreatePreview', { title })
    return d.message || t('chat.stepCreateReady')
  }
  if (d.message) return String(d.message).slice(0, 400)
  if (outputData?.success === false) return t('chat.stepFailed')
  return t('chat.stepDone')
}

/**
 * @param {object} aiMessage
 * @param {object} stepEvent event === 'observation'
 * @param {object} ctx
 * @param {function} ctx.resolveStreamStepIndex
 * @param {function} ctx.appendStepDetailLine
 * @param {function} [ctx.nextTick] 默认使用 vue.nextTick
 * @param {function} ctx.handleShowGroupInList
 * @param {number|null|undefined} ctx.projectId
 * @param {function} ctx.handleNavigation
 */
export function applyReactObservationLegacyStepEvent(aiMessage, stepEvent, ctx) {
  const resolveStreamStepIndex = ctx.resolveStreamStepIndex
  const appendStepDetailLine = ctx.appendStepDetailLine
  const tick = ctx.nextTick || nextTick
  const handleShowGroupInList = ctx.handleShowGroupInList
  const projectId = ctx.projectId
  const handleNavigation = ctx.handleNavigation

  console.log('[CHAT-STREAM] === 触发 observation 事件 ===')
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
    if (ot && ['grep', 'create', 'modify'].includes(String(ot))) {
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
            s.title === 'grep' ||
            s.title.includes('grep'))
      ) ||
      aiMessage.steps[aiMessage.steps.length - 1]
    console.log('[CHAT-STREAM] 没有找到 running 步骤，使用:', runningStep?.title)
  }
  if (_obsIdx != null && runningStep) {
    const tn = observationTool || (outputData && typeof outputData === 'object' ? outputData.tool : '')
    if (tn && ['grep', 'create', 'modify', 'search', 'database_query'].includes(String(tn))) {
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

  freezeThoughtSnapshotForStep(runningStep)
  runningStep.status = 'completed'
  const od = typeof outputData === 'object' && outputData !== null ? outputData : {}
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
    if (runningStep.stepStartedAt != null) {
      runningStep.stepDurationMs = Date.now() - runningStep.stepStartedAt
    }
    let resolvedTool =
      observationTool || (outputData && outputData.tool) || extractToolName(runningStep.title)
    if (!resolvedTool && outputData && typeof outputData === 'object') {
      const flat = outputData.data && typeof outputData.data === 'object' ? outputData.data : outputData
      if (
        flat &&
        !flat.created_id &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        ['testcase', 'bug', 'badcase', 'plan'].includes(flat.target)
      ) {
        resolvedTool = 'create'
      }
    }
    const td0 = outputData?.data || outputData
    if (typeof td0 === 'object' && td0 !== null) {
      runningStep.resultSummary = buildStepResultSummary(outputData, resolvedTool, td0)
      appendStepDetailLine(runningStep, `── 结果 ──\n${runningStep.resultSummary}`)
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
        !flat.created_id &&
        flat.preview &&
        typeof flat.preview === 'object' &&
        ['testcase', 'bug', 'badcase', 'plan'].includes(flat.target)
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
      if (existingCount > 0 && existingCount === newCount && existingNav?.target === toolData.target) {
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
            const itemId = parseInt(rr?.target_id || r?.target_id || rr?.id || r?.id)
            const itemPlanId =
              (rr?.plan_id ?? r?.plan_id) != null ? parseInt(rr?.plan_id ?? r?.plan_id) : null

            if (isNaN(itemId)) {
              console.warn('[MODIFY] 跳过无效 ID:', r.target_id || r.id)
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
              console.log(
                '[MODIFY-DEBUG] fieldDiff.field:',
                fname,
                'isDetail:',
                DETAIL_FIELDS.includes(fname)
              )
              if (DETAIL_FIELDS.includes(fname)) {
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
              target: rr?.target || r?.target || toolData.target || 'badcase',
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
              target: toolData.target || 'badcase'
            }
          } else {
            const planGroups = {}
            allItems.forEach((item) => {
              const planKey = item.plan_id !== null ? String(item.plan_id) : 'unplanned'
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
                        plan_id: planId === 'unplanned' ? null : parseInt(planId),
                        target: toolData.target || currentGroup[0]?.target || 'badcase',
                        items: [...currentGroup]
                      })
                    }
                    currentGroup = [item]
                  }
                }
              })

              if (currentGroup.length > 0) {
                modifyGroups.push({
                  plan_id: planId === 'unplanned' ? null : parseInt(planId),
                  target: toolData.target || currentGroup[0]?.target || 'badcase',
                  items: [...currentGroup]
                })
              }
            })

            aiMessage.modifyGroups = Object.freeze([...modifyGroups])
            aiMessage.modifyNavigation = {
              batch_modify: true,
              batch_results: [...allItems],
              batch_count: allItems.length,
              target: allItems[0]?.target || toolData.target || 'badcase'
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
        aiMessage.modifyNavigation = {
          target: toolData.target,
          target_id: toolData.target_id,
          diff: toolData.diff,
          modifications: toolData.modifications,
          confirmation_required: true
        }
        console.log('[MODIFY] 存储沙箱预览导航:', aiMessage.modifyNavigation)
      } else if (toolData.diff && toolData.before && toolData.after) {
        aiMessage.modifyNavigation = {
          target: toolData.target || 'bug',
          target_id: toolData.target_id,
          diff: toolData.diff,
          before: toolData.before,
          after: toolData.after,
          plan_id: toolData.before?.plan_id,
          success: toolData.success,
          message: toolData.message
        }
        console.log('[MODIFY] 存储单个修改导航:', aiMessage.modifyNavigation)
      }
    }

    if (toolName === 'create' && toolData && typeof toolData === 'object') {
      const hasDiff = Array.isArray(toolData.diff) && toolData.diff.length > 0
      const hasPreview = toolData.preview && typeof toolData.preview === 'object' && Object.keys(toolData.preview).length > 0
      const looksLikePreview =
        toolData.success !== false && !toolData.created_id && (hasDiff || hasPreview)
      if (looksLikePreview) {
        const pv = toolData.preview && typeof toolData.preview === 'object' ? toolData.preview : {}
        const adoptedId =
          projectId != null
            ? getStableCreatedId(projectId, toolData.target || 'testcase', pv)
            : null
        if (adoptedId != null) {
          const planIdNav = pv.plan_id ?? pv.planId
          aiMessage.modifyNavigation = {
            target: toolData.target || 'bug',
            target_id: adoptedId,
            preview: toolData.preview,
            plan_id: planIdNav,
            confirmation_required: false,
            navigate_to_existing: true,
            created_id: adoptedId,
            is_create: false,
            diff: hasDiff ? toolData.diff : []
          }
          window.dispatchEvent(
            new CustomEvent('grep-navigate', {
              detail: {
                planId: planIdNav,
                bugId: adoptedId,
                target: toolData.target || 'bug'
              },
              bubbles: true
            })
          )
          console.log('[CREATE] 稳定键已采纳，改为定位已存在行:', adoptedId)
        } else {
          aiMessage.modifyNavigation = {
            target: toolData.target || 'testcase',
            target_id: 'new',
            diff: hasDiff ? toolData.diff : [],
            preview: toolData.preview,
            modifications: toolData.preview || {},
            confirmation_required: true,
            is_create: true
          }
        }
        console.log('[CREATE] 存储新建预览（modifyNavigation）:', aiMessage.modifyNavigation)
      } else if (toolData.success === false || toolData.error) {
        const errText = toolData.error || toolData.message || '新建预览失败'
        aiMessage.executionResults.push({
          step: runningStep.title,
          text: `create：${errText}`,
          success: false
        })
        console.warn('[CREATE] 工具返回失败，未生成预览:', toolData)
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

        handleNavigation(navigationData)
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
