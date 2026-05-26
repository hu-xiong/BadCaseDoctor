<template>
  <div class="badcase-detail-wrapper" :class="{ 'is-embedded': embedded }">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载项目信息...</div>
    </div>
    
    <!-- 顶部导航栏：嵌入模式隐藏第一栏（布局/人头），保留第二栏（返回/操作） -->
    <div class="top-bar top-bar--stacked">
      <!-- 第一栏：仅在非嵌入模式显示 -->
      <div v-if="!embedded" class="top-bar-row top-bar-row--primary">
        <div class="top-left">
          <div class="logo">
            <span class="logo-text">BadCase Doctor</span>
            <span class="star-icon">⭐</span>
          </div>

          <div class="breadcrumb">
            <span
              class="breadcrumb-item breadcrumb-link"
              @click="goBackToProjectDetail"
              :title="projectInfo?.name || '返回项目详情'"
            >
              {{ projectInfo?.name || '项目' }}
            </span>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item">{{ editContextCrumb }}</span>
            <span class="dropdown-arrow">▼</span>
          </div>

          <span class="edit-permission">编辑权限</span>
        </div>

        <div class="top-right">
          <div class="layout-buttons">
            <button class="layout-btn" :class="{ active: !leftSidebarHidden }" @click="setLayout('left')" title="切换侧边栏">
              <div class="layout-icon left-aligned"></div>
            </button>
            <button class="layout-btn" :class="{ active: showTerminal }" @click="setLayout('bottom')" title="切换终端">
              <div class="layout-icon bottom-aligned"></div>
            </button>
            <button class="layout-btn" :class="{ active: showAIAssistant }" @click="setLayout('right')" title="切换AI助手">
              <div class="layout-icon right-aligned"></div>
            </button>
          </div>

          <div class="user-dropdown" @click="toggleUserDropdown">
            <div class="user-avatar">👤</div>

            <div v-if="showUserDropdown" class="user-menu" @click.stop>
              <div class="user-info">
                <div class="user-name">{{ currentUser?.name || '用户' }}</div>
                <div class="user-email">{{ currentUser?.email || 'user@example.com' }}</div>
              </div>
              <div class="menu-divider"></div>
              <div class="menu-item" @click="showNotifications">
                <span class="menu-icon">🔔</span>
                <span class="menu-text">通知</span>
              </div>
              <div class="menu-item" @click="showHelp">
                <span class="menu-icon">❓</span>
                <span class="menu-text">帮助</span>
              </div>
              <div class="menu-item" @click="showTeamManagement">
                <span class="menu-icon">👥</span>
                <span class="menu-text">团队管理</span>
              </div>
              <div class="menu-item" @click="showUserProfile">
                <span class="menu-icon">👤</span>
                <span class="menu-text">个人资料</span>
              </div>
              <div class="menu-divider"></div>
              <div class="menu-item logout-item" @click="logout">
                <span class="menu-icon">🚪</span>
                <span class="menu-text">退出登录</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 第二栏：页面级标题与操作 -->
      <div class="top-bar-row top-bar-row--secondary">
        <div class="secondary-left">
          <span v-if="!embedded || isEdit" class="back-arrow" @click="goBack">←</span>
          <span class="page-title">{{ pageHeadline }}</span>
        </div>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧主要内容区 -->
      <div class="content-left">
        <!-- 标题区域 -->
        <div class="title-section">
          <input 
            v-model="badcase.title" 
            class="title-input" 
            placeholder="请输入BadCase标题"
            maxlength="100"
          />
          <div class="title-count">{{ badcase.title.length }} / 100</div>
        </div>

        <!-- 状态和负责人信息 -->
        <div class="status-section">
          <div class="status-item">
            <span class="status-label">流程状态:</span>
            <div class="status-dropdown" @click="toggleStatusDropdown">
              <div class="status-pill">
                <span class="status-text">{{ getStatusText(badcase.status) }}</span>
                <span class="arrow-icon" :class="{ 'rotated': showStatusDropdown }">▼</span>
              </div>
              <div v-if="showStatusDropdown" class="status-dropdown-menu">
                <div 
                  v-for="status in availableStatuses" 
                  :key="status.value"
                  class="status-option"
                  :class="{ 'selected': badcase.status === status.value }"
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
                <div v-else-if="badcase.project_id && projectMembers.length === 0" class="assignee-section">
                  <div class="section-title">项目成员 (0人)</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">ℹ️</span>
                    <span class="tip-text">该项目暂无成员，请先添加项目成员</span>
                  </div>
                </div>
                
                <!-- 未选择项目时的提示 -->
                <div v-else-if="!badcase.project_id" class="assignee-section">
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
                      
                      <!-- 计划信息（BadCase和Bug数量） -->
                      <span class="plan-info" v-if="plan.badcase_count > 0 || plan.bug_count > 0">
                        <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                        <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
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
                        <span class="plan-info" v-if="childPlan.badcase_count > 0 || childPlan.bug_count > 0">
                          <span v-if="childPlan.badcase_count > 0" class="count-badge badcase">{{ childPlan.badcase_count }}</span>
                          <span v-if="childPlan.bug_count > 0" class="count-badge bug">{{ grandChildPlan.bug_count }}</span>
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
                            <span class="plan-info" v-if="grandChildPlan.badcase_count > 0 || grandChildPlan.bug_count > 0">
                              <span v-if="grandChildPlan.badcase_count > 0" class="count-badge badcase">{{ grandChildPlan.badcase_count }}</span>
                              <span v-if="grandChildPlan.bug_count > 0" class="count-badge bug">{{ grandChildPlan.bug_count }}</span>
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
        
        <!-- 相似问题（选填） -->
        <div class="problem-section" :class="{ 'has-diff': pendingDiff?.modifications?.base_problem }">
          <div v-if="pendingDiff?.modifications?.base_problem" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('base_problem')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('base_problem')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-old">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ pendingDiff.modifications.base_problem.old || '未设置' }}</span>
              </div>
              <div class="diff-arrow">→</div>
              <div class="diff-new">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ pendingDiff.modifications.base_problem.new }}</span>
              </div>
            </div>
          </div>
          <h3 class="problem-title">相似问题（选填）:</h3>
          <textarea 
            v-model="badcase.base_problem" 
            class="problem-textarea" 
            :class="{ 'field-with-diff': pendingDiff?.modifications?.base_problem }"
            placeholder="若无相似问题可留空；有则简要描述…"
            maxlength="500"
          ></textarea>
          <div class="problem-count">{{ (badcase.base_problem || '').length }} / 500</div>
        </div>
                
        <!-- 复现步骤编辑器（Tiptap） -->
        <div class="editor-section" :class="{ 'has-diff': pendingDiff?.modifications?.reproduction_steps }">
            <div v-if="pendingDiff?.modifications?.reproduction_steps" class="field-diff-panel">
              <div class="diff-header">
                <span class="diff-label">修改预览:</span>
                <div class="diff-actions">
                  <button @click="applyFieldChange('reproduction_steps')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                  <button @click="cancelFieldChange('reproduction_steps')" class="btn-cancel" title="取消">✗</button>
                </div>
              </div>
              <div class="diff-content">
                <div class="diff-old">
                  <span class="diff-tag old">原值</span>
                  <span class="diff-value">{{ pendingDiff.modifications.reproduction_steps.old || '未设置' }}</span>
                </div>
                <div class="diff-arrow">→</div>
                <div class="diff-new">
                  <span class="diff-tag new">新值</span>
                  <span class="diff-value">{{ pendingDiff.modifications.reproduction_steps.new }}</span>
                </div>
              </div>
            </div>
          <div class="editor-content">
            <div class="editor-title-row">
              <h3 class="editor-title">BadCase复现步骤:</h3>
              <button type="button" class="toolbar-btn" title="添加附件到侧栏" @click="addAttachment">📎</button>
            </div>
            <RichTextHtmlEditor
              v-model="badcase.reproduction_steps"
              class="editor-textarea"
              :class="{ 'field-with-diff': pendingDiff?.modifications?.reproduction_steps }"
              placeholder="请详细描述BadCase的复现步骤..."
            />
            <div class="editor-count">{{ stepsLength }} / 2000</div>
          </div>
        </div>
        
        <!-- 答案输入框 -->
        <div class="answer-section" :class="{ 'has-diff': pendingDiff?.modifications?.answer }">
          <div v-if="pendingDiff?.modifications?.answer" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('answer')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('answer')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-old">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ pendingDiff.modifications.answer.old || '未设置' }}</span>
              </div>
              <div class="diff-arrow">→</div>
              <div class="diff-new">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ pendingDiff.modifications.answer.new }}</span>
              </div>
            </div>
          </div>
          <h3 class="answer-title">答案:</h3>
          <textarea 
            v-model="badcase.answer" 
            class="answer-textarea" 
            :class="{ 'field-with-diff': pendingDiff?.modifications?.answer }"
            placeholder="请输入答案..."
            maxlength="1000"
          ></textarea>
          <div class="answer-count">{{ badcase.answer.length }} / 1000</div>
        </div>
        
        <!-- 正确答案输入框 -->
        <div class="correct-answer-section" :class="{ 'has-diff': pendingDiff?.modifications?.correct_answer }">
          <div v-if="pendingDiff?.modifications?.correct_answer" class="field-diff-panel">
            <div class="diff-header">
              <span class="diff-label">正确答案修改预览:</span>
              <div class="diff-actions">
                <button @click="applyFieldChange('correct_answer')" class="btn-confirm" title="采纳（立即落库）">✓</button>
                <button @click="cancelFieldChange('correct_answer')" class="btn-cancel" title="取消">✗</button>
              </div>
            </div>
            <div class="diff-content">
              <div class="diff-old">
                <span class="diff-tag old">原值</span>
                <span class="diff-value">{{ pendingDiff.modifications.correct_answer.old || '未设置' }}</span>
              </div>
              <div class="diff-arrow">→</div>
              <div class="diff-new">
                <span class="diff-tag new">新值</span>
                <span class="diff-value">{{ pendingDiff.modifications.correct_answer.new }}</span>
              </div>
            </div>
          </div>
          <h3 class="correct-answer-title">正确答案:</h3>
          <textarea 
            v-model="badcase.correct_answer" 
            class="correct-answer-textarea" 
            :class="{ 'field-with-diff': pendingDiff?.modifications?.correct_answer }"
            placeholder="请输入正确答案..."
            maxlength="1000"
          ></textarea>
          <div class="correct-answer-count">{{ badcase.correct_answer.length }} / 1000</div>
        </div>
                
        <!-- 问题分类和优先级 -->
        <div class="category-section">
          <div class="form-row" :class="{ 'has-diff': pendingDiff?.modifications?.case_category }">
            <label class="form-label required">问题分类:</label>
            <div v-if="pendingDiff?.modifications?.case_category" class="field-diff-panel-inline">
              <div class="diff-content">
                <span class="diff-old">{{ pendingDiff.modifications.case_category.old || '未设置' }}</span>
                <span class="diff-arrow">→</span>
                <span class="diff-new">{{ pendingDiff.modifications.case_category.new }}</span>
                <div class="diff-actions">
                  <button type="button" @click="applyFieldChange('case_category')" class="btn-confirm-sm" title="采纳（立即落库）">✓</button>
                  <button type="button" @click="cancelFieldChange('case_category')" class="btn-cancel-sm" title="取消">✗</button>
                </div>
              </div>
            </div>
            <select
              v-model="badcase.case_category"
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
          <div class="form-row" :class="{ 'has-diff': pendingDiff?.modifications?.priority }">
            <label class="form-label required">优先级:</label>
            <div v-if="pendingDiff?.modifications?.priority" class="field-diff-panel-inline">
              <div class="diff-content">
                <span class="diff-old">{{ formatBadcasePriorityLabel(pendingDiff.modifications.priority.old) }}</span>
                <span class="diff-arrow">→</span>
                <span class="diff-new">{{ formatBadcasePriorityLabel(pendingDiff.modifications.priority.new) }}</span>
                <div class="diff-actions">
                  <button type="button" @click="applyFieldChange('priority')" class="btn-confirm-sm" title="采纳（立即落库）">✓</button>
                  <button type="button" @click="cancelFieldChange('priority')" class="btn-cancel-sm" title="取消">✗</button>
                </div>
              </div>
            </div>
            <select
              v-model="badcase.priority"
              class="form-select"
              :class="{ 'field-with-diff': pendingDiff?.modifications?.priority }"
            >
              <option value="p1">P1 - 紧急</option>
              <option value="p2">P2 - 高</option>
              <option value="p3">P3 - 中</option>
              <option value="p4">P4 - 低</option>
            </select>
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
            <button class="action-btn save-btn" @click="saveBadcase" :disabled="saveLoading">
              {{ saveLoading ? '保存中...' : '保存' }}
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
          <div class="project-select">
            <label class="select-label">项目名称:</label>
            <select v-model="badcase.project_id" class="form-select" @change="handleProjectChange">
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
               <span class="field-value">{{ badcase.document_type || '其他文档' }}</span>
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
             <div v-for="(attachment, index) in badcase.attachments" :key="index" class="attachment-item">
               <span class="attachment-name">{{ attachment.name }}</span>
               <button class="remove-attachment-btn" @click="removeAttachment(index)">×</button>
             </div>
             <div v-if="badcase.attachments.length === 0" class="no-attachments">
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

         <div
           id="diff-field-append_comment"
           class="sidebar-section comment-section"
           :class="{ 'has-diff': hasEntityFieldDiff('append_comment') }"
         >
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
                   v-if="isEdit && badcaseId"
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
import { ref, reactive, onMounted, onActivated, onUnmounted, computed, nextTick, watch, inject } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BACKEND_BASE_URL, createBadcase, getBadcaseDetail, updateBadcase, addBadcaseComment, getProjectEditContext, getProjectPlans, getProjectMembers, getCurrentUser, getPlanDetail } from '../api.js'
import { snowflakeIdStr, normalizePlanId, isEmptyPlanKey } from '../utils/snowflakeId.js'
import { richTextHtmlHasContent, richTextHtmlDisplayLength } from '../utils/richTextContent.js'
import { personPrimaryLabel, personSecondaryLabel, applyDefaultAssigneeOnCreate } from '../utils/personLabel'
import user from '../store/user.js'
import MonacoDiffEditor from './MonacoDiffEditor.vue'
import RichTextHtmlEditor from './RichTextHtmlEditor.vue'
import {
  getPendingModifyDiffForDetail,
  clearPendingModifyDiffForDetail
} from '../utils/bcdSessionStore.js'


export default {
  name: 'NewBadcase',
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
    const { t } = useI18n()
    const router = useRouter()
    const route = useRoute()
    const loading = ref(false)
    const saveLoading = ref(false)
    const isEdit = ref(false)
    const badcaseId = ref(null)
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
      { value: 'pending', label: '待处理' },
      { value: 'resolved', label: '已解决' },
      { value: 'closed', label: '已关闭' },
      { value: 'hold', label: 'hold' },
      { value: 'reopened', label: '重新打开' },
      { value: 'not_badcase', label: 'not a badcase' }
    ])
    
    // 当前用户信息 - 使用全局用户状态
    const currentUser = computed(() => user.value)

    // 顶部栏：用户下拉菜单
    const showUserDropdown = ref(false)

    // 顶部栏：布局按钮（本页用于保持与项目详情页一致）
    const leftSidebarHidden = ref(false)
    const showTerminal = ref(false)
    const showAIAssistant = ref(false)
    
    // 最近选择的用户列表（暂时为空，后续可以从历史记录中获取）
    const recentAssignees = ref([])
    
    const assigneeSearchText = ref('')
    const planSearchText = ref('')
    const showPlanDropdown = ref(false)
    
    // 已展开的计划ID列表
    const expandedPlans = ref([])
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

    // 这些字段使用“就地 diff”（显示在对应文本域内部），不在顶部 MonacoDiffEditor 列表重复展示
    const inlineDiffFields = ['base_problem', 'answer', 'correct_answer', 'reproduction_steps', 'case_category', 'priority']
    
    const badcase = reactive({
      title: '',
      case_category: '功能缺陷', // 默认问题分类为"功能缺陷"
      base_problem: '',
      badcase_result: '',
      answer: '',
      correct_answer: '',
      problem_reason: '',
      solution: '',
      priority: 'p3', // 与后端 BadCase.priority 默认一致
      status: 'new',
      assignee: [],
      plan: '',
      reproduction_steps: '',
      comment: '',
      associate_project: true,
      project_id: '',
      assigned_users: '',
      document_type: '其他文档',
      attachments: []
    })

    /** 编辑态：面包屑与副标题用 BadCase 标题，避免长期显示泛化的「编辑BadCase」 */
    const editContextCrumb = computed(() => {
      if (!isEdit.value) return '编辑BadCase'
      const raw = String(badcase.title || '').trim()
      if (!raw) return '编辑BadCase'
      return raw.length > 22 ? `${raw.slice(0, 21)}…` : raw
    })
    const pageHeadline = computed(() => {
      if (!isEdit.value) return '新建BadCase'
      const raw = String(badcase.title || '').trim()
      if (!raw) return '编辑BadCase'
      return raw.length > 40 ? `${raw.slice(0, 39)}…` : raw
    })

    /** 编辑加载 / 预填 / 采纳后：统一为 p1–p4，避免 P1、文案与 option value 不一致导致下拉空白 */
    const normalizeBadcasePriorityForForm = () => {
      const raw = String(badcase.priority ?? '').trim()
      if (!raw) {
        badcase.priority = 'p3'
        return
      }
      const low = raw.toLowerCase()
      if (['p1', 'p2', 'p3', 'p4'].includes(low)) {
        badcase.priority = low
        return
      }
      const m = raw.match(/p\s*([1-4])/i)
      if (m) {
        badcase.priority = `p${m[1]}`
        return
      }
      if (low.includes('紧急') || low.includes('urgent')) {
        badcase.priority = 'p1'
        return
      }
      if (low.includes('高')) {
        badcase.priority = 'p2'
        return
      }
      if (low.includes('中')) {
        badcase.priority = 'p3'
        return
      }
      if (low.includes('低')) {
        badcase.priority = 'p4'
        return
      }
      badcase.priority = 'p3'
    }

    const BADCASE_CASE_CATEGORY_OPTIONS = Object.freeze([
      '功能缺陷',
      '性能问题',
      '界面问题',
      '兼容性问题',
      '安全问题',
      '其他'
    ])

    /** 与问题分类下拉 option 对齐，避免沙箱/接口返回值与 option 不一致导致空白 */
    const normalizeBadcaseCaseCategoryForForm = () => {
      const raw = String(badcase.case_category ?? '').trim()
      if (!raw) {
        badcase.case_category = ''
        return
      }
      if (BADCASE_CASE_CATEGORY_OPTIONS.includes(raw)) return
      const collapsed = raw.replace(/\s+/g, '').replace(/\u3000/g, '')
      for (const o of BADCASE_CASE_CATEGORY_OPTIONS) {
        if (collapsed === o.replace(/\s+/g, '')) {
          badcase.case_category = o
          return
        }
      }
      for (const o of BADCASE_CASE_CATEGORY_OPTIONS) {
        if (raw.length >= 2 && (o.startsWith(raw) || (o.length >= 2 && raw.startsWith(o.slice(0, 2))))) {
          badcase.case_category = o
          return
        }
      }
      const lower = raw.toLowerCase()
      const en = {
        functional: '功能缺陷',
        function: '功能缺陷',
        performance: '性能问题',
        compatibility: '兼容性问题',
        security: '安全问题',
        other: '其他'
      }
      if (en[lower]) {
        badcase.case_category = en[lower]
      }
    }

    // 获取状态文本
    const getStatusText = (status) => {
      const statusMap = {
        'new': '新建'
      }
      return statusMap[status] || status
    }

    /** 优先级 diff 展示：统一 p1/P1 等为与下拉选项一致的文案 */
    const formatBadcasePriorityLabel = (v) => {
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

    const aliasPendingModKey = (mods, fromKey, toKey) => {
      if (mods[fromKey] && !mods[toKey]) {
        mods[toKey] = mods[fromKey]
        delete mods[fromKey]
      }
    }

    const normalizePendingDiffModifications = (pd) => {
      if (!pd?.modifications || typeof pd.modifications !== 'object') return pd
      const mods = { ...pd.modifications }
      aliasPendingModKey(mods, 'correct_answer_final', 'correct_answer')
      aliasPendingModKey(mods, 'correct_answer_text', 'answer')
      aliasPendingModKey(mods, 'severity', 'priority')
      aliasPendingModKey(mods, 'classification', 'case_category')
      aliasPendingModKey(mods, 'category', 'case_category')
      aliasPendingModKey(mods, 'similar_questions', 'base_problem')
      aliasPendingModKey(mods, 'similar_question', 'base_problem')
      aliasPendingModKey(mods, 'related_questions', 'base_problem')
      aliasPendingModKey(mods, 'related_problem', 'base_problem')
      aliasPendingModKey(mods, 'specific_problem', 'base_problem')
      aliasPendingModKey(mods, 'reproduce_steps', 'reproduction_steps')
      aliasPendingModKey(mods, 'steps_to_reproduce', 'reproduction_steps')
      aliasPendingModKey(mods, 'reproduction_step', 'reproduction_steps')
      aliasPendingModKey(mods, 'badcase_reproduction_steps', 'reproduction_steps')
      aliasPendingModKey(mods, 'comment', 'append_comment')
      aliasPendingModKey(mods, 'remark', 'append_comment')
      return { ...pd, modifications: mods }
    }

    const clearPendingDiffFieldByAliases = (aliases) => {
      const mods = pendingDiff.value?.modifications
      if (!mods || !Array.isArray(aliases)) return
      for (const key of aliases) {
        if (key && Object.prototype.hasOwnProperty.call(mods, key)) {
          delete mods[key]
        }
      }
    }

    const clearBadcaseDetailPendingDiffField = (field) => {
      const f = String(field || '')
      if (!f) return
      const aliases = [f]
      if (f === 'reproduction_steps' || f === 'steps_to_reproduce' || f === 'reproduce_steps' || f === 'badcase_reproduction_steps') {
        aliases.push('reproduction_steps', 'steps_to_reproduce', 'reproduce_steps', 'badcase_reproduction_steps')
      } else if (f === 'correct_answer' || f === 'correct_answer_final' || f === 'correct_answer_text' || f === 'answer') {
        aliases.push('correct_answer', 'correct_answer_final', 'correct_answer_text', 'answer')
      } else if (f === 'priority' || f === 'severity') {
        aliases.push('priority', 'severity')
      } else if (f === 'case_category' || f === 'classification' || f === 'category') {
        aliases.push('case_category', 'classification', 'category')
      } else if (f === 'base_problem' || f === 'similar_questions' || f === 'similar_question' || f === 'related_questions' || f === 'related_problem' || f === 'specific_problem') {
        aliases.push('base_problem', 'similar_questions', 'similar_question', 'related_questions', 'related_problem', 'specific_problem')
      } else if (f === 'append_comment' || f === 'comment' || f === 'remark') {
        aliases.push('append_comment', 'comment', 'remark')
      }
      clearPendingDiffFieldByAliases([...new Set(aliases)])
    }

    const applyDetailFieldToBadcase = (field, val) => {
      const f = String(field || '')
      if (!f) return
      if (f === 'append_comment' || f === 'comment' || f === 'remark') return
      if (f === 'plan_id') {
        badcase.plan = normalizePlanId(val) || ''
        return
      }
      if (f === 'project_id') {
        badcase.project_id = val != null ? String(val) : ''
        badcase.associate_project = !!badcase.project_id
        return
      }
      if (f === 'steps_to_reproduce' || f === 'reproduce_steps' || f === 'badcase_reproduction_steps') {
        badcase.reproduction_steps = val || ''
        return
      }
      if (f === 'correct_answer_final' || f === 'correct_answer_text') {
        badcase.correct_answer = val || ''
        return
      }
      if (f === 'severity') {
        badcase.priority = val || ''
        return
      }
      if (f === 'classification' || f === 'category') {
        badcase.case_category = val || ''
        return
      }
      if (
        f === 'similar_questions' ||
        f === 'similar_question' ||
        f === 'related_questions' ||
        f === 'related_problem' ||
        f === 'specific_problem'
      ) {
        badcase.base_problem = val || ''
        return
      }
      if (Object.prototype.hasOwnProperty.call(badcase, f)) {
        badcase[f] = val
      }
    }

    const applyPendingModificationsToForm = () => {
      if (!pendingDiff.value?.modifications) return
      for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
        if (field === 'append_comment' || field === 'comment') continue
        if (
          !data ||
          typeof data !== 'object' ||
          !('new' in data) ||
          data.new === undefined ||
          String(data.new).trim() === ''
        ) {
          continue
        }
        if (field === 'plan_id') {
          badcase.plan = normalizePlanId(data.new) || ''
          continue
        }
        if (field === 'project_id') {
          badcase.project_id = String(data.new)
          badcase.associate_project = true
          continue
        }
        if (badcase.hasOwnProperty(field)) {
          badcase[field] = data.new
        }
      }
      normalizeBadcasePriorityForForm()
      normalizeBadcaseCaseCategoryForForm()
    }

    /** 沙箱跳入已打开的嵌入 Tab：keep-alive 复用时重新灌入 session 中的 pending diff */
    const focusAppendCommentDiffInSidebar = async () => {
      if (!hasEntityFieldDiff('append_comment')) return
      isRightSidebarOpen.value = true
      await nextTick()
      scrollToDiffField('append_comment')
    }

    const reloadPendingDiffFromSession = async () => {
      if (!props.embedded) return
      const showDiffMode = props.show_diff
      if (!showDiffMode) {
        pendingDiff.value = null
        return
      }
      const pd0 = getPendingModifyDiffForDetail(
        snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
      )
      if (!pd0) {
        pendingDiff.value = null
        return
      }
      try {
        let pd = { ...pd0 }
        const tid = pd?.targetId != null ? String(pd.targetId).trim() : ''
        const cur =
          props.id != null
            ? String(props.id).trim()
            : badcaseId.value
              ? String(badcaseId.value).trim()
              : ''
        const tgt = String(pd?.target || '').toLowerCase().replace(/-/g, '_')
        const isBc = tgt === 'badcase' || tgt === 'bad_case' || tgt === ''
        if (!isBc || (cur && tid && tid !== cur)) return
        pd = normalizePendingDiffModifications(pd)
        pendingDiff.value = pd
        applyPendingModificationsToForm()
        await focusAppendCommentDiffInSidebar()
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
      const projectId = badcase.project_id
      const oldProjectId = badcase._previousProjectId // 保存之前的项目ID
      console.log('handleProjectChange: 项目选择改变，项目ID:', projectId, '之前项目ID:', oldProjectId)
      
      // 只有在项目真正改变时才清空相关数据
      if (oldProjectId !== projectId) {
        console.log('项目ID发生变化，清空相关数据')
        
        // 在编辑模式下，如果项目ID没有真正改变，保持现有数据
        if (isEdit.value && oldProjectId && oldProjectId.toString() === projectId.toString()) {
          console.log('编辑模式下项目ID未真正改变，保持现有数据')
        } else {
          badcase.plan = ''
          badcase.assignee = []
          availablePlans.value = []
          // 清空项目成员
          projectMembers.value = []
        }
      } else {
        console.log('项目ID未变化，保持现有数据')
      }
      
      // 更新之前的项目ID
      badcase._previousProjectId = projectId
      
      // 获取项目信息
      if (projectId) {
        const project = availableProjects.value.find(p => p.id == projectId)
        if (project) {
          projectInfo.value = project
          console.log('handleProjectChange: 找到项目信息:', project.name)
          // 获取项目计划
          fetchProjectPlans(projectId)
          // 获取项目成员
          fetchProjectMembers(projectId)
        } else {
          console.log('handleProjectChange: 未找到项目信息')
        }
      } else {
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
    
    // 使用后端 plans 树直接生成下拉选项（避免额外请求 /plans）
    const setAvailablePlansFromTree = async (plansTree) => {
      const formattedPlans = []

      const processPlans = (planList, level = 0) => {
        const processedPlans = []
        ;(planList || []).forEach(plan => {
          // 只显示进行中的计划，且必须是 badcase 类型计划
          if (plan.status === 'active') {
            const children = plan.children && plan.children.length > 0 ? processPlans(plan.children, level + 1) : []

            if (children.length > 0 || plan.status === 'active') {
              const planIdStr = snowflakeIdStr(plan.id) || String(plan.id)
              const planOption = {
                value: planIdStr,
                label: plan.name,
                level,
                is_pinned: plan.is_pinned || false,
                icon: plan.icon || '📁',
                badcase_count: plan.badcase_count || 0
              }
              if (children.length > 0) planOption.children = children
              processedPlans.push(planOption)
            }
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
            badcase_count: pl.badcase_count || 0
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
      if (isEmptyPlanKey(badcase.plan)) {
        return '请选择计划'
      }
      return (
        findPlanLabelInTree(availablePlans.value, badcase.plan) ||
        selectedPlanDisplayName.value ||
        '…'
      )
    })

    const applyInitialPlanForCreate = (query, planIdProp) => {
      const raw = query.plan_id ?? planIdProp
      const id = normalizePlanId(raw)
      badcase.plan = id || ''
    }
    
    // 刷新项目计划
    const refreshProjectPlans = async () => {
      if (badcase.project_id) {
        console.log('刷新项目计划')
        await fetchProjectPlans(badcase.project_id)
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
    
    // 初始化BadCase数据
    const initBadcase = async () => {
      try {
        // 优先使用 props，其次使用路由参数
        const query = route.query
        console.log('=== [NewBadcase] 初始化BadCase开始 ===')
        console.log('[NewBadcase] 路由查询参数:', query)
        console.log('[NewBadcase] Props 参数:', props)
        console.log('[NewBadcase] props.id:', props.id, 'type:', typeof props.id)
        console.log('[NewBadcase] props.edit:', props.edit, 'type:', typeof props.edit)
        console.log('[NewBadcase] props.show_diff:', props.show_diff, 'type:', typeof props.show_diff)
        console.log('[NewBadcase] pendingDiff 初始值:', pendingDiff.value)
        
        // 判断是否编辑模式：
        // 1）显式传入 edit=true
        // 2）路由 query.edit=true
        // 3）存在明确的 id（优先使用 props.id，其次 pendingDiff.targetId）
        const showDiffMode = props.show_diff || query.show_diff === 'true'
        // 注意：props.id 是最可靠的来源，因为它是由父组件传递的
        const rawId = props.id ?? query.id ?? (pendingDiff.value?.targetId ?? null)
        // 编辑模式判断：props.edit 为 true 时直接进入编辑模式
        const isEditMode = props.edit === true || query.edit === 'true' || !!rawId
        console.log('[NewBadcase] 计算编辑模式参数:', {
          props_id: props.id,
          props_id_type: typeof props.id,
          query_id: query.id,
          pending_target_id: pendingDiff.value?.targetId,
          rawId,
          rawId_type: typeof rawId,
          props_edit: props.edit,
          props_edit_type: typeof props.edit,
          query_edit: query.edit,
          isEditMode,
          showDiffMode
        })
        const itemId = rawId
        const itemProjectId = props.project_id || query.project_id
        
        // 防御：避免把 undefined/null 的字符串当成有效 id
        const normalizedItemId =
          itemId === undefined || itemId === null ? null : String(itemId).trim()
        const effectiveItemId =
          !normalizedItemId || normalizedItemId === 'undefined' || normalizedItemId === 'null'
            ? null
            : normalizedItemId
        console.log('[NewBadcase] 处理后的 ID:', {
          itemId,
          normalizedItemId,
          effectiveItemId
        })

        if (isEditMode && effectiveItemId) {
          console.log('编辑模式，BadCase ID:', itemId)
          isEdit.value = true
          badcaseId.value = effectiveItemId
          loading.value = true

          try {
          const response = await getBadcaseDetail(effectiveItemId)
          if (response.data.success && response.data.badcase) {
            console.log('=== BadCase详情API响应 ===')
            console.log('完整响应:', response.data)
            console.log('BadCase数据:', response.data.badcase)
            console.log('复现步骤字段:', response.data.badcase.reproduction_steps)
            console.log('复现步骤类型:', typeof response.data.badcase.reproduction_steps)
            
            Object.assign(badcase, response.data.badcase)
            normalizeBadcasePriorityForForm()
            normalizeBadcaseCaseCategoryForForm()
            console.log('BadCase信息加载成功:', badcase)
            console.log('加载后的复现步骤:', badcase.reproduction_steps)
            console.log('原始数据中的项目ID:', response.data.badcase.project_id, '类型:', typeof response.data.badcase.project_id)
            console.log('原始数据中的计划ID:', response.data.badcase.plan, '类型:', typeof response.data.badcase.plan)
            
            // 确保数据类型一致
            if (badcase.project_id) {
              badcase.project_id = badcase.project_id.toString()
              console.log('编辑模式：项目ID类型转换后:', badcase.project_id, '类型:', typeof badcase.project_id)
            }
            
            badcase.plan = normalizePlanId(badcase.plan_id ?? badcase.plan) || ''
            entityComments.value = Array.isArray(response.data.badcase.comments) ? [...response.data.badcase.comments] : []
            
            // 确保编辑模式下正确设置关联项目状态
            if (badcase.project_id) {
              badcase.associate_project = true
              console.log('编辑模式：设置associate_project为true，项目ID:', badcase.project_id)
              
              // 初始化_previousProjectId，避免handleProjectChange误判
              badcase._previousProjectId = badcase.project_id
              console.log('编辑模式：初始化_previousProjectId:', badcase._previousProjectId)
            }
            
            // 复现步骤由 RichTextHtmlEditor v-model 绑定 badcase.reproduction_steps

            // 计划/成员由 onMounted 中 getProjectEditContext 一次性拉取，避免与 initBadcase 重复打 /plans、/members
            if (badcase.project_id) {
              console.log('编辑模式，项目ID:', badcase.project_id, '（plans/members 由 edit-context 统一加载）')
              
              // 确保数据同步
              console.log('编辑模式初始化完成后，当前状态:')
              console.log('- badcase.project_id:', badcase.project_id)
              console.log('- badcase.associate_project:', badcase.associate_project)
              console.log('- badcase.plan:', badcase.plan)
              console.log('- projectInfo:', projectInfo.value)
              console.log('- projectMembers.length:', projectMembers.value.length)
              console.log('- availablePlans.length:', availablePlans.value.length)
              
              // 强制触发响应式更新
              await nextTick()
              
              // 延迟再次触发响应式更新，确保模板正确渲染
              setTimeout(async () => {
                console.log('延迟响应式更新，当前状态:')
                console.log('- badcase.project_id:', badcase.project_id)
                console.log('- badcase.associate_project:', badcase.associate_project)
                console.log('- badcase.plan:', badcase.plan)
                console.log('- projectInfo:', projectInfo.value)
                console.log('- availablePlans:', availablePlans.value)
                
                // 强制触发响应式更新
                await nextTick()
                
                // 再次检查状态，确保数据正确设置
                console.log('最终检查 - 模板渲染前:')
                console.log('- badcase.project_id:', badcase.project_id)
                console.log('- badcase.associate_project:', badcase.associate_project)
                console.log('- badcase.plan:', badcase.plan)
                console.log('- availablePlans长度:', availablePlans.value.length)
                console.log('- availablePlans内容:', availablePlans.value)
                
                // 强制更新badcase对象，触发响应式更新
                const temp = { ...badcase }
                Object.assign(badcase, temp)
                
                await nextTick()
                
                // 最终状态检查
                console.log('最终状态检查:')
                console.log('- badcase.project_id:', badcase.project_id)
                console.log('- badcase.plan:', badcase.plan)
                console.log('- badcase.associate_project:', badcase.associate_project)
                console.log('- availableProjects:', availableProjects.value)
                console.log('- availablePlans:', availablePlans.value)
                
                // 检查项目匹配
                const matchedProject = availableProjects.value.find(p => p.id == badcase.project_id)
                console.log('匹配的项目:', matchedProject)
                
                // 检查计划匹配
                const matchedPlan = availablePlans.value.find(p => p.value == badcase.plan)
                console.log('匹配的计划:', matchedPlan)
              }, 100)
            } else {
              console.log('编辑模式，BadCase没有项目ID')
            }
          } else {
            alert('获取BadCase信息失败')
            goBack()
          }
        } catch (error) {
          console.error('=== 获取BadCase信息失败 ===')
          console.error('错误类型:', error.name)
          console.error('错误消息:', error.message)
          console.error('错误堆栈:', error.stack)
          alert('获取BadCase信息失败: ' + error.message)
          goBack()
        } finally {
          loading.value = false
          if (isEdit.value) {
            const t0 = String(badcase.title || '').trim()
            emit('titleLoaded', t0 || `BadCase ${badcaseId.value || ''}`)
          }
        }
        } else if (pendingDiff.value?.targetId) {
          // 兜底：如果上面没走编辑分支，但存在 pendingDiff.targetId，仍然强制按编辑逻辑处理
          const fallbackId = String(pendingDiff.value.targetId).trim()
          if (fallbackId && fallbackId !== 'undefined' && fallbackId !== 'null') {
            console.log('兜底编辑模式，BadCase ID 来自 pendingDiff.targetId:', fallbackId)
            isEdit.value = true
            badcaseId.value = fallbackId
            loading.value = true
            try {
              const response = await getBadcaseDetail(fallbackId)
              if (response.data.success && response.data.badcase) {
                Object.assign(badcase, response.data.badcase)
                normalizeBadcasePriorityForForm()
                normalizeBadcaseCaseCategoryForForm()
                console.log('兜底编辑模式：BadCase信息加载成功:', badcase)
              } else {
                alert('获取BadCase信息失败')
                goBack()
              }
            } catch (error) {
              console.error('兜底编辑模式：获取BadCase信息失败:', error)
              alert('获取BadCase信息失败: ' + error.message)
              goBack()
            } finally {
              loading.value = false
              if (isEdit.value) {
                const t0 = String(badcase.title || '').trim()
                emit('titleLoaded', t0 || `BadCase ${badcaseId.value || ''}`)
              }
            }
          }
        } else if (query.project_id || props.project_id) {
          const pidRaw = query.project_id || props.project_id
          console.log('新建模式，项目ID:', pidRaw)
          console.log('project_id类型:', typeof pidRaw)
          console.log('availableProjects:', availableProjects.value)

          // 新建模式，设置项目ID
          badcase.project_id = String(pidRaw)
          console.log('设置badcase.project_id:', badcase.project_id)
          console.log('设置后badcase.project_id类型:', typeof badcase.project_id)

          // 获取项目信息
          const project = availableProjects.value.find(p => p.id == badcase.project_id)
          if (project) {
            projectInfo.value = project
            console.log('找到项目信息:', project.name)
          } else {
            console.log('未找到项目信息，availableProjects:', availableProjects.value)
            console.log('尝试查找项目，project_id:', badcase.project_id)
            console.log('availableProjects中的项目ID类型:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
          }

          // 计划/成员由下方 getProjectEditContext 统一加载，避免重复请求

          // 确保数据同步
          console.log('初始化完成后，当前状态:')
          console.log('- badcase.project_id:', badcase.project_id)
          console.log('- projectMembers.length:', projectMembers.value.length)
          console.log('- availablePlans.length:', availablePlans.value.length)
        } else {
          console.log('没有项目ID参数')
          console.log('所有查询参数:', query)
        }

        console.log('=== 初始化BadCase完成 ===')

        // 最终状态检查
        if (isEdit.value) {
          console.log('=== 编辑模式最终状态检查 ===')
          console.log('badcase对象:', badcase)
          console.log('badcase.project_id:', badcase.project_id)
          console.log('badcase.plan:', badcase.plan)
          console.log('badcase.associate_project:', badcase.associate_project)
          console.log('availableProjects:', availableProjects.value)
          console.log('availablePlans:', availablePlans.value)
          console.log('projectInfo:', projectInfo.value)
        }
      } catch (initError) {
        console.error('=== initBadcase函数执行失败 ===')
        console.error('错误类型:', initError.name)
        console.error('错误消息:', initError.message)
        console.error('错误堆栈:', initError.stack)
        alert('BadCase初始化失败: ' + initError.message)
        loading.value = false
      }
    }

    // 保存BadCase
    const saveBadcase = async () => {
      console.log('=== 开始保存BadCase ===')
      console.log('当前BadCase数据:', badcase)
      console.log('当前复现步骤:', badcase.reproduction_steps)
      
      if (!badcase.title.trim()) {
        alert('请输入BadCase标题')
        return
      }
      if (!badcase.case_category) {
        alert('请选择问题分类')
        return
      }
      if (!badcase.priority) {
        alert('请选择优先级')
        return
      }
      
      if (!richTextHtmlHasContent(badcase.reproduction_steps)) {
        alert('请输入复现步骤')
        return
      }

      saveLoading.value = true
      try {
        const rawPlanKey =
          badcase.plan_id != null && badcase.plan_id !== '' ? badcase.plan_id : badcase.plan
        let plan_id = null
        if (!isEmptyPlanKey(rawPlanKey)) {
          const ps = snowflakeIdStr(rawPlanKey)
          if (ps) plan_id = ps
        }
        // 仅新建模式添加 card_id，用于后端校验卡片类型（雪花勿 parseInt）
        const cardIdStr =
          !isEdit.value && props.card_id != null && props.card_id !== '' ? snowflakeIdStr(props.card_id) : ''
        const cardIdValue = cardIdStr || null
        const badcaseData = {
          title: badcase.title,
          case_category: badcase.case_category,
          base_problem: (badcase.base_problem || '').trim(),
          reproduction_steps: badcase.reproduction_steps || '',
          badcase_result: badcase.badcase_result || '待确认',
          answer: badcase.answer || '待确认',
          correct_answer: badcase.correct_answer || '待确认',
          problem_reason: badcase.problem_reason || '',
          solution: badcase.solution || '',
          priority: badcase.priority,
          status: badcase.status,
          // 优先使用 assignee_id（用户ID），兼容旧格式
          assignee: badcase.assignee_id ? String(badcase.assignee_id) : (Array.isArray(badcase.assignee) ? badcase.assignee.join(',') : badcase.assignee),
          plan: badcase.plan,
          plan_id,
          project_id: badcase.project_id,
          assigned_users: Array.isArray(badcase.assigned_users) ? badcase.assigned_users.join(',') : badcase.assigned_users,
          document_type: badcase.document_type,
          attachments: badcase.attachments.map(att => ({
            name: att.name,
            size: att.size
          }))
        }
        // 新建时添加卡片ID
        if (cardIdValue) {
          badcaseData.card_id = cardIdValue
        }
        
        console.log('准备发送的BadCase数据:', badcaseData)
        console.log('复现步骤字段值:', badcaseData.reproduction_steps)
        console.log('复现步骤字段类型:', typeof badcaseData.reproduction_steps)

        let result
        if (isEdit.value) {
          console.log('=== 更新BadCase ===')
          console.log('BadCase ID:', badcaseId.value)
          console.log('更新数据:', badcaseData)
          result = await updateBadcase(badcaseId.value, badcaseData)
          console.log('更新响应:', result)
          
          if (result.data.success) {
            alert('BadCase更新成功')
            goBack()
          } else {
            alert(`更新失败: ${result.data.error || '未知错误'}`)
          }
        } else {
          console.log('=== 创建BadCase ===')
          console.log('创建数据:', badcaseData)
          result = await createBadcase(badcaseData)
          console.log('创建BadCase响应:', result)
          
          if (result.data.success) {
            alert('BadCase创建成功')
            goBack()
          } else {
            const errorMsg = result.data.error || '未知错误'
            console.error('创建失败:', errorMsg)
            alert(`创建失败: ${errorMsg}`)
          }
        }
      } catch (error) {
        console.error('保存BadCase失败:', error)
        console.error('错误详情:', error.response?.data || error.message)
        alert(`保存失败: ${error.response?.data?.error || error.message || '请重试'}`)
      } finally {
        saveLoading.value = false
      }
    }

    // 复制文档链接
    const copyDocumentLink = () => {
      const link = `https://knowledge-base.example.com/project/${badcase.project_id}/documents`
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
        badcase.attachments.push({
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
      badcase.attachments.splice(index, 1)
    }

    const fileInput = ref(null)
    const commentEditorActive = ref(false)
    const activateCommentEditor = () => {
      commentEditorActive.value = true
    }
    const finishCommentEditor = () => {
      commentEditorActive.value = false
    }

    const badcaseDraftPreset = inject('badcaseDraftPreset', null)

    const _escHtml = (s) =>
      String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
    watch(
      () => badcaseDraftPreset?.value?.token ?? 0,
      async (tok) => {
        if (!tok || !badcaseDraftPreset?.value?.description) return
        if (isEdit.value) return
        const block = String(badcaseDraftPreset.value.description).trim()
        if (!block) return
        const fragment = `<p><strong>【终端关联】</strong></p><pre style="white-space:pre-wrap;word-break:break-all;">${_escHtml(block)}</pre>`
        await nextTick()
        const cur = (badcase.reproduction_steps || '').trim()
        badcase.reproduction_steps = cur ? `${cur}<p><br></p>${fragment}` : fragment
      }
    )
    
    const stepsLength = computed(() => richTextHtmlDisplayLength(badcase.reproduction_steps))
    
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
      if (field === 'append_comment') keys.push('remark')
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

    const plainCommentFromDiffValue = (val) =>
      formatEntityDiffValue('append_comment', typeof val === 'object' && val !== null && 'new' in val ? val.new : val)

    const commentPlainAlreadyListed = (plain) => {
      const want = String(plain || '').trim()
      if (!want) return false
      return entityComments.value.some((c) => {
        const tempDiv = document.createElement('div')
        tempDiv.innerHTML = String(c.content || '')
        const body = (tempDiv.textContent || tempDiv.innerText || '').trim()
        return body === want
      })
    }

    const optimisticAppendEntityComment = (text) => {
      const plain = String(text || '').trim()
      if (!plain || commentPlainAlreadyListed(plain)) return
      const author = currentUser.value ? personPrimaryLabel(currentUser.value) : '—'
      entityComments.value = [
        ...entityComments.value,
        {
          id: `pending-${Date.now()}`,
          content: plain.includes('<') ? plain : `<p>${plain.replace(/\n/g, '<br>')}</p>`,
          user_name: author,
          created_at: new Date().toISOString(),
          source_message_id: pendingDiff.value?.messageId ?? null
        }
      ]
    }

    const loadEntityComments = async () => {
      const id = badcaseId.value
      if (!id) return
      try {
        const response = await getBadcaseDetail(id)
        const list = response?.data?.badcase?.comments
        entityComments.value = Array.isArray(list) ? [...list] : []
      } catch (e) {
        console.error('[Badcase] 加载评论失败:', e)
      }
    }

    const reloadEntityCommentsAfterAdopt = async (expectedPlain = '') => {
      const want = String(expectedPlain || '').trim()
      const delays = want ? [0, 200, 450, 800] : [0]
      for (const ms of delays) {
        if (ms) await new Promise((resolve) => setTimeout(resolve, ms))
        await loadEntityComments()
        if (!want || commentPlainAlreadyListed(want)) return
      }
    }

    const clearCommentPendingDiffKeys = () => {
      const mods = pendingDiff.value?.modifications
      if (!mods) return
      for (const k of ['append_comment', 'comment', 'remark']) {
        delete mods[k]
      }
      if (Object.keys(mods).filter((key) => !String(key).startsWith('_')).length === 0) {
        clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
        pendingDiff.value = null
      }
    }

    const resolveEditorBadcaseId = () => {
      const raw =
        props.id != null && props.id !== ''
          ? props.id
          : badcaseId.value != null && badcaseId.value !== ''
            ? badcaseId.value
            : null
      return raw != null ? String(raw).trim() : ''
    }

    const onDetailModifyAdopted = async (event) => {
      const tid = event?.detail?.targetId != null ? String(event.detail.targetId).trim() : ''
      const cur = resolveEditorBadcaseId()
      if (!tid || !cur || tid !== cur) return

      const fieldUpdates = event?.detail?.fieldUpdates
      if (fieldUpdates && typeof fieldUpdates === 'object') {
        for (const [field, val] of Object.entries(fieldUpdates)) {
          const f = String(field)
          if (f === 'append_comment' || f === 'comment' || f === 'remark') {
            const plain = plainCommentFromDiffValue(val)
            optimisticAppendEntityComment(plain)
            await reloadEntityCommentsAfterAdopt(plain)
            clearCommentPendingDiffKeys()
          } else {
            applyDetailFieldToBadcase(f, val)
            clearBadcaseDetailPendingDiffField(f)
          }
        }
      }

      if (
        pendingDiff.value?.modifications &&
        Object.keys(pendingDiff.value.modifications).filter((k) => !String(k).startsWith('_')).length === 0
      ) {
        pendingDiff.value = null
      }
    }

    const submitCommentDraft = async () => {
      if (!isEdit.value || !badcaseId.value || !richTextHtmlHasContent(commentDraft.value)) return
      commentSubmitting.value = true
      try {
        const resp = await addBadcaseComment(badcaseId.value, { content: commentDraft.value })
        const res = resp?.data || resp
        if (res?.success && res.comment) {
          entityComments.value = [...entityComments.value, res.comment]
          commentDraft.value = ''
          commentEditorActive.value = false
        } else {
          alert(res?.error || res?.message || '发表评论失败')
        }
      } catch (e) {
        console.error('[Badcase] 发表评论失败:', e)
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
      badcase.status = status
      showStatusDropdown.value = false
    }

    // 切换负责人下拉框显示
    const toggleAssigneeDropdown = () => {
      showAssigneeDropdown.value = !showAssigneeDropdown.value
    }

    // 获取负责人显示文本
    const getAssigneeDisplayText = () => {
      const resolveId = (rawId) => {
        const sid = String(rawId)
        const member = projectMembers.value.find(m => String(m.id) === sid)
        if (member) return personPrimaryLabel(member)
        if (currentUser.value && String(currentUser.value.id) === sid) {
          return personPrimaryLabel(currentUser.value)
        }
        if (/^\d+$/.test(sid)) return `用户#${sid}`
        return personPrimaryLabel({ name: sid, email: sid })
      }

      if (badcase.assignee_id != null && badcase.assignee_id !== '') {
        return resolveId(badcase.assignee_id)
      }

      if (!badcase.assignee || (Array.isArray(badcase.assignee) && badcase.assignee.length === 0)) {
        return '未指派'
      }

      if (typeof badcase.assignee === 'string') {
        const s = badcase.assignee.trim()
        if (!s) return '未指派'
        return resolveId(s)
      }

      if (Array.isArray(badcase.assignee)) {
        if (badcase.assignee.length === 1) return resolveId(badcase.assignee[0])
        const labels = badcase.assignee.slice(0, 2).map((x) => resolveId(x))
        return badcase.assignee.length > 2 ? `${labels.join('、')} 等 ${badcase.assignee.length} 人` : labels.join('、')
      }

      return personPrimaryLabel(badcase.assignee)
    }

    // 检查负责人是否被选中
    const isAssigneeSelected = (assigneeValue) => {
      // 优先使用 assignee_id（后端返回的用户ID）
      if (badcase.assignee_id) {
        return badcase.assignee_id.toString() === assigneeValue.toString()
      }
      // 兼容旧逻辑：检查数组
      if (Array.isArray(badcase.assignee)) {
        return badcase.assignee.includes(assigneeValue)
      }
      // 兼容字符串比较
      return badcase.assignee && badcase.assignee.toString() === assigneeValue.toString()
    }

    // 切换负责人选择状态
    const toggleAssignee = (assigneeValue) => {
      // 更新 assignee_id（用于选中状态判断）
      badcase.assignee_id = parseInt(assigneeValue)
      
      // 同时更新 assignee 数组（兼容旧逻辑）
      if (!badcase.assignee) {
        badcase.assignee = []
      }
      
      // 单选模式：清空并设置为当前选中值
      badcase.assignee = [assigneeValue]
      
      console.log('切换负责人:', assigneeValue, 'assignee_id:', badcase.assignee_id)
    }

    // 切换计划下拉框显示
    const togglePlanDropdown = () => {
      showPlanDropdown.value = !showPlanDropdown.value
    }

    // 选择计划
    const selectPlan = (planValue) => {
      badcase.plan = normalizePlanId(planValue) || String(planValue)
      selectedPlanDisplayName.value = findPlanLabelInTree(availablePlans.value, badcase.plan) || ''
      showPlanDropdown.value = false
    }

    const isPlanSelected = (planValue) => planIdsMatch(badcase.plan, planValue)
    
    // 确认字段修改
    const confirmFieldChange = (field) => {
      console.log('[DIFF] 确认字段修改:', field)
      if (pendingDiff.value?.modifications?.[field]) {
        // 已经预填充了新值，直接清除 diff 显示
        delete pendingDiff.value.modifications[field]
        
        // 如果所有字段都已确认，清除 sessionStorage 并通知对话区
        const remainingFields = Object.keys(pendingDiff.value.modifications || {}).filter(k => !String(k).startsWith('_'))
        if (remainingFields.length === 0) {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
          // 通知对话区修改已确认
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
    
    // 取消字段修改
    const cancelFieldChange = (field) => {
      console.log('[DIFF] 取消字段修改:', field)
      if (pendingDiff.value?.modifications?.[field]) {
        // 恢复原值
        const oldValue = pendingDiff.value.modifications[field].old
        if (field === 'append_comment' || field === 'comment') {
          // 评论只追加，取消 diff 即可
        } else if (field === 'plan_id') {
          badcase.plan = normalizePlanId(oldValue) || ''
        } else if (field === 'project_id') {
          badcase.project_id = oldValue ? String(oldValue) : ''
          badcase.associate_project = !!badcase.project_id
        } else if (badcase.hasOwnProperty(field)) {
          badcase[field] = oldValue || ''
        }
        if (field === 'priority') {
          normalizeBadcasePriorityForForm()
        }
        if (field === 'case_category') {
          normalizeBadcaseCaseCategoryForForm()
        }

        // 清除该字段的 diff
        delete pendingDiff.value.modifications[field]
        
        // 如果所有字段都已取消，清除 sessionStorage
        const remainingFields = Object.keys(pendingDiff.value.modifications || {}).filter(k => !String(k).startsWith('_'))
        if (remainingFields.length === 0) {
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
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

    const notifyDetailAdoptCompleteIfDone = (adoptedField, adoptedValue) => {
      if (pendingDiff.value) return
      const tid =
        props.id != null && props.id !== ''
          ? String(props.id).trim()
          : badcaseId.value
            ? String(badcaseId.value).trim()
            : ''
      if (!tid) return
      window.dispatchEvent(
        new CustomEvent('detail-modify-adopted', {
          detail: {
            targetId: tid,
            targetType: 'badcase',
            adoptedField,
            adoptedValue
          },
          bubbles: true
        })
      )
    }

    // 采纳字段修改：单字段落库（复用既有 /api/projects/{project_id}/modify）
    const applyFieldChange = async (field) => {
      if (!pendingDiff.value?.modifications?.[field]) return

      const projectId = badcase.project_id || props.project_id
      const targetId = pendingDiff.value?.targetId || props.id
      const target = pendingDiff.value?.target || 'badcase'
      const newValue = pendingDiff.value.modifications[field]?.new

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
            modifications: { [field]: newValue },
            confirm: true,
            message_id: pendingDiff.value?.messageId
          })
        })
        const result = await resp.json()
        if (!result.success) {
          console.error('[DIFF] 采纳失败:', result.error)
          return
        }

        if (field === 'append_comment' || field === 'comment') {
          const plain = plainCommentFromDiffValue(newValue)
          optimisticAppendEntityComment(plain)
          if (result.async === true) {
            await new Promise((resolve) => setTimeout(resolve, 420))
          }
          await reloadEntityCommentsAfterAdopt(plain)
          commentDraft.value = ''
        } else if (field === 'plan_id') {
          badcase.plan = normalizePlanId(newValue) || ''
        } else if (field === 'project_id') {
          badcase.project_id = String(newValue)
          badcase.associate_project = true
        } else if (badcase.hasOwnProperty(field)) {
          badcase[field] = newValue
        }
        if (field === 'priority') {
          normalizeBadcasePriorityForForm()
        }
        if (field === 'case_category') {
          normalizeBadcaseCaseCategoryForForm()
        }

        confirmFieldChange(field)
        notifyDetailAdoptCompleteIfDone(field, newValue)
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
      if (badcase.project_id) {
        const targetUrl = `/project-detail/${badcase.project_id}`
        // 如果有计划ID，添加到URL参数中，让ProjectDetail自动展开
        if (!isEmptyPlanKey(badcase.plan)) {
          router.push(`${targetUrl}?expand_plan=${badcase.plan}`)
        } else {
          router.push(targetUrl)
        }
      } else {
        // 如果没有项目ID，使用浏览器后退
        router.go(-1)
      }
    }

    // 顶部栏：回到项目详情（与面包屑交互一致）
    const goBackToProjectDetail = () => {
      showUserDropdown.value = false
      if (badcase.project_id) {
        router.push(`/project-detail/${badcase.project_id}`)
      } else if (props.project_id) {
        router.push(`/project-detail/${props.project_id}`)
      } else if (projectInfo.value?.id) {
        router.push(`/project-detail/${projectInfo.value.id}`)
      } else {
        goBack()
      }
    }

    const toggleUserDropdown = () => {
      showUserDropdown.value = !showUserDropdown.value
    }

    const showNotifications = () => {
      showUserDropdown.value = false
      alert(t('project.notificationsDev'))
    }

    const showHelp = () => {
      showUserDropdown.value = false
      alert('帮助功能开发中...')
    }

    const showTeamManagement = () => {
      showUserDropdown.value = false
      alert('团队管理功能开发中...')
    }

    const showUserProfile = () => {
      showUserDropdown.value = false
      alert('个人资料功能开发中...')
    }

    const logout = () => {
      showUserDropdown.value = false
      // 与 ProjectDetail 一致：动态导入并调用 logout
      import('../store/user.js').then(({ logout: logoutUser }) => {
        logoutUser()
      })
      router.push('/login')
    }

    const setLayout = (layout) => {
      switch (layout) {
        case 'left':
          leftSidebarHidden.value = !leftSidebarHidden.value
          break
        case 'bottom':
          showTerminal.value = !showTerminal.value
          break
        case 'right':
          showAIAssistant.value = !showAIAssistant.value
          break
      }
    }
    
    onMounted(async () => {
      window.addEventListener('badcase-detail-refresh', onDetailModifyAdopted)
      console.log('=== 组件挂载开始 ===')
      
      try {
        // 仅在 show_diff 模式下读取待确认 diff；普通“编辑详情”一律忽略并清理历史 diff
        const query = route.query
        const showDiffMode = props.show_diff || query.show_diff === 'true'
        if (showDiffMode) {
          const diffEarly = getPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
          console.log('[DIFF] showDiffMode:', showDiffMode)
          console.log('[DIFF] bcd:ss:diff active:', !!diffEarly)
          if (diffEarly) {
            try {
              pendingDiff.value = diffEarly
              console.log('[DIFF] 预读取到 diff 数据:', pendingDiff.value)
              console.log('[DIFF] pendingDiff.modifications:', pendingDiff.value?.modifications)
              console.log('[DIFF] modifications keys:', pendingDiff.value?.modifications ? Object.keys(pendingDiff.value.modifications) : [])
              if (pendingDiff.value?.modifications) {
                pendingDiff.value = normalizePendingDiffModifications(pendingDiff.value)
              }
            } catch (e) {
              console.error('[DIFF] 预读取 diff 失败:', e)
            }
          }
        } else {
          // 普通编辑模式：防止历史 diff 污染任意 BadCase 详情
          clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
          pendingDiff.value = null
        }

        // embedded 模式下尽量少请求（ProjectDetail 已有大量上下文），提升进入编辑页速度
        if (!user.value) {
          await fetchCurrentUser()
        }
        
        // 然后初始化BadCase
        console.log('开始初始化BadCase...')
        await initBadcase()
        console.log('BadCase初始化完成')

        // 初始化后，一次性拉取编辑页最小上下文（project + plans + members）
        const ctxProjectId = badcase.project_id || props.project_id
        if (ctxProjectId) {
          try {
            const resp = await getProjectEditContext(ctxProjectId)
            if (resp.data?.success) {
              projectInfo.value = resp.data.project || projectInfo.value
              projectMembers.value = resp.data.members || projectMembers.value
              // 将当前项目添加到 availableProjects 中，确保下拉框能显示
              if (resp.data.project && !availableProjects.value.find(p => p.id == resp.data.project.id)) {
                availableProjects.value.push(resp.data.project)
              }
              // 直接用 edit-context 返回的 plans，避免额外请求 /plans
              await setAvailablePlansFromTree(resp.data.plans || [])
            }
          } catch (e) {
            console.error('获取编辑页上下文失败:', e)
          }
        }
        if (!isEdit.value) {
          applyInitialPlanForCreate(route.query, props.plan_id)
          await ensurePlanOptionVisible(badcase.plan)
          applyDefaultAssigneeOnCreate(badcase, user.value, { isEdit: false })
        } else {
          await ensurePlanOptionVisible(badcase.plan)
        }

        // 如果是 show_diff 场景：过滤掉已采纳的字段（当前 DB 值已等于 diff 的 new 值）
        const queryForPrefill = route.query
        const showDiffModeForPrefill = props.show_diff || queryForPrefill.show_diff === 'true'
        const clearPendingModifyIfNotThisBadcase = () => {
          if (!showDiffModeForPrefill || !pendingDiff.value?.modifications) return
          const pd = pendingDiff.value
          const tid = pd.targetId != null ? String(pd.targetId).trim() : ''
          const cur = badcaseId.value ? String(badcaseId.value).trim() : ''
          const tgt = String(pd.target || '').toLowerCase().replace(/-/g, '_')
          const isBc = tgt === 'badcase' || tgt === 'bad_case' || tgt === ''
          if (!isBc || (isEdit.value && cur && tid && tid !== cur)) {
            clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
            pendingDiff.value = null
          }
        }
        clearPendingModifyIfNotThisBadcase()
        if (showDiffModeForPrefill && pendingDiff.value?.modifications) {
          const mods = pendingDiff.value.modifications
          for (const [field, data] of Object.entries(mods)) {
            if (String(field).startsWith('_')) continue
            const newVal = data?.new != null ? String(data.new).trim() : ''
            const oldVal = data?.old != null ? String(data.old).trim() : ''
            const curVal = badcase[field] != null ? String(badcase[field]).trim() : ''
            if (newVal && curVal === newVal && oldVal === newVal) {
              delete mods[field]
            }
          }
          const remaining = Object.keys(mods).filter(k => !String(k).startsWith('_'))
          if (remaining.length === 0) {
            clearPendingModifyDiffForDetail(
            snowflakeIdStr(props.project_id) || snowflakeIdStr(badcase.project_id)
          )
            pendingDiff.value = null
          }
        }
        const reconcilePendingOldFromLoadedBadcase = () => {
          if (!pendingDiff.value?.modifications) return
          for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
            if (String(field).startsWith('_')) continue
            if (!badcase.hasOwnProperty(field) || !data || typeof data !== 'object' || !('new' in data)) continue
            if (field !== 'status' && field !== 'title' && field !== 'case_category') continue
            const bv = badcase[field]
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
        reconcilePendingOldFromLoadedBadcase()
        if (showDiffModeForPrefill && pendingDiff.value?.modifications) {
          for (const [field, data] of Object.entries(pendingDiff.value.modifications)) {
            if (
              badcase.hasOwnProperty(field) &&
              data &&
              typeof data === 'object' &&
              'new' in data &&
              data.new !== undefined &&
              String(data.new).trim() !== ''
            ) {
              badcase[field] = data.new
            }
          }
        }
        normalizeBadcasePriorityForForm()
        normalizeBadcaseCaseCategoryForForm()
        if (isEdit.value && props.embedded) {
          const t0 = String(badcase.title || '').trim()
          if (t0) emit('titleLoaded', t0)
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

    onUnmounted(() => {
      window.removeEventListener('badcase-detail-refresh', onDetailModifyAdopted)
    })
    
    return {
      loading,
      saveLoading,
      isEdit,
      editContextCrumb,
      pageHeadline,
      badcase,
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
      showUserDropdown,
      leftSidebarHidden,
      showTerminal,
      showAIAssistant,
      goBackToProjectDetail,
      toggleUserDropdown,
      showNotifications,
      showHelp,
      showTeamManagement,
      showUserProfile,
      logout,
      setLayout,
      recentAssignees,
      availablePlans,
      filteredPlans,
      expandedPlans,
      getStatusText,
      formatBadcasePriorityLabel,
      saveBadcase,
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
      confirmFieldChange,
      cancelFieldChange,
      applyFieldChange,
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
      inlineDiffFields,
      isRightSidebarOpen,
      toggleRightSidebar
    }
  }
}
</script>

<style scoped>
.comment-input-subtitle {
  margin: 12px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #495057;
}

.comment-section {
  margin-top: 16px;
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

.badcase-detail-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f9fa;
}

/* 嵌入在 ProjectDetail：占满父容器，避免底部按钮被裁切 */
.badcase-detail-wrapper.is-embedded {
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

/* 顶部导航栏（对齐 ProjectDetail 的 top-bar 规格） */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e9ecef;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.top-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.top-bar--stacked {
  height: auto;
  padding: 0;
  flex-direction: column;
  align-items: stretch;
}

.top-bar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
}

.top-bar-row--primary {
  height: 60px;
}

.top-bar-row--secondary {
  height: 48px;
  border-top: 1px solid #f1f3f5;
}

.secondary-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.secondary-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

/* 顶部栏内容：与 ProjectDetail 对齐 */
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.logo:hover {
  opacity: 0.8;
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.star-icon {
  font-size: 12px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #333;
}

.breadcrumb-separator {
  color: #999;
}

.dropdown-arrow {
  font-size: 10px;
  color: #999;
  margin-left: 4px;
}

.breadcrumb-link {
  cursor: pointer;
}

.breadcrumb-link:hover {
  text-decoration: underline;
}

.edit-permission {
  font-size: 12px;
  color: #666;
  padding: 4px 8px;
  background: #f8f9fa;
  border-radius: 4px;
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

.top-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 布局按钮组样式（从 ProjectDetail 原样拷贝） */
.layout-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 16px;
}

.layout-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  position: relative;
}

.layout-btn:hover {
  background: transparent;
  transform: translateY(-1px);
}

.layout-btn.active {
  background: transparent;
  box-shadow: 0 0 0 1px #e2e8f0;
}

.layout-icon {
  width: 16px;
  height: 16px;
  background: #a0aec0;
  border-radius: 2px;
  position: relative;
}

/* 左对齐图标 - 左黑右灰 */
.layout-icon.left-aligned {
  background: #a0aec0;
}

.layout-icon.left-aligned::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 8px;
  height: 16px;
  background: #000000;
  border-radius: 1px;
}

/* 底部对齐图标 - 上黑下灰 */
.layout-icon.bottom-aligned {
  background: #a0aec0;
}

.layout-icon.bottom-aligned::before {
  content: '';
  position: absolute;
  left: 0;
  bottom: 0;
  width: 16px;
  height: 8px;
  background: #000000;
  border-radius: 1px;
}

/* 右对齐图标 - 左灰右黑 */
.layout-icon.right-aligned {
  background: #a0aec0;
}

.layout-icon.right-aligned::before {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  width: 8px;
  height: 16px;
  background: #000000;
  border-radius: 1px;
}

/* 用户下拉菜单样式（从 ProjectDetail 原样拷贝） */
.user-dropdown {
  position: relative;
  cursor: pointer;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: all 0.2s ease;
  border: 2px solid transparent;
}

.user-avatar:hover {
  background: #e0e0e0;
  border-color: #007bff;
}

.user-menu {
  position: absolute;
  top: 100%;
  right: 0;
  width: 240px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid #e0e0e0;
  z-index: 1000;
  margin-top: 8px;
  overflow: hidden;
}

.user-info {
  padding: 16px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.user-email {
  font-size: 12px;
  color: #666;
}

.menu-divider {
  height: 1px;
  background: #e0e0e0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.15s ease;
  border-bottom: 1px solid #f0f0f0;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-item:hover {
  background: #f8f9fa;
}

.menu-icon {
  font-size: 16px;
  opacity: 0.8;
}

.menu-text {
  font-size: 14px;
  color: #333;
  font-weight: 400;
}

.logout-item {
  color: #dc3545;
}

.logout-item:hover {
  background: #fff5f5;
}

.logout-item .menu-icon {
  color: #dc3545;
}

.logout-item .menu-text {
  color: #dc3545;
  font-weight: 500;
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

.count-badge.badcase {
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

/* 答案区域 */
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

/* 正确答案区域 */
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

.diff-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.diff-content--stacked {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
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

/* 右侧边栏：默认收起；展开后固定宽度 */
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

/* 内联 diff 面板样式（用于下拉框等） */
.field-diff-panel-inline {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 2px solid #f59e0b;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  display: inline-flex;
  align-items: center;
}

.field-diff-panel-inline .diff-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.field-diff-panel-inline .diff-old {
  color: #991b1b;
  font-weight: 500;
  text-decoration: line-through;
}

.field-diff-panel-inline .diff-new {
  color: #166534;
  font-weight: 600;
}

.field-diff-panel-inline .diff-arrow {
  color: #9ca3af;
  font-weight: bold;
}

.field-diff-panel-inline .diff-actions {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.btn-confirm-sm,
.btn-cancel-sm {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-confirm-sm {
  background: #10b981;
  color: white;
}

.btn-confirm-sm:hover {
  background: #059669;
  transform: scale(1.1);
}

.btn-cancel-sm {
  background: #ef4444;
  color: white;
}

.btn-cancel-sm:hover {
  background: #dc2626;
  transform: scale(1.1);
}
</style> 
