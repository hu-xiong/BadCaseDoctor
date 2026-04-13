/**
 * ReAct 流式消息初始 state 工厂（与 SimpleChatPanel handleReactAgentMode 对齐）。
 * 需求文档：后续由 useAgentStream 统一创建与 reducer 更新。
 */
export function createReactAiMessageState(id) {
  return {
    id: id ?? Date.now() + 1,
    isUser: false,
    content: '',
    time: new Date().toLocaleTimeString(),
    understanding: '...',
    steps: [],
    finalResponse: '',
    reasoningContent: '',
    thinkReasoningDraft: '',
    thinkContentDraft: '',
    lastReactPhase: null,
    reasoningDisplayContent: '',
    reasoningStreamActive: false,
    _reasoningPhaseLive: false,
    todosStreamDraft: '',
    todosStreamVisible: '',
    summaryStreamDraft: '',
    /** 增量运行总览（Markdown，lane=running_summary） */
    runningSummaryDraft: '',
    runningSummaryVersion: 0,
    thoughtCollapsed: false,
    reasoningPhaseStartTs: null,
    reasoningUiDurationMs: null,
    reasoningUiKind: null,
    reasoningBriefThresholdMs: null,
    showReasoning: true,
    agentResult: { findings: [], recommendations: [], status: 'running' },
    allObservations: [],
    evidences: [],
    executionResults: [],
    searchResults: [],
    reactPlanSteps: null,
    planUpdateReason: '',
    reactPlanPanelSuppressed: false,
    hadAgentThinkPhase: false,
    /** 规划备忘显隐：先给“正在生成任务规划…”占位，稍后再揭示 AgentTaskRun 顶部计划区 */
    _planMemoRevealReady: false,
    /** 曾收到 suppress 的 plan_init：后续 plan_update 不得抢先揭示规划备忘，须等 THINK 正文 */
    _deferPlanMemoUntilThink: false,
    reactMainLoopFinished: false,
    /** 底部「总结」块：LLM 生成中（沙箱已出、正文未到等） */
    unifiedSummaryLoading: false,
    sseMirror: null,
    /** 大模型判定纯对话：不展示分步 Thought/总结条，正文走 finalResponse（可配合 summary_stream 拼接） */
    reactDirectChatReply: false,
    /** SSE client_action：本地 wget/curl 下载脚本提示卡片（用户自行在终端执行） */
    clientLocalRunCards: [],
    /** SSE client_action kind=terminal_exec：待本机执行队列（handleReactAgentMode 尾部消费） */
    pendingTerminalExecQueue: [],
    /** 终端子 Agent 卡片（展示命令与执行状态） */
    clientTerminalExecCards: []
  }
}
