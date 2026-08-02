<template>
  <div class="testcase-detail-wrapper" :class="{ 'is-embedded': embedded }">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">{{ t('cardForm.loadingProject') }}</div>
    </div>
    
    <!-- 顶部标题栏：嵌入模式也需要返回等操作，保留显示 -->
    <div class="header-bar">
      <div class="header-left">
        <span v-if="!embedded || isEdit" class="back-arrow" @click="goBack">←</span>
        <span class="header-title">{{ isEdit ? t('project.editTestCase') : t('project.newTestCase') }}</span>
        <span class="project-name" v-if="projectInfo.name">/ {{ projectInfo.name }}</span>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧主要内容区：可滚动内容 + 底部固定操作栏 -->
      <div class="content-left">
        <div class="content-left-scroll">
        <!-- 待采纳改动（show_diff 模式） -->
        <div
          v-if="!embedded && pendingDiff && pendingDiff.modifications && pendingMonacoModifyCount() > 0"
          class="pending-diff-panel"
        >
          <div class="pending-diff-header">
            <div class="pending-diff-title">{{ t('cardForm.pendingChanges') }}</div>
            <div class="pending-diff-subtitle">{{ t('cardForm.pendingChangesSubtitle') }}</div>
          </div>

          <template v-for="(data, field) in pendingDiff.modifications" :key="field">
          <div
            v-if="!String(field).startsWith('_') && isMonacoPendingModifyField(field)"
            class="pending-diff-item"
            :id="`diff-field-${field}`"
          >
            <div class="pending-diff-item-head">
              <div class="pending-diff-field">
                <span class="pending-diff-field-label">{{ testcaseFieldLabel(field) }}</span>
              </div>
              <div class="pending-diff-actions">
                <button class="btn-icon-approve" :title="t('cardForm.adoptField')" @click="applyFieldChange(field)">✓</button>
                <button class="btn-icon-reject" :title="t('cardForm.rejectField')" @click="cancelFieldChange(field)">✗</button>
              </div>
            </div>
            <MonacoDiffEditor
              :original="String(data?.old ?? '')"
              :modified="String(data?.new ?? '')"
              language="markdown"
              theme="vs-dark"
              height="160px"
              :renderSideBySide="false"
            />
          </div>
          </template>
        </div>

        <!-- 标题区域 -->
        <div class="title-section">
          <input 
            v-model="testcase.title" 
            class="title-input" 
            :placeholder="t('testcaseForm.titlePlaceholder')"
            maxlength="100"
          />
          <div class="title-count">{{ testcase.title.length }} / 100</div>
        </div>

        <!-- 状态和维护人信息 -->
        <div class="status-section">
          <div class="status-item">
            <span class="status-label">{{ t('cardForm.status') }}:</span>
            <div class="status-dropdown" @click="toggleStatusDropdown">
              <div class="status-pill">
                <span class="status-text">{{ getStatusText(testcase.status) }}</span>
                <span class="arrow-icon" :class="{ 'rotated': showStatusDropdown }">▼</span>
              </div>
              <div v-if="showStatusDropdown" class="status-dropdown-menu">
                <div 
                  v-for="status in availableStatuses" 
                  :key="status.value"
                  class="status-option"
                  :class="{ 'selected': testcase.status === status.value }"
                  @click.stop="selectStatus(status.value)"
                >
                  {{ status.label }}
                </div>
              </div>
            </div>
          </div>
          <div class="status-item">
            <span class="status-label">{{ t('cardForm.assignee') }}:</span>
            <div class="assignee-dropdown" @click="toggleAssigneeDropdown">
              <div class="assignee-pill">
                <span class="person-icon">👤</span>
                <span class="assignee-name">{{ getAssigneeDisplayText() }}</span>
                <span class="arrow-icon" :class="{ 'rotated': showAssigneeDropdown }">▼</span>
              </div>
              <div v-if="showAssigneeDropdown" class="assignee-dropdown-menu">
                <!-- 搜索框 -->
                <div class="assignee-search">
                  <input 
                    type="text" 
                    v-model="assigneeSearchText"
                    :placeholder="t('cardForm.searchKeyword')"
                    class="search-input"
                    @click.stop
                  />
                  <span class="search-icon">🔍</span>
                </div>
                
                <!-- 当前用户 -->
                <div class="assignee-section">
                  <div class="section-title">{{ t('cardForm.currentUser') }}</div>
                  <div 
                    v-if="currentUser"
                    class="assignee-option"
                    :class="{ 'selected': isAssigneeSelected(currentUser.id.toString()) }"
                    @click.stop="toggleAssignee(currentUser.id.toString())"
                  >
                    <div class="checkbox" :class="{ 'checked': isAssigneeSelected(currentUser.id.toString()) }">
                      <span v-if="isAssigneeSelected(currentUser.id.toString())" class="checkmark">✓</span>
                    </div>
                    <div class="assignee-avatar">👤</div>
                    <div class="assignee-info">
                      <div class="assignee-name">{{ personPrimaryLabel(currentUser) }}</div>
                      <div v-if="personSecondaryLabel(currentUser)" class="assignee-id">{{ personSecondaryLabel(currentUser) }}</div>
                    </div>
                  </div>
                  <div v-else class="no-user-tip">
                    <span class="tip-icon">⚠️</span>
                    <span class="tip-text">{{ t('cardForm.noCurrentUser') }}</span>
                  </div>
                </div>
                
                <!-- 项目成员 -->
                <div v-if="projectMembers.length > 0" class="assignee-section">
                  <div class="section-title">{{ t('cardForm.projectMembersCount', { n: projectMembers.length }) }}</div>
                  <div 
                    v-for="member in projectMembers" 
                    :key="member.id"
                    class="assignee-option"
                    :class="{ 'selected': isAssigneeSelected(member.id.toString()) }"
                    @click.stop="toggleAssignee(member.id.toString())"
                  >
                    <div class="checkbox" :class="{ 'checked': isAssigneeSelected(member.id.toString()) }">
                      <span v-if="isAssigneeSelected(member.id.toString())" class="checkmark">✓</span>
                    </div>
                    <div class="assignee-avatar">👤</div>
                    <div class="assignee-info">
                      <div class="assignee-name">{{ personPrimaryLabel(member) }}</div>
                      <div v-if="personSecondaryLabel(member)" class="assignee-id">{{ personSecondaryLabel(member) }}</div>
                    </div>
                  </div>
                </div>
                
                <!-- 无项目成员时的提示 -->
                <div v-else-if="testcase.project_id && projectMembers.length === 0" class="assignee-section">
                  <div class="section-title">{{ t('cardForm.projectMembersZero') }}</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">ℹ️</span>
                    <span class="tip-text">{{ t('cardForm.noProjectMembers') }}</span>
                  </div>
                </div>
                
                <!-- 未选择项目时的提示 -->
                <div v-else-if="!testcase.project_id" class="assignee-section">
                  <div class="section-title">{{ t('cardForm.projectMembers') }}</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">⚠️</span>
                    <span class="tip-text">{{ t('cardForm.selectProjectFirst') }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="status-item">
            <span class="status-label">{{ t('cardForm.plan') }}:</span>
            <div class="plan-dropdown" @click="togglePlanDropdown">
              <div class="plan-selected-display">
                <span class="refresh-icon" @click.stop="refreshProjectPlans">🔄</span>
                <span class="plan-selected-text">
                  {{ t('cardForm.plan') }} {{ getSelectedPlanDisplayText }}
                </span>
                <span class="arrow-icon" :class="{ 'rotated': showPlanDropdown }">▼</span>
              </div>
              <div v-if="showPlanDropdown" class="plan-dropdown-menu">
                <div 
                  v-for="plan in selectableTestcasePlans" 
                  :key="plan.value"
                  class="plan-option"
                  :class="{ 'selected': String(testcase.plan) === String(plan.value) }"
                  @click.stop="selectPlan(plan.value)"
                >
                  <span class="plan-icon">{{ plan.icon || '📋' }}</span>
                  <span class="plan-label">{{ plan.label }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab导航 -->
        <div class="tabs-container">
          <div class="tabs">
            <div 
              class="tab" 
              :class="{ active: activeTab === 'basic' }"
              @click="activeTab = 'basic'"
            >
              基本信息
            </div>
            <div 
              class="tab" 
              :class="{ active: activeTab === 'defects' }"
              @click="activeTab = 'defects'"
            >
              缺陷
            </div>
            <div 
              class="tab" 
              :class="{ active: activeTab === 'execution' }"
              @click="activeTab = 'execution'"
            >
              执行
            </div>
          </div>
        </div>

        <!-- Tab内容 -->
        <div class="tab-content">
          <!-- 基本信息 Tab -->
          <div v-if="activeTab === 'basic'" class="tab-pane">
            <!-- 前置条件 - 富文本编辑器 -->
            <div class="form-group" :class="{ 'has-diff': hasDetailFieldDiff('preconditions') }">
              <label class="field-label">{{ testcaseFieldLabel('preconditions') }}</label>
              <div v-if="hasDetailFieldDiff('preconditions')" class="field-diff-panel">
                <div class="diff-header">
                  <span class="diff-label">{{ t('cardForm.diffPreview') }}:</span>
                  <div class="diff-actions">
                    <button @click="applyFieldChange('preconditions')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button @click="cancelFieldChange('preconditions')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-old">
                    <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                    <span class="diff-value">{{ formatDiffFieldValue('preconditions', detailFieldDiff('preconditions')?.old) }}</span>
                  </div>
                  <div class="diff-arrow">→</div>
                  <div class="diff-new">
                    <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                    <span class="diff-value">{{ formatDiffFieldValue('preconditions', detailFieldDiff('preconditions')?.new) }}</span>
                  </div>
                </div>
              </div>
              <div class="editor-section">
                <RichTextHtmlEditor
                  ref="preconditionsEditorRef"
                  v-model="testcase.preconditions"
                  class="editor-textarea"
                  :placeholder="t('testcaseForm.preconditionsPlaceholder')"
                />
              </div>
            </div>

            <!-- 用例步骤 -->
            <div class="form-group" :class="{ 'has-diff': hasDetailFieldDiff('steps') }" id="diff-field-steps">
              <label class="field-label">{{ testcaseFieldLabel('steps') }}</label>
              <div v-if="hasDetailFieldDiff('steps')" class="field-diff-panel">
                <div class="diff-header">
                  <span class="diff-label">{{ testcaseFieldLabel('steps') }} · {{ t('cardForm.diffPreview') }}</span>
                  <div class="diff-actions">
                    <button type="button" @click="applyFieldChange('steps')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button type="button" @click="cancelFieldChange('steps')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-row">
                    <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                    <span class="diff-value diff-value-multiline">{{ formatDiffFieldValue('steps', detailFieldDiff('steps')?.old) }}</span>
                  </div>
                  <div class="diff-row">
                    <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                    <span class="diff-value diff-value-multiline">{{ formatDiffFieldValue('steps', detailFieldDiff('steps')?.new) }}</span>
                  </div>
                </div>
              </div>
              <div class="steps-table">
                <div class="steps-header">
                  <div class="step-col-number">#</div>
                  <div class="step-col-desc">{{ t('testcaseForm.stepDesc') }}</div>
                  <div class="step-col-expected">{{ t('testcaseForm.expectedResult') }}</div>
                  <div class="step-col-actions">{{ t('testcaseForm.actions') }}</div>
                </div>
                <div 
                  v-for="(step, index) in testcase.steps" 
                  :key="index"
                  class="step-row"
                >
                  <div class="step-col-number">{{ index + 1 }}</div>
                  <div class="step-col-desc">
                    <input 
                      v-model="step.step" 
                      class="step-input"
                      :placeholder="t('testcaseForm.stepDescPlaceholder')"
                    />
                  </div>
                  <div class="step-col-expected">
                    <input 
                      v-model="step.expected" 
                      class="step-input"
                      :placeholder="t('testcaseForm.expectedPlaceholder')"
                    />
                  </div>
                  <div class="step-col-actions">
                    <button @click="removeStep(index)" class="action-btn delete-btn">
                      <span class="delete-icon">🗑</span>
                    </button>
                  </div>
                </div>
                <div class="add-step-row">
                  <button @click="addStep" class="add-step-btn">
                    + {{ t('testcaseForm.addStep') }}
                  </button>
                </div>
              </div>
            </div>

            <!-- 属性区域 -->
            <div class="properties-container">
              <h3 class="properties-title">{{ t('testcaseForm.properties') }}</h3>
              <div class="properties-grid">
                <!-- 用例类型 -->
                <div class="property-field property-field--stacked" :class="{ 'has-diff': hasDetailFieldDiff('case_type') }" id="diff-field-case_type">
                  <label class="field-label">{{ testcaseFieldLabel('case_type') }}</label>
                  <div v-if="hasDetailFieldDiff('case_type')" class="field-diff-panel field-diff-panel--stacked">
                    <div class="diff-header">
                      <span class="diff-label">{{ testcaseFieldLabel('case_type') }} · {{ t('cardForm.diffPreview') }}</span>
                      <div class="diff-actions">
                        <button type="button" @click="applyFieldChange('case_type')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                        <button type="button" @click="cancelFieldChange('case_type')" class="btn-cancel" title="取消">✗</button>
                      </div>
                    </div>
                    <div class="diff-content">
                      <div class="diff-row">
                        <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('case_type', detailFieldDiff('case_type')?.old) }}</span>
                      </div>
                      <div class="diff-row">
                        <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('case_type', detailFieldDiff('case_type')?.new) }}</span>
                      </div>
                    </div>
                  </div>
                  <select v-model="testcase.case_type" class="field-select" :class="{ 'field-with-diff': hasDetailFieldDiff('case_type') }">
                    <option value="功能测试">{{ t('testcaseForm.caseTypeFunctional') }}</option>
                    <option value="接口测试">{{ t('testcaseForm.caseTypeApi') }}</option>
                    <option value="性能测试">{{ t('testcaseForm.caseTypePerf') }}</option>
                    <option value="安全测试">{{ t('testcaseForm.caseTypeSecurity') }}</option>
                  </select>
                </div>

                <!-- 优先级 -->
                <div class="property-field property-field--stacked" :class="{ 'has-diff': hasDetailFieldDiff('priority') }" id="diff-field-priority">
                  <label class="field-label">{{ testcaseFieldLabel('priority') }}</label>
                  <div v-if="hasDetailFieldDiff('priority')" class="field-diff-panel field-diff-panel--stacked">
                    <div class="diff-header">
                      <span class="diff-label">{{ testcaseFieldLabel('priority') }} · {{ t('cardForm.diffPreview') }}</span>
                      <div class="diff-actions">
                        <button type="button" @click="applyFieldChange('priority')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                        <button type="button" @click="cancelFieldChange('priority')" class="btn-cancel" title="取消">✗</button>
                      </div>
                    </div>
                    <div class="diff-content">
                      <div class="diff-row">
                        <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('priority', detailFieldDiff('priority')?.old) }}</span>
                      </div>
                      <div class="diff-row">
                        <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('priority', detailFieldDiff('priority')?.new) }}</span>
                      </div>
                    </div>
                  </div>
                  <select v-model="testcase.priority" class="field-select" :class="{ 'field-with-diff': hasDetailFieldDiff('priority') }">
                    <option value="P0">P0</option>
                    <option value="P1">P1</option>
                    <option value="P2">P2</option>
                    <option value="P3">P3</option>
                  </select>
                </div>

                <!-- 测试类型 -->
                <div class="property-field property-field--stacked" :class="{ 'has-diff': hasDetailFieldDiff('test_type') }" id="diff-field-test_type">
                  <label class="field-label">{{ testcaseFieldLabel('test_type') }}</label>
                  <div v-if="hasDetailFieldDiff('test_type')" class="field-diff-panel field-diff-panel--stacked">
                    <div class="diff-header">
                      <span class="diff-label">{{ testcaseFieldLabel('test_type') }} · {{ t('cardForm.diffPreview') }}</span>
                      <div class="diff-actions">
                        <button type="button" @click="applyFieldChange('test_type')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                        <button type="button" @click="cancelFieldChange('test_type')" class="btn-cancel" title="取消">✗</button>
                      </div>
                    </div>
                    <div class="diff-content">
                      <div class="diff-row">
                        <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('test_type', detailFieldDiff('test_type')?.old) }}</span>
                      </div>
                      <div class="diff-row">
                        <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                        <span class="diff-value">{{ formatDiffFieldValue('test_type', detailFieldDiff('test_type')?.new) }}</span>
                      </div>
                    </div>
                  </div>
                  <select v-model="testcase.test_type" class="field-select" :class="{ 'field-with-diff': hasDetailFieldDiff('test_type') }">
                    <option value="手动">{{ t('testcaseForm.testTypeManual') }}</option>
                    <option value="自动">{{ t('testcaseForm.testTypeAuto') }}</option>
                    <option value="探索">{{ t('testcaseForm.testTypeExploratory') }}</option>
                  </select>
                </div>
              </div>
            </div>

          </div>
          
          <!-- 缺陷 Tab -->
          <div v-if="activeTab === 'defects'" class="tab-pane">
            <div
              class="form-group"
              :class="{ 'has-diff': hasDetailFieldDiff('related_defects') }"
              id="diff-field-related_defects"
            >
              <label class="field-label">{{ testcaseFieldLabel('related_defects') }}</label>
              <div v-if="hasDetailFieldDiff('related_defects')" class="field-diff-panel field-diff-panel--stacked">
                <div class="diff-header">
                  <span class="diff-label">{{ testcaseFieldLabel('related_defects') }} · {{ t('cardForm.diffPreview') }}</span>
                  <div class="diff-actions">
                    <button type="button" @click="applyFieldChange('related_defects')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button type="button" @click="cancelFieldChange('related_defects')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-row">
                    <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                    <span class="diff-value diff-value-multiline">{{ formatDiffFieldValue('related_defects', detailFieldDiff('related_defects')?.old) }}</span>
                  </div>
                  <div class="diff-row">
                    <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                    <span class="diff-value diff-value-multiline">{{ formatDiffFieldValue('related_defects', detailFieldDiff('related_defects')?.new) }}</span>
                  </div>
                </div>
              </div>
              <div class="related-defects" :class="{ 'field-with-diff': hasDetailFieldDiff('related_defects') }">
                <div 
                  v-for="(defect, index) in testcase.related_defects" 
                  :key="index"
                  class="defect-item"
                >
                  <div class="defect-info" @click="navigateToDefect(defect)">
                    <span class="defect-title">{{ defectDisplayTitle(defect) }}</span>
                  </div>
                  <button @click="removeDefect(index)" class="remove-defect-btn">×</button>
                </div>
                <button @click="openAddDefectDialog" class="add-defect-btn">
                  + {{ t('testcaseForm.addDefect') }}
                </button>
              </div>
            </div>
          </div>

          <!-- 执行 Tab -->
          <div v-if="activeTab === 'execution'" class="tab-pane">
            <div
              class="form-group property-field property-field--stacked"
              :class="{ 'has-diff': hasDetailFieldDiff('execution_result') }"
              id="diff-field-execution_result"
            >
              <label class="field-label">{{ testcaseFieldLabel('execution_result') }}</label>
              <div v-if="hasDetailFieldDiff('execution_result')" class="field-diff-panel field-diff-panel--stacked">
                <div class="diff-header">
                  <span class="diff-label">{{ testcaseFieldLabel('execution_result') }} · {{ t('cardForm.diffPreview') }}</span>
                  <div class="diff-actions">
                    <button type="button" @click="applyFieldChange('execution_result')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button type="button" @click="cancelFieldChange('execution_result')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-row">
                    <span class="diff-tag old">{{ t('cardForm.oldValue') }}</span>
                    <span class="diff-value">{{ formatDiffFieldValue('execution_result', detailFieldDiff('execution_result')?.old) }}</span>
                  </div>
                  <div class="diff-row">
                    <span class="diff-tag new">{{ t('cardForm.newValue') }}</span>
                    <span class="diff-value">{{ formatDiffFieldValue('execution_result', detailFieldDiff('execution_result')?.new) }}</span>
                  </div>
                </div>
              </div>
              <select
                v-model="testcase.execution_result"
                class="form-select field-select"
                :class="{ 'field-with-diff': hasDetailFieldDiff('execution_result') }"
              >
                <option value="">{{ t('testcaseExecution.notRun') }}</option>
                <option value="pass">{{ t('testcaseExecution.pass') }}</option>
                <option value="fail">{{ t('testcaseExecution.fail') }}</option>
                <option value="blocked">{{ t('testcaseExecution.blocked') }}</option>
                <option value="skip">{{ t('testcaseExecution.skip') }}</option>
              </select>
            </div>
            <div
              v-if="embedded && openDiagnosticTerminal && testcase.execution_result === 'fail'"
              class="form-group"
            >
              <button type="button" class="action-btn save-btn" @click="onOpenDiagnosticTerminal">
                {{ t('testcaseForm.openDiagnosticTerminal') }}
              </button>
              <p class="field-hint">{{ t('testcaseForm.diagnosticHint') }}</p>
            </div>
          </div>
        </div>

        </div>
        <!-- 保存和取消按钮：固定在底部，始终可见可点 -->
        <div class="footer-section">
          <div class="footer-actions">
            <button class="action-btn cancel-btn" @click="goBack">{{ t('common.cancel') }}</button>
            <button class="action-btn save-btn" @click="saveTestCase" :disabled="saving">
              {{ saving ? t('cardForm.saving') : t('common.save') }}
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧边栏：默认收起；展开后为固定宽度 -->
      <div class="right-panel-column">
        <button
          v-show="!isRightSidebarOpen"
          type="button"
          class="sidebar-expand-tab"
          :title="t('cardForm.expandSidebar')"
          :aria-label="t('cardForm.expandSidebar')"
          @click="isRightSidebarOpen = true"
        >
          <img src="../assets/resize-icon.svg" alt="" class="resize-icon resize-icon--expand" />
        </button>
        <div class="sidebar-right" :class="{ 'sidebar-right--open': isRightSidebarOpen }">
        <div class="resize-handle" role="button" tabindex="0" :title="t('cardForm.collapseSidebar')" @click="toggleRightSidebar" @keydown.enter.prevent="toggleRightSidebar" @keydown.space.prevent="toggleRightSidebar">
          <img src="../assets/resize-icon.svg" alt="" class="resize-icon" :class="{ 'rotated': isRightSidebarOpen }" />
        </div>
        <!-- 所属项目 -->
        <div class="sidebar-section">
          <h3 class="sidebar-title">{{ t('cardForm.project') }}</h3>
          <div class="project-select">
            <label class="select-label">{{ t('cardForm.projectName') }}:</label>
            <select
              class="form-select"
              :value="testcase.project_id == null ? '' : String(testcase.project_id)"
              @change="onProjectSelectChange"
            >
              <option value="">{{ t('cardForm.pleaseSelect') }}</option>
              <option v-for="project in availableProjects" :key="project.id" :value="String(project.id)">
                {{ project.name }}
              </option>
            </select>
          </div>
        </div>
        

        <!-- 关联文档 -->
        <div class="sidebar-section">
          <div class="section-header">
            <div class="header-left">
              <span class="header-icon">📄</span>
              <span class="header-title">{{ t('cardForm.relatedDocs') }}</span>
            </div>
            <button class="ai-recommend-btn">
              <span class="ai-icon">🤖</span>
              <span class="ai-text">{{ t('cardForm.recommendLink') }}</span>
            </button>
          </div>
          <div class="document-fields">
            <div class="field-row">
              <span class="field-label">{{ t('cardForm.docType') }}:</span>
              <span class="field-value">{{ testcase.document_type || t('cardForm.otherDoc') }}</span>
            </div>
            <div class="field-row">
              <span class="field-label">{{ t('cardForm.fileLink') }}:</span>
              <button class="copy-link-btn" @click="copyDocumentLink">
                {{ t('cardForm.copyKbLink') }}
              </button>
            </div>
          </div>
        </div>

        <!-- 附件 -->
        <div class="sidebar-section">
          <div class="section-header">
            <div class="header-left">
              <span class="header-icon">📎</span>
              <span class="header-title">{{ t('cardForm.attachments') }}</span>
            </div>
            <button class="add-attachment-btn" @click="addAttachment">
              <span class="plus-icon">+</span>
            </button>
          </div>
          <div class="attachment-list">
            <div v-for="(attachment, index) in (testcase.attachments || [])" :key="index" class="attachment-item">
              <span class="attachment-name">{{ attachment.name }}</span>
              <button class="remove-attachment-btn" @click="removeAttachment(index)">×</button>
            </div>
            <div v-if="!testcase.attachments || testcase.attachments.length === 0" class="no-attachments">
              {{ t('cardForm.noAttachments') }}
            </div>
          </div>
          <input 
            ref="fileInput" 
            type="file" 
            multiple 
            @change="handleFileUpload" 
            style="display: none"
          />
        </div>

        <!-- 评论：历史只读 + 仅追加；对话可带 append_comment diff -->
        <div
          id="diff-field-append_comment"
          class="sidebar-section comment-section"
          :class="{ 'has-diff': hasDetailFieldDiff('append_comment') }"
        >
          <h3 class="sidebar-title">{{ t('testcaseComment.historyTitle') }}</h3>
          <div v-if="hasDetailFieldDiff('append_comment')" class="field-diff-panel field-diff-panel--stacked comment-diff-panel">
            <div class="diff-header">
              <span class="diff-label">{{ testcaseFieldLabel('append_comment') }} · {{ t('cardForm.diffPreview') }}</span>
              <div class="diff-actions">
                <button type="button" @click="applyFieldChange('append_comment')" class="btn-confirm" :title="t('cardForm.adoptTitle')">✓</button>
                <button type="button" @click="cancelFieldChange('append_comment')" class="btn-cancel" :title="t('cardForm.rejectTitle')">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-row">
                <span class="diff-tag new">{{ t('testcaseComment.newComment') }}</span>
                <span class="diff-value diff-value-multiline">{{ formatDiffFieldValue('append_comment', detailFieldDiff('append_comment')?.new) }}</span>
              </div>
            </div>
          </div>
          <div v-if="testcaseComments.length" class="comment-timeline">
            <div
              v-for="c in testcaseComments"
              :key="c.id"
              class="comment-item"
              :class="{ 'is-reply': c.parent_id, 'is-pending': c.pending }"
            >
              <div class="comment-item-meta">
                <span class="comment-author">{{ c.user_name || '—' }}</span>
                <span v-if="c.parent_id" class="comment-reply-tag">{{ t('testcaseComment.replyTo', { name: c.parent_user_name || '—' }) }}</span>
                <span class="comment-time">{{ formatCommentTime(c.created_at) }}</span>
                <span v-if="c.source_message_id" class="comment-op-tag">{{ t('testcaseComment.linkedOp') }}</span>
                <span v-if="c.pending" class="comment-pending-tag">{{ t('testcaseComment.pending') }}</span>
                <button
                  v-if="isEdit && testcaseId && !c.pending"
                  type="button"
                  class="comment-reply-btn"
                  @click="startReplyToComment(c)"
                >
                  {{ t('testcaseComment.reply') }}
                </button>
              </div>
              <div class="comment-item-body" v-html="c.content"></div>
            </div>
          </div>
          <div v-else class="comment-empty">{{ t('testcaseComment.empty') }}</div>
          <div v-if="replyingTo" class="comment-reply-hint">
            {{ t('testcaseComment.replying', { name: replyingTo.user_name || '—' }) }}
            <button type="button" class="comment-reply-cancel" @click="cancelReplyToComment">{{ t('common.cancel') }}</button>
          </div>
          <h4 class="comment-input-subtitle">{{ replyingTo ? t('testcaseComment.inputReplyTitle') : t('testcaseComment.inputTitle') }}</h4>
          <div ref="commentInputContainerRef" class="comment-input-container">
            <template v-if="!commentEditorActive">
              <textarea
                class="comment-textarea-simple"
                readonly
                rows="3"
                :value="commentDraftText"
                :placeholder="t('testcaseComment.placeholder')"
                @click="activateCommentEditor"
              />
              <div class="comment-count">{{ commentDraftLength }} / 500</div>
            </template>
            <template v-else>
              <RichTextHtmlEditor
                v-model="commentDraft"
                variant="compact"
                submit-on-enter
                :placeholder="t('testcaseComment.placeholder')"
                class="rich-editor"
                @submit="submitCommentDraft"
              />
              <div class="comment-editor-actions">
                <button
                  v-if="isEdit && testcaseId"
                  type="button"
                  class="comment-submit-btn"
                  :disabled="commentSubmitting || !commentDraftLength"
                  @click="submitCommentDraft"
                >
                  {{ t('testcaseComment.submit') }}
                </button>
              </div>
              <div class="editor-count">{{ commentDraftLength }} / 500</div>
            </template>
          </div>
        </div>

        </div>
      </div>
    </div>

    <!-- 添加缺陷对话框 -->
    <div v-if="showAddDefectDialog" class="dialog-overlay" @click.self="showAddDefectDialog = false">
      <div class="dialog-container">
        <div class="dialog-header">
          <h3>添加缺陷</h3>
          <button @click="showAddDefectDialog = false" class="close-btn">×</button>
        </div>
        <div class="dialog-body">
          <!-- 搜索框 -->
          <div class="search-box">
            <input 
              v-model="defectSearchText"
              type="text"
              placeholder="输入 Bug ID 或标题搜索..."
              class="search-input"
              @keyup.enter="searchDefects"
            />
            <button @click="searchDefects" class="search-btn" :disabled="defectSearchLoading">搜索</button>
          </div>

          <div v-if="defectSearchText.trim()" class="defect-search-results">
            <div v-if="defectSearchLoading" class="defect-search-hint">搜索中…</div>
            <div v-else-if="defectSearchResults.length === 0" class="defect-search-hint">未找到匹配的缺陷（当前计划范围内）</div>
            <div
              v-else
              v-for="bug in defectSearchResults"
              :key="bug.id"
              class="bug-item defect-search-item"
              :class="{ selected: isDefectSelected(bug.id) }"
              @click="toggleDefectSelection(bug, bug.plan_id || testcase.plan_id || testcase.plan)"
            >
              <div class="checkbox" :class="{ checked: isDefectSelected(bug.id) }">
                <span v-if="isDefectSelected(bug.id)" class="checkmark">✓</span>
              </div>
              <div class="bug-info">
                <span class="bug-id">Bug-{{ bug.id }}</span>
                <span class="bug-title">{{ bug.title }}</span>
              </div>
            </div>
          </div>

          <div class="bug-tree-container" v-show="!defectSearchText.trim()">
            <div class="tree-header">
              <span class="tree-title">缺陷列表</span>
              <button @click="loadAllBugs" class="refresh-btn" title="刷新">🔄</button>
            </div>
            <div class="bug-tree">
              <DefectPickerTreeNode
                :plans="bugPlans"
                :depth="0"
                :is-defect-selected="isDefectSelected"
                @toggle-plan="togglePlanExpand"
                @toggle-card="toggleCardExpand"
                @toggle-bug="toggleDefectSelection"
              />
            </div>
          </div>
        </div>
        <div class="dialog-footer">
          <button @click="showAddDefectDialog = false" class="btn-cancel">取消</button>
          <button @click="confirmAddDefects" class="btn-confirm">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, onUnmounted, onActivated, computed, nextTick, watch, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getTestcaseFieldLabel,
  formatTestcaseModifyFieldValue,
  formatTestcaseSelectFieldLabel,
  normalizeTestcaseModifyFieldKey,
  getTestcaseModifyModKeys,
  normalizeTestcaseStepsForEditor,
  normalizeTestcaseSelectFieldForEditor,
  normalizeTestcaseExecutionResultForSelect,
  normalizeTestcaseRelatedDefectIds,
  formatTestcaseRelatedDefectsForDisplay,
  isPlaceholderTestcaseDefectTitle,
  coerceTestcaseRemarkToAppendComment,
  intentRequestsTestcaseComment,
  isTestcaseSelectDetailField,
  TESTCASE_MONACO_DETAIL_FIELDS,
  TESTCASE_SELECT_DETAIL_FIELDS
} from '../utils/testcaseModifyFields.js'
import { useRoute, useRouter } from 'vue-router'
import { BACKEND_BASE_URL, createTestCase, getTestCaseDetail, updateTestCase, deleteTestCase, addTestCaseComment, getProjects, getProjectEditContext, getProjectDetail, getProjectPlans, getPlanDetail, getProjectCards, getProjectBugs, getProjectMembers, getCurrentUser, getBugDetail } from '../api'
import DefectPickerTreeNode from './DefectPickerTreeNode.vue'
import { snowflakeIdStr, normalizePlanId, isEmptyPlanKey } from '../utils/snowflakeId.js'
import { personPrimaryLabel, personSecondaryLabel, applyDefaultAssigneeOnCreate } from '../utils/personLabel'
import { richTextHtmlDisplayLength, richTextHtmlHasContent } from '../utils/richTextContent.js'
import { ensureEditorHtmlContent } from '../utils/uploadImageUrl.js'
import { htmlToPlainText } from '../utils/richTextContent.js'
import { defineAsyncComponent } from 'vue'
import RichTextHtmlEditor from './RichTextHtmlEditor.vue'
import {
  getPendingModifyDiffForDetail,
  clearPendingModifyDiffForDetail
} from '../utils/bcdSessionStore.js'

const MonacoDiffEditor = defineAsyncComponent(() => import('./MonacoDiffEditor.vue'))

/** 与后端 / 历史数据兼容：test_case、testcase、TESTCASE 等 */
function isTestCasePlanType(planType) {
  const s = String(planType || '').toLowerCase().replace(/-/g, '_')
  return s === 'test_case' || s === 'testcase'
}

export default {
  name: 'NewTestCase',
  components: { MonacoDiffEditor, RichTextHtmlEditor, DefectPickerTreeNode },
  props: {
    id: {
      type: [String, Number],
      default: null
    },
    project_id: {
      type: [String, Number],
      default: null
    },
    plan_id: {
      type: [String, Number],
      default: null
    },
    /** 创建时关联的卡片ID，用于类型校验 */
    card_id: {
      type: [String, Number],
      default: null
    },
    edit: {
      type: Boolean,
      default: false
    },
    show_diff: {
      type: Boolean,
      default: false
    },
    pending_diff_seq: {
      type: Number,
      default: 0
    },
    /** 嵌入详情：沙箱跳转时默认 Tab（basic | defects | execution） */
    initial_tab: {
      type: String,
      default: null
    },
    embedded: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'titleLoaded'],
  setup(props, { emit }) {
    const route = useRoute()
    const router = useRouter()
    const { t } = useI18n()

    const testcaseFieldLabel = (field) => getTestcaseFieldLabel(t, field)

    const buildRelatedDefectTitleMap = () => {
      const map = {}
      for (const d of testcase.related_defects || []) {
        if (d?.id == null) continue
        const id = String(d.id).trim()
        const title = String(d.title || '').trim()
        if (id && title && !isPlaceholderTestcaseDefectTitle(id, title)) {
          map[id] = title
        }
      }
      return map
    }

    const defectDisplayTitle = (defect) => {
      const id = String(defect?.id ?? '').trim()
      const title = String(defect?.title ?? '').trim()
      if (title && !isPlaceholderTestcaseDefectTitle(id, title)) return title
      return id ? `Bug-${id}` : '—'
    }

    const hydrateRelatedDefectTitles = async () => {
      const list = testcase.related_defects
      if (!Array.isArray(list) || list.length === 0) return
      await Promise.all(
        list.map(async (d, idx) => {
          if (d?.id == null) return
          const id = String(d.id).trim()
          if (!id || !isPlaceholderTestcaseDefectTitle(id, d.title)) return
          try {
            const res = await getBugDetail(id)
            const payload = res?.data
            const bug =
              payload?.bug ??
              payload?.data ??
              (payload?.success && payload?.title != null ? payload : null)
            const title = String(bug?.title ?? '').trim()
            if (!title) return
            const planId = bug?.plan_id ?? bug?.planId ?? d.plan_id
            list[idx] = { ...d, id, title, plan_id: planId ?? d.plan_id }
          } catch (_e) {
            /* ignore */
          }
        })
      )
    }

    const formatDiffFieldValue = (field, val) => {
      const nk = normalizeTestcaseModifyFieldKey(field)
      if (nk === 'append_comment') {
        return formatTestcaseModifyFieldValue(field, val, { maxLen: 8000, t })
      }
      if (nk === 'related_defects') {
        return formatTestcaseRelatedDefectsForDisplay(val, {
          t,
          titleMap: buildRelatedDefectTitleMap()
        })
      }
      if (isTestcaseSelectDetailField(nk)) {
        return formatTestcaseSelectFieldLabel(nk, val, t)
      }
      const s = formatTestcaseModifyFieldValue(field, val, {
        maxLen: 8000,
        t,
        titleMap: buildRelatedDefectTitleMap()
      })
      return s || t('chat.notSet')
    }

    const isMonacoPendingModifyField = (field) => {
      const nk = normalizeTestcaseModifyFieldKey(field)
      return TESTCASE_MONACO_DETAIL_FIELDS.includes(nk)
    }

    const pendingMonacoModifyCount = () => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return 0
      return Object.keys(mods).filter(
        (k) => !String(k).startsWith('_') && isMonacoPendingModifyField(k)
      ).length
    }
    const detailFieldDiff = (field) => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return null
      for (const k of getTestcaseModifyModKeys(field, field)) {
        const m = mods[k]
        if (m && typeof m === 'object' && ('old' in m || 'new' in m)) return m
      }
      return null
    }
    const hasDetailFieldDiff = (field) => !!detailFieldDiff(field)
    const clearDetailFieldDiff = (field) => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return
      for (const k of getTestcaseModifyModKeys(field, field)) delete mods[k]
    }
    const restoreDetailFieldOld = (field) => {
      const nk = normalizeTestcaseModifyFieldKey(field)
      const mod = detailFieldDiff(field)
      if (!mod || mod.old === undefined) return
      let val = mod.old
      if (nk === 'steps') {
        testcase.steps = normalizeTestcaseStepsForEditor(val)
        return
      }
      if (nk === 'related_defects') {
        const ids = normalizeTestcaseRelatedDefectIds(mod.old)
        const byId = new Map(
          (testcase.related_defects || []).map((d) => [String(d.id), d])
        )
        testcase.related_defects = ids.map((id) => {
          const hit = byId.get(String(id))
          return hit ? { ...hit, id } : { id, title: '' }
        })
        void hydrateRelatedDefectTitles()
        return
      }
      if (nk === 'preconditions') {
        testcase.preconditions = ensureEditorHtmlContent(val || '')
        return
      }
      if (nk === 'remark') {
        return
      }
      if (isTestcaseSelectDetailField(nk)) {
        testcase[nk] = normalizeTestcaseSelectFieldForEditor(nk, val)
        return
      }
      if (Object.prototype.hasOwnProperty.call(testcase, nk)) {
        testcase[nk] = val
      }
    }

    const mapTestcaseModifyApiField = (nk) => {
      if (nk === 'precondition') return 'preconditions'
      return nk
    }

    /** 与 NewBug.applyPendingModificationsToBugForm 一致：show_diff 时将 new 灌入表单 */
    const applyPendingModificationsToTestcaseForm = () => {
      if (!pendingDiff.value?.modifications) return
      for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
        if (String(field).startsWith('_')) continue
        const nk = normalizeTestcaseModifyFieldKey(field)
        if (!data || typeof data !== 'object' || !('new' in data)) continue
        const nv = data.new
        if (nv === undefined) continue
        if (nk === 'related_defects' || nk === 'append_comment') {
          continue
        }
        if (typeof nv === 'string' && !String(nv).trim()) continue
        applyDetailFieldToTestcase(nk, nv)
      }
    }

    const idStrOrNull = (v) => {
      const raw = Array.isArray(v) ? v[0] : v
      if (raw == null || raw === '') return null
      // 兼容父组件误传 ref 对象（极少见），优先取 value
      const x = (typeof raw === 'object' && raw !== null && 'value' in raw) ? raw.value : raw
      const s = snowflakeIdStr(x)
      return s || null
    }

    /** 与路由、props 同步解析项目 ID（雪花勿 parseInt/Number） */
    const readProjectIdFromRoute = () => {
      return (
        idStrOrNull(route.query.project_id) ??
        idStrOrNull(props.project_id)
      )
    }

    const rawTestcaseId =
      props.id != null && props.id !== ''
        ? props.id
        : route.query.id != null && route.query.id !== ''
          ? route.query.id
          : null
    const testcaseId =
      rawTestcaseId != null && String(rawTestcaseId).trim() !== ''
        ? (idStrOrNull(rawTestcaseId) || String(rawTestcaseId).trim())
        : null
    const isEdit = !!testcaseId

    const openDiagnosticTerminal = inject('openDiagnosticTerminal', null)
    const testcaseDraftPreset = inject('testcaseDraftPreset', null)

    const loading = ref(false)
    const saving = ref(false)
    const isRightSidebarOpen = ref(false)
    const toggleRightSidebar = () => {
      isRightSidebarOpen.value = !isRightSidebarOpen.value
    }
    const showStatusDropdown = ref(false)
    const showAssigneeDropdown = ref(false)
    const showAddDefectDialog = ref(false)
    const activeTab = ref('basic')
    const fileInput = ref(null)
    const testcaseComments = ref([])
    const commentDraft = ref('')
    const commentSubmitting = ref(false)
    const replyingTo = ref(null)
    const commentEditorActive = ref(false)
    const commentInputContainerRef = ref(null)
    const activateCommentEditor = () => {
      commentEditorActive.value = true
    }
    const finishCommentEditor = () => {
      commentEditorActive.value = false
    }
    const COMMENT_EDITOR_POPUP_SEL = '.-t-v-popup-panel, .-t-v-popup-panel-h, .-t-v-h-content'
    const onCommentEditorOutsidePointerDown = (e) => {
      if (!commentEditorActive.value) return
      const root = commentInputContainerRef.value
      if (!root) return
      const target = e.target
      if (!(target instanceof Node)) return
      if (root.contains(target)) return
      if (target.closest?.(COMMENT_EDITOR_POPUP_SEL)) return
      finishCommentEditor()
    }
    watch(commentEditorActive, (active) => {
      if (active) {
        nextTick(() => {
          document.addEventListener('pointerdown', onCommentEditorOutsidePointerDown, true)
        })
      } else {
        document.removeEventListener('pointerdown', onCommentEditorOutsidePointerDown, true)
      }
    })
    onUnmounted(() => {
      document.removeEventListener('pointerdown', onCommentEditorOutsidePointerDown, true)
    })
    const defectSearchText = ref('')
    const defectSearchResults = ref([])
    const defectSearchLoading = ref(false)
    const bugPlans = ref([])

    const projectInfo = reactive({
      name: ''
    })

    // 待确认的 diff 数据
    const pendingDiff = ref(null)
    /** 采纳后递增，迫使富文本编辑器用库内最新 HTML 重挂载 */
    const preconditionsEditorRef = ref(null)

    const testcase = reactive({
      title: '',
      status: 'draft',
      case_type: '功能测试',
      priority: 'P3',
      test_type: '手动',
      preconditions: '',
      steps: [{ step: '', expected: '' }],
      requirement_id: null,
      related_defects: [],
      estimated_time: 0,
      version: 'v1',
      plan_id: null,
      assignee: [],
      assignee_id: null,
      execution_result: '',
      associate_project: true,
      project_id: readProjectIdFromRoute(),
      plan: '',
      document_type: '',
      attachments: []
    })

    watch(
      () => testcaseDraftPreset?.value?.token ?? 0,
      async (tok) => {
        if (!tok || !testcaseDraftPreset?.value?.description) return
        if (isEdit) return
        const block = String(testcaseDraftPreset.value.description).trim()
        if (!block) return
        const fragment = `【终端关联】\n${block}`
        await nextTick()
        const cur = htmlToPlainText(testcase.preconditions || '').trim()
        testcase.preconditions = cur
          ? ensureEditorHtmlContent(`${cur}\n\n${fragment}`)
          : ensureEditorHtmlContent(fragment)
      }
    )

    /** 当前页面应使用的 project_id（编辑/新建/嵌入都兜底） */
    const currentProjectId = computed(() => {
      return (
        idStrOrNull(route.query.project_id) ??
        idStrOrNull(props.project_id) ??
        idStrOrNull(testcase.project_id)
      )
    })

    const currentUser = ref(null)
    const testcasePlans = ref([])
    const selectableTestcasePlans = computed(() =>
      testcasePlans.value.filter((p) => p?.value !== 'unplanned')
    )
    const availableProjects = ref([])
    const projectMembers = ref([])
    const assigneeSearchText = ref('')
    const showPlanDropdown = ref(false)

    const availableStatuses = [
      { value: 'draft', label: '草稿' },
      { value: 'review', label: '评审' },
      { value: 'active', label: '生效' },
      { value: 'archived', label: '归档' }
    ]

    const getStatusText = (status) => {
      const statusObj = availableStatuses.find(s => s.value === status)
      return statusObj ? statusObj.label : status
    }

    const formatTestcasePriorityLabel = (v) => {
      if (v == null || String(v).trim() === '') return '未设置'
      const raw = String(v).trim()
      const u = raw.toUpperCase()
      const map = { P0: 'P0', P1: 'P1', P2: 'P2', P3: 'P3' }
      if (map[u]) return map[u]
      const low = raw.toLowerCase()
      const fromP = { p0: 'P0', p1: 'P1', p2: 'P2', p3: 'P3', p4: 'P3' }
      return fromP[low] || raw
    }

    const getAssigneeDisplayText = () => {
      if (!testcase.assignee || testcase.assignee.length === 0) {
        return '未指派'
      }
      
      const ids = Array.isArray(testcase.assignee) ? testcase.assignee : [testcase.assignee]
      const names = ids.map(id => {
        const sid = String(id)
        const member = projectMembers.value.find(m => String(m.id) === sid)
        if (member) return personPrimaryLabel(member)
        if (currentUser.value && String(currentUser.value.id) === sid) {
          return personPrimaryLabel(currentUser.value)
        }
        if (/^\d+$/.test(sid)) return `用户#${sid}`
        return personPrimaryLabel({ name: sid, email: sid })
      })
      
      if (names.length === 1) {
        return names[0]
      } else {
        return `${names[0]} 等 ${names.length} 人`
      }
    }

    const isAssigneeSelected = (assigneeValue) => {
      const want = String(assigneeValue ?? '')
      if (!want) return false
      if (testcase.assignee_id != null && testcase.assignee_id !== '') {
        return String(testcase.assignee_id) === want
      }
      if (Array.isArray(testcase.assignee)) {
        return testcase.assignee.some((x) => String(x) === want)
      }
      return testcase.assignee != null && String(testcase.assignee) === want
    }

    // 切换负责人（再点已选中的项 = 取消指派；后端仅支持单负责人）
    const toggleAssignee = (assigneeValue) => {
      const want = String(assigneeValue ?? '')
      if (!want) return
      if (isAssigneeSelected(want)) {
        testcase.assignee_id = null
        testcase.assignee = []
        return
      }
      const parsed = parseInt(want, 10)
      testcase.assignee_id = Number.isFinite(parsed) ? parsed : want
      testcase.assignee = [want]
    }

    const togglePlanDropdown = () => {
      showPlanDropdown.value = !showPlanDropdown.value
    }

    const selectedPlanDisplayName = ref('')

    const planIdsMatch = (a, b) => {
      const sa = snowflakeIdStr(a) || String(a ?? '')
      const sb = snowflakeIdStr(b) || String(b ?? '')
      return sa !== '' && sb !== '' && sa === sb
    }

    const applyPlanFromProps = async (planIdProp) => {
      if (isEdit) return
      const pid = normalizePlanId(planIdProp)
      if (!pid) return
      if (!planIdsMatch(testcase.plan, pid)) {
        testcase.plan = pid
        testcase.plan_id = pid
      }
      await ensurePlanOptionVisible(pid)
    }

    const applyInitialPlanForCreate = async () => {
      if (isEdit) return
      const pid =
        normalizePlanId(props.plan_id) ?? normalizePlanId(route.query.plan_id)
      if (pid) {
        await applyPlanFromProps(pid)
      } else if (isEmptyPlanKey(testcase.plan)) {
        testcase.plan = ''
        testcase.plan_id = null
      }
    }

    const selectPlan = (planValue) => {
      const id = normalizePlanId(planValue) || snowflakeIdStr(planValue) || String(planValue)
      testcase.plan = id
      testcase.plan_id = idStrOrNull(id)
      selectedPlanDisplayName.value =
        testcasePlans.value.find((p) => planIdsMatch(p.value, id))?.label || ''
      showPlanDropdown.value = false
    }

    const getSelectedPlanDisplayText = computed(() => {
      if (isEmptyPlanKey(testcase.plan)) {
        return t('cardForm.selectPlan')
      }
      const key = snowflakeIdStr(testcase.plan) || String(testcase.plan)
      const plan = testcasePlans.value.find(
        (p) => p.value !== 'unplanned' && (snowflakeIdStr(p.value) || String(p.value)) === key
      )
      return plan?.label || selectedPlanDisplayName.value || '…'
    })

    const ensurePlanOptionVisible = async (planKey) => {
      if (isEmptyPlanKey(planKey)) return
      const key = snowflakeIdStr(planKey) || String(planKey)
      const existing = testcasePlans.value.find((p) => planIdsMatch(p.value, key))
      if (existing) {
        selectedPlanDisplayName.value = existing.label || ''
        return
      }
      try {
        const planKeyForApi = idStrOrNull(key) || String(key)
        const resp = await getPlanDetail(planKeyForApi)
        if (resp.data?.success && resp.data.plan) {
          const pl = resp.data.plan
          const idStr = snowflakeIdStr(pl.id) || String(pl.id)
          selectedPlanDisplayName.value = pl.name || ''
          if (!testcasePlans.value.some((p) => (snowflakeIdStr(p.value) || String(p.value)) === idStr)) {
            testcasePlans.value = [
              ...testcasePlans.value.filter((p) => p.value !== 'unplanned'),
              { value: idStr, label: pl.name, icon: '🧪' }
            ]
          }
        }
      } catch (e) {
        console.warn('补全计划名称失败:', e)
      }
    }

    const refreshProjectPlans = async () => {
      if (testcase.project_id) {
        await fetchProjectPlans(testcase.project_id)
      }
    }

    const fetchProjectPlans = async (projectId) => {
      try {
        console.log('fetchProjectPlans: 开始加载项目计划, projectId:', projectId)
        const response = await getProjectPlans(projectId)
        console.log('fetchProjectPlans: API响应:', response.data)
        if (response.data.success) {
          const allPlans = response.data.plans || []
          console.log('fetchProjectPlans: 所有计划:', allPlans)
          const plans = allPlans
          console.log('fetchProjectPlans: 计划列表:', plans)
          testcasePlans.value = plans.map((p) => ({
            value: snowflakeIdStr(p.id) || String(p.id),
            label: p.name,
            icon: '🧪'
          }))
          console.log('fetchProjectPlans: 最终testcasePlans:', testcasePlans.value)
        }
      } catch (error) {
        console.error('获取项目计划失败:', error)
      }
    }

    const setTestcasePlansFromTree = async (plansTree) => {
      const result = []
      const walk = (nodes) => {
        ;(nodes || []).forEach(p => {
          result.push(p)
          if (p.children && p.children.length) walk(p.children)
        })
      }
      walk(plansTree || [])
      testcasePlans.value = result.map((p) => ({
        value: snowflakeIdStr(p.id) || String(p.id),
        label: p.name,
        icon: '🧪'
      }))
      await nextTick()
    }

    const fetchProjectMembers = async (projectId) => {
      try {
        const response = await getProjectMembers(projectId)
        if (response.data.success) {
          projectMembers.value = response.data.members || []
        }
      } catch (error) {
        console.error('获取项目成员失败:', error)
      }
    }

    const fetchCurrentUser = async () => {
      try {
        const response = await getCurrentUser()
        if (response.data.success) {
          currentUser.value = response.data.user
        }
      } catch (error) {
        console.error('获取当前用户失败:', error)
      }
    }

    const loadUserProjectsForSelect = async () => {
      try {
        const resp = await getProjects()
        if (resp.data?.success && Array.isArray(resp.data.projects)) {
          availableProjects.value = resp.data.projects.slice()
        }
      } catch (e) {
        console.error('加载项目列表失败:', e)
      }
    }

    const mergeProjectIntoOptions = (prj) => {
      if (!prj || prj.id == null) return
      if (!availableProjects.value.find(p => p.id == prj.id)) {
        availableProjects.value.push({
          id: prj.id,
          name: prj.name,
          description: prj.description,
          status: prj.status
        })
      }
    }

    const loadProjectWorkspace = async (pid) => {
      const projectIdStr = idStrOrNull(pid)
      if (!projectIdStr) return
      try {
        const resp = await getProjectEditContext(projectIdStr)
        if (resp.data?.success) {
          const prj = resp.data.project
          if (prj) {
            Object.assign(projectInfo, { name: prj.name || '' })
            mergeProjectIntoOptions(prj)
          }
          projectMembers.value = resp.data.members || []
          await setTestcasePlansFromTree(resp.data.plans || [])
        } else {
          throw new Error(resp.data?.error || 'edit-context 未返回 success')
        }
      } catch (e) {
        console.error('获取编辑页上下文失败:', e)
        try {
          const detail = await getProjectDetail(projectIdStr)
          if (detail.data?.success && detail.data.project) {
            const prj = detail.data.project
            Object.assign(projectInfo, { name: prj.name || '' })
            mergeProjectIntoOptions(prj)
          }
          await fetchProjectPlans(projectIdStr)
          await fetchProjectMembers(projectIdStr)
        } catch (e2) {
          console.error('回退加载项目详情失败:', e2)
        }
      }
    }

    const toggleStatusDropdown = () => {
      showStatusDropdown.value = !showStatusDropdown.value
    }

    const selectStatus = (status) => {
      testcase.status = status
      showStatusDropdown.value = false
    }

    const toggleAssigneeDropdown = () => {
      showAssigneeDropdown.value = !showAssigneeDropdown.value
    }

    const addStep = () => {
      testcase.steps.push({ step: '', expected: '' })
    }

    const removeStep = (index) => {
      if (testcase.steps.length > 1) {
        testcase.steps.splice(index, 1)
      }
    }

    const confirmAddDefects = () => {
      showAddDefectDialog.value = false
    }

    const openAddDefectDialog = async () => {
      showAddDefectDialog.value = true
      // 打开对话框时加载 Bug 计划
      if (testcase.project_id && bugPlans.value.length === 0) {
        await fetchBugPlans(testcase.project_id)
      }
    }

    const isDefectSelected = (defectId) => {
      const idStr = defectId != null ? String(defectId) : ''
      return testcase.related_defects.some(d => d.id.toString() === idStr)
    }

    const toggleDefectSelection = (bug, planId) => {
      const index = testcase.related_defects.findIndex(d => d.id.toString() === bug.id.toString())
      if (index > -1) {
        testcase.related_defects.splice(index, 1)
      } else {
        testcase.related_defects.push({
          id: bug.id,
          title: bug.title,
          plan_id: planId // 存储 bug 所在的计划 ID
        })
      }
    }

    const removeDefect = (index) => {
      testcase.related_defects.splice(index, 1)
    }

    const navigateToDefect = async (defect) => {
      // 导航到 Bug 详情并展开计划，复用 grep-navigate 事件机制
      // 优先使用缺陷自身的 plan_id，否则使用测试用例的计划
      const planId = defect.plan_id || testcase.plan_id || testcase.plan
      const bugId = defect.id
      
      console.log('navigateToDefect: 准备导航到 Bug', { planId, bugId, defect })
      
      // 无有效 planId 时不传递 navigate_plan 参数
      if (isEmptyPlanKey(planId) || !idStrOrNull(planId)) {
        console.log('navigateToDefect: 无有效计划ID，跳转到项目详情页')
        router.push(`/project-detail/${testcase.project_id}`)
        return
      }
      
      // 跳转到项目详情页，带上参数
      router.push(`/project-detail/${testcase.project_id}?navigate_plan=${planId}&navigate_bug=${bugId}`)
    }

    const searchDefects = async () => {
      const q = (defectSearchText.value || '').trim()
      if (!q) {
        defectSearchResults.value = []
        return
      }
      const projectId = snowflakeIdStr(testcase.project_id) || testcase.project_id
      if (!projectId) {
        alert('请先选择所属项目')
        return
      }
      defectSearchLoading.value = true
      try {
        const rawPlan = testcase.plan_id ?? testcase.plan
        const params = {}
        if (rawPlan != null && !isEmptyPlanKey(rawPlan)) {
          params.plan_id = snowflakeIdStr(rawPlan) || String(rawPlan)
        }
        const response = await getProjectBugs(projectId, 1, 500, params)
        const list = response.data?.bugs || response.data?.badcases || []
        const ql = q.toLowerCase()
        defectSearchResults.value = list.filter((b) => {
          const id = String(b.id ?? '')
          const title = String(b.title ?? '').toLowerCase()
          return id.includes(q) || title.includes(ql)
        })
      } catch (error) {
        console.error('搜索失败:', error)
        defectSearchResults.value = []
      } finally {
        defectSearchLoading.value = false
      }
    }

    const findPlanById = (plans, planValue) => {
      for (const plan of plans) {
        if (plan.value === planValue) {
          return plan
        }
        if (plan.children && plan.children.length > 0) {
          const found = findPlanById(plan.children, planValue)
          if (found) return found
        }
      }
      return null
    }

    const isLeafPlanNode = (plan) => !plan?.children || plan.children.length === 0

    const togglePlanExpand = (planValue) => {
      const plan = findPlanById(bugPlans.value, planValue)
      if (!plan) return
      plan.expanded = !plan.expanded
      if (plan.expanded && isLeafPlanNode(plan) && plan.cards === null) {
        loadCardsForPlan(planValue)
      }
    }

    const toggleCardExpand = (planValue, cardValue) => {
      const plan = findPlanById(bugPlans.value, planValue)
      if (!plan?.cards) return
      const card = plan.cards.find((c) => c.value === cardValue)
      if (!card) return
      card.expanded = !card.expanded
      if (card.expanded && card.bugs === null) {
        loadBugsForCard(planValue, cardValue)
      }
    }

    const fetchBugPlans = async (projectId) => {
      try {
        const response = await getProjectPlans(projectId)
        if (response.data.success) {
          const allPlans = response.data.plans || []
          const processPlanTree = (plans, level = 0) => {
            return plans.map(p => ({
              value: snowflakeIdStr(p.id) || String(p.id),
              label: p.name,
              icon: '📋',
              level,
              expanded: false,
              cards: null,
              bug_count: p.bug_count || 0,
              children: p.children && p.children.length > 0 ? processPlanTree(p.children, level + 1) : []
            }))
          }
          bugPlans.value = processPlanTree(allPlans)
        }
      } catch (error) {
        console.error('获取 Bug 计划失败:', error)
      }
    }

    const loadCardsForPlan = async (planId) => {
      const projectId = snowflakeIdStr(testcase.project_id) || testcase.project_id
      if (!projectId) return
      const plan = findPlanById(bugPlans.value, planId)
      if (!plan) return
      try {
        const response = await getProjectCards(projectId, 1, 500, {
          plan_id: planId,
          type: 'bug'
        })
        if (response.data?.success) {
          const raw = response.data.data || []
          plan.cards = raw
            .filter((c) => String(c.type || '').toLowerCase() === 'bug')
            .map((c) => ({
              value: snowflakeIdStr(c.id) || String(c.id),
              label: c.title || `卡片-${c.id}`,
              type: 'bug',
              expanded: false,
              bugs: null,
              bug_count: c.bug_count || 0
            }))
        } else {
          plan.cards = []
        }
      } catch (error) {
        console.error('加载缺陷卡片失败:', error)
        plan.cards = []
      }
    }

    const loadBugsForCard = async (planId, cardId) => {
      const projectId = snowflakeIdStr(testcase.project_id) || testcase.project_id
      if (!projectId) return
      const plan = findPlanById(bugPlans.value, planId)
      const card = plan?.cards?.find((c) => c.value === cardId)
      if (!card) return
      try {
        const response = await getProjectBugs(projectId, 1, 500, { card_id: cardId })
        if (response.data?.success) {
          card.bugs = response.data.badcases || response.data.bugs || []
          card.bug_count = card.bugs.length
        } else {
          card.bugs = []
        }
      } catch (error) {
        console.error('加载卡片下 Bug 失败:', error)
        card.bugs = []
      }
    }

    const loadAllBugs = async () => {
      const refreshExpanded = async (plans) => {
        for (const plan of plans) {
          if (!plan.expanded) continue
          if (isLeafPlanNode(plan)) {
            if (plan.cards === null) {
              await loadCardsForPlan(plan.value)
            }
            for (const card of plan.cards || []) {
              if (card.expanded) {
                await loadBugsForCard(plan.value, card.value)
              }
            }
          } else if (plan.children?.length) {
            await refreshExpanded(plan.children)
          }
        }
      }
      await refreshExpanded(bugPlans.value)
    }

    const commentDraftText = computed(() => {
      if (!commentDraft.value) return ''
      const tempDiv = document.createElement('div')
      tempDiv.innerHTML = commentDraft.value
      return tempDiv.textContent || tempDiv.innerText || ''
    })

    const commentDraftLength = computed(() => richTextHtmlDisplayLength(commentDraft.value))

    const formatCommentTime = (iso) => {
      if (!iso) return ''
      try {
        const d = new Date(iso)
        if (Number.isNaN(d.getTime())) return String(iso)
        return d.toLocaleString()
      } catch (_e) {
        return String(iso)
      }
    }

    const plainCommentFromDiffValue = (val) => {
      if (val == null) return ''
      let raw = val
      if (typeof raw === 'object' && raw !== null && 'new' in raw) raw = raw.new
      const s = String(raw ?? '')
      if (/<[a-z][\s\S]*>/i.test(s)) return htmlToPlainText(s).trim()
      return s.trim()
    }

    const commentBodyAlreadyListed = (plain) => {
      const want = String(plain || '').trim()
      if (!want) return false
      return testcaseComments.value.some(
        (c) => htmlToPlainText(c.content || '').trim() === want
      )
    }

    const optimisticAppendTestcaseComment = (text) => {
      const plain = String(text || '').trim()
      if (!plain || commentBodyAlreadyListed(plain)) return
      const author = currentUser.value ? personPrimaryLabel(currentUser.value) : '—'
      testcaseComments.value = [
        ...testcaseComments.value,
        {
          id: `pending-${Date.now()}`,
          content: plain.includes('<') ? plain : `<p>${plain.replace(/\n/g, '<br>')}</p>`,
          user_name: author,
          created_at: new Date().toISOString(),
          source_message_id: pendingDiff.value?.messageId ?? null
        }
      ]
    }

    const resolveCommentParentId = (comment) => {
      if (!comment || comment.pending) return null
      const id = comment.id
      if (id == null || String(id).startsWith('pending-')) return null
      return id
    }

    const startReplyToComment = (comment) => {
      replyingTo.value = comment
      commentEditorActive.value = true
      nextTick(() => {
        commentInputContainerRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
      })
    }

    const cancelReplyToComment = () => {
      replyingTo.value = null
    }

    const loadTestcaseComments = async () => {
      if (!testcaseId) return
      try {
        const response = await getTestCaseDetail(testcaseId)
        const res = response?.data || response
        const list = res?.testcase?.comments
        testcaseComments.value = Array.isArray(list) ? [...list] : []
      } catch (e) {
        console.error('[TestCase] 加载评论失败:', e)
      }
    }

    const reloadTestcaseCommentsAfterAdopt = async (expectedPlain = '') => {
      const want = String(expectedPlain || '').trim()
      const delays = want ? [0, 200, 450, 800] : [0]
      for (const ms of delays) {
        if (ms) await new Promise((resolve) => setTimeout(resolve, ms))
        await loadTestcaseComments()
        if (!want || commentBodyAlreadyListed(want)) return
      }
    }

    const reloadTestcaseCommentsAfterSubmit = async (tempId) => {
      const delays = [400, 1200, 3000]
      for (const ms of delays) {
        await new Promise((resolve) => setTimeout(resolve, ms))
        await loadTestcaseComments()
        if (!tempId || !testcaseComments.value.some((c) => c.id === tempId && c.pending)) return
      }
    }

    const submitCommentDraft = async () => {
      if (!isEdit || !testcaseId || !richTextHtmlHasContent(commentDraft.value)) return
      const parentId = replyingTo.value ? resolveCommentParentId(replyingTo.value) : null
      const author = currentUser.value ? personPrimaryLabel(currentUser.value) : '—'
      const tempId = `pending-${Date.now()}`
      const optimistic = {
        id: tempId,
        content: commentDraft.value,
        user_name: author,
        user_id: currentUser.value?.id ?? null,
        parent_id: parentId,
        parent_user_name: replyingTo.value?.user_name || '',
        created_at: new Date().toISOString(),
        pending: true
      }
      testcaseComments.value = [...testcaseComments.value, optimistic]
      const draftSnapshot = commentDraft.value
      commentDraft.value = ''
      commentEditorActive.value = false
      replyingTo.value = null
      commentSubmitting.value = true
      try {
        const resp = await addTestCaseComment(testcaseId, draftSnapshot, null, parentId)
        const res = resp?.data || resp
        if (res?.success && res.comment) {
          if (res.async) {
            reloadTestcaseCommentsAfterSubmit(tempId)
          } else {
            testcaseComments.value = testcaseComments.value.map((c) =>
              c.id === tempId ? res.comment : c
            )
          }
        } else {
          testcaseComments.value = testcaseComments.value.filter((c) => c.id !== tempId)
          alert(res?.error || '发表评论失败')
        }
      } catch (e) {
        testcaseComments.value = testcaseComments.value.filter((c) => c.id !== tempId)
        console.error('[TestCase] 发表评论失败:', e)
        alert('发表评论失败')
      } finally {
        commentSubmitting.value = false
      }
    }

    const handleProjectChange = () => {
      const sid = idStrOrNull(testcase.project_id)
      if (sid) {
        fetchProjectPlans(sid)
        fetchProjectMembers(sid)
      } else {
        testcasePlans.value = []
        projectMembers.value = []
        testcase.assignee = []
      }
    }

    const onProjectSelectChange = (e) => {
      const raw = e.target.value
      testcase.project_id = raw === '' ? null : (idStrOrNull(raw) || String(raw).trim())
      handleProjectChange()
    }

    const copyDocumentLink = () => {
      console.log('Copy document link')
    }

    const addAttachment = () => {
      fileInput.value?.click()
    }

    const removeAttachment = (index) => {
      if (testcase.attachments && Array.isArray(testcase.attachments)) {
        testcase.attachments.splice(index, 1)
      }
    }

    const handleFileUpload = (event) => {
      const files = event.target.files
      if (files && files.length > 0) {
        if (!testcase.attachments) {
          testcase.attachments = []
        }
        Array.from(files).forEach(file => {
          testcase.attachments.push({
            name: file.name,
            size: file.size
          })
        })
      }
    }

    const saveTestCase = async () => {
      if (!testcase.title.trim()) {
        alert('请输入测试用例标题')
        return
      }

      saving.value = true
      try {
        // 处理 related_defects：提取 bug id 数组（兼容元素为对象/数字/字符串，且过滤空值）
        const relatedDefectIds = Array.isArray(testcase.related_defects)
          ? testcase.related_defects
              .filter(Boolean)
              .map(d => (typeof d === 'object' ? d?.id : d))
              .filter(v => v != null && String(v).trim() !== '')
              .map(v => snowflakeIdStr(v))
              .filter(v => v)
          : []
        
        // 处理 assignee：取第一个作为 assignee_id
        const assigneeId = testcase.assignee && testcase.assignee.length > 0 
          ? testcase.assignee[0] 
          : testcase.assignee_id
        
        // plan_id：从测试用例计划「快速新建」时 route 带 plan_id（必为 test_case 计划），优先使用；否则用表单选中
        let planId = null
        const routePlanSid = route.query.plan_id ? idStrOrNull(route.query.plan_id) : null
        const planInOptions = (pidStr) =>
          !!pidStr &&
          testcasePlans.value.some(
            (p) => p.value !== 'unplanned' && idStrOrNull(p.value) === pidStr
          )
        if (isEdit) {
          if (!isEmptyPlanKey(testcase.plan)) {
            const pid = idStrOrNull(testcase.plan)
            if (pid && planInOptions(pid)) planId = pid
          } else {
            planId = testcase.plan_id != null ? idStrOrNull(testcase.plan_id) : null
          }
        } else if (routePlanSid) {
          planId = routePlanSid
        } else if (!isEmptyPlanKey(testcase.plan)) {
          const pid = idStrOrNull(testcase.plan)
          if (pid && planInOptions(pid)) planId = pid
        }
        // 兜底：嵌入在 ProjectDetail 的创建 Tab 时可能只通过 props.plan_id 传入
        if (!isEdit && planId == null) {
          const fallbackPid = props.plan_id != null && props.plan_id !== '' ? idStrOrNull(props.plan_id) : null
          if (fallbackPid) {
            planId = fallbackPid
          }
        }

        // 创建/编辑时 project_id：统一走兜底解析，避免引用未定义变量 projectId
        const pidFallback = currentProjectId.value
        const rawProjectId = testcase.project_id || pidFallback
        const finalProjectId = idStrOrNull(rawProjectId)
        if (!isEdit && !finalProjectId) {
          alert('请选择所属项目，或从项目详情页进入新建')
          saving.value = false
          return
        }

        const payload = {
          title: testcase.title,
          status: testcase.status,
          case_type: testcase.case_type,
          priority: testcase.priority,
          test_type: testcase.test_type,
          preconditions: testcase.preconditions,
          steps: testcase.steps,
          requirement_id: testcase.requirement_id,
          related_defects: relatedDefectIds,
          estimated_time: testcase.estimated_time,
          version: testcase.version,
          plan_id: planId,
          project_id: isEdit ? (pidFallback || testcase.project_id) : finalProjectId,
          assignee_id: assigneeId || null,
          execution_result: (testcase.execution_result && String(testcase.execution_result).trim()) ? testcase.execution_result : null
        }
        // 新建时添加卡片ID，用于后端校验卡片类型
        if (!isEdit && props.card_id != null && props.card_id !== '') {
          const cid = snowflakeIdStr(props.card_id)
          if (cid) payload.card_id = cid
        }

        if (isEdit) {
          await updateTestCase(testcaseId, payload)
        } else {
          await createTestCase(payload)
        }

        alert(isEdit ? '更新成功' : '创建成功')
        goBack()
      } catch (error) {
        console.error('保存失败:', error)
        console.error('后端返回:', error?.response?.data)
        const msg = error?.response?.data?.error || error?.message || '保存失败'
        alert(msg)
      } finally {
        saving.value = false
      }
    }

    const goBack = () => {
      // 嵌入在 ProjectDetail 的工作区 Tab：不要走浏览器历史，直接关闭 Tab
      if (props.embedded) {
        console.log('[EMBEDDED] 触发 close 事件')
        emit('close')
        return
      }
      // 如果是通过覆盖层打开的，触发 close 事件
      if (props.id) {
        console.log('[OVERLAY] 触发 close 事件')
        emit('close')
        return
      }
      
      const pid = currentProjectId.value || testcase.project_id
      router.push(`/project-detail/${pid || ''}`)
    }
    
    // 确认字段修改
    const confirmFieldChange = (field) => {
      console.log('[DIFF] 确认字段修改:', field)
      if (detailFieldDiff(field)) {
        clearDetailFieldDiff(field)
        
        // 如果所有字段都已确认，清除 sessionStorage 并通知对话区
        if (Object.keys(pendingDiff.value?.modifications || {}).filter(k => !k.startsWith('_')).length === 0) {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
          // 通知对话区修改已确认
          const event = new CustomEvent('modify-confirmed', {
            detail: {
              targetId: pendingDiff.value.targetId,
              targetType: 'testcase'
            },
            bubbles: true
          })
          window.dispatchEvent(event)
          pendingDiff.value = null
        }
      }
    }
    
    // 取消字段修改
    const cancelFieldChange = (field) => {
      console.log('[DIFF] 取消字段修改:', field)
      if (detailFieldDiff(field)) {
        restoreDetailFieldOld(field)
        clearDetailFieldDiff(field)
        
        // 如果所有字段都已处理，清除 sessionStorage
        if (Object.keys(pendingDiff.value?.modifications || {}).filter(k => !k.startsWith('_')).length === 0) {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
          pendingDiff.value = null
        }
      }
    }

    const scrollToDiffField = async (field) => {
      await nextTick()
      const el = document.getElementById(`diff-field-${field}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    const applyDetailFieldToTestcase = (nk, newValue) => {
      if (newValue === undefined) return
      if (nk === 'append_comment') {
        const plain = plainCommentFromDiffValue(newValue)
        optimisticAppendTestcaseComment(plain)
        void reloadTestcaseCommentsAfterAdopt(plain)
        return
      }
      if (nk === 'steps') {
        testcase.steps = normalizeTestcaseStepsForEditor(newValue)
        return
      }
      if (nk === 'related_defects') {
        const ids = normalizeTestcaseRelatedDefectIds(newValue)
        const byId = new Map(
          (testcase.related_defects || []).map((d) => [String(d.id), d])
        )
        testcase.related_defects = ids.map((id) => {
          const hit = byId.get(String(id))
          return hit ? { ...hit, id } : { id, title: '' }
        })
        void hydrateRelatedDefectTitles()
        return
      }
      if (isTestcaseSelectDetailField(nk)) {
        testcase[nk] = normalizeTestcaseSelectFieldForEditor(nk, newValue)
        return
      }
      if (nk === 'preconditions') {
        testcase.preconditions = ensureEditorHtmlContent(newValue)
        return
      }
      if (nk === 'remark') {
        return
      }
      if (Object.prototype.hasOwnProperty.call(testcase, nk)) {
        testcase[nk] = newValue
      }
    }

    const assignPreconditionsFromApi = (raw) => {
      testcase.preconditions = ensureEditorHtmlContent(raw || '')
    }

    const resolveEditorTestcaseId = () => {
      const raw =
        props.id != null && props.id !== ''
          ? props.id
          : route.query.id != null && route.query.id !== ''
            ? route.query.id
            : null
      return raw != null ? (idStrOrNull(raw) || String(raw).trim()) : ''
    }

    /** 详情内单字段采纳且 pending 已清空：通知工作区 Tab 退出 show_diff 并刷新 */
    const notifyDetailAdoptCompleteIfDone = (adoptedField, adoptedValue, serverResult = null) => {
      if (pendingDiff.value) return
      const tid = resolveEditorTestcaseId()
      if (!tid) return
      window.dispatchEvent(
        new CustomEvent('detail-modify-adopted', {
          detail: {
            targetId: tid,
            targetType: 'testcase',
            adoptedField,
            adoptedValue,
            serverResult: serverResult ?? null
          },
          bubbles: true
        })
      )
    }

    const rollbackOptimisticTestcaseField = async (field, nk, modSnapshot, pendingMeta) => {
      if (nk === 'append_comment') {
        testcaseComments.value = (testcaseComments.value || []).filter(
          (c) => !String(c?.id || '').startsWith('pending-')
        )
      } else if (modSnapshot?.old !== undefined) {
        applyDetailFieldToTestcase(nk, modSnapshot.old)
        await nextTick()
        if (nk === 'preconditions') {
          preconditionsEditorRef.value?.syncFromModel?.()
        }
      }
      const pd = pendingDiff.value || {
        targetId: pendingMeta.targetId,
        target: pendingMeta.target,
        messageId: pendingMeta.messageId,
        modifications: {}
      }
      for (const k of getTestcaseModifyModKeys(field, nk)) {
        pd.modifications[k] = { ...modSnapshot }
      }
      pendingDiff.value = pd
    }

    const applyFieldChange = async (field) => {
      const mod = detailFieldDiff(field)
      if (!mod) return
      const nk = normalizeTestcaseModifyFieldKey(field)
      const apiField = mapTestcaseModifyApiField(nk)

      const targetId = pendingDiff.value?.targetId || testcaseId
      const target = pendingDiff.value?.target || 'testcase'
      const newValue = mod.new
      const modSnapshot = { ...mod }
      const pendingMeta = {
        targetId,
        target,
        messageId: pendingDiff.value?.messageId ?? null
      }

      const pid = currentProjectId.value || testcase.project_id
      if (!pid || !targetId) {
        console.warn('[DIFF] projectId/targetId 缺失，无法采纳', { projectId: pid, targetId })
        return
      }

      if (nk === 'append_comment') {
        optimisticAppendTestcaseComment(plainCommentFromDiffValue(newValue))
        commentDraft.value = ''
      } else {
        applyDetailFieldToTestcase(nk, newValue)
        await nextTick()
        preconditionsEditorRef.value?.syncFromModel?.()
      }
      confirmFieldChange(field)

      try {
        const resp = await fetch(`${BACKEND_BASE_URL}/api/projects/${pid}/modify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            target,
            target_id: targetId,
            modifications: {
              [apiField]:
                nk === 'related_defects'
                  ? normalizeTestcaseRelatedDefectIds(newValue)
                  : newValue
            },
            confirm: true,
            message_id: pendingMeta.messageId
          })
        })
        const result = await resp.json()
        if (!result.success) {
          await rollbackOptimisticTestcaseField(field, nk, modSnapshot, pendingMeta)
          console.error('[DIFF] 采纳失败:', result.error)
          alert(result.error || '采纳失败')
          return
        }

        if (nk === 'append_comment') {
          const plain = plainCommentFromDiffValue(newValue)
          if (result.async === true) {
            await new Promise((resolve) => setTimeout(resolve, 420))
          }
          await reloadTestcaseCommentsAfterAdopt(plain)
        }

        notifyDetailAdoptCompleteIfDone(nk, newValue, result)
      } catch (e) {
        await rollbackOptimisticTestcaseField(field, nk, modSnapshot, pendingMeta)
        console.error('[DIFF] 采纳字段异常:', e)
      }
    }

    const deleteTestCaseAction = async () => {
      if (!confirm('确定要删除这个测试用例吗？此操作不可撤销。')) {
        return
      }
      
      try {
        await deleteTestCase(testcaseId)
        alert('删除成功')
        goBack()
      } catch (error) {
        console.error('删除失败:', error)
        alert('删除失败')
      }
    }

    const reconcilePendingOldFromLoadedTestcase = () => {
      if (!pendingDiff.value?.modifications) return
      for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
        if (String(field).startsWith('_')) continue
        const nk = normalizeTestcaseModifyFieldKey(field)
        if (!data || typeof data !== 'object' || !('new' in data)) continue
        if (!Object.prototype.hasOwnProperty.call(testcase, nk) && !Object.prototype.hasOwnProperty.call(testcase, field)) continue
        const bv = testcase[nk] ?? testcase[field]
        const bs =
          bv != null && typeof bv !== 'object'
            ? String(bv).trim()
            : Array.isArray(bv)
              ? JSON.stringify(bv)
              : ''
        const oldS = data.old != null ? String(data.old).trim() : ''
        const newS = data.new != null ? String(data.new).trim() : ''
        if (!newS || newS === bs) continue
        /** 执行结果：空串=未执行，须用库内当前值补全 old（modify 常不带 before） */
        if (nk === 'execution_result') {
          data.old = bv ?? ''
          continue
        }
        if (nk === 'related_defects') {
          const curIds = normalizeTestcaseRelatedDefectIds(testcase.related_defects)
          data.old = curIds
          continue
        }
        if (oldS !== bs && (bs !== '' || isTestcaseSelectDetailField(nk))) {
          data.old = bv
        }
      }
    }

    const reloadPendingDiffFromSession = async () => {
      const showDiffMode = props.show_diff || route.query.show_diff === 'true'
      if (!showDiffMode) {
        try {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
        } catch (_e) {
          /* ignore */
        }
        pendingDiff.value = null
        return
      }
      const pd = getPendingModifyDiffForDetail(
        snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
      )
      if (!pd) {
        pendingDiff.value = null
        return
      }
      try {
        const pdCopy = { ...pd }
        const tid = pd?.targetId != null ? String(pd.targetId).trim() : ''
        const cur = testcaseId ? String(testcaseId).trim() : ''
        const tgt = String(pd?.target || '').toLowerCase().replace(/-/g, '_')
        const isTc = tgt === 'testcase' || tgt === 'test_case' || tgt === ''
        if (!isTc || (isEdit && cur && tid && tid !== cur)) {
          pendingDiff.value = null
          return
        }
        pendingDiff.value = pdCopy
        const mods = pendingDiff.value?.modifications
        const commentIntent = String(
          pdCopy?._naturalQuery || pdCopy?.naturalQuery || ''
        ).trim()
        if (mods && coerceTestcaseRemarkToAppendComment(mods, commentIntent)) {
          if (Array.isArray(pendingDiff.value.diff)) {
            for (const row of pendingDiff.value.diff) {
              const nk = normalizeTestcaseModifyFieldKey(row?.field, row?.field_label)
              if (nk !== 'remark' || !intentRequestsTestcaseComment(commentIntent)) continue
              row.field = 'append_comment'
              row.field_label = getTestcaseFieldLabel('append_comment')
              const addLine = row.lines?.find((l) => l.type === 'add')
              if (addLine) {
                row.lines = [
                  { type: 'delete', content: '', line_no: 0 },
                  { type: 'add', content: addLine.content, line_no: 0 }
                ]
              }
            }
          }
        }
        if (mods) {
          for (const [field, data] of Object.entries(mods)) {
            if (String(field).startsWith('_')) continue
            const nk = normalizeTestcaseModifyFieldKey(field)
            if (nk === 'steps') {
              const parsedNew = normalizeTestcaseStepsForEditor(data?.new)
              const parsedCur = normalizeTestcaseStepsForEditor(testcase.steps)
              if (
                JSON.stringify(parsedNew) === JSON.stringify(parsedCur) &&
                parsedNew.some((s) => s.step || s.expected)
              ) {
                delete mods[field]
              }
              continue
            }
            if (nk === 'related_defects') {
              const parsedNew = normalizeTestcaseRelatedDefectIds(data?.new)
              const parsedCur = normalizeTestcaseRelatedDefectIds(testcase.related_defects)
              if (
                JSON.stringify([...parsedNew].sort()) ===
                JSON.stringify([...parsedCur].sort())
              ) {
                delete mods[field]
              }
              continue
            }
            const newVal = data?.new != null ? String(data.new).trim() : ''
            const curVal = testcase[nk] != null ? String(testcase[nk]).trim() : ''
            if (newVal && curVal === newVal) delete mods[field]
          }
          if (Object.keys(mods).filter((k) => !String(k).startsWith('_')).length === 0) {
            clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
            pendingDiff.value = null
            return
          }
        }
        reconcilePendingOldFromLoadedTestcase()
        applyPendingModificationsToTestcaseForm()
        if (detailFieldDiff('append_comment')) {
          isRightSidebarOpen.value = true
          await nextTick()
          scrollToDiffField('append_comment')
        } else if (detailFieldDiff('execution_result')) {
          activeTab.value = 'execution'
          await nextTick()
          scrollToDiffField('execution_result')
        } else if (detailFieldDiff('related_defects')) {
          activeTab.value = 'defects'
          await nextTick()
          scrollToDiffField('related_defects')
        } else {
          const it = props.initial_tab
          if (it === 'execution' || it === 'basic' || it === 'defects') {
            activeTab.value = it
          }
        }
        await nextTick()
        preconditionsEditorRef.value?.syncFromModel?.()
      } catch (e) {
        console.error('[DIFF] reloadPendingDiffFromSession 失败:', e)
        pendingDiff.value = null
      }
    }

    /** 列表/沙箱采纳后：与 Bug 一致只更新本地表单，不再 GET 详情（避免异步落库前把旧值盖回） */
    const onDetailModifyAdopted = async (event) => {
      const tid = event?.detail?.targetId != null ? String(event.detail.targetId).trim() : ''
      const cur = resolveEditorTestcaseId()
      if (!tid || !cur || tid !== cur) return

      if (event?.detail?.reloadPendingDiff === true) {
        await reloadPendingDiffFromSession()
        await nextTick()
        preconditionsEditorRef.value?.syncFromModel?.()
        return
      }

      const fieldUpdates = event?.detail?.fieldUpdates
      if (fieldUpdates && typeof fieldUpdates === 'object') {
        for (const [field, val] of Object.entries(fieldUpdates)) {
          const nk = normalizeTestcaseModifyFieldKey(field)
          applyDetailFieldToTestcase(nk, val)
          clearDetailFieldDiff(field)
        }
      }

      if (
        pendingDiff.value?.modifications &&
        Object.keys(pendingDiff.value.modifications).filter((k) => !String(k).startsWith('_')).length === 0
      ) {
        pendingDiff.value = null
      }

      await nextTick()
      preconditionsEditorRef.value?.syncFromModel?.()
    }

    onMounted(async () => {
      window.addEventListener('testcase-detail-refresh', onDetailModifyAdopted)
      console.log('=== NewTestCase onMounted 开始 ===')
      console.log('route.query:', route.query)
      console.log('props.project_id:', props.project_id, 'props.plan_id:', props.plan_id)
      console.log('testcase.project_id:', testcase.project_id)
      
      loading.value = true
      try {
        const query = route.query
        const showDiffMode = props.show_diff || query.show_diff === 'true'
        if (showDiffMode) {
          const diffEarly = getPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
          if (diffEarly) {
            try {
              pendingDiff.value = diffEarly
              console.log('[DIFF] 预读取到 diff 数据:', pendingDiff.value)
            } catch (e) {
              console.error('[DIFF] 预读取 diff 失败:', e)
            }
          }
        } else {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(testcase.project_id)
          )
          pendingDiff.value = null
        }

        await fetchCurrentUser()

        const rid = readProjectIdFromRoute()
        if (rid != null) testcase.project_id = rid

        if (isEdit && testcaseId) {
          const [, detailResp] = await Promise.all([
            loadUserProjectsForSelect(),
            getTestCaseDetail(testcaseId).catch((e) => {
              console.error('getTestCaseDetail 失败:', e)
              return null
            })
          ])
          const response = detailResp
          const res = response?.data || response
          if (res && (res.success === true) && res.testcase) {
            const data = res.testcase
            testcase.title = data.title || ''
            testcase.status = (data.status != null && data.status !== undefined) ? String(data.status) : 'draft'
            testcase.case_type = data.case_type || '功能测试'
            testcase.priority = data.priority || 'P3'
            testcase.test_type = data.test_type || '手动'
            assignPreconditionsFromApi(data.preconditions)
            testcase.steps = normalizeTestcaseStepsForEditor(data.steps)
            testcase.requirement_id = data.requirement_id
            testcase.estimated_time = data.estimated_time || 0
            testcase.version = data.version || 'v1'
            testcase.plan_id = data.plan_id
            testcase.project_id = data.project_id
            testcase.execution_result = normalizeTestcaseExecutionResultForSelect(data.execution_result)

            if (data.assignee_id) {
              testcase.assignee = [data.assignee_id.toString()]
              testcase.assignee_id = data.assignee_id
            }

            if (data.plan_id) {
              testcase.plan = data.plan_id.toString()
            }

            if (data.related_defects && Array.isArray(data.related_defects)) {
              testcase.related_defects = data.related_defects.map((item) => {
                if (item && typeof item === 'object') {
                  return {
                    id: item.id,
                    title: String(item.title || '').trim(),
                    plan_id: item.plan_id ?? item.planId ?? null
                  }
                }
                return { id: item, title: '', plan_id: null }
              })
              await hydrateRelatedDefectTitles()
            }
            testcaseComments.value = Array.isArray(data.comments) ? [...data.comments] : []
          }
        } else {
          await loadUserProjectsForSelect()
        }

        await loadProjectWorkspace(testcase.project_id)

        if (!isEdit) {
          await applyInitialPlanForCreate()
          applyDefaultAssigneeOnCreate(testcase, currentUser.value, { isEdit: false })
        } else if (!isEmptyPlanKey(testcase.plan)) {
          await ensurePlanOptionVisible(testcase.plan)
        }

        await reloadPendingDiffFromSession()

        await nextTick()
        preconditionsEditorRef.value?.syncFromModel?.()
      } catch (error) {
        console.error('加载失败:', error)
      } finally {
        loading.value = false
        // 编辑模式下通知父组件更新Tab标题
        if (isEdit && testcase.title) {
          emit('titleLoaded', testcase.title)
        }
        console.log('=== NewTestCase onMounted 完成 ===')
      }
    })

    watch(
      () => [props.show_diff, props.id, props.pending_diff_seq],
      () => {
        void reloadPendingDiffFromSession()
      },
      { flush: 'post' }
    )

    watch(
      () => props.initial_tab,
      (tab) => {
        if (!props.show_diff) return
        if (detailFieldDiff('append_comment')) return
        if (detailFieldDiff('execution_result')) return
        if (detailFieldDiff('related_defects')) return
        if (tab === 'execution' || tab === 'basic' || tab === 'defects') {
          activeTab.value = tab
        }
      }
    )

    onUnmounted(() => {
      window.removeEventListener('testcase-detail-refresh', onDetailModifyAdopted)
    })

    onActivated(async () => {
      await reloadPendingDiffFromSession()
      await nextTick()
      preconditionsEditorRef.value?.syncFromModel?.()
    })

    watch(
      () => props.plan_id,
      (planId) => {
        void applyPlanFromProps(planId)
      },
      { immediate: true }
    )

    watch(
      () => readProjectIdFromRoute(),
      async (pid) => {
        const sid = idStrOrNull(pid)
        if (!sid) return
        if (String(testcase.project_id) === sid) return
        testcase.project_id = sid
        await loadUserProjectsForSelect()
        await loadProjectWorkspace(pid)
      }
    )

    // 嵌入模式下 id 可能由父组件稍后传入，监听后补拉详情
    watch(() => props.id, async (newId) => {
      const id = newId != null && String(newId).trim() !== '' ? (idStrOrNull(newId) || String(newId).trim()) : null
      if (!id || !props.embedded) return
      loading.value = true
      try {
        const response = await getTestCaseDetail(id)
        const res = response?.data || response
        if (res && res.success === true && res.testcase) {
          const data = res.testcase
          testcase.title = data.title || ''
          testcase.status = (data.status != null && data.status !== undefined) ? String(data.status) : 'draft'
          testcase.case_type = data.case_type || '功能测试'
          testcase.priority = data.priority || 'P3'
          testcase.test_type = data.test_type || '手动'
          assignPreconditionsFromApi(data.preconditions)
          testcase.steps = normalizeTestcaseStepsForEditor(data.steps)
          testcase.plan_id = data.plan_id
          testcase.project_id = data.project_id
          testcase.execution_result = normalizeTestcaseExecutionResultForSelect(data.execution_result)
          if (data.assignee_id) {
            testcase.assignee = [String(data.assignee_id)]
            testcase.assignee_id = data.assignee_id
          }
          if (data.plan_id) testcase.plan = String(data.plan_id)
          await nextTick()
        }
      } catch (e) {
        console.error('watch id 加载测试用例失败:', e)
      } finally {
        loading.value = false
        // 编辑模式下通知父组件更新Tab标题
        if (isEdit && testcase.title) {
          emit('titleLoaded', testcase.title)
        }
      }
    }, { immediate: false })

    function onOpenDiagnosticTerminal() {
      if (!openDiagnosticTerminal) return
      const title = (testcase.title || '测试用例').trim()
      const idPart = testcaseId ? `#${testcaseId}` : ''
      const er = String(testcase.execution_result || '').trim()
      const steps = Array.isArray(testcase.steps) ? testcase.steps : []
      const stepLines = steps.slice(0, 12).map((s, i) => {
        if (typeof s === 'string') return `${i + 1}. ${s}`
        const desc = s?.step || s?.description || s?.action || ''
        const exp = s?.expected || s?.expected_result || ''
        return `${i + 1}. ${desc}${exp ? ` → 预期: ${exp}` : ''}`
      }).filter(Boolean)
      const defects = Array.isArray(testcase.related_defects) ? testcase.related_defects : []
      const defectLine = defects.length
        ? `关联缺陷: ${defects.map((d) => (typeof d === 'object' ? (d.id || d.title) : d)).filter(Boolean).join(', ')}`
        : ''
      const evidence = [
        `【失败用例】${idPart} ${title}`,
        er ? `执行结果: ${er}` : '',
        testcase.preconditions ? `前置条件: ${String(testcase.preconditions).replace(/<[^>]+>/g, '').slice(0, 300)}` : '',
        stepLines.length ? `步骤摘要:\n${stepLines.join('\n')}` : '',
        defectLine,
        '',
        '请结合上述证据与当前项目环境，生成排查用的 shell 命令（日志、健康检查、服务状态、最近错误等），并简要说明每条命令用途。',
      ].filter((x) => x !== '').join('\n')
      openDiagnosticTerminal({
        aiText: evidence,
        evidence: {
          testcase_id: testcaseId,
          title,
          execution_result: er,
          steps: steps.slice(0, 20),
          related_defects: defects,
        },
      })
    }

    return {
      loading,
      saving,
      showStatusDropdown,
      showAssigneeDropdown,
      showAddDefectDialog,
      activeTab,
      projectInfo,
      testcase,
      currentUser,
      testcasePlans,
      selectableTestcasePlans,
      availableProjects,
      projectMembers,
      assigneeSearchText,
      showPlanDropdown,
      bugPlans,
      defectSearchText,
      defectSearchResults,
      defectSearchLoading,
      availableStatuses,
      isEdit,
      getStatusText,
      formatTestcasePriorityLabel,
      getAssigneeDisplayText,
      personPrimaryLabel,
      personSecondaryLabel,
      isAssigneeSelected,
      toggleAssignee,
      togglePlanDropdown,
      selectPlan,
      getSelectedPlanDisplayText,
      refreshProjectPlans,
      openAddDefectDialog,
      confirmAddDefects,
      isDefectSelected,
      toggleDefectSelection,
      navigateToDefect,
      defectDisplayTitle,
      searchDefects,
      togglePlanExpand,
      toggleCardExpand,
      loadAllBugs,
      toggleStatusDropdown,
      selectStatus,
      toggleAssigneeDropdown,
      addStep,
      removeStep,
      removeDefect,
      fileInput,
      testcaseComments,
      commentDraft,
      commentDraftText,
      commentDraftLength,
      commentSubmitting,
      replyingTo,
      startReplyToComment,
      cancelReplyToComment,
      commentEditorActive,
      commentInputContainerRef,
      activateCommentEditor,
      finishCommentEditor,
      formatCommentTime,
      loadTestcaseComments,
      submitCommentDraft,
      handleProjectChange,
      onProjectSelectChange,
      copyDocumentLink,
      addAttachment,
      removeAttachment,
      handleFileUpload,
      saveTestCase,
      goBack,
      pendingDiff,
      t,
      testcaseFieldLabel,
      formatDiffFieldValue,
      hasDetailFieldDiff,
      detailFieldDiff,
      confirmFieldChange,
      cancelFieldChange,
      applyFieldChange,
      preconditionsEditorRef,
      openDiagnosticTerminal,
      onOpenDiagnosticTerminal,
      isRightSidebarOpen,
      toggleRightSidebar
    }
  }
}
</script>

<style scoped>
/* 复用Bug样式结构 */
.testcase-detail-wrapper {
  width: 100%;
  height: 100vh;
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}

/* 嵌入在 ProjectDetail 时占满父容器，避免底部被裁切导致保存/取消看不见 */
.testcase-detail-wrapper.is-embedded {
  flex: 1;
  min-height: 0;
  height: auto;
}

.header-bar {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-arrow {
  font-size: 24px;
  cursor: pointer;
  color: #606266;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.project-name {
  color: #909399;
  font-size: 14px;
}

.header-right {
  display: flex;
  gap: 8px;
}

.header-btn {
  padding: 8px 16px;
  border: 1px solid #dcdfe6;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.checkbox-icon {
  width: 16px;
  height: 16px;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.checkbox-icon.checked {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}

.main-content {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.content-left {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}

.content-left-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* 侧栏展开/收起（与 NewBug 一致） */
.resize-handle {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 24px;
  height: 24px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
  z-index: 10;
}

.resize-handle:hover {
  background-color: #f5f5f5;
  border-color: #d0d0d0;
}

.resize-icon {
  width: 12px;
  height: 18px;
  transition: transform 0.3s ease;
}

.resize-icon.rotated {
  transform: rotate(180deg);
}

.resize-icon--expand {
  transform: rotate(180deg);
}

.right-panel-column {
  display: flex;
  flex-direction: row;
  flex-shrink: 0;
  align-items: stretch;
  align-self: stretch;
  min-height: 0;
}

.sidebar-expand-tab {
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 10px;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.sidebar-expand-tab:hover {
  background: #f5f5f5;
  border-color: #d0d0d0;
}

.sidebar-right {
  position: relative;
  width: 0;
  min-width: 0;
  max-width: 0;
  padding: 0;
  margin: 0;
  background: #fff;
  border-left: none;
  overflow: hidden;
  box-sizing: border-box;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  transition:
    width 0.3s ease,
    min-width 0.3s ease,
    max-width 0.3s ease,
    padding 0.3s ease,
    border-color 0.3s ease,
    opacity 0.2s ease;
}

.sidebar-right.sidebar-right--open {
  width: 320px;
  min-width: 320px;
  max-width: 320px;
  min-height: 0;
  align-self: stretch;
  padding: 24px;
  border-left: 1px solid #e9ecef;
  overflow-y: auto;
  overflow-x: hidden;
  opacity: 1;
  pointer-events: auto;
}

.sidebar-section {
  margin-bottom: 32px;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e9ecef;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.radio-item input[type="radio"] {
  width: 16px;
  height: 16px;
}

.radio-text {
  font-size: 14px;
  color: #333;
}

.project-select {
  margin-top: 12px;
}

.select-label {
  display: block;
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 18px;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.document-fields {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 4px;
}

.field-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.field-label {
  font-size: 14px;
  color: #666;
}

.field-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #888;
  line-height: 1.5;
}

.field-value {
  font-size: 14px;
  color: #333;
}

.attachment-list {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 4px;
}

.no-attachments {
  text-align: center;
  color: #999;
  font-size: 14px;
  padding: 20px;
}

/* 评论样式 */
.comment-textarea-simple {
  width: 100%;
  min-height: 120px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 12px;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.2s;
  color: #333;
  line-height: 1.6;
}

.comment-textarea-simple:hover {
  border-color: #667eea;
}

.comment-textarea-simple:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.comment-textarea-simple::placeholder {
  color: #999;
}

.comment-input-container {
  position: relative;
}

.comment-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.comment-editor-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}

.comment-collapse-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  background: #fff;
  color: #495057;
  cursor: pointer;
}

.comment-collapse-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

.comment-input-subtitle {
  margin: 12px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #495057;
}

.comment-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 240px;
  overflow-y: auto;
  margin-bottom: 8px;
}

.comment-item {
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.comment-item.is-reply {
  margin-left: 16px;
  border-left: 3px solid #dee2e6;
}

.comment-item.is-pending {
  opacity: 0.85;
}

.comment-reply-btn {
  margin-left: auto;
  padding: 0;
  border: none;
  background: none;
  color: #0d6efd;
  font-size: 12px;
  cursor: pointer;
}

.comment-reply-btn:hover {
  text-decoration: underline;
}

.comment-reply-tag,
.comment-pending-tag {
  font-size: 11px;
  color: #6c757d;
}

.comment-pending-tag {
  color: #fd7e14;
}

.comment-reply-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
  padding: 6px 10px;
  font-size: 12px;
  color: #495057;
  background: #eef5ff;
  border-radius: 4px;
}

.comment-reply-cancel {
  margin-left: auto;
  padding: 0;
  border: none;
  background: none;
  color: #6c757d;
  font-size: 12px;
  cursor: pointer;
}

.comment-item-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: #6c757d;
}

.comment-author {
  font-weight: 600;
  color: #343a40;
}

.comment-op-tag {
  padding: 1px 6px;
  border-radius: 4px;
  background: #e7f1ff;
  color: #0d6efd;
  font-size: 11px;
}

.comment-item-body {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  word-break: break-word;
}

.comment-empty {
  font-size: 13px;
  color: #999;
  padding: 8px 0 12px;
}

.comment-diff-panel {
  margin-bottom: 10px;
}

.comment-submit-btn {
  margin-left: 8px;
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid #667eea;
  border-radius: 4px;
  background: #667eea;
  color: #fff;
  cursor: pointer;
}

.comment-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.editor-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
  padding: 0 12px 12px;
}

/* AI推荐按钮 */
.ai-recommend-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: none;
  border: none;
  color: #667eea;
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.ai-recommend-btn:hover {
  background: #e3f2fd;
}

.ai-icon {
  font-size: 14px;
}

/* 复制链接按钮 */
.copy-link-btn {
  background: none;
  border: none;
  color: #999;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  transition: color 0.2s;
}

.copy-link-btn:hover {
  color: #667eea;
}

/* 添加附件按钮 */
.add-attachment-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #e9ecef;
  background: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.add-attachment-btn:hover {
  background: #f8f9fa;
  border-color: #667eea;
}

.plus-icon {
  font-size: 18px;
  color: #666;
  font-weight: bold;
}

.attachment-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
  margin-bottom: 8px;
}

.attachment-name {
  font-size: 14px;
  color: #333;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-attachment-btn {
  background: none;
  border: none;
  color: #f56565;
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  transition: background-color 0.2s;
}

.remove-attachment-btn:hover {
  background: #fed7d7;
}

/* 富文本编辑器样式 */
.rich-editor {
  border: 1px solid #667eea;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.rich-editor .editor-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.rich-editor .editor-toolbar:hover {
  scrollbar-width: thin;
}

.rich-editor .editor-toolbar::-webkit-scrollbar {
  height: 0;
}

.rich-editor .editor-toolbar:hover::-webkit-scrollbar {
  height: 6px;
}

.rich-editor .editor-toolbar:hover::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.rich-editor .toolbar-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #e9ecef;
  background: #fff;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.rich-editor .toolbar-btn:hover {
  background: #e9ecef;
  border-color: #667eea;
}

.rich-editor .toolbar-divider {
  width: 1px;
  height: 16px;
  background: #e9ecef;
  margin: 0 2px;
}

.editor-content {
  min-height: 120px;
  padding: 12px;
  outline: none;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  color: #333;
  background: #fff;
}

.editor-content:empty:before {
  content: attr(placeholder);
  color: #999;
  pointer-events: none;
}

.pen-icon, .list-icon, .image-icon, .link-icon {
  font-size: 12px;
}

.title-section {
  margin-bottom: 24px;
}

.title-input {
  width: 100%;
  font-size: 24px;
  border: none;
  outline: none;
  padding: 8px 0;
  font-weight: 500;
}

.title-count {
  text-align: right;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.status-section {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #e4e7ed;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-label {
  color: #606266;
  font-size: 14px;
}

.status-dropdown {
  position: relative;
}

.status-pill {
  padding: 6px 12px;
  background: #ecf5ff;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  min-width: 120px;
  z-index: 100;
  margin-top: 4px;
}

.status-option {
  padding: 10px 16px;
  cursor: pointer;
}

.status-option:hover {
  background: #f5f7fa;
}

.status-option.selected {
  background: #ecf5ff;
  color: #409eff;
}

.assignee-selector {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.plan-select {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  min-width: 150px;
  cursor: pointer;
}

.tabs-container {
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 24px;
}

.tabs {
  display: flex;
  gap: 24px;
}

.tab {
  padding: 12px 0;
  cursor: pointer;
  color: #606266;
  border-bottom: 2px solid transparent;
}

.tab.active {
  color: #409eff;
  border-bottom-color: #409eff;
}

.tab-content {
  min-height: 400px;
}

/* 属性区域样式 */
.properties-container {
  margin-top: 32px;
  padding: 24px;
  background: #f8f9fa;
  border-radius: 8px;
}

.properties-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
}

.properties-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.property-field {
  display: flex;
  flex-direction: column;
}

.property-field--stacked .field-select {
  width: 100%;
  max-width: 520px;
}

.field-diff-panel--stacked {
  width: 100%;
  max-width: 520px;
}

.field-select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
}

/* 底部操作区：固定在左侧区域底部，始终可见可点 */
.footer-section {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 16px 24px;
  border-top: 1px solid #e9ecef;
  background: #fff;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
}

.footer-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.footer-actions .cancel-btn {
  background: #f8f9fa;
  color: #666;
  border: 1px solid #e9ecef;
}

.footer-actions .cancel-btn:hover {
  background: #e9ecef;
}

.footer-actions .save-btn {
  background: #667eea !important;
  color: #fff;
}

.footer-actions .save-btn:hover:not(:disabled) {
  background: #5a6fd8 !important;
}

.footer-actions .save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-cancel {
  padding: 12px 24px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  font-weight: 500;
  background: #fff;
  color: #606266;
}

.btn-cancel:hover {
  background: #f5f7fa;
}

.form-group {
  margin-bottom: 24px;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  color: #606266;
  font-size: 14px;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
}

.steps-table {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.steps-header {
  display: flex;
  background: #f5f7fa;
  padding: 12px;
  font-weight: 600;
  font-size: 14px;
  color: #606266;
}

.step-col-number {
  width: 60px;
}

.step-col-desc {
  flex: 1;
}

.step-col-expected {
  flex: 1;
}

.step-col-actions {
  width: 80px;
}

.step-row {
  display: flex;
  padding: 12px;
  border-top: 1px solid #e4e7ed;
  align-items: center;
}

.step-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
}

.add-step-row {
  padding: 12px;
  border-top: 1px solid #e4e7ed;
}

.add-step-btn {
  padding: 8px 16px;
  background: #ecf5ff;
  color: #409eff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.related-defects {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.defect-tag {
  padding: 4px 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.remove-tag {
  cursor: pointer;
  color: #f56c6c;
}

.add-defect-btn {
  padding: 4px 12px;
  background: #ecf5ff;
  color: #409eff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
}

/* 富文本编辑器样式 */
.editor-section {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: visible;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  flex-wrap: wrap;
}

.editor-toolbar .toolbar-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #e9ecef;
  background: #fff;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  user-select: none;
}

.editor-toolbar .toolbar-btn:hover {
  background: #f8f9fa;
  border-color: #409eff;
}

.editor-toolbar .toolbar-btn:active {
  background: #e9ecef;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #e9ecef;
  margin: 0 4px;
}

.editor-textarea {
  width: 100%;
  min-height: 150px;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  overflow-y: auto;
  padding: 16px;
}

.editor-textarea:empty:before {
  content: attr(placeholder);
  color: #999;
  pointer-events: none;
}

.action-buttons {
  display: none;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

/* show_diff：待采纳改动面板（暗色、Cursor风格） */
.pending-diff-panel {
  margin: 16px 0 20px;
  padding: 14px;
  background: #1e1e1e;
  border: 1px solid #3e3e3e;
  border-radius: 10px;
}

.pending-diff-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.pending-diff-title {
  font-size: 14px;
  font-weight: 700;
  color: #e5e7eb;
}

.pending-diff-subtitle {
  font-size: 12px;
  color: #9ca3af;
}

.pending-diff-item {
  padding: 12px;
  border: 1px solid #2d2d2d;
  border-radius: 10px;
  background: #111827;
  margin-top: 12px;
}

.pending-diff-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.pending-diff-field-label {
  font-weight: 700;
  color: #93c5fd;
}

.pending-diff-actions {
  display: flex;
  gap: 8px;
}

.btn-icon-approve,
.btn-icon-reject {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  font-size: 16px;
  cursor: pointer;
  transition: transform 0.12s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-icon-approve {
  background: #10b981;
  color: #fff;
}

.btn-icon-reject {
  background: #ef4444;
  color: #fff;
}

.btn-icon-approve:hover,
.btn-icon-reject:hover {
  transform: scale(1.06);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #e4e7ed;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.action-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
}

.delete-icon {
  font-size: 16px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .main-content {
    flex-direction: column;
  }
  
  .sidebar-right.sidebar-right--open {
    width: 100%;
    min-width: 0;
    max-width: none;
    border-left: none;
    border-top: 1px solid #e9ecef;
  }
  
  .status-section {
    flex-direction: column;
    gap: 12px;
  }
}

@media (max-width: 1200px) and (min-width: 769px) {
  .sidebar-right.sidebar-right--open {
    width: 280px;
    min-width: 280px;
    max-width: 280px;
  }
}

@media (min-width: 769px) {
  .main-content {
    flex-direction: row !important;
  }
  
  .sidebar-right.sidebar-right--open {
    width: 320px !important;
    min-width: 320px !important;
    max-width: 320px !important;
    border-left: 1px solid #e9ecef !important;
    border-top: none !important;
  }
}

/* 负责人下拉框样式 */
.assignee-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 2px solid #1976d2;
  border-radius: 6px;
  background: #fff;
  min-height: 40px;
}

.assignee-dropdown {
  position: relative;
  cursor: pointer;
}

.assignee-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
  margin-top: 4px;
  min-width: 300px;
  max-height: 400px;
  overflow-y: auto;
}

.assignee-search {
  position: relative;
  padding: 12px;
  border-bottom: 1px solid #e9ecef;
}

.assignee-section {
  margin-bottom: 8px;
}

.section-title {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.assignee-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.assignee-option:hover {
  background: #f8f9fa;
}

.assignee-option.selected {
  background: #e3f2fd;
}

.assignee-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.assignee-info {
  flex: 1;
  min-width: 0;
}

/* 计划下拉框样式 */
.plan-dropdown {
  position: relative;
  cursor: pointer;
}

.plan-selected-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 2px solid #1976d2;
  border-radius: 6px;
  background: #fff;
  transition: border-color 0.2s;
  min-height: 40px;
}

.plan-selected-display:hover {
  border-color: #1565c0;
}

.refresh-icon {
  font-size: 16px;
  color: #1976d2;
  cursor: pointer;
  transition: color 0.2s;
}

.refresh-icon:hover {
  color: #1565c0;
}

.plan-selected-text {
  flex: 1;
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.plan-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
  margin-top: 4px;
  min-width: 300px;
  max-height: 400px;
  overflow-y: auto;
}

.plan-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.plan-option:hover {
  background: #f8f9fa;
}

.plan-option.selected {
  background: #e3f2fd;
}

.plan-icon {
  font-size: 16px;
}

.plan-label {
  flex: 1;
}

/* 添加缺陷对话框样式 */
.defect-search-results {
  max-height: 280px;
  overflow-y: auto;
  margin-bottom: 12px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px;
  background: #fafbfc;
}

.defect-search-hint {
  padding: 12px;
  text-align: center;
  color: #888;
  font-size: 13px;
}

.defect-search-item {
  margin-bottom: 4px;
  cursor: pointer;
}

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.dialog-container {
  background: #fff;
  border-radius: 8px;
  width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e9ecef;
}

.dialog-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background: #f0f0f0;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.search-box {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.search-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  outline: none;
}

.search-input:focus {
  border-color: #409eff;
}

.search-btn {
  padding: 8px 16px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.search-btn:hover {
  background: #66b1ff;
}

.bug-tree-container {
  border: 1px solid #e9ecef;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
}

.tree-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  position: sticky;
  top: 0;
  z-index: 1;
}

.tree-title {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.refresh-btn:hover {
  background: #f0f0f0;
}

.bug-tree {
}

.tree-node {
  border-bottom: 1px solid #e9ecef;
}

.tree-node.sub-plan {
  margin-left: 20px;
  border-left: 2px solid #e9ecef;
}

.tree-node:last-child {
  border-bottom: none;
}

.tree-node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f8f9fa;
  cursor: pointer;
  transition: background-color 0.2s;
  user-select: none;
}

.tree-node-header:hover {
  background: #f0f0f0;
}

.expand-icon {
  font-size: 12px;
  color: #999;
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.plan-icon {
  font-size: 16px;
}

.plan-name {
  flex: 1;
  font-weight: 500;
  color: #333;
}

.bug-count {
  font-size: 12px;
  color: #999;
}

.tree-children {
  background: #fff;
}

.tree-children.loading {
  padding: 20px;
  text-align: center;
}

.loading-text {
  color: #999;
  font-size: 14px;
}

.no-bugs-tip {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 14px;
}

.bug-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px 10px 40px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.bug-item:last-child {
  border-bottom: none;
}

.bug-item:hover {
  background: #f8f9fa;
}

.bug-item.selected {
  background: #e3f2fd;
}

.checkbox {
  width: 16px;
  height: 16px;
  border: 2px solid #ddd;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.checkbox.checked {
  background: #409eff;
  border-color: #409eff;
}

.checkmark {
  color: white;
  font-size: 10px;
  font-weight: bold;
}

.bug-info {
  flex: 1;
  min-width: 0;
}

.bug-id {
  font-weight: 500;
  color: #409eff;
  margin-right: 8px;
}

.bug-title {
  color: #333;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #e9ecef;
}

.dialog-footer .btn-cancel,
.dialog-footer .btn-confirm {
  min-width: 80px;
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.2s, border-color 0.2s;
}

.dialog-footer .btn-cancel {
  background: #fff;
  border: 1px solid #dcdfe6;
  color: #606266;
}

.dialog-footer .btn-cancel:hover {
  background: #f5f7fa;
  border-color: #c0c4cc;
}

.dialog-footer .btn-confirm {
  background: #409eff;
  border: 1px solid #409eff;
  color: #fff;
}

.dialog-footer .btn-confirm:hover {
  background: #66b1ff;
  border-color: #66b1ff;
}

/* 关联缺陷样式 */
.related-defects {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.defect-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #f0f7ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  font-size: 13px;
}

.defect-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.defect-id {
  font-weight: 500;
  color: #409eff;
}

.defect-title {
  color: #606266;
}

.remove-defect-btn {
  background: none;
  border: none;
  color: #999;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
  transition: color 0.2s;
}

.remove-defect-btn:hover {
  color: #f56c6c;
}

.add-defect-btn {
  padding: 6px 12px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  color: #606266;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.add-defect-btn:hover {
  border-color: #409eff;
  color: #409eff;
}

/* 字段 diff 面板样式 */
.has-diff {
  position: relative;
}

.field-diff-panel {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.2);
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.diff-label {
  font-size: 14px;
  font-weight: 600;
  color: #92400e;
}

.diff-actions {
  display: flex;
  gap: 8px;
}

.diff-actions .btn-confirm,
.diff-actions .btn-cancel {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.diff-actions .btn-confirm {
  background: #10b981;
  color: white;
}

.diff-actions .btn-confirm:hover {
  background: #059669;
  transform: scale(1.1);
}

.diff-actions .btn-cancel {
  background: #ef4444;
  color: white;
}

.diff-actions .btn-cancel:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.diff-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.diff-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  min-width: 40px;
  text-align: center;
}

.diff-tag.old {
  background: #fee2e2;
  color: #991b1b;
}

.diff-tag.new {
  background: #d1fae5;
  color: #065f46;
}

.diff-value {
  flex: 1;
  font-size: 14px;
  color: #374151;
  word-break: break-all;
}

.diff-value-multiline {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
