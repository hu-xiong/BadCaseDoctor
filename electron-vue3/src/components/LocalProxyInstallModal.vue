<template>
  <!-- 挂到 body，避免嵌在底部终端面板（低 z-index）时被右侧 AI 栏（2000）整层盖住 -->
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="etw-modal-overlay etw-install-overlay"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      @click.self="onCancel"
    >
      <div class="etw-modal etw-install-modal" @click.stop>
        <div :id="titleId" class="etw-modal-title">{{ t('embeddedTerminal.localProxyInstallModalTitle') }}</div>
        <p class="etw-install-terms-intro">{{ t('embeddedTerminal.localProxyInstallTermsIntro') }}</p>
        <p v-if="!ready" class="etw-install-loading">{{ t('embeddedTerminal.localProxyDownloading') }}</p>
        <div class="etw-install-terms-scroll">{{ t('embeddedTerminal.localProxyInstallTerms') }}</div>

        <template v-if="downloaded">
          <p class="etw-install-path-label">{{ t('embeddedTerminal.localProxyInstallModalPathLabel') }}</p>
          <p class="etw-install-run-hint">{{ t('embeddedTerminal.localProxyInstallRunHint') }}</p>
          <textarea
            v-model="installPathDraft"
            class="etw-install-path-input"
            rows="3"
            spellcheck="false"
            autocomplete="off"
            :disabled="saving"
            :placeholder="defaultPath"
          />
          <p class="etw-install-path-hint">{{ t('embeddedTerminal.localProxyInstallPathKeepFolderHint') }}</p>
        </template>
        <p v-if="saveError" class="etw-install-save-err">{{ saveError }}</p>

        <label v-if="downloaded" class="etw-install-checkbox">
          <input v-model="agreed" type="checkbox" :disabled="saving" />
          <span>{{ t('embeddedTerminal.localProxyInstallAgreeCheckbox') }}</span>
        </label>
        <div class="etw-modal-actions etw-install-actions">
          <button type="button" class="etw-proxy-protocol-btn" :disabled="saving" @click="onCancel">
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            class="etw-proxy-protocol-btn etw-proxy-protocol-btn--primary"
            :disabled="!canPrimary"
            @click="onPrimaryClick"
          >
            {{
              saving
                ? t('embeddedTerminal.localProxyInstallSaving')
                : !ready
                  ? t('embeddedTerminal.localProxyDownloading')
                  : downloaded
                    ? t('embeddedTerminal.localProxyInstallConfirmBtn')
                    : t('embeddedTerminal.localProxyInstallDownloadBtn')
            }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const titleId = `local-proxy-install-title-${Math.random().toString(36).slice(2, 9)}`

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  defaultPath: { type: String, default: '' },
  ready: { type: Boolean, default: true },
  downloaded: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  saveError: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue', 'download', 'confirm'])

const { t } = useI18n()
const agreed = ref(false)
const installPathDraft = ref('')

const canPrimary = computed(() => {
  if (!props.ready || props.saving) return false
  if (!props.downloaded) return true
  return agreed.value && !!String(installPathDraft.value || '').trim()
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      agreed.value = false
      installPathDraft.value = String(props.defaultPath || '').trim() || ''
    }
  }
)

watch(
  () => props.defaultPath,
  (p) => {
    if (props.modelValue && !String(installPathDraft.value || '').trim()) {
      installPathDraft.value = String(p || '').trim()
    }
  }
)

function onCancel() {
  emit('update:modelValue', false)
}

function emitConfirm() {
  if (!canPrimary.value) return
  emit('confirm', { targetPath: String(installPathDraft.value || '').trim() })
}

function emitDownload() {
  if (!canPrimary.value) return
  emit('download')
}

function onPrimaryClick() {
  if (props.downloaded) return emitConfirm()
  return emitDownload()
}
</script>

<style scoped>
.etw-install-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.etw-modal-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #ececec;
}

.etw-install-modal {
  max-width: 520px;
  width: 100%;
  max-height: min(92vh, 640px);
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: #2d2d30;
  border: 1px solid #3c3c3c;
  border-radius: 10px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  color: #ccc;
}

.etw-install-terms-intro {
  margin: 0 0 6px;
  font-size: 11px;
  color: #bbb;
}

.etw-install-loading {
  margin: -2px 0 8px;
  font-size: 11px;
  color: #9bbbd4;
}

.etw-install-terms-scroll {
  flex: 1 1 auto;
  min-height: 120px;
  max-height: 240px;
  overflow: auto;
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  color: #b0b0b0;
  background: #252526;
  border: 1px solid #3c3c3c;
  border-radius: 6px;
  margin-bottom: 12px;
}

.etw-install-path-label {
  margin: 0 0 6px;
  font-size: 11px;
  color: #aaa;
}

.etw-install-path-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  font-size: 11px;
  font-family: ui-monospace, monospace;
  line-height: 1.45;
  color: #cecece;
  background: #1e1e1e;
  border: 1px solid #555;
  border-radius: 6px;
  margin-bottom: 8px;
  resize: vertical;
  min-height: 52px;
}

.etw-install-path-input:disabled {
  opacity: 0.65;
}

.etw-install-path-hint {
  margin: -2px 0 10px;
  font-size: 11px;
  line-height: 1.35;
  color: #9aa0a6;
}

.etw-install-run-hint {
  margin: -2px 0 8px;
  font-size: 11px;
  line-height: 1.4;
  color: #c7d6ff;
}

.etw-install-save-err {
  margin: 0 0 10px;
  font-size: 11px;
  line-height: 1.4;
  color: #ffab91;
}

.etw-install-checkbox {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 11px;
  line-height: 1.45;
  color: #ddd;
  cursor: pointer;
  user-select: none;
}

.etw-install-checkbox input {
  margin-top: 2px;
  flex-shrink: 0;
}

.etw-install-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 4px;
}

.etw-proxy-protocol-btn {
  padding: 5px 12px;
  font-size: 12px;
  color: #e0e0e0;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid #444;
  border-radius: 6px;
  cursor: pointer;
}

.etw-proxy-protocol-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.12);
}

.etw-proxy-protocol-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.etw-proxy-protocol-btn--primary {
  border-color: rgba(100, 181, 246, 0.5);
  color: #bbdefb;
}
</style>
