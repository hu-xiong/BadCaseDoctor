<template>
  <div v-show="visible" class="report-viewer">
    <div class="report-viewer-header">
      <div class="report-viewer-titles">
        <span class="report-viewer-kind">{{ isCdp ? '🧪' : '🤖' }}</span>
        <span class="report-viewer-title" :title="displayTitle">{{ displayTitle }}</span>
        <span v-if="report" class="report-status-chip" :class="statusClass(report.status)">
          {{ statusLabel(report.status) }}
        </span>
      </div>
      <div class="report-viewer-actions">
        <button
          type="button"
          class="report-action-btn"
          :disabled="loading"
          @click="fetchDetail"
        >
          {{ loading ? t('reportView.refreshing') : t('reportView.refresh') }}
        </button>
        <button type="button" class="report-action-btn" @click="$emit('close')">
          {{ t('reportView.close') }}
        </button>
      </div>
    </div>

    <div v-if="loading && !report" class="report-state">
      {{ t('reportView.loading') }}
    </div>
    <div v-else-if="loadError" class="report-state report-state--error">
      {{ t('reportView.loadFail') }}
    </div>
    <div v-else-if="!report" class="report-state">
      {{ t('reportView.notFound') }}
    </div>

    <div v-else class="report-viewer-body">
      <div class="report-meta-row">
        <span v-if="report.created_at">
          {{ t('reportView.createdAt') }} {{ fmtTime(report.created_at) }}
        </span>
        <span v-if="report.finished_at">
          {{ t('reportView.finishedAt') }} {{ fmtTime(report.finished_at) }}
        </span>
        <span v-if="report.session_title" :title="report.session_title">
          {{ t('reportView.session') }} {{ report.session_title }}
        </span>
        <span v-if="isCdp && report.mode">{{ t('reportView.mode') }} {{ modeLabel }}</span>
        <span v-if="isAgentRun && report.model_name">
          {{ t('reportView.model') }} {{ report.model_name }}
        </span>
      </div>

      <!-- CDP 测试报告 -->
      <template v-if="isCdp">
        <div class="report-stats">
          <div class="report-stat">
            <span class="report-stat-num ok">{{ report.pass_count || 0 }}</span>
            <span class="report-stat-lbl">{{ t('reportView.passCount') }}</span>
          </div>
          <div class="report-stat">
            <span class="report-stat-num fail">{{ report.fail_count || 0 }}</span>
            <span class="report-stat-lbl">{{ t('reportView.failCount') }}</span>
          </div>
          <div class="report-stat">
            <span class="report-stat-num">{{ steps.length }}</span>
            <span class="report-stat-lbl">{{ t('reportView.stepCount') }}</span>
          </div>
        </div>

        <div v-if="report.summary" class="report-section">
          <div class="report-section-title">{{ t('reportView.summary') }}</div>
          <p class="report-summary-text">{{ report.summary }}</p>
        </div>

        <div class="report-section">
          <div class="report-section-title">{{ t('reportView.steps') }}</div>
          <div v-if="!steps.length" class="report-empty-small">
            {{ t('reportView.noSteps') }}
          </div>
          <div
            v-for="(st, i) in steps"
            :key="i"
            class="report-step"
            :class="{ fail: st.success === false }"
          >
            <span class="report-step-icon">{{ st.success === false ? '✗' : '✓' }}</span>
            <div class="report-step-main">
              <div class="report-step-title">
                <span class="report-step-action">{{ st.action || '#' + (st.index || i + 1) }}</span>
                <span v-if="st.duration_ms != null" class="report-step-dur">
                  {{ st.duration_ms }} ms
                </span>
              </div>
              <div v-if="st.summary" class="report-step-summary">{{ st.summary }}</div>
              <div v-if="st.url" class="report-step-url" :title="st.url">{{ st.url }}</div>
              <ul v-if="stepIssues(st).length" class="report-step-issues">
                <li v-for="(iss, ii) in stepIssues(st)" :key="ii">{{ issueText(iss) }}</li>
              </ul>
            </div>
          </div>
        </div>
      </template>

      <!-- Agent 整轮运行 -->
      <template v-else>
        <div class="report-section">
          <div class="report-section-title">{{ t('reportView.userInput') }}</div>
          <pre class="report-pre">{{ report.user_input || report.title || '' }}</pre>
        </div>
        <p v-if="isInterrupted" class="report-hint">{{ t('reportView.interruptedHint') }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getReportDetail } from '../api.js'
import { reportStatusClass, reportStatusLabel } from '../utils/reportStatus.js'

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  /** 工作台 Tab 实例：meta.reportKind / meta.reportId / meta.reportTitle */
  tab: { type: Object, default: null },
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'update-meta'])

const { t } = useI18n()

const meta = computed(() => props.tab?.meta || {})
const reportKind = computed(() => String(meta.value.reportKind || ''))
const reportId = computed(() => String(meta.value.reportId || ''))

const report = ref(null)
const loading = ref(false)
const loadError = ref(false)
/** 已成功加载的 kind:id，避免同一报告重复请求 */
const loadedKey = ref('')

const isCdp = computed(() => reportKind.value === 'cdp_test')
const isAgentRun = computed(() => reportKind.value === 'agent_run')
const steps = computed(() =>
  isCdp.value && Array.isArray(report.value?.steps_json) ? report.value.steps_json : []
)
const displayTitle = computed(
  () => report.value?.title || meta.value.reportTitle || t('reportView.title')
)
const isInterrupted = computed(() =>
  ['cancelled', 'interrupted'].includes(String(report.value?.status || '').toLowerCase())
)

const MODE_LABEL_KEYS = {
  testcase: 'reportView.modeTestcase',
  explore: 'reportView.modeExplore',
  manual: 'reportView.modeManual'
}
const modeLabel = computed(() => {
  const k = MODE_LABEL_KEYS[String(report.value?.mode || '').toLowerCase()]
  return k ? t(k) : String(report.value?.mode || '')
})

const statusLabel = (st) => reportStatusLabel(t, st)
const statusClass = reportStatusClass

const fetchDetail = async () => {
  const kind = reportKind.value
  const id = reportId.value
  if (!kind || !id) return
  const key = kind + ':' + id
  loading.value = true
  loadError.value = false
  try {
    const res = await getReportDetail(kind, id)
    const data = res?.data || {}
    if (data.success && data.report) {
      report.value = data.report
      loadedKey.value = key
      const title = data.report.title
      if (title) {
        emit('update-meta', { title, reportTitle: title, reportKind: kind, reportId: id })
      }
    } else {
      loadError.value = true
    }
  } catch (e) {
    console.warn('[ReportViewerPanel] 加载报告详情失败:', e)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.visible, reportId.value, reportKind.value],
  ([vis]) => {
    if (!vis) return
    const key = reportKind.value + ':' + reportId.value
    if (key && key !== loadedKey.value) void fetchDetail()
  },
  { immediate: true }
)

const stepIssues = (st) => (Array.isArray(st?.issues) ? st.issues : [])
const issueText = (iss) => {
  if (iss == null) return ''
  if (typeof iss === 'string') return iss
  return String(iss.title || iss.summary || iss.message || JSON.stringify(iss))
}

const pad2 = (n) => String(n).padStart(2, '0')
const fmtTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
</script>

<style scoped>
.report-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #fff;
}

.report-viewer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #ececec;
  flex-shrink: 0;
}

.report-viewer-titles {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.report-viewer-kind {
  font-size: 14px;
  flex-shrink: 0;
}

.report-viewer-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-viewer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.report-action-btn {
  border: 1px solid #dcdfe3;
  background: #fff;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: #444;
  cursor: pointer;
  transition: background-color 0.15s;
}

.report-action-btn:hover {
  background: #f2f5f9;
}

.report-action-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.report-status-chip {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 8px;
  flex-shrink: 0;
  background: #f0f0f0;
  color: #777;
}

.report-state {
  padding: 18px 14px;
  color: #888;
  font-size: 13px;
}

.report-state--error {
  color: #c0392b;
}

.report-viewer-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 14px 24px;
}

.report-meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: #888;
  margin-bottom: 12px;
}

.report-stats {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.report-stat {
  flex: 1;
  min-width: 0;
  border: 1px solid #ececec;
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.report-stat-num {
  font-size: 18px;
  font-weight: 600;
  color: #444;
}

.report-stat-num.ok {
  color: #2e7d32;
}

.report-stat-num.fail {
  color: #c0392b;
}

.report-stat-lbl {
  font-size: 11px;
  color: #999;
}

.report-section {
  margin-bottom: 16px;
}

.report-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 6px;
}

.report-summary-text {
  font-size: 13px;
  color: #444;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.report-pre {
  font-size: 12px;
  color: #333;
  background: #f8f9fb;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.report-hint {
  font-size: 12px;
  color: #b26a00;
  background: #fff4e5;
  border-radius: 6px;
  padding: 8px 10px;
  margin: 0;
}

.report-empty-small {
  font-size: 12px;
  color: #999;
  padding: 6px 0;
}

.report-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  border: 1px solid #ececec;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}

.report-step.fail {
  border-color: #f3c2bc;
  background: #fffafa;
}

.report-step-icon {
  font-size: 12px;
  color: #2e7d32;
  line-height: 18px;
  flex-shrink: 0;
}

.report-step.fail .report-step-icon {
  color: #c0392b;
}

.report-step-main {
  flex: 1;
  min-width: 0;
}

.report-step-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.report-step-action {
  font-size: 12px;
  font-weight: 600;
  color: #444;
}

.report-step-dur {
  font-size: 11px;
  color: #999;
}

.report-step-summary {
  font-size: 12px;
  color: #555;
  margin-top: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}

.report-step-url {
  font-size: 11px;
  color: #1a73e8;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-step-issues {
  margin: 4px 0 0;
  padding-left: 16px;
  font-size: 11px;
  color: #b26a00;
}

/* 状态色：chip 与行内共用 */
.st-running { color: #1a73e8; }
.report-status-chip.st-running { background: #e8f1fd; color: #1a73e8; }
.st-passed { color: #2e7d32; }
.report-status-chip.st-passed { background: #e6f4ea; color: #2e7d32; }
.st-completed { color: #2e7d32; }
.report-status-chip.st-completed { background: #e6f4ea; color: #2e7d32; }
.st-failed { color: #c0392b; }
.report-status-chip.st-failed { background: #fdecea; color: #c0392b; }
.st-partial { color: #b26a00; }
.report-status-chip.st-partial { background: #fff4e5; color: #b26a00; }
.st-blocked { color: #8a8a8a; }
.report-status-chip.st-blocked { background: #f0f0f0; color: #8a8a8a; }
.st-cancelled { color: #8a8a8a; }
.report-status-chip.st-cancelled { background: #f0f0f0; color: #8a8a8a; }
.st-unknown { color: #8a8a8a; }
</style>
