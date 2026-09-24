<template>
  <section class="evidence-panel" :aria-label="mode === 'ui' ? 'UI节点证据' : '采集参数证据'">
    <p class="scope-note">
      CDP 仅采集浏览器可见报文，不含服务端完整 trace。旧数据无可靠运行归属时不显示；采集 URL 仅作文本展示，不会自动打开。
    </p>
    <div class="toolbar">
      <h2>{{ mode === 'ui' ? 'UI节点' : '采集参数' }}</h2>
      <button type="button" :disabled="loading || candidatesLoading || saving || !badcaseId" @click="refresh">刷新证据与候选</button>
    </div>
    <p class="muted">证据关联独立保存，不保存或覆盖基本信息。解除关联仅移除关系，不删除运行记录。</p>
    <p v-if="saving" role="status">正在保存证据关联，请勿重复提交…</p>
    <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
    <div v-if="saveError" class="error-message" role="alert">
      <span>{{ saveError }}</span>
      <button type="button" :disabled="loading || saving" @click="loadEvidence">重新读取关联</button>
    </div>

    <details class="candidate-picker" open>
      <summary>关联同项目运行（最近 50 条）</summary>
      <p v-if="!projectId" class="empty-state">未取得已保存详情的项目，暂时无法选择候选运行。</p>
      <p v-else-if="candidatesLoading" role="status">正在加载运行候选…</p>
      <div v-else-if="candidatesError" class="error-message" role="alert">
        <span>{{ candidatesError }}</span>
        <button type="button" :disabled="saving" @click="loadCandidates">重试候选列表</button>
      </div>
      <template v-else-if="candidatesLoaded">
        <p v-if="!candidates.length" class="empty-state">本项目暂无可关联的 CDP 测试运行。</p>
        <p v-else-if="!eligibleCandidates.length" class="empty-state">列表中的运行均已关联。</p>
        <div v-else class="candidate-list">
          <label v-for="run in eligibleCandidates" :key="run.id" class="candidate-row">
            <input v-model="selectedCandidates" type="checkbox" :value="String(run.id)" :disabled="!canSave" />
            <span>
              <strong>{{ display(run.title) }}</strong>
              <small>ID：{{ run.id }} · {{ display(run.status) }} · {{ display(run.created_at) }}</small>
              <small>CDP 会话：{{ display(run.cdp_session_id) }}</small>
            </span>
          </label>
        </div>
        <button type="button" class="primary-button" :disabled="!canSave || !selectedCandidates.length" @click="associateSelected">
          关联所选运行（{{ selectedCandidates.length }}）
        </button>
      </template>
    </details>

    <p v-if="!badcaseId" class="empty-state">请先保存 BadCase 后查看证据。</p>
    <p v-else-if="loading" role="status">正在加载已关联运行和证据…</p>
    <div v-else-if="evidenceError" class="error-message" role="alert">
      <span>{{ evidenceError }}</span>
      <button type="button" :disabled="saving" @click="loadEvidence">重试证据读取</button>
    </div>
    <template v-else-if="evidence">
      <p v-if="!linkedIds.length" class="empty-state">尚未关联运行。请从同项目候选中选择并关联；不会自动匹配历史报文。</p>
      <template v-else>
        <h3>已关联运行（{{ linkedIds.length }}）</h3>
        <div class="linked-runs" aria-label="已关联运行列表">
          <div v-for="item in linkedRuns" :key="item.id" class="linked-run" :class="{ selected: selectedRunId === item.id }">
            <button type="button" class="run-selector" :aria-pressed="selectedRunId === item.id" @click="selectedRunId = item.id">
              <strong>{{ item.run ? display(item.run.title) : '运行不可用' }}</strong>
              <small>ID：{{ item.id }}</small>
              <small>{{ item.run ? display(item.run.status) : '记录不存在、无权限或归属不可用' }}</small>
              <small v-if="item.run">{{ display(item.run.created_at) }}</small>
            </button>
            <button type="button" class="unlink-button" :disabled="!canSave" :aria-label="`解除运行 ${item.id} 的关联（不删除记录）`" @click="unlinkRun(item.id)">解除关联</button>
          </div>
        </div>
        <p v-if="!activeRun" class="empty-state">此关联运行不可用，无法显示其证据。可刷新重试或仅解除关联。</p>
        <article v-else :key="selectedRunId" class="run-detail">
          <h3>{{ display(activeRun.title) }}</h3>
          <dl class="metadata">
            <div><dt>运行 ID</dt><dd>{{ activeRun.id }}</dd></div>
            <div><dt>运行状态</dt><dd>{{ display(activeRun.status) }}</dd></div>
            <div><dt>创建时间</dt><dd>{{ display(activeRun.created_at) }}</dd></div>
          </dl>
          <pre v-if="hasValue(activeRun.summary)" class="text-block">{{ display(activeRun.summary) }}</pre>

          <section v-show="mode === 'capture'" aria-label="浏览器报文">
            <h3>浏览器报文（{{ exchanges.length }}）</h3>
            <p class="muted">采集状态：{{ captureStatusLabel(activeRun.capture_status) }}。TTFB 为首字节时间，不等同于首 token 时间（TTFT）。耗时单位为 ms。</p>
            <p v-if="activeRun.exchanges_truncated" class="warning-message">仅展示最近 20 条报文。</p>
            <p v-if="!exchanges.length" class="empty-state">
              {{ activeRun.capture_status === 'not_captured' ? '已关联此运行，但未采集到可归属的浏览器报文。' : '已关联此运行，但没有可展示的浏览器报文。' }}
            </p>
            <details v-for="(exchange, index) in exchanges" :key="index" class="record-card">
              <summary>报文 {{ index + 1 }} · {{ display(exchange.request?.model ?? exchange.response?.model) }} · 状态 {{ display(exchange.status) }}</summary>
              <dl class="metadata">
                <div v-for="field in exchangeFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ display(exchange[field.key]) }}</dd></div>
              </dl>
              <p v-if="exchange.body_clipped === true" class="warning-message">报文正文已截断，下方内容不完整。</p>
              <p v-if="exchange.model_mismatch === true" class="warning-message">请求模型与响应模型不一致，请分别核对。</p>
              <h4>Request / 请求</h4>
              <div v-for="field in requestFields" :key="field.key" class="payload-field">
                <h5>{{ field.label }}</h5>
                <pre class="text-block">{{ display(exchange.request?.[field.key]) }}</pre>
              </div>
              <h4>Response / 响应</h4>
              <div v-for="field in responseFields" :key="field.key" class="payload-field">
                <h5>{{ field.label }}</h5>
                <pre class="text-block">{{ display(exchange.response?.[field.key]) }}</pre>
              </div>
            </details>
          </section>

          <section v-show="mode === 'ui'" aria-label="节点快照与报告步骤">
            <h3>UI 节点快照（{{ snapshots.length }}）</h3>
            <p v-if="!snapshots.length" class="empty-state">已关联此运行，但没有 UI 节点快照。报告步骤不等同于节点快照。</p>
            <details v-for="(snapshot, index) in snapshots" :key="snapshot.snapshot_id ?? index" class="record-card" open>
              <summary>快照 {{ index + 1 }} · {{ display(snapshot.title) }}</summary>
              <dl class="metadata">
                <div><dt>快照 ID</dt><dd>{{ display(snapshot.snapshot_id) }}</dd></div>
                <div><dt>URL（仅文本）</dt><dd>{{ display(snapshot.url) }}</dd></div>
                <div><dt>是否截断</dt><dd>{{ display(snapshot.truncated) }}</dd></div>
              </dl>
              <p v-if="snapshot.truncated === true" class="warning-message">此快照已截断，节点列表不完整。</p>
              <p v-if="!objects(snapshot.nodes).length" class="empty-state">此快照未记录节点。</p>
              <div v-else class="table-scroll" tabindex="0" aria-label="节点列表（可横向滚动）">
                <table>
                  <thead><tr><th>ref</th><th>role</th><th>name</th><th>disabled</th><th>selector_hint</th></tr></thead>
                  <tbody>
                    <tr v-for="(node, nodeIndex) in objects(snapshot.nodes)" :key="nodeIndex">
                      <td>{{ display(node.ref) }}</td><td>{{ display(node.role) }}</td><td>{{ display(node.name) }}</td><td>{{ display(node.disabled) }}</td><td>{{ display(node.selector_hint) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>
            <h3>报告步骤（操作记录，非 UI 节点快照）</h3>
            <p v-if="!steps.length" class="empty-state">此运行没有报告步骤。</p>
            <details v-for="(step, index) in steps" :key="index" class="record-card">
              <summary>步骤 {{ display(step.index) }} · {{ display(step.action) }} · {{ step.success === true ? '成功' : step.success === false ? '失败' : '结果未知' }}</summary>
              <dl class="metadata">
                <div><dt>ref</dt><dd>{{ display(step.ref) }}</dd></div>
                <div><dt>耗时（ms）</dt><dd>{{ display(step.duration_ms) }}</dd></div>
                <div><dt>URL（仅文本）</dt><dd>{{ display(step.url) }}</dd></div>
              </dl>
              <pre class="text-block">{{ display(step.summary) }}</pre>
            </details>
          </section>
        </article>
      </template>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { getBadcaseEvidence, getProjectCdpTestRuns, updateBadcaseEvidence } from '../api.js'

const props = defineProps({
  badcaseId: { type: [String, Number], default: '' },
  projectId: { type: [String, Number], default: '' },
  active: { type: Boolean, default: false },
  mode: { type: String, default: 'capture' }
})

const evidence = ref(null)
const loading = ref(false)
const evidenceError = ref('')
const candidates = ref([])
const candidatesLoading = ref(false)
const candidatesLoaded = ref(false)
const candidatesError = ref('')
const selectedCandidates = ref([])
const selectedRunId = ref('')
const saveError = ref('')
const notice = ref('')
const pendingSaveIds = reactive(new Set())
const currentId = computed(() => String(props.badcaseId ?? ''))
const saving = computed(() => pendingSaveIds.has(currentId.value))
const canSave = computed(() => !!evidence.value && !loading.value && !saving.value && !evidenceError.value && !saveError.value)
let contextVersion = 0
let evidenceRequest = 0
let candidatesRequest = 0
let disposed = false

const hasValue = (value) => value !== undefined && value !== null && value !== ''
const display = (value) => {
  if (!hasValue(value)) return '—'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}
const objects = (value) => Array.isArray(value) ? value.filter((item) => item && typeof item === 'object' && !Array.isArray(item)) : []
const ids = (value) => [...new Set((Array.isArray(value) ? value : []).filter(hasValue).map(String))]
const linkedIds = computed(() => ids(evidence.value?.run_ids))
const linkedRuns = computed(() => {
  const unavailable = new Set(ids(evidence.value?.unavailable_run_ids))
  const runs = new Map(objects(evidence.value?.runs).map((run) => [String(run.id), run]))
  // 不展示不在 run_ids 中的记录，也不以会话/时间猜测旧采集的归属。
  return linkedIds.value.map((id) => ({ id, run: unavailable.has(id) ? null : runs.get(id) ?? null }))
})
const activeRun = computed(() => linkedRuns.value.find((item) => item.id === selectedRunId.value)?.run ?? null)
const eligibleCandidates = computed(() => candidates.value.filter((run) => !linkedIds.value.includes(String(run.id))))
const exchanges = computed(() => objects(activeRun.value?.exchanges))
const snapshots = computed(() => objects(activeRun.value?.snapshots))
const steps = computed(() => objects(activeRun.value?.steps))
const captureStatusLabel = (value) => ({ available: '可用', not_captured: '未采集' }[value] ?? '未知')

const exchangeFields = [
  { key: 'ts', label: '采集时间' }, { key: 'url', label: 'URL（仅文本）' },
  { key: 'status', label: '状态' }, { key: 'ttfb_ms', label: 'TTFB（ms）' },
  { key: 'duration_ms', label: '总耗时（ms）' }, { key: 'error', label: '错误' },
  { key: 'body_clipped', label: '正文截断' }, { key: 'model_mismatch', label: '模型不一致' }
]
const requestFields = [
  { key: 'model', label: 'model / 请求模型' }, { key: 'params', label: 'params / 采集参数' },
  { key: 'system_prompt', label: 'system_prompt / 系统提示词' }, { key: 'messages', label: 'messages / 消息' },
  { key: 'tools', label: 'tools / 工具定义' }
]
const responseFields = [
  { key: 'model', label: 'model / 响应模型' }, { key: 'text', label: 'text / 输出文本' },
  { key: 'tool_calls', label: 'tool_calls / 工具调用' }, { key: 'usage', label: 'usage / 用量' },
  { key: 'finish_reason', label: 'finish_reason / 结束原因' }
]

function errorMessage(error, fallback) {
  const detail = error?.response?.data?.error ?? error?.response?.data?.message ?? error?.message
  const status = error?.response?.status
  return `${fallback}${status ? `（HTTP ${status}）` : ''}${hasValue(detail) ? `：${display(detail)}` : ''}`
}

function parseEvidence(response) {
  const data = response?.data
  if (data?.success !== true || !Array.isArray(data.evidence?.run_ids) || !Array.isArray(data.evidence?.runs)) {
    throw new Error(display(data?.error ?? data?.message ?? '证据响应格式不正确'))
  }
  return data.evidence
}

function applyEvidence(value) {
  evidence.value = value
  if (!linkedIds.value.includes(selectedRunId.value)) selectedRunId.value = linkedIds.value[0] ?? ''
  selectedCandidates.value = selectedCandidates.value.filter((id) => eligibleCandidates.value.some((run) => String(run.id) === id))
}

function isCurrent(version, id) {
  return !disposed && version === contextVersion && id === currentId.value
}

async function loadEvidence() {
  if (!currentId.value || saving.value || disposed) return
  const version = contextVersion
  const id = currentId.value
  const request = ++evidenceRequest
  loading.value = true
  evidenceError.value = ''
  notice.value = ''
  evidence.value = null
  try {
    const response = await getBadcaseEvidence(id)
    if (!isCurrent(version, id) || request !== evidenceRequest) return
    applyEvidence(parseEvidence(response))
    saveError.value = ''
  } catch (error) {
    if (isCurrent(version, id) && request === evidenceRequest) evidenceError.value = errorMessage(error, '证据加载失败')
  } finally {
    if (isCurrent(version, id) && request === evidenceRequest) loading.value = false
  }
}

async function loadCandidates() {
  if (!props.projectId || disposed || saving.value) return
  const version = contextVersion
  const id = currentId.value
  const projectId = String(props.projectId)
  const request = ++candidatesRequest
  candidatesLoading.value = true
  candidatesError.value = ''
  candidatesLoaded.value = false
  candidates.value = []
  try {
    const response = await getProjectCdpTestRuns(projectId, 50)
    if (!isCurrent(version, id) || request !== candidatesRequest) return
    if (response.data?.success !== true || !Array.isArray(response.data.runs)) {
      throw new Error(display(response.data?.error ?? response.data?.message ?? '候选响应格式不正确'))
    }
    candidates.value = [...new Map(objects(response.data.runs).filter((run) => hasValue(run.id)).map((run) => [String(run.id), run])).values()]
    candidatesLoaded.value = true
    selectedCandidates.value = selectedCandidates.value.filter((selected) => eligibleCandidates.value.some((run) => String(run.id) === selected))
  } catch (error) {
    if (isCurrent(version, id) && request === candidatesRequest) candidatesError.value = errorMessage(error, '运行候选加载失败')
  } finally {
    if (isCurrent(version, id) && request === candidatesRequest) candidatesLoading.value = false
  }
}

function refresh() {
  if (saving.value) return
  loadEvidence()
  loadCandidates()
}

async function saveLinks(nextIds) {
  if (!canSave.value || !currentId.value) return
  const version = contextVersion
  const id = currentId.value
  pendingSaveIds.add(id)
  // 写入开始后，旧读取不得覆盖 PUT 返回的权威关联集合。
  ++evidenceRequest
  saveError.value = ''
  notice.value = ''
  try {
    const response = await updateBadcaseEvidence(id, ids(nextIds))
    if (!isCurrent(version, id)) return
    applyEvidence(parseEvidence(response))
    selectedCandidates.value = []
    notice.value = '证据关联已保存；基本信息未改动。'
  } catch (error) {
    if (isCurrent(version, id)) {
      evidence.value = null
      saveError.value = errorMessage(error, '关联保存未确认，请重新读取关联后再操作')
    }
  } finally {
    pendingSaveIds.delete(id)
    // A → B → A 时仍禁止重复保存；旧写入完成后重新读取，绝不套用旧响应。
    if (!disposed && currentId.value === id && version !== contextVersion && props.active) refresh()
  }
}

function associateSelected() {
  if (candidatesLoading.value || candidatesError.value) return
  const eligible = new Set(eligibleCandidates.value.map((run) => String(run.id)))
  const additions = selectedCandidates.value.filter((id) => eligible.has(id))
  if (additions.length) saveLinks([...linkedIds.value, ...additions])
}

function unlinkRun(id) {
  saveLinks(linkedIds.value.filter((linked) => linked !== id))
}

function ensureLoaded() {
  if (!props.active) return
  if (!evidence.value && !loading.value && !evidenceError.value && !saveError.value) loadEvidence()
  if (!candidatesLoaded.value && !candidatesLoading.value && !candidatesError.value) loadCandidates()
}

watch(() => [props.badcaseId, props.projectId], () => {
  ++contextVersion
  ++evidenceRequest
  ++candidatesRequest
  evidence.value = null
  candidates.value = []
  selectedCandidates.value = []
  selectedRunId.value = ''
  loading.value = false
  candidatesLoading.value = false
  candidatesLoaded.value = false
  evidenceError.value = ''
  candidatesError.value = ''
  saveError.value = ''
  notice.value = ''
  ensureLoaded()
}, { immediate: true, flush: 'sync' })
watch(() => props.active, ensureLoaded)
onBeforeUnmount(() => {
  disposed = true
  ++contextVersion
  ++evidenceRequest
  ++candidatesRequest
})
</script>

<style scoped>
.evidence-panel { min-width: 0; color: #303133; font-size: 14px; }
.scope-note { padding: 12px 16px; background: #ecf5ff; border-left: 3px solid #409eff; line-height: 1.7; }
.toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
h2 { margin: 0; font-size: 18px; }
h3 { margin: 20px 0 12px; font-size: 16px; }
h4 { margin: 20px 0 12px; font-size: 15px; }
h5 { margin: 12px 0 6px; font-size: 13px; }
p { line-height: 1.6; }
button { padding: 7px 12px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; color: #606266; cursor: pointer; font: inherit; }
button:hover:not(:disabled) { color: #409eff; border-color: #409eff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button:focus-visible, summary:focus-visible, input:focus-visible, .table-scroll:focus-visible { outline: 2px solid #409eff; outline-offset: 2px; }
.primary-button { margin-top: 12px; background: #409eff; border-color: #409eff; color: #fff; }
.primary-button:hover:not(:disabled) { background: #337ecc; color: #fff; }
.muted, small { color: #606266; }
.empty-state { padding: 16px; background: #f8f9fa; border: 1px dashed #dcdfe6; border-radius: 4px; color: #606266; }
.error-message { padding: 12px; color: #b42318; background: #fef0f0; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; overflow-wrap: anywhere; }
.success-message { color: #23723b; }
.warning-message { color: #915500; background: #fdf6ec; padding: 8px 12px; }
.candidate-picker, .record-card { margin-top: 16px; border: 1px solid #e4e7ed; border-radius: 6px; padding: 12px; min-width: 0; }
summary { cursor: pointer; font-weight: 600; overflow-wrap: anywhere; }
.candidate-list { max-height: 240px; overflow-y: auto; margin-top: 12px; }
.candidate-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 4px; border-bottom: 1px solid #ebeef5; cursor: pointer; overflow-wrap: anywhere; }
.candidate-row input { margin-top: 4px; flex-shrink: 0; }
.candidate-row span { min-width: 0; }
small { display: block; margin-top: 4px; font-size: 12px; overflow-wrap: anywhere; }
.linked-runs { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.linked-run { min-width: 0; border: 1px solid #dcdfe6; border-radius: 6px; padding: 8px; }
.linked-run.selected { border-color: #409eff; background: #ecf5ff; }
.run-selector { display: block; width: 100%; text-align: left; border: none; background: transparent; overflow-wrap: anywhere; }
.unlink-button { margin: 8px 0 0 12px; color: #b42318; font-size: 12px; }
.metadata { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }
.metadata > div { min-width: 0; }
dt { font-size: 12px; color: #606266; font-weight: normal; }
dd { margin: 4px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow-y: auto; }
.text-block { background: #f8f9fa; border: 1px solid #ebeef5; padding: 12px; margin: 0; border-radius: 4px; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; font: 12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; }
.table-scroll { overflow-x: auto; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; min-width: 560px; font-size: 12px; }
th, td { border: 1px solid #ebeef5; padding: 8px; text-align: left; vertical-align: top; max-width: 260px; white-space: pre-wrap; overflow-wrap: anywhere; }
th { background: #f5f7fa; }
@media (max-width: 600px) {
  .scope-note { padding: 10px; }
  .linked-runs, .metadata { grid-template-columns: minmax(0, 1fr); }
  .candidate-picker, .record-card { padding: 10px; }
  .toolbar button { width: 100%; }
}
</style>
