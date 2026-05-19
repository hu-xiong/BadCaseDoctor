<template>
  <div class="bug-detail-wrapper" :class="{ 'is-embedded': embedded }">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载项目信息...</div>
    </div>
    
    <!-- 顶部标题栏：嵌入模式也需要返回等操作，保留显示 -->
    <div class="header-bar">
      <div class="header-left">
        <span v-if="!embedded || isEdit" class="back-arrow" @click="goBack">←</span>
        <span class="header-title">{{ isEdit ? '编辑Bug' : '新建Bug' }}</span>
        <span class="project-name" v-if="projectInfo.name">/ {{ projectInfo.name }}</span>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧主要内容区 -->
      <div class="content-left">
        <!-- 待采纳改动：仅「尚无对应表单项」的字段在顶部汇总；优先级/复现步骤等均在各自字段上方展示 -->
        <div
          v-if="showPendingDiffTopPanel"
          class="pending-diff-panel"
          :class="{ 'pending-diff-panel--embedded': embedded }"
        >
          <div class="pending-diff-header">
            <div class="pending-diff-title">待采纳改动</div>
            <div class="pending-diff-subtitle">逐字段采纳/拒绝；采纳会立即落库</div>
          </div>

          <template v-for="(data, field) in pendingDiff.modifications" :key="field">
          <div
            v-if="shouldShowPendingFieldInTop(field)"
            class="pending-diff-item"
            :id="`diff-field-${field}`"
          >
            <div class="pending-diff-item-head">
              <div class="pending-diff-field">
                <span class="pending-diff-field-label">{{ pendingDiffFieldLabel(field) }}</span>
              </div>
              <div class="pending-diff-actions">
                <button class="btn-icon-approve" title="采纳该字段" @click="applyFieldChange(field)">✓</button>
                <button class="btn-icon-reject" title="拒绝该字段" @click="cancelFieldChange(field)">✗</button>
              </div>
            </div>
            <div v-if="isShortListPendingField(field)" class="pending-diff-inline-row">
              <span class="pdi-chip pdi-old">{{ formatPendingShortFieldDisplay(field, data?.old) }}</span>
              <span class="pdi-arrow">→</span>
              <span class="pdi-chip pdi-new">{{ formatPendingShortFieldDisplay(field, data?.new) }}</span>
            </div>
            <MonacoDiffEditor
              v-else
              :original="String(data?.old ?? '')"
              :modified="String(data?.new ?? '')"
              language="markdown"
              theme="vs"
              height="200px"
              :renderSideBySide="false"
            />
          </div>
          </template>
        </div>

        <!-- 标题区域 -->
        <div class="title-section">
          <input 
            v-model="bug.title" 
            class="title-input" 
            placeholder="请输入Bug标题"
            maxlength="100"
          />
          <div class="title-count">{{ bug.title.length }} / 100</div>
        </div>

        <!-- 状态和负责人信息 -->
        <div class="status-section">
          <div class="status-item">
            <span class="status-label">流程状态:</span>
            <div class="status-dropdown" @click="toggleStatusDropdown">
              <div class="status-pill">
                <span class="status-text">{{ getStatusText(bug.status) }}</span>
                <span class="arrow-icon" :class="{ 'rotated': showStatusDropdown }">▼</span>
              </div>
              <div v-if="showStatusDropdown" class="status-dropdown-menu">
                <div 
                  v-for="status in availableStatuses" 
                  :key="status.value"
                  class="status-option"
                  :class="{ 'selected': bug.status === status.value }"
                  @click.stop="selectStatus(status.value)"
                >
                  {{ status.label }}
                </div>
              </div>
            </div>
          </div>
          <div class="status-item">
            <span class="status-label">负责人:</span>
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
                    placeholder="输入关键字搜索"
                    class="search-input"
                    @click.stop
                  />
                  <span class="search-icon">🔍</span>
                </div>
                
                <!-- 当前用户 -->
                <div class="assignee-section">
                  <div class="section-title">当前用户</div>
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
                      <div v-if="personSecondaryLabel(currentUser) || currentUser.department" class="assignee-id">
                        {{ personSecondaryLabel(currentUser) || currentUser.department || '未设置部门' }}
                      </div>
                    </div>
                  </div>
                  <div v-else class="no-user-tip">
                    <span class="tip-icon">⚠️</span>
                    <span class="tip-text">未获取到当前用户信息</span>
                  </div>
                </div>
                
                <!-- 最近选择的 -->
                <div class="assignee-section">
                  <div class="section-title">最近选择的</div>
                  <div 
                    v-if="recentAssignees.length > 0"
                    v-for="assignee in recentAssignees" 
                    :key="assignee.value"
                    class="assignee-option"
                    :class="{ 'selected': isAssigneeSelected(assignee.value) }"
                    @click.stop="toggleAssignee(assignee.value)"
                  >
                    <div class="checkbox" :class="{ 'checked': isAssigneeSelected(assignee.value) }">
                      <span v-if="isAssigneeSelected(assignee.value)" class="checkmark">✓</span>
                    </div>
                    <div class="assignee-avatar">{{ assignee.avatar }}</div>
                    <div class="assignee-info">
                      <div class="assignee-name">{{ personPrimaryLabel(assignee) }}</div>
                      <div v-if="assignee.id != null" class="assignee-id">ID {{ assignee.id }}</div>
                      <div v-if="assignee.department" class="assignee-dept">{{ assignee.department }}</div>
                    </div>
                  </div>
                  <div v-else class="no-recent-tip">
                    <span class="tip-icon">ℹ️</span>
                    <span class="tip-text">暂无最近选择的用户</span>
                  </div>
                </div>
                
                <!-- 项目成员 -->
                <div v-if="projectMembers.length > 0" class="assignee-section">
                  <div class="section-title">项目成员 ({{ projectMembers.length }}人)</div>
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
                <div v-else-if="bug.project_id && projectMembers.length === 0" class="assignee-section">
                  <div class="section-title">项目成员 (0人)</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">ℹ️</span>
                    <span class="tip-text">该项目暂无成员，请先添加项目成员</span>
                  </div>
                </div>
                
                <!-- 未选择项目时的提示 -->
                <div v-else-if="!bug.project_id" class="assignee-section">
                  <div class="section-title">项目成员</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">⚠️</span>
                    <span class="tip-text">请先选择所属项目</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="status-item">
            <span class="status-label">所属计划:</span>
            <div class="plan-dropdown" @click="togglePlanDropdown">
              <!-- 当前选中的计划显示区域 -->
              <div class="plan-selected-display">
                <span class="refresh-icon" @click.stop="refreshProjectPlans">🔄</span>
                <span class="plan-selected-text">
                  所属计划 {{ getSelectedPlanDisplayText }}
                </span>
                <span class="arrow-icon" :class="{ 'rotated': showPlanDropdown }">▼</span>
              </div>
              
              <div v-if="showPlanDropdown" class="plan-dropdown-menu">
                <!-- 搜索框 -->
                <div class="plan-search">
                  <input 
                    type="text" 
                    v-model="planSearchText"
                    placeholder="搜索计划"
                    class="search-input"
                    @click.stop
                    @keyup.enter="searchPlans"
                  />
                  <button class="search-btn" @click="searchPlans">
                    <span class="search-icon">🔍</span>
                  </button>
                  <button v-if="planSearchText" class="clear-search-btn" @click="clearPlanSearch" title="清除搜索">
                    <span class="clear-icon">✕</span>
                  </button>
                </div>
                
                <!-- 计划列表 -->
                <div class="plan-list">

                  
                  <template v-for="plan in filteredPlans" :key="plan.value">
                    <div 
                      v-if="plan"
                      class="plan-option"
                      :class="{ 
                        'selected': isPlanSelected(plan.value), 
                        'expandable': plan.children && plan.children.length > 0,
                        'pinned': plan.is_pinned
                      }"
                      :data-level="plan.level || 0"
                      @click.stop="selectPlan(plan.value)"
                    >
                      <!-- 展开/收起箭头 -->
                      <span 
                        v-if="plan.children && plan.children.length > 0" 
                        class="expand-arrow"
                        :class="{ 'expanded': expandedPlans.includes(plan.value) }"
                        @click.stop="togglePlanExpansion(plan.value)"
                      >▶</span>
                      <span v-else class="expand-placeholder"></span>
                      
                      <!-- 计划图标 -->
                      <span class="plan-icon">{{ plan.icon || '📁' }}</span>
                      
                      <!-- 计划名称 -->
                      <span class="plan-name">
                        {{ plan.label }}
                        <span v-if="plan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                      </span>
                      
                      <!-- 计划信息（Bug数量） -->
                      <span class="plan-info" v-if="plan.bug_count > 0">
                        <span class="count-badge bug">{{ plan.bug_count }}</span>
                      </span>
                    </div>
                    
                    <!-- 子计划列表 -->
                    <div v-if="plan && plan.children && plan.children.length > 0 && expandedPlans.includes(plan.value)" class="sub-plan-list">
                      <div 
                        v-for="childPlan in plan.children" 
                        :key="childPlan.value"
                        class="plan-option sub-plan"
                        :class="{ 
                          'selected': isPlanSelected(childPlan.value),
                          'expandable': childPlan.children && childPlan.children.length > 0
                        }"
                        :data-level="(plan.level || 0) + 1"
                        @click.stop="selectPlan(childPlan.value)"
                      >

                        <!-- 子计划展开/收起箭头 -->
                        <span 
                          v-if="childPlan.children && childPlan.children.length > 0" 
                          class="expand-arrow"
                          :class="{ 'expanded': expandedPlans.includes(childPlan.value) }"
                          @click.stop="togglePlanExpansion(childPlan.value)"
                        >▶</span>
                        <span v-else class="expand-placeholder"></span>
                        
                        <!-- 子计划图标 -->
                        <span class="plan-icon">{{ childPlan.icon || '📁' }}</span>
                        
                        <!-- 子计划名称 -->
                        <span class="plan-name">
                          {{ childPlan.label }}
                          <span v-if="childPlan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                        </span>
                        
                        <!-- 子计划信息 -->
                        <span class="plan-info" v-if="childPlan.bug_count > 0">
                          <span class="count-badge bug">{{ childPlan.bug_count }}</span>
                        </span>
                        
                        <!-- 孙计划列表 -->
                        <div v-if="childPlan.children && childPlan.children.length > 0 && expandedPlans.includes(childPlan.value)" class="sub-plan-list level-2">
                          <div 
                            v-for="grandChildPlan in childPlan.children" 
                            :key="grandChildPlan.value"
                            class="plan-option sub-plan level-2"
                            :class="{ 'selected': isPlanSelected(grandChildPlan.value) }"
                            :data-level="(plan.level || 0) + 2"
                            @click.stop="selectPlan(grandChildPlan.value)"
                          >

                            <span class="expand-placeholder"></span>
                            <span class="plan-icon">{{ grandChildPlan.icon || '📁' }}</span>
                            <span class="plan-name">
                              {{ grandChildPlan.label }}
                              <span v-if="grandChildPlan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                            </span>
                            <span class="plan-info" v-if="grandChildPlan.bug_count > 0">
                              <span class="count-badge bug">{{ grandChildPlan.bug_count }}</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                  
                  <!-- 如果没有计划，显示提示信息 -->
                  <div v-if="filteredPlans.length === 0" class="no-plans" style="padding: 20px; text-align: center; color: #666;">
                    暂无计划数据
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

                
        <!-- 复现步骤编辑器（Tiptap） -->
        <div class="editor-section" :class="{ 'has-diff': pendingDiff?.modifications?.reproduction_steps || pendingDiff?.modifications?.steps_to_reproduce }">
          <!-- diff 显示区域 -->
          <div v-if="pendingDiff?.modifications?.reproduction_steps || pendingDiff?.modifications?.steps_to_reproduce" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">复现步骤修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('reproduction_steps')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('reproduction_steps')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-old">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ (pendingDiff.modifications.reproduction_steps || pendingDiff.modifications.steps_to_reproduce)?.old || '未设置' }}</span>
              </div>
              <div class="diff-arrow">→</div>
              <div class="diff-new">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ (pendingDiff.modifications.reproduction_steps || pendingDiff.modifications.steps_to_reproduce)?.new }}</span>
              </div>
            </div>
          </div>
          <div class="editor-content">
            <div class="editor-title-row">
              <h3 class="editor-title">Bug复现步骤:</h3>
              <button type="button" class="toolbar-btn" title="添加附件到侧栏" @click="addAttachment">📎</button>
            </div>
            <RichTextHtmlEditor
              v-model="bug.reproduction_steps"
              class="editor-textarea"
              placeholder="请详细描述Bug的复现步骤..."
            />
            <div class="editor-count">{{ stepsLength }} / 2000</div>
          </div>
        </div>
        
        <!-- 期望结果输入框 -->
        <div class="answer-section" :class="{ 'has-diff': pendingDiff?.modifications?.expected_result }">
          <!-- diff 显示区域 -->
          <div v-if="pendingDiff?.modifications?.expected_result" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">期望结果修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('expected_result')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('expected_result')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-row">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ pendingDiff.modifications.expected_result?.old || '未设置' }}</span>
              </div>
              <div class="diff-row">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ pendingDiff.modifications.expected_result?.new }}</span>
              </div>
            </div>
          </div>
          <h3 class="answer-title">期望结果:</h3>
          <textarea 
            v-model="bug.expected_result" 
            class="answer-textarea" 
            placeholder="请输入期望结果..."
            maxlength="1000"
          ></textarea>
          <div class="answer-count">{{ bug.expected_result.length }} / 1000</div>
        </div>
        
        <!-- 实际结果输入框 -->
        <div class="correct-answer-section" :class="{ 'has-diff': pendingDiff?.modifications?.actual_result }">
          <!-- diff 显示区域 -->
          <div v-if="pendingDiff?.modifications?.actual_result" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">实际结果修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('actual_result')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('actual_result')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-row">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ pendingDiff.modifications.actual_result?.old || '未设置' }}</span>
              </div>
              <div class="diff-row">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ pendingDiff.modifications.actual_result?.new }}</span>
              </div>
            </div>
          </div>
          <h3 class="correct-answer-title">实际结果:</h3>
          <textarea 
            v-model="bug.actual_result" 
            class="correct-answer-textarea" 
            placeholder="请输入实际结果..."
            maxlength="1000"
          ></textarea>
          <div class="correct-answer-count">{{ bug.actual_result.length }} / 1000</div>
        </div>
                
        <!-- 问题分类和优先级 -->
        <div class="category-section">
          <div class="form-row form-row--stack-field" :class="{ 'has-diff': pendingDiff?.modifications?.case_category }">
            <label class="form-label required">问题分类:</label>
            <div class="form-row-field-col">
              <div
                v-if="pendingDiff?.modifications?.case_category"
                id="diff-field-case_category"
                class="field-diff-panel field-diff-panel--stacked"
              >
                <div class="diff-header">
                  <span class="diff-label">问题分类修改预览:</span>
                  <div class="diff-actions">
                    <button type="button" @click="applyFieldChange('case_category')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button type="button" @click="cancelFieldChange('case_category')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-row">
                    <span class="diff-tag old">原值</span>
                    <span class="diff-value">{{ pendingDiff.modifications.case_category?.old || '未设置' }}</span>
                  </div>
                  <div class="diff-row">
                    <span class="diff-tag new">新值</span>
                    <span class="diff-value">{{ pendingDiff.modifications.case_category?.new }}</span>
                  </div>
                </div>
              </div>
              <select
                v-model="bug.case_category"
                class="form-select"
                :class="{ 'field-with-diff': pendingDiff?.modifications?.case_category }"
              >
            <option value="">请选择问题分类</option>
            <option value="功能缺陷">功能缺陷</option>
            <option value="性能问题">性能问题</option>
            <option value="界面问题">界面问题</option>
            <option value="兼容性问题">兼容性问题</option>
            <option value="安全问题">安全问题</option>
            <option value="其他">其他</option>
            </select>
            </div>
          </div>
          <div class="form-row form-row--stack-field" :class="{ 'has-diff': pendingDiff?.modifications?.priority }">
            <label class="form-label required">优先级:</label>
            <div class="form-row-field-col">
              <div
                v-if="pendingDiff?.modifications?.priority"
                id="diff-field-priority"
                class="field-diff-panel field-diff-panel--stacked"
              >
                <div class="diff-header">
                  <span class="diff-label">优先级修改预览:</span>
                  <div class="diff-actions">
                    <button type="button" @click="applyFieldChange('priority')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                    <button type="button" @click="cancelFieldChange('priority')" class="btn-cancel" title="取消">✗</button>
                  </div>
                </div>
                <div class="diff-content">
                  <div class="diff-row">
                    <span class="diff-tag old">原值</span>
                    <span class="diff-value">{{ formatBugPriorityLabel(pendingDiff.modifications.priority.old) }}</span>
                  </div>
                  <div class="diff-row">
                    <span class="diff-tag new">新值</span>
                    <span class="diff-value">{{ formatBugPriorityLabel(pendingDiff.modifications.priority.new) }}</span>
                  </div>
                </div>
              </div>
              <select v-model="bug.priority" class="form-select" :class="{ 'field-with-diff': pendingDiff?.modifications?.priority }">
              <option value="">请选择优先级</option>
              <option value="p1">P1 - 紧急</option>
              <option value="p2">P2 - 高</option>
              <option value="p3">P3 - 中</option>
              <option value="p4">P4 - 低</option>
            </select>
            </div>
          </div>
        </div>
        <!-- 底部操作区 -->
        <div class="footer-section">
          <div class="footer-tip">
            <span class="tip-icon">💡</span>
            通过配置层级限制，可以约束父子卡片的类型关系
          </div>
          <div class="footer-actions">
            <button class="action-btn cancel-btn" @click="goBack">取消</button>
            <button class="action-btn save-btn" @click="saveBug" :disabled="saveLoading">
              {{ saveLoading ? '保存中...' : '保存' }}
            </button>
                    </div>
                  </div>
                </div>
                
      <!-- 右侧边栏：默认收起；展开后为固定宽度，不会继续 flex 拉宽 -->
      <div class="right-panel-column">
        <button
          v-show="!isRightSidebarOpen"
          type="button"
          class="sidebar-expand-tab"
          title="展开侧栏"
          aria-label="展开侧栏"
          @click="isRightSidebarOpen = true"
        >
          <img src="../assets/resize-icon.svg" alt="" class="resize-icon resize-icon--expand" />
        </button>
        <div class="sidebar-right" :class="{ 'sidebar-right--open': isRightSidebarOpen }">
        <div class="resize-handle" role="button" tabindex="0" title="收起侧栏" @click="toggleRightSidebar" @keydown.enter.prevent="toggleRightSidebar" @keydown.space.prevent="toggleRightSidebar">
          <img src="../assets/resize-icon.svg" alt="" class="resize-icon" :class="{ 'rotated': isRightSidebarOpen }" />
        </div>
        
        <!-- 所属项目 -->
        <div class="sidebar-section">
          <h3 class="sidebar-title">所属项目</h3>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" v-model="bug.associate_project" :value="true" />
              <span class="radio-text">关联所属项目</span>
            </label>
            <label class="radio-item">
              <input type="radio" v-model="bug.associate_project" :value="false" />
              <span class="radio-text">暂不关联所属项目</span>
            </label>
          </div>
          <div v-if="bug.associate_project" class="project-select">
            <label class="select-label">项目名称:</label>
            <select v-model="bug.project_id" class="form-select" @change="handleProjectChange">
              <option value="">请选择</option>
              <option v-for="project in availableProjects" :key="project.id" :value="project.id.toString()">
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
               <span class="header-title">关联文档</span>
             </div>
             <button class="ai-recommend-btn">
               <span class="ai-icon">🤖</span>
               <span class="ai-text">推荐关联</span>
             </button>
           </div>
           <div class="document-fields">
             <div class="field-row">
               <span class="field-label">文档类型:</span>
               <span class="field-value">{{ bug.document_type || '其他文档' }}</span>
             </div>
             <div class="field-row">
               <span class="field-label">文件链接:</span>
               <button class="copy-link-btn" @click="copyDocumentLink">
                 复制知识库文档链接
               </button>
             </div>
           </div>
         </div>

         <!-- 附件 -->
         <div class="sidebar-section">
           <div class="section-header">
             <div class="header-left">
               <span class="header-icon">📎</span>
               <span class="header-title">附件</span>
             </div>
             <button class="add-attachment-btn" @click="addAttachment">
               <span class="plus-icon">+</span>
             </button>
           </div>
           <div class="attachment-list">
             <div v-for="(attachment, index) in bug.attachments" :key="index" class="attachment-item">
               <span class="attachment-name">{{ attachment.name }}</span>
               <button class="remove-attachment-btn" @click="removeAttachment(index)">×</button>
             </div>
             <div v-if="bug.attachments.length === 0" class="no-attachments">
               暂无附件
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

         <div class="sidebar-section comment-section" :class="{ 'has-diff': hasEntityFieldDiff('append_comment') }">
           <h3 class="sidebar-title">评论记录</h3>
           <div v-if="hasEntityFieldDiff('append_comment')" class="field-diff-panel field-diff-panel--stacked comment-diff-panel">
             <div class="diff-header">
               <span class="diff-label">追加评论 · 修改预览</span>
               <div class="diff-actions">
                 <button type="button" @click="applyFieldChange('append_comment')" class="btn-confirm" title="采纳">✓</button>
                 <button type="button" @click="cancelFieldChange('append_comment')" class="btn-cancel" title="取消">✗</button>
               </div>
             </div>
             <div class="diff-content">
               <div class="diff-row">
                 <span class="diff-tag new">新评论</span>
                 <span class="diff-value diff-value-multiline">{{ formatEntityDiffValue('append_comment', entityFieldDiff('append_comment')?.new) }}</span>
               </div>
             </div>
           </div>
           <div v-if="entityComments.length" class="comment-timeline">
             <div v-for="c in entityComments" :key="c.id" class="comment-item">
               <div class="comment-item-meta">
                 <span class="comment-author">{{ c.user_name || '—' }}</span>
                 <span class="comment-time">{{ formatCommentTime(c.created_at) }}</span>
                 <span v-if="c.source_message_id" class="comment-op-tag">来自对话操作</span>
               </div>
               <div class="comment-item-body" v-html="c.content"></div>
             </div>
           </div>
           <div v-else class="comment-empty">暂无评论</div>
           <h4 class="comment-input-subtitle">输入评论</h4>
           <div class="comment-input-container">
             <template v-if="!commentEditorActive">
               <textarea
                 class="comment-textarea-simple"
                 readonly
                 rows="3"
                 :value="commentDraftText"
                 placeholder="点击输入评论…"
                 @click="activateCommentEditor"
               />
               <div class="comment-count">{{ commentDraftLength }} / 500</div>
             </template>
             <template v-else>
               <RichTextHtmlEditor
                 v-model="commentDraft"
                 variant="compact"
                 placeholder="请输入评论"
                 class="rich-editor"
               />
               <div class="comment-editor-actions">
                 <button type="button" class="comment-collapse-btn" @click="finishCommentEditor">收起</button>
                 <button
                   v-if="isEdit && bugId"
                   type="button"
                   class="comment-submit-btn"
                   :disabled="commentSubmitting || !commentDraftLength"
                   @click="submitCommentDraft"
                 >
                   发表评论
                 </button>
               </div>
               <div class="editor-count">{{ commentDraftLength }} / 500</div>
             </template>
           </div>
         </div>

        </div>
      </div>
    </div>
    

  </div>
</template>

<script>
import { ref, reactive, onMounted, onActivated, computed, nextTick, inject, watch, defineAsyncComponent } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { BACKEND_BASE_URL, createBug, getBugDetail, updateBug, addBugComment, getProjectDetail, getProjectEditContext, getProjectPlans, getProjectMembers, getCurrentUser, getProjects, getPlanDetail } from '../api.js'
import { snowflakeIdStr, normalizePlanId, isEmptyPlanKey } from '../utils/snowflakeId.js'
import { richTextHtmlHasContent, richTextHtmlDisplayLength } from '../utils/richTextContent.js'
import { personPrimaryLabel, personSecondaryLabel, applyDefaultAssigneeOnCreate } from '../utils/personLabel'
import user from '../store/user.js'
import RichTextHtmlEditor from './RichTextHtmlEditor.vue'

const MonacoDiffEditor = defineAsyncComponent(() => import('./MonacoDiffEditor.vue'))

export default {
  name: 'NewBug',
  components: { MonacoDiffEditor, RichTextHtmlEditor },
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
    embedded: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'titleLoaded'],
  setup(props, { emit }) {
    const router = useRouter()
    const route = useRoute()
    if (import.meta.env.DEV) {
      console.log('[NewBug] props.card_id:', props.card_id, 'id:', props.id)
    }
    const loading = ref(false)
    const saveLoading = ref(false)
    const isEdit = ref(false)
    const bugId = ref(null)
    const isRightSidebarOpen = ref(false)
    const toggleRightSidebar = () => {
      isRightSidebarOpen.value = !isRightSidebarOpen.value
    }
    
    const projectInfo = ref({})
    const availableProjects = ref([])
    
    // 项目成员列表
    const projectMembers = ref([])
    const showStatusDropdown = ref(false)
    const showAssigneeDropdown = ref(false)
    
    // 可用状态列表
    const availableStatuses = ref([
      { value: 'new', label: '新建' },
      { value: 'not_a_bug', label: 'not_a_bug' },
      { value: 'new_feature', label: 'new_feature' },
      { value: 'closed', label: 'closed' },
      { value: 'hold', label: 'hold' },
      { value: 'reopened', label: 'reopened' },
      { value: 'resolved', label: 'resolved' }
    ])

    /** 列表行内已展示采纳时，嵌入顶栏不再重复 title/status/assignee */
    const PENDING_TOP_LIST_FIELDS = ['title', 'status', 'assignee']
    /** 主表单内已有「字段上方」diff 区，勿再放入顶部 pending 汇总（含嵌入模式） */
    const PENDING_DETAIL_INLINE_FIELDS = new Set([
      'priority',
      'case_category',
      'reproduction_steps',
      'steps_to_reproduce',
      'reproduce_steps',
      'expected_result',
      'actual_result'
    ])
    const PENDING_FIELD_LABELS = {
      title: '标题',
      status: '流程状态',
      assignee: '负责人',
      priority: '优先级',
      expected_result: '预期结果',
      actual_result: '实际结果',
      reproduction_steps: '复现步骤',
      comment: '备注',
      severity: '严重级别',
      case_category: '问题分类',
      environment: '环境',
      browser: '浏览器',
      os: '操作系统',
      plan: '计划'
    }

    // 当前用户信息 - 使用全局用户状态
    const currentUser = computed(() => user.value)
    
    // 最近选择的用户列表（暂时为空，后续可以从历史记录中获取）
    const recentAssignees = ref([])
    
    const assigneeSearchText = ref('')
    const planSearchText = ref('')
    const showPlanDropdown = ref(false)
    
    // 已展开的计划ID列表
    const expandedPlans = ref([])
    /** 计划树未命中时的展示名（避免直接显示雪花 id） */
    const selectedPlanDisplayName = ref('')
    
    // 可用计划列表 - 将从当前项目动态获取
    const availablePlans = ref([])
    
    // 过滤后的计划列表（用于搜索）
    const filteredPlans = computed(() => {
      const searchText = planSearchText.value.toLowerCase().trim()
      console.log('filteredPlans计算属性被调用，searchText:', searchText)
      console.log('availablePlans.value:', availablePlans.value)
      
      const list = availablePlans.value.filter((p) => p?.value !== 'unplanned')
      if (!searchText) {
        return list
      }
      
      // 递归搜索计划
      const searchPlansRecursively = (plans) => {
        const filtered = []
        for (const plan of plans) {
          const planMatches = plan.label.toLowerCase().includes(searchText)
          let filteredChildren = []
          if (plan.children && plan.children.length > 0) {
            filteredChildren = searchPlansRecursively(plan.children)
          }
          if (planMatches || filteredChildren.length > 0) {
            const filteredPlan = { ...plan }
            if (filteredChildren.length > 0) {
              filteredPlan.children = filteredChildren
            }
            filtered.push(filteredPlan)
          }
        }
        return filtered
      }
      
      const result = searchPlansRecursively(list)
      console.log('搜索结果:', result)
      return result
    })
    
    // 待确认的 diff 数据
    const pendingDiff = ref(null)

    /** 嵌入：列表已处理 title/status/assignee；其余仅在顶部展示「无表单项」的字段。非嵌入：无独立 diff 区的字段可走顶部。 */
    const showPendingDiffTopPanel = computed(() => {
      const m = pendingDiff.value?.modifications
      if (!m) return false
      const keys = Object.keys(m).filter((k) => !String(k).startsWith('_'))
      if (!keys.length) return false
      const showInTop = (k) => {
        if (PENDING_DETAIL_INLINE_FIELDS.has(k)) return false
        if (props.embedded && PENDING_TOP_LIST_FIELDS.includes(k)) return false
        return true
      }
      return keys.some(showInTop)
    })
    
    const bug = reactive({
      title: '',
      expected_result: '',
      actual_result: '',
      severity: 'medium',
      priority: 'p3',
      status: 'new',
      case_category: '功能缺陷', // 默认问题分类为"功能缺陷"
      environment: '',
      browser: '',
      os: '',
      assignee: [],
      plan: '',
      reproduction_steps: '',
      comment: '',
      associate_project: true,
      project_id: '',
      document_type: '其他文档',
      attachments: []
    })

    // 获取状态文本（下拉配置优先，其次常用枚举）
    const getStatusText = (status) => {
      if (status == null || status === '') return '—'
      const s = String(status)
      const hit = availableStatuses.value.find((x) => String(x.value) === s)
      if (hit) return hit.label
      const statusMap = {
        new: '新建',
        close: '已关闭',
        closed: '已关闭',
        pending: '处理中',
        resolved: '已解决',
        hold: '搁置',
        reopen: '重新打开',
        reopened: '重新打开',
        not_a_bug: '非缺陷',
        not_badcase: '非 BadCase'
      }
      return statusMap[s] || s
    }

    const pendingDiffFieldLabel = (field) =>
      PENDING_FIELD_LABELS[String(field)] || String(field)

    const shouldShowPendingFieldInTop = (field) => {
      const f = String(field || '')
      if (f.startsWith('_')) return false
      if (props.embedded && PENDING_TOP_LIST_FIELDS.includes(f)) return false
      if (PENDING_DETAIL_INLINE_FIELDS.has(f)) return false
      return true
    }

    const isShortListPendingField = (field) => PENDING_TOP_LIST_FIELDS.includes(String(field))

    const formatPendingShortFieldDisplay = (field, raw) => {
      if (raw == null || String(raw).trim() === '') return '未设置'
      const f = String(field)
      if (f === 'status') return getStatusText(String(raw))
      if (f === 'assignee') {
        if (typeof raw === 'object' && raw !== null && !Array.isArray(raw)) {
          return String(raw.name ?? raw.id ?? raw.username ?? '—')
        }
        if (Array.isArray(raw)) {
          return raw
            .map((x) =>
              typeof x === 'object' && x != null
                ? String(x.name ?? x.id ?? x.username ?? '')
                : String(x)
            )
            .filter(Boolean)
            .join('、') || '—'
        }
        return String(raw)
      }
      return String(raw)
    }

    // 获取项目成员列表
    const fetchProjectMembers = async (projectId) => {
      if (!projectId) {
        console.log('fetchProjectMembers: 没有项目ID，跳过')
        return
      }
      
      console.log('fetchProjectMembers: 开始获取项目成员，项目ID:', projectId)
      try {
        const response = await getProjectMembers(projectId)
        console.log('fetchProjectMembers: API响应:', response)
        if (response.data.success) {
          projectMembers.value = response.data.members || []
          console.log('项目成员获取成功:', projectMembers.value)
        } else {
          console.log('fetchProjectMembers: API返回失败:', response.data)
          projectMembers.value = []
        }
      } catch (error) {
        console.error('获取项目成员失败:', error)
        projectMembers.value = []
      }
    }

    // 项目选择改变时的处理
    const handleProjectChange = () => {
      const projectId = bug.project_id
      const oldProjectId = bug._previousProjectId // 保存之前的项目ID
      console.log('handleProjectChange: 项目选择改变，项目ID:', projectId, '之前项目ID:', oldProjectId)
      
      // 只有在项目真正改变时才清空相关数据
      if (oldProjectId !== projectId) {
        console.log('项目ID发生变化，清空相关数据')
        
        // 在编辑模式下，如果项目ID没有真正改变，保持现有数据
        if (isEdit.value && oldProjectId && oldProjectId.toString() === projectId.toString()) {
          console.log('编辑模式下项目ID未真正改变，保持现有数据')
        } else {
          bug.plan = ''
          // 清空负责人选择
          bug.assignee = []
          availablePlans.value = []
          // 清空项目成员
          projectMembers.value = []
        }
      } else {
        console.log('项目ID未变化，保持现有数据')
      }
      
      // 更新之前的项目ID
      bug._previousProjectId = projectId
      
      // 获取项目信息（未在下拉列表中的项目也可通过 edit-context 拉齐 plans/members）
      if (projectId) {
        const project = availableProjects.value.find(p => p.id == projectId)
        if (project) {
          projectInfo.value = project
          console.log('handleProjectChange: 找到项目信息:', project.name)
        } else {
          console.log('handleProjectChange: 未在下拉列表中找到项目，仍尝试 edit-context')
        }
        projectWorkspaceLoaded.value = false
        void applyProjectEditContext(projectId)
      } else {
        projectWorkspaceLoaded.value = false
        console.log('handleProjectChange: 没有项目ID')
      }
    }

    // 获取当前用户信息
    const fetchCurrentUser = async () => {
      try {
        // 如果全局用户状态已经存在，直接使用
        if (user.value) {
          console.log('使用全局用户状态:', user.value)
          return
        }
        
        const response = await getCurrentUser()
        if (response.data.success) {
          // 更新全局用户状态
          user.value = response.data.user
          console.log('当前用户信息获取成功:', user.value)
        } else {
          console.error('获取当前用户失败:', response.data)
        }
      } catch (error) {
        console.error('获取当前用户失败:', error)
      }
    }
    
    // 编辑页不需要拉全量项目列表（包含头像等），避免额外慢接口
    
    /** 一次请求拉齐 project + plans + members（与 /edit-context 对齐），避免 /plans + /members 各打一遍 */
    const projectWorkspaceLoaded = ref(false)
    const applyProjectEditContext = async (projectId) => {
      const pidStr = snowflakeIdStr(projectId) || (projectId != null && String(projectId).trim() !== '' ? String(projectId).trim() : '')
      if (!pidStr) return false
      try {
        const resp = await getProjectEditContext(pidStr)
        if (!resp.data?.success) return false
        projectInfo.value = resp.data.project || projectInfo.value
        projectMembers.value = resp.data.members || []
        if (resp.data.project && !availableProjects.value.find((p) => p.id == resp.data.project.id)) {
          availableProjects.value.push(resp.data.project)
        }
        await setAvailablePlansFromTree(resp.data.plans || [])
        projectWorkspaceLoaded.value = true
        return true
      } catch (e) {
        console.error('applyProjectEditContext 失败:', e)
        return false
      }
    }

    // 使用后端 plans 树直接生成下拉选项（避免额外请求 /plans）
    const setAvailablePlansFromTree = async (plansTree) => {
      const formattedPlans = []

      const processPlans = (planList, level = 0) => {
        const processedPlans = []
        ;(planList || []).forEach(plan => {
          const children = plan.children && plan.children.length > 0 ? processPlans(plan.children, level + 1) : []

          const isBugPlan = true
          const planIdStr = snowflakeIdStr(plan.id) || String(plan.id)
          const isSelected = bug.plan && snowflakeIdStr(bug.plan) === planIdStr
          const hasVisibleChildren = children.length > 0

          if (isBugPlan || isSelected || hasVisibleChildren) {
            const planOption = {
              value: planIdStr,
              label: plan.name,
              level,
              is_pinned: plan.is_pinned || false,
              icon: plan.icon || '📁',
              bug_count: plan.bug_count || 0,
              status: plan.status
            }
            if (children.length > 0) planOption.children = children
            processedPlans.push(planOption)
          }
        })
        return processedPlans
      }

      formattedPlans.push(...processPlans(plansTree || []))
      availablePlans.value = formattedPlans
      await nextTick()
    }

    // 搜索计划
    const searchPlans = () => {
      console.log('搜索计划:', planSearchText.value)
      // 搜索逻辑已经在 computed 属性中实现
    }
    
    // 清除计划搜索
    const clearPlanSearch = () => {
      planSearchText.value = ''
      console.log('清除计划搜索')
    }
    
    // 获取选中计划的显示文本
    const planIdsMatch = (a, b) => {
      const sa = snowflakeIdStr(a) || String(a ?? '')
      const sb = snowflakeIdStr(b) || String(b ?? '')
      return sa !== '' && sb !== '' && sa === sb
    }

    const findPlanLabelInTree = (plans, planId) => {
      for (const plan of plans) {
        if (planIdsMatch(plan.value, planId)) return plan.label
        if (plan.children?.length) {
          const found = findPlanLabelInTree(plan.children, planId)
          if (found) return found
        }
      }
      return null
    }

    const planExistsInTree = (plans, planId) => {
      for (const plan of plans) {
        if (planIdsMatch(plan.value, planId)) return true
        if (plan.children?.length && planExistsInTree(plan.children, planId)) return true
      }
      return false
    }

    const ensurePlanOptionVisible = async (planKey) => {
      const key = normalizePlanId(planKey)
      if (!key) {
        selectedPlanDisplayName.value = ''
        return
      }
      const label = findPlanLabelInTree(availablePlans.value, key)
      if (label) {
        selectedPlanDisplayName.value = label
        return
      }
      if (planExistsInTree(availablePlans.value, key)) return
      try {
        const resp = await getPlanDetail(key)
        if (resp.data?.success && resp.data.plan) {
          const pl = resp.data.plan
          const idStr = snowflakeIdStr(pl.id) || String(pl.id)
          selectedPlanDisplayName.value = pl.name || ''
          const opt = {
            value: idStr,
            label: pl.name,
            level: 0,
            is_pinned: pl.is_pinned || false,
            icon: pl.icon || '📁',
            bug_count: pl.bug_count || 0,
            status: pl.status
          }
          if (!planExistsInTree(availablePlans.value, idStr)) {
            availablePlans.value = [
              ...availablePlans.value.filter((p) => !planIdsMatch(p.value, idStr)),
              opt
            ]
          }
        }
      } catch (e) {
        console.warn('补全计划名称失败:', e)
      }
    }

    const getSelectedPlanDisplayText = computed(() => {
      if (isEmptyPlanKey(bug.plan)) {
        return '请选择计划'
      }
      return (
        findPlanLabelInTree(availablePlans.value, bug.plan) ||
        selectedPlanDisplayName.value ||
        '…'
      )
    })

    const applyInitialPlanForCreate = (query, planIdProp) => {
      const raw = query.plan_id ?? planIdProp
      const id = normalizePlanId(raw)
      bug.plan = id || ''
    }
    
    // 刷新项目计划
    const refreshProjectPlans = async () => {
      if (bug.project_id) {
        console.log('刷新项目计划')
        await fetchProjectPlans(bug.project_id)
      }
    }
    
    // 展开/收起计划
    const togglePlanExpansion = (planId) => {
      const index = expandedPlans.value.indexOf(planId)
      if (index > -1) {
        expandedPlans.value.splice(index, 1)
      } else {
        expandedPlans.value.push(planId)
      }
      console.log('展开/收起计划:', planId, '当前展开状态:', expandedPlans.value)
    }
    
    // 获取项目列表
    const fetchProjects = async () => {
      try {
        console.log('=== 开始获取项目列表 ===')
        const response = await getProjects()
        if (response.data.success) {
          availableProjects.value = response.data.projects || []
          console.log('获取项目列表成功:', availableProjects.value.length, '个项目')
        } else {
          console.error('获取项目列表失败:', response.data)
        }
      } catch (error) {
        console.error('获取项目列表异常:', error)
      }
    }
    
    // 获取当前项目的计划列表
    const fetchProjectPlans = async (projectId) => {
      if (!projectId) {
        console.log('没有项目ID，跳过获取计划')
        return
      }
      
      try {
        console.log('=== 开始获取项目计划 ===')
        console.log('项目ID:', projectId)
        console.log('当前availablePlans:', availablePlans.value)
        console.log('调用getProjectPlans函数...')
        
        const response = await getProjectPlans(projectId)
        console.log('API响应:', response)
        console.log('API响应类型:', typeof response)
        console.log('API响应数据结构:', Object.keys(response || {}))
        
        if (response.data.success) {
          await setAvailablePlansFromTree(response.data.plans || [])
        } else {
          console.error('API返回失败:', response.data)
          availablePlans.value = []
        }
      } catch (error) {
        console.error('获取项目计划失败:', error)
        availablePlans.value = []
      }
    }
    
    // 初始化Bug数据
    const initBug = async () => {
      try {
        // 优先使用 props，其次使用路由参数
        const query = route.query
        console.log('=== 初始化Bug开始 ===')
        console.log('路由查询参数:', query)
        console.log('Props 参数:', props)
        
        // 判断是否编辑模式
        const isEditMode = props.edit || query.edit === 'true'
        const itemId = props.id || query.id
        
        const normalizedBugId = snowflakeIdStr(itemId) || (itemId != null && String(itemId).trim() !== '' ? String(itemId).trim() : '')
        if (isEditMode && normalizedBugId) {
          console.log('编辑模式，Bug ID:', itemId)
          isEdit.value = true
          bugId.value = normalizedBugId
          loading.value = true
        
        try {
          const response = await getBugDetail(normalizedBugId)
          if (response.data.success && response.data.bug) {
            console.log('=== Bug详情API响应 ===')
            console.log('完整响应:', response.data)
            console.log('Bug数据:', response.data.bug)
            console.log('复现步骤字段:', response.data.bug.reproduction_steps)
            console.log('复现步骤类型:', typeof response.data.bug.reproduction_steps)
            
            // 映射后端字段到前端响应式对象
            bug.title = response.data.bug.title
            bug.case_category = response.data.bug.bug_type
            bug.reproduction_steps = response.data.bug.steps_to_reproduce || response.data.bug.description || ''
            bug.expected_result = response.data.bug.expected_result
            bug.actual_result = response.data.bug.actual_result
            bug.severity = response.data.bug.severity
            bug.priority = response.data.bug.priority
            bug.status = response.data.bug.status
            bug.project_id = response.data.bug.project_id?.toString()
            bug.plan = normalizePlanId(response.data.bug.plan_id) || ''
            
            // 处理负责人：后端是单个 assignee_id，前端期待数组 [id]
            if (response.data.bug.assignee_id) {
              bug.assignee = [response.data.bug.assignee_id.toString()]
            } else {
              bug.assignee = []
            }
            
            // 处理附件
            if (response.data.bug.attachments) {
              try {
                bug.attachments = typeof response.data.bug.attachments === 'string' 
                  ? JSON.parse(response.data.bug.attachments) 
                  : response.data.bug.attachments
              } catch (e) {
                console.error('解析附件失败:', e)
                bug.attachments = []
              }
            }

            console.log('Bug信息映射成功:', bug)
            console.log('加载后的复现步骤:', bug.reproduction_steps)
            console.log('原始数据中的项目ID:', response.data.bug.project_id)
            console.log('原始数据中的计划ID:', response.data.bug.plan_id)
            
            // 确保编辑模式下正确设置关联项目状态
            entityComments.value = Array.isArray(response.data.bug.comments) ? [...response.data.bug.comments] : []

            if (bug.project_id) {
              bug.associate_project = true
              console.log('编辑模式：设置associate_project为true，项目ID:', bug.project_id)
              
              // 初始化_previousProjectId，避免handleProjectChange误判
              bug._previousProjectId = bug.project_id
              console.log('编辑模式：初始化_previousProjectId:', bug._previousProjectId)
            }
            
            // 复现步骤由 RichTextHtmlEditor v-model 绑定 bug.reproduction_steps

            // 获取项目计划列表和成员列表（编辑模式）
            if (bug.project_id) {
              console.log('编辑模式，获取项目计划，项目ID:', bug.project_id)
              
              // 确保项目列表已加载
              if (availableProjects.value.length === 0) {
                console.log('编辑模式：项目列表为空，先加载项目列表')
                await fetchProjects()
              }
              
              // 设置项目信息
              const project = availableProjects.value.find(p => p.id == bug.project_id)
              if (project) {
                projectInfo.value = project
                console.log('编辑模式：设置项目信息:', project.name)
              } else {
                console.log('编辑模式：未找到项目信息，availableProjects:', availableProjects.value)
                console.log('尝试查找项目，bug.project_id:', bug.project_id)
                console.log('availableProjects中的项目ID类型:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
              }
              
              await applyProjectEditContext(bug.project_id)
              await ensurePlanOptionVisible(bug.plan)
              
              // 确保数据同步
              console.log('编辑模式初始化完成后，当前状态:')
              console.log('- bug.project_id:', bug.project_id)
              console.log('- bug.associate_project:', bug.associate_project)
              console.log('- bug.plan:', bug.plan)
              console.log('- projectInfo:', projectInfo.value)
              console.log('- projectMembers.length:', projectMembers.value.length)
              console.log('- availablePlans.length:', availablePlans.value.length)
              
              // 强制触发响应式更新
              await nextTick()
              
              // 检查计划和负责人是否成功加载
              console.log('检查计划和负责人是否加载成功:')
              if (bug.plan) {
                const planMatch = availablePlans.value.find(p => p.value === bug.plan || p.value === bug.plan.toString())
                console.log(`计划 ${bug.plan} 匹配结果:`, planMatch ? '✓ 找到' : '✗ 未找到')
              }
              if (bug.assignee && bug.assignee.length > 0) {
                const assigneeId = bug.assignee[0]
                const memberMatch = projectMembers.value.find(
                  m => m.id != null && String(m.id) === String(assigneeId)
                )
                console.log(`负责人 ${assigneeId} 匹配结果:`, memberMatch ? `✓ 找到 (${memberMatch.name})` : '✗ 未找到')
              }
            } else {
              console.log('编辑模式，Bug没有项目ID')
            }
          } else {
            alert('获取Bug信息失败')
            goBack()
          }
        } catch (error) {
          console.error('=== 获取Bug信息失败 ===')
          console.error('错误类型:', error.name)
          console.error('错误消息:', error.message)
          console.error('错误堆栈:', error.stack)
          alert('获取Bug信息失败: ' + error.message)
          goBack()
        } finally {
          loading.value = false
          // 编辑模式下通知父组件更新Tab标题
          if (isEdit.value && bug.title) {
            emit('titleLoaded', bug.title)
          }
        }
      } else if (query.project_id || props.project_id) {
        console.log('新建模式，项目ID:', query.project_id)
        console.log('query.project_id类型:', typeof query.project_id)
        console.log('availableProjects:', availableProjects.value)
        
        // 新建模式，设置项目ID
        bug.project_id = String(query.project_id || props.project_id)
        console.log('设置bug.project_id:', bug.project_id)
        console.log('设置后bug.project_id类型:', typeof bug.project_id)
        
        // 获取项目信息
        const project = availableProjects.value.find(p => p.id == bug.project_id)
        if (project) {
          projectInfo.value = project
          console.log('找到项目信息:', project.name)
        } else {
          console.log('未找到项目信息，availableProjects:', availableProjects.value)
          console.log('尝试查找项目，query.project_id:', query.project_id)
          console.log('availableProjects中的项目ID类型:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
          // 兜底：按 ID 拉项目详情，确保下拉和标题有数据
          try {
            const detail = await getProjectDetail(snowflakeIdStr(bug.project_id) || String(bug.project_id))
            if (detail.data?.success && detail.data.project) {
              const prj = detail.data.project
              if (!availableProjects.value.find(p => p.id == prj.id)) {
                availableProjects.value.push(prj)
              }
              projectInfo.value = prj
            }
          } catch (e) {
            console.error('兜底获取项目详情失败:', e)
          }
        }
        
        console.log('开始获取项目计划/成员（edit-context），项目ID:', bug.project_id)
        await applyProjectEditContext(bug.project_id)
        if (!isEdit.value) {
          applyInitialPlanForCreate(query, props.plan_id)
          await ensurePlanOptionVisible(bug.plan)
          applyDefaultAssigneeOnCreate(bug, user.value, { isEdit: false })
        }
        
        // 确保数据同步
        console.log('初始化完成后，当前状态:')
        console.log('- bug.project_id:', bug.project_id)
        console.log('- projectMembers.length:', projectMembers.value.length)
        console.log('- availablePlans.length:', availablePlans.value.length)
      } else {
        console.log('没有项目ID参数')
        console.log('所有查询参数:', query)
      }
      
      console.log('=== 初始化Bug完成 ===')
      
      // 最终状态检查
      if (isEdit.value) {
        console.log('=== 编辑模式最终状态检查 ===')
        console.log('bug对象:', bug)
        console.log('bug.project_id:', bug.project_id)
        console.log('bug.plan:', bug.plan)
        console.log('bug.associate_project:', bug.associate_project)
        console.log('availableProjects:', availableProjects.value)
        console.log('availablePlans:', availablePlans.value)
        console.log('projectInfo:', projectInfo.value)
      }
    } catch (initError) {
      console.error('=== initBug函数执行失败 ===')
      console.error('错误类型:', initError.name)
      console.error('错误消息:', initError.message)
      console.error('错误堆栈:', initError.stack)
      alert('Bug初始化失败: ' + initError.message)
      loading.value = false
    }
  }

    // 保存Bug
    const saveBug = async () => {
      console.log('=== 开始保存Bug ===')
      console.log('当前Bug数据:', bug)
      console.log('当前复现步骤:', bug.reproduction_steps)
      
      if (!bug.title.trim()) {
        alert('请输入Bug标题')
        return
      }
      if (!bug.case_category) {
        alert('请选择问题分类')
        return
      }
      if (!bug.priority) {
        alert('请选择优先级')
        return
      }
      
      if (!richTextHtmlHasContent(bug.reproduction_steps)) {
        alert('请输入复现步骤')
        return
      }

      saveLoading.value = true
      try {
        // 仅新建模式添加 card_id，用于后端校验卡片类型（雪花 ID 勿 parseInt/Number）
        const cardIdStr = !isEdit.value && props.card_id != null && props.card_id !== '' ? snowflakeIdStr(props.card_id) : ''
        const cardIdValue = cardIdStr || null
        console.log('[saveBug] cardIdValue:', cardIdValue, 'props.card_id:', props.card_id, 'isEdit:', isEdit.value)
        const planIdStr = isEmptyPlanKey(bug.plan) ? '' : snowflakeIdStr(bug.plan)
        const projectIdStr = bug.project_id ? snowflakeIdStr(bug.project_id) : ''
        const assigneeRaw =
          Array.isArray(bug.assignee) && bug.assignee.length > 0 ? bug.assignee[0] : bug.assignee
        const assigneeStr = assigneeRaw != null && assigneeRaw !== '' ? snowflakeIdStr(assigneeRaw) : ''
        const bugData = {
          title: bug.title,
          bug_type: bug.case_category, // 对应后端的 bug_type
          description: bug.reproduction_steps || '', // 对应后端的 description
          steps_to_reproduce: bug.reproduction_steps || '', // 对应后端的 steps_to_reproduce
          expected_result: bug.expected_result || '待确认',
          actual_result: bug.actual_result || '待确认',
          priority: bug.priority,
          status: bug.status,
          plan_id: planIdStr || null,
          project_id: projectIdStr || null,
          assignee_id: assigneeStr || null, // Bug模型只支持单负责人ID
          attachments: JSON.stringify(bug.attachments.map(att => ({
            name: att.name,
            size: att.size
          }))) // 后端 attachments 是文本字段，通常存 JSON
        }
        // 新建时添加卡片ID
        if (cardIdValue) {
          bugData.card_id = cardIdValue
        }
        
        console.log('准备发送的Bug数据:', bugData)
        console.log('复现步骤字段值:', bugData.reproduction_steps)
        console.log('复现步骤字段类型:', typeof bugData.reproduction_steps)

        let result
        if (isEdit.value) {
          console.log('=== 更新Bug ===')
          console.log('Bug ID:', bugId.value)
          console.log('更新数据:', bugData)
          result = await updateBug(bugId.value, bugData)
          console.log('更新响应:', result)
          
          if (result.data.success) {
            alert('Bug更新成功')
            goBack()
          } else {
            alert(`更新失败: ${result.data.error || '未知错误'}`)
          }
        } else {
          console.log('=== 创建Bug ===')
          console.log('创建数据:', bugData)
          result = await createBug(bugData)
          console.log('创建Bug响应:', result)
          
          if (result.data.success) {
            alert('Bug创建成功')
            goBack()
          } else {
            const errorMsg = result.data.error || '未知错误'
            console.error('创建失败:', errorMsg)
            alert(`创建失败: ${errorMsg}`)
          }
        }
      } catch (error) {
        console.error('保存Bug失败:', error)
        console.error('错误详情:', error.response?.data || error.message)
        alert(`保存失败: ${error.response?.data?.error || error.message || '请重试'}`)
      } finally {
        saveLoading.value = false
      }
    }

    // 复制文档链接
    const copyDocumentLink = () => {
      const link = `https://knowledge-base.example.com/project/${bug.project_id}/documents`
      navigator.clipboard.writeText(link).then(() => {
        alert('文档链接已复制到剪贴板')
      }).catch(() => {
        alert('复制失败，请手动复制')
      })
    }

    // 添加附件
    const addAttachment = () => {
      fileInput.value.click()
    }

    // 处理文件上传
    const handleFileUpload = (event) => {
      const files = Array.from(event.target.files)
      files.forEach(file => {
        bug.attachments.push({
          name: file.name,
          size: file.size,
          file: file
        })
      })
      // 清空input值，允许重复选择同一文件
      event.target.value = ''
    }

    // 移除附件
    const removeAttachment = (index) => {
      bug.attachments.splice(index, 1)
    }

    const fileInput = ref(null)
    const commentEditorActive = ref(false)
    const activateCommentEditor = () => {
      commentEditorActive.value = true
    }
    const finishCommentEditor = () => {
      commentEditorActive.value = false
    }

    const bugDraftPreset = inject('bugDraftPreset', null)

    const stepsLength = computed(() => richTextHtmlDisplayLength(bug.reproduction_steps))
    
    const _escHtml = (s) =>
      String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
    watch(
      () => bugDraftPreset?.value?.token ?? 0,
      async (tok) => {
        if (!tok || !bugDraftPreset?.value?.description) return
        if (isEdit.value) return
        const block = String(bugDraftPreset.value.description).trim()
        if (!block) return
        const fragment = `<p><strong>【终端关联】</strong></p><pre style="white-space:pre-wrap;word-break:break-all;">${_escHtml(block)}</pre>`
        await nextTick()
        const cur = (bug.reproduction_steps || '').trim()
        bug.reproduction_steps = cur ? `${cur}<p><br></p>${fragment}` : fragment
      }
    )
    
    const entityComments = ref([])
    const commentDraft = ref('')
    const commentSubmitting = ref(false)

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

    const entityFieldDiff = (field) => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return null
      const keys = [field, 'comment']
      if (field === 'reproduction_steps') keys.push('steps_to_reproduce')
      for (const k of keys) {
        const m = mods[k]
        if (m && typeof m === 'object' && ('old' in m || 'new' in m)) return m
      }
      return null
    }
    const hasEntityFieldDiff = (field) => !!entityFieldDiff(field)
    const formatEntityDiffValue = (field, val) => {
      if (field === 'append_comment') {
        if (!val) return ''
        const tempDiv = document.createElement('div')
        tempDiv.innerHTML = String(val)
        return (tempDiv.textContent || tempDiv.innerText || '').trim() || String(val)
      }
      return val != null ? String(val) : ''
    }

    const loadEntityComments = async () => {
      const id = bugId.value
      if (!id) return
      try {
        const response = await getBugDetail(id)
        const list = response?.data?.bug?.comments
        entityComments.value = Array.isArray(list) ? [...list] : []
      } catch (e) {
        console.error('[Bug] 加载评论失败:', e)
      }
    }

    const submitCommentDraft = async () => {
      if (!isEdit || !bugId.value || !richTextHtmlHasContent(commentDraft.value)) return
      commentSubmitting.value = true
      try {
        const resp = await addBugComment(bugId.value, commentDraft.value)
        const res = resp?.data || resp
        if (res?.success && res.comment) {
          entityComments.value = [...entityComments.value, res.comment]
          commentDraft.value = ''
          commentEditorActive.value = false
        } else {
          alert(res?.error || res?.message || '发表评论失败')
        }
      } catch (e) {
        console.error('[Bug] 发表评论失败:', e)
        alert('发表评论失败')
      } finally {
        commentSubmitting.value = false
      }
    }

    // 切换状态下拉框显示
    const toggleStatusDropdown = () => {
      showStatusDropdown.value = !showStatusDropdown.value
    }

    // 选择状态
    const selectStatus = (status) => {
      bug.status = status
      showStatusDropdown.value = false
    }

    // 切换负责人下拉框显示
    const toggleAssigneeDropdown = () => {
      showAssigneeDropdown.value = !showAssigneeDropdown.value
    }

    // 获取负责人显示文本
    const getAssigneeDisplayText = () => {
      if (!bug.assignee || bug.assignee.length === 0) {
        return '未指派'
      }
      
      const ids = Array.isArray(bug.assignee) ? bug.assignee : [bug.assignee]
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

    // 检查负责人是否被选中
    const isAssigneeSelected = (assigneeValue) => {
      return bug.assignee && bug.assignee.includes(assigneeValue)
    }

    // 切换负责人选择状态
    const toggleAssignee = (assigneeValue) => {
      if (!bug.assignee) {
        bug.assignee = []
      }
      
      const index = bug.assignee.indexOf(assigneeValue)
      if (index > -1) {
        bug.assignee.splice(index, 1)
      } else {
        bug.assignee.push(assigneeValue)
      }
    }

    // 切换计划下拉框显示
    const togglePlanDropdown = () => {
      showPlanDropdown.value = !showPlanDropdown.value
    }

    // 选择计划
    const selectPlan = (planValue) => {
      bug.plan = normalizePlanId(planValue) || String(planValue)
      selectedPlanDisplayName.value = findPlanLabelInTree(availablePlans.value, bug.plan) || ''
      showPlanDropdown.value = false
    }

    const isPlanSelected = (planValue) => planIdsMatch(bug.plan, planValue)
    
    // 确认字段修改
    const confirmFieldChange = (field) => {
      console.log('[DIFF] 确认字段修改:', field)
      if (pendingDiff.value?.modifications?.[field]) {
        delete pendingDiff.value.modifications[field]
        
        if (Object.keys(pendingDiff.value.modifications).filter(k => !k.startsWith('_')).length === 0) {
          sessionStorage.removeItem('pendingModifyDiff')
          const event = new CustomEvent('modify-confirmed', {
            detail: { targetId: pendingDiff.value.targetId },
            bubbles: true
          })
          window.dispatchEvent(event)
          
          // 通知列表页面清除 pendingModifications 标记
          const clearEvent = new CustomEvent('clear-pending-modification', {
            detail: { targetId: pendingDiff.value.targetId },
            bubbles: true
          })
          window.dispatchEvent(clearEvent)
          
          pendingDiff.value = null
        }
      }
    }
    
    /** 沙箱/模型可能用 steps_to_reproduce，界面按钮仍传 reproduction_steps，需解析到实际 key */
    const resolvePendingModifyStoreKey = (requested) => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return null
      const tryKeys = [
        requested,
        requested === 'append_comment' ? 'comment' : null,
        requested === 'comment' ? 'append_comment' : null,
        requested === 'reproduction_steps' ? 'steps_to_reproduce' : null,
        requested === 'reproduction_steps' ? 'reproduce_steps' : null,
        requested === 'steps_to_reproduce' ? 'reproduction_steps' : null
      ].filter(Boolean)
      for (const k of tryKeys) {
        if (mods[k]) return k
      }
      return null
    }

    const mapBugModifyApiField = (storeKey) => {
      if (storeKey === 'reproduction_steps' || storeKey === 'reproduce_steps') return 'steps_to_reproduce'
      return storeKey
    }

    const formatBugPriorityLabel = (v) => {
      if (v == null || String(v).trim() === '') return '未设置'
      const s = String(v).trim().toLowerCase()
      const map = {
        p1: 'P1 - 紧急',
        p2: 'P2 - 高',
        p3: 'P3 - 中',
        p4: 'P4 - 低'
      }
      return map[s] || String(v).trim()
    }

    const applyPendingModificationsToBugForm = () => {
      if (!pendingDiff.value?.modifications) return
      for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
        if (String(field).startsWith('_')) continue
        const storeKey = resolvePendingModifyStoreKey(field)
        if (!storeKey || !data || typeof data !== 'object' || !('new' in data)) continue
        if (storeKey === 'append_comment' || storeKey === 'comment') continue
        const nv = data.new
        if (nv === undefined || String(nv).trim() === '') continue
        if (storeKey === 'plan_id') {
          bug.plan = normalizePlanId(nv) || ''
        } else if (storeKey === 'project_id') {
          bug.project_id = String(nv)
          bug.associate_project = true
        } else if (
          storeKey === 'steps_to_reproduce' ||
          storeKey === 'reproduction_steps' ||
          storeKey === 'reproduce_steps'
        ) {
          bug.reproduction_steps = nv
        } else if (bug.hasOwnProperty(storeKey)) {
          bug[storeKey] = nv
        }
      }
    }

    const reloadPendingDiffFromSession = () => {
      if (!props.embedded) return
      if (!props.show_diff) {
        pendingDiff.value = null
        return
      }
      const raw = sessionStorage.getItem('pendingModifyDiff')
      if (!raw) {
        pendingDiff.value = null
        return
      }
      try {
        const pd = JSON.parse(raw)
        const tid = pd?.targetId != null ? String(pd.targetId).trim() : ''
        const cur =
          props.id != null ? String(props.id).trim() : bugId.value ? String(bugId.value).trim() : ''
        const tgt = String(pd?.target || 'bug').toLowerCase().replace(/-/g, '_')
        const isBug = tgt === 'bug' || tgt === ''
        if (!isBug || (cur && tid && tid !== cur)) return
        pendingDiff.value = pd
        applyPendingModificationsToBugForm()
      } catch (e) {
        console.error('[DIFF] reloadPendingDiffFromSession 失败:', e)
      }
    }

    watch(
      () => [props.show_diff, props.id],
      () => {
        reloadPendingDiffFromSession()
      },
      { flush: 'post' }
    )

    onActivated(() => {
      reloadPendingDiffFromSession()
    })

    // 取消字段修改
    const cancelFieldChange = (field) => {
      const storeKey = resolvePendingModifyStoreKey(field)
      if (!storeKey || !pendingDiff.value?.modifications?.[storeKey]) return
      const oldValue = pendingDiff.value.modifications[storeKey].old
      const target = pendingDiff.value?.target || 'bug'
      if (storeKey === 'append_comment' || storeKey === 'comment') {
        // 评论只追加，取消 diff 即可
      } else if (storeKey === 'plan_id') {
        bug.plan = normalizePlanId(oldValue) || ''
      } else if (storeKey === 'project_id') {
        bug.project_id = oldValue ? String(oldValue) : ''
        bug.associate_project = !!bug.project_id
      } else if (target === 'bug' && (storeKey === 'steps_to_reproduce' || storeKey === 'reproduction_steps' || storeKey === 'reproduce_steps')) {
        bug.reproduction_steps = oldValue || ''
      } else if (bug.hasOwnProperty(storeKey)) {
        bug[storeKey] = oldValue || ''
      }
      delete pendingDiff.value.modifications[storeKey]
      if (Object.keys(pendingDiff.value.modifications).filter((k) => !k.startsWith('_')).length === 0) {
        sessionStorage.removeItem('pendingModifyDiff')
        pendingDiff.value = null
      }
    }

    const scrollToDiffField = async (field) => {
      await nextTick()
      const el = document.getElementById(`diff-field-${field}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    const applyFieldChange = async (requestedField) => {
      const storeKey = resolvePendingModifyStoreKey(requestedField)
      if (!storeKey || !pendingDiff.value?.modifications?.[storeKey]) return

      const projectId = bug.project_id || props.project_id
      const targetId = pendingDiff.value?.targetId || props.id
      const target = pendingDiff.value?.target || 'bug'
      const newValue = pendingDiff.value.modifications[storeKey]?.new
      const apiField = target === 'bug' ? mapBugModifyApiField(storeKey) : storeKey

      if (!projectId || !targetId) {
        console.warn('[DIFF] projectId/targetId 缺失，无法采纳', { projectId, targetId })
        return
      }

      try {
        const resp = await fetch(`${BACKEND_BASE_URL}/api/projects/${projectId}/modify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            target,
            target_id: targetId,
            modifications: { [apiField]: newValue },
            confirm: true,
            message_id: pendingDiff.value?.messageId
          })
        })
        const result = await resp.json()
        if (!result.success) {
          console.error('[DIFF] 采纳失败:', result.error)
          return
        }

        if (storeKey === 'append_comment' || apiField === 'append_comment') {
          await loadEntityComments()
          commentDraft.value = ''
        } else if (apiField === 'plan_id') {
          bug.plan = normalizePlanId(newValue) || ''
        } else if (apiField === 'project_id') {
          bug.project_id = String(newValue)
          bug.associate_project = true
        } else if (target === 'bug' && apiField === 'steps_to_reproduce') {
          bug.reproduction_steps = newValue
        } else if (Object.prototype.hasOwnProperty.call(bug, apiField)) {
          bug[apiField] = newValue
        }

        confirmFieldChange(storeKey)
      } catch (e) {
        console.error('[DIFF] 采纳字段异常:', e)
      }
    }

    // 返回上一页
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
      
      // 如果有项目ID和计划ID，返回到项目详情页并展开对应计划
      if (bug.project_id) {
        const targetUrl = `/project-detail/${bug.project_id}`
        // 如果有计划ID，添加到URL参数中，让ProjectDetail自动展开
        if (!isEmptyPlanKey(bug.plan)) {
          router.push(`${targetUrl}?expand_plan=${bug.plan}`)
        } else {
          router.push(targetUrl)
        }
      } else {
        // 如果没有项目ID，使用浏览器后退
        router.go(-1)
      }
    }
    
    onMounted(async () => {
      console.log('=== 组件挂载开始 ===')
      
      try {
        const query = route.query
        const showDiffMode = props.show_diff || query.show_diff === 'true'
        // 与 NewBadcase 一致：普通编辑不得读 session 里的待采纳 diff，否则会误把（如卡片）title 覆盖到刚拉取的 Bug 上
        if (showDiffMode) {
          const diffDataStrEarly = sessionStorage.getItem('pendingModifyDiff')
          if (diffDataStrEarly) {
            try {
              pendingDiff.value = JSON.parse(diffDataStrEarly)
              console.log('[DIFF] 预读取到 diff 数据:', pendingDiff.value)
            } catch (e) {
              console.error('[DIFF] 预读取 diff 失败:', e)
            }
          }
        } else {
          sessionStorage.removeItem('pendingModifyDiff')
          pendingDiff.value = null
        }

        // 后台并行加载用户信息（不阻塞首屏）
        console.log('开始加载用户信息...')
        await fetchCurrentUser()
        
        // 先拉项目列表再 initBug，避免竞态下 initBug 误以为列表为空再次请求 /api/projects
        await fetchProjects()
        await initBug()
        console.log('Bug初始化完成')

        const ctxProjectId = bug.project_id
        if (ctxProjectId && !projectWorkspaceLoaded.value) {
          try {
            await applyProjectEditContext(ctxProjectId)
          } catch (e) {
            console.error('获取编辑页上下文失败:', e)
          }
        } else if (ctxProjectId && !projectInfo.value?.name) {
          const prj = availableProjects.value.find((p) => String(p.id) === String(ctxProjectId))
          if (prj) projectInfo.value = prj
        }

        const clearPendingModifyIfNotThisBug = () => {
          if (!showDiffMode || !pendingDiff.value?.modifications) return
          const pd = pendingDiff.value
          const tid = pd.targetId != null ? String(pd.targetId).trim() : ''
          const cur = bugId.value ? String(bugId.value).trim() : ''
          const tgt = String(pd.target || 'bug').toLowerCase().replace(/-/g, '_')
          const isBug = tgt === 'bug' || tgt === ''
          if (!isBug || (isEdit.value && cur && tid && tid !== cur)) {
            sessionStorage.removeItem('pendingModifyDiff')
            pendingDiff.value = null
          }
        }
        clearPendingModifyIfNotThisBug()

        // 过滤已采纳的字段（DB 值已等于 diff 的 new 值），避免重复显示
        if (pendingDiff.value?.modifications) {
          const mods = pendingDiff.value.modifications
          for (const [field, data] of Object.entries(mods)) {
            if (String(field).startsWith('_')) continue
            const newVal = data?.new != null ? String(data.new).trim() : ''
            const curVal = bug[field] != null ? String(bug[field]).trim() : ''
            if (newVal && curVal === newVal) delete mods[field]
          }
          if (Object.keys(mods).filter(k => !String(k).startsWith('_')).length === 0) {
            sessionStorage.removeItem('pendingModifyDiff')
            pendingDiff.value = null
          }
        }
        // 待确认 diff 的「旧值」若与当前库表不一致（常见：会话里错成默认 new/空），以 initBug 拉取后的表单为准
        const reconcilePendingOldFromLoadedBug = () => {
          if (!pendingDiff.value?.modifications) return
          for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
            if (String(field).startsWith('_')) continue
            if (!bug.hasOwnProperty(field) || !data || typeof data !== 'object' || !('new' in data)) continue
            if (field !== 'status' && field !== 'title') continue
            const bv = bug[field]
            const bs = bv != null ? String(bv).trim() : ''
            if (!bs) continue
            const oldS = data.old != null ? String(data.old).trim() : ''
            const newS = data.new != null ? String(data.new).trim() : ''
            if (!newS || newS === bs) continue
            if (oldS !== bs) {
              data.old = bv
            }
          }
        }
        reconcilePendingOldFromLoadedBug()
        if (pendingDiff.value?.modifications) {
          for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
            if (bug.hasOwnProperty(field) && data && typeof data === 'object' && 'new' in data && data.new !== undefined) {
              bug[field] = data.new
            }
          }
        }
        
        await nextTick()
        
        // 添加全局点击事件监听器，点击外部关闭下拉框
        document.addEventListener('click', (event) => {
          const statusDropdown = document.querySelector('.status-dropdown')
          const assigneeDropdown = document.querySelector('.assignee-dropdown')
          const planDropdown = document.querySelector('.plan-dropdown')
          
          if (statusDropdown && !statusDropdown.contains(event.target)) {
            showStatusDropdown.value = false
          }
          
          if (assigneeDropdown && !assigneeDropdown.contains(event.target)) {
            showAssigneeDropdown.value = false
          }
          
          if (planDropdown && !planDropdown.contains(event.target)) {
            showPlanDropdown.value = false
          }
        })
        
        console.log('=== 组件挂载完成 ===')
      } catch (error) {
        console.error('组件挂载过程中发生错误:', error)
      }
    })
    
    return {
      loading,
      saveLoading,
      isEdit,
      bug,
      projectInfo,
      availableProjects,
      projectMembers,
      showStatusDropdown,
      showAssigneeDropdown,
      showPlanDropdown,
      assigneeSearchText,
      planSearchText,
      availableStatuses,
      currentUser,
      recentAssignees,
      availablePlans,
      filteredPlans,
      expandedPlans,
      getStatusText,
      saveBug,
      toggleStatusDropdown,
      selectStatus,
      handleProjectChange,
      toggleAssigneeDropdown,
      getAssigneeDisplayText,
      personPrimaryLabel,
      personSecondaryLabel,
      isAssigneeSelected,
      toggleAssignee,
      togglePlanDropdown,
      selectPlan,
      isPlanSelected,
      searchPlans,
      clearPlanSearch,
      getSelectedPlanDisplayText,
      refreshProjectPlans,
      togglePlanExpansion,
      goBack,
      pendingDiff,
      showPendingDiffTopPanel,
      shouldShowPendingFieldInTop,
      pendingDiffFieldLabel,
      isShortListPendingField,
      formatPendingShortFieldDisplay,
      confirmFieldChange,
      cancelFieldChange,
      applyFieldChange,
      formatBugPriorityLabel,
      copyDocumentLink,
      addAttachment,
      handleFileUpload,
      removeAttachment,
      fileInput,
      stepsLength,
      entityComments,
      commentDraft,
      commentDraftText,
      commentDraftLength,
      commentSubmitting,
      entityFieldDiff,
      hasEntityFieldDiff,
      formatEntityDiffValue,
      formatCommentTime,
      loadEntityComments,
      submitCommentDraft,
      commentEditorActive,
      activateCommentEditor,
      finishCommentEditor,
      isRightSidebarOpen,
      toggleRightSidebar
    }
  }
}
</script>

<style scoped>
/* 伸缩按钮样式 */
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

/* 指向内「展开侧栏」的图标方向（与收起态手柄区分） */
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

/* 左侧主内容 */
.content-left {
  flex: 1;
  min-width: 300px;
  transition: all 0.3s ease;
}

/* 主内容区布局 */
.main-content {
  position: relative;
  display: flex;
  gap: 16px;
  padding: 20px;
  min-height: 600px;
}

/* 确保在嵌入模式下也能正常显示；勿沿用 min-height:600px，否则复现区与底部按钮间易被撑出大块空白 */
.bug-detail-wrapper.is-embedded .main-content {
  padding: 16px;
  min-height: 0;
}
</style>

<style scoped>
.bug-detail-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f9fa;
}

/* 嵌入在 ProjectDetail：占满父容器，避免底部按钮被裁切 */
.bug-detail-wrapper.is-embedded {
  flex: 1;
  min-height: 0;
  height: auto;
}

/* 加载指示器 */
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

/* 待采纳改动：浅色卡片，与主表单一致 */
.pending-diff-panel {
  margin: 16px 0 20px;
  padding: 16px 16px 12px;
  background: #fafafa;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

.pending-diff-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.pending-diff-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.pending-diff-subtitle {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.45;
}

.pending-diff-panel--embedded {
  margin-top: 0;
  margin-bottom: 12px;
}

.pending-diff-priority-inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 0 2px;
  font-size: 13px;
  color: #374151;
}

.pending-diff-priority-inline .diff-val {
  font-weight: 600;
  color: #111827;
}

.pending-diff-priority-inline .diff-arrow {
  color: #9ca3af;
}

.pending-diff-priority-inline .diff-old-tag,
.pending-diff-priority-inline .diff-new-tag {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
}

.pending-diff-item {
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  margin-top: 10px;
}

.pending-diff-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.pending-diff-field-label {
  font-weight: 600;
  color: #1d4ed8;
}

.pending-diff-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.pending-diff-inline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
  font-size: 13px;
}

.pending-diff-inline-row .pdi-arrow {
  color: #9ca3af;
  font-weight: 500;
}

.pending-diff-inline-row .pdi-chip {
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 8px;
  line-height: 1.35;
  word-break: break-word;
}

.pending-diff-inline-row .pdi-chip.pdi-old {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.pending-diff-inline-row .pdi-chip.pdi-new {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.pending-diff-panel .btn-icon-approve,
.pending-diff-panel .btn-icon-reject {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  font-size: 16px;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.pending-diff-panel .btn-icon-approve {
  background: #059669;
  color: #fff;
}

.pending-diff-panel .btn-icon-reject {
  background: #dc2626;
  color: #fff;
}

.pending-diff-panel .btn-icon-approve:hover,
.pending-diff-panel .btn-icon-reject:hover {
  transform: scale(1.06);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

.loading-text {
  color: #666;
  font-size: 16px;
  font-weight: 500;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 顶部标题栏 */
.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e9ecef;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-arrow {
  font-size: 20px;
  cursor: pointer;
  color: #666;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.back-arrow:hover {
  background-color: #f0f0f0;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.project-name {
  font-size: 16px;
  color: #666;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  background: #fff;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.header-btn:hover {
  background: #f8f9fa;
  border-color: #dee2e6;
}

.checkbox-icon {
  width: 16px;
  height: 16px;
  border: 1px solid #ddd;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: transparent;
}

.checkbox-icon.checked {
  background: #667eea;
  border-color: #667eea;
  color: #fff;
}

.gear-icon, .close-icon {
  font-size: 16px;
}

.close-btn:hover {
  background: #f56565;
  color: #fff;
  border-color: #f56565;
}

/* 主内容区 */
.main-content {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 左侧内容区 */
.content-left {
  flex: 1;
  min-height: 0;
  padding: 24px;
  overflow-y: auto;
  background: #fff;
  margin: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* 标题区域 */
.title-section {
  margin-bottom: 24px;
  position: relative;
}

.title-input {
  width: 100%;
  font-size: 24px;
  font-weight: 600;
  border: none;
  outline: none;
  padding: 8px 0;
  border-bottom: 2px solid #e9ecef;
  transition: border-color 0.2s;
}

.title-input:focus {
  border-bottom-color: #667eea;
}

.title-count {
  position: absolute;
  right: 0;
  top: 8px;
  font-size: 12px;
  color: #999;
}

/* 状态区域 */
.status-section {
  display: flex;
  gap: 24px;
  margin-bottom: 32px;
  flex-wrap: wrap;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-label {
  font-size: 14px;
  color: #666;
  font-weight: 500;
}

.status-pill, .assignee-pill, .plan-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 20px;
  font-size: 14px;
  color: #666;
}

.status-pill {
  background: #e9ecef;
  color: #495057;
}

.assignee-pill {
  background: #e3f2fd;
  color: #1976d2;
}

.plan-pill {
  background: #f3e5f5;
  color: #7b1fa2;
}

.arrow-icon {
  font-size: 12px;
  color: #999;
  transition: transform 0.2s;
}

.arrow-icon.rotated {
  transform: rotate(180deg);
}

.person-icon, .folder-icon {
  font-size: 14px;
}

/* 状态下拉框样式 */
.status-dropdown {
  position: relative;
  cursor: pointer;
}

.status-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
  margin-top: 4px;
  min-width: 120px;
}

.status-option {
  padding: 8px 12px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: background-color 0.2s;
}

.status-option:hover {
  background: #f8f9fa;
}

.status-option.selected {
  background: #667eea;
  color: #fff;
}

.status-option:first-child {
  border-radius: 6px 6px 0 0;
}

.status-option:last-child {
  border-radius: 0 0 6px 6px;
}

/* 负责人下拉框样式 */
.assignee-dropdown {
  position: relative;
  cursor: pointer;
}

.assignee-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
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

/* 搜索框样式 */
.assignee-search {
  position: relative;
  padding: 12px;
  border-bottom: 1px solid #e9ecef;
}

.search-input {
  width: 100%;
  padding: 8px 32px 8px 12px;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  font-size: 14px;
  outline: none;
}

.search-input:focus {
  border-color: #667eea;
}

.search-icon {
  position: absolute;
  right: 20px;
  top: 50%;
  transform: translateY(-50%);
  color: #999;
  font-size: 14px;
}

/* 分组标题 */
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

/* 负责人选项样式 */
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

/* 复选框样式 */
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
  background: #667eea;
  border-color: #667eea;
}

.checkmark {
  color: white;
  font-size: 10px;
  font-weight: bold;
}

/* 头像样式 */
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

/* 用户信息样式 */
.assignee-info {
  flex: 1;
  min-width: 0;
}

.assignee-name {
  font-weight: 500;
  margin-bottom: 2px;
}

.assignee-id {
  font-size: 12px;
  color: #666;
  margin-bottom: 2px;
}

.assignee-dept {
  font-size: 12px;
  color: #999;
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
  right: 0;
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

/* 计划搜索框样式 */
.plan-search {
  position: relative;
  padding: 12px;
  border-bottom: 1px solid #e9ecef;
  display: flex;
  align-items: center;
  gap: 20px;
  background: #f8f9fa;
}

.plan-search .search-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.plan-search .search-input:focus {
  border-color: #1976d2;
}

.search-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.search-btn:hover {
  background: #f0f0f0;
}

.clear-search-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
  color: #666;
}

.clear-search-btn:hover {
  background: #f0f0f0;
  color: #333;
}

.clear-icon {
  font-size: 12px;
}

/* 计划列表样式 */
.plan-list {
  max-height: 300px;
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

.plan-option.unplanned {
  background: #f8f9fa;
  border-left: 3px solid #28a745;
  font-weight: 500;
}

.plan-option.unplanned:hover {
  background: #e9ecec;
}

/* 子计划列表样式 */
.sub-plan-list {
  margin-left: 20px;
  border-left: 2px solid #e9ecef;
  padding-left: 12px;
}

.sub-plan-list.level-2 {
  margin-left: 40px;
  border-left: 2px solid #f0f0f0;
}

.plan-option.sub-plan {
  background: #fafbfc;
}

.plan-option.sub-plan:hover {
  background: #f0f0f0;
}

.plan-option.sub-plan.level-2 {
  background: #f8f9fa;
}

.plan-option.sub-plan.level-2:hover {
  background: #e9ecec;
}



.plan-option:hover {
  background: #f8f9fa;
}

.plan-option.selected {
  background: #e3f2fd;
  color: #1976d2;
}

.plan-option.expandable {
  font-weight: 500;
  background: #f8f9fa;
}

.plan-option.expandable:hover {
  background: #e9ecec;
}

.expand-arrow {
  font-size: 10px;
  color: #333;
  width: 12px;
  text-align: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 12px;
}

.plan-icon {
  font-size: 16px;
  color: #667eea;
  width: 20px;
  text-align: center;
}

.plan-name {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
}

.plan-info {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.count-badge {
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  color: #fff;
}

.count-badge.bug {
  background: #ff6b6b;
}

.count-badge.bug {
  background: #4ecdc4;
}

.plan-option.pinned {
  background: #fff3cd;
  border-left: 3px solid #ffc107;
}

.plan-option.pinned:hover {
  background: #ffeaa7;
}

.plan-option.pinned.selected {
  background: #e3f2fd;
  border-left: 3px solid #1976d2;
}

.pin-indicator {
  font-size: 10px;
  color: #ff6b6b;
  opacity: 0.8;
}

/* 层级缩进 */
.plan-option[data-level="1"] .plan-indent {
  margin-left: 20px;
}

.plan-option[data-level="2"] .plan-indent {
  margin-left: 40px;
}

.plan-option[data-level="3"] .plan-indent {
  margin-left: 60px;
}

/* 编辑器区域 */
.editor-section {
  margin-bottom: 32px;
  border: 1px solid #e9ecef;
  border-radius: 8px;
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

.toolbar-btn {
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

.toolbar-btn:hover {
  background: #f8f9fa;
  border-color: #667eea;
}

.toolbar-btn:active {
  background: #e9ecef;
}

.toolbar-btn:hover {
  background: #e9ecef;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #e9ecef;
  margin: 0 4px;
}

.editor-content {
  padding: 16px;
}

.editor-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.editor-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 0;
}

.editor-textarea {
  width: 100%;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
}

.editor-textarea:deep(.rich-text-html-editor) {
  width: 100%;
}

.editor-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

/* 问题描述区域 */
.problem-section {
  margin-bottom: 32px;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  overflow: hidden;
}

.problem-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.problem-textarea {
  width: 100%;
  min-height: 80px;
  max-height: 120px;
  padding: 12px;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 1.5;
  resize: vertical;
  font-family: inherit;
}

.problem-textarea:focus {
  background: #fafbfc;
}

.problem-textarea::placeholder {
  color: #999;
  font-style: italic;
}

.problem-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
  padding: 0 16px 16px;
}

/* 期望结果区域 */
.answer-section {
  margin-bottom: 32px;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  overflow: hidden;
}

.answer-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.answer-textarea {
  width: 100%;
  min-height: 120px;
  border: none;
  outline: none;
  resize: vertical;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  padding: 16px;
  background: #fff;
}

.answer-textarea::placeholder {
  color: #999;
}

.answer-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
  padding: 0 16px 16px;
}

/* 正确期望结果区域 */
.correct-answer-section {
  margin-bottom: 32px;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  overflow: hidden;
}

.correct-answer-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.correct-answer-textarea {
  width: 100%;
  min-height: 120px;
  border: none;
  outline: none;
  resize: vertical;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  padding: 16px;
  background: #fff;
}

.correct-answer-textarea::placeholder {
  color: #999;
}

.correct-answer-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
  padding: 0 16px 16px;
}

/* 分类区域 */
.category-section {
  margin-bottom: 32px;
}

.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
}

.form-row--stack-field {
  align-items: flex-start;
}

.form-row-field-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.form-row-field-col .form-select {
  max-width: 100%;
}

.field-diff-panel--stacked {
  width: 100%;
  max-width: 520px;
}

.form-label {
  width: 100px;
  color: #333;
  font-size: 14px;
  font-weight: 500;
}

.form-label.required::before {
  content: '*';
  color: #f56565;
  margin-right: 4px;
}

.form-select {
  flex: 1;
  max-width: 300px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  background: #fff;
}

/* 底部区域 */
.footer-section {
  position: sticky;
  bottom: 0;
  z-index: 5;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  margin: 0 -24px -24px;
  border-top: 1px solid #e9ecef;
  background: #fff;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
}

.footer-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 14px;
}

.tip-icon {
  font-size: 16px;
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

.cancel-btn {
  background: #f8f9fa;
  color: #666;
  border: 1px solid #e9ecef;
}

.cancel-btn:hover {
  background: #e9ecef;
}

.save-btn {
  background: #667eea;
  color: #fff;
}

.save-btn:hover:not(:disabled) {
  background: #5a6fd8;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 右侧边栏：默认收起；展开后固定宽度，不使用 flex:1 继续拉宽 */
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

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.select-label {
  display: block;
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.team-management-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #17a2b8;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.team-management-btn:hover {
  background: #138496;
}

.team-icon {
  font-size: 14px;
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
}

.team-management-modal {
  max-width: 1000px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
}



.comment-section {
  margin-top: 16px;
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

.comment-label {
  display: block;
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.comment-textarea {
  width: 100%;
  min-height: 120px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 12px;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

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

.editor-count {
  text-align: right;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
  padding: 0 12px 12px;
}

/* 关联文档样式 */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 6px 6px 0 0;
  border-bottom: 1px solid #e9ecef;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 16px;
  color: #667eea;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

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

.document-fields {
  padding: 16px;
}

.field-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.field-label {
  font-size: 14px;
  color: #666;
}

.field-value {
  font-size: 14px;
  color: #999;
}

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

/* 附件样式 */
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

.attachment-list {
  padding: 16px;
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

.no-attachments {
  text-align: center;
  color: #999;
  font-size: 14px;
  padding: 20px;
}

/* 富文本编辑器样式 */
.rich-editor {
  border: 1px solid #667eea;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  flex-wrap: wrap;
}

.editor-toolbar .toolbar-btn {
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

.editor-toolbar .toolbar-btn:hover {
  background: #e9ecef;
  border-color: #667eea;
}

.editor-toolbar .toolbar-divider {
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

@media (max-width: 768px) {
  .header-bar {
    padding: 12px 16px;
  }
  
  .content-left {
    margin: 8px;
    padding: 16px;
  }
  
  .sidebar-right.sidebar-right--open {
    padding: 16px;
  }
  
  .title-input {
    font-size: 20px;
  }
}

/* 开发者工具打开时的布局优化 */
@media (max-width: 1200px) and (min-width: 769px) {
  .sidebar-right.sidebar-right--open {
    width: 280px;
    min-width: 280px;
    max-width: 280px;
  }
  
  .content-left {
    padding: 20px;
  }
}

/* 强制保持左右布局的最小宽度 */
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

/* 无项目成员提示样式 */
.no-members-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  color: #666;
  font-size: 13px;
  background: #f8f9fa;
  border-radius: 6px;
  margin: 8px 0;
}

.tip-icon {
  font-size: 14px;
}

.tip-text {
  flex: 1;
}

/* 无用户信息提示样式 */
.no-user-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  color: #ff6b6b;
  font-size: 13px;
  background: #fff5f5;
  border-radius: 6px;
  margin: 8px 0;
  border: 1px solid #fed7d7;
}

/* 无最近选择用户提示样式 */
.no-recent-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  color: #666;
  font-size: 13px;
  background: #f8f9fa;
  border-radius: 6px;
  margin: 8px 0;
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

.btn-confirm,
.btn-cancel {
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

.btn-confirm {
  background: #10b981;
  color: white;
}

.btn-confirm:hover {
  background: #059669;
  transform: scale(1.1);
}

.btn-cancel {
  background: #ef4444;
  color: white;
}

.btn-cancel:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.diff-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.diff-old,
.diff-new {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  display: inline-block;
  width: fit-content;
}

.diff-tag.old {
  background: #fecaca;
  color: #991b1b;
}

.diff-tag.new {
  background: #bbf7d0;
  color: #166534;
}

.diff-value {
  font-size: 14px;
  color: #333;
  word-break: break-all;
}

.diff-arrow {
  font-size: 18px;
  color: #9ca3af;
}

.field-with-diff {
  border-color: #f59e0b !important;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2) !important;
}
</style> 