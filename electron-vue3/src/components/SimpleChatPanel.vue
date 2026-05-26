<template>
  <div class="simple-chat-panel">
    <div v-if="agentLocalProxyHint" class="agent-local-proxy-hint" role="status">
      <span class="agent-local-proxy-hint-text">{{ agentLocalProxyHint }}</span>
      <button
        type="button"
        class="agent-local-proxy-hint-dismiss"
        :title="t('chat.closePreview')"
        @click="agentLocalProxyHint = ''"
      >
        ×
      </button>
    </div>
    <!-- 图片大图预览弹层 -->
    <Teleport to="body">
      <div v-if="imagePreviewSrc" class="image-preview-overlay" @click.self="closeImagePreview">
        <div class="image-preview-stage" @click.stop>
          <div class="image-preview-toolbar">
            <button
              type="button"
              class="image-preview-tool-btn"
              :title="t('chat.copyImage')"
              @click.stop="copyPreviewImage"
            >
              <svg class="image-preview-tool-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
              </svg>
            </button>
            <button
              type="button"
              class="image-preview-tool-btn"
              :title="t('chat.downloadImage')"
              @click.stop="downloadPreviewImage"
            >
              <svg class="image-preview-tool-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
              </svg>
            </button>
            <button
              type="button"
              class="image-preview-tool-btn image-preview-tool-btn--close"
              :title="t('chat.closePreview')"
              @click.stop="closeImagePreview"
            >
              <svg class="image-preview-tool-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </button>
          </div>
          <img :src="imagePreviewSrc" class="image-preview-full" :alt="t('chat.imagePreview')" />
        </div>
      </div>
    </Teleport>

    <!-- 消息列表区域 -->
    <div class="messages-container" ref="messagesContainer">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">💬</div>
        <p>{{ t('chat.empty') }}</p>
      </div>
      
      <div 
        v-for="(message, messageIdx) in messages" 
        :key="messageListRowKey(message, messageIdx)"
        class="message-block"
        :data-message-id="message.id"
      >
        <!-- 用户消息 -->
        <div v-if="message.isUser" class="user-message-block">
          <div class="message-header">
            <span class="message-author">{{ t('chat.me') }}</span>
            <span class="message-time">{{ message.time }}</span>
          </div>
          <div class="user-message-toggle-wrap">
            <div
              v-if="!isUserMessageEditingInline(message)"
              class="user-message-bubble"
              tabindex="0"
              role="button"
              @pointerdown="onUserBubblePointerDown($event, message)"
              @keydown.enter.prevent="scheduleBeginEditUserMessage(message)"
            >
              <template v-if="message.images && message.images.length > 0">
                <div class="user-message-images">
                  <img v-for="(img, i) in message.images" :key="i" :src="img.data" class="user-msg-thumb" :alt="t('chat.uploadImageAlt')" @click.stop="openImagePreview(img.data, img.filename)" />
                </div>
              </template>
              <template v-if="message.content">{{ message.content }}</template>
            </div>
            <div
              v-else
              class="inline-composer"
            >
            <div
              class="input-box-wrapper"
              :class="{ 'input-box-wrapper--dragover': isInlineDragOver }"
              @dragover.prevent="isInlineDragOver = true"
              @dragleave.prevent="isInlineDragOver = false"
              @drop.prevent="handleInlineImageDrop"
            >
              <div v-if="inlinePendingImages.length > 0" class="pending-images-row">
                <div v-for="(img, idx) in inlinePendingImages" :key="idx" class="pending-image-item">
                  <img
                    :src="img.data"
                    class="pending-thumb"
                    :alt="t('chat.imagePreview')"
                    @click.stop="openImagePreview(img.data, img.filename)"
                  />
                  <button type="button" class="pending-image-remove" @click.stop="removePendingInline(idx)" :title="t('chat.removeImage')">×</button>
                </div>
              </div>
              <textarea
                ref="inlineTextareaRef"
                v-model="inlineInputMessage"
                @input="autoResizeInline"
                @keydown.enter.exact="handleInlineSend"
                @keydown.enter.shift.exact="addNewLineInline"
                @keydown.esc.exact="cancelEditUserMessage"
                @paste="onPasteInlineComposer"
                @compositionstart="isComposing = true"
                @compositionend="isComposing = false"
                :placeholder="t('chat.placeholderWithImage')"
                class="message-input"
                rows="1"
              ></textarea>

              <div class="input-footer">
                <div class="footer-left">
                  <div class="selector-item">
                    <select v-model="selectedAgent" class="footer-select">
                      <option value="agent">{{ t('chat.agentMode') }}</option>
                      <option value="chat">{{ t('chat.chatMode') }}</option>
                    </select>
                  </div>
                  <div class="selector-item model-select-wrapper">
                    <img
                      v-if="inlineModelIsQwen"
                      :src="qwenIcon"
                      alt="Qwen"
                      class="model-icon"
                    />
                    <img
                      v-else-if="inlineModelIsGlm"
                      :src="glmIcon"
                      alt="GLM"
                      class="model-icon"
                    />
                    <img
                      v-else-if="inlineModelIsDeepSeek || inlineModelIsAuto"
                      :src="deepThinkingIcon"
                      :alt="inlineModelIsAuto ? 'Auto' : 'DeepSeek'"
                      class="model-icon"
                    />
                    <select v-model="inlineEditSelectedModel" class="footer-select">
                      <option
                        v-for="opt in chatModelOptions"
                        :key="'inline-' + opt.id"
                        :value="opt.id"
                      >{{ opt.label }}</option>
                    </select>
                  </div>
                </div>

                <div class="footer-right">
                  <input
                    ref="inlineImageFileInputRef"
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
                    multiple
                    style="display: none"
                    @change="handleInlineImageSelect"
                  />
                  <button
                    type="button"
                    class="image-upload-button"
                    :class="{ 'image-upload-button--active': inlinePendingImages.length > 0 }"
                    :title="t('chat.uploadImageAlt')"
                    @click="triggerInlineImageSelect"
                  >
                    <img :src="imageUploadIcon" :alt="t('chat.uploadImageAlt')" class="image-upload-icon" />
                  </button>
                  <button
                    v-if="!isSending"
                    @click="handleInlineSend"
                    class="send-icon-button"
                    :disabled="!inlineInputMessage.trim() && inlinePendingImages.length === 0"
                    :title="t('chat.send')"
                  >
                    <img class="send-icon-img" :src="sendCursorIcon" alt="send" />
                  </button>
                  <button
                    v-else
                    type="button"
                    @click.stop="handleStop"
                    class="stop-icon-button"
                    :title="t('chat.stop')"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <rect x="6" y="6" width="12" height="12" rx="2"></rect>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
          </div>
        </div>
        
        <!-- AI消息 -->
        <div v-else class="ai-message-block">
          <div class="message-header">
            <span class="message-author">{{ t('chat.ai') }}</span>
            <span class="message-time">{{ message.time }}</span>
          </div>
                    
          <!-- AI 等待：仅一组三点；占位 step 已挂载时仍用此处占位，避免与 AgentTaskRun 内多段「...」重复 -->
          <template
            v-if="
              message.understanding &&
              !message.finalResponse &&
              !message._planMemoRevealReady &&
              (
                !message.steps ||
                message.steps.length === 0 ||
                (message._placeholderSteps && !substantiveThinkPhase(message))
              )
            "
          >
            <template v-if="message.understanding === '...'">
              <span class="loading-dots loading-dots--solo" aria-hidden="true">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </span>
            </template>
            <template v-else>
              <span class="ai-understanding-inline">{{ message.understanding }}</span>
            </template>
          </template>
                    

                    
          <!-- ReAct think：占位阶段 AgentTaskRun 隐藏时在此展示流式推理；揭壳后改由 AgentTaskRun 内展示，避免双栏 -->
          <div
            v-if="showFirstThinkBlock(message) && !!message._placeholderSteps"
            class="cursor-reasoning-wrap"
          >
            <div class="cursor-reasoning-block">
              <button
                type="button"
                class="cursor-reason-summary"
                @click="message.thoughtCollapsed = !message.thoughtCollapsed"
              >
                <span class="cursor-reason-pill">{{ thoughtSummaryLabel(message) }}</span>
                <span
                  v-if="message.thoughtCollapsed && message.agentResult?.thinking_time != null"
                  class="cursor-reason-meta"
                >
                  {{ Number(message.agentResult.thinking_time).toFixed(1) }}s
                </span>
                <span class="cursor-reason-chevron">{{ message.thoughtCollapsed ? '▶' : '▼' }}</span>
              </button>
              <div v-if="!message.thoughtCollapsed" class="cursor-reason-feed">
                <div class="cursor-reason-feed-stack">
                  <!-- 流式中：content 轨与 reasoning 轨同时存在时用双 pre；仅 reasoning 时用打字机缓冲（避免多包同帧合并后 thinkReasoningDraft 整段闪现） -->
                  <template
                    v-if="message._reasoningPhaseLive && thinkDraftContentVisible(message)"
                  >
                    <pre
                      v-if="thinkDraftReasoningVisible(message)"
                      class="react-sse-stream react-sse-stream--reasoning"
                    >{{ squeezeReasoningVerticalWhitespace(message.thinkReasoningDraft) }}</pre>
                    <pre
                      class="react-sse-stream react-sse-stream--content"
                    >{{ squeezeReasoningVerticalWhitespace(message.thinkContentDraft) }}</pre>
                  </template>
                  <div
                    v-else-if="
                      message._reasoningPhaseLive &&
                      (thinkDraftReasoningVisible(message) || reasoningPlainVisible(message))
                    "
                    class="cursor-reason-plain"
                  >{{ reasoningPlainForDisplay(message) }}</div>
                  <!-- 流式结束：双栏 Markdown 或旧版单栏 -->
                  <div
                    v-else-if="thinkDraftReasoningVisible(message) || thinkDraftContentVisible(message)"
                    class="reasoning-text reasoning-markdown cursor-reason-inner react-sse-md-wrap"
                  >
                    <div
                      v-if="thinkDraftReasoningVisible(message)"
                      class="react-sse-md react-sse-stream--reasoning"
                      v-html="formatReasoningMarkdown(message.thinkReasoningDraft || '')"
                    ></div>
                    <div
                      v-if="thinkDraftContentVisible(message)"
                      class="react-sse-md react-sse-stream--content"
                      v-html="formatReasoningMarkdown(message.thinkContentDraft || '')"
                    ></div>
                  </div>
                  <div
                    v-else-if="reasoningMarkdownStreamVisible(message)"
                    class="reasoning-text reasoning-markdown cursor-reason-inner"
                    v-html="formatReasoningMarkdown(message.reasoningContent || '')"
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <!-- 单根包裹，避免大块 fragment 与 Teleport 交错 patch -->
          <div class="ai-agent-run-stack">
          <!-- Cursor 式：顶部计划 + 分步流式执行日志；修改类沙箱在「最后一个 modify 步之后」内嵌，避免后续 create 等插在 modify 与沙箱之间 -->
          <AgentTaskRun
            v-if="getAgentTaskRunViewForAi(message).showSteps"
            :steps="getAgentTaskRunViewForAi(message).steps"
            :plan-memo-rows="planMemoRowsForMessage(message)"
            :instantPlan="!!message.isHistorical"
            :suppress-plan-overview="suppressPlanOverviewForMessage(message)"
            :hide-preface-placeholder="!!message._placeholderSteps && !substantiveThinkPhase(message)"
            :modify-sandbox-pending="messageHasPendingSandboxConfirm(message)"
            :sandbox-after-modify-step-index="getAgentTaskRunViewForAi(message).embedIdx"
            @grep-bug-click="handleNavigation"
          >
            <template #modifySandbox>
              <div :id="'sandbox-mod-embed-' + message.id" class="agent-modify-sandbox-anchor" />
            </template>
          </AgentTaskRun>

          <div
            v-if="message.clientLocalRunCards && message.clientLocalRunCards.length"
            class="client-local-run-section"
          >
            <div
              v-for="(lc, lcIdx) in message.clientLocalRunCards"
              :key="'lcr-' + message.id + '-' + lcIdx"
              class="client-local-run-card findings-card"
            >
              <div class="client-local-run-head">
                <span class="card-icon">⬇</span>
                <span class="card-title">{{ lc.title || t('chat.localRunDownload') }}</span>
              </div>
              <p class="client-local-run-body text-muted small">{{ lc.body || t('chat.localRunIntro') }}</p>

              <template v-if="lc.artifacts && lc.artifacts.length">
                <p class="client-local-run-os small text-muted">
                  {{ t('chat.localRunDetectedOs', { os: localRunOsLabel(detectClientOS()) }) }}
                </p>
                <div
                  v-for="art in lc.artifacts"
                  :key="(art.os || '') + '-' + (art.filename || '')"
                  class="client-local-run-platform"
                >
                  <div class="client-local-run-platform-title">
                    <strong>{{ art.label || art.os }}</strong>
                    <span v-if="art.available === false" class="badge bg-warning text-dark ms-2">{{ t('chat.localRunBinaryMissing') }}</span>
                  </div>
                  <div class="client-local-run-actions">
                    <a
                      class="btn btn-sm btn-primary"
                      :href="localRunArtifactUrl(art)"
                      :download="art.filename"
                      target="_blank"
                      rel="noopener noreferrer"
                    >{{ t('chat.localRunDownload') }}</a>
                    <template v-if="art.os === 'win'">
                      <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunWinPowerShellDownload(art))">
                        {{ t('chat.localRunCopyPs') }}
                      </button>
                      <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunWinCurlDownload(art))">
                        {{ t('chat.localRunCopyCurlExe') }}
                      </button>
                      <button type="button" class="btn btn-sm btn-success" @click="copyLocalRunLine(localRunWinRunLine(art))">
                        {{ t('chat.localRunCopyRun') }}
                      </button>
                    </template>
                    <template v-else>
                      <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunUnixWget(art))">
                        {{ t('chat.localRunCopyWget') }}
                      </button>
                      <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunUnixCurl(art))">
                        {{ t('chat.localRunCopyCurl') }}
                      </button>
                      <button type="button" class="btn btn-sm btn-success" @click="copyLocalRunLine(localRunUnixChmodRun(art))">
                        {{ t('chat.localRunCopyRun') }}
                      </button>
                    </template>
                  </div>
                  <pre v-if="art.os === 'win'" class="client-local-run-pre">{{ localRunWinPowerShellDownload(art) }}</pre>
                  <pre v-else class="client-local-run-pre">{{ localRunUnixWget(art) + '\n' + localRunUnixChmodRun(art) }}</pre>
                </div>
              </template>
              <template v-else>
                <div class="client-local-run-actions">
                  <a
                    class="btn btn-sm btn-primary"
                    :href="localRunAbsoluteUrl(lc)"
                    :download="localRunFilename(lc)"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ t('chat.localRunDownload') }}</a>
                  <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunLegacyWgetLine(lc))">
                    {{ t('chat.localRunCopyWget') }}
                  </button>
                  <button type="button" class="btn btn-sm btn-outline-secondary" @click="copyLocalRunLine(localRunLegacyCurlLine(lc))">
                    {{ t('chat.localRunCopyCurl') }}
                  </button>
                  <button type="button" class="btn btn-sm btn-success" @click="copyLocalRunLine(localRunLegacyRunLine(lc))">
                    {{ t('chat.localRunCopyRun') }}
                  </button>
                </div>
                <pre class="client-local-run-pre" aria-label="wget">{{ localRunLegacyWgetLine(lc) }}</pre>
                <pre class="client-local-run-pre" aria-label="run">{{ localRunLegacyRunLine(lc) }}</pre>
              </template>
              <p v-if="localRunCopyTip" class="client-local-run-tip small text-success">{{ localRunCopyTip }}</p>
            </div>
          </div>
          
          <!-- 工具执行卡片 - 隐藏，已整合到TodoTimeline中 -->
          <!-- <ExecutionResult 
            v-if="message.executionResults && message.executionResults.length > 0" 
            :results="message.executionResults"
            :instant="message.isHistorical || false"
          /> -->
          
          <!-- 执行证据卡片 - 隐藏，已整合到TodoTimeline步骤展开区 -->
          <!-- <div v-if="message.evidences && message.evidences.length > 0" class="evidence-section">
            <div class="evidence-title">📊 执行证据</div>
            <EvidenceCard 
              v-for="(evidence, index) in message.evidences"
              :key="index"
              :evidence="evidence.data"
              :isAnimating="false"
            />
          </div> -->
          
          <!-- 搜索结果显示 -->
          <div v-if="message.searchResults && message.searchResults.length > 0" class="search-results-section">
            <div class="search-results-title">🔍 {{ t('chat.searchResults') }}</div>
            <div class="search-results-container">
              <div v-for="(result, index) in message.searchResults" :key="index" class="search-result-item">
                <div class="search-result-rank">{{ result.rank || index + 1 }}</div>
                <div class="search-result-content">
                  <a v-if="result.url" :href="result.url" target="_blank" class="search-result-title">{{ result.title }}</a>
                  <div v-else class="search-result-title">{{ result.title }}</div>
                  <div class="search-result-url">{{ result.url }}</div>
                  <div class="search-result-snippet">{{ result.snippet }}</div>
                </div>
              </div>
            </div>
          </div>
          
          <div
            v-if="message.modifyNavigation?.is_create && tempCardProposalForMessage(message.id)"
            class="temp-card-proposal-bar temp-card-proposal-bar--inline"
          >
            <span class="temp-card-proposal-text">{{
              t('chat.tempCardProposal', {
                plan: tempCardProposalForMessage(message.id).planLabel,
                cardTitle: tempCardProposalForMessage(message.id).cardTitle
              })
            }}</span>
            <div class="temp-card-proposal-actions">
              <button
                type="button"
                class="temp-card-proposal-btn temp-card-proposal-btn--approve"
                @click="approveTempCardProposal(tempCardProposalForMessage(message.id))"
              >
                {{ t('chat.tempCardApprove') }}
              </button>
              <button
                type="button"
                class="temp-card-proposal-btn temp-card-proposal-btn--reject"
                @click="rejectTempCardProposal(tempCardProposalForMessage(message.id))"
              >
                {{ t('chat.tempCardReject') }}
              </button>
            </div>
          </div>
          <div :id="'sandbox-mod-below-' + message.id" class="agent-modify-sandbox-anchor" />
          <Teleport
            v-if="
              sandboxTeleportTargetExists(message) &&
              (message.modifyGroups?.length || message.modifyNavigation) &&
              !(
                message.modifyNavigation?.is_create &&
                isCreateAwaitingTempCard(message.id) &&
                tempCardProposalForMessage(message.id)
              )
            "
            :to="sandboxModifyTeleportTargetForMessage(message)"
          >
          <!-- 修改预览导航区域 - 沙箱预览：整行点击跳转，下三角=展开/收起，无单独跳转按钮 -->
          <div v-if="message.modifyGroups && message.modifyGroups.length > 0" class="modify-navigation-section">
            <template v-for="(group, groupIdx) in message.modifyGroups" :key="groupIdx">
              <!-- 仍有待确认：完整可展开 diff -->
              <div
                v-if="groupHasPendingSandboxConfirm(group, message)"
                class="collapsible-card findings-card sandbox-card"
                :class="{ 'sandbox-card--has-expand': sandboxPreviewNeedsCollapse(message, groupIdx) }"
                style="margin-bottom: 12px;"
              >
                <div class="collapsible-header sandbox-header" @click="handleShowGroupInList(group, message.id)">
                  <span class="card-icon">📝</span>
                  <span class="card-title">{{ t('chat.sandboxPreview') }}</span>
                  <span class="card-count">{{ t('chat.itemsCount', { n: countGroupSandboxDisplayRows(group) }) }}</span>
                  <span v-if="group.plan_id" class="plan-badge">{{ t('chat.planBadge', { id: group.plan_id }) }}</span>
                </div>
                <div
                  class="collapsible-content modify-navigation-content sandbox-preview-body"
                  :class="{ 'sandbox-preview-body--collapsed': isSandboxPreviewCollapsed(message, groupIdx) }"
                >
                  <div
                    v-if="isSandboxPreviewCollapsed(message, groupIdx)"
                    class="sandbox-preview-fade"
                    aria-hidden="true"
                  />
                  <template v-for="(entry, vidx) in visibleGroupSandboxEntries(message, groupIdx)" :key="`${entry.gix}-${entry.rowIdx}-${vidx}`">
                    <div v-if="entry.showRecordHeader" class="group-item-target">
                      {{ t('chat.recordNum', { id: entry.git.target_id }) }}
                    </div>
                    <div class="modify-field-preview">
                      <span class="field-label">{{ sandboxFieldHeaderLabel(entry.fieldDiff, entry.git, group.target) }}:</span>
                      <span :class="['old-value', { 'empty-value': !(formatSandboxModifySideDisplay(entry.git, entry.fieldDiff, 'old') || getFieldOldValue(entry.fieldDiff)) }]">
                        {{ (formatSandboxModifySideDisplay(entry.git, entry.fieldDiff, 'old') || getFieldOldValue(entry.fieldDiff)) || t('chat.notSet') }}
                      </span>
                      <span class="arrow">→</span>
                      <span class="new-value">{{ (formatSandboxModifySideDisplay(entry.git, entry.fieldDiff, 'new') || getFieldNewValue(entry.fieldDiff)) || '-' }}</span>
                    </div>
                  </template>
                  <template
                    v-if="!sandboxPreviewNeedsCollapse(message, groupIdx) || isSandboxExpanded(message, groupIdx)"
                    v-for="(git, gix) in group.items"
                    :key="'muted-' + gix"
                  >
                    <template v-if="!isSandboxModifyItemPending(git, message)">
                      <div class="modify-field-preview modify-field-preview--muted">
                        {{ t('chat.adoptedNoPendingDetail') }}
                      </div>
                    </template>
                    <div
                      v-else-if="group.items.length > 1 && isSandboxModifyItemPending(git, message) && !resolveSandboxDiffRowsForDisplay(git, group.target).length"
                      class="modify-field-preview modify-field-preview--muted"
                    >
                      {{ t('chat.noDiffLines', { id: git.target_id }) }}
                    </div>
                  </template>
                  <div v-if="group.items.length > 1 && group.items.some((it) => isSandboxModifyItemPending(it, message))" class="group-items-hint">
                    {{ t('chat.mergeGroupHint', { n: group.items.length }) }}
                  </div>
                </div>
                <button
                  v-if="sandboxPreviewNeedsCollapse(message, groupIdx)"
                  type="button"
                  class="sandbox-expand-bar"
                  :class="{ expanded: isSandboxExpanded(message, groupIdx) }"
                  :title="isSandboxExpanded(message, groupIdx) ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
                  @click.stop="toggleSandboxExpand(message, groupIdx)"
                >
                  <img class="sandbox-expand-chevron" :src="chevronDownIcon" alt="" />
                </button>
              </div>
              <!-- 本组已全部采纳：只保留一行摘要，避免重复 N 条「已采纳」占用空间 -->
              <div
                v-else
                class="sandbox-adopted-summary findings-card"
                style="margin-bottom: 12px;"
                @click="handleShowGroupInList(group, message.id)"
              >
                <div class="sandbox-header sandbox-header--compact">
                  <span class="card-icon">→</span>
                  <span class="card-title">{{ t('chat.sandboxGroupAllAdopted', { n: group.items?.length || 0 }) }}</span>
                  <span v-if="group.plan_id" class="plan-badge">{{ t('chat.planBadge', { id: group.plan_id }) }}</span>
                </div>
              </div>
            </template>
          </div>
          
          <!-- 兼容旧版本：单个 modifyNavigation，同样整行点击跳转、下三角=展开 -->
          <div v-else-if="message.modifyNavigation" class="modify-navigation-section">
            <!-- 批量且已全部采纳：单行摘要，避免展开后三条重复「已采纳」 -->
            <div
              v-if="
                message.modifyNavigation.batch_modify &&
                message.modifyNavigation.batch_results?.length &&
                !messageHasPendingSandboxConfirm(message)
              "
              class="sandbox-adopted-summary findings-card"
              @click="handleShowModifyInList(message.modifyNavigation, message.id)"
            >
              <div class="sandbox-header sandbox-header--compact">
                <span class="card-icon">→</span>
                <span class="card-title">{{
                  t('chat.sandboxGroupAllAdopted', { n: message.modifyNavigation.batch_results.length })
                }}</span>
                <span v-if="message.modifyNavigation.plan_id" class="plan-badge">{{
                  t('chat.planBadge', { id: message.modifyNavigation.plan_id })
                }}</span>
              </div>
            </div>
            <div
              v-else
              class="collapsible-card findings-card sandbox-card"
              :class="{ 'sandbox-card--has-expand': sandboxPreviewNeedsCollapse(message, null) }"
            >
              <div class="collapsible-header sandbox-header" @click="handleShowModifyInList(message.modifyNavigation, message.id)">
                <span class="card-icon">{{ message.modifyNavigation.batch_modify ? '🧩' : (message.modifyNavigation.navigate_to_existing ? '🔍' : (message.modifyNavigation.is_create ? '➕' : '📝')) }}</span>
                <span class="card-title">{{ message.modifyNavigation.batch_modify ? t('chat.batchSandboxPreview') : (message.modifyNavigation.navigate_to_existing ? t('chat.createdLocate') : (message.modifyNavigation.is_create ? t('chat.newPreview') : t('chat.sandboxPreview'))) }}</span>
                <span class="card-count">{{ t('chat.itemsCount', { n: message.modifyNavigation.batch_modify ? (message.modifyNavigation.batch_count || message.modifyNavigation.batch_results?.length || 0) : getSandboxDiffRows(message).length }) }}</span>
              </div>
              <div
                class="collapsible-content modify-navigation-content sandbox-preview-body"
                :class="{ 'sandbox-preview-body--collapsed': isSandboxPreviewCollapsed(message, null) }"
              >
                <div
                  v-if="isSandboxPreviewCollapsed(message, null)"
                  class="sandbox-preview-fade"
                  aria-hidden="true"
                />
                <!-- 批量 modify：按条与列表一致；已采纳项不再展示 diff -->
                <template
                  v-if="message.modifyNavigation.batch_modify && message.modifyNavigation.batch_results?.length"
                >
                  <div
                    v-if="
                      messageHasPendingSandboxConfirm(message) &&
                      message.modifyNavigation.batch_results.every((br) => getBatchItemSandboxDiffRows(br).length === 0)
                    "
                    class="sandbox-list-empty"
                  >
                    {{ t('chat.batchSandboxBatchHint') }}
                  </div>
                  <template v-for="(entry, vidx) in visibleBatchSandboxEntries(message)" :key="`batch-${entry.bix}-${entry.rowIdx}-${vidx}`">
                    <div v-if="entry.showRecordHeader" class="group-item-target">
                      {{ t('chat.recordNum', { id: entry.br.target_id }) }}
                    </div>
                    <div class="modify-field-preview">
                      <span class="field-label">{{ sandboxFieldHeaderLabel(entry.fieldDiff, entry.br) }}:</span>
                      <span
                        :class="['old-value', { 'empty-value': !formatSandboxModifySideDisplay(entry.br, entry.fieldDiff, 'old') }]"
                      >
                        {{ formatSandboxModifySideDisplay(entry.br, entry.fieldDiff, 'old') || t('chat.notSet') }}
                      </span>
                      <span class="arrow">→</span>
                      <span class="new-value">{{ formatSandboxModifySideDisplay(entry.br, entry.fieldDiff, 'new') || '-' }}</span>
                    </div>
                  </template>
                  <template
                    v-if="!sandboxPreviewNeedsCollapse(message, null) || isSandboxExpanded(message, null)"
                    v-for="(br, bix) in message.modifyNavigation.batch_results"
                    :key="'batch-muted-' + bix"
                  >
                    <template v-if="!isSandboxModifyItemPending(br, message)">
                      <div class="modify-field-preview modify-field-preview--muted">
                        {{ t('chat.adoptedNoPendingDetail') }}
                      </div>
                    </template>
                    <div
                      v-else-if="message.modifyNavigation.batch_results.length > 1 && !getBatchItemSandboxDiffRows(br, message.modifyNavigation?.target).length"
                      class="modify-field-preview modify-field-preview--muted"
                    >
                      {{ t('chat.noDiffLines', { id: br.target_id }) }}
                    </div>
                  </template>
                  <div
                    v-if="
                      message.modifyNavigation.batch_results.length > 1 &&
                      message.modifyNavigation.batch_results.some((r) => isSandboxModifyItemPending(r, message))
                    "
                    class="group-items-hint"
                  >
                    {{ t('chat.mergeGroupHint', { n: message.modifyNavigation.batch_results.length }) }}
                  </div>
                </template>
                <template v-else>
                  <div
                    v-if="message.modifyNavigation.is_create && getSandboxDiffRows(message).length === 0"
                    class="sandbox-list-empty"
                  >
                    {{ t('chat.detailFieldsHint') }}
                  </div>
                  <div v-for="(fieldDiff, idx) in visibleSandboxPreviewRows(message, null)" :key="idx" class="modify-field-preview">
                    <span class="field-label">{{ sandboxFieldHeaderLabel(fieldDiff, message.modifyNavigation) }}:</span>
                    <template v-if="message.modifyNavigation.is_create">
                      <span class="new-value create-value">{{ fieldDiff.lines?.find(l => l.type === 'add')?.content || '-' }}</span>
                    </template>
                    <template v-else>
                      <span :class="['old-value', { 'empty-value': !formatSandboxModifySideDisplay(message.modifyNavigation, fieldDiff, 'old') }]">
                        {{ formatSandboxModifySideDisplay(message.modifyNavigation, fieldDiff, 'old') || t('chat.notSet') }}
                      </span>
                      <span class="arrow">→</span>
                      <span class="new-value">{{ formatSandboxModifySideDisplay(message.modifyNavigation, fieldDiff, 'new') || '-' }}</span>
                    </template>
                  </div>
                </template>
              </div>
              <button
                v-if="sandboxPreviewNeedsCollapse(message, null)"
                type="button"
                class="sandbox-expand-bar"
                :class="{ expanded: isSandboxExpanded(message, null) }"
                :title="isSandboxExpanded(message, null) ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
                @click.stop="toggleSandboxExpand(message, null)"
              >
                <img class="sandbox-expand-chevron" :src="chevronDownIcon" alt="" />
              </button>
            </div>
          </div>
          
          <div
            v-if="messageHasPendingSandboxConfirm(message) && !(message.modifyNavigation && message.modifyNavigation.navigate_to_existing)"
            class="sandbox-confirm-hint"
          >
            {{ t('chat.sandboxFooter') }}
          </div>
          <div
            v-if="message.modifyNavigation && message.modifyNavigation.navigate_to_existing"
            class="sandbox-confirm-hint sandbox-confirm-hint--muted"
          >
            {{ t('chat.alreadyAdoptedLocate') }}
          </div>
          </Teleport>
          </div>
          
          <!-- Bug 导航：grep 多结果；已挂到对应 grep 步骤「执行结果」下时不重复显示 -->
          <div
            v-if="message.navigation && message.navigation.type === 'multiple' && !grepNavigationOnSteps(message)"
            class="bug-navigation-section"
          >
            <div class="collapsible-card findings-card">
              <details :open="true">
                <summary class="collapsible-header">
                  <span class="card-icon">{{ grepNavCardIcon(message) }}</span>
                  <span class="card-title">{{ grepNavCardTitle(message) }}</span>
                  <span class="card-count">{{ t('chat.navRecords', { n: message.navigation.items.length }) }}</span>
                  <span class="card-arrow">→</span>
                </summary>
                <div class="collapsible-content bug-navigation-list">
                  <div
                    v-for="(item, idx) in message.navigation.items"
                    :key="idx"
                    class="bug-nav-item"
                    @click="handleNavigation(item)"
                  >
                    <span class="bug-nav-icon">→</span>
                    <span class="bug-nav-title">{{ item.title || item.bug_title }}</span>
                    <span v-if="item.plan_name" class="bug-nav-plan">{{ item.plan_name }}</span>
                  </div>
                </div>
              </details>
            </div>
          </div>
                    
          <!-- 最终回复（无统一总结时展示） -->
          <div v-if="message.finalResponse && !hasUnifiedSummary(message)" class="ai-response">
            <div class="ai-response-text">
              {{ message.finalResponse }}
            </div>
          </div>
          
          <!-- 统一总结：标题秒数 = 整轮 wall time（execution_time），与正文里「总耗时」一致；勿用 thinking_time（仅首轮规划） -->
            <div v-if="hasUnifiedSummary(message)" class="unified-summary-section">
            <div class="unified-summary-header">
              {{
                message.unifiedSummaryLoading
                  ? t('chat.summaryHeaderLoading')
                  : t('chat.summarySeconds', { s: (message.agentResult.execution_time ?? message.agentResult.thinking_time ?? 0).toFixed(2) })
              }}
            </div>
            <div class="unified-summary-content reasoning-content">
              <!-- 仅等「终局/统一总结」流（summary_stream 或 running_summary_stream 首包前）：勿调 getUnifiedSummaryBody，否则增 runningSummaryDraft 一直非空会挡掉三点 -->
              <div v-if="message.unifiedSummaryLoading && !String((message.summaryStreamDraft || '')).trim()" class="unified-summary-loading">
                <span class="loading-dots loading-dots--solo" aria-hidden="true">
                  <span class="dot"></span>
                  <span class="dot"></span>
                  <span class="dot"></span>
                </span>
              </div>
              <div
                v-else-if="unifiedSummaryBodyIsMarkdown(message)"
                class="reasoning-text unified-summary-text reasoning-markdown react-sse-md-wrap"
                v-html="formatReasoningMarkdown(getUnifiedSummaryBody(message))"
              ></div>
              <div v-else class="reasoning-text unified-summary-text">{{ getUnifiedSummaryBody(message) }}</div>
              <CreatePreview 
                v-if="message.createPreview && message.createPreview.preview" 
                :previewData="message.createPreview"
                @confirm="handleConfirmCreate"
                @cancel="handleCancelCreate"
              />
            </div>
          </div>
                    
          <!-- Bug 保存按钮（仅当有 Bug 结果时显示） -->
          <div v-if="message.agentResult && message.agentResult.bugs_found && message.agentResult.bugs_found.length > 0" class="save-bugs-section">
            <button @click="handleSaveBugs(message.agentResult)" class="save-bugs-button">
              💾 保存 {{ message.agentResult.bugs_found.length }} 个 Bug
            </button>
            <span class="bugs-count">发现 {{ message.agentResult.bugs_found.length }} 个问→</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 临时卡片确认（新建预览未指定卡片时） -->
    <div v-for="p in tempCardProposals" :key="p.scopeKey" class="temp-card-proposal-bar">
      <span class="temp-card-proposal-text">{{
        t('chat.tempCardProposal', { plan: p.planLabel, cardTitle: p.cardTitle })
      }}</span>
      <div class="temp-card-proposal-actions">
        <button type="button" class="temp-card-proposal-btn temp-card-proposal-btn--approve" @click="approveTempCardProposal(p)">
          {{ t('chat.tempCardApprove') }}
        </button>
        <button type="button" class="temp-card-proposal-btn temp-card-proposal-btn--reject" @click="rejectTempCardProposal(p)">
          {{ t('chat.tempCardReject') }}
        </button>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-container">
      <div 
        class="input-box-wrapper"
        :class="{ 'input-box-wrapper--dragover': isDragOver }"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="handleImageDrop"
      >
        <!-- 图片缩略图预览 -->
        <div v-if="pendingImages.length > 0" class="pending-images-row">
          <div v-for="(img, idx) in pendingImages" :key="idx" class="pending-image-item">
            <img
              :src="img.data"
              class="pending-thumb"
              :alt="t('chat.imagePreview')"
              @click.stop="openImagePreview(img.data, img.filename)"
            />
            <button type="button" class="pending-image-remove" @click.stop="removePendingImage(idx)" :title="t('chat.removeImage')">×</button>
          </div>
        </div>
        <textarea 
          ref="textareaRef"
          v-model="inputMessage"
          @input="autoResize"
          @keydown.enter.exact="handleSend"
          @keydown.enter.shift.exact="addNewLine"
          @paste="onPasteMainComposer"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          :placeholder="t('chat.placeholderWithImage')"
          class="message-input"
          rows="1"
        ></textarea>
        
        <div class="input-footer">
          <div class="footer-left">
            <div class="selector-item">
              <select v-model="selectedAgent" class="footer-select">
                <option value="agent">{{ t('chat.agentMode') }}</option>
                <option value="chat">{{ t('chat.chatMode') }}</option>
              </select>
            </div>
            <!-- 移除 ReAct/执行选择器 - 统一使用 ReAct 模式 -->
          <div class="selector-item model-select-wrapper">
            <img
              v-if="isQwenModel"
              :src="qwenIcon"
              alt="Qwen"
              class="model-icon"
            />
            <img
              v-else-if="isGlmModel"
              :src="glmIcon"
              alt="GLM"
              class="model-icon"
            />
            <img
              v-else-if="isDeepSeekModel || isAutoModel"
              :src="deepThinkingIcon"
              :alt="isAutoModel ? 'Auto' : 'DeepSeek'"
              class="model-icon"
            />
            <select v-model="selectedModel" @change="saveModelSelection" class="footer-select">
              <option
                v-for="opt in chatModelOptions"
                :key="opt.id"
                :value="opt.id"
              >{{ opt.label }}</option>
            </select>
          </div>
          </div>
          <div class="footer-right">
            <input
              ref="imageFileInputRef"
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
              multiple
              style="display: none"
              @change="handleImageSelect"
            />
            <button
              type="button"
              class="image-upload-button"
              :class="{ 'image-upload-button--active': pendingImages.length > 0 }"
              :title="t('chat.uploadImageAlt')"
              @click="triggerImageSelect"
            >
              <img :src="imageUploadIcon" :alt="t('chat.uploadImageAlt')" class="image-upload-icon" />
            </button>
            <button
              v-if="!isSending"
              type="button"
              @click="handleSend"
              class="send-icon-button"
              :disabled="!inputMessage.trim() && pendingImages.length === 0"
              :title="t('chat.send')"
            >
              <img class="send-icon-img" :src="sendCursorIcon" alt="send" />
            </button>
            <button 
              v-else
              type="button"
              @click.stop="handleStop" 
              class="stop-icon-button"
              :title="t('chat.stop')"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <rect x="6" y="6" width="12" height="12" rx="2"></rect>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted, watch, computed, toRaw, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import {
  BACKEND_BASE_URL,
  getChatSession,
  addChatMessage,
  saveAgentBugs,
  generateSessionTitle,
  getBugDetail
} from '../api.js'
import {
  patchAgentRunSeq,
  patchAgentRunSnapshot,
  getAgentRun,
  clearAgentRun,
  saveDraft,
  getDraft,
  clearDraft,
  AGENT_RUN_STALE_MS
} from '../utils/bcdSessionStore.js'
import { apiLocaleParam } from '../i18n/index.js'
import EvidenceCard from './EvidenceCard.vue'
import StepTimeline from './StepTimeline.vue'
import StreamingMessage from './StreamingMessage.vue'
import AgentTaskRun from './AgentTaskRun.vue'
import ExecutionResult from './ExecutionResult.vue'
import CreatePreview from './CreatePreview.vue'
import deepThinkingIcon from '../assets/deep-thinking-icon.svg'
import chevronDownIcon from '../assets/chevron-down-qoder.png'
import qwenIcon from '../assets/qwen-icon.png'
import glmIcon from '../assets/glm-icon.png'
import sendCursorIcon from '../assets/send-cursor.png'
import imageUploadIcon from '../assets/image-upload-icon.png'
import {
  createReactAiMessageState,
  foldAgentSseText,
  consumeAgentSseV1Chunk,
  yieldAgentSseUiFrame,
  createSseUiPaintScheduler,
  sseChunkNeedsImmediatePaint,
  shouldMergeModifyPreviewItems,
  DETAIL_FIELDS,
  extractToolName
} from '../composables/useAgentStream.js'
import { pruneTrailingPhantomAgentSteps } from '../composables/reactObservationStream.js'
import { reconcileReactMessageAfterSseClose } from '../composables/reactEngineLegacyStream.js'
import { isElectronPtyAvailable } from '../utils/electronPtySocketAdapter.js'
import { stripReasoningChannelArtifacts } from '../utils/stripReasoningChannelArtifacts.js'
import { snowflakeIdStr } from '../utils/snowflakeId.js'
import { diffReviewPushShared } from '../composables/useDiffReviewPush.js'
import {
  readBugReproductionStepsFromRow,
  formatBugReproductionStepsForDisplay,
  readBugExpectedResultFromRow,
  formatBugExpectedResultForDisplay,
  BUG_EXPECTED_RESULT_KEYS,
  BUG_EXPECTED_PENDING_ALIASES,
  enrichBugSandboxDiffRows
} from '../utils/bugModifyFields.js'
import {
  normalizeTestcaseModifyFieldKey,
  isTestcaseDetailModifyField,
  getTestcaseModifyModKeys,
  getTestcaseFieldLabel,
  formatTestcaseModifyFieldValue,
  formatTestcaseSelectFieldLabel,
  isTestcaseSelectDetailField,
  readTestcaseModifySideValue,
  readTestcaseDetailRawField,
  testcaseDetailFieldValuesEqual,
  normalizeTestcaseSandboxDiffRow,
  enrichTestcaseSandboxDiffRows,
  buildTestcaseRelatedDefectTitleMap,
  collectTestcaseRelatedDefectIdsFromNav,
  isPlaceholderTestcaseDefectTitle,
  remapMislabeledTestcaseSandboxFieldKey,
  isTestcaseExecutionResultEnumValue,
  TESTCASE_DETAIL_FIELDS,
  TESTCASE_LIST_FIELDS,
  TESTCASE_FIELD_LABEL_I18N
} from '../utils/testcaseModifyFields.js'
import {
  localGoProxyOk as sharedLocalGoProxyRef,
  pingLocalGoProxy as sharedPingLocalGoProxy
} from '../composables/useLocalGoProxyStatus'

// Props
const props = defineProps({
  sessionId: {
    type: Number,
    required: false,
    default: null
  },
  projectId: {
    type: Number,
    required: false,
    default: null
  },
  /** 已由项目页拉取时传入，后端 gather 可跳过 Redis/MySQL 查项目名（压低首包延迟） */
  projectDisplayName: {
    type: String,
    required: false,
    default: ''
  },
  /** 左侧计划树当前选中的迭代计划 id（字符串，避免大整数精度丢失） */
  planId: {
    type: [String, Number],
    required: false,
    default: null
  }
})

const emit = defineEmits(['title-updated'])

const { t } = useI18n()

/** 由 ProjectDetail 在打开项目时拉取（mode=recent），避免每条对话在后端做向量检索 */
const projectLongMemoryContext = inject('projectLongMemoryContext', null)
/** 项目页当前聚焦的 Bug/用例等（雪花 record_id），供 Agent 复制新建 */
const agentUiContext = inject('agentUiContext', null)

const agentUiContextForReact = () => {
  try {
    const r =
      agentUiContext && typeof agentUiContext === 'object' && 'value' in agentUiContext
        ? agentUiContext.value
        : agentUiContext
    if (!r || typeof r !== 'object') return {}
    const rid = r.record_id ?? r.recordId
    if (rid == null || String(rid).trim() === '') return {}
    return { ui_context: r }
  } catch (_e) {
    return {}
  }
}

const localGoProxyOk = inject('localGoProxyOk', sharedLocalGoProxyRef)
const pingLocalGoProxy = inject('pingLocalGoProxy', sharedPingLocalGoProxy)
/** 浏览器 + Agent：本地代理未运行时顶部提示 */
const agentLocalProxyHint = ref('')
const longMemoryContextForReact = () => {
  try {
    const r = projectLongMemoryContext
    const v = r && typeof r === 'object' && 'value' in r ? r.value : null
    if (!v || typeof v !== 'object') return {}
    const txt = String(v.long_memory_text || '').trim()
    const items = v.long_memory_items
    if (!txt && (!Array.isArray(items) || !items.length)) return {}
    return { long_memory_context: { long_memory_text: txt, long_memory_items: Array.isArray(items) ? items : [] } }
  } catch (e) {
    return {}
  }
}

const localeForApi = () => apiLocaleParam()

/**
 * 首轮 Thought / think 阶段 SSE 排查：开启任一方式后刷新页面，控制台输出 [REACT-THINK-SSE]
 * - localStorage.setItem('badcase_debug_react_sse','1')
 * - URL 查询参数 debug_react_sse=1（与 hash 路由兼容：可以是 ?debug_react_sse=1 或 #/path?debug_react_sse=1）
 * 默认后端 REACT_THINK_CONTENT_ONLY=1 时，模型主输出走 content_delta，SSE 多为 todos_stream；reasoning 仅在模型侧有 reasoning_delta 时出现
 */
function readDebugReactThinkSSE() {
  try {
    if (typeof window === 'undefined' || typeof localStorage === 'undefined') return false
    if (localStorage.getItem('badcase_debug_react_sse') === '1') return true
    const q = window.location.search || ''
    const h = String(window.location.hash || '')
    const fromSearch = new URLSearchParams(q).get('debug_react_sse') === '1'
    const hashQuery = h.includes('?') ? h.slice(h.indexOf('?')) : ''
    const fromHash = hashQuery ? new URLSearchParams(hashQuery).get('debug_react_sse') === '1' : false
    return fromSearch || fromHash
  } catch {
    return false
  }
}
const isDebugReactThinkSSE = readDebugReactThinkSSE()

const messages = ref([])
/** 新建预览缺卡片时：对话区确认是否创建临时 Bug/BadCase/用例卡片 */
const tempCardProposals = ref([])
/** 已发起临时卡片确认、尚未落列表时隐藏沙箱新建预览 */
const createAwaitingTempCardMessageIds = ref([])
/** 沙箱/修改预览：关联缺陷 id → Bug 标题（按需 getBugDetail 补全） */
const sandboxBugTitleById = ref({})
/** GET /api/chat-sessions/:id 同步，用于判断是否为默认标题并触发生成 */
const sessionTitleRef = ref('')
const titleGenInFlight = ref(false)

function isPlaceholderSessionTitle(title) {
  const s = String(title ?? '').trim().toLowerCase()
  if (!s) return true
  if (s === 'newchat' || s === 'new chat' || s.startsWith('newchat')) return true
  if (s === '未命名会话' || s === 'untitled session') return true
  return false
}

  /** 新建预览：与左侧列表列一致，避免长文/详情字段占满卡片 */
  const CREATE_PREVIEW_LIST_FIELDS = {
    bug: new Set([
      'title',
      'status',
      'priority',
      'severity',
      'assignee',
      'assignee_id',
      'owner',
      'bug_type',
      'plan_id',
      'environment',
      'browser',
      'os'
    ]),
    badcase: new Set([
      'title',
      'status',
      'priority',
      'assignee',
      'assignee_id',
      'case_category',
      'plan_id',
      'document_type'
    ]),
    testcase: new Set([
      'title',
      'status',
      'priority',
      'assignee',
      'assignee_id',
      'case_type',
      'test_type',
      'plan_id',
      'version'
    ]),
    plan: new Set(['name', 'title', 'plan_type', 'status', 'priority', 'parent_id', 'start_date', 'end_date', 'cycle'])
  }

  const filterCreatePreviewDiff = (diff, target) => {
    if (!Array.isArray(diff) || diff.length === 0) return []
    const t = (target || 'bug').toLowerCase()
    const allow = CREATE_PREVIEW_LIST_FIELDS[t] || CREATE_PREVIEW_LIST_FIELDS.bug
    return diff.filter((fd) => {
      const f = fd && fd.field
      if (!f) return false
      return allow.has(f)
    })
  }

  /** 统一归一 diff 行字段名与 i18n 标签，并补全测例属性快照 */
  const inferSandboxNavTarget = (ctx, groupTarget = null) => {
    const explicit = String(groupTarget || ctx?.target || '')
      .trim()
      .toLowerCase()
    if (explicit === 'testcase' || explicit === 'test_case') return 'testcase'
    const mods = ctx?.modifications
    if (mods && typeof mods === 'object') {
      if (Object.keys(mods).some((k) => isTestcaseDetailModifyField(k))) return 'testcase'
    }
    const b = ctx?.before
    if (
      b &&
      typeof b === 'object' &&
      (b.case_type != null ||
        b.testcase_type != null ||
        b.steps != null ||
        b.preconditions != null ||
        b.execution_result != null ||
        b.executionResult != null ||
        b.related_defects != null ||
        b.append_comment != null)
    ) {
      return 'testcase'
    }
    if (Array.isArray(ctx?.diff)) {
      if (ctx.diff.some((fd) => isTestcaseDetailModifyField(fd?.field, fd?.field_label))) {
        return 'testcase'
      }
    }
    return explicit
  }

  const mergeSandboxDefectTitleMap = (nav) => ({
    ...sandboxBugTitleById.value,
    ...buildTestcaseRelatedDefectTitleMap(nav)
  })

  const hydrateSandboxDefectTitles = async (nav) => {
    if (!nav || typeof nav !== 'object') return
    const merged = mergeSandboxDefectTitleMap(nav)
    const ids = collectTestcaseRelatedDefectIdsFromNav(nav).filter(
      (id) => !merged[id] || isPlaceholderTestcaseDefectTitle(id, merged[id])
    )
    if (!ids.length) return
    const updates = {}
    await Promise.all(
      ids.map(async (id) => {
        if (
          sandboxBugTitleById.value[id] &&
          !isPlaceholderTestcaseDefectTitle(id, sandboxBugTitleById.value[id])
        ) {
          return
        }
        try {
          const res = await getBugDetail(id)
          const payload = res?.data
          const bug =
            payload?.bug ??
            payload?.data ??
            (payload?.success && payload?.title != null ? payload : null)
          const title = String(bug?.title ?? '').trim()
          if (!title || isPlaceholderTestcaseDefectTitle(id, title)) return
          updates[id] = title
        } catch (_e) {
          /* ignore */
        }
      })
    )
    if (Object.keys(updates).length) {
      sandboxBugTitleById.value = { ...sandboxBugTitleById.value, ...updates }
    }
  }

  const collectModifyNavsFromMessages = (msgs) => {
    const navs = []
    if (!Array.isArray(msgs)) return navs
    for (const msg of msgs) {
      if (msg?.modifyNavigation) navs.push(msg.modifyNavigation)
      for (const grp of msg.modifyGroups || []) {
        for (const it of grp.items || []) {
          if (it && typeof it === 'object') navs.push(it)
        }
        if (Array.isArray(grp.batch_results)) {
          for (const br of grp.batch_results) {
            if (br && typeof br === 'object') navs.push(br)
          }
        }
      }
      const nav = msg?.modifyNavigation
      if (nav && Array.isArray(nav.batch_results)) {
        for (const br of nav.batch_results) {
          if (br && typeof br === 'object') navs.push(br)
        }
      }
    }
    return navs
  }

  watch(
    messages,
    (msgs) => {
      for (const nav of collectModifyNavsFromMessages(msgs)) {
        void hydrateSandboxDefectTitles(nav)
      }
    },
    { deep: true }
  )

  const resolveSandboxDiffRowsForDisplay = (ctx, groupTarget = null) => {
    const tgt = inferSandboxNavTarget(ctx, groupTarget)
    const base = Array.isArray(ctx?.diff) ? ctx.diff : []
    const navObj = {
      target: tgt || ctx?.target,
      before: ctx?.before,
      after: ctx?.after,
      modifications: ctx?.modifications,
      diff: base
    }
    void hydrateSandboxDefectTitles(navObj)
    const tcRows = enrichTestcaseSandboxDiffRows(navObj, base, t, {
      defectTitleMap: mergeSandboxDefectTitleMap(navObj)
    })
    return enrichBugSandboxDiffRows(navObj, tcRows)
  }

  const countGroupSandboxDisplayRows = (group) => {
    if (!group?.items?.length) return 0
    let n = 0
    for (const git of group.items) {
      n += resolveSandboxDiffRowsForDisplay(git, group.target).length
    }
    return n
  }

  /** 单条 batch_result 展平为沙箱 diff 行（供批量卡片按条判断是否仍待确认） */
  const getBatchItemSandboxDiffRows = (br, navTarget = null) => {
    if (!br || typeof br !== 'object') return []
    const tid = br.target_id ?? br.targetId
    const title =
      (br.record_title && String(br.record_title).trim()) ||
      (br.before && (br.before.title || br.before.name) && String(br.before.title || br.before.name).trim()) ||
      ''
    const head =
      tid != null
        ? `#${tid}${title ? ` ${title.slice(0, 40)}${title.length > 40 ? '...' : ''}` : ''}`
        : ''
    const resolved = resolveSandboxDiffRowsForDisplay(br, navTarget || br.target)
    if (!head) return resolved
    return resolved.map((fd) => {
      const fl = fd.field_label || getTestcaseFieldLabel(t, fd.field, fd.field_label)
      return { ...fd, field_label: `${head} · ${fl}` }
    })
  }

  /** 沙箱卡片内展示的 diff 行：新建仅列表字段；修改仍展示全部；批量预览取 batch_results（nav.diff 仅单条时有值） */
  const getSandboxDiffRows = (message) => {
    const nav = message?.modifyNavigation
    if (!nav) return []
    if (nav.is_create) return filterCreatePreviewDiff(nav.diff, nav.target)
    if (
      nav.batch_modify === true &&
      Array.isArray(nav.batch_results) &&
      nav.batch_results.length > 0
    ) {
      const rows = []
      for (const br of nav.batch_results) {
        rows.push(...getBatchItemSandboxDiffRows(br, nav.target))
      }
      return rows
    }
    return resolveSandboxDiffRowsForDisplay(nav)
  }

  /** Bug/卡片：优先级在沙箱里与表单一致；优先读 modifications / before.after，避免 diff 行「紧急→紧急」 */
  const formatSandboxBugPriorityText = (raw) => {
    if (raw == null || String(raw).trim() === '') return ''
    const s = String(raw).trim().toLowerCase()
    const map = { p1: 'P1 - 紧急', p2: 'P2 - 高', p3: 'P3 - 中', p4: 'P4 - 低' }
    if (map[s]) return map[s]
    return String(raw).trim()
  }

  /** 沙箱状态列：与列表 i18n 一致，避免英文枚举直接展示；未知值原样返回 */
  const formatSandboxBugStatusText = (raw) => {
    const s = String(raw ?? '')
      .trim()
      .toLowerCase()
    if (!s) return ''
    const keyMap = {
      new: 'list.statusNew',
      pending: 'list.statusPending',
      resolved: 'list.statusResolved',
      closed: 'list.statusClosed',
      close: 'list.statusClosed',
      hold: 'list.statusHold',
      reopened: 'list.statusReopen',
      reopen: 'list.statusReopen',
      not_badcase: 'list.statusNotType',
      draft: 'list.badcaseStatus.draft',
      review: 'list.badcaseStatus.review',
      active: 'list.badcaseStatus.active',
      archived: 'list.badcaseStatus.archived'
    }
    const i18nKey = keyMap[s]
    if (i18nKey) {
      if (i18nKey === 'list.statusNotType') {
        return t(i18nKey, { type: t('list.types.badcase') })
      }
      return t(i18nKey)
    }
    return String(raw).trim()
  }

  /** BadCase 行快照：兼容 snake/camel 与误用的 classification 键 */
  const readBadcaseCaseCategoryFromRow = (row) => {
    if (!row || typeof row !== 'object') return ''
    const v = row.case_category ?? row.caseCategory ?? row.classification
    return v != null ? String(v).trim() : ''
  }

  /** 模型/ diff 行字段名归一（与详情、modify 工具一致） */
  const normalizeSandboxFieldKey = (fk, label = '', tgt = '') => {
    const t = String(tgt || '')
      .trim()
      .toLowerCase()
    if (t === 'testcase' || t === 'test_case') {
      return normalizeTestcaseModifyFieldKey(fk, label)
    }
    const tcNk = normalizeTestcaseModifyFieldKey(fk, label)
    if (TESTCASE_DETAIL_FIELDS.includes(tcNk) || TESTCASE_LIST_FIELDS.includes(tcNk)) {
      return tcNk
    }
    const f = String(fk || '')
      .trim()
      .toLowerCase()
      .replace(/-/g, '_')
    const lab = String(label || '').trim()
    if (f === 'precondition' || lab === 'precondition' || lab === '前置条件') return 'preconditions'
    if (f === 'reproduce_steps' || f === 'steps_to_reproduce') return 'reproduction_steps'
    if (lab === '复现步骤' || lab.includes('复现步骤')) return 'reproduction_steps'
    if (t === 'bug' && f === 'steps') return 'reproduction_steps'
    if (
      t === 'bug' &&
      (f === 'expected' ||
        f === 'expected_result' ||
        lab === '期望结果' ||
        lab === '预期结果' ||
        (lab.includes('期望') && lab.includes('结果')) ||
        (lab.includes('预期') && lab.includes('结果')))
    ) {
      return 'expected_result'
    }
    if (
      t === 'bug' &&
      (f === 'actual' ||
        f === 'actual_result' ||
        lab === '实际结果' ||
        (lab.includes('实际') && lab.includes('结果')))
    ) {
      return 'actual_result'
    }
    return f || lab
  }

  const readSandboxModifySideRaw = (ctx, fieldDiff, which) => {
    const tgt = String(ctx?.target || '').toLowerCase()
    let fk = normalizeSandboxFieldKey(fieldDiff?.field, fieldDiff?.field_label, tgt)
    const label = String(fieldDiff?.field_label || '')
    const mods = ctx?.modifications && typeof ctx.modifications === 'object' ? ctx.modifications : {}
    const lineNew = fieldDiff?.lines?.find((l) => l.type === 'add')?.content
    const lineOld = fieldDiff?.lines?.find((l) => l.type === 'delete')?.content
    const modExec = mods.execution_result
    const modStatus = mods.status
    const sampleNew =
      (modExec && typeof modExec === 'object' ? modExec.new : null) ??
      (modStatus && typeof modStatus === 'object' ? modStatus.new : null) ??
      lineNew
    const sampleOld =
      (modExec && typeof modExec === 'object' ? modExec.old : null) ??
      (modStatus && typeof modStatus === 'object' ? modStatus.old : null) ??
      lineOld
    if (tgt === 'testcase' || tgt === 'test_case') {
      fk = remapMislabeledTestcaseSandboxFieldKey(
        fk,
        label,
        which === 'old' ? sampleOld : sampleNew
      )
    }
    const isPriority =
      fk === 'priority' ||
      fk === 'severity' ||
      label.includes('优先级') ||
      label.includes('严重程度') ||
      label.includes('严重级别')
    const isTcExecution =
      (tgt === 'testcase' || tgt === 'test_case') &&
      (fk === 'execution_result' ||
        isTestcaseExecutionResultEnumValue(which === 'old' ? sampleOld : sampleNew))
    const isStatus =
      !isTcExecution &&
      (fk === 'status' ||
        (/状态/.test(label) && !/执行结果|test\s*result/i.test(label)))
    if (isPriority && mods.priority && typeof mods.priority === 'object') {
      const v = which === 'old' ? mods.priority.old : mods.priority.new
      if (v != null && String(v).trim() !== '') return String(v).trim()
    }
    if (isStatus && mods.status && typeof mods.status === 'object') {
      const v = which === 'old' ? mods.status.old : mods.status.new
      if (v != null && String(v).trim() !== '') return String(v).trim()
    }
    if ((tgt === 'bug' || tgt === 'badcase' || tgt === 'testcase' || tgt === 'card') && isPriority) {
      const b = ctx?.before
      const a = ctx?.after
      if (which === 'old' && b?.priority != null && String(b.priority).trim() !== '') return String(b.priority).trim()
      if (which === 'new' && a?.priority != null && String(a.priority).trim() !== '') return String(a.priority).trim()
    }
    if ((tgt === 'bug' || tgt === 'badcase' || tgt === 'testcase' || tgt === 'card') && isStatus) {
      const b = ctx?.before
      const a = ctx?.after
      if (which === 'old' && b?.status != null && String(b.status).trim() !== '') return String(b.status).trim()
      if (which === 'new' && a?.status != null && String(a.status).trim() !== '') return String(a.status).trim()
    }

    const isBugRepro =
      tgt === 'bug' &&
      (fk === 'reproduction_steps' ||
        fk === 'steps_to_reproduce' ||
        fk === 'reproduce_steps' ||
        fk === 'steps' ||
        label.includes('复现步骤'))
    if (isBugRepro) {
      for (const mk of ['steps_to_reproduce', 'reproduction_steps', 'reproduce_steps']) {
        const m = mods[mk]
        if (m && typeof m === 'object') {
          const v = which === 'old' ? m.old : m.new
          if (v != null && String(v).trim() !== '') {
            return formatBugReproductionStepsForDisplay(v)
          }
        }
      }
      const row = which === 'old' ? ctx?.before : ctx?.after
      const fromRow = readBugReproductionStepsFromRow(row)
      if (fromRow) return formatBugReproductionStepsForDisplay(fromRow)
      if (which === 'old' && Array.isArray(messages.value)) {
        const tid = snowflakeIdStr(ctx?.target_id ?? ctx?.targetId ?? ctx?.id)
        if (tid) {
          try {
            const merged = getMergedPendingForTarget(messages.value, 'bug', tid)
            const fromMerged = readBugReproductionStepsFromRow(merged?.before)
            if (fromMerged) return formatBugReproductionStepsForDisplay(fromMerged)
          } catch (_e) {
            /* noop */
          }
        }
      }
    }

    const isBugExpected =
      tgt === 'bug' &&
      (fk === 'expected_result' ||
        fk === 'expected' ||
        label === '期望结果' ||
        label === '预期结果' ||
        (label.includes('期望') && label.includes('结果')) ||
        (label.includes('预期') && label.includes('结果')))
    if (isBugExpected && (tgt === 'bug' || tgt === 'card')) {
      for (const mk of [...BUG_EXPECTED_RESULT_KEYS, ...BUG_EXPECTED_PENDING_ALIASES]) {
        const m = mods[mk]
        if (m && typeof m === 'object') {
          const v = which === 'old' ? m.old : m.new
          if (v != null && String(v).trim() !== '') {
            return formatBugExpectedResultForDisplay(v)
          }
        }
      }
      const row = which === 'old' ? ctx?.before : ctx?.after
      const fromRow = readBugExpectedResultFromRow(row)
      if (fromRow) return formatBugExpectedResultForDisplay(fromRow)
      if (which === 'old' && Array.isArray(messages.value)) {
        const tid = snowflakeIdStr(
          tgt === 'card' ? ctx?.before?.source_id ?? ctx?.after?.source_id : null
        ) ?? snowflakeIdStr(ctx?.target_id ?? ctx?.targetId ?? ctx?.id)
        const nt = tgt === 'card' ? 'bug' : tgt
        if (tid) {
          try {
            const merged = getMergedPendingForTarget(messages.value, nt, tid)
            const fromMerged = readBugExpectedResultFromRow(merged?.before)
            if (fromMerged) return formatBugExpectedResultForDisplay(fromMerged)
          } catch (_e) {
            /* noop */
          }
        }
      }
    }

    /** 详情字段：diff delete 常为空，须读 modifications / before / 会话合并快照 */
    const isTcDetail =
      (tgt === 'testcase' || tgt === 'test_case') && isTestcaseDetailModifyField(fk, label)
    const isOtherDetail =
      (tgt !== 'testcase' && tgt !== 'test_case') && DETAIL_FIELDS.includes(fk) && !isBugRepro
    if (isTcDetail || isOtherDetail) {
      if (isTcDetail) {
        const defectMap =
          fk === 'related_defects' ? mergeSandboxDefectTitleMap(ctx) : null
        const fromTc = readTestcaseModifySideValue(
          ctx,
          fk,
          fieldDiff?.field,
          label,
          which,
          mods,
          t,
          defectMap
        )
        if (fromTc) return fromTc
      } else {
        const modKeys = getTestcaseModifyModKeys(fk, fieldDiff?.field)
        for (const mk of modKeys) {
          const m = mods[mk]
          if (m && typeof m === 'object') {
            const v = which === 'old' ? m.old : m.new
            const formatted = formatTestcaseModifyFieldValue(fk, v, { t })
            if (formatted) return formatted
          }
        }
        const row = which === 'old' ? ctx?.before : ctx?.after
        const defectMapRow =
          fk === 'related_defects' ? mergeSandboxDefectTitleMap(ctx) : null
        const fromRow = readTestcaseModifySideValue(
          ctx,
          fk,
          fieldDiff?.field,
          label,
          which,
          {},
          t,
          defectMapRow
        )
        if (fromRow) return fromRow
      }
      const tid = snowflakeIdStr(ctx?.target_id ?? ctx?.targetId ?? ctx?.id)
      const nt = tgt === 'test_case' ? 'testcase' : tgt
      if (tid && which === 'old' && Array.isArray(messages.value)) {
        try {
          const merged = getMergedPendingForTarget(messages.value, nt, tid)
          const snap = merged?.before && typeof merged.before === 'object' ? merged.before : null
          if (isTcDetail) {
            const defectMapMerged =
              fk === 'related_defects'
                ? mergeSandboxDefectTitleMap({ before: snap, after: null, modifications: mods })
                : null
            const fromMerged = readTestcaseModifySideValue(
              { before: snap, after: null },
              fk,
              fieldDiff?.field,
              label,
              'old',
              mods,
              t,
              defectMapMerged
            )
            if (fromMerged) return fromMerged
          }
        } catch (_e) {
          /* noop */
        }
      }
    }

    /** BadCase：沙箱 diff 行可能用 classification，库字段为 case_category；补全旧值避免误显示「未设置」 */
    const isBadcaseCaseCategory =
      (tgt === 'badcase' || tgt === 'bad_case') &&
      (fk === 'case_category' ||
        fk === 'classification' ||
        fk === 'category' ||
        fk.includes('问题分类') ||
        label.includes('问题分类'))
    const ccMod =
      isBadcaseCaseCategory &&
      ((mods.case_category && typeof mods.case_category === 'object' && mods.case_category) ||
        (mods.classification && typeof mods.classification === 'object' && mods.classification) ||
        (mods.category && typeof mods.category === 'object' && mods.category) ||
        null)
    if (ccMod) {
      const v = which === 'old' ? ccMod.old : ccMod.new
      if (v != null && String(v).trim() !== '') return String(v).trim()
    }
    if (isBadcaseCaseCategory) {
      const b = ctx?.before
      const a = ctx?.after
      if (which === 'old') {
        const cv = readBadcaseCaseCategoryFromRow(b)
        if (cv) return cv
      } else {
        const cv = readBadcaseCaseCategoryFromRow(a)
        if (cv) return cv
      }
    }

    // 分组/批量项上常缺 before：从本会话合并后的待采纳 payload 补 status（与列表、详情 reconcile 一致）
    if (isStatus && (which === 'old' || which === 'new')) {
      const tid = snowflakeIdStr(ctx?.target_id ?? ctx?.targetId ?? ctx?.id)
      const nt = tgt || 'bug'
      if (tid && Array.isArray(messages.value)) {
        try {
          const merged = getMergedPendingForTarget(messages.value, nt, tid)
          if (which === 'old') {
            const b = merged?.before && typeof merged.before === 'object' ? merged.before : null
            if (b?.status != null && String(b.status).trim() !== '') return String(b.status).trim()
          } else {
            const a = merged?.after && typeof merged.after === 'object' ? merged.after : null
            if (a?.status != null && String(a.status).trim() !== '') return String(a.status).trim()
          }
        } catch (_e) {
          /* noop */
        }
      }
    }
    // target=card 时 before 常缺 status（或沙箱库未联到 Bug）：用 source_id 或同会话中带 card_id 的源表快照补旧状态
    if (isStatus && which === 'old' && tgt === 'card' && Array.isArray(messages.value)) {
      const sid = snowflakeIdStr(ctx?.before?.source_id ?? ctx?.after?.source_id)
      if (sid) {
        for (const st of ['bug', 'badcase', 'testcase']) {
          try {
            const m = getMergedPendingForTarget(messages.value, st, sid)
            const stv = m?.before && String(m.before.status ?? '').trim()
            if (stv) return stv
          } catch (_e2) {
            /* noop */
          }
        }
      }
      const cardId = snowflakeIdStr(ctx?.target_id ?? ctx?.targetId ?? ctx?.id)
      if (cardId) {
        for (const msg of messages.value) {
          if (!msg || msg.isUser) continue
          const nav = msg.modifyNavigation
          const blocks = []
          if (nav?.batch_modify && Array.isArray(nav.batch_results)) {
            blocks.push(...nav.batch_results)
          } else if (nav && !nav.is_create) {
            blocks.push(nav)
          }
          for (const block of blocks) {
            const bb = block?.before
            if (!bb || typeof bb !== 'object') continue
            if (snowflakeIdStr(bb.card_id ?? bb.cardId) !== cardId) continue
            const stv = String(bb.status ?? '').trim()
            if (stv) return stv
          }
          for (const grp of msg.modifyGroups || []) {
            for (const it of grp.items || []) {
              const bb = it?.before
              if (!bb || typeof bb !== 'object') continue
              if (snowflakeIdStr(bb.card_id ?? bb.cardId) !== cardId) continue
              const stv = String(bb.status ?? '').trim()
              if (stv) return stv
            }
          }
        }
      }
    }
    const lineType = which === 'old' ? 'delete' : 'add'
    const line = fieldDiff?.lines?.find((l) => l.type === lineType)
    return line?.content != null ? String(line.content).trim() : ''
  }

  const formatSandboxModifySideDisplay = (ctx, fieldDiff, which) => {
    const tgt = String(ctx?.target || '').toLowerCase()
    let fk = normalizeSandboxFieldKey(fieldDiff?.field, fieldDiff?.field_label, tgt)
    const label = String(fieldDiff?.field_label || '')
    const mods = ctx?.modifications && typeof ctx.modifications === 'object' ? ctx.modifications : {}
    const lineNew = fieldDiff?.lines?.find((l) => l.type === 'add')?.content
    const lineOld = fieldDiff?.lines?.find((l) => l.type === 'delete')?.content
    const modExec = mods.execution_result
    const modStatus = mods.status
    const sampleNew =
      (modExec && typeof modExec === 'object' ? modExec.new : null) ??
      (modStatus && typeof modStatus === 'object' ? modStatus.new : null) ??
      lineNew
    const sampleOld =
      (modExec && typeof modExec === 'object' ? modExec.old : null) ??
      (modStatus && typeof modStatus === 'object' ? modStatus.old : null) ??
      lineOld
    if (tgt === 'testcase' || tgt === 'test_case') {
      fk = remapMislabeledTestcaseSandboxFieldKey(
        fk,
        label,
        which === 'old' ? sampleOld : sampleNew
      )
    }
    const isPriority =
      fk === 'priority' ||
      fk === 'severity' ||
      label.includes('优先级') ||
      label.includes('严重程度') ||
      label.includes('严重级别')
    const isTcExecution =
      (tgt === 'testcase' || tgt === 'test_case') &&
      (fk === 'execution_result' ||
        isTestcaseExecutionResultEnumValue(which === 'old' ? sampleOld : sampleNew))
    const isStatus =
      !isTcExecution &&
      (fk === 'status' ||
        (/状态/.test(label) && !/执行结果|test\s*result/i.test(label)))
    const raw = readSandboxModifySideRaw(ctx, fieldDiff, which)
    if (raw === '') return ''
    const isTcField = isTestcaseDetailModifyField(fk, label) || isTcExecution
    if (isTcField && (isTestcaseSelectDetailField(fk) || isTcExecution)) {
      return formatTestcaseSelectFieldLabel(fk, raw, t)
    }
    if (isTcField) {
      const titleMap =
        fk === 'related_defects' ? mergeSandboxDefectTitleMap(ctx) : undefined
      return formatTestcaseModifyFieldValue(fk, raw, { t, titleMap })
    }
    if ((tgt === 'testcase' || tgt === 'test_case') && isPriority) {
      return formatTestcaseModifyFieldValue('priority', raw)
    }
    if ((tgt === 'bug' || tgt === 'badcase' || tgt === 'testcase' || tgt === 'card') && isPriority) {
      return formatSandboxBugPriorityText(raw)
    }
    if ((tgt === 'bug' || tgt === 'badcase' || tgt === 'testcase' || tgt === 'card') && isStatus) {
      return formatSandboxBugStatusText(raw)
    }
    return raw
  }

  /** 沙箱 diff 行标题：BadCase 常被标成「严重程度」，与详情里「优先级」表单一致 */
  const sandboxFieldHeaderLabel = (fd, ctx, groupTargetFallback = null) => {
    const fk = String(fd?.field || '').trim().toLowerCase()
    const lab = String(fd?.field_label || '').trim()
    const tgt = String((ctx && ctx.target) || groupTargetFallback || '')
      .trim()
      .toLowerCase()
    const lineNew = fd?.lines?.find((l) => l.type === 'add')?.content
    const lineOld = fd?.lines?.find((l) => l.type === 'delete')?.content
    const tcNk = remapMislabeledTestcaseSandboxFieldKey(
      normalizeTestcaseModifyFieldKey(fd?.field, lab),
      lab,
      lineNew ?? lineOld
    )
    if (
      tgt === 'testcase' ||
      tgt === 'test_case' ||
      TESTCASE_DETAIL_FIELDS.includes(tcNk) ||
      TESTCASE_LIST_FIELDS.includes(tcNk)
    ) {
      return getTestcaseFieldLabel(t, tcNk, lab)
    }
    if (tgt === 'badcase' || tgt === 'bad_case') {
      if (
        fk === 'base_problem' ||
        fk === 'similar_questions' ||
        fk === 'similar_question' ||
        /相似问题/.test(lab)
      ) {
        return '相似问题'
      }
      if (
        fk === 'reproduction_steps' ||
        fk === 'reproduce_steps' ||
        fk === 'steps_to_reproduce' ||
        /复现步骤/.test(lab)
      ) {
        return 'BadCase复现步骤'
      }
      if (fk === 'case_category' || fk === 'classification' || fk === 'category' || lab.includes('问题分类')) {
        return t('cardDetail.caseCategory')
      }
      if (fk === 'priority' || fk === 'severity' || /优先级|严重程度|严重级别/.test(lab)) {
        return t('cardDetail.priority')
      }
    }
    if (tgt === 'bug') {
      const nkBug = normalizeSandboxFieldKey(fd?.field, lab, tgt)
      if (nkBug === 'expected_result' || (lab.includes('期望') && lab.includes('结果')) || (lab.includes('预期') && lab.includes('结果'))) {
        return '期望结果'
      }
      if (nkBug === 'actual_result' || (lab.includes('实际') && lab.includes('结果'))) {
        return '实际结果'
      }
      if (fk === 'severity' || (/严重/.test(lab) && !lab.includes('优先级'))) return t('cardDetail.severity')
      if (fk === 'priority' || lab.includes('优先级')) return t('cardDetail.priority')
    }
    const nk = normalizeSandboxFieldKey(fd?.field, lab, tgt)
    const labelKeyByTarget = {
      bug: {
        title: 'cardDetail.title',
        status: 'cardDetail.status',
        assignee: 'cardDetail.assignee',
        priority: 'cardDetail.priority',
        severity: 'cardDetail.severity',
        steps_to_reproduce: 'cardDetail.reproducer',
        reproduction_steps: 'cardDetail.reproducer',
        expected_result: 'cardDetail.expected',
        actual_result: 'cardDetail.actual'
      },
      badcase: {
        title: 'cardDetail.title',
        status: 'cardDetail.status',
        assignee: 'cardDetail.assignee',
        priority: 'cardDetail.priority',
        case_category: 'cardDetail.caseCategory',
        base_problem: 'cardDetail.scenario',
        reproduction_steps: 'cardDetail.reproducer',
        answer: 'cardDetail.expected',
        correct_answer: 'cardDetail.expected',
        badcase_result: 'cardDetail.actual',
        solution: 'cardDetail.description',
        problem_reason: 'cardDetail.description'
      },
      bad_case: {
        title: 'cardDetail.title',
        status: 'cardDetail.status',
        assignee: 'cardDetail.assignee',
        priority: 'cardDetail.priority',
        case_category: 'cardDetail.caseCategory',
        reproduction_steps: 'cardDetail.reproducer'
      }
    }
    const bucket = labelKeyByTarget[tgt]
    if (bucket && bucket[nk]) {
      const tr = t(bucket[nk])
      if (tr && tr !== bucket[nk]) return tr
    }
    if (/^[\u4e00-\u9fff]/.test(lab)) return lab
    if (lab && !/^[a-z][a-z0-9_]*$/i.test(lab)) return lab
    return lab || nk || String(fd?.field || '') || ''
  }

  /** 从批量预览项中取记录标题，用于「同一ID / 同标题」合并沙箱分组 */
  const getModifyItemRecordTitle = (item) => {
    if (!item) return ''
    const b = item.before
    if (b && (b.title || b.name)) {
      return String(b.title || b.name).trim()
    }
    if (item.record_title) {
      return String(item.record_title).trim()
    }
    const rows = item.diff || []
    for (const fd of rows) {
      const fname = fd.field || fd.field_label || ''
      if (fname === 'title' || String(fname).includes('标题')) {
        const line = fd.lines?.find(l => l.type === 'delete') || fd.lines?.find(l => l.type === 'unchanged')
        if (line?.content) return String(line.content).trim()
      }
    }
    return ''
  }

  /** 是否已在某步「执行结果」下展示 grep 的 Bug 导航（避免底部再重复一块） */
  const grepNavigationOnSteps = (message) => {
    const steps = message?.steps
    if (!Array.isArray(steps) || !steps.length) return false
    return steps.some((s) => s && s.grepNavigation && s.grepNavigation.type === 'multiple')
  }

  /** grep 导航卡片标题：按条目 target 区分 Bug / BadCase / 测试用例 */
  const grepNavCardTitle = (message) => {
    const items = message?.navigation?.items
    if (!items?.length) return '点击跳转到列表'
    const ts = [...new Set(items.map((i) => (i?.target || 'bug').toString().toLowerCase()))]
    const labelKey = { bug: 'chat.navLabelBug', badcase: 'chat.navLabelBadcase', testcase: 'chat.navLabelTestcase' }
    if (ts.length === 1) {
      const k = ts[0]
      return t('chat.grepJumpTo', { type: t(labelKey[k] || 'chat.navLabelBug') })
    }
    return t('chat.grepJumpList')
  }

  const grepNavCardIcon = (message) => {
    const items = message?.navigation?.items
    if (!items?.length) return '📍'
    const ts = [...new Set(items.map((i) => (i?.target || 'bug').toString().toLowerCase()))]
    if (ts.length === 1) {
      if (ts[0] === 'bug') return '🐛'
      if (ts[0] === 'badcase') return '📋'
      if (ts[0] === 'testcase') return '📝'
    }
    return '📍'
  }

  const detectClientOS = () => {
    if (typeof navigator === 'undefined') return 'unknown'
    const ua = navigator.userAgent || ''
    if (/Windows NT/i.test(ua)) return 'win'
    if (/Mac OS X|Macintosh/i.test(ua)) return 'darwin'
    if (/Linux/i.test(ua)) return 'linux'
    return 'unknown'
  }

  const localRunOsLabel = (os) => {
    if (os === 'win') return t('chat.localRunOsWin')
    if (os === 'linux') return t('chat.localRunOsLinux')
    if (os === 'darwin') return t('chat.localRunOsDarwin')
    return t('chat.localRunOsUnknown')
  }

  const localRunArtifactUrl = (art) => {
    const path = art?.download_path || ''
    if (!path) return ''
    try {
      if (typeof window === 'undefined') return path
      return new URL(path, window.location.origin).href
    } catch {
      return path
    }
  }

  const localRunWinPowerShellDownload = (art) => {
    const url = localRunArtifactUrl(art)
    const fn = art?.filename || 'badcase-local-proxy.exe'
    if (!url) return ''
    return `Invoke-WebRequest -Uri ${JSON.stringify(url)} -OutFile ${JSON.stringify(fn)}`
  }
  const localRunWinCurlDownload = (art) => {
    const url = localRunArtifactUrl(art)
    const fn = art?.filename || 'badcase-local-proxy.exe'
    if (!url) return ''
    return `curl.exe -fsSL ${JSON.stringify(url)} -o ${JSON.stringify(fn)}`
  }
  const localRunWinRunLine = (art) => {
    const fn = art?.filename || 'badcase-local-proxy.exe'
    return `.\\${fn}`
  }

  const localRunUnixWget = (art) => {
    const url = localRunArtifactUrl(art)
    const fn = art?.filename || 'badcase-local-proxy'
    if (!url) return ''
    return `wget -O ${JSON.stringify(fn)} ${JSON.stringify(url)}`
  }
  const localRunUnixCurl = (art) => {
    const url = localRunArtifactUrl(art)
    const fn = art?.filename || 'badcase-local-proxy'
    if (!url) return ''
    return `curl -fsSL ${JSON.stringify(url)} -o ${JSON.stringify(fn)}`
  }
  const localRunUnixChmodRun = (art) => {
    const fn = art?.filename || 'badcase-local-proxy'
    const q = JSON.stringify(fn)
    const bare = q.slice(1, -1)
    return `chmod +x ${q} && ./${bare}`
  }

  const localRunAbsoluteUrl = (card) => {
    const path = card?.download_path || ''
    if (!path) return ''
    try {
      if (typeof window === 'undefined') return path
      return new URL(path, window.location.origin).href
    } catch {
      return path
    }
  }
  const localRunFilename = (card) => {
    const fn = (card?.filename || 'script.sh').trim()
    return fn || 'script.sh'
  }
  const localRunLegacyWgetLine = (card) => {
    const url = localRunAbsoluteUrl(card)
    const fn = localRunFilename(card)
    if (!url) return ''
    return `wget -O ${JSON.stringify(fn)} ${JSON.stringify(url)}`
  }
  const localRunLegacyCurlLine = (card) => {
    const url = localRunAbsoluteUrl(card)
    const fn = localRunFilename(card)
    if (!url) return ''
    return `curl -fsSL ${JSON.stringify(url)} -o ${JSON.stringify(fn)}`
  }
  const localRunLegacyRunLine = (card) => {
    const fn = localRunFilename(card)
    const q = JSON.stringify(fn)
    const bare = q.slice(1, -1)
    return `chmod +x ${q} && ./${bare}`
  }
  const localRunCopyTip = ref('')
  let localRunCopyTimer = null
  const copyLocalRunLine = async (text) => {
    const line = String(text || '').trim()
    if (!line) return
    try {
      await navigator.clipboard.writeText(line)
      localRunCopyTip.value = t('chat.localRunCopied')
      if (localRunCopyTimer) clearTimeout(localRunCopyTimer)
      localRunCopyTimer = setTimeout(() => {
        localRunCopyTip.value = ''
      }, 2200)
    } catch (e) {
      console.error('[localRun] clipboard', e)
    }
  }

const inputMessage = ref('')
const editingUserMessageId = ref(null)
/** 与 message.id 比较时用字符串，避免历史 id 为 string、本地为 number 时误判为「正在编辑」导致气泡不渲染、点击无门 */
const isUserMessageEditingInline = (msg) => {
  if (editingUserMessageId.value == null || !msg) return false
  return String(editingUserMessageId.value) === String(msg.id)
}

/** 列表项 key：role + id + index（勿在编辑态改 key：整行 remount 易与 Teleport 拆卸顺序冲突 → parentNode null） */
const messageListRowKey = (m, idx) => {
  const role = m?.isUser ? 'u' : 'a'
  const id = m?.id != null ? String(m.id) : 'na'
  return `${role}-${id}-${idx}`
}

const inlineInputMessage = ref('')
const inlineTextareaRef = ref(null)
/** v-for 内 ref 可能为数组；需在调用处取真实 DOM */
const unwrapTextareaEl = (raw) => {
  if (raw == null) return null
  if (Array.isArray(raw)) {
    const el = raw.find((x) => x && x.nodeType === 1)
    return el || null
  }
  return raw && raw.nodeType === 1 ? raw : null
}
const imageFileInputRef = ref(null)
const inlineImageFileInputRef = ref(null)
const pendingImages = ref([])
/** 点击用户气泡进入的内联编辑：待发送图片，与底部主输入 pendingImages 分离 */
const inlinePendingImages = ref([])
const isDragOver = ref(false)
const isInlineDragOver = ref(false)
const imagePreviewSrc = ref(null)
const imagePreviewFilename = ref('image.png')
const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']
const MAX_IMAGE_SIZE = 4 * 1024 * 1024
const MAX_IMAGES = 5

/** 选文件 / 拖拽用白名单；剪贴板截图常见无 type，仅在有扩展名或来自 paste 路径里单独放宽 */
const isAllowedImageMime = (mime) => {
  const t = (mime || '').trim().toLowerCase()
  if (!t) return false
  if (ACCEPTED_IMAGE_TYPES.includes(t)) return true
  return t.startsWith('image/')
}

const triggerImageSelect = () => {
  imageFileInputRef.value?.click?.()
}

const handleImageSelect = (e) => {
  const files = e.target?.files
  if (!files?.length) return
  addImageFiles(Array.from(files))
  e.target.value = ''
}

const handleImageDrop = (e) => {
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (!files?.length) return
  addImageFiles(Array.from(files), pendingImages)
}

const handleInlineImageDrop = (e) => {
  isInlineDragOver.value = false
  const files = e.dataTransfer?.files
  if (!files?.length) return
  addImageFiles(Array.from(files), inlinePendingImages)
}

const addImageFiles = async (files, targetRef = pendingImages, { allowEmptyMime = false } = {}) => {
  for (const file of files) {
    if (targetRef.value.length >= MAX_IMAGES) break
    const t = (file.type || '').trim().toLowerCase()
    const mimeOk = isAllowedImageMime(file.type) || (allowEmptyMime && !t)
    if (!mimeOk) continue
    if (file.size > MAX_IMAGE_SIZE) continue
    try {
      const data = await fileToBase64(file)
      targetRef.value.push({ data, filename: file.name })
    } catch (err) {
      console.warn('图片读取失败:', err)
    }
  }
}

const fileToBase64 = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

const removePendingImage = (idx, targetRef = pendingImages) => {
  targetRef.value = targetRef.value.filter((_, i) => i !== idx)
}

const triggerInlineImageSelect = () => {
  inlineImageFileInputRef.value?.click?.()
}

const handleInlineImageSelect = (e) => {
  const files = e.target?.files
  if (!files?.length) return
  addImageFiles(Array.from(files), inlinePendingImages)
  e.target.value = ''
}

/** 从剪贴板追加图片到指定待发送列表（仅处理图片文件，不挡纯文本粘贴） */
const handleComposerPaste = (e, targetRef) => {
  if (!targetRef) return
  const files = []
  const items = e.clipboardData?.items
  if (items?.length) {
    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      if (it.kind !== 'file') continue
      const f = it.getAsFile()
      if (f && (isAllowedImageMime(f.type) || !(f.type || '').trim())) files.push(f)
    }
  }
  // Electron / 部分环境下截图只在 files 里暴露，items 无 file 项
  const dtFiles = e.clipboardData?.files
  if (dtFiles?.length && !files.length) {
    for (let i = 0; i < dtFiles.length; i++) {
      const f = dtFiles[i]
      if (f && (isAllowedImageMime(f.type) || !(f.type || '').trim())) files.push(f)
    }
  }
  if (!files.length) return
  e.preventDefault()
  void addImageFiles(files, targetRef, { allowEmptyMime: true })
}

/** 模板里 ref 会被自动解包，内联箭头若直接传 pendingImages 会变成裸数组，导致 .value 失效 */
const onPasteMainComposer = (e) => handleComposerPaste(e, pendingImages)
const onPasteInlineComposer = (e) => handleComposerPaste(e, inlinePendingImages)
const removePendingInline = (idx) => removePendingImage(idx, inlinePendingImages)

const guessFilenameFromDataUrl = (src) => {
  const s = String(src || '')
  const m = s.match(/^data:image\/([\w+.-]+);/i)
  if (!m) return 'image.png'
  const ext = m[1].toLowerCase().replace('jpeg', 'jpg').replace('svg+xml', 'svg')
  return `image.${ext}`
}

const dataUrlToBlob = async (dataUrl) => {
  const res = await fetch(dataUrl)
  return res.blob()
}

const openImagePreview = (src, filename) => {
  if (!src) return
  imagePreviewSrc.value = src
  const fn = filename != null && String(filename).trim() !== '' ? String(filename).trim() : ''
  imagePreviewFilename.value = fn || guessFilenameFromDataUrl(src)
}

const closeImagePreview = () => {
  imagePreviewSrc.value = null
  imagePreviewFilename.value = 'image.png'
}

const copyPreviewImage = async () => {
  const src = imagePreviewSrc.value
  if (!src) return
  try {
    const blob = await dataUrlToBlob(src)
    const type = blob.type && blob.type.startsWith('image/') ? blob.type : 'image/png'
    if (navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
      await navigator.clipboard.write([new ClipboardItem({ [type]: blob })])
      return
    }
    throw new Error('clipboard unsupported')
  } catch (err) {
    console.warn('[CHAT] 复制图片失败:', err)
  }
}

const downloadPreviewImage = () => {
  const src = imagePreviewSrc.value
  if (!src) return
  try {
    const a = document.createElement('a')
    a.href = src
    a.download = imagePreviewFilename.value || 'image.png'
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch (err) {
    console.warn('[CHAT] 下载图片失败:', err)
  }
}

const clearPendingImages = () => {
  pendingImages.value = []
}

const handleDocumentPointerDown = (e) => {
  // 处于内联编辑态时：点到编辑区外面 -> 自动退出恢复原文
  if (!editingUserMessageId.value) return
  const target = e?.target
  if (!target) return
  // 点击在内联编辑器内部则不处理
  if (target.closest && target.closest('.inline-composer')) return
  if (target.closest && target.closest('.image-preview-overlay')) return
  if (target.closest && target.closest('.pending-thumb')) return
  // 点到另一条用户气泡时不要在这里 cancel：同步卸载/重排会导致随后的 click 丢失，表现为“点了没反应”
  if (target.closest && target.closest('.user-message-bubble')) return
  cancelEditUserMessage()
}
const selectedAgent = ref('agent')

/** 下拉选项：默认内置列表，onMounted 时由 GET /api/models 覆盖 */
const FALLBACK_CHAT_MODEL_OPTIONS = [
  { id: 'auto', label: 'Auto' },
  { id: 'qwen3.5-plus', label: 'Qwen-3.5-Plus' },
  { id: 'qwen3.6-flash', label: 'Qwen-3.6-Flash' },
  { id: 'qwen3.6-plus', label: 'Qwen-3.6-Plus' },
  { id: 'qwen-max-thinking', label: 'Qwen-Max' },
  { id: 'deepseek-v4-pro', label: 'DeepSeek-V4-Pro' },
  { id: 'deepseek-v4-flash', label: 'DeepSeek-V4-Flash' },
  { id: 'glm-5', label: 'GLM-5' },
]
const chatModelOptions = ref([...FALLBACK_CHAT_MODEL_OPTIONS])
const chatModelIds = computed(() => new Set(chatModelOptions.value.map((o) => o.id)))

function normalizeSavedChatModel(saved) {
  const s = (saved || '').trim()
  if (chatModelIds.value.has(s)) return s
  return 'auto'
}

async function loadChatModelsFromApi() {
  try {
    const resp = await fetch(`${BACKEND_BASE_URL}/api/models`, { credentials: 'include' })
    if (!resp.ok) return
    const data = await resp.json()
    const models = data?.models
    if (!data?.success || !Array.isArray(models) || !models.length) return
    const opts = [{ id: 'auto', label: 'Auto' }]
    for (const m of models) {
      const id = (m?.id || '').trim()
      if (!id) continue
      opts.push({ id, label: (m?.label || id).trim() || id })
    }
    chatModelOptions.value = opts
    const normalized = normalizeSavedChatModel(selectedModel.value)
    if (normalized !== selectedModel.value) {
      selectedModel.value = normalized
      localStorage.setItem('selectedChatModel', normalized)
    }
    inlineEditSelectedModel.value = normalizeSavedChatModel(inlineEditSelectedModel.value)
  } catch (e) {
    console.warn('[MODEL] GET /api/models failed, using fallback list', e)
  }
}

/** 历史用户消息无 llm_model 时，用紧随其后的助手消息的模型推断（与落库顺序一致） */
function inferUserLlmModelFromFollowingAssistant(msgs, userIdx) {
  if (!Array.isArray(msgs) || userIdx < 0) return null
  for (let j = userIdx + 1; j < msgs.length; j++) {
    const m = msgs[j]
    if (!m || m.isUser) continue
    const mid = m.llmModel ?? m.llm_model
    if (mid != null && String(mid).trim()) return normalizeSavedChatModel(String(mid))
    break
  }
  return null
}

// 从 localStorage 读取上次选择的模型；旧版文心/GLM-Flash 等已不在注册表，回退为 Auto
const savedModel = localStorage.getItem('selectedChatModel')
const selectedModel = ref(normalizeSavedChatModel(savedModel))
/** 内联编辑历史用户消息时的模型（与底部主输入 selectedModel 分离，勿改 localStorage） */
const inlineEditSelectedModel = ref(normalizeSavedChatModel(savedModel))
const inlineModelIsAuto = computed(() => inlineEditSelectedModel.value === 'auto')
const inlineModelIsQwen = computed(
  () => inlineEditSelectedModel.value && inlineEditSelectedModel.value.startsWith('qwen')
)
const inlineModelIsGlm = computed(
  () => inlineEditSelectedModel.value && inlineEditSelectedModel.value.startsWith('glm')
)
const inlineModelIsDeepSeek = computed(
  () => inlineEditSelectedModel.value && inlineEditSelectedModel.value.startsWith('deepseek')
)
if (savedModel != null && normalizeSavedChatModel(savedModel) !== savedModel) {
  localStorage.setItem('selectedChatModel', selectedModel.value)
}
const isAutoModel = computed(() => selectedModel.value === 'auto')
const isQwenModel = computed(() => selectedModel.value && selectedModel.value.startsWith('qwen'))
const isGlmModel = computed(() => selectedModel.value && selectedModel.value.startsWith('glm'))
const isDeepSeekModel = computed(() => selectedModel.value && selectedModel.value.startsWith('deepseek'))
const messagesContainer = ref(null)
const textareaRef = ref(null)
const isSending = ref(false)
const isComposing = ref(false)  // 输入法组合状态
const abortController = ref(null)  // 用于终止请求
/** 当前 ReAct/聊天 SSE 的 body reader；与 AbortController 配合，避免仅 abort 时 read 仍挂起（Electron 长连接） */
const reactSseReaderRef = ref(null)
/** 与 SSE 信封 request_id 一致，停止时 POST /api/agent/react/cancel 让后端主循环合作退出 */
const reactStreamRequestIdRef = ref(null)
/** 刷新后续流：轮询 /api/agent/react/buffer（仅断线/F5；在线 SSE 不走 buffer） */
const REACT_RESUME_POLL_MS = 1200
/** 在线 SSE：仅记 lastSeq，避免每条 chunk 全量 JSON 快照拖慢主线程 */
const REACT_STREAM_PATCH_SEQ_MS = 2500
/** F5 续流 UI 壳：与 lastSeq 分键 + 降频（buffer 仍是主真相） */
const REACT_AGENT_RUN_SNAPSHOT_MS = 10000
/** 在线 SSE：stream 增量合并刷新上限（ms），约 30fps；工具/phase 仍立即 flush */
const REACT_SSE_PAINT_MIN_MS = 32
const reactResumePollTimerRef = ref(null)
const reactResumeInFlightRef = ref(false)
let draftSaveTimer = null
const currentProjectId = ref(null)
// 沙箱预览展开状态：key = `${messageId}-${groupIdx}` 或 `${messageId}-single`；>3 项默认收起，悬停显示上/下箭头
const sandboxExpanded = ref({})
const getSandboxKey = (messageId, groupIdx) => (groupIdx == null ? `${messageId}-single` : `${messageId}-${groupIdx}`)
/** 新建/修改沙箱预览 diff 行数超过该值时默认收起（与深度思考区 reasoning-toggle 交互一致） */
const SANDBOX_PREVIEW_COLLAPSE_OVER = 3

const findChatMessageById = (messageId) => {
  const idStr = String(messageId)
  return messages.value.find((m) => m && String(m.id) === idStr) ?? null
}

/** 模板传入 message 对象或 id；避免 Teleport/响应式下仅 id 查找不到导致始终「展开」 */
const resolveSandboxExpandMessage = (messageOrId) => {
  if (messageOrId != null && typeof messageOrId === 'object' && 'id' in messageOrId) {
    return messageOrId
  }
  return findChatMessageById(messageOrId)
}

const sandboxExpandMessageId = (messageOrId) => {
  const msg = resolveSandboxExpandMessage(messageOrId)
  return msg?.id ?? messageOrId
}

const getSandboxPreviewRowCount = (message, groupIdx) => {
  if (!message) return 0
  if (groupIdx != null) {
    const group = message.modifyGroups?.[groupIdx]
    return countGroupSandboxDisplayRows(group)
  }
  return getSandboxDiffRows(message).length
}

const sandboxPreviewNeedsCollapse = (message, groupIdx) =>
  getSandboxPreviewRowCount(message, groupIdx) > SANDBOX_PREVIEW_COLLAPSE_OVER

const shouldDefaultCollapseSandboxPreview = (message, groupIdx) =>
  sandboxPreviewNeedsCollapse(message, groupIdx)

const isSandboxExpanded = (messageOrId, groupIdx) => {
  const msg = resolveSandboxExpandMessage(messageOrId)
  const messageId = sandboxExpandMessageId(messageOrId)
  const key = getSandboxKey(messageId, groupIdx)
  const explicit = sandboxExpanded.value[key]
  if (explicit === true) return true
  if (explicit === false) return false
  return !shouldDefaultCollapseSandboxPreview(msg, groupIdx)
}

const toggleSandboxExpand = (messageOrId, groupIdx) => {
  const messageId = sandboxExpandMessageId(messageOrId)
  const key = getSandboxKey(messageId, groupIdx)
  sandboxExpanded.value = {
    ...sandboxExpanded.value,
    [key]: !isSandboxExpanded(messageOrId, groupIdx)
  }
}

const isSandboxPreviewCollapsed = (messageOrId, groupIdx) =>
  sandboxPreviewNeedsCollapse(resolveSandboxExpandMessage(messageOrId), groupIdx) &&
  !isSandboxExpanded(messageOrId, groupIdx)

/** 收起时仍展示前 N 项（与 Cursor 一致），而非整块隐藏 */
const visibleSandboxPreviewRows = (messageOrId, groupIdx, sourceRows = null) => {
  const msg = resolveSandboxExpandMessage(messageOrId)
  if (!msg) return sourceRows || []
  const rows = sourceRows ?? getSandboxDiffRows(msg)
  if (!sandboxPreviewNeedsCollapse(msg, groupIdx)) return rows
  if (isSandboxExpanded(msg, groupIdx)) return rows
  return rows.slice(0, SANDBOX_PREVIEW_COLLAPSE_OVER)
}

const flattenGroupSandboxEntries = (message, groupIdx) => {
  const group = message?.modifyGroups?.[groupIdx]
  if (!group?.items?.length) return []
  const out = []
  const multi = group.items.length > 1
  for (let gix = 0; gix < group.items.length; gix++) {
    const git = group.items[gix]
    if (!isSandboxModifyItemPending(git, message)) continue
    const diffs = resolveSandboxDiffRowsForDisplay(git, group.target)
    for (let rowIdx = 0; rowIdx < diffs.length; rowIdx++) {
      out.push({
        git,
        gix,
        rowIdx,
        fieldDiff: diffs[rowIdx],
        showRecordHeader: multi && (out.length === 0 || out[out.length - 1].gix !== gix)
      })
    }
  }
  return out
}

const visibleGroupSandboxEntries = (messageOrId, groupIdx) => {
  const msg = resolveSandboxExpandMessage(messageOrId)
  if (!msg) return []
  const flat = flattenGroupSandboxEntries(msg, groupIdx)
  if (!sandboxPreviewNeedsCollapse(msg, groupIdx)) return flat
  if (isSandboxExpanded(msg, groupIdx)) return flat
  return flat.slice(0, SANDBOX_PREVIEW_COLLAPSE_OVER)
}

const flattenBatchSandboxEntries = (message) => {
  const nav = message?.modifyNavigation
  if (!nav?.batch_modify || !Array.isArray(nav.batch_results) || !nav.batch_results.length) {
    return []
  }
  const out = []
  const multi = nav.batch_results.length > 1
  for (let bix = 0; bix < nav.batch_results.length; bix++) {
    const br = nav.batch_results[bix]
    if (!isSandboxModifyItemPending(br, message)) continue
    const diffs = getBatchItemSandboxDiffRows(br, nav.target)
    for (let rowIdx = 0; rowIdx < diffs.length; rowIdx++) {
      out.push({
        br,
        bix,
        rowIdx,
        fieldDiff: diffs[rowIdx],
        showRecordHeader: multi && (out.length === 0 || out[out.length - 1].bix !== bix)
      })
    }
  }
  return out
}

const visibleBatchSandboxEntries = (messageOrId) => {
  const msg = resolveSandboxExpandMessage(messageOrId)
  if (!msg) return []
  const flat = flattenBatchSandboxEntries(msg)
  if (!sandboxPreviewNeedsCollapse(msg, null)) return flat
  if (isSandboxExpanded(msg, null)) return flat
  return flat.slice(0, SANDBOX_PREVIEW_COLLAPSE_OVER)
}

/** 最后一个含 modify/create 的工具步骤下标（与 AgentTaskRun.execToolKind 一致） */
const lastSandboxToolStepIndex = (steps) => {
  if (!Array.isArray(steps)) return -1
  let last = -1
  for (let i = 0; i < steps.length; i++) {
    const title = String(steps[i]?.title || '').toLowerCase()
    if (title.includes('modify') || title.includes('create')) last = i
  }
  return last
}

/**
 * 已 prune 的 steps 上计算沙箱嵌入下标（与 AgentTaskRun 共用同一数组，避免模板重复剪枝）。
 */
const sandboxEmbedAfterModifyStepIndexFromSteps = (message, steps) => {
  if (!message || message.isUser) return -1
  if (message._placeholderSteps) return -1
  const hasSandboxUi =
    (message.modifyGroups && message.modifyGroups.length > 0) || !!message.modifyNavigation
  if (!hasSandboxUi) return -1
  if (!Array.isArray(steps) || steps.length < 2) return -1
  const lastTool = lastSandboxToolStepIndex(steps)
  if (lastTool < 0 || lastTool >= steps.length - 1) return -1
  return lastTool
}

/** 剪枝步骤 + 嵌入下标（同一 tick 内可能对同一 message 读多次） */
const getAgentTaskRunViewForAi = (message) => {
  const steps = pruneTrailingPhantomAgentSteps(message?.steps || [])
  return {
    showSteps: steps.length > 0 && !message._placeholderSteps,
    steps,
    embedIdx: sandboxEmbedAfterModifyStepIndexFromSteps(message, steps)
  }
}

/**
 * 沙箱 Teleport 固定落到 below 锚点：embed 在 AgentTaskRun 子树内，与 Teleport 同条消息一起拆时易出现
 *「目标先被卸掉、Teleport 子节点再 remove」→ parentNode === null。below 与本组件内 Teleport 兄弟、先于内容挂载，更稳。
 */
const sandboxModifyTeleportTargetForMessage = (message) => {
  const idPart = message?.id != null ? String(message.id) : 'na'
  return `#sandbox-mod-below-${idPart}`
}

/** 检查 Teleport 目标锚点是否已挂载（与 #sandbox-mod-below-{id} 同条消息内联） */
const sandboxTeleportTargetExists = (message) => {
  if (message?.id == null || message?.id === undefined) return false
  try {
    return !!document.getElementById(`sandbox-mod-below-${String(message.id)}`)
  } catch {
    return false
  }
}

// 将运行中状态收敛（停止/异常时用）
const finalizeRunningMessage = (aiMessage, reason = 'stopped') => {
  if (!aiMessage) return

  if (Array.isArray(aiMessage.steps)) {
    aiMessage.steps.forEach(step => {
      if (step?.status === 'running') {
        step.status = 'skipped'
        step.description = reason === 'stopped' ? '已停止' : '已中断'
        if (step.toolCall && step.toolCall.output === '执行中...') {
          step.toolCall.output = reason === 'stopped' ? '已停止' : '已中断'
        }
      }
      // AgentTaskRun phaseWait.active 时仍显示三点动画；停止后必须清掉
      if (step?.phaseWait) step.phaseWait = null
    })
  }

  if (!aiMessage.agentResult || typeof aiMessage.agentResult !== 'object') {
    aiMessage.agentResult = { findings: [], recommendations: [] }
  }
  aiMessage.agentResult.status = reason === 'stopped' ? 'cancelled' : 'failed'

  // 顶部提示同步更新，避免还停留在“修改中/执行中”
  if (typeof aiMessage.understanding === 'string') {
    aiMessage.understanding = reason === 'stopped' ? '⏹️ 已停止生成' : '⚠️ 已中断'
  }

  if (!aiMessage.finalResponse) {
    aiMessage.finalResponse = reason === 'stopped' ? '已停止生成' : '已中断'
  }

  cancelTodosStreamTypewriter(aiMessage)
  aiMessage.todosStreamVisible = ''
  flushReasoningTypewriter(aiMessage)
}

// 格式化消息内容（支持简单的markdown）
const formatMessage = (content) => {
  return content
    .replace(/\n/g, '<br>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

// 零宽字符（历史后端占位等）：不计入「是否有可见正文」判断
const INVISIBLE_REASONING_CHARS = /[\u200B-\u200D\uFEFF\u2060]/g

/**
 * reasoning 轨常见「三连以上换行」或通道残留；pre-wrap 会撑出大块空白（DeepSeek-V4-Flash 等尤甚）。
 * 与 AgentTaskRun.collapseThoughtDisplayNewlines / stripReasoningChannelArtifacts 对齐。
 */
const squeezeReasoningVerticalWhitespace = (raw) => {
  let t = stripReasoningChannelArtifacts(
    String(raw || '')
      .replace(/\r\n/g, '\n')
      .replace(INVISIBLE_REASONING_CHARS, '')
  )
  for (let i = 0; i < 12; i++) {
    const n = t.replace(/\n{3,}/g, '\n\n')
    if (n === t) break
    t = n
  }
  return t.trim()
}
/** 首轮 Agent 思考区是否展示：是否有实质可见文本（reasoningContent 为历史字段名，实为 THINK 阶段草稿缓冲） */
const substantiveReasoning = (text) => {
  if (text == null || typeof text !== 'string') return false
  return text.replace(INVISIBLE_REASONING_CHARS, '').trim().length > 0
}

/** ReAct「思考」阶段：reasoning 和 content 轨（与 SSE stream_channel 对齐）或旧版单缓冲 */
const substantiveThinkPhase = (m) => {
  if (!m) return false
  const r = String(m.thinkReasoningDraft || '').replace(INVISIBLE_REASONING_CHARS, '').trim()
  const c = String(m.thinkContentDraft || '').replace(INVISIBLE_REASONING_CHARS, '').trim()
  if (r.length > 0 || c.length > 0) return true
  return substantiveReasoning(m.reasoningContent)
}

/** 首轮 Thought Markdown 区：至少 2 个可见字符再渲染，避免流式首包只来一个括号标点显得像坏 UI */
const reasoningMarkdownStreamVisible = (m) => {
  if (!m) return false
  const t = String(m.reasoningContent || '').replace(INVISIBLE_REASONING_CHARS, '').trim()
  return t.length >= 2
}

const _thinkDraftStrip = (s) => String(s || '').replace(INVISIBLE_REASONING_CHARS, '').trim()
const _thinkDraftMeaningful = (s) => {
  const t = _thinkDraftStrip(s)
  return t.length >= 1 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(t)
}
/** 流式 live：1 个有效字即可上屏；与 AgentTaskRun plain 流一致，避免等满 2 字 */
const thinkDraftReasoningVisible = (m) => {
  const t = _thinkDraftStrip(m?.thinkReasoningDraft)
  if (m?._reasoningPhaseLive && t.length >= 1) return _thinkDraftMeaningful(m?.thinkReasoningDraft)
  return t.length >= 2
}
const thinkDraftContentVisible = (m) => {
  const t = _thinkDraftStrip(m?.thinkContentDraft)
  if (m?._reasoningPhaseLive && t.length >= 1) return _thinkDraftMeaningful(m?.thinkContentDraft)
  return t.length >= 2
}

/** SSE 上的 react_phase 是否为统一流 Thought 轨（含子过程 observe / decide）；未带字段时按旧协议视为 think */
const sseIsReactThinkPhase = (reactPhase) =>
  reactPhase == null ||
  reactPhase === '' ||
  reactPhase === 'think' ||
  reactPhase === 'observe' ||
  reactPhase === 'decide'

/**
 * 是否展示消息顶部「首轮 Thought」区（think 阶段、待办步骤出现前）
 * 与后端两段式一致：先流式「文字说明」（reasoning / reasoning 轨），再流式待办 XML（todos_stream）
 * 合并进同一块的 content 轨或 reasoningContent，见 _thinkTodoMergedIntoReasoning
 * 设为 false 则仅不渲染本 DOM，SSE 仍写入
 */
const SHOW_FIRST_ROUND_THOUGHT_UI = true

/**
 * 首轮「think」区是否渲染：有可见正文，且内容来自 ReAct react_phase=think（由 hadAgentThinkPhase 标记）
 * lastReactPhase 会随后续 SSE 变为 act/observe_decide，不能单靠它判断本块是否该出现
 */
const showFirstThinkBlock = (m) => {
  if (!SHOW_FIRST_ROUND_THOUGHT_UI) return false
  if (!m || m.reactDirectChatReply) return false
  if (!substantiveThinkPhase(m)) return false
  return !!m.hadAgentThinkPhase
}

/** 排查：step.reasoning / step.todos_stream 与草稿、hadAgentThinkPhase、首轮 Thought 可见性 */
function logReactThinkStepDetail(stepEvent, aiMessage) {
  if (!isDebugReactThinkSSE || !stepEvent || !aiMessage) return
  if (stepEvent.event !== 'reasoning' && stepEvent.event !== 'todos_stream') return
  const kind = stepEvent.event
  const len =
    kind === 'reasoning'
      ? String(stepEvent.content ?? stepEvent.data ?? '').length
      : String(stepEvent.delta ?? '').length
  const tr = String(aiMessage.thinkReasoningDraft || '').length
  const tc = String(aiMessage.thinkContentDraft || '').length
  const rc = String(aiMessage.reasoningContent || '').length
  console.log('[REACT-THINK-SSE] step', {
    event: kind,
    react_phase: stepEvent.react_phase,
    stream_channel: stepEvent.stream_channel,
    pieceLen: len,
    draftLens: { thinkReasoning: tr, thinkContent: tc, reasoningContent: rc },
    hadAgentThinkPhase: !!aiMessage.hadAgentThinkPhase,
    _reasoningPhaseLive: !!aiMessage._reasoningPhaseLive,
    substantiveThinkPhase: substantiveThinkPhase(aiMessage),
    showFirstThinkBlock: showFirstThinkBlock(aiMessage),
    hint:
      kind === 'todos_stream'
        ? '默认 REACT_THINK_CONTENT_ONLY=1 时主文来自 content_delta→todos_stream；无 reasoning_delta 则仅有本事件'
        : 'reasoning_delta→step.reasoning；与 todos_stream 同属 think 阶段 Thought '
  })
}

// 思考过程：使用 marked 做完整 Markdown 渲染（换行、加粗、列表、代码块等）
marked.setOptions({ gfm: true, breaks: true })
const formatReasoningMarkdown = (content) => {
  if (!content || typeof content !== 'string') return ''
  try {
    let text = squeezeReasoningVerticalWhitespace(content)
    // 若模型未输出换行，在中文句号/分号后插入换行，便于展示段落
    if (!/\n/.test(text) && /[。；]/.test(text)) {
      text = text.replace(/([。；])/g, '$1\n')
    }
    return marked.parse(text, { gfm: true, breaks: true })
  } catch (e) {
    return content.replace(/\n/g, '<br>')
  }
}

// 获取工具层级
const getToolLevel = (toolName) => {
  if (!toolName) return 'level-unknown'
  const name = toolName.toLowerCase()
  if (name.startsWith('l1_') || name.includes('click') || name.includes('input') || name.includes('wait') || name.includes('assert')) {
    return 'level-l1'
  } else if (name.startsWith('l2_') || name.includes('form_') || name.includes('fill') || name.includes('submit')) {
    return 'level-l2'
  } else if (name.startsWith('l3_') || name.includes('complete_') || name.includes('test_')) {
    return 'level-l3'
  }
  return 'level-unknown'
}

// 获取工具图标
const getToolIcon = (toolName) => {
  if (!toolName) return '🔧'
  const name = toolName.toLowerCase()
  if (name.includes('click')) return '🖱️'
  if (name.includes('input') || name.includes('text')) return '⌨️'
  if (name.includes('wait')) return '⏳'
  if (name.includes('assert') || name.includes('check')) return '✅'
  if (name.includes('form')) return '📋'
  if (name.includes('submit')) return '📤'
  if (name.includes('login') || name.includes('complete')) return '🔑'
  if (name.includes('test') || name.includes('scenario')) return '🧪'
  return '🔧'
}

// 获取工具层级标签
const getToolLevelLabel = (toolName) => {
  const level = getToolLevel(toolName)
  if (level === 'level-l1') return '(L1 原子)'
  if (level === 'level-l2') return '(L2 复合)'
  if (level === 'level-l3') return '(L3 流程)'
  return ''
}

/** 将后端 Todo 字符串列表转为 ReAct 步骤（与流式 todos / todos_partial 共用）*/
const buildReactStepsFromTodoStrings = (todoData) => {
  return (todoData || []).map((todo, idx) => {
    const todoText = typeof todo === 'string' ? todo : (todo.title || todo.text || todo.content || `任务${idx + 1}`)
    let friendlyTitle = todoText
    const toolMatch = todoText.match(/使用\s*(\w+)\s*工具/)
    if (toolMatch) {
      friendlyTitle = toolMatch[1]
    } else if (todoText.includes('database_query') || todoText.includes('查询')) {
      friendlyTitle = 'database_query'
    } else if (todoText.includes('grep') || todoText.includes('定位')) {
      friendlyTitle = 'grep'
    } else if (todoText.includes('modify') || todoText.includes('修改')) {
      friendlyTitle = 'modify'
    } else if (todoText.includes('create') || todoText.includes('创建')) {
      friendlyTitle = 'create'
    } else if (todoText.includes('browser_test') || todoText.includes('测试')) {
      friendlyTitle = 'browser_test'
    } else if (todoText.includes('search') || todoText.includes('搜索')) {
      friendlyTitle = 'search'
    }
    return {
      title: friendlyTitle,
      originalTodo: todoText,
      status: 'pending',
      description: '',
      progressLog: [],
      detailLog: [],
      inputParams: null,
      stepStartedAt: null,
      stepDurationMs: null,
      resultSummary: '',
      llmDraft: '', // 决策/观察：用户可读流式说明（react_ui_stream decision_observe）
      paramsSummaryDraft: '', // 入参说明（react_ui_stream params）
      reasoningStepDraft: '', // 无 segment 时的 reasoning_step 兜底
      reasoningDecideDraft: '', // 兼容旧逻辑；汇总见 thoughtReasoningDraft
      /** ReAct Thought：深度思考 reasoning（浅显 content（亮），与 API reasoning_delta / content_delta 对齐 */
      thoughtReasoningDraft: '',
      thoughtContentDraft: '',
      /** Agent 行动前自然语言（非模型 reasoning 参数）*/
      agentThoughtDraft: '',
      thoughtTiming: null, // { durationMs, kind, segment, briefThresholdMs } Cursor 式耗时
      /** 首次收到本步 executing 时的 Date.now()：用于 Thought 墙钟勿把 grep/modify 整段算进「思考」*/
      thoughtPhaseEndAtMs: null,
      toolExecStartedAt: null,
      /** 后端 grep_perf_ms / 墙钟 tool 段，用于工具行秒数（勿用整步 stepDurationMs） */
      toolExecDurationMs: null,
      /** phase_wait SSE：接收 decision_xml / result_xml 等等待中 */
      phaseWait: null
    }
  })
}

/** 取消首轮 Todo 正文的逐字追赶动画 */
const cancelTodosStreamTypewriter = (msg) => {
  if (!msg) return
  const id = msg._todosTypewriterRaf
  if (id != null) {
    cancelAnimationFrame(id)
    msg._todosTypewriterRaf = null
  }
}

/**
 * 将 todosStreamDraft 以逐字方式写入 todosStreamVisible（rAF 追赶，chunk 再大也像打字机）
 */
const scheduleTodosStreamTypewriter = (msg) => {
  if (!msg) return
  const loop = () => {
    msg._todosTypewriterRaf = null
    const draft = msg.todosStreamDraft || ''
    const vis = msg.todosStreamVisible || ''
    if (!draft) {
      msg.todosStreamVisible = ''
      return
    }
    if (vis.length >= draft.length) return
    const backlog = draft.length - vis.length
    const n = Math.min(backlog, Math.max(1, Math.ceil(backlog / 6)))
    msg.todosStreamVisible = draft.slice(0, vis.length + n)
    if ((msg.todosStreamVisible || '').length < draft.length) {
      msg._todosTypewriterRaf = requestAnimationFrame(loop)
    }
  }
  if (msg._todosTypewriterRaf != null) return
  msg._todosTypewriterRaf = requestAnimationFrame(loop)
}

/**
 * 思考区不再内嵌滚动：内容从顶部向下增高，贴对话区底部时由外部 messages-container 滚动
 * 观感为整段对话向上「冒泡」，且思考面板本身不出现滚动条
 */
let _reasoningChatScrollRaf = null
const scrollChatDuringReasoningStream = () => {
  if (_reasoningChatScrollRaf != null) return
  _reasoningChatScrollRaf = requestAnimationFrame(() => {
    _reasoningChatScrollRaf = null
    nextTick(() => {
      const el = messagesContainer.value
      if (el) el.scrollTop = el.scrollHeight
    })
  })
}

const cancelReasoningTypewriter = (msg) => {
  if (!msg) return
  const id = msg._reasoningTypewriterRaf
  if (id != null) {
    cancelAnimationFrame(id)
    msg._reasoningTypewriterRaf = null
  }
}

/** 思考流结束：一次性对齐到全文，关闭「流式纯文本」阶段后再走 Markdown */
const flushReasoningTypewriter = (msg) => {
  if (!msg) return
  cancelReasoningTypewriter(msg)
  msg.reasoningDisplayContent = msg.reasoningContent || ''
  msg.reasoningStreamActive = false
  msg._reasoningPhaseLive = false
  scrollChatDuringReasoningStream()
}

/**
 * 深度思考：reasoningContent 为后端原文；历史回放可打字机追赶
 * SSE live（_reasoningPhaseLive）时也必须逐帧追赶展示：若把 reasoningDisplayContent 一次性对齐全文，
 * 同一事件循环内多条 SSE 会先合并进 reasoningContent，再只触发一次本函数，导致观察段等出现「整段一次性出现」。
 *
 * 优化：当 token 到达太快时（积压大且间隔短），走 _runFastTypewriter 微延迟追赶。
 */
const scheduleReasoningTypewriter = (msg) => {
  if (!msg) return
  if (msg.isHistorical) {
    msg.reasoningDisplayContent = msg.reasoningContent || ''
    return
  }
  if (msg._reasoningPhaseLive) {
    cancelReasoningTypewriter(msg)
    const full = msg.reasoningContent || ''
    const vis = msg.reasoningDisplayContent || ''
    const backlog = full.length - vis.length
    const now = Date.now()
    if (!msg._typewriterLastUpdate) msg._typewriterLastUpdate = now
    const timeSinceLastUpdate = now - msg._typewriterLastUpdate

    if (backlog > 50 && timeSinceLastUpdate < 50 && !msg._typewriterFastMode) {
      msg._typewriterFastMode = true
      msg._typewriterTargetContent = full
      msg.reasoningStreamActive = true
      _runFastTypewriter(msg)
      return
    }

    msg._typewriterLastUpdate = now
    msg.reasoningStreamActive = true
    scrollChatDuringReasoningStream()

    const loopLive = () => {
      msg._reasoningTypewriterRaf = null
      const f = msg.reasoningContent || ''
      let v = msg.reasoningDisplayContent || ''
      if (v.length > f.length) {
        msg.reasoningDisplayContent = f
        v = f
      }
      if (v.length >= f.length) {
        scrollChatDuringReasoningStream()
        return
      }
      const b = f.length - v.length
      const n = Math.min(b, Math.max(1, Math.ceil(b / 14)))
      msg.reasoningDisplayContent = f.slice(0, v.length + n)
      scrollChatDuringReasoningStream()
      if ((msg.reasoningDisplayContent || '').length < (msg.reasoningContent || '').length) {
        msg._reasoningTypewriterRaf = requestAnimationFrame(loopLive)
      }
    }
    if (!msg._typewriterFastMode && backlog > 0 && msg._reasoningTypewriterRaf == null) {
      msg._reasoningTypewriterRaf = requestAnimationFrame(loopLive)
    }
    return
  }
  msg.reasoningStreamActive = true
  const loop = () => {
    msg._reasoningTypewriterRaf = null
    const full = msg.reasoningContent || ''
    let vis = msg.reasoningDisplayContent || ''
    if (vis.length > full.length) {
      msg.reasoningDisplayContent = full
      vis = full
    }
    if (vis.length >= full.length) {
      scrollChatDuringReasoningStream()
      msg.reasoningStreamActive = false
      return
    }
    const backlog = full.length - vis.length
    // 更小步进 + rAF：减少单帧布局变化，观感更接近匀速打字
    const n = Math.min(backlog, Math.max(1, Math.ceil(backlog / 14)))
    msg.reasoningDisplayContent = full.slice(0, vis.length + n)
    scrollChatDuringReasoningStream()
    if ((msg.reasoningDisplayContent || '').length < full.length) {
      msg._reasoningTypewriterRaf = requestAnimationFrame(loop)
    } else {
      msg.reasoningStreamActive = false
    }
  }
  if (msg._reasoningTypewriterRaf != null) return
  msg._reasoningTypewriterRaf = requestAnimationFrame(loop)
}

/**
 * 快速输出模式：扩展思维后大量 token 同时到达时使用微延迟模拟打字效果
 * 注意：始终使用最新的 reasoningContent，而不是快照
 */
const _runFastTypewriter = (msg) => {
  if (!msg || !msg._typewriterFastMode) return
  
  const loop = () => {
    if (!msg._typewriterFastMode) return
    
    // 使用最新的 reasoningContent，而不是快照
    const target = msg.reasoningContent || ''
    const current = msg.reasoningDisplayContent || ''
    
    if (current.length >= target.length && !msg._reasoningPhaseLive) {
      // 流已结束且已追上，真正结束
      msg.reasoningDisplayContent = target
      msg._typewriterFastMode = false
      msg._typewriterTargetContent = null
      msg.reasoningStreamActive = false
      scrollChatDuringReasoningStream()
      return
    }

    const backlog = target.length - current.length
    // live 且已追上：避免 setTimeout 空转，等新 delta 再由 scheduleReasoningTypewriter 拉起
    if (backlog <= 0) {
      msg.reasoningStreamActive = true
      scrollChatDuringReasoningStream()
      if (msg._reasoningPhaseLive) {
        msg._typewriterFastMode = false
      }
      return
    }
    // 快速模式下每帧追加更多字符，但仍有延迟感
    const charsPerFrame = Math.max(3, Math.min(12, Math.ceil(backlog / 8)))
    msg.reasoningDisplayContent = target.slice(0, current.length + charsPerFrame)
    msg.reasoningStreamActive = true
    scrollChatDuringReasoningStream()
    
    // 使用 setTimeout 创建微延迟（16-32ms），模拟打字机节奏
    const delay = Math.max(16, Math.min(32, 24 - Math.floor(charsPerFrame / 2)))
    setTimeout(() => {
      if (msg._typewriterFastMode) {
        requestAnimationFrame(loop)
      }
    }, delay)
  }
  
  requestAnimationFrame(loop)
}

/** 流式阶段展示用纯文本（Vue 插值自动转义，不做 marked）*/
const reasoningPlainForDisplay = (message) => {
  if (!message) return ''
  return squeezeReasoningVerticalWhitespace(message.reasoningDisplayContent ?? '')
}

/** 打字机纯文本轨：至少 2 个可见字符再渲染，避免「一个符 + 空槽」*/
const reasoningPlainVisible = (m) => {
  if (!m) return false
  const t = String(reasoningPlainForDisplay(m) || '').replace(INVISIBLE_REASONING_CHARS, '').trim()
  return t.length >= 2
}

// 格式化 steps 为 TodoTimeline 所需的 todos 数据结构
const formatTodosForTimeline = (steps, message) => {
  if (!steps || !Array.isArray(steps)) return []
  
  return steps.map((step, index) => {
    // 提取工具名称
    let toolName = step.toolCall?.name || step.title || extractToolName(step.originalTodo || step.title)
    
    // 生成友好的步骤描述（参考图2风格：简洁直接）
    let friendlyText = ''
    let resultSummary = ''
    
    // 判断步骤是否已完成
    const isCompleted = step.status === 'completed' || step.status === 'done'
    const isSkipped = step.status === 'skipped'
    const isRunning = step.status === 'running'
    
    // 优先使用步骤标题（已经是工具名称）
    if (step.title && ['database_query', 'grep', 'modify', 'create', 'browser_test', 'search'].includes(step.title)) {
      toolName = step.title
    }

    if (toolName === 'database_query') {
      friendlyText = '🔍 使用 database_query 工具查询数据'
      // 只有完成时才显示结果摘要
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted && step.toolCall?.output) {
        const output = step.toolCall.output
        try {
          const data = typeof output === 'string' ? JSON.parse(output) : output
          if (data.bugs && Array.isArray(data.bugs)) {
            resultSummary = `查询完成，找到 ${data.bugs.length} 个Bug`
          } else if (data.similar_count !== undefined) {
            resultSummary = `查询完成，相似缺陷 ${data.similar_count} 条`
          } else if (data.data?.bugs) {
            resultSummary = `查询完成，找到 ${data.data.bugs.length} 个Bug`
          } else {
            resultSummary = '查询完成'
          }
        } catch {
          resultSummary = '查询完成'
        }
      } else if (isRunning) {
        resultSummary = '查询中...'
      }
    } else if (toolName === 'grep') {
      friendlyText = '🎯 使用 grep 工具进行精准定位分析'
      // 只有完成时才显示结果摘要
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted) {
        const output = step.toolCall?.output
        if (output) {
          try {
            const data = typeof output === 'string' ? JSON.parse(output) : output
            // 优先使用后端生成的summary（已包含计划名和意图分析）
            if (data.data?.summary) {
              resultSummary = data.data.summary
            } else if (data.data?.badcase_analysis) {
              const count = data.data.badcase_analysis.length || 0
              resultSummary = count > 0 ? `分析完成，定位到 ${count} 条BadCase` : '分析完成，未找到BadCase'
            } else if (data.data?.plan_tree) {
              const planCount = data.data.plan_tree.total_plans || 0
              const badcaseCount = data.data.badcase_analysis?.length || 0
              resultSummary = badcaseCount > 0 
                ? `分析完成，解析 ${planCount} 个计划，定位 ${badcaseCount} 条BadCase`
                : `分析完成，解析 ${planCount} 个计划，未找到BadCase`
            } else if (data.data?.testcase_location?.length) {
              const n = data.data.testcase_location.length
              resultSummary = `分析完成，定位到 ${n} 条测试用例`
            } else {
              resultSummary = '分析完成，未找到匹配项'
            }
          } catch {
            resultSummary = '分析完成'
          }
        } else {
          // 没有输出时也显示结果
          resultSummary = '分析完成，无结果返回'
        }
      } else if (isRunning) {
        resultSummary = '分析中...'
      }
    } else if (toolName === 'browser_test') {
      friendlyText = '🌐 使用 browser_test 工具执行浏览器自动化测试'
      resultSummary = isSkipped ? '已跳过' : (isCompleted ? '测试执行完成' : (isRunning ? '测试执行中...' : ''))
    } else if (toolName === 'log_analyzer') {
      friendlyText = '📋 使用 log_analyzer 工具分析日志'
      resultSummary = isSkipped ? '已跳过' : (isCompleted ? '日志分析完成' : (isRunning ? '日志分析中...' : ''))
    } else if (toolName === 'modify') {
      friendlyText = '✏️ 使用 modify 工具修改数据'
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted) {
        const output = step.toolCall?.output
        if (output) {
          try {
            const data = typeof output === 'string' ? JSON.parse(output) : output
            if (data.batch_modify && data.results) {
              const successCount = data.results.filter(r => r.result?.success).length
              resultSummary = `批量修改完成，成功 ${successCount}/${data.results.length} 条`
            } else if (data.success && data.diff) {
              resultSummary = '修改预览完成，等待确认'
            } else if (data.success) {
              resultSummary = '修改执行成功'
            } else if (data.error) {
              resultSummary = `修改失败: ${data.error}`
            } else {
              resultSummary = '修改完成'
            }
          } catch {
            resultSummary = '修改完成'
          }
        } else {
          resultSummary = '修改完成，无结果返回'
        }
      } else if (isRunning) {
        // 实时显示后端下发的进度文案（流式）
        resultSummary = step.description || '修改中...'
      }
    } else if (toolName === 'create') {
      friendlyText = '➕ 使用 create 工具新建记录'
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted) {
        const output = step.toolCall?.output
        if (output) {
          try {
            const data = typeof output === 'string' ? JSON.parse(output) : output
            const inner = data.data || data
            if (inner.success === false || data.success === false) {
              resultSummary = `创建失败: ${inner.error || data.error || t('chat.stepUnknownErr')}`
            } else {
              const hasCreatePreview = inner.preview?.title || (inner.diff && inner.diff.length)
              if (inner.success !== false && !inner.created_id && hasCreatePreview) {
                const previewTitle = inner.preview?.title || inner.target || '待确认'
                resultSummary = inner.message
                  ? String(inner.message).slice(0, 120)
                  : `新建预览就绪: ${previewTitle}`
              } else if (inner.created_id) {
                resultSummary = `已创建，ID=${inner.created_id}`
              } else if (inner.error) {
                resultSummary = `创建失败: ${inner.error}`
              } else {
                resultSummary = '执行完成'
              }
            }
          } catch {
            resultSummary = '执行完成'
          }
        } else {
          resultSummary = '执行完成'
        }
      } else if (isRunning) {
        const last = (step.progressLog && step.progressLog.length) ? step.progressLog[step.progressLog.length - 1] : ''
        resultSummary = last || step.description || '正在生成新建预览...'
      }
    } else {
      // 其他工具，使用原始title
      friendlyText = step.title || step.description || '未知任务'
      const lastLog = (step.progressLog && step.progressLog.length) ? step.progressLog[step.progressLog.length - 1] : ''
      resultSummary = isSkipped
        ? '已跳过'
        : (isCompleted ? '执行完成' : (isRunning ? (lastLog || step.description || '执行中...') : ''))
    }
    
    // 关联对应的evidence卡片
    const relatedEvidence = message?.evidences?.find(ev => 
      ev.data?.tool === toolName || ev.data?.title?.includes(toolName)
    )

    // LLM 决策/观察等流式正文：进行中时优先在子标题展示（打字机效果）
    if (isRunning && step.llmDraft && String(step.llmDraft).trim()) {
      const raw = String(step.llmDraft)
      resultSummary = raw.length > 320 ? raw.slice(0, 320) + '...' : raw
    }
    
    return {
      text: friendlyText,
      resultSummary: resultSummary,  // 结果摘要（modify 运行中时为最新进度）
      status: step.status || 'pending',
      showTypewriter: step.status === 'running',
      toolCall: step.toolCall,  // 保留toolCall供展开
      evidence: relatedEvidence?.data,  // 关联的evidence数据
      progressLog: step.progressLog || []  // modify 等实时进度日志，用于流式多行展示
    }
  })
}

/**
 * 解析 SSE 里的步骤下标：避免 Number(null)===0 把未带 index 的事件错绑到第 1 步，
 * 导致 grep 步骤上出现 create 心跳 / observation
 */
const resolveStreamStepIndex = (raw, steps) => {
  if (raw === null || raw === undefined) return null
  if (typeof raw === 'string' && raw.trim() === '') return null
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) return null
  if (!Array.isArray(steps) || !steps[n]) return null
  return n
}

/** 仅当后端下发过计划（plan / todos）时才有行；无则规划备忘整块不渲染 */
const planMemoRowsForMessage = (msg) => {
  if (!msg || !Array.isArray(msg.reactPlanSteps) || msg.reactPlanSteps.length === 0) return undefined
  return msg.reactPlanSteps
}

/** 仅有计划数据时才用「等 THINK 再揭示」；无计划时不挡其它 UI */
const suppressPlanOverviewForMessage = (msg) => {
  if (!msg) return false
  const hasPlan = Array.isArray(msg.reactPlanSteps) && msg.reactPlanSteps.length > 0
  if (!hasPlan) return false
  return msg._planMemoRevealReady === false || msg.reactPlanPanelSuppressed === true
}

/** 步骤执行日志：流式追加，去重连续相同行（心跳「已等待 x.xs」不去重，避免界面像卡住）*/
const appendStepDetailLine = (step, line) => {
  if (!step || line == null || line === '') return
  const t = String(line).trimEnd()
  if (!t) return
  if (!step.detailLog) step.detailLog = []
  const last = step.detailLog[step.detailLog.length - 1]
  const isHeartbeat = /已等待\s*[\d.]+s/.test(t)
  if (last === t && !isHeartbeat) return
  step.detailLog.push(t)
  if (step.detailLog.length > 100) step.detailLog.shift()
  // 新数组引用，确保子组件（AgentTaskRun）对流式追加即时刷新
  step.detailLog = [...step.detailLog]
}

// 获取 diff 字段的旧值（多行 diff 须合并全部 delete 行）
const getFieldOldValue = (fieldDiff) => {
  if (!fieldDiff || !fieldDiff.lines) return null
  const deleteLines = fieldDiff.lines.filter((l) => l.type === 'delete')
  if (deleteLines.length > 0) {
    return deleteLines.map((l) => (l.content != null ? String(l.content) : '')).join('\n').trim() || null
  }
  const unchangedLine = fieldDiff.lines.find((l) => l.type === 'unchanged')
  if (unchangedLine) return unchangedLine.content
  return null
}

// 获取 diff 字段的新值（多行 diff 须合并全部 add 行）
const getFieldNewValue = (fieldDiff) => {
  if (!fieldDiff || !fieldDiff.lines) return null
  const addLines = fieldDiff.lines.filter((l) => l.type === 'add')
  if (addLines.length > 0) {
    return addLines.map((l) => (l.content != null ? String(l.content) : '')).join('\n').trim() || null
  }
  const unchangedLine = fieldDiff.lines.find((l) => l.type === 'unchanged')
  if (unchangedLine) return unchangedLine.content
  return null
}

/**
 * 首轮 THINK 标题：与 AgentTaskRun 折叠头一致，文案一律来自 i18n（agentTask.*），勿硬编码。
 */
const thoughtSummaryLabel = (message) => {
  // 流式推理未结束：眉标固定为「思考中 / Thinking」，勿用「思考」（易被理解成已结束）
  if (message?._reasoningPhaseLive) return t('agentTask.thinking')
  const hasBody = substantiveThinkPhase(message)
  if (!hasBody) return t('agentTask.thinking')
  const ms = message.reasoningUiDurationMs
  const kind = message.reasoningUiKind
  const thr = message.reasoningBriefThresholdMs ?? 800
  if (kind === 'brief' || (ms != null && ms >= 0 && ms < thr)) return t('agentTask.thoughtBriefly')
  if (ms != null && ms >= 0) return t('agentTask.thoughtFor', { s: (ms / 1000).toFixed(1) })
  const tt = message.agentResult?.thinking_time
  if (tt != null && tt >= 0 && Number(tt) < 0.8) return t('agentTask.thoughtBriefly')
  if (tt != null && tt >= 0) return t('agentTask.thoughtFor', { s: Number(tt).toFixed(1) })
  return t('agentTask.thought')
}

// 是否显示「统一总结」块（关键发现 + 执行统计合并，Cursor 式耗时 Xs）
const hasUnifiedSummary = (message) => {
  if (message.reactDirectChatReply) return false
  if (message.unifiedSummaryLoading) return true
  // 增量运行总览 / 总结流式草稿：仅主循环结束（SSE finished）后再展示，避免中途底部刷字或占位
  const _afterLoop = message.reactMainLoopFinished === true
  if (_afterLoop && message.summaryStreamDraft && String(message.summaryStreamDraft).trim()) return true
  if (_afterLoop && message.runningSummaryDraft && String(message.runningSummaryDraft).trim()) return true
  const r = message.agentResult
  if (!r || r.status !== 'success') return false
  return (r.findings && r.findings.length > 0) || r.execution_time != null || (r.steps_count != null && r.steps_count > 0)
}

/** 落库曾误把 done.summary 写成沙箱一句提示，历史消息需跳过该占位，改用 findings 等兜底 */
const isLegacySandboxOnlySummaryText = (txt) => {
  const s = String(txt || '').trim()
  if (!s || s.length > 480) return false
  if (/\n##\s/.test(s)) return false
  return /沙箱预览完成|预览已生成|请确认是否应用|请确认变更|sandbox preview completed|preview completed|confirm whether to apply/i.test(
    s
  )
}

// 统一总结正文：优先流式草稿（summary_stream / running_summary_stream）；无草稿时取 summaryText 或 findings 兜底
const getUnifiedSummaryBody = (message) => {
  const r = message.agentResult
  const _afterLoop = message.reactMainLoopFinished === true
  const _rsDraft = String(message.runningSummaryDraft || '').trim()
  if (
    message.unifiedSummaryLoading &&
    !(String(message.summaryStreamDraft || '').trim()) &&
    !_rsDraft &&
    !(r?.summaryText && String(r.summaryText).trim())
  ) {
    return ''
  }
  if (_afterLoop && message.summaryStreamDraft && String(message.summaryStreamDraft).trim()) {
    return String(message.summaryStreamDraft).trim()
  }
  // 增量运行总览：勿要求 _afterLoop，避免 tail 与 running_summary 包顺序导致草稿被忽略、只剩执行统计兜底
  if (_rsDraft) {
    return _rsDraft
  }
  if (r?.summaryText && typeof r.summaryText === 'string' && r.summaryText.trim()) {
    const st = r.summaryText.trim()
    if (!isLegacySandboxOnlySummaryText(st)) return st
  }
  const lines = []
  if (r?.findings && r.findings.length > 0) {
    r.findings.forEach(f => lines.push('- ' + (typeof f === 'string' ? f : String(f))))
  }
  // 耗时与步数已在总结标题「总结 X.XXs」与步骤区展示，此处不再拼「执行统计/完成步骤/任务成功」
  const body = lines.join('\n')
  // 有思考耗时但无思考内容时提示（qwen-max 等模型可能不返回 reasoning_content）
  const thinkingTime = (r?.thinking_time ?? r?.execution_time ?? 0)
  if (thinkingTime > 0 && !substantiveThinkPhase(message)) {
    const hint = '思考过程未返回（当前模型或接口可能不返回思考内容）'
    return body ? `${hint}\n\n${body}` : hint
  }
  return body
}

/** 底部统一总结是否用 Markdown 渲染（增量运行总览含固定 ## 标题） */
const unifiedSummaryBodyIsMarkdown = (message) => {
  const t = getUnifiedSummaryBody(message)
  return typeof t === 'string' && /(\n|^)##\s/.test(t)
}

// 处理导航指令（展开计划并定位 Bug / BadCase / 测试用例）
const handleNavigation = (navigation) => {
  if (!navigation) return
  
  // 处理多个Bug导航：不自动跳转，由用户点击选择
  if (navigation.type === 'multiple') {
    console.log('[NAV] 检测到多个定位结果，在关键发现中显示列表，等待用户点击')
    return
  }
  
  // 单个Bug导航：直接跳转
  if (navigation.type !== 'expand_and_locate') return
  
  console.log('[NAV] 执行导航:', navigation)

  const recordIdRaw = navigation.record_id ?? navigation.bug_id ?? navigation.id
  const recordId =
    snowflakeIdStr(recordIdRaw) ||
    (recordIdRaw != null && String(recordIdRaw).trim() !== '' ? String(recordIdRaw).trim() : '')
  const navTarget = (navigation.target || 'bug').toString().toLowerCase().replace(/-/g, '_')
  let normalizedTarget = navTarget === 'test_case' || navTarget === 'testcase' ? 'testcase' : navTarget
  if (normalizedTarget === 'bad_case' || normalizedTarget === 'badcase') normalizedTarget = 'badcase'
  const cardIdRaw =
    navigation.card_id != null && navigation.card_id !== ''
      ? navigation.card_id
      : normalizedTarget === 'card'
        ? recordIdRaw
        : undefined
  const cardIdNav =
    cardIdRaw != null && cardIdRaw !== ''
      ? snowflakeIdStr(cardIdRaw) || String(cardIdRaw).trim()
      : undefined

  const mergedLegacyRaw =
    navigation.merged_from_legacy != null && String(navigation.merged_from_legacy).trim() !== ''
      ? String(navigation.merged_from_legacy).trim().toLowerCase().replace(/-/g, '_')
      : null
  const mergedLegacy =
    mergedLegacyRaw === 'bad_case'
      ? 'badcase'
      : mergedLegacyRaw === 'test_case'
        ? 'testcase'
        : mergedLegacyRaw
  const legacyRowIdRaw =
    navigation.legacy_row_id != null && navigation.legacy_row_id !== ''
      ? navigation.legacy_row_id
      : navigation.source_id != null && navigation.source_id !== ''
        ? navigation.source_id
        : null
  const legacyRowId =
    legacyRowIdRaw != null && legacyRowIdRaw !== ''
      ? snowflakeIdStr(legacyRowIdRaw) || String(legacyRowIdRaw).trim()
      : null

  // 发送自定义事件给父组件 ProjectDetail
  const event = new CustomEvent('grep-navigate', {
    detail: {
      planId: navigation.plan_id,
      plan_id: navigation.plan_id,
      bugId: recordId,
      recordId,
      target: normalizedTarget,
      title: navigation.title,
      navTitle: navigation.navTitle ?? navigation.title,
      ...(mergedLegacy
        ? {
            merged_from_legacy: mergedLegacy,
            mergedFromLegacy: mergedLegacy
          }
        : {}),
      ...(legacyRowId != null && legacyRowId !== ''
        ? { legacy_row_id: legacyRowId, legacyRowId }
        : {}),
      ...(cardIdNav != null && cardIdNav !== '' ? { card_id: cardIdNav, cardId: cardIdNav } : {}),
      /**
       * 纯「卡片层」命中须留在迭代卡片表；grep 合并项（merged_from_legacy）要进子类型列表，勿标 prefer_card_layer。
       */
      ...(normalizedTarget === 'card' && !mergedLegacy ? { prefer_card_layer: true } : {})
    }
  })
  window.dispatchEvent(event)
  
  console.log('[NAV] 已发送导航事件，detail:', event.detail)
}

// 确认修改
const handleConfirmModify = async (modifyData) => {
  console.log('[MODIFY] 用户确认修改:', modifyData)
  
  // 清除modifyNavigation
  const currentMessage = messages.value[messages.value.length - 1]
  if (currentMessage) {
    currentMessage.modifyNavigation = null
  }
  
  // 调用modify工具，confirm=true
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_input: `确认修改${modifyData.target} ID=${modifyData.target_id}`,
        project_id: props.projectId,
        model: selectedModel.value,
        session_id: props.sessionId,
        confirm_modify: modifyData, // 传递modify数据
        locale: localeForApi()
      })
    })
    
    console.log('[MODIFY] 修改已提交')
  } catch (error) {
    console.error('[MODIFY] 修改失败:', error)
  }
}

/**
 * 聚合同一 (target, target_id) 在会话中所有未采纳的修改：不同字段合并，相同字段后面覆盖前面
 * 用于 diff review：已采纳的不参与；后面对话对前面 diff 的合并形成新diff
 * @returns {{ modifications: {}, diff: [], plan_id, messageId } | null}
 */
function getMergedPendingForTarget(msgs, target, targetIdRaw) {
  const want = snowflakeIdStr(targetIdRaw)
  if (!want) return null
  const items = []
  for (let i = 0; i < (msgs || []).length; i++) {
    const msg = msgs[i]
    if (!msg || msg.isUser) continue
    const msgIdx = i
    for (const group of msg.modifyGroups || []) {
      for (const item of group.items || []) {
        const tid = snowflakeIdStr(item.target_id ?? item.targetId ?? item.id)
        if (!tid || tid !== want) continue
        if (item.target && item.target !== target) continue
        if (item.cancelled === true) continue
        const itTarget = item.target || group.target || target
        const pk = makePersistDiffKey(itTarget, tid)
        let includeItem = true
        if (persistedPendingLoaded.value && pk) {
          if (persistedPendingDiffKeys.value.has(pk)) includeItem = true
          else {
            includeItem = !msg.isHistorical && item.confirmation_required !== false
          }
        } else if (item.confirmation_required === false) {
          includeItem = false
        }
        if (!includeItem) continue
        items.push({
          ...item,
          plan_id: group.plan_id,
          messageId: msg.id,
          _msgIdx: msgIdx
        })
      }
    }
    const nav = msg.modifyNavigation
    if (nav?.batch_modify && nav.batch_results?.length) {
      for (const r of nav.batch_results) {
        const tid = snowflakeIdStr(r.target_id)
        if (!tid || tid !== want) continue
        if (r.cancelled === true) continue
        if (r.target && r.target !== target) continue
        const itTarget = r.target || nav.target || target
        const pk = makePersistDiffKey(itTarget, tid)
        let includeR = true
        if (persistedPendingLoaded.value && pk) {
          if (persistedPendingDiffKeys.value.has(pk)) includeR = true
          else {
            includeR = !msg.isHistorical && r.confirmation_required !== false
          }
        } else if (r.confirmation_required === false) {
          includeR = false
        }
        if (!includeR) continue
        items.push({
          ...r,
          plan_id: r.plan_id ?? nav.plan_id,
          messageId: msg.id,
          _msgIdx: msgIdx
        })
      }
    } else if (nav && !nav.batch_modify && !nav.is_create && nav.cancelled !== true) {
      const tid = snowflakeIdStr(nav.target_id ?? nav.targetId)
      if (!tid || tid !== want || (nav.target || 'badcase') !== target) {
        continue
      }
      const pk = makePersistDiffKey(target, tid)
      let include = false
      if (persistedPendingLoaded.value && pk) {
        if (persistedPendingDiffKeys.value.has(pk)) include = true
        else include = !msg.isHistorical && nav.confirmation_required !== false
      } else {
        include = nav.confirmation_required !== false
      }
      if (include) {
        items.push({
          target_id: tid,
          target: nav.target || 'badcase',
          modifications: nav.modifications || {},
          diff: nav.diff || [],
          plan_id: nav.plan_id ?? nav.preview?.plan_id,
          messageId: msg.id,
          _msgIdx: msgIdx,
          before: nav.before ?? null,
          after: nav.after ?? null
        })
      }
    }
  }
  if (items.length === 0) return null
  items.sort((a, b) => (a._msgIdx ?? 0) - (b._msgIdx ?? 0))
  const mergedMods = {}
  const mergedDiffByField = {}
  for (const item of items) {
    const mods = item.modifications || {}
    for (const [field, val] of Object.entries(mods)) {
      const prev = mergedMods[field]
      const v = val && typeof val === 'object' && 'new' in val ? val : { old: '', new: val }
      mergedMods[field] = {
        old: prev ? prev.old : (v.old ?? ''),
        new: v.new ?? ''
      }
    }
    const diffs = item.diff || []
    for (const fd of diffs) {
      const fkey = fd.field ?? fd.field_label ?? ''
      if (!fkey) continue
      const delLine = fd.lines?.find((l) => l.type === 'delete')
      const addLine = fd.lines?.find((l) => l.type === 'add')
      if (!mergedDiffByField[fkey]) {
        mergedDiffByField[fkey] = { field: fkey, field_label: fd.field_label ?? fkey, firstOld: delLine?.content ?? '', lastNew: addLine?.content ?? '' }
      } else {
        if (addLine) mergedDiffByField[fkey].lastNew = addLine.content
      }
    }
  }
  for (const [fkey, { firstOld, lastNew }] of Object.entries(mergedDiffByField)) {
    if (!(fkey in mergedMods)) mergedMods[fkey] = { old: firstOld, new: lastNew }
  }
  const diff = Object.values(mergedDiffByField).map(({ field, field_label, firstOld, lastNew }) => ({
    field,
    field_label: field_label || field,
    lines: [
      { type: 'delete', content: firstOld || '' },
      { type: 'add', content: lastNew || '' }
    ]
  }))
  const last = items[items.length - 1]
  let pickBefore = last.before ?? null
  let pickAfter = last.after ?? null
  for (let i = items.length - 1; i >= 0; i--) {
    const b = items[i].before
    if (b && typeof b === 'object') {
      pickBefore = b
      if (b.status != null && String(b.status).trim() !== '') break
    }
  }
  for (let i = items.length - 1; i >= 0; i--) {
    const a = items[i].after
    if (a && typeof a === 'object') {
      pickAfter = a
      break
    }
  }
  return {
    modifications: mergedMods,
    diff,
    plan_id: last.plan_id,
    messageId: last.messageId,
    /** 供列表跳转与沙箱补全：优先带 status 的 before；单条 modifyNavigation 也带上 nav.before/after */
    before: pickBefore,
    after: pickAfter
  }
}

// 沙箱预览按钮文案：按目标类型显示「跳转到Bug/BadCase/测试用例详情」
const getModifyJumpButtonLabel = (target) => {
  if (target === 'bug') return t('chat.jumpBug')
  if (target === 'badcase') return t('chat.jumpBadcase')
  if (target === 'testcase') return t('chat.jumpTestcase')
  return t('chat.showInList')
}

const makePersistDiffKey = (target, targetId) => {
  const nt = normalizeModifyTarget(target)
  const tid = snowflakeIdStr(targetId)
  if (!nt || !tid) return ''
  return `${nt}:${tid}`
}

const persistedPendingDiffKeys = ref(new Set())
const persistedPendingLoaded = ref(false)
let _persistedPendingLoadedAt = 0
let _persistedPendingFetchInFlight = null
let _persistedPendingEtag = ''
let _persistedPendingForceFetchAt = 0

/**
 * 是否仍应对列表派发「待确认」：
 * - pending 表里有该 key → 仍待确认（返回 false = 未采纳）
 * - 历史消息且表里没有 → 视为已处理（返回 true）
 * - 实时流且表里没有 → 仍以工具 JSON 的 initialProcessed 为准（避免预览刚写出、GET pending 尚未含该行时误判「一出来就采纳」）
 */
const resolveAlreadyProcessedByPersisted = (
  initialProcessed,
  target,
  targetId,
  messageIsHistorical = false
) => {
  if (!persistedPendingLoaded.value) return !!initialProcessed
  const key = makePersistDiffKey(target, targetId)
  if (!key) return !!initialProcessed
  if (persistedPendingDiffKeys.value.has(key)) return false
  if (messageIsHistorical) return true
  return !!initialProcessed
}

/**
 * @param {boolean} force
 * @param {{ emitListSync?: boolean }} opts emitListSync：是否派发 diff-review-sync。从沙箱/聊天侧即将 show-modify-in-list 时应为 false，否则左侧会再 restore 一次，diff 连闪且可能与合并后的 payload 不一致。
 */
const applyPersistedKeysFromServerItems = (items) => {
  const next = new Set()
  ;(Array.isArray(items) ? items : []).forEach((it) => {
    const key = makePersistDiffKey(it.target, it.target_id)
    if (key) next.add(key)
  })
  persistedPendingDiffKeys.value = next
  persistedPendingLoaded.value = true
  _persistedPendingLoadedAt = Date.now()
}

const onDiffReviewPushForChat = (ev) => {
  const { type, payload } = ev?.detail || {}
  if (type === 'snapshot') {
    applyPersistedKeysFromServerItems(payload?.items || [])
    return
  }
  if (type === 'upsert' && payload) {
    const key = makePersistDiffKey(payload.target, payload.target_id)
    if (!key) return
    const next = new Set(persistedPendingDiffKeys.value)
    next.add(key)
    persistedPendingDiffKeys.value = next
    persistedPendingLoaded.value = true
    _persistedPendingLoadedAt = Date.now()
    return
  }
  if (type === 'resolve' && payload) {
    const key = makePersistDiffKey(payload.target, payload.target_id)
    if (!key) return
    const next = new Set(persistedPendingDiffKeys.value)
    next.delete(key)
    persistedPendingDiffKeys.value = next
  }
}

const refreshPersistedPendingDiffKeys = async (force = false, opts = {}) => {
  const emitListSync = opts.emitListSync !== false
  const allowNetworkWhenPushOk = opts.allowNetworkWhenPushOk === true
  try {
    if (!props.projectId) return
    const now = Date.now()
    if (!force && now - _persistedPendingLoadedAt < 1500) return
    const pushOk =
      diffReviewPushShared.connected.value &&
      now - (diffReviewPushShared.lastEventAt.value || 0) < 120000
    if (pushOk && !allowNetworkWhenPushOk) return
    if (force && now - _persistedPendingForceFetchAt < 5000) return
    if (_persistedPendingFetchInFlight) return _persistedPendingFetchInFlight
    _persistedPendingForceFetchAt = force ? now : _persistedPendingForceFetchAt
    _persistedPendingFetchInFlight = (async () => {
      const headers = {}
      if (_persistedPendingEtag) headers['If-None-Match'] = _persistedPendingEtag
      const resp = await fetch(
        `${BACKEND_BASE_URL}/api/projects/${props.projectId}/diff-reviews?status=pending`,
        { credentials: 'include', headers }
      )
      if (resp.status === 304) {
        persistedPendingLoaded.value = true
        _persistedPendingLoadedAt = now
        return
      }
      if (!resp.ok) return
      const et = resp.headers.get('ETag')
      if (et) _persistedPendingEtag = et.replace(/^"|"$/g, '')
      const data = await resp.json()
      const items = Array.isArray(data?.items) ? data.items : []
      const next = new Set()
      items.forEach((it) => {
        const key = makePersistDiffKey(it.target, it.target_id)
        if (key) next.add(key)
      })
      persistedPendingDiffKeys.value = next
      persistedPendingLoaded.value = true
      _persistedPendingLoadedAt = now
      if (emitListSync) {
        window.dispatchEvent(new CustomEvent('diff-review-sync', { bubbles: true }))
      }
    })()
    await _persistedPendingFetchInFlight
    return
  } catch (e) {
    persistedPendingLoaded.value = false
    console.warn('[DIFF] 刷新持久化 pending keys 失败:', e)
  } finally {
    _persistedPendingFetchInFlight = null
  }
}

const hasDetailFieldInPreview = (diffRows, mods) => {
  const diffRowImpliesDetail = (fd) => {
    const fk = String(fd?.field || '').trim().toLowerCase()
    if (fk && DETAIL_FIELDS.includes(fk)) return true
    const lab = String(fd?.field_label || '')
    return /优先级|严重程度|严重级别|用例类型|测试类型|问题分类|相似问题|复现|正确答案|答案|原因|描述|步骤|备注|评论|追加评论|基线/i.test(lab)
  }
  const diffHasDetail = Array.isArray(diffRows) && diffRows.some(diffRowImpliesDetail)
  if (diffHasDetail) return true
  if (mods && typeof mods === 'object') {
    return Object.keys(mods).some((k) => {
      const nk = String(k).trim().toLowerCase()
      return (
        DETAIL_FIELDS.includes(nk) ||
        TESTCASE_DETAIL_FIELDS.includes(nk) ||
        /优先级|严重程度|用例类型|测试类型|问题分类/.test(String(k))
      )
    })
  }
  return false
}

// 在列表中显示修改（并跳转到对应详情页）
// 处理分组跳转到列表
const handleShowGroupInList = async (group, messageId, navOpts = {}) => {
  console.log('[MODIFY] 分组跳转到列表', group, 'messageId:', messageId)

  // 防御性检查
  if (!group) {
    console.error('[MODIFY] group 为空')
    return
  }
  if (!group.items || !Array.isArray(group.items) || group.items.length === 0) {
    console.warn('[MODIFY] group.items 为空或无效')
    return
  }

  if (!navOpts.skipPersistedRefresh) {
    await refreshPersistedPendingDiffKeys(true, { emitListSync: false })
  }

  const msgObj = messages.value.find((m) => m.id === messageId)
  const messageIsHistorical = !!(msgObj && msgObj.isHistorical)

  const peerTargetIds = group.items
    .map((it) => snowflakeIdStr(it?.target_id ?? it?.targetId ?? it?.id))
    .filter((id) => !!id)

  const batchItems = []
  /** 已采纳：合并为一次 grep-navigate，避免逐条异步定位造成「一行行」闪高亮 */
  const adoptedNav = []
  for (let index = 0; index < group.items.length; index++) {
    const item = group.items[index]
    const rawId = item?.target_id ?? item?.targetId ?? item?.id
    if (!item || rawId === undefined || rawId === null) {
      console.warn('[MODIFY] 跳过无效 item:', item)
      continue
    }
    const idStr = snowflakeIdStr(rawId)
    if (!idStr) {
      console.warn('[MODIFY] 跳过无效 target_id:', rawId)
      continue
    }
    let alreadyProcessed = item.confirmation_required === false
    const tgt = item.target || group.target || 'badcase'
    alreadyProcessed = resolveAlreadyProcessedByPersisted(
      alreadyProcessed,
      tgt,
      idStr,
      messageIsHistorical
    )
    const merged = !alreadyProcessed ? getMergedPendingForTarget(messages.value, tgt, idStr) : null
    const payload = merged
      ? {
          diff: merged.diff,
          modifications: merged.modifications,
          plan_id: merged.plan_id ?? group.plan_id,
          messageId: merged.messageId,
          before: merged.before ?? null,
          after: merged.after ?? null
        }
      : {
          diff: item.diff || [],
          modifications: item.modifications || {},
          plan_id: group.plan_id,
          messageId,
          before: item.before ?? null,
          after: item.after ?? null
        }

    if (alreadyProcessed) {
      const openDetail = hasDetailFieldInPreview(payload.diff, payload.modifications)
      const navCidAdopted =
        item.card_id ??
        item.cardId ??
        payload.before?.card_id ??
        payload.before?.cardId ??
        payload.after?.card_id ??
        payload.after?.cardId
      const navCidAdoptedStr =
        navCidAdopted != null && String(navCidAdopted).trim() !== ''
          ? snowflakeIdStr(navCidAdopted) || String(navCidAdopted).trim()
          : null
      adoptedNav.push({
        intTargetId: idStr,
        tgt,
        openDetail,
        planId: payload.plan_id ?? group.plan_id ?? null,
        ...(navCidAdoptedStr ? { navCardId: navCidAdoptedStr } : {})
      })
    } else {
      const gCardNav = (() => {
        const c = item.card_id ?? item.cardId ?? item.before?.card_id ?? item.before?.cardId
        if (c == null || String(c).trim() === '') return null
        return snowflakeIdStr(c) || String(c).trim()
      })()
      batchItems.push({
        targetId: idStr,
        target: tgt,
        diff: payload.diff,
        modifications: payload.modifications,
        plan_id: payload.plan_id,
        executed: false,
        messageId: payload.messageId,
        batchIndex: index,
        peerTargetIds,
        before: payload.before ?? null,
        after: payload.after ?? null,
        ...(gCardNav ? { card_id: gCardNav } : {})
      })
    }
  }
  if (adoptedNav.length > 0) {
    const detailFirst = adoptedNav.find((x) => x.openDetail)
    const planId = adoptedNav[0].planId ?? group.plan_id ?? null
    const cardFromAdopted = adoptedNav.find((x) => x.navCardId)?.navCardId
    window.dispatchEvent(
      new CustomEvent('grep-navigate', {
        detail: {
          planId,
          target: detailFirst?.tgt ?? adoptedNav[0].tgt,
          recordIds: adoptedNav.map((x) => x.intTargetId),
          openDetail: !!detailFirst,
          ...(detailFirst
            ? { recordId: detailFirst.intTargetId, bugId: detailFirst.intTargetId }
            : {}),
          ...(cardFromAdopted ? { card_id: cardFromAdopted, cardId: cardFromAdopted } : {})
        },
        bubbles: true
      })
    )
  }
  if (batchItems.length > 0) {
    window.dispatchEvent(
      new CustomEvent('show-modify-in-list', {
        detail: { __modifyListBatch: true, items: batchItems },
        bubbles: true
      })
    )
    console.log('[DEBUG-show-modify-in-list batch from SimpleChatPanel]', batchItems.length, 'items')
  }
}

const handleShowModifyInList = async (modifyData, messageId) => {
  console.log('[MODIFY] 在列表中显示修改(来自后端结果):', modifyData, 'messageId:', messageId)
  await refreshPersistedPendingDiffKeys(true, { emitListSync: false })

  const msgObj = messages.value.find((m) => m.id === messageId)
  const messageIsHistorical = !!(msgObj && msgObj.isHistorical)

  // 防御性检查
  if (!modifyData) {
    console.error('[MODIFY] modifyData 为空')
    return
  }

  // 新建已采纳：只跳转列表，不再派发待确认新建事件
  if (modifyData.navigate_to_existing && modifyData.created_id != null) {
    const pv = modifyData.preview || {}
    const planId = modifyData.plan_id ?? pv.plan_id ?? pv.planId
    const cidNav = pv.card_id ?? pv.cardId ?? modifyData.card_id ?? modifyData.cardId
    const cidStr =
      cidNav != null && String(cidNav).trim() !== ''
        ? snowflakeIdStr(cidNav) || String(cidNav).trim()
        : null
    window.dispatchEvent(new CustomEvent('grep-navigate', {
      detail: {
        planId,
        bugId: modifyData.created_id,
        recordId: modifyData.created_id,
        target: modifyData.target || 'bug',
        ...(cidStr ? { card_id: cidStr, cardId: cidStr } : {})
      },
      bubbles: true
    }))
    return
  }
  
  // 批量修改：合并为一次 show-modify-in-list，避免多个 async 监听交错导致黄条逐个出现
  if (modifyData.batch_modify && modifyData.batch_results && Array.isArray(modifyData.batch_results) && modifyData.batch_results.length > 0) {
    console.log('[MODIFY] 批量修改，合并为单次列表事件')
    const peerTargetIds = modifyData.batch_results
      .map((r) => snowflakeIdStr(r?.target_id))
      .filter((id) => !!id)
    const batchItems = []
    const adoptedNavBatch = []
    for (let index = 0; index < modifyData.batch_results.length; index++) {
      const result = modifyData.batch_results[index]
      if (!result || result.target_id === undefined) {
        console.warn('[MODIFY] 跳过无效 result:', result)
        continue
      }
      const idStr = snowflakeIdStr(result.target_id)
      if (!idStr) {
        console.warn('[MODIFY] 跳过无效 target_id:', result.target_id)
        continue
      }
      let alreadyProcessed = result.confirmation_required === false
      const tgt = result.target || 'badcase'
      alreadyProcessed = resolveAlreadyProcessedByPersisted(
        alreadyProcessed,
        tgt,
        idStr,
        messageIsHistorical
      )
      const merged = !alreadyProcessed ? getMergedPendingForTarget(messages.value, tgt, idStr) : null
      const payload = merged || {
        diff: result.diff || [],
        modifications: result.modifications || {},
        plan_id: result.plan_id,
        messageId,
        before: result.before ?? null,
        after: result.after ?? null
      }
      if (alreadyProcessed) {
        const openDetail = hasDetailFieldInPreview(payload.diff, payload.modifications)
        adoptedNavBatch.push({
          intTargetId: idStr,
          tgt,
          openDetail,
          planId: payload.plan_id ?? result.plan_id ?? modifyData.plan_id ?? null
        })
      } else {
        const cardNavStr = (() => {
          const c = result.card_id ?? result.cardId ?? result.before?.card_id ?? result.before?.cardId
          if (c == null || String(c).trim() === '') return null
          return snowflakeIdStr(c) || String(c).trim()
        })()
        batchItems.push({
          targetId: idStr,
          target: tgt,
          diff: payload.diff,
          modifications: payload.modifications,
          plan_id: payload.plan_id ?? result.plan_id,
          executed: false,
          messageId: payload.messageId ?? messageId,
          batchIndex: index,
          peerTargetIds,
          before: payload.before ?? null,
          after: payload.after ?? null,
          ...(cardNavStr ? { card_id: cardNavStr } : {})
        })
      }
    }
    if (adoptedNavBatch.length > 0) {
      const detailFirst = adoptedNavBatch.find((x) => x.openDetail)
      const planId = adoptedNavBatch[0].planId ?? modifyData.plan_id ?? null
      const cardFromBatch = (() => {
        for (const br of modifyData.batch_results || []) {
          const c =
            br?.card_id ??
            br?.cardId ??
            br?.before?.card_id ??
            br?.before?.cardId ??
            br?.after?.card_id ??
            br?.after?.cardId
          if (c != null && String(c).trim() !== '') {
            return snowflakeIdStr(c) || String(c).trim()
          }
        }
        return null
      })()
      window.dispatchEvent(
        new CustomEvent('grep-navigate', {
          detail: {
            planId,
            target: detailFirst?.tgt ?? adoptedNavBatch[0].tgt,
            recordIds: adoptedNavBatch.map((x) => x.intTargetId),
            openDetail: !!detailFirst,
            ...(detailFirst
              ? { recordId: detailFirst.intTargetId, bugId: detailFirst.intTargetId }
              : {}),
            ...(cardFromBatch ? { card_id: cardFromBatch, cardId: cardFromBatch } : {})
          },
          bubbles: true
        })
      )
    }
    if (batchItems.length > 0) {
      window.dispatchEvent(
        new CustomEvent('show-modify-in-list', {
          detail: { __modifyListBatch: true, items: batchItems },
          bubbles: true
        })
      )
    }
    return
  }
  
  // 新建预览（create 工具）：无真实 target_id，单独派发事件由 ProjectDetail 处理计划跳转与待创建状态  
  if (modifyData.is_create) {
    const preview =
      modifyData.preview ||
      modifyData.modifications ||
      {}
    const event = new CustomEvent('show-create-in-list', {
      detail: {
        target: modifyData.target || 'testcase',
        preview: { ...preview },
        diff: modifyData.diff || [],
        messageId
      },
      bubbles: true
    })
    window.dispatchEvent(event)
    console.log('[CREATE] 派发 show-create-in-list:', event.detail)
    return
  }

  // 单个修改
  const rawId = modifyData.target_id ?? modifyData.targetId ?? modifyData.id
  const targetIdStr = snowflakeIdStr(rawId)
  if (!targetIdStr) {
    console.error('[MODIFY] 无效的 target_id:', rawId)
    return
  }

  const navCardStr = (() => {
    const c =
      modifyData.card_id ??
      modifyData.cardId ??
      modifyData.before?.card_id ??
      modifyData.before?.cardId
    if (c == null || String(c).trim() === '') return null
    return snowflakeIdStr(c) || String(c).trim()
  })()
  
  let alreadyProcessed =
    modifyData.cancelled === true ||
    modifyData.confirmation_required === false
  const tgt = modifyData.target || 'badcase'
  alreadyProcessed = resolveAlreadyProcessedByPersisted(
    alreadyProcessed,
    tgt,
    targetIdStr,
    messageIsHistorical
  )
  const merged = !alreadyProcessed ? getMergedPendingForTarget(messages.value, tgt, targetIdStr) : null
  const payload = merged || {
    diff: modifyData.diff || [],
    modifications: modifyData.modifications || {},
    plan_id: modifyData.plan_id || modifyData.before?.plan_id || null,
    messageId,
    before: modifyData.before ?? null,
    after: modifyData.after ?? null
  }
  if (alreadyProcessed) {
    const openDetail = hasDetailFieldInPreview(payload.diff, payload.modifications)
    const grepCardStr = (() => {
      const c =
        modifyData.card_id ??
        modifyData.cardId ??
        payload.before?.card_id ??
        payload.before?.cardId ??
        payload.after?.card_id ??
        payload.after?.cardId
      if (c == null || String(c).trim() === '') return null
      return snowflakeIdStr(c) || String(c).trim()
    })()
    window.dispatchEvent(new CustomEvent('grep-navigate', {
      detail: {
        planId: payload.plan_id ?? modifyData.plan_id ?? null,
        recordId: targetIdStr,
        bugId: targetIdStr,
        target: tgt,
        openDetail,
        ...(grepCardStr ? { card_id: grepCardStr, cardId: grepCardStr } : {})
      },
      bubbles: true
    }))
  } else {
    const event = new CustomEvent('show-modify-in-list', {
      detail: {
        targetId: targetIdStr,
        target: tgt,
        diff: payload.diff,
        modifications: payload.modifications,
        plan_id: payload.plan_id,
        executed: alreadyProcessed,
        messageId: payload.messageId ?? messageId,
        before: payload.before ?? null,
        after: payload.after ?? null,
        ...(navCardStr ? { card_id: navCardStr } : {})
      },
      bubbles: true
    })
    window.dispatchEvent(event)
  }
}

/** 将本会话内仍待确认的 create 预览同步到左侧列表（无需先点沙箱卡片） */
const syncPendingCreatePreviewsToWorkbench = async () => {
  for (const msg of messages.value) {
    if (!msg || msg.isUser || !msg.modifyNavigation) continue
    const nav = msg.modifyNavigation
    if (
      nav.is_create !== true ||
      nav.navigate_to_existing ||
      nav.confirmation_required === false
    ) {
      continue
    }
    try {
      await handleShowModifyInList(nav, msg.id)
    } catch (e) {
      console.warn('[CREATE] 同步待确认新建到列表失败:', e)
    }
  }
}

// 取消修改
const handleCancelModify = () => {
  console.log('[MODIFY] 用户取消修改')
  // 清除modifyNavigation
  const currentMessage = messages.value[messages.value.length - 1]
  if (currentMessage) {
    currentMessage.modifyNavigation = null
  }
}

// 确认应用沙箱预览的修改（已废弃，现在统一跳转到左侧列表确认）
const handleConfirmModification = async (modifyData) => {
  console.log('[MODIFY] 此方法已废弃，请使用 handleShowModifyInList')
}

// 取消沙箱预览的修改
const handleCancelModification = (message) => {
  console.log('[MODIFY] 用户取消沙箱预览')
  message.modifyNavigation = null
}

// 审核单个修改项 - 采纳
const handleApproveItem = async (item) => {
  console.log('[MODIFY] 用户采纳单项修改:', item)
  // 修改已经执行，这里只是记录用户确认
  // 可以发送通知或更新UI状态
}

// 审核单个修改项 - 拒绝
const handleRejectItem = async (item) => {
  console.log('[MODIFY] 用户拒绝单项修改:', item)
  // 需要回滚该修改
  if (item.result?.before) {
    try {
      const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: `回滚修改，恢复原状态`,
          project_id: props.projectId,
          model: selectedModel.value,
          session_id: props.sessionId,
          locale: localeForApi(),
          rollback_modify: {
            target: 'bug',
            target_id: item.bug_id,
            modifications: item.result.before
          }
        })
      })
      console.log('[MODIFY] 回滚请求已发送')
    } catch (error) {
      console.error('[MODIFY] 回滚失败:', error)
    }
  }
}

// 全部采纳
const handleApproveAll = async (results) => {
  console.log('[MODIFY] 用户采纳全部修改:', results)
  // 所有修改已执行，记录确认
}

// 全部拒绝
const handleRejectAll = async (results) => {
  console.log('[MODIFY] 用户拒绝全部修改:', results)
  // 需要回滚所有修改
  for (const item of results) {
    if (item.result?.before) {
      try {
        await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_input: `回滚修改`,
            project_id: props.projectId,
            model: selectedModel.value,
            session_id: props.sessionId,
            locale: localeForApi(),
            rollback_modify: {
              target: 'bug',
              target_id: item.bug_id,
              modifications: item.result.before
            }
          })
        })
      } catch (error) {
        console.error('[MODIFY] 回滚失败:', error)
      }
    }
  }
}

// 确认创建
const handleConfirmCreate = async (createData) => {
  console.log('[CREATE] 用户确认创建:', createData)
  
  // 调用create工具，confirm=true
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_input: `确认创建${createData.target}`,
        project_id: props.projectId,
        model: selectedModel.value,
        session_id: props.sessionId,
        locale: localeForApi(),
        confirm_create: createData  // 传递create数据
      })
    })
    
    console.log('[CREATE] 创建已提交')
  } catch (error) {
    console.error('[CREATE] 创建失败:', error)
  }
}

// 取消创建
const handleCancelCreate = () => {
  console.log('[CREATE] 用户取消创建')
  // 只需记录日志，不做处理
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

/** ReAct：某步开始时把对应该步的日志滚入可视区（与顶部静态待办联动） */
const scrollAgentStepLogIntoView = (messageId, stepIndex) => {
  if (messageId == null || stepIndex == null || stepIndex < 0) return
  nextTick(() => {
    const root = messagesContainer.value
    if (!root) return
    const el = root.querySelector(`[data-message-id="${messageId}"] [data-agent-step="${stepIndex}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

/** 是否已是可用的 modify 沙箱导航（单条或批量）；勿因缺少 batch_results 就覆盖为「新建预览」 */
const isValidModifySandboxNavigation = (nav) => {
  if (!nav || typeof nav !== 'object') return false
  if (nav.is_create === true || nav.target_id === 'new' || nav.targetId === 'new') return false
  if (nav.batch_modify === true && Array.isArray(nav.batch_results) && nav.batch_results.length > 0) {
    return true
  }
  const tid = snowflakeIdStr(nav.target_id ?? nav.targetId)
  if (!tid) return false
  const hasDiff = Array.isArray(nav.diff) && nav.diff.length > 0
  const hasMods =
    nav.modifications &&
    typeof nav.modifications === 'object' &&
    Object.keys(nav.modifications).filter((k) => !String(k).startsWith('_')).length > 0
  return hasDiff || hasMods || nav.before != null || nav.after != null
}

/** execution_results 内单条 observation 是否像 modify 沙箱（有 preview 的是 create，不能仅凭 diff 误判） */
const looksLikeModifyToolObservation = (toolData) => {
  if (!toolData || typeof toolData !== 'object') return false
  if (toolData.created_id != null && toolData.created_id !== '') return false
  if (toolData.batch_modify === true) return true
  if (Array.isArray(toolData.batch_results) && toolData.batch_results.length > 0) return true
  if (Array.isArray(toolData.results) && toolData.results.length > 0) return true
  const tid = snowflakeIdStr(toolData.target_id ?? toolData.targetId)
  if (!tid || tid === 'new') return false
  const hasDiff = Array.isArray(toolData.diff) && toolData.diff.length > 0
  if (!hasDiff) return false
  if (toolData.preview && typeof toolData.preview === 'object' && Object.keys(toolData.preview).length > 0) {
    return false
  }
  return (
    toolData.before != null ||
    toolData.after != null ||
    toolData.confirmation_required === true ||
    toolData.sandbox_preview != null
  )
}

/**
 * 从流式阶段写入的 executionResults 中恢复 modify 批量预览（应因 observation 未写入 modifyNavigation 的旧消息）
 * 注意：executionResults 的 step 常为步骤标题（中文），不能要求 step === 'modify'
 */
const recoverModifyNavigationFromExecutionResults = (execRaw) => {
  if (!execRaw) return null
  let exec = execRaw
  if (typeof exec === 'string') {
    try {
      exec = JSON.parse(exec)
    } catch {
      return null
    }
  }
  if (!Array.isArray(exec)) return null

  const fromToolData = (toolData, topTarget) => {
    if (!toolData || typeof toolData !== 'object') return null
    const tgt = toolData.target || topTarget || 'badcase'
    if (looksLikeModifyToolObservation(toolData)) {
      const tid = snowflakeIdStr(toolData.target_id ?? toolData.targetId)
      if (tid && tid !== 'new') {
        return {
          target: tgt,
          target_id: tid,
          diff: Array.isArray(toolData.diff) ? toolData.diff : [],
          modifications: toolData.modifications || {},
          confirmation_required: toolData.confirmation_required !== false,
          before: toolData.before ?? null,
          after: toolData.after ?? null,
          plan_id: toolData.plan_id ?? toolData.before?.plan_id ?? null,
          success: toolData.success === true
        }
      }
    }
    if (Array.isArray(toolData.batch_results) && toolData.batch_results.length > 0) {
      return {
        batch_modify: true,
        batch_results: toolData.batch_results,
        batch_count: toolData.batch_count ?? toolData.batch_results.length,
        target: tgt
      }
    }
    if (Array.isArray(toolData.results) && toolData.results.length > 0) {
      const batch_results_flat = []
      for (const r of toolData.results) {
        const obs = r && r.result && typeof r.result === 'object' ? r.result : {}
        const tid = r?.id ?? r?.target_id ?? obs.target_id
        const tidStr = snowflakeIdStr(tid)
        if (!tidStr) continue
        batch_results_flat.push({
          target_id: tidStr,
          plan_id: r?.plan_id ?? obs.plan_id ?? null,
          target: tgt || obs.target || 'badcase',
          diff: obs.diff || [],
          modifications: obs.modifications || {},
          before: obs.before,
          after: obs.after,
          confirmation_required: obs.confirmation_required !== false,
          success: obs.success === true,
          record_title: (obs.before || {}).title,
          result: obs
        })
      }
      if (batch_results_flat.length > 0) {
        return {
          batch_modify: true,
          batch_results: batch_results_flat,
          batch_count: batch_results_flat.length,
          target: tgt
        }
      }
    }
    return null
  }

  for (const row of exec) {
    if (!row || row.text == null) continue
    let td = row.text
    if (typeof td === 'string') {
      try {
        td = JSON.parse(td)
      } catch {
        continue
      }
    }
    if (!td || typeof td !== 'object') continue
    const inner = td.data && typeof td.data === 'object' ? td.data : td
    const tryCreatePreview = (toolData, topTarget) => {
      if (!toolData || typeof toolData !== 'object') return null
      if (looksLikeModifyToolObservation(toolData)) return null
      const hasDiff = Array.isArray(toolData.diff) && toolData.diff.length > 0
      const hasPreview =
        toolData.preview &&
        typeof toolData.preview === 'object' &&
        Object.keys(toolData.preview).length > 0
      if (toolData.success === false || toolData.created_id) return null
      if (!hasPreview) return null
      const tgt = toolData.target || topTarget || 'bug'
      return {
        target: tgt,
        target_id: 'new',
        diff: hasDiff ? toolData.diff : [],
        preview: toolData.preview,
        modifications: toolData.preview || {},
        confirmation_required: toolData.confirmation_required !== false,
        is_create: true
      }
    }
    const hitModify = fromToolData(inner, td.target) || fromToolData(td, td.target)
    if (hitModify) return hitModify
    const hitCreate = tryCreatePreview(inner, td.target) || tryCreatePreview(td, td.target)
    if (hitCreate) return hitCreate
  }
  return null
}

/** 与 loadSessionMessages 内逻辑一致：用 batch_modify + batch_results 生成分组卡片 */
const rebuildModifyGroupsFromBatchNav = (modifyNav, mergeFn) => {
  if (
    !modifyNav ||
    modifyNav.batch_modify !== true ||
    !Array.isArray(modifyNav.batch_results) ||
    modifyNav.batch_results.length === 0
  ) {
    return null
  }
  const merge = typeof mergeFn === 'function' ? mergeFn : () => false
  const normalizedItems = modifyNav.batch_results
    .map((r, idx) => {
      const rawId = r?.target_id ?? r?.targetId ?? r?.id
      const tid = snowflakeIdStr(rawId)
      if (!tid) return null
      return {
        ...r,
        target_id: tid,
        batchOrder: Number.isFinite(Number(r?.batchOrder)) ? Number(r.batchOrder) : idx
      }
    })
    .filter(Boolean)
  const planGroups = {}
  normalizedItems.forEach((item) => {
    const planKey = item.plan_id != null ? String(item.plan_id) : 'unplanned'
    if (!planGroups[planKey]) planGroups[planKey] = []
    planGroups[planKey].push(item)
  })
  const rebuilt = []
  Object.entries(planGroups).forEach(([planId, items]) => {
    items.sort((a, b) => (a.batchOrder ?? 0) - (b.batchOrder ?? 0))
    let currentGroup = []
    items.forEach((item, idx) => {
      if (idx === 0) {
        currentGroup.push(item)
        return
      }
      const prev = items[idx - 1]
      if (merge(prev, item)) {
        currentGroup.push(item)
      } else {
        if (currentGroup.length > 0) {
          rebuilt.push({
            plan_id: planId === 'unplanned' ? null : parseInt(planId, 10),
            items: [...currentGroup]
          })
        }
        currentGroup = [item]
      }
    })
    if (currentGroup.length > 0) {
      rebuilt.push({
        plan_id: planId === 'unplanned' ? null : parseInt(planId, 10),
        items: [...currentGroup]
      })
    }
  })
  return rebuilt.length > 0 ? rebuilt : null
}

/** 历史会话：是否隐藏顶部「规划备忘」，与线上一致。优先读落库 agent_result.react_plan_panel_suppressed；旧数据按默认 REACT_PLAN_SSE_MIN_STEPS=3 推断（无法还原 intent need_plan_ui）。*/
const computeHistoricalReactPlanPanelSuppressed = (steps, agent) => {
  if (agent && typeof agent.react_plan_panel_suppressed === 'boolean') {
    return agent.react_plan_panel_suppressed
  }
  const n = Array.isArray(steps) ? steps.length : 0
  if (n === 0) return true
  const minSteps = 3
  return minSteps > 0 && n < minSteps
}

function scheduleIdle(fn) {
  if (typeof requestIdleCallback !== 'undefined') {
    requestIdleCallback(() => {
      void fn()
    }, { timeout: 800 })
  } else {
    setTimeout(() => {
      void fn()
    }, 0)
  }
}

/** 解析落库的 images 字段（JSON 字符串或数组）为编辑/展示用的 { data, filename }[] */
function parseStoredMessageImages(raw) {
  if (raw == null || raw === '') return []
  let parsed = raw
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return []
    try {
      parsed = JSON.parse(s)
    } catch {
      return []
    }
  }
  if (!Array.isArray(parsed)) return []
  const out = []
  for (const item of parsed) {
    if (!item || typeof item !== 'object') continue
    let data = item.data ?? item.url ?? item.base64 ?? ''
    if (typeof data !== 'string' || !data.trim()) continue
    data = data.trim()
    if (!data.startsWith('data:') && /^[A-Za-z0-9+/=\s]+$/.test(data.replace(/\s/g, '').slice(0, 80))) {
      data = `data:image/png;base64,${data.replace(/\s/g, '')}`
    }
    out.push({
      data,
      filename: item.filename || item.name || 'image.png',
    })
  }
  return out
}

/** 从 GET /api/chat-sessions/:id 单条消息转为 UI 结构（与原先 map 逻辑一致） */
function rawApiMessageToUi(msg) {
  if (msg.is_user) {
    const lm =
      msg.llm_model != null && String(msg.llm_model).trim() !== ''
        ? normalizeSavedChatModel(String(msg.llm_model))
        : null
    const histImages = parseStoredMessageImages(msg.images)
    return {
      id: msg.id,
      isUser: true,
      content: msg.content,
      time: new Date(msg.created_at).toLocaleTimeString(),
      isHistorical: true,
      llmModel: lm,
      images: histImages.length > 0 ? histImages : undefined,
    }
  }
  let modifyNav = msg.modify_navigation ? JSON.parse(msg.modify_navigation) : null
  let modifyGroups = msg.modify_groups ? JSON.parse(msg.modify_groups) : null
  if (!isValidModifySandboxNavigation(modifyNav) && msg.execution_results) {
    const recovered = recoverModifyNavigationFromExecutionResults(msg.execution_results)
    if (recovered) modifyNav = recovered
  }
  if (
    (!modifyGroups || !Array.isArray(modifyGroups) || modifyGroups.length === 0) &&
    modifyNav &&
    modifyNav.batch_modify === true &&
    Array.isArray(modifyNav.batch_results) &&
    modifyNav.batch_results.length > 0
  ) {
    try {
      const rebuilt = rebuildModifyGroupsFromBatchNav(modifyNav, shouldMergeModifyPreviewItems)
      if (rebuilt?.length) modifyGroups = rebuilt
    } catch (e) {
      console.warn('[MODIFY] 重建历史 modifyGroups 失败:', e)
    }
  }

  let _histSteps = msg.steps ? JSON.parse(msg.steps) : []
  const _histAgent = msg.agent_result ? JSON.parse(msg.agent_result) : { findings: [], recommendations: [], status: 'success' }
  let _histDirectChat = _histAgent.direct_chat_reply === true
  if (_histDirectChat && 'direct_chat_reply' in _histAgent) {
    try {
      delete _histAgent.direct_chat_reply
    } catch {
      // ignore
    }
  }
  const _histFr = String(msg.final_response || msg.content || '').trim()
  const _histNoFindings = !Array.isArray(_histAgent.findings) || _histAgent.findings.length === 0
  let _histStepsLen = Array.isArray(_histSteps) ? _histSteps.length : 0
  const _histScn =
    _histAgent.steps_count != null && _histAgent.steps_count !== ''
      ? Number(_histAgent.steps_count)
      : null
  if (
    _histAgent.status !== 'error' &&
    _histScn === 0 &&
    _histNoFindings &&
    _histStepsLen > 0
  ) {
    _histSteps = []
    _histStepsLen = 0
  }
  if (
    !_histDirectChat &&
    _histStepsLen === 0 &&
    _histNoFindings &&
    _histFr &&
    !String(_histAgent.summaryText || '').trim() &&
    (_histAgent.execution_time != null || _histAgent.thinking_time != null)
  ) {
    _histDirectChat = true
    _histAgent.execution_time = null
    _histAgent.thinking_time = null
    _histAgent.steps_count = 0
  }
  const _histPlanSteps =
    Array.isArray(_histAgent.react_plan_steps) && _histAgent.react_plan_steps.length > 0
      ? _histAgent.react_plan_steps
      : null
  const assistantLlm =
    msg.llm_model != null && String(msg.llm_model).trim() !== ''
      ? normalizeSavedChatModel(String(msg.llm_model))
      : null
  return {
    id: msg.id,
    isUser: false,
    content: msg.content,
    understanding: msg.understanding,
    reasoningContent: msg.reasoning,
    hadAgentThinkPhase: substantiveReasoning(msg.reasoning || ''),
    steps: _histSteps,
    thoughtCollapsed: true,
    reactDirectChatReply: _histDirectChat,
    reactPlanSteps: _histPlanSteps,
    reactPlanPanelSuppressed: computeHistoricalReactPlanPanelSuppressed(_histSteps, _histAgent),
    executionResults: msg.execution_results ? JSON.parse(msg.execution_results) : [],
    agentResult: _histAgent,
    evidences: msg.evidences ? JSON.parse(msg.evidences) : [],
    navigation: msg.navigation ? JSON.parse(msg.navigation) : null,
    modifyNavigation: modifyNav,
    modifyGroups: modifyGroups,
    finalResponse: _histFr || msg.final_response || '',
    time: new Date(msg.created_at).toLocaleTimeString(),
    isHistorical: true,
    llmModel: assistantLlm,
  }
}

// 加载会话消息
const loadSessionMessages = async () => {
  if (!props.sessionId) {
    console.log('[SimpleChatPanel] sessionId为null，跳过加载')
    return
  }

  console.log('[SimpleChatPanel] 开始加载会话sessionId:', props.sessionId)

  try {
    const response = await getChatSession(props.sessionId, { limit: 10 })
    if (response.data.success) {
      sessionTitleRef.value = response.data.session?.title ?? ''
      const raw = response.data.session.messages || []
      historyHasMore.value = !!response.data.session?.has_more
      historyBeforeId.value = response.data.session?.next_before_id ?? (raw?.[0]?.id ?? null)
      if (raw.length === 0) {
        messages.value = []
        scrollToBottom()
        scheduleIdle(async () => {
          try {
            await refreshPersistedPendingDiffKeys(true)
            await nextTick()
            scrollToBottom()
          } catch (e) {
            console.error('[MODIFY] 刷新 diff pending 失败', e)
          }
        })
        return
      }
      const CHUNK = 28
      const accumulated = []
      for (let i = 0; i < raw.length; i += CHUNK) {
        const slice = raw.slice(i, i + CHUNK)
        for (let j = 0; j < slice.length; j += 1) {
          accumulated.push(rawApiMessageToUi(slice[j]))
        }
        messages.value = accumulated.slice()
        await nextTick()
        if (i === 0) scrollToBottom()
      }
      for (let k = 0; k + 1 < accumulated.length; k++) {
        const u = accumulated[k]
        const a = accumulated[k + 1]
        if (u?.isUser && u.llmModel == null && a && !a.isUser && a.llmModel) u.llmModel = a.llmModel
      }
      messages.value = accumulated.slice()
      scrollToBottom()

      // 与后端 diff_review pending 对齐（沙箱是否待确认、列表黄条由 GET 结果驱动）
      scheduleIdle(async () => {
        try {
          await refreshPersistedPendingDiffKeys(true)
          await syncPendingCreatePreviewsToWorkbench()
          await nextTick()
          scrollToBottom()
          restoreInputDraftForSession()
          await resolveSessionRecoveryOnLoad()
        } catch (e) {
          console.error('[MODIFY] 刷新 diff pending 失败', e)
        }
      })
    }
  } catch (error) {
    console.error('加载会话消息失败:', error)
  }
}

const historyLoading = ref(false)
const historyHasMore = ref(false)
const historyBeforeId = ref(null)

async function loadOlderHistoryIfNeeded() {
  if (!props.sessionId) return
  if (historyLoading.value) return
  if (!historyHasMore.value) return
  const beforeId = Number(historyBeforeId.value)
  if (!Number.isFinite(beforeId) || beforeId <= 0) return
  const root = messagesContainer.value
  if (!root) return
  if (root.scrollTop > 40) return

  historyLoading.value = true
  const prevScrollHeight = root.scrollHeight
  try {
    const resp = await getChatSession(props.sessionId, { limit: 10, before_id: beforeId })
    if (resp?.data?.success) {
      const raw = resp.data.session?.messages || []
      const uiMsgs = raw.map(rawApiMessageToUi)
      if (uiMsgs.length > 0) {
        const merged = [...uiMsgs, ...messages.value]
        for (let k = 0; k + 1 < merged.length; k++) {
          const u = merged[k]
          const a = merged[k + 1]
          if (u?.isUser && u.llmModel == null && a && !a.isUser && a.llmModel) u.llmModel = a.llmModel
        }
        messages.value = merged
        historyHasMore.value = !!resp.data.session?.has_more
        historyBeforeId.value = resp.data.session?.next_before_id ?? (raw?.[0]?.id ?? historyBeforeId.value)
        await nextTick()
        // 维持滚动位置：插入前后的高度差抵消
        const nextScrollHeight = root.scrollHeight
        root.scrollTop = nextScrollHeight - prevScrollHeight + root.scrollTop
      } else {
        historyHasMore.value = false
      }
    } else {
      historyHasMore.value = false
    }
  } catch (e) {
    console.warn('[HISTORY] 加载更早消息失败:', e)
  } finally {
    historyLoading.value = false
  }
}

// 保存模型选择到 localStorage
const saveModelSelection = () => {
  localStorage.setItem('selectedChatModel', selectedModel.value)
  console.log('[MODEL] 已保存模型选择:', selectedModel.value)
}

// 切换思考过程的展开/收起状态
const toggleReasoning = (message) => {
  message.showReasoning = !message.showReasoning
}

// 与后端/列表约定对齐：统一 check API 使用的 target 名
const normalizeModifyTarget = (target) => {
  const t = (target == null ? '' : String(target)).toLowerCase().replace(/-/g, '_')
  if (t === 'test_case') return 'testcase'
  return t
}

// 沙箱是否仍「待列表确认」：pending 表命中则一定待确认；表未命中时历史消息视为已处理，实时消息回退 JSON（与 resolveAlreadyProcessedByPersisted 一致）
const isSandboxModifyItemPending = (item, message = null) => {
  if (!item || typeof item !== 'object') return false
  if (item.cancelled === true) return false
  if (
    item.is_create === true ||
    item.target_id === 'new' ||
    item.targetId === 'new'
  ) {
    if (item.confirmation_required === false) return false
    if (message?.isHistorical) return item.confirmation_required !== false
    return true
  }
  const tid = snowflakeIdStr(item.target_id ?? item.targetId ?? item.id)
  if (!tid) return false
  const tgt = normalizeModifyTarget(item.target || 'badcase')
  const pk = makePersistDiffKey(tgt, tid)
  if (persistedPendingLoaded.value && pk) {
    if (persistedPendingDiffKeys.value.has(pk)) return true
    if (message?.isHistorical) return false
    return item.confirmation_required !== false
  }
  if (item.confirmation_required === false) return false
  return true
}

/** 某一 modifyGroup 内是否仍有一条待列表确认（与 isSandboxModifyItemPending 一致） */
const groupHasPendingSandboxConfirm = (group, message) => {
  const items = group?.items
  if (!Array.isArray(items) || items.length === 0) return false
  return items.some((it) => isSandboxModifyItemPending(it, message))
}

const messageHasPendingSandboxConfirm = (message) => {
  if (!message) return false
  if (message.modifyGroups?.length) {
    return message.modifyGroups.some((g) =>
      g.items?.some((it) => isSandboxModifyItemPending(it, message))
    )
  }
  const nav = message.modifyNavigation
  if (nav && !nav.batch_modify) {
    if (nav.navigate_to_existing) return false
    return isSandboxModifyItemPending(
      {
        confirmation_required: nav.confirmation_required,
        success: nav.success,
        target_id: nav.target_id ?? nav.targetId,
        target: nav.target,
        is_create: nav.is_create === true
      },
      message
    )
  }
  if (nav?.batch_modify && nav.batch_results?.length) {
    return nav.batch_results.some((r) => isSandboxModifyItemPending(r, message))
  }
  return false
}

/** 左侧切换迭代计划时，把本会话里该计划下「未采纳」的沙箱修改同步到列表（无需先点沙箱）。同一 target_id 只派发一次，使用跨消息合并后的 diff（不同字段合并，相同字段后覆盖前）。 */
const handleRequestPendingModifyForPlan = async (event) => {
  const planId = event.detail?.planId
  const suppressAutoOpenDetail = event.detail?.suppressAutoOpenDetail === true
  const planKey = snowflakeIdStr(planId)
  if (!planKey) return
  await refreshPersistedPendingDiffKeys(true, { emitListSync: false })
  const hasBackendPendingRow = (target, targetId) => {
    if (!persistedPendingLoaded.value) return false
    const k = makePersistDiffKey(target, targetId)
    return !!(k && persistedPendingDiffKeys.value.has(k))
  }

  const seen = new Set()
  const batchItems = []
  for (const msg of messages.value) {
    if (!msg || msg.isUser) continue

    if (msg.modifyGroups?.length) {
      for (const group of msg.modifyGroups) {
        if (snowflakeIdStr(group.plan_id) !== planKey) continue
        const peerTargetIds = (group.items || [])
          .map((it) => snowflakeIdStr(it?.target_id ?? it?.targetId ?? it?.id))
          .filter((id) => !!id)
        for (const item of group.items || []) {
          const rawId = item?.target_id ?? item?.targetId ?? item?.id
          const idStr = snowflakeIdStr(rawId)
          if (!idStr) continue
          const tgt = item.target || 'badcase'
          if (item.cancelled === true) continue
          if (!hasBackendPendingRow(tgt, idStr)) continue
          const key = `${tgt}:${idStr}`
          if (seen.has(key)) continue
          seen.add(key)
          const merged = getMergedPendingForTarget(messages.value, tgt, idStr)
          if (!merged) continue
          batchItems.push({
            targetId: idStr,
            target: tgt,
            diff: merged.diff,
            modifications: merged.modifications,
            plan_id: merged.plan_id ?? group.plan_id,
            executed: false,
            messageId: merged.messageId,
            batchIndex: 0,
            peerTargetIds,
            suppressAutoOpenDetail,
            restoreHydrateOnly: suppressAutoOpenDetail === true,
            before: merged.before ?? null,
            after: merged.after ?? null
          })
        }
      }
    }

    const nav = msg.modifyNavigation
    if (!nav) continue

    if (nav.batch_modify && nav.batch_results?.length) {
      const peerTargetIds = nav.batch_results
        .map((r) => snowflakeIdStr(r?.target_id))
        .filter((id) => !!id)
      for (const result of nav.batch_results) {
        const tplPid = result.plan_id ?? nav.plan_id
        if (snowflakeIdStr(tplPid) !== planKey) continue
        const idStr = snowflakeIdStr(result.target_id)
        if (!idStr) continue
        const tgt = result.target || 'badcase'
        if (result.cancelled === true) continue
        if (!hasBackendPendingRow(tgt, idStr)) continue
        const key = `${tgt}:${idStr}`
        if (seen.has(key)) continue
        seen.add(key)
        const merged = getMergedPendingForTarget(messages.value, tgt, idStr)
        if (!merged) continue
        batchItems.push({
          targetId: idStr,
          target: tgt,
          diff: merged.diff,
          modifications: merged.modifications,
          plan_id: merged.plan_id ?? tplPid,
          executed: false,
          messageId: merged.messageId,
          batchIndex: 0,
          peerTargetIds,
          suppressAutoOpenDetail,
          restoreHydrateOnly: suppressAutoOpenDetail === true,
          before: merged.before ?? null,
          after: merged.after ?? null
        })
      }
      continue
    }

    if (nav.is_create) {
      const tplPid = nav.plan_id ?? nav.preview?.plan_id ?? nav.preview?.planId
      if (snowflakeIdStr(tplPid) !== planKey) continue
      if (nav.navigate_to_existing || nav.confirmation_required === false) continue
      try {
        await handleShowModifyInList(nav, msg.id)
      } catch (e) {
        console.warn('[CREATE] 计划切换同步新建预览失败:', e)
      }
      continue
    }

    if (!nav.batch_modify && !nav.is_create) {
      if (nav.cancelled === true) continue
      const tplPid = nav.plan_id ?? nav.preview?.plan_id ?? nav.preview?.planId
      if (snowflakeIdStr(tplPid) !== planKey) continue
      const idStr = snowflakeIdStr(nav.target_id ?? nav.targetId)
      if (!idStr) continue
      const tgt = nav.target || 'badcase'
      if (!hasBackendPendingRow(tgt, idStr)) continue
      const key = `${tgt}:${idStr}`
      if (seen.has(key)) continue
      seen.add(key)
      const merged = getMergedPendingForTarget(messages.value, tgt, idStr)
      if (!merged) continue
      batchItems.push({
        targetId: idStr,
        target: tgt,
        diff: merged.diff,
        modifications: merged.modifications,
        plan_id: merged.plan_id ?? tplPid,
        executed: false,
        messageId: merged.messageId,
        peerTargetIds: [idStr],
        suppressAutoOpenDetail,
        restoreHydrateOnly: suppressAutoOpenDetail === true,
        before: merged.before ?? null,
        after: merged.after ?? null
      })
    }
  }

  if (batchItems.length > 0) {
    window.dispatchEvent(
      new CustomEvent('show-modify-in-list', {
        detail: { __modifyListBatch: true, items: batchItems },
        bubbles: true
      })
    )
  }
}

/** 落库前 JSON.stringify：Vue reactive / 循环引用不致崩 */
const safeJsonForDb = (val, label = 'json') => {
  try {
    if (val == null) return JSON.stringify(val)
    return JSON.stringify(toRaw(val))
  } catch (e) {
    console.error(`[CHAT] ${label} 序列化失败`, e)
    return 'null'
  }
}

const newReactRunId = () => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    /* ignore */
  }
  return `react-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

/** 流式草稿由 buffer 重放即可，不必进 sessionStorage */
const REACT_RESUME_SNAPSHOT_OMIT_KEYS = new Set([
  'thinkReasoningDraft',
  'thinkContentDraft',
  'runningSummaryDraft',
  'summaryStreamDraft'
])

const snapshotReactMessageForResume = (aiMessage) => {
  if (!aiMessage) return null
  try {
    const raw = toRaw(aiMessage)
    return JSON.parse(
      JSON.stringify(raw, (k, v) => {
        if (k.startsWith('_') || REACT_RESUME_SNAPSHOT_OMIT_KEYS.has(k)) return undefined
        return v
      })
    )
  } catch {
    return null
  }
}

let lastAgentRunSnapshotTs = 0
const maybePatchAgentRunSnapshot = (projectId, sessionId, aiMessage, { force = false } = {}) => {
  if (!projectId || !sessionId || !aiMessage) return
  const now = Date.now()
  if (!force && now - lastAgentRunSnapshotTs < REACT_AGENT_RUN_SNAPSHOT_MS) return
  lastAgentRunSnapshotTs = now
  const snap = snapshotReactMessageForResume(aiMessage)
  if (snap) patchAgentRunSnapshot(projectId, sessionId, snap)
}

const flushAgentRunSnapshotOnPageHide = () => {
  if (!isSending.value && reactStreamRequestIdRef.value == null) return
  const pid = currentProjectId.value || props.projectId
  const sid = props.sessionId
  if (!pid || !sid) return
  const runMeta = getAgentRun(pid, sid)
  if (!runMeta?.runId || runMeta.status !== 'streaming') return
  let aiMessage = null
  const cid = runMeta.clientMessageId
  if (cid != null) aiMessage = findChatMessageById(cid)
  if (!aiMessage) {
    const last = messages.value[messages.value.length - 1]
    if (last && !last.isUser) aiMessage = last
  }
  if (aiMessage) maybePatchAgentRunSnapshot(pid, sid, aiMessage, { force: true })
}

const applyReactSnapshotToMessage = (aiMessage, snap) => {
  if (!aiMessage || !snap || typeof snap !== 'object') return
  const keys = [
    'understanding',
    'steps',
    'finalResponse',
    'reasoningContent',
    'thinkReasoningDraft',
    'thinkContentDraft',
    'executionResults',
    'modifyNavigation',
    'modifyGroups',
    'agentResult',
    'evidences',
    'reactPlanSteps',
    'runningSummaryDraft',
    'summaryStreamDraft',
    'reactDirectChatReply',
    'lastReactPhase'
  ]
  for (const k of keys) {
    if (snap[k] !== undefined) aiMessage[k] = snap[k]
  }
}

const buildReactSseConsumeCtx = () => ({
  scrollToBottom,
  isDebugReactThinkSSE,
  buildReactStepsFromTodoStrings,
  thinkCtx: {
    resolveStreamStepIndex,
    scheduleReasoningTypewriter,
    scheduleTodosStreamTypewriter,
    sseIsReactThinkPhase,
    logReactThinkStepDetail
  },
  engineCtx: {
    flushReasoningTypewriter,
    cancelTodosStreamTypewriter,
    buildReactStepsFromTodoStrings,
    resolveStreamStepIndex,
    appendStepDetailLine,
    scrollAgentStepLogIntoView,
    handleShowGroupInList,
    handleShowModifyInList,
    projectId: props.projectId,
    handleNavigation,
    nextTick
  }
})

const stopReactResumePoll = () => {
  if (reactResumePollTimerRef.value) {
    clearInterval(reactResumePollTimerRef.value)
    reactResumePollTimerRef.value = null
  }
}

const persistReactAssistantMessage = async (aiMessage, modelUsed) => {
  let modifyNavForSave = aiMessage.modifyNavigation
  if (!isValidModifySandboxNavigation(modifyNavForSave) && aiMessage.executionResults?.length) {
    const recovered = recoverModifyNavigationFromExecutionResults(aiMessage.executionResults)
    if (recovered) {
      modifyNavForSave = recovered
      aiMessage.modifyNavigation = recovered
    }
  }
  if (
    modifyNavForSave &&
    modifyNavForSave.batch_modify === true &&
    (!aiMessage.modifyGroups || !Array.isArray(aiMessage.modifyGroups) || aiMessage.modifyGroups.length === 0)
  ) {
    const rebuilt = rebuildModifyGroupsFromBatchNav(modifyNavForSave, shouldMergeModifyPreviewItems)
    if (rebuilt?.length) {
      aiMessage.modifyGroups = Object.freeze([...rebuilt])
      await refreshPersistedPendingDiffKeys(true, { emitListSync: false })
      for (const grp of rebuilt) {
        if (grp.items && grp.items.length > 0) {
          await handleShowGroupInList(grp, aiMessage.id, { skipPersistedRefresh: true })
        }
      }
    }
  }
  if (
    modifyNavForSave?.is_create === true &&
    modifyNavForSave.confirmation_required !== false &&
    !modifyNavForSave.navigate_to_existing
  ) {
    await syncPendingCreatePreviewsToWorkbench()
  }

  const _persistAgent = { ...(aiMessage.agentResult || {}) }
  const _persistRunning = String(aiMessage.runningSummaryDraft || '').trim()
  const _persistSummaryStream = String(aiMessage.summaryStreamDraft || '').trim()
  if (_persistRunning) _persistAgent.summaryText = _persistRunning
  else if (_persistSummaryStream) _persistAgent.summaryText = _persistSummaryStream
  if (aiMessage.reactDirectChatReply) _persistAgent.direct_chat_reply = true
  else delete _persistAgent.direct_chat_reply
  _persistAgent.react_plan_panel_suppressed = !!aiMessage.reactPlanPanelSuppressed
  if (Array.isArray(aiMessage.reactPlanSteps) && aiMessage.reactPlanSteps.length > 0) {
    _persistAgent.react_plan_steps = aiMessage.reactPlanSteps
  } else {
    try {
      delete _persistAgent.react_plan_steps
    } catch {
      /* ignore */
    }
  }
  if (aiMessage.agentResult?.status) {
    _persistAgent.status = aiMessage.agentResult.status
  }
  if (aiMessage.agentResult?.interrupt_reason) {
    _persistAgent.interrupt_reason = aiMessage.agentResult.interrupt_reason
  }

  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '处理完成',
    understanding: aiMessage.understanding,
    reasoning: aiMessage.reasoningContent || '',
    steps: safeJsonForDb(aiMessage.steps, 'steps'),
    execution_results: safeJsonForDb(aiMessage.executionResults || [], 'execution_results'),
    agent_result: safeJsonForDb(_persistAgent, 'agent_result'),
    evidences: safeJsonForDb(aiMessage.evidences || [], 'evidences'),
    navigation: safeJsonForDb(aiMessage.navigation ?? null, 'navigation'),
    modify_navigation: safeJsonForDb(aiMessage.modifyNavigation ?? null, 'modify_navigation'),
    modify_groups: safeJsonForDb(aiMessage.modifyGroups ?? null, 'modify_groups'),
    final_response: aiMessage.finalResponse,
    llm_model: modelUsed
  })
}

const findUserInputBeforeAssistant = (aiMessage) => {
  const idx = messages.value.findIndex((m) => m && String(m.id) === String(aiMessage?.id))
  for (let i = idx - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m?.isUser) return String(m.content || '').trim()
  }
  return ''
}

const fetchReactRunStatus = async (reactRequestId) => {
  const rid = (reactRequestId || '').trim()
  if (!rid) return { running: false, status: 'unknown' }
  try {
    const resp = await fetch(
      `${BACKEND_BASE_URL}/api/agent/react/run-status?request_id=${encodeURIComponent(rid)}`,
      { credentials: 'include' }
    )
    if (!resp.ok) return { running: false, status: 'unknown' }
    const data = await resp.json().catch(() => ({}))
    if (!data?.success) return { running: false, status: 'unknown' }
    return {
      running: !!(data.running || data.status === 'running'),
      status: data.status || 'unknown'
    }
  } catch {
    return { running: false, status: 'unknown' }
  }
}

/** §5.2.1：仅 SSE 续流；§5.2.2 任务延续暂缓（性能优化 + DAG 后再做） */
const resolveSessionRecoveryOnLoad = async () => {
  const pid = currentProjectId.value || props.projectId
  const sid = props.sessionId
  if (!sid || !pid || reactResumeInFlightRef.value || isSending.value) return

  const runMeta = getAgentRun(pid, sid)
  if (!runMeta?.runId || runMeta.status !== 'streaming') return

  const st = await fetchReactRunStatus(runMeta.runId)
  if (st.running) {
    await tryResumeReactStreamAfterLoad()
  } else {
    clearAgentRun(pid, sid)
  }
}

const flushDraftSaveTimer = () => {
  if (draftSaveTimer) {
    clearTimeout(draftSaveTimer)
    draftSaveTimer = null
  }
}

const scheduleDraftSave = () => {
  const pid = currentProjectId.value || props.projectId
  const sid = props.sessionId
  if (!pid || !sid) return
  flushDraftSaveTimer()
  draftSaveTimer = setTimeout(() => {
    draftSaveTimer = null
    saveDraft(pid, sid, inputMessage.value)
  }, 600)
}

/** §5.1.5：切会话时同步落盘旧草稿，再恢复新会话草稿（不等防抖） */
const onSessionIdChangeForDraft = (newId, oldId) => {
  const pid = currentProjectId.value || props.projectId
  if (!pid) return
  flushDraftSaveTimer()
  if (oldId != null && oldId !== '') {
    saveDraft(pid, oldId, inputMessage.value)
  }
  if (newId != null && newId !== '') {
    inputMessage.value = getDraft(pid, newId) || ''
    nextTick(() => autoResize())
  } else {
    inputMessage.value = ''
    nextTick(() => autoResize())
  }
}

const restoreInputDraftForSession = () => {
  const pid = currentProjectId.value || props.projectId
  const sid = props.sessionId
  if (!pid || !sid) return
  if (inputMessage.value.trim()) return
  const d = getDraft(pid, sid)
  inputMessage.value = d || ''
  nextTick(() => autoResize())
}

const formatReactStreamError = (err) => {
  const name = err?.name || ''
  const msg = String(err?.message || err || '未知错误')
  const lower = msg.toLowerCase()
  if (name === 'TypeError' && (lower.includes('failed to fetch') || lower.includes('network'))) {
    return '连接已断开'
  }
  if (lower.includes('network') || lower.includes('load failed') || name === 'NetworkError') {
    return '连接已断开'
  }
  return msg
}

// 保存消息到数据库
const saveMessageToDb = async (messageData) => {
  if (!props.sessionId) return
  
  try {
    await addChatMessage(props.sessionId, messageData)
  } catch (error) {
    console.error('保存消息失败:', error)
  }
}

const sendText = async (rawText, imagesToSend = null, sendOptions = {}) => {
  const { consumeMainPending = false, clearInlinePending = false, requestModel: requestModelOpt } = sendOptions
  const text = (rawText || '').trim()
  const images = Array.isArray(imagesToSend) ? imagesToSend : pendingImages.value
  const hasImages = images && images.length > 0
  if ((!text && !hasImages) || isSending.value) return

  const effectiveText = text || (hasImages ? '请根据这张图片描述内容并处理我的意图' : '')
  const imagesPayload = hasImages ? images.map(({ data, filename }) => ({ data, filename })) : []

  const requestModel = normalizeSavedChatModel(
    requestModelOpt != null && String(requestModelOpt).trim() !== '' ? String(requestModelOpt) : selectedModel.value
  )

  abortController.value = new AbortController()
  isSending.value = true

  try {
    if (hasImages) {
      if (consumeMainPending) clearPendingImages()
      if (clearInlinePending) inlinePendingImages.value = []
    }

    const userMessage = {
      id: Date.now(),
      content: effectiveText,
      isUser: true,
      time: new Date().toLocaleTimeString(),
      images: hasImages ? images : undefined,
      llmModel: requestModel,
    }
    messages.value.push(userMessage)

    await saveMessageToDb({
      is_user: true,
      content: userMessage.content,
      images: hasImages ? JSON.stringify(imagesPayload) : undefined,
      llm_model: requestModel,
    })

    // 默认标题（如 newchat）时根据首条/当前用户消息生成标题；后端曾因 await async chat 导致失败
    if (
      props.sessionId &&
      effectiveText.trim() &&
      isPlaceholderSessionTitle(sessionTitleRef.value) &&
      !titleGenInFlight.value
    ) {
      titleGenInFlight.value = true
      generateSessionTitle(props.sessionId, userMessage.content)
        .then((res) => {
          const data = res?.data
          if (data?.success && data?.title) {
            console.log('[CHAT] 会话标题已生成', data.title)
            sessionTitleRef.value = data.title
            emit('title-updated', data.title)
          }
        })
        .catch((err) => {
          console.error('[CHAT] 生成会话标题失败:', err)
        })
        .finally(() => {
          titleGenInFlight.value = false
        })
    }

    const messageContent = effectiveText

    nextTick(() => {
      inputMessage.value = ''
      autoResize()
    })
    const pidDraft = currentProjectId.value || props.projectId
    if (pidDraft && props.sessionId) clearDraft(pidDraft, props.sessionId)

    scrollToBottom()

    if (selectedAgent.value === 'agent' && !isElectronPtyAvailable()) {
      try {
        if (typeof pingLocalGoProxy === 'function') await pingLocalGoProxy()
      } catch (_) {
        /* ignore */
      }
      const ok = localGoProxyOk && typeof localGoProxyOk === 'object' && 'value' in localGoProxyOk ? localGoProxyOk.value : null
      agentLocalProxyHint.value = ok === false ? t('chat.agentNeedsLocalProxy') : ''
    } else {
      agentLocalProxyHint.value = ''
    }

    // Agent 模式一律走后端 /api/agent/react，由后端统一做意图识别与分流
    if (selectedAgent.value === 'agent') {
      await handleReactAgentMode(messageContent, imagesPayload, {
        model: requestModel
      })
    } else {
      await handleChatMode(messageContent, imagesPayload, { model: requestModel })
    }
  } catch (e) {
    console.error('[CHAT] sendText 流程异常:', e)
  } finally {
    // 避免 ReAct/聊天抛错或中断后 isSending 未复位，导致发送键一直不可用
    isSending.value = false
    abortController.value = null
    reactSseReaderRef.value = null
  }
}

const handleSend = async (e) => {
  e?.preventDefault()
  if (isComposing.value) return
  // 续流或上一轮 SSE 未复位时 isSending=true，发送钮会变成停止钮且 sendText 直接 return
  if (isSending.value) {
    handleStop()
    stopReactResumePoll()
    reactResumeInFlightRef.value = false
    await nextTick()
  }
  const text = inputMessage.value
  const imgs = [...pendingImages.value]
  await sendText(text, imgs, { consumeMainPending: true })
}

const beginEditUserMessage = (msg) => {
  if (!msg) return
  editingUserMessageId.value = msg.id
  inlineInputMessage.value = msg.content || ''
  inlinePendingImages.value = parseStoredMessageImages(msg.images)
  const idx = messages.value.findIndex((m) => m && String(m.id) === String(msg.id))
  const fromMsg =
    msg.llmModel != null && String(msg.llmModel).trim() !== ''
      ? normalizeSavedChatModel(String(msg.llmModel))
      : msg.llm_model != null && String(msg.llm_model).trim() !== ''
        ? normalizeSavedChatModel(String(msg.llm_model))
        : null
  const inferred = fromMsg ?? (idx >= 0 ? inferUserLlmModelFromFollowingAssistant(messages.value, idx) : null)
  inlineEditSelectedModel.value = normalizeSavedChatModel(inferred ?? selectedModel.value)
  nextTick(() => {
    try {
      unwrapTextareaEl(inlineTextareaRef.value)?.focus?.()
    } catch (e) {}
  })
}

/** 推迟到宏任务：在 pointerdown 里同步切换 v-if 会拆掉当前事件目标，Vue unmount 可能读到 parentNode===null */
const scheduleBeginEditUserMessage = (msg) => {
  if (!msg) return
  setTimeout(() => beginEditUserMessage(msg), 0)
}

/** pointerdown 触发编辑；缩略图排除；必须异步进入编辑态（见 scheduleBeginEditUserMessage） */
const onUserBubblePointerDown = (e, msg) => {
  if (!e || e.button !== 0) return
  const t = e.target
  if (t && typeof t.closest === 'function' && t.closest('.user-msg-thumb')) return
  scheduleBeginEditUserMessage(msg)
}

const cancelEditUserMessage = () => {
  editingUserMessageId.value = null
  inlineInputMessage.value = ''
  inlinePendingImages.value = []
}

/** 内联发送前：把编辑内容写回气泡并退出编辑态，避免 isSending 期间仍挂着空 textarea */
const finishInlineEditBeforeSend = (text, imgs) => {
  const editId = editingUserMessageId.value
  if (editId != null) {
    const idx = messages.value.findIndex((m) => m && String(m.id) === String(editId))
    if (idx >= 0) {
      const m = messages.value[idx]
      const trimmed = (text || '').trim()
      if (trimmed) m.content = trimmed
      if (imgs && imgs.length > 0) {
        m.images = imgs.map(({ data, filename }) => ({ data, filename }))
      } else {
        m.images = undefined
      }
    }
  }
  editingUserMessageId.value = null
  inlineInputMessage.value = ''
  inlinePendingImages.value = []
}

const handleInlineSend = async (e) => {
  e?.preventDefault()
  if (isComposing.value) return
  const text = inlineInputMessage.value
  const imgs = [...inlinePendingImages.value]
  const trimmed = (text || '').trim()
  if (!trimmed && imgs.length === 0) return
  finishInlineEditBeforeSend(text, imgs)
  await nextTick()
  await sendText(text, imgs, { clearInlinePending: true, requestModel: inlineEditSelectedModel.value })
}

const addNewLineInline = (e) => {
  // 保持 textarea 默认换行行为
  // 这里无需阻止默认
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  window.addEventListener('diff-review-push', onDiffReviewPushForChat)
})

/** F5 / 断线后：从 bcd:ss:agent + 后端 SSE 缓冲续流（仅由 resolveSessionRecoveryOnLoad P1 触发） */
const tryResumeReactStreamAfterLoad = async () => {
  const pid = currentProjectId.value || props.projectId
  const sid = props.sessionId
  if (!pid || !sid || reactResumeInFlightRef.value || isSending.value) return

  const runMeta = getAgentRun(pid, sid)
  if (!runMeta?.runId || runMeta.status !== 'streaming') return

  let stResp
  try {
    stResp = await fetch(
      `${BACKEND_BASE_URL}/api/agent/react/run-status?request_id=${encodeURIComponent(runMeta.runId)}`,
      { credentials: 'include' }
    )
  } catch {
    return
  }
  if (!stResp.ok) return
  const stJson = await stResp.json().catch(() => ({}))
  if (!stJson?.success) return
  if (!stJson.running && stJson.status !== 'running') {
    clearAgentRun(pid, sid)
    return
  }

  reactResumeInFlightRef.value = true
  isSending.value = true
  stopReactResumePoll()

  let resumeFailed = false
  let aiMessage = null
  const cid = runMeta.clientMessageId
  if (cid != null) {
    aiMessage = findChatMessageById(cid)
  }
  if (!aiMessage) {
    const last = messages.value[messages.value.length - 1]
    if (last && !last.isUser && last.agentResult?.status === 'running') {
      aiMessage = last
    }
  }
  if (!aiMessage) {
    aiMessage = reactive(createReactAiMessageState(runMeta.clientMessageId || Date.now() + 1))
    if (runMeta.uiSnapshot) applyReactSnapshotToMessage(aiMessage, runMeta.uiSnapshot)
    messages.value.push(aiMessage)
    scrollToBottom()
  } else if (runMeta.uiSnapshot) {
    applyReactSnapshotToMessage(aiMessage, runMeta.uiSnapshot)
  }

  reactStreamRequestIdRef.value = runMeta.runId
  let sinceSeq = Number(runMeta.lastSeq) || 0
  const modelUsed = runMeta.llmModel || selectedModel.value
  const sseCtx = buildReactSseConsumeCtx()
  const uiPaintResume = createSseUiPaintScheduler(nextTick, { minIntervalMs: REACT_SSE_PAINT_MIN_MS })
  let finished = false

  const pollOnce = async () => {
    if (finished) return
    try {
      const resp = await fetch(
        `${BACKEND_BASE_URL}/api/agent/react/buffer?request_id=${encodeURIComponent(runMeta.runId)}&since_seq=${sinceSeq}`,
        { credentials: 'include' }
      )
      if (!resp.ok) return
      const data = await resp.json().catch(() => ({}))
      if (!data?.success) return
      const events = Array.isArray(data.events) ? data.events : []
      let maxSeq = sinceSeq
      let needsImmediatePaint = false
      for (const chunk of events) {
        try {
          const seq = Number(chunk?.seq)
          if (Number.isFinite(seq) && seq > maxSeq) maxSeq = seq
          consumeAgentSseV1Chunk(chunk, aiMessage, sseCtx)
          if (sseChunkNeedsImmediatePaint(chunk)) needsImmediatePaint = true
        } catch (e) {
          console.error('[CHAT-RESUME] chunk:', e)
        }
      }
      sinceSeq = maxSeq
      if (events.length > 0) {
        if (needsImmediatePaint) await uiPaintResume.flushNow()
        else uiPaintResume.schedule()
        await uiPaintResume.drain()
        patchAgentRunSeq(pid, sid, {
          runId: runMeta.runId,
          status: 'streaming',
          clientMessageId: aiMessage.id,
          lastSeq: sinceSeq,
          llmModel: modelUsed
        })
        maybePatchAgentRunSnapshot(pid, sid, aiMessage)
      }

      const run = data.run || {}
      if (!run.running && run.status !== 'running') {
        finished = true
        stopReactResumePoll()
        flushReasoningTypewriter(aiMessage)
        reconcileReactMessageAfterSseClose(aiMessage)
        await uiPaintResume.flushNow()
        await persistReactAssistantMessage(aiMessage, modelUsed)
        clearAgentRun(pid, sid)
        reactStreamRequestIdRef.value = null
        isSending.value = false
        reactResumeInFlightRef.value = false
        uiPaintResume.dispose()
        scrollToBottom()
      }
    } catch (e) {
      console.warn('[CHAT-RESUME] poll failed', e)
    }
  }

  try {
    await pollOnce()
    reactResumePollTimerRef.value = setInterval(() => {
      void pollOnce()
    }, REACT_RESUME_POLL_MS)

    const staleMs = Date.now() - (runMeta.updatedAt || runMeta.startedAt || 0)
    if (staleMs > AGENT_RUN_STALE_MS * 3) {
      patchAgentRunSeq(pid, sid, { status: 'stale', runId: runMeta.runId })
      stopReactResumePoll()
      isSending.value = false
      reactResumeInFlightRef.value = false
      uiPaintResume.dispose()
    }
  } catch (e) {
    resumeFailed = true
    console.warn('[CHAT-RESUME] aborted', e)
    stopReactResumePoll()
    isSending.value = false
    reactResumeInFlightRef.value = false
    clearAgentRun(pid, sid)
    uiPaintResume.dispose()
  }
  if (resumeFailed) return
  /** 续流结束由 pollOnce 内 finished 分支 dispose；此处仅兜底 */
}

// 停止生成
const handleStop = () => {
  const rid = reactStreamRequestIdRef.value
  if (rid) {
    void fetch(`${BACKEND_BASE_URL}/api/agent/react/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ request_id: rid })
    }).catch(() => {})
    reactStreamRequestIdRef.value = null
  }
  // 先把 UI 状态收敛（即使网络层 abort 还没抛异常）
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg && !lastMsg.isUser) {
    finalizeRunningMessage(lastMsg, 'stopped')
  }

  const rd = reactSseReaderRef.value
  if (rd) {
    try {
      rd.cancel('user_stop')
    } catch (e) {
      /* release read lock */
    }
    reactSseReaderRef.value = null
  }
  if (abortController.value) {
    try {
      abortController.value.abort()
    } catch (e) {}
    abortController.value = null
  }
  isSending.value = false
  const pid = currentProjectId.value || props.projectId
  if (pid && props.sessionId) {
    patchAgentRunSeq(pid, props.sessionId, { status: 'cancelled', runId: rid || undefined })
  }
  stopReactResumePoll()
}

// ReAct Agent 模式 - 调用后端 ReAct 接口 (流式处理)
const handleReactAgentMode = async (userMessage, images = [], opts = {}) => {
  const modelUsed = normalizeSavedChatModel(opts?.model ?? selectedModel.value)
  console.log('[MODEL-DEBUG] 当前选择的模型', modelUsed)
  
  const aiMessage = reactive(createReactAiMessageState(Date.now() + 1))
  
  messages.value.push(aiMessage)
  scrollToBottom()

  const reactRunId = newReactRunId()
  const pid = currentProjectId.value || props.projectId
  if (pid && props.sessionId) {
    patchAgentRunSeq(pid, props.sessionId, {
      runId: reactRunId,
      status: 'streaming',
      clientMessageId: aiMessage.id,
      lastSeq: 0,
      llmModel: modelUsed,
      startedAt: Date.now()
    })
    patchAgentRunSnapshot(pid, props.sessionId, null)
    lastAgentRunSnapshotTs = 0
  }
  let lastAgentRunPatchTs = 0
  let streamLastSeq = 0

  const stopSignal = abortController.value?.signal
  reactSseReaderRef.value = null
  reactStreamRequestIdRef.value = reactRunId
  
  try {
    console.log(`[CHAT-REACT] 调用 ReAct Agent 接口 (流式): ${userMessage}`)
    console.log('[MODEL-DEBUG] 请求参数 model:', modelUsed)
    const response = await fetch(`${BACKEND_BASE_URL}/api/agent/react`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      signal: stopSignal,
      body: JSON.stringify({
        user_input: userMessage,
        model: modelUsed,
        stream: true,
        project_id: currentProjectId.value || props.projectId,
        images: images || [],
        locale: localeForApi(),
        ...(String(props.projectDisplayName || '').trim()
          ? { project_display_name: String(props.projectDisplayName).trim() }
          : {}),
        ...(props.planId != null && String(props.planId).trim() !== ''
          ? { plan_id: String(props.planId).trim() }
          : {}),
        request_id: reactRunId,
        ...(props.sessionId ? { chat_session_id: String(props.sessionId) } : {}),
        ...longMemoryContextForReact(),
        ...agentUiContextForReact()
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const reader = response.body.getReader()
    reactSseReaderRef.value = reader
    const decoder = new TextDecoder()
    let buffer = ''

    const sseV1ConsumeCtx = buildReactSseConsumeCtx()
    const uiPaint = createSseUiPaintScheduler(nextTick, { minIntervalMs: REACT_SSE_PAINT_MIN_MS })

    try {
      while (true) {
        if (stopSignal?.aborted) break
        const { value, done } = await reader.read()
        if (done) break

        const chunkText = decoder.decode(value, { stream: true })
        const folded = foldAgentSseText(buffer, chunkText)
        buffer = folded.nextBuffer

        let maxSeq = 0
        let breakLoop = false
        let needsImmediatePaint = false
        for (const chunk of folded.chunks) {
          try {
            if (chunk && chunk.request_id) {
              reactStreamRequestIdRef.value = String(chunk.request_id)
            }
            const r = consumeAgentSseV1Chunk(chunk, aiMessage, sseV1ConsumeCtx)
            if (r && r.breakChunkLoop) {
              breakLoop = true
              break
            }
            const seq = Number(chunk?.seq)
            if (Number.isFinite(seq) && seq > maxSeq) maxSeq = seq
            if (sseChunkNeedsImmediatePaint(chunk)) needsImmediatePaint = true
          } catch (e) {
            console.error('[CHAT-STREAM] 解析失败:', e, chunk)
          }
        }
        if (maxSeq > streamLastSeq) streamLastSeq = maxSeq
        if (needsImmediatePaint) {
          await uiPaint.flushNow()
        } else if (folded.chunks.length > 0) {
          uiPaint.schedule()
        }
        const now = Date.now()
        if (
          pid &&
          props.sessionId &&
          streamLastSeq > 0 &&
          now - lastAgentRunPatchTs > REACT_STREAM_PATCH_SEQ_MS
        ) {
          lastAgentRunPatchTs = now
          patchAgentRunSeq(pid, props.sessionId, {
            runId: reactStreamRequestIdRef.value || reactRunId,
            status: 'streaming',
            clientMessageId: aiMessage.id,
            lastSeq: streamLastSeq,
            llmModel: modelUsed
          })
          maybePatchAgentRunSnapshot(pid, props.sessionId, aiMessage)
        }
        if (breakLoop) break
      }
    } finally {
      reactSseReaderRef.value = null
      reactStreamRequestIdRef.value = null
    }
    flushReasoningTypewriter(aiMessage)
    reconcileReactMessageAfterSseClose(aiMessage)
    await uiPaint.flushNow()
    uiPaint.dispose()
  } catch (error) {
    console.error('ReAct 执行失败:', error)
    // 如果用户已点过停止（我们已在 handleStop 里收敛 UI），这里不要再覆盖成错误
    if (aiMessage?.agentResult?.status === 'cancelled') {
      // noop
    } else {
      const msg = String(error?.message || error || '')
      const msgLower = msg.toLowerCase()
      const aborted =
        stopSignal?.aborted ||
        error?.name === 'AbortError' ||
        msgLower.includes('aborted') ||
        msgLower.includes('bodystreambuffer')

      if (aborted) {
        finalizeRunningMessage(aiMessage, 'stopped')
      } else {
        finalizeRunningMessage(aiMessage, 'failed')
        const short = formatReactStreamError(error)
        // 纯连接断开：预览沙箱不依赖 SSE，不必在底部再刷一大段说明
        aiMessage.finalResponse = short === '连接已断开' ? '' : `错误: ${short}`
      }
    }
  }

  if (pid && props.sessionId) {
    clearAgentRun(pid, props.sessionId)
  }
  if (
    aiMessage?.agentResult?.status !== 'cancelled' &&
    aiMessage?.agentResult?.status !== 'failed'
  ) {
    await persistReactAssistantMessage(aiMessage, modelUsed)
  }
}

// Agent 模式 - 调用后端 Agent 接口
const handleAgentMode = async (userMessage) => {
  const aiMessage = {
    id: Date.now() + 1,
    isUser: false,
    time: new Date().toLocaleTimeString(),
    understanding: '...',
    steps: [],
    finalResponse: '',
    agentResult: null
  }
  
  messages.value.push(aiMessage)
  scrollToBottom()
  
  try {
    // 调用后端 Agent 接口
    console.log(`[CHAT-EXECUTE] 正在调用 /api/agent/execute 接口: ${userMessage}`)
    // 使用 fetch 调用 /api/agent/execute（不使用 ReAct）
    const response = await fetch(`${BACKEND_BASE_URL}/api/agent/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_input: userMessage,
        model: selectedModel.value,
        project_id: currentProjectId.value || props.projectId,  // 传入项目ID
        conversation_history: messages.value.map(m => ({
          role: m.isUser ? 'user' : 'assistant',
          content: m.content || m.finalResponse || m.understanding
        })),
        agent_mode: 'auto',
        locale: localeForApi()
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const data = await response.json()
    
    if (data.code === 200) {
      const resultData = data.data
      
      // 更新 AI 理解
      aiMessage.understanding = `已识别【${resultData.detected_agent}】【意图：${resultData.detected_intent}】`
      
      // 添加执行步骤
      if (resultData.result && resultData.result.data) {
        aiMessage.steps = [
          {
            title: `${resultData.detected_agent} - ${resultData.detected_intent}`,
            description: `执行步骤: ${resultData.result.data.steps_executed || 0}`,
            status: 'completed'
          }
        ]
      }
      
      // 保存 Agent 结果
      aiMessage.agentResult = resultData.result && resultData.result.data ? resultData.result.data : null
      
      // 设置最终回复
      if (resultData.result && resultData.result.data && resultData.result.data.bugs_found && resultData.result.data.bugs_found.length > 0) {
        aiMessage.finalResponse = `已发现 ${resultData.result.data.bugs_found.length} 个 Bug，点击下方「保存 Bug」按钮可保存到数据库`
      } else if (resultData.result && resultData.result.message) {
        aiMessage.finalResponse = resultData.result.message
      } else if (resultData.result && resultData.result.data) {
        aiMessage.finalResponse = `测试执行并分析完成。执行耗时: ${resultData.result.data.execution_duration?.toFixed(2)}s`
      } else {
        aiMessage.finalResponse = '已接收你的输入，正在处理...'
      }
      
      scrollToBottom()
    } else {
      aiMessage.finalResponse = `错误: ${data.message}`
    }
  } catch (error) {
    console.error('[CHAT-EXECUTE] Agent 执行失败:', error)
    aiMessage.finalResponse = `错误: ${error.message || '未知错误'}`
  }
  
  // 保存 AI 消息到数据库
  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '正在处理...', // 可按需补全落库字段
    understanding: aiMessage.understanding,
    steps: JSON.stringify(aiMessage.steps),
    final_response: aiMessage.finalResponse,
    llm_model: selectedModel.value,
  })
  
  scrollToBottom()
}

const handleChatMode = async (userMessage, images = [], opts = {}) => {
  const modelUsed = normalizeSavedChatModel(opts?.model ?? selectedModel.value)
  const aiMessage = {
    id: Date.now() + 1,
    isUser: false,
    content: '',
    time: new Date().toLocaleTimeString(),
    understanding: '...',
    steps: [],
    finalResponse: ''
  }
  
  messages.value.push(aiMessage)
  scrollToBottom()

  const chatStopSignal = abortController.value?.signal
  reactSseReaderRef.value = null
  
  try {
    console.log(`[CHAT] 调用聊天接口 (流式): ${userMessage}`)
    const response = await fetch(`${BACKEND_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      signal: chatStopSignal,
      body: JSON.stringify({
        inputMessage: userMessage,
        model: modelUsed,
        images: images || [],
        locale: localeForApi(),
        projectId: currentProjectId.value || props.projectId || null,
        ...(props.sessionId ? { sessionId: String(props.sessionId) } : {}),
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const reader = response.body.getReader()
    reactSseReaderRef.value = reader
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        if (chatStopSignal?.aborted) break
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          try {
            const jsonStr = line.replace('data: ', '').trim()
            if (!jsonStr) continue
            const chunk = JSON.parse(jsonStr)

            if (chunk.type === 'start') {
              aiMessage.understanding = '...'
            } else if (chunk.type === 'chunk') {
              if (aiMessage.understanding === '...') {
                aiMessage.understanding = ''
              }
              aiMessage.finalResponse += chunk.content
            } else if (chunk.type === 'agent_start') {
              aiMessage.understanding = '...'
            } else if (chunk.type === 'result') {
              const result = chunk.data
              if (result.message) {
                aiMessage.finalResponse += `\n\n【Agent 结果】 ${result.message}`
              }
              if (result.data && typeof result.data === 'object') {
                aiMessage.steps.push({
                  title: 'Agent 执行结果',
                  description: '详细数据已记录',
                  status: 'completed',
                  toolCall: { name: 'AgentResult', output: JSON.stringify(result.data, null, 2) }
                })
              }
            } else if (chunk.type === 'error') {
              aiMessage.finalResponse += `\n\n【错误】 ${chunk.message}`
            }

            scrollToBottom()
          } catch (e) {
            console.warn('解析聊天流数据失败', e, line)
          }
        }
      }
    } finally {
      reactSseReaderRef.value = null
    }
  } catch (error) {
    console.error('聊天执行失败:', error)
    const msg = String(error?.message || error || '')
    const aborted =
      chatStopSignal?.aborted ||
      error?.name === 'AbortError' ||
      msg.toLowerCase().includes('aborted')
    if (aborted) {
      finalizeRunningMessage(aiMessage, 'stopped')
    } else {
      aiMessage.finalResponse = `错误: ${error.message || '未知错误'}`
    }
  }
  
  // 保存到数据库
  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '处理完成',
    understanding: aiMessage.understanding,
    steps: JSON.stringify(aiMessage.steps),
    final_response: aiMessage.finalResponse,
    llm_model: modelUsed,
  })
}

// 延迟函数
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// 保存 Bug
const handleSaveBugs = async (agentResult) => {
  try {
    // 需要于整个应用中获取 projectId
    // 暂时使用模拟 projectId
    const projectId = currentProjectId.value || props.projectId || 1
    
    if (!projectId) {
      alert('没有项目信息，不能保存 Bug')
      return
    }
    
    const bugsToSave = agentResult.bugs_found.map(bug => ({
      title: bug.title,
      severity: bug.severity || 'medium',
      priority: bug.priority || 'medium',
      steps_to_reproduce: bug.steps_to_reproduce || '',
      expected: bug.expected || '',
      actual: bug.actual || '',
      source: 'agent_test'
    }))
    
    console.log('[CHAT] 正在保存 Bug...', bugsToSave)
    
    const response = await saveAgentBugs({
      project_id: projectId,
      bugs: bugsToSave
    })
    
    if (response.data.code === 200) {
      alert(`成功保存 ${response.data.data.saved_count} 个 Bug`)
      console.log('Bug ID:', response.data.data.bug_ids)
    } else {
      alert(`保存失败: ${response.data.message}`)
    }
  } catch (error) {
    console.error('Bug 保存失败:', error)
    alert(`错误: ${error.message}`)
  }
}
const addNewLine = (e) => {
  e.preventDefault()
  inputMessage.value += '\n'
  autoResize()
}

// 自动调整 textarea 高度
const autoResize = () => {
  const textarea = unwrapTextareaEl(textareaRef.value)
  if (textarea?.style) {
    textarea.style.height = 'auto'
    const scrollHeight = textarea.scrollHeight
    // 最小高度 60px（约 3 行），最大高度 300px（约 15 行）
    const newHeight = Math.min(Math.max(scrollHeight, 60), 300)
    textarea.style.height = newHeight + 'px'
    // 当内容超过最大高度时，启用滚动条
    textarea.style.overflowY = scrollHeight > 300 ? 'auto' : 'hidden'
  }
}

// 自动调整 inline textarea 高度
const autoResizeInline = () => {
  const textarea = unwrapTextareaEl(inlineTextareaRef.value)
  if (textarea?.style) {
    textarea.style.height = 'auto'
    const scrollHeight = textarea.scrollHeight
    // 最小高度 60px（约 3 行），最大高度 300px（约 15 行）
    const newHeight = Math.min(Math.max(scrollHeight, 60), 300)
    textarea.style.height = newHeight + 'px'
    // 当内容超过最大高度时，启用滚动条
    textarea.style.overflowY = scrollHeight > 300 ? 'auto' : 'hidden'
  }
}

const chatComposerPreset = inject('chatComposerPreset', null)
watch(
  () => chatComposerPreset?.value?.token ?? 0,
  async (tok) => {
    if (!tok || !chatComposerPreset?.value?.text) return
    inputMessage.value = String(chatComposerPreset.value.text)
    await nextTick()
    textareaRef.value?.focus?.()
    autoResize()
  }
)

watch(inputMessage, () => {
  scheduleDraftSave()
})

watch(() => props.sessionId, onSessionIdChangeForDraft)

const _normAdoptTargetType = (t) =>
  String(t || 'bug')
    .toLowerCase()
    .replace(/-/g, '_')

const navRecordIdMatchesAdoptTarget = (item, targetNorm, want) => {
  if (!item || typeof item !== 'object') return false
  const tt = _normAdoptTargetType(item.target || 'bug')
  if (tt !== targetNorm) return false
  let rid = item.record_id
  if (rid == null) {
    if (targetNorm === 'bug') rid = item.bug_id
    else if (targetNorm === 'badcase' || targetNorm === 'testcase') rid = item.source_id
    else if (targetNorm === 'card') rid = item.card_id ?? item.id
  }
  return rid != null && snowflakeIdStr(rid) === want
}

const patchGrepNavItemsForAdoptTitle = (items, targetNorm, want, newTitle) => {
  if (!Array.isArray(items) || !newTitle) return false
  let changed = false
  for (const it of items) {
    if (!navRecordIdMatchesAdoptTarget(it, targetNorm, want)) continue
    it.title = newTitle
    if (targetNorm === 'bug') it.bug_title = newTitle
    changed = true
  }
  return changed
}

const patchExecutionResultsTitlesForAdopt = (obj, targetNorm, want, newTitle) => {
  if (!newTitle) return false
  let changed = false
  if (Array.isArray(obj)) {
    for (const x of obj) {
      if (patchExecutionResultsTitlesForAdopt(x, targetNorm, want, newTitle)) changed = true
    }
    return changed
  }
  if (obj && typeof obj === 'object') {
    const tid = obj.target_id != null ? obj.target_id : obj.targetId
    if (tid != null && snowflakeIdStr(tid) === want) {
      const ot = _normAdoptTargetType(obj.target || '')
      if (!ot || ot === targetNorm || (targetNorm === 'bug' && ot === 'bug')) {
        for (const side of ['before', 'after']) {
          const sub = obj[side]
          if (sub && typeof sub === 'object' && 'title' in sub) {
            sub.title = newTitle
            changed = true
          }
        }
      }
    }
    for (const v of Object.values(obj)) {
      if (patchExecutionResultsTitlesForAdopt(v, targetNorm, want, newTitle)) changed = true
    }
  }
  return changed
}

/** 列表采纳改标题后：同步本条助手消息里的「定位结果」grep 文案与沙箱/执行结果里的 before.after.title，避免刷新前 UI 陈旧 */
const patchMessageLocateTitlesAfterAdopt = (msg, want, targetType, newTitle) => {
  const nt = String(newTitle || '').trim()
  if (!nt || !want) return false
  const tn = _normAdoptTargetType(targetType)
  let touched = false
  const nav = msg.navigation
  if (nav && nav.type === 'multiple' && Array.isArray(nav.items)) {
    if (patchGrepNavItemsForAdoptTitle(nav.items, tn, want, nt)) touched = true
  }
  const steps = msg.steps
  if (Array.isArray(steps)) {
    for (const s of steps) {
      const gn = s && s.grepNavigation
      if (gn && gn.type === 'multiple' && Array.isArray(gn.items)) {
        if (patchGrepNavItemsForAdoptTitle(gn.items, tn, want, nt)) touched = true
      }
    }
  }
  const er = msg.executionResults
  if (er != null && patchExecutionResultsTitlesForAdopt(er, tn, want, nt)) touched = true

  const patchModifyShape = (navObj) => {
    if (!navObj || snowflakeIdStr(navObj.target_id ?? navObj.targetId) !== want) return
    for (const side of ['before', 'after']) {
      const sub = navObj[side]
      if (sub && typeof sub === 'object' && 'title' in sub) {
        sub.title = nt
        touched = true
      }
    }
  }
  const mn = msg.modifyNavigation
  if (mn) {
    if (mn.batch_modify && Array.isArray(mn.batch_results)) {
      for (const br of mn.batch_results) patchModifyShape(br)
    } else {
      patchModifyShape(mn)
    }
  }
  if (msg.modifyGroups && Array.isArray(msg.modifyGroups)) {
    for (const g of msg.modifyGroups) {
      const items = g && g.items
      if (!Array.isArray(items)) continue
      for (const it of items) {
        patchModifyShape(it)
      }
    }
  }
  return touched
}

const onChatTempCardProposal = (event) => {
  const d = event?.detail || {}
  if (!d.scopeKey) return
  const ix = tempCardProposals.value.findIndex((p) => p.scopeKey === d.scopeKey)
  const entry = { ...d }
  if (ix >= 0) {
    const next = [...tempCardProposals.value]
    next[ix] = entry
    tempCardProposals.value = next
  } else {
    tempCardProposals.value = [...tempCardProposals.value, entry]
  }
}

const dismissTempCardProposal = (scopeKey) => {
  tempCardProposals.value = tempCardProposals.value.filter((p) => p.scopeKey !== scopeKey)
}

const isCreateAwaitingTempCard = (messageId) => {
  if (messageId == null || messageId === undefined) return false
  return createAwaitingTempCardMessageIds.value.includes(String(messageId))
}

const tempCardProposalForMessage = (messageId) => {
  if (messageId == null || messageId === undefined) return null
  const id = String(messageId)
  return tempCardProposals.value.find((p) => p.messageId != null && String(p.messageId) === id) ?? null
}

const onCreateAwaitingTempCard = (event) => {
  const { messageId, active } = event?.detail || {}
  if (messageId == null || messageId === undefined) return
  const id = String(messageId)
  let arr = [...createAwaitingTempCardMessageIds.value]
  if (active) {
    if (!arr.includes(id)) arr.push(id)
  } else {
    arr = arr.filter((x) => x !== id)
  }
  createAwaitingTempCardMessageIds.value = arr
}

const approveTempCardProposal = (p) => {
  window.dispatchEvent(
    new CustomEvent('temp-card-approve', { detail: { scopeKey: p.scopeKey }, bubbles: true })
  )
  dismissTempCardProposal(p.scopeKey)
}

const rejectTempCardProposal = (p) => {
  window.dispatchEvent(
    new CustomEvent('temp-card-reject', { detail: { scopeKey: p.scopeKey }, bubbles: true })
  )
  dismissTempCardProposal(p.scopeKey)
}

onMounted(() => {
  void loadChatModelsFromApi()
  scrollToBottom()
  // 初始化textarea高度
  nextTick(() => {
    autoResize()
  })
  // 加载会话消息
  loadSessionMessages()
  
  // 监听修改取消/确认事件
  window.addEventListener('modify-cancelled', handleModifyCancelled)
  window.addEventListener('modify-confirmed', handleModifyConfirmed)
  window.addEventListener('request-pending-modify-for-plan', handleRequestPendingModifyForPlan)
  window.addEventListener('chat-temp-card-proposal', onChatTempCardProposal)
  window.addEventListener('create-awaiting-temp-card', onCreateAwaitingTempCard)
  window.addEventListener('pagehide', flushAgentRunSnapshotOnPageHide)

  // 历史消息：滚动到顶部时按需加载更早内容（先出最新一屏）
  nextTick(() => {
    const root = messagesContainer.value
    if (!root) return
    root.addEventListener('scroll', loadOlderHistoryIfNeeded, { passive: true })
  })
})

// 处理修改取消事件
const handleModifyCancelled = (event) => {
  const { targetId } = event.detail
  const want = snowflakeIdStr(targetId)
  console.log('[MODIFY] 收到取消事件，targetId:', want)
  if (!want) return

  // 与确认事件保持一致：同步标记 modifyGroups / batch_results / modifyNavigation
  messages.value.forEach((msg, msgIdx) => {
    let updated = false

    if (msg.modifyGroups && Array.isArray(msg.modifyGroups)) {
      msg.modifyGroups.forEach((group) => {
        if (!group.items || !Array.isArray(group.items)) return
        const itemIdx = group.items.findIndex(
          (i) => snowflakeIdStr(i.target_id ?? i.targetId ?? i.id) === want
        )
        if (itemIdx !== -1) {
          const newItem = {
            ...group.items[itemIdx],
            cancelled: true,
            confirmation_required: false,
            success: true
          }
          group.items.splice(itemIdx, 1, newItem)
          updated = true
        }
      })
    }

    if (msg.modifyNavigation) {
      if (msg.modifyNavigation.batch_modify && Array.isArray(msg.modifyNavigation.batch_results)) {
        const resultIdx = msg.modifyNavigation.batch_results.findIndex(
          (r) => snowflakeIdStr(r.target_id ?? r.targetId ?? r.id) === want
        )
        if (resultIdx !== -1) {
          msg.modifyNavigation.batch_results.splice(resultIdx, 1, {
            ...msg.modifyNavigation.batch_results[resultIdx],
            cancelled: true,
            confirmation_required: false,
            success: true
          })
          updated = true
        }
      } else if (snowflakeIdStr(msg.modifyNavigation.target_id ?? msg.modifyNavigation.targetId) === want) {
        msg.modifyNavigation = {
          ...msg.modifyNavigation,
          cancelled: true,
          success: true,
          confirmation_required: false
        }
        updated = true
      }
    }

    if (updated) {
      messages.value[msgIdx] = { ...messages.value[msgIdx] }
      console.log('[MODIFY] 已标记消息为已更新', msg.id, 'targetId:', want)
    }
  })
  void refreshPersistedPendingDiffKeys(true, { emitListSync: false })
}

// 处理修改确认事件
const handleModifyConfirmed = (event) => {
  const detail = event.detail || {}
  const { targetId, newTitle: evNewTitle, oldTitle: evOldTitle, targetType: evTargetType } = detail
  const want = snowflakeIdStr(targetId)
  const newTitle = typeof evNewTitle === 'string' ? evNewTitle.trim() : ''
  const oldTitle = typeof evOldTitle === 'string' ? evOldTitle.trim() : ''
  const targetType = evTargetType || 'bug'
  console.log('[MODIFY] 收到确认事件，targetId:', want, 'newTitle:', newTitle)

  if (!want) {
    console.error('[MODIFY] 无效的 targetId:', targetId)
    return
  }

  // 找到对应的 modifyNavigation / modifyGroups 并标记为已执行
  messages.value.forEach((msg, msgIdx) => {
    let updated = false

    // 处理 modifyGroups
    if (msg.modifyGroups && Array.isArray(msg.modifyGroups)) {
      msg.modifyGroups.forEach((group, groupIdx) => {
        if (!group.items || !Array.isArray(group.items)) return

        const itemIdx = group.items.findIndex(
          (i) => snowflakeIdStr(i.target_id ?? i.targetId) === want
        )
        if (itemIdx !== -1) {
          // 创建新对象触发响应式更新
          const newItem = {
            ...group.items[itemIdx],
            confirmation_required: false,
            success: true
          }
          // 替换数组中的项
          group.items.splice(itemIdx, 1, newItem)
          updated = true
          console.log('[MODIFY] modifyGroups 中标记项为已执行:', want)

          // 检查组内是否全部确认完成
          const allGroupConfirmed = group.items.every(
            (i) => i.confirmation_required === false || i.cancelled === true
          )
          if (allGroupConfirmed) {
            console.log('[MODIFY] 该分组全部确认完成 plan_id:', group.plan_id)
          }
        }
      })
    }

    // 处理 modifyNavigation
    if (msg.modifyNavigation) {
      // 批量修改：标记 batch_results 中对应的项
      if (msg.modifyNavigation.batch_modify && msg.modifyNavigation.batch_results) {
        const resultIdx = msg.modifyNavigation.batch_results.findIndex(
          (r) => snowflakeIdStr(r.target_id) === want
        )
        if (resultIdx !== -1) {
          // 创建新对象触发响应式更新
          msg.modifyNavigation.batch_results.splice(resultIdx, 1, {
            ...msg.modifyNavigation.batch_results[resultIdx],
            confirmation_required: false,
            success: true
          })
          updated = true
          console.log('[MODIFY] 批量修改中标记项为已执行:', want)

          // 检查是否所有项都已确认
          const allConfirmed = msg.modifyNavigation.batch_results.every(
            (r) => r.confirmation_required === false || r.cancelled === true
          )
          if (allConfirmed) {
            console.log('[MODIFY] 批量修改全部确认完成')
          }
        }
      }
      // 单个修改：标记整个 modifyNavigation
      else if (snowflakeIdStr(msg.modifyNavigation.target_id) === want) {
        msg.modifyNavigation = {
          ...msg.modifyNavigation,
          success: true,
          confirmation_required: false
        }
        updated = true
        console.log('[MODIFY] 已标记消息为已执行', msg.id)
      }
    }

    if (newTitle && patchMessageLocateTitlesAfterAdopt(msg, want, targetType, newTitle)) {
      updated = true
    }

    // 触发响应式更新
    if (updated) {
      messages.value[msgIdx] = { ...messages.value[msgIdx] }
    }
  })

  if (oldTitle && newTitle && oldTitle !== newTitle) {
    const cur = String(sessionTitleRef.value || '')
    if (cur.includes(oldTitle)) {
      sessionTitleRef.value = cur.split(oldTitle).join(newTitle)
    }
  }

  // 列表侧 confirmModify 已 refreshActiveWorkbenchList；勿再 diff-review-sync 触发二次 restore/拉表
  void refreshPersistedPendingDiffKeys(true, { emitListSync: false })
}

// 大图预览：Escape 关闭（与下方 watch 成对注册/移除）
const imagePreviewEscapeHandler = (e) => {
  if (e.key === 'Escape') closeImagePreview()
}
watch(imagePreviewSrc, (src) => {
  if (src) {
    document.addEventListener('keydown', imagePreviewEscapeHandler)
  } else {
    document.removeEventListener('keydown', imagePreviewEscapeHandler)
  }
})

// 组件卸载：统一移除监听、中断请求、清理 rAF（须在 imagePreviewEscapeHandler 定义之后）
onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  window.removeEventListener('diff-review-push', onDiffReviewPushForChat)
  document.removeEventListener('keydown', imagePreviewEscapeHandler)
  stopReactResumePoll()

  if (reactSseReaderRef.value) {
    try {
      reactSseReaderRef.value.cancel('unmount')
    } catch (e) {}
    reactSseReaderRef.value = null
  }
  if (abortController.value) {
    try {
      abortController.value.abort()
    } catch (e) {}
    abortController.value = null
  }
  isSending.value = false

  if (_reasoningChatScrollRaf != null) {
    cancelAnimationFrame(_reasoningChatScrollRaf)
    _reasoningChatScrollRaf = null
  }
  try {
    messages.value.forEach((msg) => {
      cancelTodosStreamTypewriter(msg)
      cancelReasoningTypewriter(msg)
    })
  } catch (e) {}

  window.removeEventListener('modify-cancelled', handleModifyCancelled)
  window.removeEventListener('chat-temp-card-proposal', onChatTempCardProposal)
  window.removeEventListener('create-awaiting-temp-card', onCreateAwaitingTempCard)
  window.removeEventListener('modify-confirmed', handleModifyConfirmed)
  window.removeEventListener('request-pending-modify-for-plan', handleRequestPendingModifyForPlan)
  window.removeEventListener('pagehide', flushAgentRunSnapshotOnPageHide)
  flushAgentRunSnapshotOnPageHide()

  const root = messagesContainer.value
  if (root) root.removeEventListener('scroll', loadOlderHistoryIfNeeded)
})

// 监听 sessionId 变化，重新加载消息
watch(() => props.sessionId, (newSessionId) => {
  const rd = reactSseReaderRef.value
  if (rd) {
    try {
      rd.cancel('session_switch')
    } catch (e) {
      /* release read lock */
    }
    reactSseReaderRef.value = null
  }
  if (abortController.value) {
    try {
      abortController.value.abort()
    } catch (e) {}
    abortController.value = null
  }
  isSending.value = false
  historyLoading.value = false
  stopReactResumePoll()
  reactResumeInFlightRef.value = false
  reactInterruptedHint.value = null

  try {
    messages.value.forEach((msg) => {
      cancelTodosStreamTypewriter(msg)
      cancelReasoningTypewriter(msg)
    })
  } catch (e) {}

  sessionTitleRef.value = ''
  titleGenInFlight.value = false
  if (newSessionId) {
    messages.value = []
    historyHasMore.value = false
    historyBeforeId.value = null
    loadSessionMessages()
  } else {
    messages.value = []
  }
})
</script>

<style scoped>
.simple-chat-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #1e1e1e;
  color: #d4d4d4;
  min-height: 0;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.agent-local-proxy-hint {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.45;
  color: #ffe0b2;
  background: rgba(255, 152, 0, 0.12);
  border-bottom: 1px solid rgba(255, 152, 0, 0.25);
}

.agent-local-proxy-hint-text {
  flex: 1;
  min-width: 0;
}

.agent-local-proxy-hint-dismiss {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  color: #ccc;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 0 4px;
  border-radius: 4px;
}

.agent-local-proxy-hint-dismiss:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.react-recovery-banner {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.45;
  color: #b3e5fc;
  background: rgba(3, 169, 244, 0.1);
  border-top: 1px solid rgba(3, 169, 244, 0.22);
}

.react-recovery-banner-text {
  flex: 1;
  min-width: 0;
}

.react-recovery-banner-actions {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
}

.react-recovery-btn {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: transparent;
  color: #d4d4d4;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
}

.react-recovery-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.react-recovery-btn--primary {
  border-color: rgba(3, 169, 244, 0.45);
  color: #81d4fa;
}

.react-recovery-btn--primary:hover {
  background: rgba(3, 169, 244, 0.18);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #888;
  font-size: 14px;
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.message-block {
  display: flex;
  flex-direction: column;
  width: 100%;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* AI理解意图loading动画：左侧三个点，尽量弱化卡片感 */
.ai-understanding {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0;
  background: transparent;
  margin: 4px 0;
}

.ai-understanding-text {
  min-width: 18px;
  text-align: left;
  color: #e5e7eb;
  font-size: 12px;
  letter-spacing: 2px;
  animation: thinkingPulse 1s ease-in-out infinite;
}

.ai-understanding-inline {
  display: inline-block;
  margin: 4px 0;
  color: #e5e7eb;
  font-size: 12px;
}

@keyframes thinkingPulse {
  0% { opacity: 0.3; }
  50% { opacity: 1; }
  100% { opacity: 0.3; }
}


.loading-dots {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
}

.loading-dots--solo {
  margin-left: 0;
}

.loading-dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #888;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.loading-dots .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes dotPulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.message-author {
  font-weight: 600;
  font-size: 13px;
  color: #d4d4d4;
}

.message-time {
  font-size: 11px;
  color: #888;
}

/* 用户消息样式 */
.user-message-block {
  display: flex;
  flex-direction: column;
  align-items: stretch; /* 让“用户输入条”占满整行 */
  width: 100%;
}

.user-message-toggle-wrap {
  width: 100%;
  min-width: 0;
}

.user-message-bubble {
  width: 100%;
  max-width: 100%;
  padding: 12px 16px;
  cursor: pointer;
  background: rgba(148, 163, 184, 0.10); /* 未选中：更轻的浅灰底 */
  color: #e5e7eb;
  border: 1px solid rgba(148, 163, 184, 0.18); /* 未选中：更淡的细边框 */
  border-radius: 10px; /* 接近输入框的圆角 */
  line-height: 1.5;
  white-space: pre-wrap;
  overflow: visible; /* 避免底部阴影/截断观感 */
  word-wrap: break-word;
  word-break: break-word;
  font-size: 14px;
  box-shadow: none; /* 不要阴影 */
  outline: none; /* 交给 focus 样式 */
  transition: background 0.15s ease, border-color 0.15s ease;
}

/* 选中态（点击获得焦点）——对齐你第二张图的“更亮底 + 更清晰边框” */
.user-message-bubble:focus {
  background: rgba(148, 163, 184, 0.16);
  border-color: rgba(148, 163, 184, 0.32);
}

/* 键盘导航时给一个更明确的可见焦点（不影响鼠标点击观感） */
.user-message-bubble:focus-visible {
  border-color: rgba(96, 165, 250, 0.55);
}

/* 用户消息进入编辑态：容器占满整行，并与底部输入框统一背景/边框 */
.inline-composer {
  width: 100%;
}

.inline-composer .input-box-wrapper {
  width: 100%;
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  overflow: hidden;
}

.inline-composer .input-box-wrapper:focus-within {
  border-color: #3e3e3e;
  box-shadow: none;
}

/* AI消息样式 */
.ai-message-block {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 单根包裹 AgentTaskRun + 沙箱锚点 + Teleport；勿用 display:contents，部分环境下与 Teleport 拆卸交互差 */
.ai-agent-run-stack {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}

/* 深度思考：与 .simple-chat-panel 同色底，无边框；正文为 Cursor 系灰字，区别于普通回复 */
.cursor-reasoning-wrap {
  /* 与下方 AgentTaskRun/正文保留小幅间距；过大易被误认为「思考」与正文脱节 */
  margin: 6px 0 12px;
  max-width: 100%;
}
.cursor-reasoning-block {
  border: none;
  border-radius: 0;
  background: transparent;
  overflow: visible;
}
.cursor-reason-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 2px 0 4px;
  margin: 0;
  border: none;
  background: transparent;
  color: #858585;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  font-weight: 400;
}
.cursor-reason-summary:hover {
  background: transparent;
  color: #9d9d9d;
}
.cursor-reason-pill {
  color: #6b9bd1;
  font-weight: 500;
  letter-spacing: 0.01em;
}
.cursor-reason-meta {
  color: #858585;
  font-size: 11px;
  font-weight: 400;
}
.cursor-reason-chevron {
  margin-left: auto;
  opacity: 0.55;
  font-size: 10px;
  color: #858585;
}
/* 无内嵌滚动：高度随全文伸展，不出现滚动条 */
.cursor-reason-feed {
  overflow: visible;
  max-height: none;
  padding: 0 0 4px;
  border: none;
  background: transparent;
}
.cursor-reason-feed-stack {
  width: 100%;
}
/* ReAct THINK：SSE stream_channel=reasoning（偏冷、弱对比）与 content（偏亮） */
.react-sse-stream {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 6px;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
  line-height: 1.58;
  white-space: pre-wrap;
  word-break: break-word;
  tab-size: 2;
}
.react-sse-stream--reasoning {
  color: #7d8fa3;
  background: rgba(96, 140, 220, 0.07);
  border: 1px solid rgba(96, 140, 220, 0.14);
}
.react-sse-stream--content {
  color: #c4ccd6;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.react-sse-md-wrap .react-sse-md {
  margin-bottom: 0.75em;
}
.react-sse-md-wrap .react-sse-md:last-child {
  margin-bottom: 0;
}
/* 流式：从顶部向下排，与 Cursor 思考正文接近（sans + 冷灰字） */
.cursor-reason-plain {
  margin: 0;
  padding: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
  line-height: 1.62;
  letter-spacing: 0.01em;
  color: #9d9d9d;
  white-space: pre-wrap;
  word-break: break-word;
  tab-size: 2;
}
.cursor-reason-inner {
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
  line-height: 1.62;
  color: #9d9d9d;
  animation: none;
}
.cursor-reason-inner.reasoning-markdown :deep(p) {
  margin: 0 0 0.65em;
  color: #9d9d9d;
}
.cursor-reason-inner.reasoning-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.cursor-reason-inner.reasoning-markdown :deep(strong) {
  color: #b4b4b4;
  font-weight: 600;
}
.cursor-reason-inner.reasoning-markdown :deep(code) {
  font-family: ui-monospace, 'Cascadia Code', Consolas, Menlo, monospace;
  font-size: 12px;
  color: #c8c8c8;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
}
.cursor-reason-inner.reasoning-markdown :deep(pre) {
  margin: 0.5em 0;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.cursor-reason-inner.reasoning-markdown :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  color: #c8c8c8;
}
.cursor-reason-inner.reasoning-markdown :deep(ul),
.cursor-reason-inner.reasoning-markdown :deep(ol) {
  margin: 0.35em 0 0.5em 1.25em;
  color: #9d9d9d;
}
/* 步骤列表 */
.ai-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.step-item {
  padding: 12px;
  background: #252526;
  border-radius: 6px;
  border-left: 3px solid #666;
  transition: all 0.3s ease;
}

.step-item.running {
  border-left-color: #ffa500;
  background: #2d2d2d;
}

.step-item.completed {
  border-left-color: #4caf50;
}

.step-item.error {
  border-left-color: #f44336;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.step-icon {
  font-size: 16px;
}

.step-title {
  font-weight: 500;
  color: #d4d4d4;
  font-size: 13px;
}

.step-description {
  color: #aaa;
  font-size: 12px;
  margin-top: 4px;
  margin-left: 24px;
}

/* 工具调用 */
.tool-call {
  margin-top: 8px;
  margin-left: 24px;
  padding: 8px 12px;
  background: #1e1e1e;
  border-radius: 4px;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.tool-icon {
  font-size: 14px;
}

.tool-name {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  color: #4fc3f7;
}

.tool-level {
  font-size: 11px;
  color: #999;
  margin-left: auto;
  padding: 2px 6px;
  background: #1e1e1e;
  border-radius: 3px;
}

/* 分层工具样式 */
.tool-call.level-l1 {
  border-left: 2px solid #ff9800;
  background: #2a2420;
}

.tool-call.level-l2 {
  border-left: 2px solid #00bcd4;
  background: #1a2627;
}

.tool-call.level-l3 {
  border-left: 2px solid #4caf50;
  background: #1b2718;
}

/* 自我修正信息 */
.correction-info {
  margin-top: 8px;
  margin-left: 24px;
  padding: 10px 12px;
  background: #2a2a2a;
  border-left: 2px solid #ff5722;
  border-radius: 4px;
}

.correction-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.correction-icon {
  font-size: 14px;
}

.correction-title {
  font-weight: 500;
  color: #ff5722;
  font-size: 12px;
}

.correction-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.correction-item {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: #aaa;
}

.correction-item .label {
  color: #999;
  font-weight: 500;
  min-width: 40px;
}

.correction-item .value {
  color: #d4d4d4;
  flex: 1;
}

.tool-output {
  margin-top: 4px;
}

.tool-output pre {
  margin: 0;
  padding: 8px;
  background: #0d1117;
  border-radius: 4px;
  color: #aaa;
  font-size: 12px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* AI 最终回复 */
.ai-response {
  padding: 12px 16px;
  background: #2d2d2d;
  border-radius: 6px;
}

.response-text,
.ai-response-text {
  color: #d4d4d4;
  line-height: 1.6;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.input-container {
  flex-shrink: 0;
  padding: 16px;
  background: #1e1e1e;
  position: sticky;
  bottom: 0;
  z-index: 100;
}

.input-box-wrapper {
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.input-box-wrapper:focus-within {
  border-color: #3e3e3e;
  box-shadow: none;
}

.input-box-wrapper--dragover {
  border-color: #58a6ff;
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.3);
}

.pending-images-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 12px 2px;
  background: transparent;
}

/* 有图片预览时，缩小输入框与图片之间的间距 */
.input-box-wrapper:has(.pending-images-row) .message-input {
  padding-top: 6px;
}

.pending-image-item {
  position: relative;
}

.pending-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #3e3e3e;
  cursor: pointer;
}

.pending-image-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: #e74c3c;
  color: white;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pending-image-remove:hover {
  background: #c0392b;
}

.image-upload-button {
  width: 22px;
  height: 22px;
  padding: 0;
  margin-right: 10px;
  border: 1px solid rgba(255, 255, 255, 0.30);
  background: rgba(255, 255, 255, 0.30);
  border-radius: 999px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease;
}

.image-upload-button--active {
  background: #ffffff;
  border-color: #ffffff;
}

.image-upload-button:hover {
  transform: scale(1.05);
}

.image-upload-button:hover:not(.image-upload-button--active) {
  background: rgba(255, 255, 255, 0.4);
  border-color: rgba(255, 255, 255, 0.4);
}

.image-upload-button.image-upload-button--active:hover {
  background: #f8fafc;
  border-color: #f8fafc;
}

.image-upload-button:active {
  transform: scale(0.95);
}

.image-upload-icon {
  width: 12px;
  height: 12px;
  display: block;
  filter: brightness(0) saturate(100%);
  opacity: 0.95;
}

.user-message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.user-msg-thumb {
  max-width: 120px;
  max-height: 80px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #3e3e3e;
  cursor: pointer;
}

/* 图片大图预览弹层（须高于 ProjectWorkspaceShell 顶栏 10100） */
.image-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 120000;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px 24px;
  cursor: zoom-out;
}

.image-preview-stage {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: min(96vw, 1400px);
  max-height: min(88vh, 900px);
  cursor: default;
}

.image-preview-toolbar {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: 8px;
  background: rgba(30, 30, 30, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
  pointer-events: auto;
}

.image-preview-tool-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #e8e8e8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.image-preview-tool-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

.image-preview-tool-btn--close:hover {
  background: rgba(220, 80, 80, 0.35);
}

.image-preview-tool-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.image-preview-full {
  display: block;
  max-width: min(96vw, 1400px);
  max-height: min(88vh, 900px);
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.message-input {
  width: 100%;
  padding: 12px 14px;
  background: transparent;
  border: none;
  color: #d4d4d4;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  line-height: 1.5;
  min-height: 60px;  /* 最小高度 60px（约 3 行） */
  max-height: 300px;  /* 最大高度 300px（约 15 行） */
  overflow-y: hidden;  /* 默认隐藏滚动条，由 JS 动态控制 */
  box-sizing: border-box;
}

.message-input::placeholder {
  color: #666;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 8px;               /* 进一步压缩高度 */
  background: transparent;         /* 去掉浅灰载体 */
  border-top: none;               /* 去掉细线 */
}

.footer-left {
  display: flex;
  gap: 8px;
  align-items: center;
}

.selector-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(226, 232, 240, 0.7);
  font-size: 11px;
}

.selector-label {
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.footer-select {
  /* 默认（未选中）：更浅灰，更像 Cursor 输入区工具条 */
  background: rgba(148, 163, 184, 0.10);
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: #e5e7eb;
  font-size: 12px;        /* 选择器更大一点 */
  padding: 2px 10px;      /* 增大可点区域 */
  border-radius: 8px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.footer-select:hover {
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.28);
}

.footer-select:focus {
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.32);
}

/* 下拉菜单（Electron/Chromium 下通常可生效） */
.footer-select option {
  /* 展开菜单保持 Cursor：深色底 + 白字 */
  background: #1f1f1f;
  color: #e6e6e6;
}

.footer-right {
  display: flex;
  align-items: center;
}

.send-icon-button {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #ffffff;
  border: 1px solid #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.12s ease, opacity 0.12s ease, background 0.12s ease, border-color 0.12s ease;
}

.send-icon-button:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #f8fafc;
  transform: scale(1.05);
}

.send-icon-button:active:not(:disabled) {
  transform: scale(0.95);
}

.send-icon-button:disabled {
  background: rgba(255, 255, 255, 0.30);
  border-color: rgba(255, 255, 255, 0.30);
  cursor: not-allowed;
  opacity: 1;
}

.send-icon-img {
  width: 11px;
  height: 11px;
  display: block;
  filter: brightness(0) saturate(100%);
  opacity: 0.95;
}

.stop-icon-button {
  background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
  color: white;
  border: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
}

.stop-icon-button:hover {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  transform: scale(1.05);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.45);
}

.stop-icon-button:active {
  transform: scale(0.95);
}

/* 滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #3e3e3e;
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #4e4e4e;
}

/* Bug 保存部分 */
.save-bugs-section {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #2d3a2d;
  border-left: 3px solid #4caf50;
  border-radius: 6px;
}

.save-bugs-button {
  background: #4caf50;
  color: white;
  border: none;
  padding: 8px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.save-bugs-button:hover {
  background: #45a049;
  transform: scale(1.02);
}

.save-bugs-button:active {
  transform: scale(0.98);
}

.bugs-count {
  font-size: 12px;
  color: #aaa;
  margin-left: auto;
}

/* 执行证据部分 */
.evidence-section {
  margin: 12px 0;
  padding: 12px 0;
  border-top: 1px solid #e5e7eb;
}

.reasoning-section {
  margin: 10px 0;
}
.reasoning-details {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}
.reasoning-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #6b7280;
  list-style: none;
}
.reasoning-summary::-webkit-details-marker { display: none; }
.reasoning-content {
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  color: #374151;
  word-break: break-word;
  border-top: 1px solid #e5e7eb;
}
.reasoning-content.reasoning-markdown {
  white-space: normal;
}
.reasoning-markdown p { margin: 0.4em 0; line-height: 1.6; }
.reasoning-markdown p:first-child { margin-top: 0; }
.reasoning-markdown h1, .reasoning-markdown h2, .reasoning-markdown h3 { font-weight: 600; margin: 0.75em 0 0.25em; }
.reasoning-markdown h1 { font-size: 1.2em; }
.reasoning-markdown h2 { font-size: 1.1em; }
.reasoning-markdown h3 { font-size: 1em; }
.reasoning-markdown ul, .reasoning-markdown ol { margin: 0.4em 0; padding-left: 1.5em; }
.reasoning-markdown li { margin: 0.2em 0; }
.reasoning-markdown strong { font-weight: 700; }
.reasoning-markdown code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.reasoning-markdown pre { background: #f1f5f9; padding: 10px; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; font-size: 0.85em; white-space: pre-wrap; }
.reasoning-markdown pre code { background: none; padding: 0; }

.findings-section {
  margin: 16px 0;
}

.findings-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.client-local-run-section {
  margin: 12px 0;
}
.client-local-run-card {
  padding: 12px 14px;
  margin-bottom: 10px;
}
.client-local-run-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.client-local-run-body {
  margin: 0 0 10px;
  line-height: 1.5;
}
.client-local-run-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.client-local-run-pre {
  font-size: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px 10px;
  margin: 6px 0 0;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.client-local-run-tip {
  margin: 8px 0 0;
}

.client-local-run-os {
  margin: 0 0 10px;
}

.client-local-run-platform {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #e5e7eb;
}

.client-local-run-platform-title {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.findings-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f0f9ff;
  border-bottom: 1px solid #bae6fd;
}

.findings-icon {
  font-size: 18px;
}

.findings-title {
  font-size: 14px;
  font-weight: 600;
  color: #0369a1;
  flex: 1;
}

.findings-count {
  font-size: 12px;
  padding: 2px 8px;
  background: #0ea5e9;
  color: #fff;
  border-radius: 12px;
  font-weight: 500;
}

.findings-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.finding-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.6;
}

.finding-bullet {
  color: #0ea5e9;
  font-size: 16px;
  flex-shrink: 0;
  margin-top: 2px;
}

.finding-text {
  font-size: 14px;
  color: #374151;
}

/* Bug导航列表 */
.bug-navigation-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e0e7ff;
}

.bug-nav-header {
  font-size: 13px;
  font-weight: 600;
  color: #4338ca;
  margin-bottom: 8px;
}

.bug-nav-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 4px 0;
  background: #f8fafc;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.bug-nav-item:hover {
  background: #e0e7ff;
  transform: translateX(4px);
}

.bug-nav-icon {
  color: #4f46e5;
  margin-right: 8px;
  font-size: 14px;
}

.bug-nav-title {
  color: #1e293b;
  font-size: 14px;
  font-weight: 500;
  flex: 1;
}

.bug-nav-plan {
  color: #64748b;
  font-size: 12px;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}

/* 修改导航区域 */
.modify-navigation-section {
  margin: 12px 0;
}

/* Teleport 目标：无内容时不占位（内嵌模式下下方锚点为空） */
.agent-modify-sandbox-anchor:empty {
  display: none;
}

.sandbox-confirm-hint {
  margin: 0 0 12px;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.45;
  color: #94a3b8;
  border-left: 3px solid rgba(59, 130, 246, 0.45);
  background: rgba(15, 23, 42, 0.35);
  border-radius: 0 6px 6px 0;
}

.sandbox-confirm-hint strong {
  color: #cbd5e1;
}

.sandbox-confirm-hint--muted {
  border-left-color: rgba(34, 197, 94, 0.45);
  color: #86efac;
}

.plan-badge {
  background: transparent;
  color: #ffffff;
  font-size: 12px;
  padding: 0;
  border-radius: 0;
  margin-left: 8px;
  font-weight: 600;
  opacity: 0.95;
}

/* Cursor 风格：展开条在卡片底边居中，悬停整张卡片才显示 */
.sandbox-card--has-expand {
  position: relative;
}

.sandbox-preview-body {
  position: relative;
}

.sandbox-preview-body--collapsed {
  padding-bottom: 4px;
}

.sandbox-preview-fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 28px;
  pointer-events: none;
  background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.88));
}

.sandbox-expand-bar {
  position: relative;
  display: block;
  width: 100%;
  height: 20px;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
  overflow: visible;
}

.sandbox-card--has-expand:hover .sandbox-expand-bar {
  opacity: 1;
}

/*  chevron 骑在底边线上（与 Cursor diff 块一致） */
.sandbox-expand-chevron {
  position: absolute;
  left: 50%;
  top: 0;
  width: 14px;
  height: 14px;
  display: block;
  transform: translate(-50%, -50%);
  filter: brightness(0) saturate(100%) invert(73%) sepia(11%) saturate(326%) hue-rotate(176deg) brightness(90%) contrast(86%);
  transition: transform 0.12s ease;
  pointer-events: none;
}

.sandbox-expand-bar.expanded .sandbox-expand-chevron {
  transform: translate(-50%, -50%) rotate(180deg);
}

.group-item-target {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin: 8px 0 4px;
}
.group-item-target:first-of-type {
  margin-top: 0;
}

.group-items-hint {
  font-size: 12px;
  color: #888;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #eee;
}

/* 首轮 Todo 流式正文（LLM content_delta） */
.todos-stream-block {
  margin: 10px 0 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.todos-stream-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
  font-weight: 600;
}
.todos-stream-pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: #334155;
  max-height: 220px;
  overflow-y: auto;
}

.modify-navigation-content {
  padding: 12px 16px;
}

.sandbox-list-empty {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  padding: 4px 0 8px;
}

.modify-field-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 14px;
}

.modify-field-preview--muted {
  font-size: 12px;
  color: #94a3b8;
  font-style: italic;
  padding: 6px 0;
  display: block;
}

.modify-field-preview .field-label {
  color: #6b7280;
  font-weight: 500;
}

.modify-field-preview .old-value {
  color: #ef4444;
  text-decoration: line-through;
  background: #fef2f2;
  padding: 2px 6px;
  border-radius: 4px;
}

.modify-field-preview .old-value.empty-value {
  color: #9ca3af;
  text-decoration: none;
  background: #f3f4f6;
  font-style: italic;
}

.modify-field-preview .arrow {
  color: #9ca3af;
}

.modify-field-preview .new-value {
  color: #059669;
  background: #ecfdf5;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

/* 新建操作的值样式：更深的暗绿色 */
.modify-field-preview .new-value.create-value {
  color: #047857;
  background: #d1fae5;
  font-weight: 600;
}

.modify-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

.btn-primary {
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-secondary {
  padding: 8px 16px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

.btn-icon-approve,
.btn-icon-reject {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon-approve {
  background: #10b981;
  color: white;
}

.btn-icon-approve:hover {
  background: #059669;
  transform: scale(1.1);
}

.btn-icon-reject {
  background: #ef4444;
  color: white;
}

.btn-icon-reject:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.evidence-title {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
  font-size: 14px;
}

/* 搜索结果部分 */
.search-results-section {
  margin: 12px 0;
  padding: 12px;
  background: #f0f4f8;
  border-left: 3px solid #2196F3;
  border-radius: 4px;
}

.search-results-title {
  font-weight: 600;
  color: #1976D2;
  margin-bottom: 12px;
  font-size: 14px;
}

.search-results-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 500px;
  overflow-y: auto;
}

.search-result-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  background: white;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
  transition: all 0.2s;
}

.search-result-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: #2196F3;
}

.search-result-rank {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  background: #2196F3;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
  margin-top: 2px;
}

.search-result-content {
  flex: 1;
  min-width: 0;
}

.search-result-title {
  font-weight: 600;
  color: #1976D2;
  margin-bottom: 4px;
  font-size: 13px;
  word-break: break-word;
}

.search-result-title:hover {
  color: #1565C0;
  text-decoration: underline;
}

.search-result-url {
  font-size: 11px;
  color: #6b8cae;
  margin-bottom: 6px;
  word-break: break-all;
  font-family: 'Courier New', monospace;
}

.search-result-snippet {
  font-size: 12px;
  color: #555;
  line-height: 1.4;
  word-break: break-word;
}

/* 思考过程样式 - 极简深色风格 */
.reasoning-section {
  margin: 8px 0;
}

.reasoning-details {
  background: transparent; /* 和对话面板融为一体 */
  border: none;
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.reasoning-details[open] {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.22); /* 与待办一致：细边框线包起来 */
}

.reasoning-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: transparent;
  cursor: pointer;
  list-style: none;
  font-size: 12px;
  font-weight: 500;
  color: #ccc;
  user-select: none;
  transition: background 0.2s;
  border-bottom: none; /* 由内容区 border-top 做分隔，避免双线 */
}

/* 未展开时：不要展示底边框 */
.reasoning-details:not([open]) .reasoning-summary {
  border-bottom: none;
}

/* 行背景保持和对话面板一致：不做 hover/选中变色 */
.reasoning-summary:hover {
  background: transparent;
}

.reasoning-summary::-webkit-details-marker {
  display: none;
}

.reasoning-toggle {
  width: 10px;
  height: 10px;
  display: block;
  flex-shrink: 0;
  margin-left: 6px; /* 在“深度思考”右侧一点 */
  /* 让图标颜色更接近 Qoder 的灰色 */
  filter: brightness(0) saturate(100%) invert(73%) sepia(11%) saturate(326%) hue-rotate(176deg) brightness(90%) contrast(86%);
  opacity: 0; /* 默认不显示 */
  transition: opacity 0.15s ease;
  pointer-events: none;
}

/* 两个图标根据 open 状态切换 */
.reasoning-toggle--down { display: none; }

/* 折叠：hover 才显示向右 */
.reasoning-details:not([open]) .reasoning-summary:hover .reasoning-toggle--right {
  opacity: 0.95;
}

/* 展开：常显向下，隐藏向右 */
.reasoning-details[open] .reasoning-toggle--right { display: none; }
.reasoning-details[open] .reasoning-toggle--down {
  display: block;
  opacity: 0.95;
}

.reasoning-icon {
  width: 14px;
  height: 14px;
  display: block;
  filter: invert(1); /* 深色背景下反相成浅色/白色 */
}

.reasoning-title {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

/* 旧的倒三角箭头不再使用 */
.reasoning-arrow { display: none; }

.reasoning-content {
  padding: 12px 16px;
  background: transparent; /* 不要深色底，保持轻量 */
  border-top: 1px solid rgba(148, 163, 184, 0.22); /* 标题/内容分隔线 */
  font-size: 13px;
  line-height: 1.6;
  color: #fff;
  overflow-x: auto;
}

.reasoning-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #cbd5e1; /* Cursor 风格：正文偏灰 */
  animation: reasoningTyping 0.03s steps(1) infinite;
}

.reasoning-text.reasoning-markdown {
  white-space: normal; /* 交给 markdown 的标签排版 */
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Liberation Sans', sans-serif;
  color: #cbd5e1;
}

/* Cursor 风格：Markdown 分层配色 */
.reasoning-text.reasoning-markdown :deep(p) {
  margin: 0 0 10px;
  line-height: 1.65;
}
.reasoning-text.reasoning-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.reasoning-text.reasoning-markdown :deep(strong) {
  color: #f8fafc;
  font-weight: 600;
}
.reasoning-text.reasoning-markdown :deep(em) {
  color: #e5e7eb;
}
.reasoning-text.reasoning-markdown :deep(h1),
.reasoning-text.reasoning-markdown :deep(h2),
.reasoning-text.reasoning-markdown :deep(h3) {
  margin: 14px 0 8px;
  color: #f1f5f9;
  font-weight: 600;
  font-size: 13px;
}
.reasoning-text.reasoning-markdown :deep(ul),
.reasoning-text.reasoning-markdown :deep(ol) {
  margin: 8px 0 10px 18px;
  padding: 0;
}
.reasoning-text.reasoning-markdown :deep(li) {
  margin: 4px 0;
}
.reasoning-text.reasoning-markdown :deep(code) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  color: #e2e8f0;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.18);
  padding: 1px 6px;
  border-radius: 6px;
}
.reasoning-text.reasoning-markdown :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.18);
  overflow: auto;
}
.reasoning-text.reasoning-markdown :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
  color: #e5e7eb;
}
.reasoning-text.reasoning-markdown :deep(a) {
  color: #93c5fd;
  text-decoration: none;
}
.reasoning-text.reasoning-markdown :deep(a:hover) {
  text-decoration: underline;
}

@keyframes reasoningTyping {
  from {
    caret-color: #00ff00;
  }
  to {
    caret-color: transparent;
  }
}

/* 统一总结：Cursor 式「耗时 Xs」打字机，无图标 */
.unified-summary-section {
  margin: 12px 0;
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 6px;
  overflow: hidden;
}
.unified-summary-header {
  padding: 6px 12px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.unified-summary-loading {
  display: flex;
  align-items: center;
  min-height: 1.25em;
}
.unified-summary-content.unified-summary-content {
  padding: 12px 16px;
}
.unified-summary-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #fff;
  animation: reasoningTyping 0.03s steps(1) infinite;
}

/* 通用可折叠卡片样式 - 与深度思考一致：深色背景、白色字体（关键发现、沙箱预览、Bug 导航等） */
.collapsible-card {
  background: transparent; /* 跟随对话面板底色 */
  border: 1px solid rgba(148, 163, 184, 0.22); /* 细小边框线区分块 */
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s ease;
  margin-bottom: 12px;
}

.collapsible-card[open] {
  background: transparent;
  border-color: rgba(148, 163, 184, 0.28);
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: transparent;
  cursor: pointer;
  list-style: none;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  user-select: none;
  transition: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}

.collapsible-header:hover {
  background: transparent;
}

.collapsible-header::-webkit-details-marker {
  display: none;
}

.card-icon {
  font-size: 14px;
  opacity: 0.8;
}

.card-title {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

.card-count {
  font-size: 11px;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 10px;
  color: #ccc;
}

.card-arrow {
  font-size: 10px;
  transition: transform 0.2s ease;
  opacity: 0.6;
  color: #888;
}

.collapsible-card[open] .card-arrow {
  transform: rotate(180deg);
}

.sandbox-card .sandbox-header {
  cursor: pointer;
}
.sandbox-adopted-summary {
  border: 1px solid rgba(34, 197, 94, 0.35);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: rgba(34, 197, 94, 0.06);
}
.sandbox-adopted-summary:hover {
  background: rgba(34, 197, 94, 0.1);
}
.sandbox-header--compact {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  font-size: 13px;
  color: #a7f3d0;
}
.sandbox-adopted-summary .card-title {
  flex: 1;
  min-width: 0;
}
.sandbox-card .card-arrow.expanded {
  transform: rotate(180deg);
}

.collapsible-content {
  padding: 12px 16px;
  background: transparent;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  font-size: 13px;
  line-height: 1.6;
  color: #fff;
  overflow-x: auto;
}

/* 关键发现/沙箱预览/Bug 导航内部内容 - 与深度思考一致的白字深色 */
.collapsible-content .finding-item,
.collapsible-content .finding-text {
  color: #fff;
}
.collapsible-content .finding-bullet {
  color: #888;
}
.collapsible-content .bug-navigation-list {
  border-top-color: rgba(148, 163, 184, 0.22);
}
.collapsible-content .bug-nav-item {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: #fff;
}
.collapsible-content .bug-nav-item:hover {
  background: transparent;
}
.collapsible-content .bug-nav-icon {
  color: #888;
}
.collapsible-content .bug-nav-title {
  color: #fff;
}
.collapsible-content .bug-nav-plan {
  color: #aaa;
  background: rgba(255, 255, 255, 0.08);
}
.collapsible-content .modify-field-preview .field-label {
  color: #ccc;
}
.collapsible-content .modify-field-preview .old-value {
  color: #f87171;
  background: rgba(248, 113, 113, 0.15);
}
.collapsible-content .modify-field-preview .old-value.empty-value {
  color: #888;
  background: transparent;
}
.collapsible-content .modify-field-preview .arrow {
  color: #666;
}
.collapsible-content .modify-field-preview .new-value {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.15);
}

/* 新建操作的值样式：更深的暗绿色（暗色主题） */
.collapsible-content .modify-field-preview .new-value.create-value {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.2);
  font-weight: 600;
}
.collapsible-content .modify-actions {
  border-top-color: rgba(148, 163, 184, 0.22);
}
.collapsible-content .group-items-hint {
  color: #aaa;
}
.collapsible-content .btn-primary {
  background: #333;
  color: #fff;
  border: 1px solid #444;
}
.collapsible-content .btn-primary:hover {
  background: #444;
}

.model-select-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}

.model-icon--ernie {
  width: 16px;
  height: 16px;
}

.temp-card-proposal-bar--inline {
  margin: 8px 0 10px;
}

.temp-card-proposal-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 0 12px 8px;
  padding: 10px 12px;
  border: 1px solid rgba(59, 130, 246, 0.35);
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.1);
  font-size: 12px;
  color: #e2e8f0;
  line-height: 1.45;
}

.temp-card-proposal-text {
  flex: 1;
  min-width: 200px;
}

.temp-card-proposal-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.temp-card-proposal-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.temp-card-proposal-btn--approve {
  color: #052e16;
  background: #4ade80;
  border-color: #22c55e;
}

.temp-card-proposal-btn--reject {
  color: #fecaca;
  background: transparent;
  border-color: rgba(248, 113, 113, 0.45);
}
</style>
