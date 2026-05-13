<template>
  <!-- 全局命令历史弹框：覆盖所有面板，出现在 top-bar 下方 -->
  <Teleport to="body">
    <div v-if="showGlobalCmdHistory" class="etw-global-cmd-history">
      <div class="etw-global-cmd-panel">
        <div class="etw-global-cmd-search-row">
          <span class="etw-global-cmd-icon codicon codicon-search"></span>
          <input
            :ref="el => { globalCmdSearchInput = el }"
            v-model="globalCmdSearchText"
            class="etw-global-cmd-search"
            :placeholder="t('embeddedTerminal.searchPlaceholder')"
            @keydown="onGlobalCmdKeydown"
          />
        </div>
        <div class="etw-global-cmd-divider"></div>
        <div ref="globalCmdListRef" class="etw-global-cmd-list">
          <div
            v-for="(cmd, idx) in filteredGlobalCmdHistory"
            :key="idx"
            class="etw-global-cmd-item"
            :class="{ 'etw-global-cmd-item--selected': idx === globalCmdSelected }"
            @click="pickGlobalCmd(idx)"
            @mouseenter="globalCmdSelected = idx"
          >
            <span class="etw-global-cmd-num">{{ cmd.index }}</span>
            <span class="etw-global-cmd-text">{{ cmd.text }}</span>
          </div>
          <div v-if="!filteredGlobalCmdHistory.length" class="etw-global-cmd-empty">
            {{ t('embeddedTerminal.noCommandHistory') }}
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <ProjectWorkspaceShell
    :projectName="projectName || t('project.detailTitle')"
    :currentUser="currentUser"
    :leftSidebarHidden="leftSidebarHidden"
    :showTerminal="showTerminal"
    :showAIAssistant="showAIAssistant"
    :showUserDropdown="showUserDropdown"
    @goToDashboard="goToDashboard"
    @setLayout="setLayout"
    @toggleUserDropdown="toggleUserDropdown"
    @showNotifications="showNotifications"
    @showHelp="openHelpWorkbenchTab"
    @openSettings="openAppSettings"
    @logout="logout"
    @showProjectManagement="openProjectManagementWorkbenchTab"
  >
    <!-- 窄条导航栏和主内容容器 -->
    <div class="narrow-nav-and-main">
      <!-- 窄条导航栏（始终显示） -->
      <NarrowNavBar
        @return-to-plans="handleReturnToPlans"
        @open-search="handleOpenGlobalSearch"
        @open-settings="openAppSettings"
        @open-archive="handleOpenArchive"
        @open-plugins="activeLeftPanel='plugins'"
      />

      <div class="main-container">
      <!-- 左侧导航栏 -->
      <div class="left-sidebar" :class="{ 'collapsed': planCollapsed }" v-show="!leftSidebarHidden" :style="{ width: !planCollapsed ? leftSidebarWidth + 'px' : '60px' }">
        <!-- 拖拽手柄 -->
        <div v-show="!planCollapsed" class="drag-handle-left" @mousedown="startDragLeftSidebar"></div>

        <LeftSidebarHost
          :activeLeftPanel="activeLeftPanel"
          :projectId="projectId"
          :currentUser="currentUser"
          :planCollapsed="planCollapsed"
          :loading="loading"
          :activePlans="activePlans"
          :archivedPlans="archivedPlans"
          :selectedPlan="selectedPlan"
          :expandedPlans="expandedPlans"
          :hoveredPlan="hoveredPlan"
          :contextMenu="contextMenu"
          :contextMenuDragActive="contextMenuDragActive"
          :getPlanIcon="getPlanIcon"
          :formatDate="formatDate"
          :showCreatePlanModal="showCreatePlanModal"
          :selectPlan="selectPlan"
          :showPlanActions="showPlanActions"
          :hidePlanActions="hidePlanActions"
          :togglePlanExpansion="togglePlanExpansion"
          :showContextMenu="showContextMenu"
          :onContextMenuDragStart="onContextMenuDragStart"
          :createSubPlan="createSubPlan"
          :createSiblingPlan="createSiblingPlan"
          :editPlan="editPlan"
          :archivePlan="archivePlan"
          :deletePlan="deletePlan"
          :pinPlan="pinPlan"
          :pendingDeletePlanId="pendingDeletePlanId"
          :confirmDelete="confirmDelete"
          :cancelModify="cancelModify"
          @closeSearch="activeLeftPanel='plans'"
          @selectSearchResult="handleSearchResultSelect"
          @pluginAction="handlePluginAction"
        />
      </div>

      <!-- 主内容区域 -->
      <div class="main-content" :class="{ 
        'full-width': leftSidebarHidden,
        'with-right-sidebar': showAIAssistant
      }" :style="{ 
        width: showAIAssistant ? 'calc(100% - ' + rightSidebarWidth + 'px)' : '100%'
      }">
        <div v-if="workbenchTabs.length" class="workbench-tabbar">
          <div
            ref="workbenchTabsStripRef"
            class="workbench-tabs-strip"
            :class="{ dragging: workbenchTabStripDraggingUI }"
            @mousedown="onWorkbenchTabStripMouseDown"
            @wheel="onWorkbenchTabStripWheel"
          >
            <button
              v-for="tab in workbenchTabs"
              :key="tab.id"
              type="button"
              class="workbench-tab"
              :class="{ active: tab.id === activeWorkbenchTabId }"
              @click="onWorkbenchTabButtonClick(tab.id)"
            >
              <SelectableTitleTip class="workbench-tab-title" :text="tab.title">
                {{ tab.title }}
              </SelectableTitleTip>
              <span class="workbench-tab-close" @click.stop="closeWorkbenchTab(tab.id, $event)">×</span>
            </button>
          </div>
          <div ref="workbenchMenuRef" class="workbench-tabbar-trailing">

            <button
              type="button"
              class="workbench-more-btn"
              :title="t('common.more')"
              @click.stop="toggleWorkbenchTabMenu"
            >
              ⋯
            </button>
            <div v-if="showWorkbenchTabMenu" class="workbench-tab-dropdown" @click.stop>
              <button
                v-for="tab in workbenchTabsForMoreMenu"
                :key="'menu-' + tab.id"
                type="button"
                class="workbench-dropdown-item"
                :class="{ active: tab.id === activeWorkbenchTabId }"
                :title="tab.title"
                @click="onWorkbenchMenuSelectTab(tab.id)"
              >
                {{ tab.title }}
              </button>
              <div class="workbench-dropdown-sep" />
              <button type="button" class="workbench-dropdown-item danger" @click="closeAllWorkbenchTabs">
                {{ t('common.closeAll') }}
              </button>
            </div>
          </div>
        </div>
        <div class="main-content-body">
        
        <!-- keep-alive：列表/详情切换时复用实例，减轻 Tab 来回切换的重复挂载与卡顿 -->
        <!-- 必须同时有组件引用：避免 showMainEditor 与 ref 短暂不一致时 :is="null" 触发 patch 报错 Cannot read properties of null (reading 'type') -->
        <keep-alive v-if="showMainEditor && mainEditorComponent" :max="16">
          <component
            :is="mainEditorComponent"
            :key="mainEditorCacheKey"
            :project_id="projectId"
            :plan_id="mainEditorPlanId"
            :card_id="mainEditorCardId"
            :id="mainEditorItemId"
            :edit="mainEditorEdit"
            :show_diff="mainEditorShowDiff"
            :embedded="true"
            @close="closeMainEditor"
            @titleLoaded="handleTitleLoaded"
          />
        </keep-alive>
        <component
          :is="AppSettingsPanel"
          v-else-if="isSettingsWorkbenchTab"
          :user="currentUser"
          :project-id="projectId"
          :initial-pane="appSettingsInitialPane"
          :visible="isSettingsWorkbenchTab"
          @close="closeAppSettingsWorkbenchTab"
        />
        <component
          :is="TerminalSettingsWorkbenchPanel"
          v-else-if="isTerminalSettingsWorkbenchTab"
          :visible="isTerminalSettingsWorkbenchTab"
        />
        <component
          :is="ProjectHelpPanel"
          v-else-if="isHelpWorkbenchTab"
          :visible="isHelpWorkbenchTab"
        />
        <component
          :is="WorkflowNotificationsPanel"
          v-else-if="isNotificationsWorkbenchTab"
          :project-id="projectId"
          :visible="isNotificationsWorkbenchTab"
        />
        <component
          :is="ProjectManage"
          v-else-if="isProjectManagementWorkbenchTab"
          :visible="isProjectManagementWorkbenchTab"
          @project-selected="handleProjectSelected"
        />
        <keep-alive v-else :max="16">
          <BadcaseListPanel
            v-if="currentTypeFilter === 'badcase'"
            :key="'badcase-' + selectedPlan"
            :project_id="projectId"
            :plan_id="selectedPlan"
            :generateBreadcrumb="() => getTypeListBreadcrumb('badcase', activeWorkbenchTab?.meta?.cardTitle)"
            :showLongBreadcrumb="true"
            :currentPlanType="'badcase'"
            :totalBadcases="totalBadcases"
            :page="badcasePage"
            :page-size="badcasePerPage"
            @update:page="onWorkbenchListPage"
            :refreshBadcases="() => fetchBadcasesByPlan(selectedPlan)"
            :filteredBadcases="filteredBadcases"
            :badcaseLoading="badcaseLoading"
            :selectedTasks="selectedTasks"
            :selectAll="selectAll"
            :toggleSelectAll="toggleSelectAll"
            :toggleTaskSelection="toggleTaskSelection"
            :editBadcase="editBadcase"
            :searchText="searchText"
            :selectedAssignee="selectedAssignee"
            :selectedStatus="selectedStatus"
            :projectMembers="projectMembers"
            :applyFilters="applyFilters"
            :pendingModifications="pendingModifications"
            :isLastInConsecutiveGroup="isLastInConsecutiveGroup"
            :getConsecutiveGroupSize="getConsecutiveGroupSize"
            :confirmModify="confirmModify"
            :cancelModify="cancelModify"
            :confirmDelete="confirmDelete"
            :isLastInConsecutiveDeleteGroup="isLastInConsecutiveDeleteGroup"
            :getConsecutiveDeleteGroupSize="getConsecutiveDeleteGroupSize"
            :confirmConsecutiveDeleteGroup="confirmConsecutiveDeleteGroup"
            :cancelConsecutiveDeleteGroup="cancelConsecutiveDeleteGroup"
            :getBadcaseStatusText="getBadcaseStatusText"
            :getAssigneeDisplayText="getAssigneeDisplayText"
            :pendingCreates="pendingCreatesForCurrentView"
            :confirmCreate="confirmCreate"
            :cancelCreate="cancelCreate"
            :isLastInCreateCluster="isLastInCreateCluster"
            :getCreateClusterSize="getCreateClusterSize"
            :confirmConsecutiveCreateGroup="confirmConsecutiveCreateGroup"
            :cancelConsecutiveCreateGroup="cancelConsecutiveCreateGroup"
            @openCreate="handleOpenCreate"
          />
          <BugListPanel
            v-else-if="currentTypeFilter === 'bug'"
            :key="'bug-' + selectedPlan"
            :project_id="projectId"
            :plan_id="selectedPlan"
            :generateBreadcrumb="() => getTypeListBreadcrumb('bug', activeWorkbenchTab?.meta?.cardTitle)"
            :showLongBreadcrumb="true"
            :currentPlanType="'bug'"
            :totalBadcases="totalBadcases"
            :page="badcasePage"
            :page-size="badcasePerPage"
            @update:page="onWorkbenchListPage"
            :refreshBadcases="() => fetchBadcasesByPlan(selectedPlan, 1, activeWorkbenchTab?.meta?.cardId)"
            :filteredBadcases="filteredBadcases"
            :badcaseLoading="badcaseLoading"
            :selectedTasks="selectedTasks"
            :selectAll="selectAll"
            :toggleSelectAll="toggleSelectAll"
            :toggleTaskSelection="toggleTaskSelection"
            :editBadcase="editBadcase"
            :searchText="searchText"
            :selectedAssignee="selectedAssignee"
            :selectedStatus="selectedStatus"
            :projectMembers="projectMembers"
            :applyFilters="applyFilters"
            :pendingModifications="pendingModifications"
            :isLastInConsecutiveGroup="isLastInConsecutiveGroup"
            :getConsecutiveGroupSize="getConsecutiveGroupSize"
            :confirmModify="confirmModify"
            :cancelModify="cancelModify"
            :confirmDelete="confirmDelete"
            :isLastInConsecutiveDeleteGroup="isLastInConsecutiveDeleteGroup"
            :getConsecutiveDeleteGroupSize="getConsecutiveDeleteGroupSize"
            :confirmConsecutiveDeleteGroup="confirmConsecutiveDeleteGroup"
            :cancelConsecutiveDeleteGroup="cancelConsecutiveDeleteGroup"
            :getBadcaseStatusText="getBadcaseStatusText"
            :getAssigneeDisplayText="getAssigneeDisplayText"
            :pendingCreates="pendingCreatesForCurrentView"
            :confirmCreate="confirmCreate"
            :cancelCreate="cancelCreate"
            :isLastInCreateCluster="isLastInCreateCluster"
            :getCreateClusterSize="getCreateClusterSize"
            :confirmConsecutiveCreateGroup="confirmConsecutiveCreateGroup"
            :cancelConsecutiveCreateGroup="cancelConsecutiveCreateGroup"
            @openCreate="handleOpenCreate"
          />
          <TestCaseListPanel
            v-else-if="currentTypeFilter === 'testcase'"
            :key="'testcase-' + selectedPlan"
            :project_id="projectId"
            :plan_id="selectedPlan"
            :generateBreadcrumb="() => getTypeListBreadcrumb('testcase', activeWorkbenchTab?.meta?.cardTitle)"
            :showLongBreadcrumb="true"
            :currentPlanType="'test_case'"
            :totalBadcases="totalBadcases"
            :page="badcasePage"
            :page-size="badcasePerPage"
            @update:page="onWorkbenchListPage"
            :refreshBadcases="() => fetchBadcasesByPlan(selectedPlan, 1, activeWorkbenchTab?.meta?.cardId)"
            :filteredBadcases="filteredBadcases"
            :badcaseLoading="badcaseLoading"
            :selectedTasks="selectedTasks"
            :selectAll="selectAll"
            :toggleSelectAll="toggleSelectAll"
            :toggleTaskSelection="toggleTaskSelection"
            :editBadcase="editBadcase"
            :searchText="searchText"
            :selectedAssignee="selectedAssignee"
            :selectedStatus="selectedStatus"
            :projectMembers="projectMembers"
            :applyFilters="applyFilters"
            :pendingModifications="pendingModifications"
            :isLastInConsecutiveGroup="isLastInConsecutiveGroup"
            :getConsecutiveGroupSize="getConsecutiveGroupSize"
            :confirmModify="confirmModify"
            :cancelModify="cancelModify"
            :confirmDelete="confirmDelete"
            :isLastInConsecutiveDeleteGroup="isLastInConsecutiveDeleteGroup"
            :getConsecutiveDeleteGroupSize="getConsecutiveDeleteGroupSize"
            :confirmConsecutiveDeleteGroup="confirmConsecutiveDeleteGroup"
            :cancelConsecutiveDeleteGroup="cancelConsecutiveDeleteGroup"
            :getBadcaseStatusText="getBadcaseStatusText"
            :getAssigneeDisplayText="getAssigneeDisplayText"
            :pendingCreates="pendingCreatesForCurrentView"
            :confirmCreate="confirmCreate"
            :cancelCreate="cancelCreate"
            :isLastInCreateCluster="isLastInCreateCluster"
            :getCreateClusterSize="getCreateClusterSize"
            :confirmConsecutiveCreateGroup="confirmConsecutiveCreateGroup"
            :cancelConsecutiveCreateGroup="cancelConsecutiveCreateGroup"
            @openCreate="handleOpenCreate"
          />
          <CardPanel
            v-else
            :key="listPanelCacheKey"
            ref="cardPanelRef"
            v-model:searchText="searchText"
            :breadcrumb="projectName"
            :title="selectedBaselinePlanName || t('project.selectPlan')"
            :showHeader="true"
            :itemType="'card'"
            :items="filteredCards"
            :total="totalCards"
            :page="cardPage"
            :page-size="cardPerPage"
            :loading="cardLoading"
            :selectedItems="selectedTasks"
            :selectAll="selectAll"
            :toggleSelectAll="toggleSelectAll"
            :toggleTaskSelection="toggleTaskSelection"
            :editItem="editCard"
            :onQuickCreate="handleQuickCreate"
            :onQuickUpdate="handleQuickUpdate"
            :pendingModifications="pendingModifications"
            :confirmModify="confirmModify"
            :cancelModify="cancelModify"
            :confirmDelete="confirmDelete"
            :hasDetailFieldModifications="hasDetailFieldModifications"
            :toggleDetailExpand="toggleDetailExpand"
            :expandedDetailRows="expandedDetailRows"
            :isLastInConsecutiveGroup="isLastInConsecutiveCardGroup"
            :getConsecutiveGroupSize="getConsecutiveCardGroupSize"
            :isLastInConsecutiveCardDeleteGroup="isLastInConsecutiveCardDeleteGroup"
            :getConsecutiveCardDeleteGroupSize="getConsecutiveCardDeleteGroupSize"
            :confirmConsecutiveCardDeleteGroup="confirmConsecutiveCardDeleteGroup"
            :cancelConsecutiveCardDeleteGroup="cancelConsecutiveCardDeleteGroup"
            :pendingCreates="pendingCreatesForCurrentView"
            :confirmCreate="confirmCreate"
            :cancelCreate="cancelCreate"
            :isLastInCreateCluster="isLastInCreateCluster"
            :getCreateClusterSize="getCreateClusterSize"
            :confirmConsecutiveCreateGroup="confirmConsecutiveCreateGroup"
            :cancelConsecutiveCreateGroup="cancelConsecutiveCreateGroup"
            @openCreate="handleOpenCreate"
            @openTypeList="handleOpenTypeList"
            @refresh="handleCardPanelRefresh"
            @update:page="onCardListPage"
            @search="onCardSearchSubmit"
          />
        </keep-alive>
        </div>
        
        <!-- 底部Terminal和Output区域 -->
        <div v-if="showTerminal" class="bottom-panel" :class="{
          'with-left-sidebar': !leftSidebarHidden && !planCollapsed,
          'with-collapsed-sidebar': !leftSidebarHidden && planCollapsed
        }" :style="{ 
          height: bottomPanelHeight + 'px',
          left: (leftSidebarHidden ? 48 : (!planCollapsed ? 48 + leftSidebarWidth : 108)) + 'px',
          right: showAIAssistant ? rightSidebarWidth + 'px' : '0px',
          zIndex: 100
        }">
          <!-- 拖拽手柄 -->
          <div class="drag-handle-horizontal" @mousedown="startDragBottomPanel"></div>
          
          <div class="panel-content">
            <EmbeddedTerminalWorkspace
              ref="embeddedTerminalWorkspaceRef"
              :key="'embedded-terminal-workspace-v3'"
              :working-directory="currentWorkingDir"
              :project-id="projectId"
            />
          </div>
        </div>
      </div>
    </div><!-- 关闭 narrow-nav-and-main -->

    <!-- 右侧AI助手面板 -->
      <div v-if="showAIAssistant" class="right-sidebar ai-assistant-panel" :style="{ width: rightSidebarWidth + 'px' }">
        <!-- 拖拽手柄 -->
        <div class="drag-handle" @mousedown="startDragRightSidebar"></div>
        
        <!-- 面板头部 -->
        <div class="ai-panel-header">
          <div class="ai-panel-tabs">
            <div v-if="currentSession && sessions[currentSession]" class="ai-tab active">
              <span class="ai-tab-title" :title="sessions[currentSession].title || t('common.unnamedSession')">{{
                sessions[currentSession].title || t('common.unnamedSession')
              }}</span>
              <button class="tab-close" @click.stop="closeSessionTab(currentSession)">×</button>
            </div>
            <div v-else-if="currentSession" class="ai-tab active">
              <span class="ai-tab-title">{{ t('common.sessionLoading') }}</span>
            </div>
          </div>
          <div class="ai-panel-actions">
            <button class="ai-action-btn" :title="t('common.newSession')" @click="createNewSession">+</button>
            <div ref="aiHistoryDropdownRef" class="dropdown">
              <button class="ai-action-btn" :title="t('common.sessionHistory')" @click="toggleHistory">🕐</button>
              <div class="dropdown-menu history-menu" :class="{ 'show': showHistory }">
                <div v-if="historyLoading" class="dropdown-item loading">{{ t('common.loading') }}</div>
                <div v-else-if="sessionHistory.length === 0" class="dropdown-item empty">{{ t('common.noHistorySessions') }}</div>
                <template v-else>
                  <div 
                    v-for="session in sessionHistory" 
                    :key="session.id" 
                    class="dropdown-item history-item"
                    :class="{ 'active': currentSession === session.id }"
                    @click="switchSession(session.id)"
                  >
                    <div class="history-title">{{ session.title || t('common.unnamedSession') }}</div>
                    <div class="history-time">{{ new Date(session.created_at).toLocaleString() }}</div>
                  </div>
                </template>
              </div>
            </div>
            <div ref="aiMoreDropdownRef" class="dropdown">
              <button class="ai-action-btn dropdown-toggle" :title="t('common.moreOptions')" @click="toggleDropdown">⋯</button>
              <div class="dropdown-menu" :class="{ 'show': showDropdown }">
                <a class="dropdown-item" href="#" @click="closeSession">{{ t('common.closeSession') }}</a>
                <a class="dropdown-item" href="#" @click="exportChat">{{ t('common.exportChat') }}</a>
                <a class="dropdown-item" href="#" @click="clearMessages">{{ t('common.clearMessages') }}</a>
              </div>
            </div>
          </div>
        </div>
        <!-- 聊天面板区域 -->
        <div class="chat-panel-container">
          <SimpleChatPanel
            v-if="currentSession"
            :sessionId="currentSession"
            :projectId="Number(projectId)"
            :project-display-name="projectName || ''"
            @title-updated="handleTitleUpdated"
          />
          <div v-else class="chat-empty-placeholder">
            <p>{{ t('common.chatEmptyHint') }}</p>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 基线管理模态框 -->
    <div v-show="showBaselineManagementModal" class="modal-overlay" @click="closeBaselineManagementModal">
      <div class="modal-content baseline-modal" @click.stop>
        <div class="modal-header">
          <h3>{{ t('project.baselineTitle') }}</h3>
          <button class="close-btn" @click="closeBaselineManagementModal">✕</button>
        </div>
        
        <div class="modal-body">
          <div class="baseline-layout">
            <!-- 左侧：BadCase计划列表 -->
            <div class="baseline-left-panel">
              <div class="panel-header">
                <h4>{{ t('project.baselinePlanList') }}</h4>
              </div>
              <div class="plan-list">
                <div 
                  v-for="plan in projectPlans" 
                  :key="plan.id"
                  class="plan-item"
                  :class="{ 
                    'active': selectedBaselinePlan === plan.id,
                    'parent-plan': plan.children && plan.children.length > 0,
                    'child-plan': plan.parent_id
                  }"
                >
                  <div class="plan-content">
                    <div class="plan-header" @click="selectBaselinePlan(plan.id)">
                      <!-- 折叠展开箭头 -->
                      <span 
                        v-if="plan.children && plan.children.length > 0"
                        class="expand-arrow"
                        :class="{ 'expanded': !plan.collapsed }"
                        @click.stop="toggleBaselinePlanExpansion(plan.id)"
                      >
                        ▶
                      </span>
                      <span v-else class="expand-placeholder"></span>
                      <span class="plan-icon">{{ plan.children && plan.children.length > 0 ? '📁' : '📋' }}</span>
                      <span class="plan-name">{{ plan.name }}</span>
                      <span class="plan-count">{{ plan.badcase_count || 0 }}</span>
                    </div>
                    <!-- 子计划 -->
                    <div v-if="plan.children && plan.children.length > 0 && !plan.collapsed" class="sub-plans">
                      <div 
                        v-for="subPlan in plan.children" 
                        :key="subPlan.id"
                        class="sub-plan-item"
                        :class="{ 'active': selectedBaselinePlan === subPlan.id }"
                        @click="selectBaselinePlan(subPlan.id)"
                      >
                        <span class="sub-plan-icon">📋</span>
                        <span class="sub-plan-name">{{ subPlan.name }}</span>
                        <span class="sub-plan-count">{{ subPlan.badcase_count || 0 }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 右侧：BadCase列表和基线管理 -->
            <div class="baseline-right-panel">
              <div class="panel-header">
                <h4>{{ selectedBaselinePlanName || t('project.selectPlan') }}</h4>
                <div class="baseline-actions">
                  <button class="baseline-btn" @click="createNewBaseline" :disabled="!selectedBaselinePlan || selectedBadcases.length === 0">
                    {{ t('project.createBaseline') }}
                  </button>
                  <button class="baseline-btn" @click="compareBaselines" :disabled="!hasBaselines">
                    {{ t('project.compareBaseline') }}
                  </button>
                </div>
              </div>
              
              <div class="badcase-section">
                <div class="section-header">
                  <span>{{ t('project.notInBaseline') }}</span>
                  <span class="count">({{ availableBadcases.length }})</span>
                </div>
                
                <div class="badcase-list">
                  <div v-if="availableBadcases.length === 0" class="empty-state">
                    <div class="empty-icon">📋</div>
                    <div class="empty-text">{{ t('project.noBadcaseInPlan') }}</div>
                  </div>
                  <div 
                    v-else
                    v-for="badcase in availableBadcases" 
                    :key="badcase.id"
                    class="badcase-item"
                    :class="{ 'selected': selectedBadcases.includes(badcase.id) }"
                    @click="toggleBadcaseSelection(badcase.id)"
                  >
                    <div class="badcase-checkbox">
                      <input 
                        type="checkbox" 
                        :checked="selectedBadcases.includes(badcase.id)"
                        @change="toggleBadcaseSelection(badcase.id)"
                      />
                    </div>
                    <div class="badcase-info">
                      <div class="badcase-title">{{ badcase.title }}</div>
                      <div class="badcase-meta">
                        <span class="status-badge" :class="badcase.status">{{ getBadcaseStatusText(badcase.status) }}</span>
                        <span class="assignee">{{ getAssigneeDisplayText(badcase.assignee) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 基线列表 -->
              <div class="baseline-section">
                <div class="section-header">
                  <span>{{ t('project.baselineList') }}</span>
                  <span class="count">({{ baselines.length }})</span>
                </div>
                
                <div class="baseline-list">
                  <div v-if="baselines.length === 0" class="empty-state">
                    <div class="empty-icon">📊</div>
                    <div class="empty-text">{{ t('project.noBaselines') }}</div>
                  </div>
                  <div 
                    v-else
                    v-for="baseline in baselines" 
                    :key="baseline.id"
                    class="baseline-item"
                    :class="{ 'active': selectedBaseline === baseline.id }"
                    @click="selectBaseline(baseline.id)"
                  >
                    <div class="baseline-info">
                      <div class="baseline-name">{{ baseline.name }}</div>
                      <div class="baseline-meta">
                        <span class="version">v{{ baseline.version }}</span>
                        <span class="date">{{ new Date(baseline.created_at).toLocaleDateString() }}</span>
                        <span class="count">{{ baseline.badcase_count }}{{ t('project.badcaseCountUnit') }}</span>
                      </div>
                    </div>
                    <div class="baseline-actions">
                      <button class="action-btn" @click.stop="viewBaseline(baseline.id)">{{ t('common.view') }}</button>
                      <button class="action-btn delete" @click.stop="deleteBaseline(baseline.id)">{{ t('common.delete') }}</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    

    

    
    <!-- 新建计划模态框 -->
    <div v-if="showCreateModal" class="modal-overlay" @click="closeCreateModal">
      <div class="plan-modal-content" @click.stop>
        <div class="plan-modal-header">
          <h3>{{ getModalTitle() }}</h3>
          <button class="plan-modal-close" @click="closeCreateModal">✕</button>
        </div>
        
        <div class="plan-modal-body">
          <div class="plan-form-row">
            <div class="plan-form-item">
              <label class="plan-form-label required">标题</label>
              <input 
                type="text" 
                v-model="newPlan.name" 
                class="plan-form-input"
                maxlength="50"
              />
            </div>
          </div>
          
          <div class="plan-form-row plan-form-row-2col">
            <div class="plan-form-item">
              <label class="plan-form-label required">开始时间</label>
              <input type="date" v-model="newPlan.startDate" class="plan-form-input" placeholder=" " />
            </div>
            <div class="plan-form-item">
              <label class="plan-form-label required">结束时间</label>
              <input type="date" v-model="newPlan.endDate" class="plan-form-input" placeholder=" " />
            </div>
          </div>
          
          <div class="plan-form-row">
            <div class="plan-form-item">
              <label class="plan-form-label">{{ t('project.parentPlan') }}</label>
              <select v-model="newPlan.parentId" class="plan-form-select">
                <option value="">{{ t('project.selectParentPlaceholder') }}</option>
                <option v-for="plan in availableParentPlans" :key="plan.id" :value="plan.id">
                  {{ plan.name }}
                </option>
              </select>
            </div>
          </div>
          
          <div class="plan-form-row">
            <div class="plan-form-item">
              <label class="plan-form-label">{{ t('common.description') }}</label>
              <textarea 
                v-model="newPlan.description" 
                class="plan-form-textarea"
                maxlength="500"
              ></textarea>
            </div>
          </div>
        </div>
        
        <div class="plan-modal-footer">
          <button class="plan-btn plan-btn-default" @click="createPlanAndContinue" :disabled="!isFormValid">
            继续添加
          </button>
          <div class="plan-modal-footer-right">
            <button class="plan-btn plan-btn-cancel" @click="closeCreateModal">{{ t('prefs.cancel') }}</button>
            <button class="plan-btn plan-btn-primary" @click="createPlan" :disabled="!isFormValid">
              {{ isEditingPlan ? t('common.update') : t('common.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 项目设置模态框 -->
    <div v-if="showProjectSettingsModal" class="modal-overlay" @click="closeConfigModals">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('project.projectSettings') }}</h3>
          <button class="close-btn" @click="closeConfigModals">×</button>
        </div>
        
        <div class="modal-body">
          <p>{{ t('common.devPlaceholder') }}</p>
        </div>
      </div>
    </div>
    
    <!-- 权限设置模态框 -->
    <div v-if="showPermissionSettingsModal" class="modal-overlay" @click="closeConfigModals">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('project.permissionSettings') }}</h3>
          <button class="close-btn" @click="closeConfigModals">×</button>
        </div>
        
        <div class="modal-body">
          <p>{{ t('common.devPlaceholder') }}</p>
        </div>
      </div>
    </div>

  </ProjectWorkspaceShell>
</template>

<script>
import { ref, reactive, onMounted, onUnmounted, computed, watch, nextTick, provide, shallowRef, markRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BACKEND_BASE_URL, getProjectPlans, getProjectDetail, createPlan as createPlanApi, updatePlan as updatePlanApi, deletePlan as deletePlanApi, pinPlan as pinPlanApi, getProjectBadcases, getProjectBugs, getProjectTestCases, getProjectCards, createCard, updateCard, updateBadcasePlan, getProjectMembers, getChatSessions, createChatSession, getChatSession, getBugDetail, getBadcaseDetail, getTestCaseDetail, getCardDetail, getPlanBaselines, createBaseline as apiCreateBaseline, getBaselineDetail, deleteBaseline as apiDeleteBaseline, deleteBadcase, deleteBug, deleteTestCase, deleteCard, clearChatMessageDeleteNavigation } from '../api.js'
import { getBadCaseStatusText } from '../constants/status.js'
import EmbeddedTerminalWorkspace from './EmbeddedTerminalWorkspace.vue'
import TerminalSettingsWorkbenchPanel from './TerminalSettingsWorkbenchPanel.vue'
import SimpleChatPanel from './SimpleChatPanel.vue'
import AppSettingsPanel from './AppSettingsPanel.vue'
import ProjectHelpPanel from './ProjectHelpPanel.vue'
import WorkflowNotificationsPanel from './WorkflowNotificationsPanel.vue'
import ProjectWorkspaceShell from './ProjectWorkspaceShell.vue'
import NarrowNavBar from './NarrowNavBar.vue'
import LeftSidebarHost from './left/LeftSidebarHost.vue'
import BadcaseListPanel from './panels/BadcaseListPanel.vue'
import BugListPanel from './panels/BugListPanel.vue'
import TestCaseListPanel from './panels/TestCaseListPanel.vue'
import CardPanel from './panels/CardPanel.vue'
import NewBadcase from './NewBadcase.vue'
import NewBug from './NewBug.vue'
import NewTestCase from './NewTestCase.vue'
import ProjectManage from './ProjectManage.vue'
import userStore from '../store/user.js'
import { persistStableCreatedId, getStableCreatedId } from '../utils/createPreviewKeys.js'
import { useLocalGoProxyStatus } from '../composables/useLocalGoProxyStatus'
import SelectableTitleTip from './SelectableTitleTip.vue'

// 在浏览器环境中，这些Node.js模块可能不可用，需要处理
let os, path
try {
  os = require('os')
  path = require('path')
} catch (e) {
  // 浏览器环境，使用模拟实现
  os = {
    homedir: () => '/Users/v_huxiong'
  }
  path = {
    join: (...args) => args.join('/'),
    isAbsolute: (p) => p.startsWith('/')
  }
}

export default {
  name: 'ProjectDetail',
  components: {
    ProjectWorkspaceShell,
    LeftSidebarHost,
    BadcaseListPanel,
    BugListPanel,
    TestCaseListPanel,
    CardPanel,
    EmbeddedTerminalWorkspace,
    TerminalSettingsWorkbenchPanel,
    SimpleChatPanel,
    NarrowNavBar,
    SelectableTitleTip
  },
  setup() {
    const router = useRouter()
    const route = useRoute()
    const { t } = useI18n()

    // 项目信息
    const projectName = ref('')
    const projectId = ref(null)
    // 嵌入式终端 cwd：非空则传给 go-local-proxy；空则由代理用其**启动时的当前目录**（与你在哪开的 PS 一致）
    const currentWorkingDir = ref('')
    // 搜索和过滤
    const planSearchText = ref('')
    const showOnlyMine = ref(false)
    const includeSubPlans = ref(false)

    // 新增搜索和筛选变量
    const searchText = ref('')
    const selectedAssignee = ref('')
    const selectedStatus = ref('')
    const projectMembers = ref([])


    // 展开状态
    const expandedSections = reactive({
      inProgress: true,
      archived: false
    })


    // 选择状态
    const selectedPlan = ref(null)
    const highlightBugId = ref(null) // 用于高亮显示的bug ID
    const urlContentType = ref(null) // URL参数传递的内容类型，优先级高于计划类型
    const currentTypeFilter = ref('') // 当前类型过滤器，用于显示对应类型的面板
    const currentPlan = computed(() => {
      if (!selectedPlan.value) {
        return null
      }
      
      const findPlan = (plans, id) => {
        for (const p of plans) {
          if (p.id == id) return p
          if (p.children && p.children.length > 0) {
            const found = findPlan(p.children, id)
            if (found) return found
          }
        }
        return null
      }
      return findPlan(projectPlans.value, selectedPlan.value)
    })
    
    const currentPlanType = computed(() => {
      // 以后类型以“卡片类型/列表上下文”为主。
      // 这里仅保留 URL 传递的内容类型（多 Tab/导航场景），否则默认 badcase。
      if (urlContentType.value) {
        console.log('🐛 currentPlanType: 使用URL参数类型:', urlContentType.value)
        return urlContentType.value
      }
      return 'badcase'
    })

    /** 列表区 keep-alive 缓存键：同一计划/类型视图切换回来时可复用实例 */
    const listPanelCacheKey = computed(
      () =>
        'list-' +
        currentPlanType.value +
        '-' +
        String(selectedPlan.value ?? '') +
        '-' +
        (urlContentType.value || '')
    )

    const selectAll = ref(false)
    const selectedTasks = ref([])

    // 项目计划数据
    const projectPlans = ref([])
    const filteredPlans = ref([])
    const loading = ref(false)
    // 计划下测试用例数量（单独接口拉取，与列表一致，保证侧边栏显示正确）
    const planTestCaseCounts = ref({})

    // 悬停和上下文菜单状态
    const hoveredPlan = ref(null)
    const contextMenu = reactive({
      visible: false,
      planId: null,
      x: 0,
      y: 0
    })
    const contextMenuDragActive = ref(false)
    let contextMenuOutsideCloseCleanup = null
    const _contextMenuDrag = { startX: 0, startY: 0, origX: 0, origY: 0 }

    // 显示状态
    const planCollapsed = ref(false)

    // AI助手下拉菜单状态
    const showDropdown = ref(false)

    // Terminal命令输入栏状态
    const showTerminalInput = ref(false)

    // 会话管理
    const currentSession = ref(null)
    const sessions = ref({})
    const showHistory = ref(false)
    const sessionHistory = ref([])
    const historyLoading = ref(false)
    /** AI 面板：会话历史 / 更多菜单，点击外部关闭 */
    const aiHistoryDropdownRef = ref(null)
    const aiMoreDropdownRef = ref(null)
    let aiHistoryOutsideCleanup = null
    let aiMoreOutsideCleanup = null

    const showProjectSettingsModal = ref(false)
    const showPermissionSettingsModal = ref(false)
    const showBaselineManagementModal = ref(false)

    // 用户下拉菜单状态
    const showUserDropdown = ref(false)
    const appSettingsInitialPane = ref('account')
    /** 设置页：工作台 Tab id（与列表/详情并列） */
    const SETTINGS_WORKBENCH_TAB_ID = 'app-settings'
    /** 帮助页：工作台 Tab id */
    const HELP_WORKBENCH_TAB_ID = 'app-help'
    /** 通知收件箱：工作台 Tab id */
    const NOTIFICATIONS_WORKBENCH_TAB_ID = 'app-notifications'
    /** 嵌入式终端设置：与计划 Tab 并列于主内容区顶栏 */
    const TERMINAL_SETTINGS_WORKBENCH_TAB_ID = 'workbench-terminal-settings'
    const currentUser = ref(null)
    
    // 布局控制状态
    const showTerminal = ref(false)
    const showAIAssistant = ref(false)

    const terminalCtl = ref(null)
    const embeddedTerminalWorkspaceRef = ref(null)
    provide('terminalCtl', terminalCtl)

    const { localGoProxyOk, localGoProxyLastError, pingLocalGoProxy } = useLocalGoProxyStatus()
    provide('localGoProxyOk', localGoProxyOk)
    provide('localGoProxyLastError', localGoProxyLastError)
    provide('pingLocalGoProxy', pingLocalGoProxy)
    const chatComposerPreset = ref({ token: 0, text: '' })
    provide('chatComposerPreset', chatComposerPreset)

    const badcaseDraftPreset = ref({ token: 0, description: '' })
    provide('badcaseDraftPreset', badcaseDraftPreset)
    const bugDraftPreset = ref({ token: 0, description: '' })
    provide('bugDraftPreset', bugDraftPreset)
    const testcaseDraftPreset = ref({ token: 0, description: '' })
    provide('testcaseDraftPreset', testcaseDraftPreset)

    provide('openTerminalQuickEditor', () => {
      try {
        embeddedTerminalWorkspaceRef.value?.openQuickEditor?.()
      } catch (_) {
        /* ignore */
      }
    })

    provide('terminalCreateBadcaseFromSelection', () => {
      try {
        embeddedTerminalWorkspaceRef.value?.createBadcaseFromTerminal?.()
      } catch (_) {
        /* ignore */
      }
    })
    provide('terminalCreateBugFromSelection', () => {
      try {
        embeddedTerminalWorkspaceRef.value?.createBugFromTerminal?.()
      } catch (_) {
        /* ignore */
      }
    })
    provide('terminalCreateTestcaseFromSelection', () => {
      try {
        embeddedTerminalWorkspaceRef.value?.createTestcaseFromTerminal?.()
      } catch (_) {
        /* ignore */
      }
    })

    // ── 全局命令历史弹框（出现在 top-bar 下方，跨越所有面板） ──
    const showGlobalCmdHistory = ref(false)
    const globalCmdHistoryList = ref([])
    const globalCmdSearchText = ref('')
    const globalCmdSelected = ref(0)
    const globalCmdSearchInput = ref(null)
    const globalCmdListRef = ref(null)

    const indexedGlobalCmd = computed(() =>
      globalCmdHistoryList.value.map((text, i) => ({ text, index: i + 1 }))
    )
    const filteredGlobalCmdHistory = computed(() => {
      const q = globalCmdSearchText.value.trim().toLowerCase()
      if (!q) return indexedGlobalCmd.value
      return indexedGlobalCmd.value.filter((c) => c.text.toLowerCase().includes(q))
    })

    function openGlobalCmdHistory(csid) {
      if (!csid) return
      // 先强制关闭再打开，确保触发更新
      showGlobalCmdHistory.value = false
      nextTick(() => {
        // 从子组件获取命令历史
        const termCommandRegistry = globalThis.__termCommandRegistry__
        if (termCommandRegistry) {
          globalCmdHistoryList.value = termCommandRegistry.getCommands(csid) || []
        } else {
          globalCmdHistoryList.value = []
        }
        globalCmdSelected.value = 0
        globalCmdSearchText.value = ''
        showGlobalCmdHistory.value = true
        // setTimeout 确保 Teleport 完成后再聚焦
        setTimeout(() => {
          const input = document.querySelector('.etw-global-cmd-search')
          if (input) input.focus()
        }, 100)
      })
    }

    function scrollGlobalSelectedIntoView() {
      nextTick(() => {
        const el = globalCmdListRef.value?.querySelector('.etw-global-cmd-item--selected')
        el?.scrollIntoView({ block: 'nearest' })
      })
    }

    function onGlobalCmdKeydown(e) {
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        globalCmdSelected.value = Math.max(0, globalCmdSelected.value - 1)
        scrollGlobalSelectedIntoView()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        globalCmdSelected.value = Math.min(filteredGlobalCmdHistory.value.length - 1, globalCmdSelected.value + 1)
        scrollGlobalSelectedIntoView()
      } else if (e.key === 'Enter') {
        e.preventDefault()
        pickGlobalCmd(globalCmdSelected.value)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        showGlobalCmdHistory.value = false
      }
    }

    function pickGlobalCmd(idx) {
      const item = filteredGlobalCmdHistory.value[idx]
      if (!item) return
      showGlobalCmdHistory.value = false
      // 通过全局 terminal 实例写入命令（_activeTerm 定义在 termRegistry 上）
      const termRegistry = globalThis.__termRegistry__
      if (termRegistry) {
        const term = termRegistry._activeTerm
        if (term) {
          term.write(item.text + '\r')
        }
      }
    }

    provide('openGlobalCmdHistory', openGlobalCmdHistory)

    /** 打开项目时拉取最近长期记忆，随每条 ReAct 请求传入（不在每条对话后端 embed） */
    const projectLongMemoryContext = ref(null)
    provide('projectLongMemoryContext', projectLongMemoryContext)

    const loadProjectLongMemoryBootstrap = async () => {
      const pid = projectId.value
      if (pid == null || pid === '') {
        projectLongMemoryContext.value = null
        return
      }
      try {
        const r = await fetch(`${BACKEND_BASE_URL}/api/memory/retrieve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            query: '',
            project_id: Number(pid),
            mode: 'recent'
          })
        })
        const j = await r.json().catch(() => ({}))
        if (j?.code === 200 && j?.data) {
          const merged = String(j.data.merged || '').trim()
          const memories = j.data.memories || []
          if (merged || (Array.isArray(memories) && memories.length)) {
            projectLongMemoryContext.value = {
              long_memory_text: merged,
              long_memory_items: memories
            }
          } else {
            projectLongMemoryContext.value = null
          }
        } else {
          projectLongMemoryContext.value = null
        }
      } catch (e) {
        console.warn('[long-memory] project bootstrap failed', e)
        projectLongMemoryContext.value = null
      }
    }

    const leftSidebarHidden = ref(false)
    
    // 主区域挂载 Editor（用于替代 overlay 的一种模式）
    const showMainEditor = ref(false)
    /** 组件对象勿用深度 ref，避免 Vue 把组件选项做成深层响应式（控制台告警） */
    const mainEditorComponent = shallowRef(null)
    const mainEditorItemId = ref(null)
    const mainEditorEdit = ref(true)
    const mainEditorPlanId = ref(null)
    const mainEditorShowDiff = ref(false)
    /** 创建时关联的卡片ID，用于类型校验 */
    const mainEditorCardId = ref(null)
    /** 嵌入详情：badcase | bug | test_case，与 mainEditorItemId 组成稳定 keep-alive 键 */
    const embeddedEditorKind = ref('badcase')

    /** 详情区 keep-alive：同一实体 Tab 切换时复用实例，避免反复挂载与 mainEditorKey 强刷 */
    const mainEditorCacheKey = computed(() => {
      const id = mainEditorItemId.value
      const editFlag = mainEditorEdit.value ? '1' : '0'
      const diffFlag = mainEditorShowDiff.value ? '1' : '0'
      const pid = mainEditorPlanId.value == null ? 'na' : String(mainEditorPlanId.value)
      if (id == null || id === '') {
        return `editor-${embeddedEditorKind.value}-create-${pid}-${editFlag}-${diffFlag}`
      }
      return `editor-${embeddedEditorKind.value}-detail-${id}-${pid}-${editFlag}-${diffFlag}`
    })

    /** Cursor 式工作区：计划列表 / 详情 各为一个 Tab，标题为短名 */
    const workbenchTabs = ref([])
    const workbenchTabsForMoreMenu = computed(() => workbenchTabs.value)
    const activeWorkbenchTabId = ref(null)
    const isSettingsWorkbenchTab = computed(() => activeWorkbenchTabId.value === SETTINGS_WORKBENCH_TAB_ID)
    const isHelpWorkbenchTab = computed(() => activeWorkbenchTabId.value === HELP_WORKBENCH_TAB_ID)
    const isProjectManagementWorkbenchTab = computed(() => activeWorkbenchTabId.value === 'project-management')
    const isNotificationsWorkbenchTab = computed(
      () => activeWorkbenchTabId.value === NOTIFICATIONS_WORKBENCH_TAB_ID
    )
    const isTerminalSettingsWorkbenchTab = computed(
      () => activeWorkbenchTabId.value === TERMINAL_SETTINGS_WORKBENCH_TAB_ID
    )
    const activeWorkbenchTab = computed(() => workbenchTabs.value.find(t => t.id === activeWorkbenchTabId.value))
    
    /** 供嵌入式终端展示/关联的“当前卡片上下文”（来自工作台 Tab meta） */
    const terminalCardContext = computed(() => {
      const meta = activeWorkbenchTab.value?.meta || {}
      const cardId = meta.cardId ?? null
      const cardTitle = meta.cardTitle ?? ''
      const type = meta.type ?? meta.editorPlanType ?? meta.kind ?? ''
      if (!cardId) {
        return { cardId: null, cardTitle: '', type: type ? String(type) : '' }
      }
      return { cardId, cardTitle: String(cardTitle || ''), type: type ? String(type) : '' }
    })
    provide('terminalCardContext', terminalCardContext)

    /** 供嵌入式终端展示/关联的“当前迭代计划上下文”（来自左侧计划树 selectedPlan） */
    const terminalPlanContext = computed(() => {
      const pid = selectedPlan.value
      // 当前版本已不再存在“未计划”；若历史状态仍残留 unplanned，也按空处理
      if (!pid || pid === 'unplanned') return { planId: null, planTitle: '' }
      const p = currentPlan.value
      const title = p?.title ?? p?.name ?? ''
      return { planId: pid, planTitle: String(title || '') }
    })
    provide('terminalPlanContext', terminalPlanContext)
    const workbenchMenuRef = ref(null)
    const workbenchTabsStripRef = ref(null)
    /** Tab 条左键拖拽平移时用于样式（抓手 / 禁止选中文本） */
    const workbenchTabStripDraggingUI = ref(false)
    /** 拖拽滑动与单击切换 Tab 互斥 */
    const _tabStripDrag = { active: false, startX: 0, startScroll: 0, dragged: false }
    const showWorkbenchTabMenu = ref(false)
    /** 列表/Tab 导航诊断：控制台执行 localStorage.setItem('bcd:listNavDebug','1') 后刷新；置 '0' 关闭 */
    const isListNavDebug = () =>
      (typeof import.meta !== 'undefined' && import.meta.env?.DEV) ||
      (typeof localStorage !== 'undefined' && localStorage.getItem('bcd:listNavDebug') === '1')
    const logListNav = (tag, payload) => {
      if (!isListNavDebug()) return
      console.log(`[LIST-NAV] ${tag}`, payload === undefined ? '' : payload)
    }
    let workbenchMenuOutsideCleanup = null
    
    // 左侧对话框拖拽状态
    const leftSidebarWidth = ref(280)
    const isDraggingLeftSidebar = ref(false)
    const leftDragStartX = ref(0)
    const leftDragStartWidth = ref(280)
    
    // 右侧对话框拖拽状态
    const rightSidebarWidth = ref(320)
    const isDraggingRightSidebar = ref(false)
    const rightDragStartX = ref(0)
    const rightDragStartWidth = ref(320)
    
    // 底部面板拖拽状态
    const bottomPanelHeight = ref(300)
    const isDraggingBottomPanel = ref(false)
    const dragStartY = ref(0)
    const dragStartHeight = ref(300)
    
    // 基线管理相关状态
    const selectedBaselinePlan = ref(null)
    const selectedBaseline = ref(null)
    const selectedBadcases = ref([])
    const baselines = ref([])
    const availableBadcases = ref([])
    
    // 窄条导航栏相关状态
    // 左侧可挂载面板：plans/search/archive/plugins + 插件
    const activeLeftPanel = ref('plans')
    // 搜索改为左侧面板，不再使用覆盖层
    
    // 窄条导航栏处理函数
    const handleReturnToPlans = () => {
      // 切回迭代计划树面板
      activeLeftPanel.value = 'plans'

      // 收起左侧边栏
      if (leftSidebarHidden.value) {
        leftSidebarHidden.value = false
        planCollapsed.value = false
      }
      
      // 如果有选中的计划，选中该计划并挂载Tab（与点击迭代1行为一致）
      if (selectedPlan.value) {
        selectPlan(selectedPlan.value)
      } else {
        // 如果没有选中计划，关闭所有工作区Tab
        workbenchTabs.value = []
        activeWorkbenchTabId.value = null
      }
    }
    
    const handleOpenGlobalSearch = () => {
      // 搜索作为左侧挂载面板展示（无 X 关闭）
      activeLeftPanel.value = 'search'
    }
    
    // 打开归档视图
    const handleOpenArchive = () => {
      // 新架构：归档作为左侧挂载面板
      activeLeftPanel.value = 'archive'
      // 展开已归档计划的section
      if (!expandedSections.archived) {
        expandedSections.archived = true
      }
      // 确保侧边栏显示
      if (leftSidebarHidden.value) {
        leftSidebarHidden.value = false
        planCollapsed.value = false
      }
    }

    const handlePluginAction = (evt) => {
      const type = evt?.type
      if (type === 'openSearch') {
        handleOpenGlobalSearch()
        return
      }
      if (type === 'openArchive') {
        handleOpenArchive()
        return
      }
      console.log('[pluginAction] unknown:', evt)
    }
    
    const handleOpenCardCreate = () => {
      // 直接选中当前计划并打开 BadCase 列表（和点击迭代1一样的界面）
      // 如果没有选中计划，使用第一个计划
      let targetPlanId = selectedPlan.value
      if (!targetPlanId && activePlans.value && activePlans.value.length > 0) {
        targetPlanId = activePlans.value[0].id
      }
      
      if (targetPlanId) {
        // 选中该计划并加载 BadCase 列表
        selectPlan(targetPlanId)
      } else {
        // 如果没有任何计划，显示提示
        console.warn('没有可用的迭代计划')
      }
    }
    
    const handleSearchResultSelect = (result) => {
      console.log('选择搜索结果:', result)
      // openMainEditor(实体id, 类型, showDiff) — 禁止 (类型, id)，否则 mapToEditorPlanType 会把数字当成 badcase
      if (result.type === 'bug') {
        openMainEditor(result.id, 'bug', true)
      } else if (result.type === 'badcase') {
        openMainEditor(result.id, 'badcase', true)
      } else if (result.type === 'testcase') {
        openMainEditor(result.id, 'testcase', true)
      }
    }
    
    // 计划展开状态
    const expandedPlans = ref([])
    
    // 新建计划模态框状态
    const showCreateModal = ref(false)
    const isCreatingSubPlan = ref(false) // 区分是创建普通计划还是子计划
    const isCreatingSiblingPlan = ref(false) // 是否创建同级计划
    const isEditingPlan = ref(false) // 是否处于编辑模式
    const editingPlanId = ref(null) // 正在编辑的计划ID
    const newPlan = reactive({
      name: '',
      startDate: '',
      endDate: '',
      parentId: '',
      description: ''
    })
    
    // BadCase数据
    const badcases = ref([])
    const filteredBadcases = ref([]) // 根据选择的计划过滤后的BadCase
    const badcaseLoading = ref(false)
    const badcasePage = ref(1)
    const badcasePerPage = ref(20)
    const totalBadcases = ref(0)
    
    // Card数据（统一卡片列表）
    const cards = ref([])
    const filteredCards = ref([])
    const cardLoading = ref(false)
    const cardPage = ref(1)
    const cardPerPage = ref(20)
const totalCards = ref(0)
    const cardPanelRef = ref(null) // CardPanel 组件实例引用

    const pendingModifications = ref({}) // 存储待确认的修改
    /** 须在 restorePendingDiffReviews 之前声明：route watch immediate 会立刻恢复 diff，避免 TDZ */
    const highlightRowId = ref(null) // 高亮的列表行，用于滚动&样式
    const pendingCreates = ref([]) // 存储待确认的新建（无 before diff）
    const processedCreateKeyMap = reactive({})
    const createdIdByCreateKey = reactive({})
    const expandedDetailRows = ref([]) // 展开的详情行

    /** 与列表 currentPlanType / create target 对齐（bug、badcase、test_case） */
    const normalizeCreateTarget = (t) => {
      const s = (t || '').toString().toLowerCase()
      if (s === 'testcase' || s === 'test_case') return 'test_case'
      if (s === 'bug') return 'bug'
      if (s === 'badcase') return 'badcase'
      if (s === 'card') return 'card'
      return s
    }
    const normalizeViewType = (ct) => {
      const s = (ct || '').toString().toLowerCase()
      if (s === 'testcase' || s === 'test_case') return 'test_case'
      if (s === 'bug') return 'bug'
      if (s === 'badcase') return 'badcase'
      if (s === 'card') return 'card'
      return s
    }
    /**
     * 仅在「当前视图」展示待确认新建行：内容类型一致，且 plan_id 与当前选中的迭代计划一致（未计划视图只显示无 plan 的预览）。
     */
    const pendingCreatesForCurrentView = computed(() => {
      const list = pendingCreates.value || []
      const ct = normalizeViewType(currentPlanType.value)
      const sp = selectedPlan.value
      const tfRaw = (currentTypeFilter.value ?? '').toString().toLowerCase()
      const onCardOverview =
        tfRaw !== 'badcase' && tfRaw !== 'bug' && tfRaw !== 'testcase'
      return list.filter((pc) => {
        const t = normalizeCreateTarget(pc.target)
        if (onCardOverview) {
          if (t !== 'card') return false
        } else if (t !== ct) {
          return false
        }
        const pp = pc.preview?.plan_id ?? pc.preview?.planId
        const ppNum = pp != null && pp !== '' ? Number(pp) : null
        const isUnplannedPreview =
          ppNum == null || !Number.isFinite(ppNum) || ppNum === 0
        const isUnplannedTab =
          sp === null || sp === undefined || sp === 'unplanned'
        if (isUnplannedTab) {
          return isUnplannedPreview
        }
        const sid = Number(sp)
        if (!Number.isFinite(sid)) return false
        if (isUnplannedPreview) return false
        return Number(ppNum) === sid
      })
    })

    const PROCESSED_CREATE_KEY_LS_PREFIX = 'badcase_doctor:processed_create_key:'
    const getProcessedCreateKeyStorageKey = (pid) =>
      `${PROCESSED_CREATE_KEY_LS_PREFIX}${String(pid)}`

    const loadProcessedCreateFromStorage = (pid) => {
      if (!pid && pid !== 0) return
      const raw = localStorage.getItem(getProcessedCreateKeyStorageKey(pid))
      try {
        const obj = raw ? (JSON.parse(raw) || {}) : {}
        Object.keys(obj).forEach((createKey) => {
          if (!createKey) return
          processedCreateKeyMap[createKey] = true
          const meta = obj[createKey]
          if (meta && typeof meta === 'object' && meta.createdId) {
            createdIdByCreateKey[createKey] = meta.createdId
          }
        })
      } catch (e) {
        console.warn('[CREATE] 载入 processed create key 失败:', e)
      }
    }

    const persistProcessedCreateKey = (pid, createKey, meta = {}) => {
      if (!pid && pid !== 0) return
      if (!createKey) return
      const storageKey = getProcessedCreateKeyStorageKey(pid)
      let obj = {}
      try {
        const raw = localStorage.getItem(storageKey)
        obj = raw ? (JSON.parse(raw) || {}) : {}
      } catch {
        obj = {}
      }
      obj[createKey] = {
        processed: true,
        ...(obj[createKey] && typeof obj[createKey] === 'object' ? obj[createKey] : {}),
        ...(meta && typeof meta === 'object' ? meta : {})
      }
      try {
        localStorage.setItem(storageKey, JSON.stringify(obj))
      } catch (e) {
        console.warn('[CREATE] persist processed create key 失败:', e)
      }
    }

    const createSessionId = `${Date.now()}_${Math.random().toString(16).slice(2)}`
    const makeCreateKey = (target, preview, messageId = null) => {
      const t = target || 'testcase'
      const p = preview || {}
      const title = (
        p.title ||
        p.name ||
        p.bug_title ||
        p.bugTitle ||
        p.testcase_title ||
        p.badcase_title ||
        ''
      ).toString().trim()
      const planId = p.plan_id ?? p.planId ?? null
      const scope = (messageId ?? p._messageId ?? p.messageId) ?? `session:${createSessionId}`
      return `${scope}|${t}|${title}|${planId ?? 'null'}`
    }
    
    // 详情字段（列表行内不做 diff；含需在详情确认的优先级）
    // 注意：bug 的复现字段为 reproduction_steps，badcase 为 reproduction_steps，testcase 为 preconditions/steps/remark/baseline 等
    const DETAIL_FIELDS = [
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
      // 兼容：后端 diff 里可能使用复现步骤字段名
      'reproduce_steps',
      'priority'
    ]
    
    // 字段标签映射
    const FIELD_LABELS = {
      'title': '标题',
      'status': '状态',
      'priority': '优先级',
      'assignee': '负责人',
      'base_problem': '相似问题',
      'reproduction_steps': '复现步骤',
      'answer': '答案',
      'correct_answer': '正确答案',
      'badcase_result': 'BadCase结果',
      'solution': '解决方式',
      'problem_reason': '问题原因',
      'description': '描述',
      'steps_to_reproduce': '复现步骤',
      'expected_result': '预期结果',
      'actual_result': '实际结果',
      'preconditions': '前置条件',
      'steps': '测试步骤',
      'remark': '备注',
      'baseline': '基线'
    }
    // 标签/中文 -> 英文 key（用于 diff 里传中文字段名时识别为详情字段）
    const LABEL_TO_FIELD = {}
    Object.entries(FIELD_LABELS).forEach(([key, label]) => {
      LABEL_TO_FIELD[label] = key
    })
    LABEL_TO_FIELD['期望结果'] = 'expected_result' // 常见说法
    ;['Owner', 'owner', 'Assignee', 'assignee'].forEach((k) => {
      LABEL_TO_FIELD[k] = 'assignee'
    })

    /** diff 行字段名归一化：与 modify 工具、列表 LIST_FIELDS 对齐，避免仅英文标签时误判为「详情字段」而只打开详情、不展示列表行内 diff */
    const normalizeDiffFieldKey = (rawField) => {
      const raw = rawField ?? ''
      const mapped = LABEL_TO_FIELD[raw] || raw
      return mapped === 'assignee_id' ? 'assignee' : mapped
    }

    // 列表字段（在表格列中即可直接看到/编辑的字段；优先级 diff 仅走详情，不包含在此）
    const LIST_FIELDS = [
      'title',
      'status',
      'assignee'
    ]

    // 计算属性
    const selectedBaselinePlanName = computed(() => {
      if (!selectedBaselinePlan.value) return ''
      
      // 递归查找计划（包括子计划）
      const findPlan = (plans, planId) => {
        for (const plan of plans) {
          if (plan.id == planId) return plan
          if (plan.children && plan.children.length > 0) {
            const found = findPlan(plan.children, planId)
            if (found) return found
          }
        }
        return null
      }
      
      const plan = findPlan(projectPlans.value, selectedBaselinePlan.value)
      if (plan) {
        // 如果是子计划，显示 "父计划 > 子计划" 的格式
        if (plan.parent_id) {
          const parentPlan = projectPlans.value.find(p => p.id == plan.parent_id)
          return parentPlan ? `${parentPlan.name} > ${plan.name}` : plan.name
        }
        return plan.name
      }
      return ''
    })
    
    const hasBaselines = computed(() => baselines.value.length > 0)
    
    const planMatchesInProgress = (plan) => {
      if (plan.status_type === 'archived') return false
      const st = String(plan.status ?? '').toLowerCase()
      if (['archived', 'completed', 'finished', 'done', 'closed', 'cancelled', 'canceled'].includes(st)) {
        return false
      }
      // 旧接口：非 active 常被标成 status_type=unplanned，但 status 实为 draft/pending 等，应出现在「进行中」
      const legacyUnplannedButOngoing =
        plan.status_type === 'unplanned' &&
        st &&
        !['unplanned', 'new'].includes(st)
      return (
        plan.status_type === 'in_progress' ||
        legacyUnplannedButOngoing ||
        plan.status === 'active' ||
        plan.status === 'in_progress' ||
        plan.status === 'running' ||
        plan.status === 'open' ||
        plan.status === 'doing' ||
        plan.status === 'draft' ||
        plan.status === 'pending'
      )
    }

    /** 递归保留「自身进行中」或「子树中有进行中」的节点，避免进行中子计划挂在已归档父计划下时侧边栏整块空白 */
    const filterInProgressPlanTree = (plans) => {
      if (!plans || !plans.length) return []
      const out = []
      for (const plan of plans) {
        const childFiltered = plan.children?.length
          ? filterInProgressPlanTree(plan.children)
          : []
        const selfMatch = planMatchesInProgress(plan)
        if (selfMatch || childFiltered.length) {
          out.push({ ...plan, children: childFiltered })
        }
      }
      return out
    }

    // 根据状态类型过滤计划（整棵树，不仅顶层）
    const inProgressPlans = computed(() => {
      const plans = filterInProgressPlanTree(projectPlans.value)
      console.log('🔍 进行中计划过滤结果（递归）:', {
        total: projectPlans.value.length,
        filtered: plans.length,
        plans: plans.map((p) => ({
          id: p.id,
          name: p.name,
          status: p.status,
          status_type: p.status_type,
          childCount: p.children?.length || 0
        }))
      })
      return plans
    })
    
    // 活跃迭代 = 未计划 + 进行中（排除已归档）
    const activePlans = computed(() => {
      // 排除已归档的计划
      const active = projectPlans.value.filter(plan => {
        const st = String(plan.status ?? '').toLowerCase()
        return !(
          plan.status_type === 'archived' ||
          ['archived', 'completed', 'finished', 'done'].includes(st)
        )
      })
      return active
    })
    
    const archivedPlans = computed(() => {
      // 兼容更多可能的状态值，包括已归档、已完成和已结束状态
      return projectPlans.value.filter(plan => 
        (plan.status_type === 'archived') || 
        (plan.status === 'archived') || 
        (plan.status === 'completed') ||
        (plan.status === 'finished') ||
        (plan.status === 'done')
      )
    })
    
    // 获取BadCase数据
    const fetchBadcases = async (page = 1) => {
      console.log('=== fetchBadcases 开始 ===')
      console.log('项目ID:', projectId.value)
      console.log('页码:', page)
      console.log('每页数量:', badcasePerPage.value)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取BadCase数据')
        return
      }
      
      badcaseLoading.value = true
      try {
        console.log('调用API: 获取列表')
        const additionalParams = {}
        
        // 获取当前 Tab 的 cardId（如果有的话）
        const currentTab = activeWorkbenchTab.value
        const cardId = currentTab?.meta?.cardId
        
        // 如果有 cardId，优先使用 cardId 过滤（卡片分类型，计划不分类型）
        if (cardId) {
          additionalParams.card_id = cardId
          console.log(`🔍 按卡片ID过滤: cardId=${cardId}`)
        } else if (selectedPlan.value) {
          // 确保是数字类型传递给后端
          const planId = parseInt(selectedPlan.value)
          if (!isNaN(planId)) {
            additionalParams.plan_id = planId
          }
        }
        
        // 优先使用 currentTypeFilter（当前视图类型）决定 API，兜底用 currentPlanType
        const viewType = currentTypeFilter.value === 'bug' ? 'bug'
                       : currentTypeFilter.value === 'testcase' ? 'test_case'
                       : currentPlanType.value
        if (viewType) {
          additionalParams.content_type = viewType
        }
        
        let response
        if (viewType === 'bug') {
          console.log('🔍 检测到当前视图类型为 bug，调用 getProjectBugs')
          response = await getProjectBugs(projectId.value, page, badcasePerPage.value, additionalParams)
        } else if (viewType === 'test_case') {
          console.log('🔍 检测到当前视图类型为 test_case，调用 getProjectTestCases')
          response = await getProjectTestCases(projectId.value, page, badcasePerPage.value, additionalParams)
        } else {
          console.log('🔍 调用 getProjectBadcases')
          response = await getProjectBadcases(projectId.value, page, badcasePerPage.value, additionalParams)
        }
        
        console.log('API响应:', response)
        
        if (response && response.data && response.data.success) {
          badcases.value = response.data.badcases || []
          filteredBadcases.value = [...badcases.value] // 初始化过滤后的BadCase
          // 兼容 pagination.total 和直接的 total
          totalBadcases.value = (response.data.pagination && response.data.pagination.total) || response.data.total || 0
          badcasePage.value = page
          console.log('BadCase数据获取成功:', badcases.value)
          console.log('BadCase数量:', badcases.value.length)
          console.log('总数量:', totalBadcases.value)
          
          // 应用筛选条件
          applyFilters()
          
          // 检查每个BadCase的数据
          badcases.value.forEach((badcase, index) => {
            console.log(`BadCase ${index + 1}:`, {
              id: badcase.id,
              title: badcase.title,
              status: badcase.status,
              assignee: badcase.assignee,
              plan_id: badcase.plan_id, // 添加plan_id字段的调试
              created_at: badcase.created_at
            })
          })
        } else {
          console.error('获取BadCase数据失败:', response?.data?.error || '未知错误')
          badcases.value = []
          totalBadcases.value = 0
        }
      } catch (error) {
        console.error('获取BadCase数据异常:', error)
        console.error('错误详情:', error.message)
        console.error('错误堆栈:', error.stack)
        badcases.value = []
        totalBadcases.value = 0
      } finally {
        badcaseLoading.value = false
        console.log('=== fetchBadcases 完成 ===')
      }
    }
    
    // 快速创建卡片（只填标题）
    const handleQuickCreate = async (title, type = 'bug') => {
      console.log('[handleQuickCreate] 快速创建卡片:', title, '类型:', type)
      
      if (!title?.trim()) {
        console.error('标题不能为空')
        return
      }
      
      try {
        const cardData = {
          title: title.trim(),
          project_id: projectId.value,
          plan_id: selectedPlan.value || null,
          type: type || 'bug'
        }
        
        const response = await createCard(cardData)
        console.log('[handleQuickCreate] 创建响应:', response)
        
        if (response?.data?.success) {
          // 后端统一返回 { success, data: card.to_dict() }，兼容历史字段名 card
          const newCard = response.data.data ?? response.data.card
          console.log('[handleQuickCreate] 卡片创建成功:', newCard)
          
          if (!newCard || newCard.id == null) {
            console.error('[handleQuickCreate] 响应缺少卡片数据', response.data)
            alert(t('common.unknownError'))
            return
          }
          // 在列表前面插入新卡片
          filteredCards.value = [newCard, ...filteredCards.value]
          totalCards.value++
          
          // 等待 DOM 更新
          await nextTick()
          
          // 通知 CardPanel 新卡片已添加，用于显示新标记
          const panelInstance = cardPanelRef?.value
          if (panelInstance && typeof panelInstance.addNewlyCreatedId === 'function') {
            panelInstance.addNewlyCreatedId(newCard.id)
          }
          
          return newCard
        } else {
          console.error('[handleQuickCreate] 创建失败:', response?.data?.error)
          alert(response?.data?.error || t('common.unknownError'))
        }
      } catch (error) {
        console.error('[handleQuickCreate] 创建异常:', error)
        alert(error?.message || t('common.unknownError'))
      }
    }
    
    // 获取Card数据（统一卡片列表）
    const fetchCards = async (page = 1) => {
      console.log('=== fetchCards 开始 ===')
      console.log('项目ID:', projectId.value)
      console.log('页码:', page)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取Card数据')
        return
      }
      
      cardLoading.value = true
      try {
        const additionalParams = {}
        if (selectedPlan.value) {
          const planId = parseInt(selectedPlan.value)
          if (!isNaN(planId)) {
            additionalParams.plan_id = planId
          }
        }
        
        const response = await getProjectCards(projectId.value, page, cardPerPage.value, additionalParams)
        console.log('[CardPanel] Cards API响应:', response)
        
        if (response && response.data && response.data.success) {
          cards.value = response.data.data || response.data.cards || []
          // 按创建时间倒序排列（新的在前）
          cards.value.sort((a, b) => {
            const timeA = new Date(b.created_at || 0).getTime()
            const timeB = new Date(a.created_at || 0).getTime()
            return timeA - timeB
          })
          filteredCards.value = [...cards.value]
          totalCards.value = (response.data.pagination && response.data.pagination.total) || response.data.total || 0
          cardPage.value = page
          console.log('[CardPanel] Card数据获取成功:', cards.value)
          
          // 应用筛选条件
          if (searchText.value) {
            const search = searchText.value.toLowerCase()
            filteredCards.value = filteredCards.value.filter((c) => {
              const t = (c.title && String(c.title).toLowerCase()) || ''
              const r = (c.remark && String(c.remark).toLowerCase()) || ''
              const d = (c.description && String(c.description).toLowerCase()) || ''
              const a = (c.assignee && String(c.assignee).toLowerCase()) || ''
              return t.includes(search) || r.includes(search) || d.includes(search) || a.includes(search)
            })
          }
        } else {
          console.error('获取Card数据失败:', response?.data?.error || '未知错误')
          cards.value = []
          filteredCards.value = []
          totalCards.value = 0
        }
      } catch (error) {
        console.error('获取Card数据异常:', error)
        cards.value = []
        filteredCards.value = []
        totalCards.value = 0
      } finally {
        cardLoading.value = false
        console.log('=== fetchCards 完成 ===')
      }
    }

    const parsePositivePlanId = (v) => {
      if (v == null || v === '') return null
      const n = typeof v === 'number' ? v : parseInt(String(v), 10)
      return Number.isFinite(n) && n > 0 ? n : null
    }

    /** 列表分页可能不含目标行时，用详情接口解析 plan_id，避免误判进「未计划」Tab */
    const resolvePlanIdByRecordApi = async (target, rawId) => {
      const id = parseInt(String(rawId), 10)
      if (!Number.isFinite(id) || id <= 0) return null
      let tt = (target || 'badcase').toString().toLowerCase()
      if (tt === 'test_case') tt = 'testcase'
      try {
        if (tt === 'bug') {
          const res = await getBugDetail(id)
          if (res?.data?.success && res.data.bug) {
            const b = res.data.bug
            return parsePositivePlanId(b.navigation_plan_id ?? b.plan_id)
          }
        } else if (tt === 'badcase') {
          const res = await getBadcaseDetail(id)
          const bc = res?.data?.badcase
          if (res?.data?.success && bc) {
            return parsePositivePlanId(bc.plan_id)
          }
        } else if (tt === 'testcase') {
          const res = await getTestCaseDetail(id)
          const tc = res?.data?.testcase
          if (res?.data?.success && tc) {
            return parsePositivePlanId(tc.plan_id)
          }
        } else if (tt === 'card') {
          const res = await getCardDetail(id)
          const card = res?.data?.data
          if (res?.data?.success && card) {
            return parsePositivePlanId(card.plan_id)
          }
        }
      } catch (e) {
        console.warn('[NAV] resolvePlanIdByRecordApi failed', target, id, e)
      }
      return null
    }

    /** show-modify-in-list 连发时合并为一次列表请求，避免反复触发后端权限检查与查库 */
    let _modifyListFetchCoalesceTimer = null
    let _modifyListFetchCoalescePromise = null
    const awaitCoalescedFetchBadcasesForModifyList = () => {
      if (!_modifyListFetchCoalescePromise) {
        let resolvePromise
        _modifyListFetchCoalescePromise = new Promise((resolve) => {
          resolvePromise = resolve
        })
        if (_modifyListFetchCoalesceTimer) clearTimeout(_modifyListFetchCoalesceTimer)
        _modifyListFetchCoalesceTimer = setTimeout(async () => {
          _modifyListFetchCoalesceTimer = null
          try {
            await fetchBadcases(1)
          } finally {
            resolvePromise()
            _modifyListFetchCoalescePromise = null
          }
        }, 48)
      }
      return _modifyListFetchCoalescePromise
    }

    const normalizeDiffTargetForApi = (target) => {
      const t = (target || '').toString().toLowerCase().replace('-', '_')
      if (t === 'test_case') return 'testcase'
      return t || 'badcase'
    }

    /** 与后端 chat_message.id（MySQL INT）一致；临时消息用 Date.now() 会溢出，勿传库 */
    const MYSQL_SIGNED_INT_MAX = 2147483647
    const safeIntFkForDiffApi = (v) => {
      if (v == null || v === '') return null
      const n = Number(v)
      if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1 || n > MYSQL_SIGNED_INT_MAX) return null
      return n
    }

    const persistPendingDiffReview = async ({
      target,
      targetId,
      planId,
      diff,
      modifications,
      messageId
    }) => {
      try {
        if (!projectId.value || targetId == null) return
        const resp = await fetch(`${BACKEND_BASE_URL}/api/projects/${projectId.value}/diff-reviews/upsert`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            target: normalizeDiffTargetForApi(target),
            target_id: Number(targetId),
            plan_id: planId ?? null,
            diff: Array.isArray(diff) ? diff : [],
            modifications: modifications && typeof modifications === 'object' ? modifications : {},
            message_id: safeIntFkForDiffApi(messageId),
            session_id: safeIntFkForDiffApi(currentSession.value)
          })
        })
        if (!resp.ok) {
          const txt = await resp.text().catch(() => '')
          console.warn('[DIFF] upsert pending 非成功:', resp.status, txt?.slice?.(0, 500) || txt)
        }
      } catch (e) {
        console.warn('[DIFF] upsert pending 失败(忽略不阻断):', e)
      }
    }

    const resolveDiffReviewState = async ({ target, targetId, action, messageId }) => {
      try {
        if (!projectId.value || targetId == null) return
        const resp = await fetch(`${BACKEND_BASE_URL}/api/projects/${projectId.value}/diff-reviews/resolve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            target: normalizeDiffTargetForApi(target),
            target_id: Number(targetId),
            action,
            message_id: safeIntFkForDiffApi(messageId),
            session_id: safeIntFkForDiffApi(currentSession.value)
          })
        })
        if (!resp.ok) {
          const txt = await resp.text()
          throw new Error(txt || `HTTP ${resp.status}`)
        }
      } catch (e) {
        console.warn('[DIFF] resolve 状态失败:', e)
        throw e
      }
    }

    let diffReviewSyncDebounceTimer = null
    /** 与 show-modify 连发时避免 restore 重复整页跳转/高亮（约「闪三次」） */
    let _restorePendingNavFingerprint = ''
    let _restorePendingNavAtMs = 0
    const handleDiffReviewSync = () => {
      if (diffReviewSyncDebounceTimer) clearTimeout(diffReviewSyncDebounceTimer)
      diffReviewSyncDebounceTimer = setTimeout(async () => {
        diffReviewSyncDebounceTimer = null
        try {
          await restorePendingDiffReviews()
        } catch (_e) {
          /* ignore */
        }
      }, 320)
    }

    const restorePendingDiffReviews = async () => {
      try {
        if (!projectId.value) return
        const resp = await fetch(
          `${BACKEND_BASE_URL}/api/projects/${projectId.value}/diff-reviews?status=pending`,
          { credentials: 'include' }
        )
        if (!resp.ok) return
        const data = await resp.json()
        const items = Array.isArray(data?.items) ? data.items : []

        const clearModifyDiffMemory = () => {
          if (Object.keys(pendingModifications.value).length > 0) {
            pendingModifications.value = {}
          }
          if (highlightRowId.value != null) {
            highlightRowId.value = null
          }
          try {
            sessionStorage.removeItem('pendingModifyDiff')
          } catch (_e) {
            /* ignore */
          }
        }

        // 持久化无当前用户可见的待采纳/rejected：清空列表 modify 黄条内存，避免 SPA 长驻与 DB 脱钩
        if (!items.length) {
          clearModifyDiffMemory()
          return
        }

        const batchItems = items
          .map((it) => ({
            targetId: Number(it.target_id),
            target: normalizeDiffTargetForApi(it.target),
            diff: Array.isArray(it.diff) ? it.diff : [],
            modifications: it.modifications && typeof it.modifications === 'object' ? it.modifications : {},
            plan_id: it.plan_id ?? null,
            executed: false,
            messageId: it.message_id ?? null,
            batchIndex: 0,
            peerTargetIds: [Number(it.target_id)],
            suppressAutoOpenDetail: true
          }))
          .filter((x) => Number.isFinite(x.targetId) && x.targetId > 0)
        if (!batchItems.length) {
          clearModifyDiffMemory()
          return
        }

        const navFp = batchItems
          .map((x) => x.targetId)
          .sort((a, b) => a - b)
          .join(',')
        const nowNav = Date.now()
        const hi = highlightRowId.value != null ? Number(highlightRowId.value) : NaN
        const hiInBatch =
          Number.isFinite(hi) && batchItems.some((x) => Number(x.targetId) === hi)
        const skipHeavyListNav =
          navFp === _restorePendingNavFingerprint &&
          nowNav - _restorePendingNavAtMs < 2800 &&
          hiInBatch
        _restorePendingNavFingerprint = navFp
        _restorePendingNavAtMs = nowNav

        if (!skipHeavyListNav) {
          await handleShowModifyInList({ detail: { __modifyListBatch: true, items: batchItems } })
        }

        // 以本次 GET 为权威：删掉内存里不在返回集合中的 target_id（他处已采纳/拒绝后本地残留）
        const allowed = new Set(batchItems.map((x) => x.targetId))
        const next = { ...pendingModifications.value }
        let changed = false
        for (const k of Object.keys(next)) {
          const id = Number(k)
          if (!Number.isFinite(id)) continue
          if (!allowed.has(id)) {
            delete next[k]
            changed = true
          }
        }
        if (changed) {
          pendingModifications.value = next
        }
        if (highlightRowId.value != null && !allowed.has(Number(highlightRowId.value))) {
          highlightRowId.value = null
        }
        try {
          const raw = sessionStorage.getItem('pendingModifyDiff')
          if (raw) {
            const o = JSON.parse(raw)
            const tid = o && o.targetId != null ? Number(o.targetId) : NaN
            if (Number.isFinite(tid) && !allowed.has(tid)) {
              sessionStorage.removeItem('pendingModifyDiff')
            }
          }
        } catch (_e) {
          try {
            sessionStorage.removeItem('pendingModifyDiff')
          } catch (__e) {
            /* ignore */
          }
        }
      } catch (e) {
        console.warn('[DIFF] 恢复 pending 失败(忽略不阻断):', e)
      }
    }

    // 刷新BadCase数据（须返回 Promise，否则采纳新建后 await refreshBadcases 无法等待列表就绪）
    const refreshBadcases = () => fetchBadcases(1)

    // 获取项目成员
    const fetchProjectMembers = async () => {
      try {
        console.log('=== 开始获取项目成员 ===')
        const response = await getProjectMembers(projectId.value)
        
        if (response && response.data && response.data.success) {
          projectMembers.value = response.data.members
          console.log('✅ 项目成员获取成功:', projectMembers.value)
        } else {
          console.error('获取项目成员失败:', response?.data?.error || '未知错误')
          projectMembers.value = []
        }
      } catch (error) {
        console.error('获取项目成员异常:', error)
        projectMembers.value = []
      }
    }


    
    // 获取计划状态文本
    const getPlanStatusText = (status) => {
      const keyMap = {
        active: 'project.planStateActive',
        archived: 'project.planStateArchived',
        completed: 'project.planStateCompleted'
      }
      const k = keyMap[status]
      return k ? t(k) : status
    }

    const getBadcaseStatusText = (status) => {
      if (status === null || status === undefined || String(status).trim() === '') {
        return t('chat.notSet')
      }
      const k = `list.badcaseStatus.${status}`
      const tr = t(k)
      if (tr !== k) return tr
      return getBadCaseStatusText(status)
    }

    // 获取BadCase背景样式类
    const getBadcaseBackgroundClass = (badcase) => {
      const classes = []
      
      // 根据来源设置背景
      if (badcase.source === 'ai-generated') {
        classes.push('ai-generated')
      } else if (badcase.source === 'manual') {
        classes.push('manual')
      } else {
        classes.push('default')
      }
      
      // 根据状态设置样式
      if (badcase.status === 'new') {
        classes.push('status-new')
      } else if (badcase.status === 'pending') {
        classes.push('status-pending')
      } else if (badcase.status === 'resolved') {
        classes.push('status-resolved')
      } else if (badcase.status === 'close') {
        classes.push('status-closed')
      }
      
      // 根据优先级设置样式
      if (badcase.priority === 'p1') {
        classes.push('priority-high')
      } else if (badcase.priority === 'p2') {
        classes.push('priority-medium')
      } else if (badcase.priority === 'p3') {
        classes.push('priority-low')
      }
      
      return classes.join(' ')
    }

    // 获取BadCase图标
    const getBadcaseIcon = (badcase) => {
      if (badcase.source === 'ai-generated') {
        return '🤖'
      } else if (badcase.priority === 'p1') {
        return '🔥'
      } else if (badcase.priority === 'p2') {
        return '⚠️'
      } else if (badcase.priority === 'p3') {
        return '📝'
      } else {
        return '📋'
      }
    }

    // 接受BadCase
    const acceptBadcase = (badcase) => {
      // 更新BadCase状态为已接受
      badcase.aiStatus = 'accepted'
      
      // 这里可以调用API更新BadCase状态
      console.log('接受BadCase:', badcase)
      
      // 显示成功消息
      // 可以添加toast通知
    }

    // 拒绝BadCase
    const rejectBadcase = (badcase) => {
      // 更新BadCase状态为已拒绝
      badcase.aiStatus = 'rejected'
      
      // 这里可以调用API更新BadCase状态或删除BadCase
      console.log('拒绝BadCase:', badcase)
      
      // 显示成功消息
      // 可以添加toast通知
    }
    
    // AI助手下拉菜单相关方法
    const toggleDropdown = () => {
      showDropdown.value = !showDropdown.value
      showHistory.value = false
    }

    const toggleHistory = async () => {
      showHistory.value = !showHistory.value
      showDropdown.value = false
      if (showHistory.value) {
        await fetchSessions()
      }
    }

    const fetchSessions = async () => {
      if (!projectId.value) return
      historyLoading.value = true
      try {
        const response = await getChatSessions(projectId.value)
        if (response.data.success) {
          sessionHistory.value = response.data.sessions.sort((a, b) => 
            new Date(b.created_at) - new Date(a.created_at)
          )
        }
      } catch (error) {
        console.error('获取会话历史失败:', error)
      } finally {
        historyLoading.value = false
      }
    }
    
    const closeSession = () => {
      showDropdown.value = false
      setLayout('left')
    }
    
    const exportChat = () => {
      showDropdown.value = false
      // 导出对话功能
      console.log('导出对话')
    }
    
    const clearMessages = () => {
      showDropdown.value = false
      // 清空对话功能
      console.log('清空对话')
    }

    // 处理会话标题更新
    const handleTitleUpdated = (newTitle) => {
      console.log('[ProjectDetail] 收到标题更新:', newTitle)
      // 更新当前会话的标题
      if (currentSession.value && sessions.value[currentSession.value]) {
        sessions.value[currentSession.value].title = newTitle
      }
      // 更新历史记录中的标题
      const historyItem = sessionHistory.value.find(s => s.id === currentSession.value)
      if (historyItem) {
        historyItem.title = newTitle
      }
    }

    // 会话管理方法
    const switchSession = (sessionId) => {
      currentSession.value = sessionId
      showDropdown.value = false
      showHistory.value = false
      
      // 确保该会话在 sessions 对象中（如果需要的话，SimpleChatPanel 内部也会根据 sessionId 加载）
      if (!sessions.value[sessionId]) {
        // 查找历史记录中的信息填充到 sessions
        const sessionInfo = sessionHistory.value.find(s => s.id === sessionId)
        if (sessionInfo) {
          sessions.value[sessionId] = sessionInfo
        } else {
          // 如果历史中没有，可能需要调用 getChatSession 获取
          sessions.value[sessionId] = { id: sessionId, title: t('common.loading') }
        }
      }
    }
    
    const createNewSession = async () => {
      if (!projectId.value) {
        alert(t('project.errorNoProjectId'))
        return
      }

      try {
        const response = await createChatSession(projectId.value, {
          title: 'newchat',
          memory_enabled: true
        })

        if (response.data.success) {
          const newSess = response.data.session
          sessions.value[newSess.id] = newSess
          currentSession.value = newSess.id
          showTerminalInput.value = true
          showHistory.value = false
          console.log('新建会话成功:', newSess)
        } else {
          alert(t('project.sessionCreateFail', { msg: response.data.error || t('common.unknownError') }))
        }
      } catch (error) {
        console.error('新建会话异常:', error)
        alert(t('project.sessionCreateError'))
      }
    }

    async function openAiComposerPrefill(text) {
      showAIAssistant.value = true
      if (!currentSession.value) {
        await createNewSession()
      }
      await nextTick()
      chatComposerPreset.value = { token: Date.now(), text: String(text || '') }
    }
    provide('openAiComposerPrefill', openAiComposerPrefill)

    async function openDiagnosticTerminal(opts) {
      showTerminal.value = true
      showAIAssistant.value = true
      const text = opts && opts.aiText != null ? String(opts.aiText) : ''
      if (!currentSession.value) {
        await createNewSession()
      }
      await nextTick()
      chatComposerPreset.value = { token: Date.now(), text }
    }
    provide('openDiagnosticTerminal', openDiagnosticTerminal)

    /** type-list Tab 在 meta.cardTitle 丢失时（分页/刷新后卡片列表未命中），按 cardId 从内存卡片表解析标题 */
    const resolveTypeListCardTitleFromMeta = (meta) => {
      const m = meta || {}
      const cid = m.cardId
      if (cid == null || cid === '') return ''
      const n = typeof cid === 'number' ? cid : parseInt(String(cid), 10)
      if (!Number.isFinite(n) || n <= 0) return ''
      const lists = [filteredCards.value, cards.value]
      for (const list of lists) {
        if (!Array.isArray(list)) continue
        const row = list.find((c) => Number(c.id) === n)
        if (row?.title) return String(row.title)
      }
      return ''
    }

    // 获取类型列表面包屑（无卡片名时不保留末尾「/」，避免与右侧 x/y 计数连成「迭代1/2/2」误读）
    const getTypeListBreadcrumb = (type, cardTitle) => {
      const planName = selectedBaselinePlanName.value || `迭代${selectedPlan.value}`
      const meta = activeWorkbenchTab.value?.meta || {}
      let seg =
        cardTitle != null && String(cardTitle).trim() !== ''
          ? String(cardTitle).trim()
          : meta.cardTitle != null && String(meta.cardTitle).trim() !== ''
            ? String(meta.cardTitle).trim()
            : ''
      if (!seg) seg = resolveTypeListCardTitleFromMeta(meta)
      if (!seg) return planName
      return `${planName}/${seg}`
    }

    // 处理类型列表打开 - 创建新Tab
    const handleOpenTypeList = async (type, cardTitle, cardId) => {
      // 先保存当前 CardPanel Tab 的类型状态
      const currentTabId = activeWorkbenchTabId.value
      const currentTab = workbenchTabs.value.find(t => t.id === currentTabId)
      if (currentTab?.kind === 'plan-list') {
        upsertWorkbenchTab({
          id: currentTabId,
          meta: { ...currentTab.meta, type: currentTypeFilter.value }
        })
      }
      
      // 创建新的类型列表 Tab，标题为卡片标题，保存卡片ID用于类型校验
      const tabId = `type-list-${type}-${selectedPlan.value}-${Date.now()}`
      upsertWorkbenchTab({
        id: tabId,
        kind: 'type-list',
        title: cardTitle || `${type}列表`,
        meta: { type, planId: selectedPlan.value, cardTitle, cardId }
      })
      currentTypeFilter.value = type
      activeWorkbenchTabId.value = tabId
      
      // 等待 DOM 更新后，调用 activateWorkbenchTab 触发数据获取
      await nextTick()
      await activateWorkbenchTab(tabId)
    }

    // 处理新建按钮点击 - 在新Tab中打开对应的创建界面
    const handleOpenCreate = (planType) => {
      const editorType = planType === 'test_case' ? 'test_case' : planType
      // 从当前Tab获取卡片ID，用于类型校验
      const currentTab = activeWorkbenchTab.value
      const cardId = currentTab?.meta?.cardId
      const cardTitle = currentTab?.meta?.cardTitle
      console.log('[handleOpenCreate] planType:', planType, 'cardId:', cardId, 'currentTab:', currentTab?.kind, currentTab?.meta)
      
      // 保存当前Tab ID用于返回
      const returnTo = activeWorkbenchTabId.value
      const pidKey = selectedPlan.value == null ? 'unplanned' : String(selectedPlan.value)
      const tid = `create-${editorType}-${pidKey}-${Date.now()}`
      const titleMap = {
        badcase: t('project.newBadcase') || '新建 BadCase',
        bug: t('project.newBug') || '新建 Bug',
        test_case: t('project.newTestCase') || '新建 测试用例'
      }
      upsertWorkbenchTab({
        id: tid,
        kind: 'create',
        title: truncateForTab(titleMap[editorType] || '新建', '新建'),
        meta: { editorPlanType: editorType, planId: selectedPlan.value, returnTo, cardId, cardTitle }
      })
      activeWorkbenchTabId.value = tid
      // 传递cardId给编辑器，用于校验卡片类型
      mountEditorComponents(null, editorType, false, false, selectedPlan.value, cardId)
    }

    // 获取当前应该显示的面板组件
    const getCurrentPanelComponent = () => {
      switch (currentTypeFilter.value) {
        case 'badcase':
          return 'BadcaseListPanel'
        case 'bug':
          return 'BugListPanel'
        case 'testcase':
          return 'TestCaseListPanel'
        default:
          return 'CardPanel'
      }
    }

    // 处理子组件加载完数据后更新Tab标题
    const handleTitleLoaded = (title) => {
      const tid = activeWorkbenchTabId.value
      if (tid) {
        const tab = workbenchTabs.value.find(t => t.id === tid)
        if (tab && (tab.kind === 'detail' || tab.kind === 'create')) {
          upsertWorkbenchTab({
            id: tid,
            title: truncateForTab(title, '编辑')
          })
        }
      }
    }

    watch(
      () => route.query.terminal_cmd,
      async (cmd) => {
        if (cmd == null || cmd === '') return
        showTerminal.value = true
        showAIAssistant.value = true
        await openAiComposerPrefill(String(cmd))
      },
      { immediate: true }
    )

    const closeSessionTab = (sessionId) => {
      // 这里的逻辑改为关闭右侧面板
      setLayout('left')
    }
    

    // 当显示terminal输入时，自动聚焦到输入框（已由新的终端实现）


    // 获取BadCase类型文本
    const getBadcaseTypeText = (type) => {
      const typeMap = {
        badcase: () => t('list.types.badcase'),
        bug: () => t('list.types.bug'),
        test_request: () => t('project.badcaseTypeRequest')
      }
      const fn = typeMap[type]
      return fn ? fn() : type
    }
    
    // 根据内容类型获取计划图标
    const getPlanIcon = (contentType) => {
      const iconMap = {
        'badcase': '📋',
        'bug': '🐛',
        'test_case': '🧪'
      }
      return iconMap[contentType] || '📋'
    }
    
    // 格式化日期
    const formatDate = (dateStr) => {
      if (!dateStr) return ''
      const date = new Date(dateStr)
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const day = String(date.getDate()).padStart(2, '0')
      return `${month}-${day}`
    }
    
    // 根据内容类型获取计划类型文本
    const getPlanTypeText = (contentType) => {
      const typeMap = {
        badcase: () => t('project.contentBadcase'),
        bug: () => t('project.contentBug'),
        test_case: () => t('project.contentTestCase')
      }
      const fn = typeMap[contentType]
      return fn ? fn() : t('project.unknownType')
    }
    
    // 获取负责人显示文本（列表 API 常为名字字符串；新建预览 preview.assignee_id 为成员数字 id）
    const getAssigneeDisplayText = (assignee) => {
      if (assignee == null || assignee === '') {
        return t('list.unassigned')
      }
      const n =
        typeof assignee === 'number'
          ? assignee
          : typeof assignee === 'string' && /^\d+$/.test(String(assignee).trim())
            ? Number(String(assignee).trim())
            : NaN
      if (Number.isFinite(n) && n > 0) {
        const m = projectMembers.value.find((x) => Number(x.id) === n)
        if (m?.name) return m.name
      }

      // 如果assignee是字符串（单个值），直接返回
      if (typeof assignee === 'string') {
        return assignee
      }

      // 如果是数组
      if (Array.isArray(assignee)) {
        if (assignee.length === 1) {
          return assignee[0]
        } else {
          return `${assignee[0]}...`
        }
      }

      return assignee
    }

    // 生成面包屑导航
    const generateBreadcrumb = () => {
      const managementLabel =
        currentPlanType.value === 'bug'
          ? t('project.mgmtBug')
          : currentPlanType.value === 'test_case'
            ? t('project.mgmtTestCase')
            : t('project.mgmtBadcase')
      
      if (!currentPlan.value) {
        return managementLabel
      }
      
      const breadcrumb = []
      let plan = currentPlan.value
      
      const findParent = (plans, parentId) => {
        for (const p of plans) {
          if (p.id == parentId) return p
          if (p.children && p.children.length > 0) {
            const found = findParent(p.children, parentId)
            if (found) return found
          }
        }
        return null
      }

      // 从当前计划向上遍历，构建完整路径
      let tempPlan = plan
      while (tempPlan) {
        breadcrumb.unshift(tempPlan.name)
        // 查找父计划
        if (tempPlan.parent_id) {
          tempPlan = findParent(projectPlans.value, tempPlan.parent_id)
        } else {
          tempPlan = null
        }
      }
      
      // 添加管理类型前缀
      breadcrumb.unshift(managementLabel)
      // 添加项目名称
      breadcrumb.unshift(projectName.value || t('project.detailTitle'))
      
      return breadcrumb.join(' / ')
    }
    
    // 处理计划数据，添加图标和格式化；保证 test_case_count 等数量字段必为数字
    const processPlanData = (plans) => {
      if (!plans) return []
      return plans.map(plan => {
        // 计划仅作为容器；列表类型由卡片/Tab 上下文决定
        const contentType = 'badcase'
        const children = plan.children ? processPlanData(plan.children) : []
        return {
          ...plan,
          content_type: contentType,
          icon: getPlanIcon(contentType),
          statusText: getPlanStatusText(plan.status),
          children,
          badcase_count: Number(plan.badcase_count ?? 0),
          bug_count: Number(plan.bug_count ?? 0),
          test_case_count: Number(plan.test_case_count ?? 0)
        }
      })
    }
    
    // 计算属性
    const availableParentPlans = computed(() => {
      return projectPlans.value.filter(plan => plan.status === 'active')
    })
    
    const namePlaceholder = computed(() => {
      if (!newPlan.startDate || !newPlan.endDate) return t('project.planNamePlaceholder')
      const start = new Date(newPlan.startDate)
      const end = new Date(newPlan.endDate)
      const startStr = `${(start.getMonth() + 1).toString().padStart(2, '0')}.${start.getDate().toString().padStart(2, '0')}`
      const endStr = `${(end.getMonth() + 1).toString().padStart(2, '0')}.${end.getDate().toString().padStart(2, '0')}`
      return `${startStr}~${endStr}`
    })
    
    const isFormValid = computed(() => {
      return newPlan.startDate && newPlan.endDate && newPlan.name.trim()
    })
    
    // 获取项目计划
    const fetchProjectPlans = async () => {
      if (!projectId.value) {
        console.log('项目ID为空，无法获取计划')
        return
      }
      
      loading.value = true
      try {
        console.log('=== 开始获取项目计划 ===')
        console.log('项目ID:', projectId.value)
        console.log('API URL:', `${BACKEND_BASE_URL}/api/projects/${projectId.value}/plans`)
        
        const response = await getProjectPlans(projectId.value)
        console.log('获取项目计划完整响应:', response)
        console.log('响应状态:', response.status)
        console.log('响应数据:', response.data)
        if (response && response.data && response.data.success) {
          projectPlans.value = processPlanData(response.data.plans)
          // 后端 plans 接口已用 GROUP BY 聚合返回每个计划的 test_case_count，无需单独请求
          const agg = {}
          const setAgg = (plans) => {
            if (!plans?.length) return
            plans.forEach(p => {
              // 确保 key 和 value 都是正确的类型
              agg[Number(p.id)] = Number(p.test_case_count ?? 0)
              if (p.children?.length) setAgg(p.children)
            })
          }
          setAgg(projectPlans.value)
          planTestCaseCounts.value = agg
          filterPlans()
          projectPlans.value = [...projectPlans.value]
          filteredPlans.value = [...filteredPlans.value]
          
          // 如果没有选中任何计划，自动选中第一个活跃计划并挂载Tab
          if (!selectedPlan.value && filteredPlans.value.length > 0) {
            const firstPlan = filteredPlans.value[0]
            console.log('自动选中第一个计划:', firstPlan.id, firstPlan.name)
            await selectPlan(firstPlan.id)
          }
        } else {
          console.error('获取项目计划失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('获取项目计划失败:', error)
        console.error('错误详情:', {
          message: error.message,
          status: error.response?.status,
          statusText: error.response?.statusText,
          data: error.response?.data
        })
      } finally {
        loading.value = false
      }
    }
    
    // 获取项目信息
    const fetchProjectInfo = async () => {
      console.log('=== fetchProjectInfo 开始 ===')
      console.log('项目ID:', projectId.value)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取项目信息')
        return
      }
      
      try {
        console.log('调用API: getProjectDetail')
        const response = await getProjectDetail(projectId.value)
        console.log('项目信息API响应:', response)
        
        if (response && response.data && response.data.success) {
          projectName.value = response.data.project.name
          console.log('项目名称设置成功:', projectName.value)
        } else {
          console.error('获取项目信息失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('获取项目信息失败:', error)
        console.error('错误详情:', error.message)
        console.error('错误堆栈:', error.stack)
      } finally {
        console.log('=== fetchProjectInfo 完成 ===')
      }
    }
    
    // 方法
    const toggleSection = (section) => {
      expandedSections[section] = !expandedSections[section]
    }
    
    /** 切换侧栏计划视图时关闭主区域嵌入详情，否则会一直盖在列表上 */
    const clearEmbeddedEditor = () => {
      if (!showMainEditor.value) return
      showMainEditor.value = false
      mainEditorComponent.value = null
      mainEditorItemId.value = null
      mainEditorEdit.value = true
      mainEditorPlanId.value = null
      mainEditorShowDiff.value = false
      mainEditorCardId.value = null
    }

    const MAX_TAB_TITLE = 28
    const truncateForTab = (text, fallback = '') => {
      const s = (text || '').trim() || fallback
      return s.length > MAX_TAB_TITLE ? s.slice(0, MAX_TAB_TITLE - 1) + '…' : s
    }

    const findPlanRecursive = (plans, id) => {
      if (!plans || id == null) return null
      for (const p of plans) {
        if (p.id == id) return p
        if (p.children?.length) {
          const f = findPlanRecursive(p.children, id)
          if (f) return f
        }
      }
      return null
    }

    const mapToEditorPlanType = (t) => {
      if (t === 'bug') return 'bug'
      if (t === 'test_case' || t === 'testcase') return 'test_case'
      if (t === 'badcase' || t === 'bad_case') return 'badcase'
      if (t === 'card') {
        console.warn(
          '[EDITOR-TYPE] mapToEditorPlanType: 仍为 "card"（应在 openMainEditor 内先解析卡片行），兜底为 badcase'
        )
        return 'badcase'
      }
      console.warn(
        '[EDITOR-TYPE] mapToEditorPlanType: 未识别类型，兜底为 badcase。入参:',
        t,
        'typeof:',
        typeof t
      )
      return 'badcase'
    }

    const upsertWorkbenchTab = (tab) => {
      const i = workbenchTabs.value.findIndex((x) => x.id === tab.id)
      if (i >= 0) {
        workbenchTabs.value[i] = { ...workbenchTabs.value[i], ...tab }
      } else {
        workbenchTabs.value.push(tab)
      }
    }

    /** 卡片列表加载后补全 type-list Tab 的 meta.cardTitle，避免面包屑只剩迭代名、被误认为卡片错误 */
    watch(
      () => [activeWorkbenchTabId.value, cards.value, filteredCards.value],
      () => {
        const tab = workbenchTabs.value.find((t) => t.id === activeWorkbenchTabId.value)
        if (!tab || tab.kind !== 'type-list') return
        const meta = tab.meta || {}
        if (meta.cardTitle != null && String(meta.cardTitle).trim() !== '') return
        const cid = meta.cardId
        if (cid == null || cid === '') return
        const n = typeof cid === 'number' ? cid : parseInt(String(cid), 10)
        if (!Number.isFinite(n) || n <= 0) return
        const row =
          (Array.isArray(filteredCards.value) && filteredCards.value.find((c) => Number(c.id) === n)) ||
          (Array.isArray(cards.value) && cards.value.find((c) => Number(c.id) === n))
        if (!row?.title) return
        upsertWorkbenchTab({
          id: tab.id,
          meta: { ...meta, cardTitle: String(row.title) }
        })
      },
      { flush: 'post' }
    )

    const mountEditorComponents = (itemId, editorPlanType, showDiff, edit = true, planId = null, cardId = null) => {
      const compName =
        editorPlanType === 'bug' ? 'NewBug' : editorPlanType === 'test_case' ? 'NewTestCase' : 'NewBadcase'
      console.log('[mountEditorComponents]', {
        itemId,
        editorPlanType,
        挂载组件: compName,
        showDiff,
        planId,
        cardId,
        说明:
          editorPlanType === 'bug'
            ? 'editorPlanType=bug'
            : editorPlanType === 'test_case'
              ? 'editorPlanType=test_case'
              : 'editorPlanType 非 bug/test_case → 使用 NewBadcase（若不该出现请查 mapToEditorPlanType / openMainEditor 入参）'
      })
      if (editorPlanType === 'bug') {
        mainEditorComponent.value = markRaw(NewBug)
      } else if (editorPlanType === 'test_case') {
        mainEditorComponent.value = markRaw(NewTestCase)
      } else {
        mainEditorComponent.value = markRaw(NewBadcase)
      }
      embeddedEditorKind.value = editorPlanType
      mainEditorItemId.value = itemId
      mainEditorEdit.value = !!edit
      mainEditorPlanId.value = planId
      mainEditorShowDiff.value = showDiff
      mainEditorCardId.value = cardId
      showMainEditor.value = true
    }

    const selectPlan = async (planId) => {
      clearEmbeddedEditor()
      const pid = typeof planId === 'number' ? planId : parseInt(String(planId), 10)
      if (Number.isNaN(pid)) {
        console.error('无效 planId:', planId)
        return
      }
      const planObj = findPlanRecursive(projectPlans.value, pid)
      const title = truncateForTab(planObj?.name, t('tab.planFallback', { id: pid }))
      upsertWorkbenchTab({
        id: `plan-${pid}`,
        kind: 'plan-list',
        title,
        meta: { planId: pid, urlContentType: null, type: null }
      })
      activeWorkbenchTabId.value = `plan-${pid}`
      console.log('选择计划:', planId)
      currentTypeFilter.value = null
      await applyPlanListTabState({ planId: pid, urlContentType: null })
    }
    
    // 根据BadCase选择对应的计划
    const selectBadcasePlan = async (badcase) => {
      console.log('=== 开始检索BadCase相关计划 ===')
      console.log('BadCase信息:', {
        id: badcase.id,
        title: badcase.title,
        plan_id: badcase.plan_id,
        status: badcase.status
      })
      
      if (badcase.plan_id) {
        // 如果BadCase有plan_id，选择对应的计划
        selectedPlan.value = badcase.plan_id
        console.log(`✅ BadCase "${badcase.title}" 绑定到计划 ${badcase.plan_id}`)
        
        // 调用API接口获取该计划下的BadCase
        console.log(`🔍 调用API: /api/projects/${projectId.value}/badcases?page=1&per_page=20&plan_id=${badcase.plan_id}`)
        await fetchBadcasesByPlan(badcase.plan_id, 1)
        
        // 同时展开对应的计划section
        expandedSections[badcase.plan_id] = true
        
        // API调用完成后，根据选择的计划过滤BadCase
        console.log('API调用完成，开始过滤BadCase')
        filterBadcasesByPlan(badcase.plan_id)
        console.log(`📂 展开计划section: ${badcase.plan_id}`)
        
        // 高亮显示选中的计划
        console.log(`🎯 计划 ${badcase.plan_id} 已选中`)
      } else {
        // 如果BadCase没有plan_id，创建一个新计划并关联
        console.log(`⚠️ BadCase "${badcase.title}" 没有绑定计划，开始创建新计划...`)
        createPlanForBadcase(badcase)
      }
      
      console.log('=== BadCase计划检索完成 ===')
    }
    
    // 为BadCase创建新计划并关联
    const createPlanForBadcase = async (badcase) => {
      try {
        console.log('=== 开始为BadCase创建新计划 ===')
        console.log(`BadCase: ${badcase.title} (ID: ${badcase.id})`)
        
        // 创建新计划
        const newPlan = {
          name: `计划-${badcase.title}`,
          description: `为BadCase "${badcase.title}" 自动创建的计划`,
          project_id: projectId.value,
          status: 'active',
          type: 'task',
          priority: 'medium'
        }
        
        console.log('新计划数据:', newPlan)
        
        // 调用API创建计划
        const response = await createPlanApi(newPlan)
        
        if (response && response.data && response.data.success) {
          const createdPlan = response.data.plan
          console.log(`✅ 新计划创建成功: ${createdPlan.name} (ID: ${createdPlan.id})`)
          
          // 关联BadCase到新计划
          await associateBadcaseWithPlan(badcase.id, createdPlan.id)
          
          // 选择新创建的计划
          selectedPlan.value = createdPlan.id
          console.log(`🎯 已选择新创建的计划: ${createdPlan.id}`)
          
          // 展开新计划的section
          expandedSections[createdPlan.id] = true
          
          // 刷新计划列表
          await fetchProjectPlans()
          
          // 获取新计划下的BadCase
          console.log(`🔍 调用API: /api/projects/${projectId.value}/badcases?page=1&per_page=20&plan_id=${createdPlan.id}`)
          await fetchBadcasesByPlan(createdPlan.id, 1)
          
          // 立即根据新创建的计划过滤BadCase
          nextTick(() => {
            filterBadcasesByPlan(createdPlan.id)
          })
          
          console.log('✅ BadCase已成功关联到新计划')
        } else {
          console.error('❌ 创建计划失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('❌ 创建计划异常:', error)
        console.error('错误详情:', error.message)
      }
      
      console.log('=== BadCase计划创建完成 ===')
    }
    
    // 关联BadCase到计划
    const associateBadcaseWithPlan = async (badcaseId, planId) => {
      try {
        console.log(`🔗 开始关联BadCase ${badcaseId} 到计划 ${planId}`)
        
        // 调用API更新BadCase的plan_id
        const response = await updateBadcasePlan(badcaseId, planId)
        
        if (response && response.data && response.data.success) {
          console.log(`✅ BadCase ${badcaseId} 已成功关联到计划 ${planId}`)
          
          // 更新本地BadCase数据
          const badcaseIndex = badcases.value.findIndex(b => b.id === badcaseId)
          if (badcaseIndex !== -1) {
            badcases.value[badcaseIndex].plan_id = planId
            console.log('✅ 本地BadCase数据已更新')
          }
          
          // 同时更新filteredBadcases中的数据
          const filteredIndex = filteredBadcases.value.findIndex(b => b.id === badcaseId)
          if (filteredIndex !== -1) {
            filteredBadcases.value[filteredIndex].plan_id = planId
            console.log('✅ 本地过滤后的BadCase数据已更新')
          }
        } else {
          console.error('❌ 关联BadCase失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('❌ 关联BadCase异常:', error)
        console.error('错误详情:', error.message)
      }
    }
    
    /** 按 planId 和 cardId 解析应使用的列表 API
     *  优先使用 currentTypeFilter（当前视图类型），因为从卡片进入列表时视图类型是明确的
     *  当有 cardId 时，也可以使用 card 的类型 */
    const getPlanListApiKindByPlanId = (planId, cardId = null) => {
      // 优先使用 currentTypeFilter（当前视图类型）
      // 因为从卡片进入 bug/testcase 列表时，currentTypeFilter 是 'bug' 或 'testcase'
      // 而计划的 content_type 可能还是 'badcase'
      const typeFilter = currentTypeFilter.value
      if (typeFilter === 'bug') {
        console.log(`[getPlanListApiKindByPlanId] 使用 currentTypeFilter: bug`)
        return 'bug'
      }
      if (typeFilter === 'testcase') {
        console.log(`[getPlanListApiKindByPlanId] 使用 currentTypeFilter: test_case`)
        return 'test_case'
      }
      
      // 如果有 cardId，尝试使用 card 的类型
      if (cardId) {
        const card = filteredCards.value.find(c => c.id === cardId || c.id === parseInt(cardId))
        if (card && card.type) {
          console.log(`[getPlanListApiKindByPlanId] 使用Card类型: ${card.type}, cardId: ${cardId}`)
          const raw = card.type.toString().toLowerCase()
          if (raw === 'bug') return 'bug'
          if (raw === 'testcase' || raw === 'test_case') return 'test_case'
          return 'badcase'
        }
      }
      
      // 兜底使用计划的 content_type
      const numericPlanId = typeof planId === 'number' ? planId : parseInt(String(planId), 10)
      if (Number.isNaN(numericPlanId)) {
        console.log(`[getPlanListApiKindByPlanId] 无效planId，使用 currentPlanType: ${currentPlanType.value}`)
        return currentPlanType.value
      }
      const planObj = findPlanRecursive(projectPlans.value, numericPlanId)
      if (!planObj) {
        console.log(`[getPlanListApiKindByPlanId] 未找到计划，使用 currentPlanType: ${currentPlanType.value}`)
        return currentPlanType.value
      }
      // 以后不再从计划推导类型，统一回退当前视图类型
      return currentPlanType.value
    }
    
    // 根据计划ID调用API获取BadCase
    const fetchBadcasesByPlan = async (planId, page = 1, cardId = null) => {
      console.log(`=== fetchBadcasesByPlan 开始 ===`)
      console.log('计划ID:', planId)
      console.log('页码:', page)
      console.log('卡片ID:', cardId)
      console.log('项目ID:', projectId.value)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取BadCase数据')
        return
      }
      
      badcaseLoading.value = true
      try {
        // 构建API参数 - 处理数字或字符串类型的planId
        const params = {}
        
        // 转换为数字，如果有效则设置参数
        const numericPlanId = typeof planId === 'number' ? planId : parseInt(planId)
        
        // 如果有 cardId，优先使用 cardId 过滤（卡片分类型，计划不分类型）
        if (cardId) {
          params.card_id = cardId
          console.log(`🔍 按卡片ID过滤: cardId=${cardId}`)
        } else if (planId && !isNaN(numericPlanId)) {
          params.plan_id = numericPlanId
          console.log(`🔍 检索计划ID: ${numericPlanId} 的数据`)
        } else if (!cardId) {
          console.error('❌ 无效的计划ID:', planId, '类型:', typeof planId)
          return
        }
        
        console.log('📋 API参数:', params)

        const listKind = getPlanListApiKindByPlanId(planId, cardId)
        let response
        if (listKind === 'bug') {
          console.log(`🔍 调用 getProjectBugs，检索计划ID: ${planId}, 卡片ID: ${cardId}`)
          response = await getProjectBugs(projectId.value, page, badcasePerPage.value, params)
        } else if (listKind === 'test_case') {
          console.log(`🔍 调用 getProjectTestCases，检索计划ID: ${planId}, 卡片ID: ${cardId}`)
          response = await getProjectTestCases(projectId.value, page, badcasePerPage.value, params)
        } else {
          console.log(`🔍 调用 getProjectBadcases，检索计划ID: ${planId}`)
          response = await getProjectBadcases(projectId.value, page, badcasePerPage.value, params)
        }
        console.log('API响应:', response)
        
        if (response && response.data && response.data.success) {
          badcases.value = response.data.badcases || []
          filteredBadcases.value = [...badcases.value] // 初始化过滤后的BadCase
          totalBadcases.value = response.data.total || 0
          badcasePage.value = page
          
          console.log(`✅ 计划 ${planId} 的BadCase检索成功，共${badcases.value.length}个`)
          console.log(`📊 检索结果: 总数=${totalBadcases.value}, 当前页=${badcasePage.value}`)
          
          // 检查每个BadCase的数据
          badcases.value.forEach((badcase, index) => {
            console.log(`BadCase ${index + 1}:`, {
              id: badcase.id,
              title: badcase.title,
              status: badcase.status,
              assignee: badcase.assignee,
              plan_id: badcase.plan_id,
              card_id: badcase.card_id,
              created_at: badcase.created_at
            })
          })
          
          // 设置选中的计划并应用筛选条件
          selectedPlan.value = planId
          applyFilters()
          
          console.log('📊 过滤完成后的状态:')
          console.log('- badcases.value.length:', badcases.value.length)
          console.log('- filteredBadcases.value.length:', filteredBadcases.value.length)
          console.log('- selectedPlan.value:', selectedPlan.value)
          

        } else {
          console.error('获取BadCase数据失败:', response?.data?.error || '未知错误')
          badcases.value = []
          totalBadcases.value = 0
        }
      } catch (error) {
        console.error('获取BadCase数据异常:', error)
        console.error('错误详情:', error.message)
        console.error('错误堆栈:', error.stack)
        badcases.value = []
        totalBadcases.value = 0
      } finally {
        badcaseLoading.value = false
        console.log('=== fetchBadcasesByPlan 完成 ===')
      }
    }
    
    // 根据选择的计划过滤BadCase
    const filterBadcasesByPlan = (planId) => {
      console.log(`=== filterBadcasesByPlan 开始 ===`)
      console.log('计划ID:', planId)
      
      // 设置选中的计划
      selectedPlan.value = planId
      
      // 调用统一的筛选方法
      applyFilters()
      
      console.log(`=== filterBadcasesByPlan 完成 ===`)
    }


    /** 按 Tab 元数据恢复列表状态 */
    const applyPlanListTabState = async (meta) => {
      const m = meta || {}
      const { planId, urlContentType: uct } = m
      const numericPlanIdForState =
        planId != null && planId !== 'unplanned'
          ? typeof planId === 'number'
            ? planId
            : parseInt(String(planId), 10)
          : NaN
      if (!Number.isNaN(numericPlanIdForState) && numericPlanIdForState > 0) {
        // 与侧栏点计划一致时 meta.urlContentType 为 null；grep/modify 可按记录类型覆盖
        urlContentType.value = uct !== undefined ? uct : null
        selectedPlan.value = numericPlanIdForState
        // 获取卡片数据（统一卡片列表）
        await fetchCards()
        await nextTick()
        window.dispatchEvent(
          new CustomEvent('request-pending-modify-for-plan', {
            detail: { planId: numericPlanIdForState, suppressAutoOpenDetail: true }
          })
        )
      }
    }


    /** 首次进入 / 刷新后若尚无工作区 Tab，则根据当前列表状态补一条，保证默认也有 Tab 栏 */
    const ensureWorkbenchTabForCurrentView = () => {
      if (showMainEditor.value) return
      if (workbenchTabs.value.length > 0) return

      const st = selectedPlan.value
      const uct = urlContentType.value

      const numericPlanId =
        st != null && st !== 'unplanned'
          ? typeof st === 'number'
            ? st
            : parseInt(String(st), 10)
          : NaN

      if (!Number.isNaN(numericPlanId)) {
        const planObj = findPlanRecursive(projectPlans.value, numericPlanId)
        const title = truncateForTab(planObj?.name, t('tab.planFallback', { id: numericPlanId }))
        upsertWorkbenchTab({
          id: `plan-${numericPlanId}`,
          kind: 'plan-list',
          title,
          meta: { planId: numericPlanId, urlContentType: null }
        })
        activeWorkbenchTabId.value = `plan-${numericPlanId}`
        return
      }
    }

    const activateWorkbenchTab = async (tabId) => {
      const tab = workbenchTabs.value.find((t) => t.id === tabId)
      if (!tab) return
      activeWorkbenchTabId.value = tabId
      if (tab.kind === 'settings') {
        clearEmbeddedEditor()
        const p = tab.meta?.initialPane
        if (['account', 'team', 'preferences'].includes(p)) {
          appSettingsInitialPane.value = p
        }
        return
      }
      if (tab.kind === 'help') {
        clearEmbeddedEditor()
        return
      }
      if (tab.kind === 'notifications') {
        clearEmbeddedEditor()
        return
      }
      if (tab.kind === 'terminal-settings') {
        clearEmbeddedEditor()
        return
      }
      if (tab.kind === 'detail') {
        const { entityId, editorPlanType, showDiff, planId: metaPlan, cardId: metaCard } = tab.meta || {}
        let pid = metaPlan ?? null
        if (pid != null && pid !== '' && pid !== 'unplanned') {
          const n = typeof pid === 'number' ? pid : parseInt(String(pid), 10)
          pid = Number.isFinite(n) && n > 0 ? n : null
        } else pid = null
        if (pid == null && selectedPlan.value != null && selectedPlan.value !== '' && selectedPlan.value !== 'unplanned') {
          const sp = typeof selectedPlan.value === 'number' ? selectedPlan.value : parseInt(String(selectedPlan.value), 10)
          if (Number.isFinite(sp) && sp > 0) pid = sp
        }
        let cid = metaCard ?? null
        if (cid != null && cid !== '') {
          const cn = typeof cid === 'number' ? cid : parseInt(String(cid), 10)
          cid = Number.isFinite(cn) && cn > 0 ? cn : null
        } else cid = null
        mountEditorComponents(entityId, editorPlanType, !!showDiff, true, pid, cid)
        return
      }
      if (tab.kind === 'create') {
        const { editorPlanType, planId, cardId } = tab.meta || {}
        mountEditorComponents(null, editorPlanType, false, false, planId ?? null, cardId ?? null)
        return
      }
      if (tab.kind === 'type-list') {
        clearEmbeddedEditor()
        const { type, planId, cardId } = tab.meta || {}
        currentTypeFilter.value = type
        if (type === 'bug') urlContentType.value = 'bug'
        else if (type === 'testcase') urlContentType.value = 'test_case'
        else if (type === 'badcase') urlContentType.value = 'badcase'
        selectedPlan.value = planId
        // 切换到类型列表时，获取该卡片下的数据
        if (planId) {
          await nextTick()
          fetchBadcasesByPlan(planId, 1, cardId)
        }
        return
      }
      // plan-list Tab: restore type from meta
      if (tab.kind === 'plan-list') {
        clearEmbeddedEditor()
        const { planId, urlContentType: uctMeta, type } = tab.meta || {}
        let tf = type
        if (tf === undefined || tf === null || tf === '') {
          if (uctMeta === 'bug') tf = 'bug'
          else if (uctMeta === 'test_case') tf = 'testcase'
          else if (uctMeta === 'badcase') tf = 'badcase'
        }
        currentTypeFilter.value = tf || ''
        await applyPlanListTabState({ planId, urlContentType: uctMeta })
        return
      }
      clearEmbeddedEditor()
      await applyPlanListTabState(tab.meta || {})
    }

    const closeWorkbenchTab = async (tabId, e) => {
      if (e) e.stopPropagation()
      
      const idx = workbenchTabs.value.findIndex((t) => t.id === tabId)
      if (idx === -1) return
      const wasActive = activeWorkbenchTabId.value === tabId
      
      workbenchTabs.value.splice(idx, 1)
      if (!wasActive) {
        refreshBadcases()
        fetchProjectPlans()
        return
      }
      const next = workbenchTabs.value[idx] || workbenchTabs.value[idx - 1]
      if (next) {
        await activateWorkbenchTab(next.id)
      } else {
        activeWorkbenchTabId.value = null
        clearEmbeddedEditor()
        selectedPlan.value = null
        urlContentType.value = null
      }
      refreshBadcases()
      fetchProjectPlans()
      await nextTick()
      ensureWorkbenchTabForCurrentView()
    }

    const toggleWorkbenchTabMenu = () => {
      showWorkbenchTabMenu.value = !showWorkbenchTabMenu.value
    }

    const scrollActiveWorkbenchTabIntoView = () => {
      const strip = workbenchTabsStripRef.value
      if (!strip) return
      const activeEl = strip.querySelector('.workbench-tab.active')
      if (!activeEl) return
      activeEl.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    }

    /** 展开左侧计划树至某一计划（grep / modify / URL 展开共用） */
    const expandPlanTreeToPlanId = (targetId) => {
      if (targetId == null) return
      const tid = typeof targetId === 'number' ? targetId : parseInt(String(targetId), 10)
      if (Number.isNaN(tid)) return
      const findAndExpand = (plans, id, parents = []) => {
        for (const plan of plans) {
          if (plan.id === id) {
            parents.forEach((parentId) => {
              if (!expandedPlans.value.includes(parentId)) {
                expandedPlans.value.push(parentId)
              }
            })
            return true
          }
          if (plan.children && plan.children.length > 0) {
            if (findAndExpand(plan.children, id, [...parents, plan.id])) {
              return true
            }
          }
        }
        return false
      }
      findAndExpand(projectPlans.value, tid)
    }

    /**
     * grep / 沙箱预览跳转 / 对话 modify 列表定位：更新并激活对应「计划列表」Tab，
     * 与 activateWorkbenchTab + applyPlanListTabState 一致，避免仅改 selectedPlan 而用户仍停在别的 Tab。
     */
    const upsertAndActivatePlanListTab = async (meta) => {
      const m = meta || {}
      const { planId, urlContentType: uct } = m
      const numericPlanIdForTab =
        planId != null && planId !== 'unplanned'
          ? typeof planId === 'number'
            ? planId
            : parseInt(String(planId), 10)
          : NaN

      if (!Number.isNaN(numericPlanIdForTab) && numericPlanIdForTab > 0) {
        const planObj = findPlanRecursive(projectPlans.value, numericPlanIdForTab)
        const title = truncateForTab(planObj?.name, t('tab.planFallback', { id: numericPlanIdForTab }))
        logListNav('openPlanListTab', {
          planId: numericPlanIdForTab,
          tabTitle: title,
          urlContentType: uct
        })
        upsertWorkbenchTab({
          id: `plan-${numericPlanIdForTab}`,
          kind: 'plan-list',
          title,
          meta: { planId: numericPlanIdForTab, urlContentType: uct !== undefined ? uct : null }
        })
        await activateWorkbenchTab(`plan-${numericPlanIdForTab}`)
        await nextTick()
        scrollActiveWorkbenchTabIntoView()
      }
    }

    /**
     * grep / 沙箱：打开「某卡片下」的类型列表 Tab（Bug / BadCase / 测试用例），与 CardPanel 点进列表一致。
     */
    const upsertAndActivateTypeListTab = async ({ planId, cardId, type, cardTitle }) => {
      const pid =
        planId != null && planId !== 'unplanned'
          ? typeof planId === 'number'
            ? planId
            : parseInt(String(planId), 10)
          : NaN
      const cid =
        cardId != null ? (typeof cardId === 'number' ? cardId : parseInt(String(cardId), 10)) : NaN
      if (Number.isNaN(pid) || pid <= 0 || Number.isNaN(cid) || cid <= 0) return
      const tl =
        type === 'badcase'
          ? 'badcase'
          : type === 'testcase' || type === 'test_case'
            ? 'testcase'
            : 'bug'
      const tabId = `type-list-${tl}-${pid}-${cid}`
      const title = truncateForTab(
        cardTitle || `${tl}列表`,
        t('tab.planFallback', { id: pid })
      )
      logListNav('openTypeListTab', {
        planId: pid,
        cardId: cid,
        type: tl,
        tabTitle: title,
        tabId
      })
      upsertWorkbenchTab({
        id: tabId,
        kind: 'type-list',
        title,
        meta: { type: tl, planId: pid, cardTitle, cardId: cid }
      })
      await activateWorkbenchTab(tabId)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    const onWorkbenchTabStripMouseDown = (e) => {
      if (e.button !== 0) return
      if (e.target.closest?.('.workbench-tab-close')) return
      const el = workbenchTabsStripRef.value
      if (!el) return
      _tabStripDrag.active = true
      _tabStripDrag.startX = e.clientX
      _tabStripDrag.startScroll = el.scrollLeft
      _tabStripDrag.dragged = false
      workbenchTabStripDraggingUI.value = false
      const onMove = (ev) => {
        if (!_tabStripDrag.active) return
        const dx = ev.clientX - _tabStripDrag.startX
        if (Math.abs(dx) > 4) {
          _tabStripDrag.dragged = true
          workbenchTabStripDraggingUI.value = true
        }
        el.scrollLeft = _tabStripDrag.startScroll - dx
      }
      const onUp = () => {
        _tabStripDrag.active = false
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        setTimeout(() => {
          workbenchTabStripDraggingUI.value = false
        }, 0)
      }
      document.addEventListener('mousemove', onMove, { passive: true })
      document.addEventListener('mouseup', onUp)
    }

    const onWorkbenchTabStripWheel = (e) => {
      const el = workbenchTabsStripRef.value
      if (!el) return
      if (e.shiftKey && Math.abs(e.deltaY) > 0) {
        e.preventDefault()
        el.scrollLeft += e.deltaY
      }
    }

    const onWorkbenchTabButtonClick = async (tabId) => {
      if (_tabStripDrag.dragged) {
        _tabStripDrag.dragged = false
        return
      }
      await activateWorkbenchTab(tabId)
    }

    const onWorkbenchMenuSelectTab = async (tabId) => {
      showWorkbenchTabMenu.value = false
      await activateWorkbenchTab(tabId)
    }

    const closeAllWorkbenchTabs = async () => {
      showWorkbenchTabMenu.value = false
      workbenchTabs.value = []
      activeWorkbenchTabId.value = null
      clearEmbeddedEditor()
      selectedPlan.value = null
      urlContentType.value = null
      refreshBadcases()
      fetchProjectPlans()
      await nextTick()
      ensureWorkbenchTabForCurrentView()
    }

    watch(showWorkbenchTabMenu, (open) => {
      workbenchMenuOutsideCleanup?.()
      workbenchMenuOutsideCleanup = null
      if (!open) return
      nextTick(() => {
        // 延后注册，避免与打开菜单的同一轮点击/冒泡冲突导致一打开就关
        setTimeout(() => {
          const fn = (e) => {
            const el = workbenchMenuRef.value
            if (el && !el.contains(e.target)) {
              showWorkbenchTabMenu.value = false
            }
          }
          document.addEventListener('mousedown', fn, true)
          workbenchMenuOutsideCleanup = () => document.removeEventListener('mousedown', fn, true)
        }, 16)
      })
    })

    watch(showHistory, (open) => {
      aiHistoryOutsideCleanup?.()
      aiHistoryOutsideCleanup = null
      if (!open) return
      nextTick(() => {
        setTimeout(() => {
          const fn = (e) => {
            const el = aiHistoryDropdownRef.value
            if (el && !el.contains(e.target)) {
              showHistory.value = false
            }
          }
          document.addEventListener('mousedown', fn, true)
          aiHistoryOutsideCleanup = () => document.removeEventListener('mousedown', fn, true)
        }, 16)
      })
    })

    watch(showDropdown, (open) => {
      aiMoreOutsideCleanup?.()
      aiMoreOutsideCleanup = null
      if (!open) return
      nextTick(() => {
        setTimeout(() => {
          const fn = (e) => {
            const el = aiMoreDropdownRef.value
            if (el && !el.contains(e.target)) {
              showDropdown.value = false
            }
          }
          document.addEventListener('mousedown', fn, true)
          aiMoreOutsideCleanup = () => document.removeEventListener('mousedown', fn, true)
        }, 16)
      })
    })

    watch(activeWorkbenchTabId, () => {
      nextTick(() => scrollActiveWorkbenchTabIntoView())
    })

    /** Bug/BadCase/TestCase 列表用 filteredBadcases；迭代卡片总表用 filteredCards */
    const selectionListForCurrentView = computed(() => {
      const tf = (currentTypeFilter.value ?? '').toString().toLowerCase()
      if (tf === 'badcase' || tf === 'bug' || tf === 'testcase') {
        return filteredBadcases.value || []
      }
      return filteredCards.value || []
    })

    const toggleSelectAll = () => {
      const list = selectionListForCurrentView.value
      const ids = list.map((x) => x.id).filter((id) => id != null)
      const allSelected =
        ids.length > 0 && ids.every((id) => selectedTasks.value.includes(id))
      if (allSelected) {
        selectedTasks.value = []
        selectAll.value = false
      } else {
        selectedTasks.value = [...ids]
        selectAll.value = ids.length > 0
      }
    }

    const toggleTaskSelection = (taskId) => {
      const index = selectedTasks.value.indexOf(taskId)
      if (index > -1) {
        selectedTasks.value.splice(index, 1)
      } else {
        selectedTasks.value.push(taskId)
      }
      const list = selectionListForCurrentView.value
      const ids = list.map((x) => x.id).filter((id) => id != null)
      selectAll.value =
        ids.length > 0 &&
        selectedTasks.value.length === ids.length &&
        ids.every((id) => selectedTasks.value.includes(id))
    }

    const handleCardPanelRefresh = async () => {
      selectedTasks.value = []
      selectAll.value = false
      await fetchCards(1)
    }

    const onCardListPage = (p) => {
      if (typeof p !== 'number' || p < 1) return
      selectedTasks.value = []
      selectAll.value = false
      fetchCards(p)
    }

    const onCardSearchSubmit = () => {
      selectedTasks.value = []
      selectAll.value = false
      fetchCards(1)
    }

    const onWorkbenchListPage = (p) => {
      if (typeof p !== 'number' || p < 1) return
      selectedTasks.value = []
      selectAll.value = false
      const tab = workbenchTabs.value.find((t) => t.id === activeWorkbenchTabId.value)
      const cardId = tab?.meta?.cardId ?? null
      const planId = selectedPlan.value
      if (planId == null || planId === '') return
      fetchBadcasesByPlan(planId, p, cardId)
    }

    // 编辑 BadCase/Bug/TestCase（统一入口）
    // 根据当前视图类型决定编辑器类型：bug列表用bug，badcase列表用badcase
    const editBadcase = (badcaseId) => {
      console.log('=== editBadcase函数被调用 ===')
      console.log('BadCase/Bug/TestCase ID:', badcaseId)
      console.log('项目ID:', projectId.value)
      console.log('当前视图类型 currentTypeFilter:', currentTypeFilter.value)

      // 根据当前视图类型决定编辑器类型，而不是依赖计划的 content_type
      // 这样从卡片进入 bug 列表时，点击 bug 记录会正确打开 bug 编辑器
      const editorType = currentTypeFilter.value === 'bug' ? 'bug' 
                       : currentTypeFilter.value === 'testcase' ? 'test_case'
                       : currentPlanType.value

      console.log('使用的编辑器类型:', editorType)
      
      // 统一改为主区域挂载编辑，避免 overlay 顶栏/布局重复
      openMainEditor(badcaseId, editorType, false)
    }
    
    // 编辑卡片：必须用 itemType=card 走 openMainEditor 内解析（type/source_id），禁止用 currentPlanType（多为 badcase 会误开 NewBadcase）
    const editCard = (cardId) => {
      console.log('[editCard] 卡片编辑入口', {
        cardId,
        currentPlanType: currentPlanType.value,
        note: '统一 openMainEditor(cardId, "card")，避免计划 content_type 与卡片实体类型不一致'
      })
      openMainEditor(cardId, 'card', false)
    }
    
    // 快速更新卡片（行内编辑）
    const handleQuickUpdate = async (updateData) => {
      console.log('[handleQuickUpdate] 快速更新卡片:', updateData)
      console.log('[handleQuickUpdate] 传递的 type:', updateData.type)
      
      try {
        const response = await updateCard(updateData.id, {
          title: updateData.title,
          type: updateData.type
        })
        
        console.log('[handleQuickUpdate] 更新响应:', response.data)
        const updatedCard = response.data.data ?? response.data.card
        console.log('[handleQuickUpdate] 后端返回的卡片:', updatedCard)
        
        if (response.data.success) {
          // 更新列表中的卡片数据
          const index = filteredCards.value.findIndex(c => c.id === updateData.id)
          if (index !== -1) {
            // 使用后端返回的完整卡片数据（API 为 data，兼容 card）
            if (updatedCard && typeof updatedCard === 'object') {
              filteredCards.value[index] = { ...filteredCards.value[index], ...updatedCard }
            } else {
              filteredCards.value[index] = {
                ...filteredCards.value[index],
                title: updateData.title,
                type: updateData.type
              }
            }
            console.log('[handleQuickUpdate] 更新后的卡片:', filteredCards.value[index])
          }
        } else {
          console.error('[handleQuickUpdate] 更新失败:', response.data.error)
          alert(response.data.error || '更新失败')
        }
      } catch (err) {
        console.error('[handleQuickUpdate] 更新卡片失败:', err)
        alert('更新卡片失败')
      }
    }
    
    // 打开编辑覆盖层
    // 在主区域挂载 Editor（替代 overlay）
    const openMainEditor = async (itemId, itemType, showDiff = false) => {
      /** 历史误调用：openMainEditor('bug', 14) — 第二参应是类型；若第一参为类型名且第二参为数字则交换 */
      const typeToken = new Set(['bug', 'badcase', 'bad_case', 'testcase', 'test_case', 'card'])
      let mid = itemId
      let mty = itemType
      const secondIsNumericId =
        typeof mty === 'number'
          ? Number.isFinite(mty)
          : typeof mty === 'string' && /^\d+$/.test(String(mty).trim())
      if (typeToken.has(String(mid).toLowerCase()) && secondIsNumericId) {
        console.warn(
          '[MAIN-EDITOR] 已自动纠正参数顺序：应为 openMainEditor(实体id, 类型)。曾误传 (类型字符串, id)。',
          { 误传第一参: mid, 误传第二参: mty }
        )
        const rid = typeof mty === 'number' ? mty : parseInt(String(mty).trim(), 10)
        let ty = String(mid).toLowerCase()
        if (ty === 'bad_case') ty = 'badcase'
        mty = ty === 'test_case' ? 'testcase' : ty
        mid = rid
      }
      itemId = mid
      itemType = mty

      console.log('[MAIN-EDITOR] 打开主区域编辑:', { itemId, itemType, showDiff })

      /** target=card 时 itemId 为 Card.id；详情 API 需要 Bug/BadCase/TestCase 的 source_id，且组件不能误用 mapToEditorPlanType 默认成 badcase */
      let editorSourceType = itemType
      let entityIdForEditor = itemId
      let cardRowForId = null
      if (itemType === 'card') {
        cardRowForId =
          (Array.isArray(filteredCards.value) && filteredCards.value.find((c) => c.id == itemId)) ||
          (Array.isArray(cards.value) && cards.value.find((c) => c.id == itemId)) ||
          null
        const cid =
          typeof itemId === 'number' ? itemId : parseInt(String(itemId), 10)
        if (!cardRowForId && Number.isFinite(cid) && cid > 0) {
          try {
            const res = await getCardDetail(cid)
            const c = res?.data?.data ?? res?.data?.card
            if (res?.data?.success && c && (c.id != null || c.title != null || c.type != null)) {
              cardRowForId = {
                id: c.id ?? cid,
                type: c.type,
                source_type: c.source_type,
                source_id: c.source_id,
                title: c.title,
                plan_id: c.plan_id
              }
              console.log('[MAIN-EDITOR] itemType=card 本地无行，已用 getCardDetail 补全', {
                cardId: cid,
                type: cardRowForId.type,
                source_type: cardRowForId.source_type,
                source_id: cardRowForId.source_id
              })
            }
          } catch (e) {
            console.warn('[MAIN-EDITOR] getCardDetail 失败，无法解析卡片实体', cid, e)
          }
        }
        if (cardRowForId) {
          const raw = String(cardRowForId.type || cardRowForId.source_type || '').toLowerCase()
          if (raw === 'bug') editorSourceType = 'bug'
          else if (raw === 'testcase' || raw === 'test_case') editorSourceType = 'test_case'
          else if (raw === 'bad_case' || raw === 'badcase') editorSourceType = 'badcase'
          else editorSourceType = 'badcase'
          const sid = cardRowForId.source_id
          if (sid != null && sid !== '') {
            const sn = typeof sid === 'number' ? sid : parseInt(String(sid), 10)
            if (Number.isFinite(sn) && sn > 0) entityIdForEditor = sn
          }
          console.log('[MAIN-EDITOR] itemType=card 已解析卡片行', {
            cardId: itemId,
            rowType: cardRowForId.type,
            source_type: cardRowForId.source_type,
            source_id: cardRowForId.source_id,
            editorSourceType,
            entityIdForEditor
          })
        } else {
          console.warn('[MAIN-EDITOR] itemType=card 但本地无行且 getCardDetail 未补全', {
            itemId,
            filteredLen: filteredCards.value?.length,
            cardsLen: cards.value?.length,
            后果: '随后 mapToEditorPlanType(card)→badcase，可能误请求 /badcases/:id'
          })
        }
      }

      const et = mapToEditorPlanType(editorSourceType)
      console.log('[MAIN-EDITOR] 映射后的编辑器类型:', et, {
        editorSourceType,
        entityIdForEditor,
        cardId: itemType === 'card' ? itemId : null
      })
      const returnTo = activeWorkbenchTabId.value
      const tid = `detail-${et}-${entityIdForEditor}`
      const curTab = workbenchTabs.value.find((t) => t.id === returnTo)
      // 根据类型在正确的数组中查找（card 不要用 badcases 按 id 误命中）
      let row = null
      if (itemType === 'card') {
        row = cardRowForId
      } else {
        row = badcases.value.find((b) => b.id == itemId)
      }
      if (!row && itemType !== 'card') {
        row =
          (Array.isArray(filteredCards.value) && filteredCards.value.find((c) => c.id == itemId)) ||
          (Array.isArray(cards.value) && cards.value.find((c) => c.id == itemId)) ||
          null
      }
      const title = truncateForTab(row?.title, '编辑')

      let planIdForEditor = null
      const metaPlan = curTab?.meta?.planId
      if (metaPlan != null && metaPlan !== '' && metaPlan !== 'unplanned') {
        const mp = typeof metaPlan === 'number' ? metaPlan : parseInt(String(metaPlan), 10)
        if (Number.isFinite(mp) && mp > 0) planIdForEditor = mp
      }
      if (planIdForEditor == null && selectedPlan.value != null && selectedPlan.value !== '' && selectedPlan.value !== 'unplanned') {
        const sp = typeof selectedPlan.value === 'number' ? selectedPlan.value : parseInt(String(selectedPlan.value), 10)
        if (Number.isFinite(sp) && sp > 0) planIdForEditor = sp
      }
      if (planIdForEditor == null && row?.plan_id != null && row.plan_id !== '') {
        const pp = parseInt(String(row.plan_id), 10)
        if (Number.isFinite(pp) && pp > 0) planIdForEditor = pp
      }

      let cardIdForEditor = curTab?.meta?.cardId ?? null
      if (itemType === 'card') {
        const cn = typeof itemId === 'number' ? itemId : parseInt(String(itemId), 10)
        if (Number.isFinite(cn) && cn > 0) cardIdForEditor = cn
      } else if (cardIdForEditor == null && row) {
        const rc = row.card_id ?? row.cardId
        if (rc != null && rc !== '') {
          const cn = typeof rc === 'number' ? rc : parseInt(String(rc), 10)
          cardIdForEditor = Number.isFinite(cn) && cn > 0 ? cn : null
        }
      }

      upsertWorkbenchTab({
        id: tid,
        kind: 'detail',
        title,
        meta: {
          entityId: entityIdForEditor,
          editorPlanType: et,
          showDiff: !!showDiff,
          returnTo,
          planId: planIdForEditor,
          cardId: cardIdForEditor
        }
      })
      activeWorkbenchTabId.value = tid
      mountEditorComponents(entityIdForEditor, et, showDiff, true, planIdForEditor, cardIdForEditor)
    }
    
    const openMainCreateEditor = (itemType, planId = null) => {
      const et = mapToEditorPlanType(itemType)
      const returnTo = activeWorkbenchTabId.value
      const pidKey = planId == null || planId === '' ? 'unplanned' : String(planId)
      const tid = `create-${et}-${pidKey}`
      const titleMap = {
        badcase: '新建 BadCase',
        bug: '新建 Bug',
        test_case: '新建 测试用例'
      }
      upsertWorkbenchTab({
        id: tid,
        kind: 'create',
        title: truncateForTab(titleMap[et] || '新建', '新建'),
        meta: { editorPlanType: et, planId: planId ?? null, returnTo }
      })
      activeWorkbenchTabId.value = tid
      mountEditorComponents(null, et, false, false, planId ?? null)
    }

    function openNewBadcaseFromTerminal(text) {
      const snippet = String(text || '').trim()
      if (!snippet) return
      badcaseDraftPreset.value = { token: Date.now(), description: snippet.slice(0, 12000) }
      const pid =
        selectedPlan.value && selectedPlan.value !== 'unplanned'
          ? typeof selectedPlan.value === 'number'
            ? selectedPlan.value
            : parseInt(String(selectedPlan.value), 10)
          : null
      openMainCreateEditor('badcase', Number.isFinite(pid) ? pid : null)
    }
    provide('openNewBadcaseFromTerminal', openNewBadcaseFromTerminal)

    function openNewBugFromTerminal(text) {
      const snippet = String(text || '').trim()
      if (!snippet) return
      bugDraftPreset.value = { token: Date.now(), description: snippet.slice(0, 12000) }
      const pid =
        selectedPlan.value && selectedPlan.value !== 'unplanned'
          ? typeof selectedPlan.value === 'number'
            ? selectedPlan.value
            : parseInt(String(selectedPlan.value), 10)
          : null
      openMainCreateEditor('bug', Number.isFinite(pid) ? pid : null)
    }
    provide('openNewBugFromTerminal', openNewBugFromTerminal)

    function openNewTestcaseFromTerminal(text) {
      const snippet = String(text || '').trim()
      if (!snippet) return
      testcaseDraftPreset.value = { token: Date.now(), description: snippet.slice(0, 12000) }
      const pid =
        selectedPlan.value && selectedPlan.value !== 'unplanned'
          ? typeof selectedPlan.value === 'number'
            ? selectedPlan.value
            : parseInt(String(selectedPlan.value), 10)
          : null
      openMainCreateEditor('test_case', Number.isFinite(pid) ? pid : null)
    }
    provide('openNewTestcaseFromTerminal', openNewTestcaseFromTerminal)

    const closeMainEditor = async () => {
      console.log('[MAIN-EDITOR] 关闭主区域编辑')
      const tid = activeWorkbenchTabId.value
      const tab = tid ? workbenchTabs.value.find((t) => t.id === tid) : null
      if (tab?.kind === 'detail' || tab?.kind === 'create') {
        const returnTo = tab?.meta?.returnTo
        const canReturn =
          returnTo &&
          returnTo !== tid &&
          workbenchTabs.value.some((t) => t.id === returnTo)

        // 先切换 active 到来源 Tab，让 closeWorkbenchTab 走"非 active 关闭"的分支
        if (canReturn) {
          activeWorkbenchTabId.value = returnTo
        }
        clearEmbeddedEditor()
        await closeWorkbenchTab(tid, null)
        if (canReturn) {
          await activateWorkbenchTab(returnTo)
        }
      } else {
        clearEmbeddedEditor()
        refreshBadcases()
        fetchProjectPlans()
      }
    }
    
    const goToDashboard = () => {
      router.push('/dashboard')
    }

    /** 与 agents/tools/modify_tool._sanitize_title_modifications 对齐，用于前端采纳 URL */
    const titleChangeIntentInNaturalQuery = (nq) => {
      const s = String(nq || '').trim()
      if (!s) return false
      const markers = [
        '标题改为',
        '改标题',
        '标题改成',
        '重命名',
        '改名为',
        '改成叫',
        '名称改为',
        '题目改为',
        'rename',
        'title to',
        'change title'
      ]
      if (markers.some((m) => s.includes(m))) return true
      const sl = s.toLowerCase()
      return (
        sl.includes('title') &&
        (sl.includes('rename') || sl.includes('change') || s.includes('改为'))
      )
    }

    /**
     * 列表点 √ 采纳：去掉模型误带的 title（界面可能只画了状态 diff，但 payload 里仍有 title）。
     * restorePendingDiffReviews 恢复的 pending 常无 _naturalQuery，必须在发 POST 前剔除。
     */
    const pruneSpuriousTitleForAdopt = (modifyData, modifications) => {
      if (!modifications || typeof modifications !== 'object') return
      // Card 列表采纳必须带上 title，不能用 Bug 的「误带标题」规则剔除
      if (modifyData?._target === 'card') return
      if (!Object.prototype.hasOwnProperty.call(modifications, 'title')) return
      const otherKeys = Object.keys(modifications).filter((k) => k !== 'title')
      const hasOther = otherKeys.length > 0
      const tv = modifyData?.title
      const oldT =
        tv && typeof tv === 'object' && 'old' in tv ? String(tv.old ?? '').trim() : ''
      const newT =
        tv && typeof tv === 'object' && 'new' in tv ? String(tv.new ?? '').trim() : ''
      if (oldT && newT && oldT === newT) {
        delete modifications.title
        return
      }
      const nq = typeof modifyData?._naturalQuery === 'string' ? modifyData._naturalQuery : ''
      const wantsTitle = titleChangeIntentInNaturalQuery(nq)
      if (hasOther && !wantsTitle) {
        delete modifications.title
        return
      }
      // 仅有 title 且无改标题用语：与后端「仅 title」sanitize 对齐，避免误写 Bug.title 进而列表展示串台
      if (!hasOther && !wantsTitle) {
        delete modifications.title
      }
    }
    
    // 确认修改（单条）。opts.skipRestoreFetch=true 时不在末尾 restore/拉列表，供连续组合批末尾统一执行，减少闪烁。
    const confirmModify = async (bugId, opts = {}) => {
      const skipRestoreFetch = opts.skipRestoreFetch === true
      console.log('[MODIFY] 确认修改 Bug:', bugId, skipRestoreFetch ? '(batch中间步，defer restore/fetch)' : '')
      const modifyData = pendingModifications.value[bugId]
      if (!modifyData) {
        console.log('[MODIFY] 没有待修改数据')
        return
      }
      
      // 获取目标类型（优先使用保存的类型，其次根据当前计划类型推断）
      const targetType = modifyData._target || (currentPlanType.value === 'bug' ? 'bug' : (currentPlanType.value === 'test_case' ? 'testcase' : 'badcase'))
      console.log('[MODIFY] 目标类型:', targetType, '_target:', modifyData._target, 'currentPlanType:', currentPlanType.value)
      
      // 转换 modifyData 格式: { field: { old, new } } -> { field: new_value }
      const modifications = {}
      const oldValues = {}  // 保存旧值用于回滚
      for (const [field, value] of Object.entries(modifyData)) {
        if (field === '_target' || field === '_messageId' || field === '_naturalQuery') continue  // 跳过内部字段
        if (typeof value === 'object' && 'new' in value) {
          modifications[field] = value.new
          oldValues[field] = value.old
        } else {
          modifications[field] = value
        }
      }

      pruneSpuriousTitleForAdopt(modifyData, modifications)

      console.log(
        '[MODIFY_ADOPT] bugId=%s keys=%s title_after_prune=%s',
        bugId,
        Object.keys(modifications).join(','),
        modifications.title !== undefined ? String(modifications.title).slice(0, 80) : '(omit)'
      )
      
      // ======== 乐观更新：立即更新 UI ========
      let badcaseRow = null
      let cardRow = null
      if (targetType === 'card') {
        cardRow = cards.value.find((c) => Number(c.id) === Number(bugId))
        if (cardRow) {
          for (const [field, value] of Object.entries(modifications)) {
            if (Object.prototype.hasOwnProperty.call(cardRow, field)) {
              cardRow[field] = value
            }
          }
        }
      } else {
        // 采纳路径不写 title：Bug.title 与迭代卡片标题解耦，避免列表「卡片标题」随误写跳动
        const optimisticMods = { ...modifications }
        delete optimisticMods.title
        badcaseRow = badcases.value.find((b) => b.id === bugId)
        if (badcaseRow) {
          for (const [field, value] of Object.entries(optimisticMods)) {
            if (badcaseRow.hasOwnProperty(field)) {
              badcaseRow[field] = value
            }
          }
        }
      }
      
      // 2. 立即清除待修改标记
      const newPending = { ...pendingModifications.value }
      delete newPending[bugId]
      pendingModifications.value = newPending
      
      console.log('[MODIFY] 已清除 pendingModifications，bugId:', bugId)
      console.log('[MODIFY] 清除后的 pendingModifications:', pendingModifications.value)
      
      // 3. 立即通知对话区更新状态
      const event = new CustomEvent('modify-confirmed', {
        detail: { targetId: bugId },
        bubbles: true
      })
      window.dispatchEvent(event)
      
      console.log('[MODIFY] UI 已乐观更新')
      
      // 必须 await 到 resolve + restore 完成，否则连续组内多条并发会互相把对方从 diff-reviews 再次刷回列表
      return fetch(`${BACKEND_BASE_URL}/api/projects/${projectId.value}/modify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',  // 携带 cookies
        body: JSON.stringify({
          target: targetType,
          target_id: bugId,
          modifications: modifications,
          confirm: true,
          message_id: modifyData._messageId,
          natural_query:
            typeof modifyData._naturalQuery === 'string' ? modifyData._naturalQuery : ''
        })
      })
      .then((response) => response.json())
      .then(async (result) => {
        console.log('[MODIFY] 后端修改结果:', result)
        if (result.success) {
          // diff_review_state 在 POST /modify 内已同步删除，无需再 resolve confirm
          if (!skipRestoreFetch) {
            try {
              await restorePendingDiffReviews()
            } catch (e) {
              console.warn('[DIFF] restorePendingDiffReviews 失败:', e)
            }
            fetchBadcases()
            // 计划下「卡片」总览：刷新 Card，避免仅刷新了 Bug 行而卡片标题与 Card 表不一致
            if (!currentTypeFilter.value) {
              fetchCards(1).catch((e) => console.warn('[MODIFY] fetchCards 失败:', e))
            }
          }
          return result
        }
        console.error('[MODIFY] 后端修改失败，回滚 UI:', result.error)
        const rollbackRow = targetType === 'card' ? cardRow : badcaseRow
        if (rollbackRow) {
          for (const [field, value] of Object.entries(oldValues)) {
            if (rollbackRow.hasOwnProperty(field)) {
              rollbackRow[field] = value
            }
          }
        }
        pendingModifications.value[bugId] = modifyData
        return result
      })
      .catch((error) => {
        console.error('[MODIFY] 后端请求失败，回滚 UI:', error)
        const rollbackRow = targetType === 'card' ? cardRow : badcaseRow
        if (rollbackRow) {
          for (const [field, value] of Object.entries(oldValues)) {
            if (rollbackRow.hasOwnProperty(field)) {
              rollbackRow[field] = value
            }
          }
        }
        pendingModifications.value[bugId] = modifyData
        throw error
      })
    }

    /** 连续多条一次 HTTP：POST /modify body.items；后端单线程顺序落库并更新 diff_review_state */
    const confirmModifyBatch = async (groupIds) => {
      const snapshots = []
      for (const bugId of groupIds) {
        const modifyData = pendingModifications.value[bugId]
        if (!modifyData) continue
        const modifications = {}
        const oldValues = {}
        for (const [field, value] of Object.entries(modifyData)) {
          if (field === '_target' || field === '_messageId' || field === '_naturalQuery') continue
          if (typeof value === 'object' && value !== null && 'new' in value) {
            modifications[field] = value.new
            oldValues[field] = value.old
          } else {
            modifications[field] = value
          }
        }
        pruneSpuriousTitleForAdopt(modifyData, modifications)
        snapshots.push({ bugId, modifyData, modifications, oldValues })
      }
      if (snapshots.length === 0) return
      if (snapshots.length === 1) {
        return confirmModify(snapshots[0].bugId)
      }

      const targetType =
        snapshots[0].modifyData._target ||
        (currentPlanType.value === 'bug'
          ? 'bug'
          : currentPlanType.value === 'test_case'
            ? 'testcase'
            : 'badcase')
      const messageId = snapshots[0].modifyData._messageId
      const items = snapshots.map((s) => ({
        target_id: s.bugId,
        modifications: s.modifications,
        natural_query:
          typeof s.modifyData._naturalQuery === 'string' ? s.modifyData._naturalQuery : ''
      }))

      const rollback = () => {
        for (const s of snapshots) {
          const row = badcases.value.find((b) => b.id === s.bugId)
          if (row) {
            for (const [field, value] of Object.entries(s.oldValues)) {
              if (row.hasOwnProperty(field)) row[field] = value
            }
          }
        }
        const next = { ...pendingModifications.value }
        for (const s of snapshots) {
          next[s.bugId] = s.modifyData
        }
        pendingModifications.value = next
      }

      for (const s of snapshots) {
        const row = badcases.value.find((b) => b.id === s.bugId)
        if (row) {
          const om = { ...s.modifications }
          delete om.title
          for (const [field, value] of Object.entries(om)) {
            if (row.hasOwnProperty(field)) row[field] = value
          }
        }
      }
      const newPending = { ...pendingModifications.value }
      for (const s of snapshots) delete newPending[s.bugId]
      pendingModifications.value = newPending

      for (const s of snapshots) {
        window.dispatchEvent(
          new CustomEvent('modify-confirmed', {
            detail: { targetId: s.bugId },
            bubbles: true
          })
        )
      }

      try {
        const response = await fetch(`${BACKEND_BASE_URL}/api/projects/${projectId.value}/modify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            confirm: true,
            target: targetType,
            message_id: messageId,
            items
          })
        })
        const result = await response.json()
        if (result.success) {
          try {
            await restorePendingDiffReviews()
          } catch (e) {
            console.warn('[DIFF] restorePendingDiffReviews 失败:', e)
          }
          fetchBadcases()
          if (!currentTypeFilter.value) {
            fetchCards(1).catch((e) => console.warn('[MODIFY] fetchCards 失败:', e))
          }
          return result
        }
        console.error('[MODIFY] 批量采纳失败:', result.error)
        rollback()
        return result
      } catch (error) {
        console.error('[MODIFY] 批量请求异常:', error)
        rollback()
        throw error
      }
    }
    
    // 取消修改。opts.skipRestore=true 时不在末尾 restore，供连续组批量末尾统一 restore。
    const cancelModify = async (bugId, opts = {}) => {
      const skipRestore = opts.skipRestore === true
      console.log('[MODIFY] 取消修改 Bug:', bugId, skipRestore ? '(batch中间步，defer restore)' : '')
      const modifyData = pendingModifications.value[bugId]
      // 创建新对象触发响应式更新
      const newPending = { ...pendingModifications.value }
      delete newPending[bugId]
      pendingModifications.value = newPending
      
      // 通知对话区更新状态（标记为已取消）
      const event = new CustomEvent('modify-cancelled', {
        detail: { targetId: bugId },
        bubbles: true
      })
      window.dispatchEvent(event)
      await resolveDiffReviewState({
        target: modifyData?._target || (currentPlanType.value === 'bug' ? 'bug' : (currentPlanType.value === 'test_case' ? 'testcase' : 'badcase')),
        targetId: bugId,
        action: 'reject',
        messageId: modifyData?._messageId
      })
      const midClear = safeIntFkForDiffApi(modifyData?._messageId)
      if (modifyData?._pendingDelete && midClear != null) {
        try {
          await clearChatMessageDeleteNavigation(midClear, { cancel: true })
        } catch (e) {
          console.warn('[DELETE] 取消时清空 delete_navigation 失败:', e)
        }
      }
      if (!skipRestore) {
        await restorePendingDiffReviews()
      }
    }

    /** 侧栏列表与 modify 一致：待删行 ✓ 真正删除、✗ 取消（清预览） */
    const pendingDeletePlanId = computed(() => {
      const pm = pendingModifications.value
      for (const k of Object.keys(pm)) {
        const v = pm[k]
        if (v?._pendingDelete && String(v._target || '').toLowerCase() === 'plan') {
          const n = Number(k)
          if (Number.isFinite(n) && n > 0) return n
        }
      }
      return null
    })

    const normalizePendingDeleteTarget = (modifyData) => {
      const targetType = String(modifyData?._target || 'bug')
        .toLowerCase()
        .replace(/-/g, '_')
      if (targetType === 'test_case') return 'testcase'
      if (targetType === 'bad_case') return 'badcase'
      return targetType
    }

    const deleteApiForNormalizedTarget = (normalizedTarget, tid) => {
      switch (normalizedTarget) {
        case 'card':
          return deleteCard(tid)
        case 'badcase':
          return deleteBadcase(tid)
        case 'bug':
          return deleteBug(tid)
        case 'testcase':
          return deleteTestCase(tid)
        case 'plan':
          return deletePlanApi(tid)
        default:
          return Promise.reject(new Error(`unknown delete target: ${normalizedTarget}`))
      }
    }

    const confirmDelete = async (targetId, opts = {}) => {
      const skipRestoreFetch = opts.skipRestoreFetch === true
      const tid = Number(targetId)
      const modifyData = pendingModifications.value[tid]
      if (!modifyData?._pendingDelete) return

      const normalizedTarget = normalizePendingDeleteTarget(modifyData)

      try {
        const res = await deleteApiForNormalizedTarget(normalizedTarget, tid)
        if (res?.data && res.data.success === false) {
          throw new Error(res?.data?.error || 'delete failed')
        }

        const newPending = { ...pendingModifications.value }
        delete newPending[tid]
        pendingModifications.value = newPending

        window.dispatchEvent(
          new CustomEvent('modify-confirmed', {
            detail: { targetId: tid, deletedTargetType: normalizedTarget },
            bubbles: true
          })
        )

        try {
          await resolveDiffReviewState({
            target: normalizedTarget,
            targetId: tid,
            action: 'confirm',
            messageId: modifyData._messageId
          })
        } catch (e) {
          console.warn('[DELETE] resolveDiffReviewState:', e)
        }

        const midDb = safeIntFkForDiffApi(modifyData._messageId)
        if (midDb != null) {
          try {
            await clearChatMessageDeleteNavigation(midDb)
          } catch (e) {
            console.warn('[DELETE] clearChatMessageDeleteNavigation:', e)
          }
        }

        if (!skipRestoreFetch) {
          try {
            await restorePendingDiffReviews()
          } catch (e) {
            console.warn('[DIFF] restorePendingDiffReviews:', e)
          }

          if (normalizedTarget === 'plan') {
            if (Number(selectedPlan.value) === tid) {
              selectedPlan.value = null
            }
            await fetchProjectPlans()
          } else if (normalizedTarget === 'card') {
            await fetchCards(1).catch((e) => console.warn('[DELETE] fetchCards:', e))
          } else {
            fetchBadcases()
            if (!currentTypeFilter.value) {
              fetchCards(1).catch((e) => console.warn('[DELETE] fetchCards:', e))
            }
          }
        }
      } catch (error) {
        console.error('[DELETE] 列表采纳删除失败:', error)
        alert(
          t('list.batchDeleteFail', {
            msg: error?.response?.data?.error || error?.message || t('common.unknownError')
          })
        )
      }
    }

    /**
     * 连续多条待删：顺序调删除接口，全部成功后再清 pending / 事件 / 刷新（与 confirmModifyBatch 同构，仅 HTTP 不同）。
     * 类型不一致时逐条 confirmDelete（中间步 skip 末尾统一 refresh）。
     */
    const confirmDeleteBatch = async (groupIds, opts = {}) => {
      const skipRestoreFetch = opts.skipRestoreFetch === true
      const ids = groupIds.map(Number).filter((n) => Number.isFinite(n) && n > 0)
      if (!ids.length) return

      const snapshots = []
      for (const bugId of ids) {
        const modifyData = pendingModifications.value[bugId]
        if (!modifyData?._pendingDelete) continue
        const normalizedTarget = normalizePendingDeleteTarget(modifyData)
        snapshots.push({ bugId, modifyData, normalizedTarget })
      }
      if (snapshots.length === 0) return
      if (snapshots.length === 1) {
        return confirmDelete(snapshots[0].bugId, { skipRestoreFetch })
      }

      const nt0 = snapshots[0].normalizedTarget
      if (!snapshots.every((s) => s.normalizedTarget === nt0)) {
        console.warn('[DELETE] 批量目标类型不一致，逐条删除')
        for (let i = 0; i < snapshots.length; i++) {
          const last = i === snapshots.length - 1
          await confirmDelete(snapshots[i].bugId, {
            skipRestoreFetch: last ? skipRestoreFetch : true
          })
        }
        return
      }

      try {
        for (const s of snapshots) {
          const res = await deleteApiForNormalizedTarget(s.normalizedTarget, s.bugId)
          if (res?.data && res.data.success === false) {
            throw new Error(res?.data?.error || 'delete failed')
          }
        }

        const newPending = { ...pendingModifications.value }
        for (const s of snapshots) delete newPending[s.bugId]
        pendingModifications.value = newPending

        for (const s of snapshots) {
          window.dispatchEvent(
            new CustomEvent('modify-confirmed', {
              detail: { targetId: s.bugId, deletedTargetType: nt0 },
              bubbles: true
            })
          )
        }
        for (const s of snapshots) {
          try {
            await resolveDiffReviewState({
              target: nt0,
              targetId: s.bugId,
              action: 'confirm',
              messageId: s.modifyData._messageId
            })
          } catch (e) {
            console.warn('[DELETE] resolveDiffReviewState:', e)
          }
        }
        const midSet = new Set()
        for (const s of snapshots) {
          const m = safeIntFkForDiffApi(s.modifyData._messageId)
          if (m != null) midSet.add(m)
        }
        for (const mid of midSet) {
          try {
            await clearChatMessageDeleteNavigation(mid)
          } catch (e) {
            console.warn('[DELETE] clearChatMessageDeleteNavigation:', e)
          }
        }

        if (!skipRestoreFetch) {
          try {
            await restorePendingDiffReviews()
          } catch (e) {
            console.warn('[DIFF] restorePendingDiffReviews:', e)
          }
          if (nt0 === 'plan') {
            const deleted = new Set(snapshots.map((s) => s.bugId))
            if (deleted.has(Number(selectedPlan.value))) {
              selectedPlan.value = null
            }
            await fetchProjectPlans()
          } else if (nt0 === 'card') {
            await fetchCards(1).catch((e) => console.warn('[DELETE] fetchCards:', e))
          } else {
            fetchBadcases()
            if (!currentTypeFilter.value) {
              fetchCards(1).catch((e) => console.warn('[DELETE] fetchCards:', e))
            }
          }
        }
      } catch (error) {
        console.error('[DELETE] 批量删除失败:', error)
        alert(
          t('list.batchDeleteFail', {
            msg: error?.response?.data?.error || error?.message || t('common.unknownError')
          })
        )
      }
    }

    /** 去重且保持首次出现顺序（用于一批 target id） */
    const uniqPreserveOrderNumeric = (arr) => {
      const seen = new Set()
      const out = []
      for (const x of arr || []) {
        const n = Number(x)
        if (!Number.isFinite(n) || n <= 0) continue
        if (!seen.has(n)) {
          seen.add(n)
          out.push(n)
        }
      }
      return out
    }

    /** 同一条批量预览内各行的 _peerTargetIds，跨分页仍视为一组（✓ 在最后一条上显示总数） */
    const mergePeerTargetIdsIntoPending = (peerTargetIds) => {
      const ids = uniqPreserveOrderNumeric(peerTargetIds)
      if (ids.length < 2) return
      const next = { ...pendingModifications.value }
      let changed = false
      for (const pid of ids) {
        if (!next[pid]) continue
        next[pid] = { ...next[pid], _peerTargetIds: ids }
        changed = true
      }
      if (changed) pendingModifications.value = next
    }

    /**
     * Bug/BadCase/TestCase 列表行与 pending 键对齐：modify 可能挂在源表 id 上，也可能挂在 Card.id（target=card）上。
     */
    const getPendingModifyMapKeyForBadcaseRow = (badcase) => {
      const pm = pendingModifications.value
      if (!badcase) return null
      const direct = pm[badcase.id]
      if (direct && !direct._pendingDelete) return badcase.id
      const cid = Number(badcase.card_id ?? badcase.cardId)
      if (Number.isFinite(cid) && cid > 0) {
        const alt = pm[cid]
        if (alt && !alt._pendingDelete) return cid
      }
      return null
    }

    // 获取连续相邻的待修改记录组
    const getConsecutiveGroups = () => {
      const result = []
      let currentGroup = []

      // 遍历 filteredBadcases 找出连续的待修改记录（键与列表 ✓/✗ 所用 modifyPendingMapKey 一致）
      filteredBadcases.value.forEach((badcase, index) => {
        const pk = getPendingModifyMapKeyForBadcaseRow(badcase)
        if (pk != null) {
          currentGroup.push(pk)
        } else {
          if (currentGroup.length > 0) {
            result.push([...currentGroup])
            currentGroup = []
          }
        }
      })
      
      // 处理最后一组
      if (currentGroup.length > 0) {
        result.push(currentGroup)
      }
      
      return result
    }
    
    // 判断是否是连续组的最后一个（含跨分页：由 _peerTargetIds / 同 message_id 决定）
    const isLastInConsecutiveGroup = (id) => {
      const g = getModifyGroupIdsForList(id)
      return g.length > 0 && g[g.length - 1] === id
    }

    // 获取连续组的大小
    const getConsecutiveGroupSize = (id) => {
      return getModifyGroupIdsForList(id).length
    }

    /** Bug/BadCase/TestCase 列表：仅连续「待删」行（与 modify 分组互斥） */
    const getConsecutiveDeleteGroups = () => {
      const pendingIds = Object.keys(pendingModifications.value)
        .map(Number)
        .filter((id) => pendingModifications.value[id]?._pendingDelete)
      const result = []
      let currentGroup = []
      filteredBadcases.value.forEach((badcase) => {
        if (pendingIds.includes(badcase.id)) {
          currentGroup.push(badcase.id)
        } else {
          if (currentGroup.length > 0) {
            result.push([...currentGroup])
            currentGroup = []
          }
        }
      })
      if (currentGroup.length > 0) {
        result.push(currentGroup)
      }
      return result
    }
    const isLastInConsecutiveDeleteGroup = (id) => {
      const g = getDeleteGroupIdsForList(id)
      return g.length > 0 && g[g.length - 1] === id
    }
    const getConsecutiveDeleteGroupSize = (id) => {
      return getDeleteGroupIdsForList(id).length
    }

    /** 迭代卡片总表：仅统计 _target===card 的 pending，顺序与 filteredCards 一致 */
    const getConsecutiveCardGroups = () => {
      const pendingIds = Object.keys(pendingModifications.value)
        .map(Number)
        .filter(
          (id) =>
            pendingModifications.value[id]?._target === 'card' &&
            !pendingModifications.value[id]?._pendingDelete
        )
      const result = []
      let currentGroup = []
      filteredCards.value.forEach((card) => {
        if (pendingIds.includes(card.id)) {
          currentGroup.push(card.id)
        } else {
          if (currentGroup.length > 0) {
            result.push([...currentGroup])
            currentGroup = []
          }
        }
      })
      if (currentGroup.length > 0) {
        result.push(currentGroup)
      }
      return result
    }
    const isLastInConsecutiveCardGroup = (id) => {
      const g = getCardModifyGroupIdsForList(id)
      return g.length > 0 && g[g.length - 1] === id
    }
    const getConsecutiveCardGroupSize = (id) => {
      return getCardModifyGroupIdsForList(id).length
    }

    /** 卡片总表：连续「待删」卡片行 */
    const getConsecutiveCardDeleteGroups = () => {
      const pendingIds = Object.keys(pendingModifications.value)
        .map(Number)
        .filter(
          (id) =>
            pendingModifications.value[id]?._target === 'card' &&
            pendingModifications.value[id]?._pendingDelete
        )
      const result = []
      let currentGroup = []
      filteredCards.value.forEach((card) => {
        if (pendingIds.includes(card.id)) {
          currentGroup.push(card.id)
        } else {
          if (currentGroup.length > 0) {
            result.push([...currentGroup])
            currentGroup = []
          }
        }
      })
      if (currentGroup.length > 0) {
        result.push(currentGroup)
      }
      return result
    }
    const isLastInConsecutiveCardDeleteGroup = (id) => {
      const g = getCardDeleteGroupIdsForList(id)
      return g.length > 0 && g[g.length - 1] === id
    }
    const getConsecutiveCardDeleteGroupSize = (id) => {
      return getCardDeleteGroupIdsForList(id).length
    }

    /**
     * 列表「一批」的真实 id 集合：优先 _peerTargetIds（跨分页），其次同 _messageId 同类型，
     * 最后才用当前页 filteredBadcases 中的相邻行（旧逻辑）。
     */
    const getModifyGroupIdsForList = (id) => {
      const pm = pendingModifications.value
      const p = pm[id]
      if (!p || p._pendingDelete) return [id]

      if (Array.isArray(p._peerTargetIds) && p._peerTargetIds.length >= 2) {
        const ordered = uniqPreserveOrderNumeric(p._peerTargetIds)
        const filtered = ordered.filter((pid) => {
          const x = pm[pid]
          return x && !x._pendingDelete
        })
        if (filtered.length >= 2) return filtered
      }

      const mid = p._messageId
      if (mid != null && mid !== '') {
        const sameMsg = Object.keys(pm)
          .map(Number)
          .filter((pid) => {
            const x = pm[pid]
            return (
              x &&
              !x._pendingDelete &&
              String(x._messageId ?? '') === String(mid)
            )
          })
          .sort((a, b) => a - b)
        if (sameMsg.length >= 2) return sameMsg
      }

      const groups = getConsecutiveGroups()
      for (const group of groups) {
        if (group.includes(id)) return [...group]
      }
      return [id]
    }

    const getDeleteGroupIdsForList = (id) => {
      const pm = pendingModifications.value
      const p = pm[id]
      if (!p || !p._pendingDelete) return [id]

      if (Array.isArray(p._peerTargetIds) && p._peerTargetIds.length >= 2) {
        const ordered = uniqPreserveOrderNumeric(p._peerTargetIds)
        const filtered = ordered.filter((pid) => {
          const x = pm[pid]
          return x && x._pendingDelete
        })
        if (filtered.length >= 2) return filtered
      }

      const mid = p._messageId
      if (mid != null && mid !== '') {
        const sameMsg = Object.keys(pm)
          .map(Number)
          .filter((pid) => {
            const x = pm[pid]
            return x && x._pendingDelete && String(x._messageId ?? '') === String(mid)
          })
          .sort((a, b) => a - b)
        if (sameMsg.length >= 2) return sameMsg
      }

      const groups = getConsecutiveDeleteGroups()
      for (const group of groups) {
        if (group.includes(id)) return [...group]
      }
      return [id]
    }

    const getCardModifyGroupIdsForList = (id) => {
      const pm = pendingModifications.value
      const p = pm[id]
      if (!p || p._pendingDelete || String(p._target || '').toLowerCase() !== 'card') return [id]

      if (Array.isArray(p._peerTargetIds) && p._peerTargetIds.length >= 2) {
        const ordered = uniqPreserveOrderNumeric(p._peerTargetIds)
        const filtered = ordered.filter((pid) => {
          const x = pm[pid]
          return x && !x._pendingDelete && String(x._target || '').toLowerCase() === 'card'
        })
        if (filtered.length >= 2) return filtered
      }

      const mid = p._messageId
      if (mid != null && mid !== '') {
        const sameMsg = Object.keys(pm)
          .map(Number)
          .filter((pid) => {
            const x = pm[pid]
            return (
              x &&
              !x._pendingDelete &&
              String(x._target || '').toLowerCase() === 'card' &&
              String(x._messageId ?? '') === String(mid)
            )
          })
          .sort((a, b) => a - b)
        if (sameMsg.length >= 2) return sameMsg
      }

      const groups = getConsecutiveCardGroups()
      for (const group of groups) {
        if (group.includes(id)) return [...group]
      }
      return [id]
    }

    const getCardDeleteGroupIdsForList = (id) => {
      const pm = pendingModifications.value
      const p = pm[id]
      if (!p || !p._pendingDelete || String(p._target || '').toLowerCase() !== 'card') return [id]

      if (Array.isArray(p._peerTargetIds) && p._peerTargetIds.length >= 2) {
        const ordered = uniqPreserveOrderNumeric(p._peerTargetIds)
        const filtered = ordered.filter((pid) => {
          const x = pm[pid]
          return x && x._pendingDelete && String(x._target || '').toLowerCase() === 'card'
        })
        if (filtered.length >= 2) return filtered
      }

      const mid = p._messageId
      if (mid != null && mid !== '') {
        const sameMsg = Object.keys(pm)
          .map(Number)
          .filter((pid) => {
            const x = pm[pid]
            return (
              x &&
              x._pendingDelete &&
              String(x._target || '').toLowerCase() === 'card' &&
              String(x._messageId ?? '') === String(mid)
            )
          })
          .sort((a, b) => a - b)
        if (sameMsg.length >= 2) return sameMsg
      }

      const groups = getConsecutiveCardDeleteGroups()
      for (const group of groups) {
        if (group.includes(id)) return [...group]
      }
      return [id]
    }

    // 检查是否有详情字段修改
    const hasDetailFieldModifications = (id) => {
      const modifyData = pendingModifications.value[id]
      if (!modifyData) return false
      
      // 检查是否有详情字段被修改
      for (const field of Object.keys(modifyData)) {
        if (field.startsWith('_')) continue // 跳过内部字段
        if (DETAIL_FIELDS.includes(field)) {
          return true
        }
      }
      return false
    }
    
    // 获取详情字段修改
    const getDetailFieldModifications = (id) => {
      const modifyData = pendingModifications.value[id]
      if (!modifyData) return {}
      
      const detailMods = {}
      for (const [field, data] of Object.entries(modifyData)) {
        if (field.startsWith('_')) continue // 跳过内部字段
        if (DETAIL_FIELDS.includes(field)) {
          detailMods[field] = data
        }
      }
      return detailMods
    }
    
    // 切换详情展开状态
    const toggleDetailExpand = (id) => {
      const index = expandedDetailRows.value.indexOf(id)
      if (index === -1) {
        expandedDetailRows.value.push(id)
      } else {
        expandedDetailRows.value.splice(index, 1)
      }
    }
    
    // 获取字段标签
    const getFieldLabel = (field) => {
      return FIELD_LABELS[field] || field
    }
    
    // 获取记录所在的连续组（跨分页时见 getModifyGroupIdsForList）
    const getConsecutiveGroup = (id) => {
      return getModifyGroupIdsForList(id)
    }
    
    // 批量确认所有修改
    const confirmAllModify = async () => {
      const pendingIds = Object.keys(pendingModifications.value)
        .map(Number)
        .filter((id) => !pendingModifications.value[id]?._pendingDelete)
      console.log('[MODIFY] 批量确认修改:', pendingIds)
      if (!pendingIds.length) return
      await confirmModifyBatch(pendingIds)
    }
    
    // 批量取消所有修改
    const cancelAllModify = async () => {
      const pendingIds = Object.keys(pendingModifications.value)
      console.log('[MODIFY] 批量取消修改:', pendingIds)
      
      for (const id of pendingIds) {
        await cancelModify(parseInt(id))
      }
    }
    
    // 确认连续组（列表上「N条」+ ✓）：多条时单次 POST items[]，仅一条时走原单条接口
    const confirmConsecutiveGroup = async (id) => {
      const group = getConsecutiveGroup(id)
      console.log('[MODIFY] 确认连续组:', group)
      if (!group.length) return
      return confirmModifyBatch(group)
    }
    
    // 取消连续组
    const cancelConsecutiveGroup = async (id) => {
      const group = getConsecutiveGroup(id)
      console.log('[MODIFY] 取消连续组:', group)
      if (!group.length) return
      for (let i = 0; i < group.length; i++) {
        const last = i === group.length - 1
        await cancelModify(group[i], { skipRestore: !last })
      }
    }

    const getConsecutiveDeleteGroup = (id) => {
      return getDeleteGroupIdsForList(id)
    }

    const confirmConsecutiveDeleteGroup = async (id) => {
      const group = getConsecutiveDeleteGroup(id)
      console.log('[DELETE] 确认连续删除组:', group)
      if (!group.length) return
      return confirmDeleteBatch(group)
    }

    const cancelConsecutiveDeleteGroup = async (id) => {
      const group = getConsecutiveDeleteGroup(id)
      console.log('[DELETE] 取消连续删除组:', group)
      if (!group.length) return
      for (let i = 0; i < group.length; i++) {
        const last = i === group.length - 1
        await cancelModify(group[i], { skipRestore: !last })
      }
    }

    const getConsecutiveCardDeleteGroup = (id) => {
      return getCardDeleteGroupIdsForList(id)
    }

    const confirmConsecutiveCardDeleteGroup = async (id) => {
      const group = getConsecutiveCardDeleteGroup(id)
      if (!group.length) return
      return confirmDeleteBatch(group)
    }

    const cancelConsecutiveCardDeleteGroup = async (id) => {
      const group = getConsecutiveCardDeleteGroup(id)
      if (!group.length) return
      for (let i = 0; i < group.length; i++) {
        const last = i === group.length - 1
        await cancelModify(group[i], { skipRestore: !last })
      }
    }

    // 显示/隐藏计划操作按钮
    const showPlanActions = (planId) => {
      hoveredPlan.value = planId
    }
    
    const hidePlanActions = (planId) => {
      // 延迟隐藏，避免菜单闪烁
      setTimeout(() => {
        if (hoveredPlan.value === planId) {
          hoveredPlan.value = null
        }
      }, 100)
    }
    
    const closeContextMenu = () => {
      contextMenuOutsideCloseCleanup?.()
      contextMenuOutsideCloseCleanup = null
      contextMenu.visible = false
      contextMenu.planId = null
    }

    const clampContextMenuToViewport = () => {
      nextTick(() => {
        const el = document.querySelector('.context-menu')
        if (!el) return
        const rect = el.getBoundingClientRect()
        const pad = 6
        let x = contextMenu.x
        let y = contextMenu.y
        if (rect.right > window.innerWidth - pad) {
          x = Math.max(pad, window.innerWidth - rect.width - pad)
        }
        if (rect.bottom > window.innerHeight - pad) {
          y = Math.max(pad, window.innerHeight - rect.height - pad)
        }
        if (rect.left < pad) x = pad
        if (rect.top < pad) y = pad
        contextMenu.x = x
        contextMenu.y = y
      })
    }

    const onContextMenuDragStart = (e) => {
      if (e.button !== 0) return
      e.preventDefault()
      _contextMenuDrag.startX = e.clientX
      _contextMenuDrag.startY = e.clientY
      _contextMenuDrag.origX = contextMenu.x
      _contextMenuDrag.origY = contextMenu.y
      contextMenuDragActive.value = true
      const onMove = (ev) => {
        const dx = ev.clientX - _contextMenuDrag.startX
        const dy = ev.clientY - _contextMenuDrag.startY
        let nx = _contextMenuDrag.origX + dx
        let ny = _contextMenuDrag.origY + dy
        const el = document.querySelector('.context-menu')
        const w = el ? el.offsetWidth : 200
        const h = el ? el.offsetHeight : 280
        const pad = 6
        nx = Math.max(pad, Math.min(nx, window.innerWidth - w - pad))
        ny = Math.max(pad, Math.min(ny, window.innerHeight - h - pad))
        contextMenu.x = nx
        contextMenu.y = ny
      }
      const onUp = () => {
        contextMenuDragActive.value = false
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove, { passive: true })
      document.addEventListener('mouseup', onUp)
    }

    const bindContextMenuOutsideClose = () => {
      contextMenuOutsideCloseCleanup?.()
      contextMenuOutsideCloseCleanup = null
      setTimeout(() => {
        const fn = (ev) => {
          if (ev.target.closest?.('.context-menu')) return
          closeContextMenu()
        }
        document.addEventListener('mousedown', fn, true)
        contextMenuOutsideCloseCleanup = () => document.removeEventListener('mousedown', fn, true)
      }, 0)
    }

    // 显示上下文菜单（固定定位 + 视口内校正 + 可拖动 + 内容区滚动）
    const showContextMenu = (plan, event) => {
      event.preventDefault()
      event.stopPropagation()
      contextMenu.visible = true
      contextMenu.planId = plan.id
      contextMenu.x = event.clientX
      contextMenu.y = event.clientY
      bindContextMenuOutsideClose()
      nextTick(() => clampContextMenuToViewport())
    }

    // 应用筛选条件
    const applyFilters = () => {
      console.log('=== 开始应用筛选条件 ===')
      console.log('搜索文本:', searchText.value)
      console.log('选中的负责人:', selectedAssignee.value)
      console.log('选中的状态:', selectedStatus.value)
      console.log('包含子计划:', includeSubPlans.value)
      
      // 首先根据计划过滤
      let filtered = [...badcases.value]
      
      // 根据计划过滤
      if (selectedPlan.value) {
        // 递归查找计划（包括子计划）
        const findPlan = (plans, planId) => {
          for (const plan of plans) {
            if (plan.id == planId) return plan
            if (plan.children && plan.children.length > 0) {
              const found = findPlan(plan.children, planId)
              if (found) return found
            }
          }
          return null
        }
        
        const selectedPlanObj = findPlan(projectPlans.value, selectedPlan.value)
        if (selectedPlanObj) {
          let planBadcases = []
          
          // 检查是否是子计划（有parent_id）
          if (selectedPlanObj.parent_id) {
            // 如果是子计划，只收集该子计划的BadCase
            planBadcases = filtered.filter(b => b.plan_id == selectedPlan.value)
          } else if (selectedPlanObj.children && selectedPlanObj.children.length > 0) {
            // 如果是父计划，根据includeSubPlans决定是否包含子计划
            if (includeSubPlans.value) {
              // 包含子计划
              selectedPlanObj.children.forEach(childPlan => {
                const childBadcases = filtered.filter(b => b.plan_id == childPlan.id)
                planBadcases.push(...childBadcases)
              })
            } else {
              // 不包含子计划，只显示父计划本身的BadCase
              planBadcases = filtered.filter(b => b.plan_id == selectedPlan.value)
            }
          } else {
            // 如果是没有子计划的父计划，收集该计划的BadCase
            planBadcases = filtered.filter(b => b.plan_id == selectedPlan.value)
          }
          
          filtered = planBadcases
        } else {
          // 如果找不到计划，直接根据plan_id过滤
          filtered = filtered.filter(b => b.plan_id == selectedPlan.value)
        }
      }
      
      // 根据搜索文本过滤（标题或负责人）
      if (searchText.value.trim()) {
        const searchLower = searchText.value.toLowerCase()
        filtered = filtered.filter(b => {
          const titleMatch = b.title && b.title.toLowerCase().includes(searchLower)
          const assigneeMatch = b.assignee && b.assignee.toLowerCase().includes(searchLower)
          return titleMatch || assigneeMatch
        })
      }
      
      // 根据负责人过滤
      if (selectedAssignee.value) {
        if (selectedAssignee.value === 'mine') {
          // 只看自己的
          filtered = filtered.filter(b => b.assignee == currentUser.value?.id || b.assignee == currentUser.value?.name)
        } else {
          // 指定负责人
          const member = projectMembers.value.find(m => m.id == selectedAssignee.value)
          if (member) {
            filtered = filtered.filter(b => b.assignee == member.id || b.assignee == member.name)
          }
        }
      }
      
      // 根据状态过滤
      if (selectedStatus.value) {
        filtered = filtered.filter(b => b.status === selectedStatus.value)
      }
      
      console.log('筛选后的BadCase数量:', filtered.length)
      filteredBadcases.value = filtered
      
      // 更新全选状态
      selectAll.value = false
      selectedTasks.value = []
    }
    
    // 菜单操作方法
    const createSubPlan = (plan) => {
      closeContextMenu()
      console.log('创建子计划:', plan.name)
      
      // 设置默认日期为今天和一周后
      const today = new Date()
      const nextWeek = new Date(today)
      nextWeek.setDate(today.getDate() + 7)
      
      newPlan.startDate = today.toISOString().split('T')[0]
      newPlan.endDate = nextWeek.toISOString().split('T')[0]
      newPlan.name = ''
      newPlan.description = ''
      newPlan.parentId = plan.id // 设置当前计划为父计划
      newPlan.scopeNotification = false
      newPlan.contentType = 'badcase'
      
      isCreatingSiblingPlan.value = false
      isCreatingSubPlan.value = true
      showCreateModal.value = true
    }
    
    const createSiblingPlan = (plan) => {
      closeContextMenu()
      console.log('创建同级计划:', plan.name, '父计划ID:', plan.parent_id)
      console.log('计划层级信息:', {
        id: plan.id,
        name: plan.name,
        parent_id: plan.parent_id,
        level: plan.parent_id ? (plan.parent_id.toString().includes('.') ? '孙计划' : '子计划') : '顶级计划'
      })
      
      // 设置默认日期为今天和一周后
      const today = new Date()
      const nextWeek = new Date(today)
      nextWeek.setDate(today.getDate() + 7)
      
      newPlan.startDate = today.toISOString().split('T')[0]
      newPlan.endDate = nextWeek.toISOString().split('T')[0]
      newPlan.name = ''
      newPlan.description = ''
      // 设置与当前计划相同的父计划ID
      newPlan.parentId = plan.parent_id || '' // 如果是顶级计划，则同级计划也是顶级
      console.log('设置父计划ID为:', newPlan.parentId)
      newPlan.scopeNotification = false
      newPlan.contentType = 'badcase'
      
      isCreatingSiblingPlan.value = true
      isCreatingSubPlan.value = false
      showCreateModal.value = true
    }
    
    const editPlan = (plan) => {
      closeContextMenu()
      console.log('编辑计划:', plan.name)
      
      // 填充表单数据
      newPlan.cycle = plan.cycle || 'one_week'
      newPlan.startDate = plan.start_date ? plan.start_date.split('T')[0] : ''
      newPlan.endDate = plan.end_date ? plan.end_date.split('T')[0] : ''
      newPlan.count = plan.plan_count || 1
      newPlan.name = plan.name || ''
      newPlan.parentId = plan.parent_id || ''
      newPlan.description = plan.description || ''
      newPlan.scopeNotification = plan.scope_notification || false
      newPlan.statusType = plan.status_type || 'in_progress'
      newPlan.contentType = 'badcase'
      
      console.log('🐛 编辑计划，加载的 contentType:', newPlan.contentType)
      
      // 设置编辑状态
      isEditingPlan.value = true
      editingPlanId.value = plan.id
      isCreatingSubPlan.value = false
      
      // 显示模态框
      showCreateModal.value = true
    }
    
    const archivePlan = (plan) => {
      closeContextMenu()
      console.log('归档计划:', plan.name)
      // TODO: 实现归档计划功能
    }
    
    const deletePlan = async (plan) => {
      closeContextMenu()
      if (confirm(t('project.deletePlanConfirm', { name: plan.name }))) {
        try {
          console.log('开始删除计划:', plan.name, 'ID:', plan.id)
          
          const response = await deletePlanApi(plan.id)
          console.log('删除计划响应:', response)
          
          if (response && response.data && response.data.success) {
            console.log('计划删除成功:', plan.name)
            alert(t('project.deletePlanOk'))
            
            // 重新获取计划列表
            await fetchProjectPlans()
          } else {
            const errorMsg = response?.data?.error || t('common.unknownError')
            console.error('删除计划失败:', errorMsg)
            alert(t('project.deletePlanFail', { msg: errorMsg }))
          }
        } catch (error) {
          console.error('删除计划失败 - 详细错误:', error)
          console.error('错误响应:', error.response)
          console.error('错误状态:', error.response?.status)
          console.error('错误数据:', error.response?.data)
          
          let errorMessage = t('project.deletePlanErr')
          if (error.response) {
            errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
          } else if (error.request) {
            errorMessage += ': ' + t('project.networkUnreachable')
          } else {
            errorMessage += `: ${error.message}`
          }
          
          alert(errorMessage)
        }
      }
    }
    
    const pinPlan = async (plan) => {
      closeContextMenu()
      const actionLabel = plan.is_pinned ? t('project.unpin') : t('project.pin')
      console.log(`${actionLabel}计划:`, plan.name)
      
      try {
        const response = await pinPlanApi(plan.id)
        console.log('置顶API响应:', response)
        
        if (response && response.data && response.data.success) {
          console.log(`计划${actionLabel}成功:`, plan.name)
          alert(t('project.pinSuccess', { action: actionLabel }))
          
          // 重新获取计划列表以更新排序
          await fetchProjectPlans()
        } else {
          const errorMsg = response?.data?.error || t('common.unknownError')
          console.error(`${actionLabel}计划失败:`, errorMsg)
          alert(t('project.pinFail', { action: actionLabel, msg: errorMsg }))
        }
      } catch (error) {
        console.error(`${actionLabel}计划失败 - 详细错误:`, error)
        
        let errorMessage = t('project.pinErr', { action: actionLabel })
        if (error.response) {
          errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
        } else if (error.request) {
          errorMessage += ': ' + t('project.networkUnreachable')
        } else {
          errorMessage += `: ${error.message}`
        }
        
        alert(errorMessage)
      }
    }
    
    const favoritePlan = (plan) => {
      closeContextMenu()
      console.log('收藏计划:', plan.name)
      // TODO: 实现收藏计划功能
    }
    
    const createBaseline = (plan) => {
      closeContextMenu()
      console.log('新建基线:', plan.name)
      // TODO: 实现新建基线功能
    }
    
    // 头部按钮功能
    const showCreatePlanModal = () => {
      console.log('点击右侧新建计划按钮')
      // 设置默认日期为今天和一周后
      const today = new Date()
      const nextWeek = new Date(today)
      nextWeek.setDate(today.getDate() + 7)
      
      newPlan.startDate = today.toISOString().split('T')[0]
      newPlan.endDate = nextWeek.toISOString().split('T')[0]
      newPlan.name = ''
      newPlan.description = ''
      newPlan.parentId = ''
      newPlan.scopeNotification = false
      
      // 重置所有模式状态
      isCreatingSubPlan.value = false
      isCreatingSiblingPlan.value = false
      isEditingPlan.value = false
      editingPlanId.value = null
      
      showCreateModal.value = true
      console.log('新建计划模态框已打开，模式状态:', {
        isCreatingSubPlan: isCreatingSubPlan.value,
        isCreatingSiblingPlan: isCreatingSiblingPlan.value,
        isEditingPlan: isEditingPlan.value
      })
    }
    
    const resetNewPlanForm = () => {
      newPlan.name = ''
      newPlan.startDate = ''
      newPlan.endDate = ''
      newPlan.parentId = ''
      newPlan.description = ''
    }
    
    const closeCreateModal = () => {
      console.log('关闭新建计划模态框')
      showCreateModal.value = false
      isCreatingSubPlan.value = false
      isCreatingSiblingPlan.value = false
      isEditingPlan.value = false
      editingPlanId.value = null
      resetNewPlanForm()
    }
    
    const getModalTitle = () => {
      if (isEditingPlan.value) {
        return t('project.modalEditPlan')
      } else if (isCreatingSubPlan.value) {
        return t('project.modalNewSubPlan')
      } else if (isCreatingSiblingPlan.value) {
        return t('project.modalNewSiblingPlan')
      } else {
        return t('project.modalNewPlan')
      }
    }
    

    
    const showBaselineManagement = async () => {
      console.log('显示基线管理 - 方法被调用')
      console.log('修改前模态框状态:', showBaselineManagementModal.value)
      
      try {
        showBaselineManagementModal.value = true
        console.log('修改后模态框状态:', showBaselineManagementModal.value)
        
        // 强制触发响应式更新
        nextTick(() => {
          console.log('nextTick后模态框状态:', showBaselineManagementModal.value)
        })
        
        // 加载基线数据
        await loadBaselines()
        // 初始化基线管理中的计划折叠状态
        initBaselinePlanCollapseState()
        console.log('基线数据加载完成')
      } catch (error) {
        console.error('显示基线管理时出错:', error)
        console.error('错误详情:', error.message)
      }
    }
    
    const closeBaselineManagementModal = () => {
      showBaselineManagementModal.value = false
      selectedBaselinePlan.value = null
      selectedBaseline.value = null
      selectedBadcases.value = []
      availableBadcases.value = []
    }
    
    const selectBaselinePlan = (planId) => {
      selectedBaselinePlan.value = planId
      // 加载该计划下未在基线中的BadCase
      loadAvailableBadcases(planId)
      // 加载该计划的基线列表
      loadBaselines()
    }
    
    const toggleBadcaseSelection = (badcaseId) => {
      const index = selectedBadcases.value.indexOf(badcaseId)
      if (index > -1) {
        selectedBadcases.value.splice(index, 1)
      } else {
        selectedBadcases.value.push(badcaseId)
      }
    }
    
    const createNewBaseline = async () => {
      if (!selectedBaselinePlan.value || selectedBadcases.value.length === 0) {
        console.log('请选择计划和BadCase')
        return
      }
      
      try {
        const baselineName = `基线_${new Date().toLocaleDateString()}`
        console.log('创建基线:', baselineName, '包含BadCase:', selectedBadcases.value)
        
        // 调用API创建基线
        const response = await apiCreateBaseline({
          name: baselineName,
          plan_id: selectedBaselinePlan.value,
          badcase_ids: selectedBadcases.value
        })
        
        const newBaseline = response.data.baseline
        console.log('基线创建成功:', newBaseline)
        
        baselines.value.unshift(newBaseline)
        selectedBadcases.value = []
        
        console.log(`基线创建成功！包含${newBaseline.badcase_count}个BadCase`)
      } catch (error) {
        console.error('创建基线失败:', error)
        console.error('错误详情:', error.message)
        
        // 模拟创建成功
        const newBaseline = {
          id: Date.now(),
          name: `基线_${new Date().toLocaleDateString()}`,
          version: baselines.value.length + 1,
          created_at: new Date().toISOString(),
          badcase_count: selectedBadcases.value.length,
          plan_id: selectedBaselinePlan.value
        }
        
        baselines.value.unshift(newBaseline)
        selectedBadcases.value = []
        
        console.log(`基线创建成功（模拟）！包含${newBaseline.badcase_count}个BadCase`)
      }
    }
    
    const compareBaselines = () => {
      if (baselines.value.length < 2) {
        console.log('至少需要2个基线才能进行对比')
        return
      }
      
      // TODO: 实现基线对比功能
      console.log('基线对比功能开发中...')
    }
    
    const selectBaseline = (baselineId) => {
      selectedBaseline.value = baselineId
    }
    
    const viewBaseline = async (baselineId) => {
      try {
        console.log('查看基线详情:', baselineId)
        const response = await getBaselineDetail(baselineId)
        const baseline = response.data.baseline
        console.log('基线详情:', baseline)
        
        // 显示基线详情（可以弹出模态框或在页面上显示）
        alert(`基线详情\n名称: ${baseline.name}\n版本: v${baseline.version}\n创建时间: ${new Date(baseline.created_at).toLocaleString()}\n包含BadCase数量: ${baseline.badcase_count}`)
      } catch (error) {
        console.error('获取基线详情失败:', error)
        // 模拟数据
        const baseline = baselines.value.find(b => b.id === baselineId)
        if (baseline) {
          alert(`基线详情\n名称: ${baseline.name}\n版本: v${baseline.version}\n创建时间: ${new Date(baseline.created_at).toLocaleString()}\n包含BadCase数量: ${baseline.badcase_count}`)
        }
      }
    }
    
    const deleteBaseline = async (baselineId) => {
      if (window.confirm(t('project.deleteBaselineConfirm'))) {
        try {
          await apiDeleteBaseline(baselineId)
          console.log('基线删除成功:', baselineId)
          const index = baselines.value.findIndex(b => b.id === baselineId)
          if (index > -1) {
            baselines.value.splice(index, 1)
          }
        } catch (error) {
          console.error('删除基线失败:', error)
          // 即使API调用失败，也从本地数组中删除（模拟删除）
          const index = baselines.value.findIndex(b => b.id === baselineId)
          if (index > -1) {
            baselines.value.splice(index, 1)
          }
        }
      }
    }
    
    // 初始化基线管理中的计划折叠状态
    const initBaselinePlanCollapseState = () => {
      // 为每个有子计划的计划添加折叠状态
      // 使用 projectPlans 而不是 filteredPlans，因为 filteredPlans 可能被搜索过滤
      projectPlans.value.forEach(plan => {
        if (plan.children && plan.children.length > 0) {
          // 默认展开状态
          plan.collapsed = false
        }
      })
    }
    
    // 切换基线管理中计划的展开/折叠状态
    const toggleBaselinePlanExpansion = (planId) => {
      const plan = projectPlans.value.find(p => p.id == planId)
      if (plan && plan.children && plan.children.length > 0) {
        plan.collapsed = !plan.collapsed
        console.log(`计划 ${plan.name} 折叠状态切换为:`, plan.collapsed ? '折叠' : '展开')
      }
    }
    
    const loadBaselines = async () => {
      try {
        console.log('开始加载基线数据...')
        if (selectedBaselinePlan.value) {
          const response = await getPlanBaselines(selectedBaselinePlan.value)
          baselines.value = response.data.baselines || []
          console.log('基线数据加载成功:', baselines.value)
        } else {
          baselines.value = []
        }
        // 模拟数据（当API调用失败时使用）
        if (baselines.value.length === 0) {
          baselines.value = [
            {
              id: 1,
              name: '基线_v1.0',
              version: 1,
              created_at: '2025-08-15T10:00:00Z',
              badcase_count: 5,
              plan_id: selectedBaselinePlan.value
            },
            {
              id: 2,
              name: '基线_v1.1',
              version: 2,
              created_at: '2025-08-16T14:30:00Z',
              badcase_count: 8,
              plan_id: selectedBaselinePlan.value
            }
          ]
          console.log('使用模拟基线数据:', baselines.value)
        }
        console.log('基线数据加载成功:', baselines.value)
        
        // 暂时注释掉测试代码，避免语法错误
        /*
        // 为测试目的，确保子计划有自己的BadCase
        // 动态获取子计划的ID
        let subPlanId = null
        if (projectPlans.value.length > 0) {
          const firstPlan = projectPlans.value[0]
          if (firstPlan.children && firstPlan.children.length > 0) {
            subPlanId = firstPlan.children[0].id
            console.log('找到子计划ID:', subPlanId)
          }
        }
        
        if (subPlanId) {
          const testSubPlanBadcase = {
            id: 999,
            title: '子计划测试BadCase',
            type: 'BadCase',
            status: '新建',
            assignee: '测试用户',
            plan_id: subPlanId, // 动态获取的子计划ID
            created_at: '2025-08-18T10:00:00Z'
          }
          
          // 如果这个测试BadCase不存在，则添加到badcases列表中
          if (!badcases.value.find(b => b.id === testSubPlanBadcase.id)) {
            badcases.value.push(testSubPlanBadcase)
            console.log('添加测试子计划BadCase:', testSubPlanBadcase)
          }
        }
        */
        
      } catch (error) {
        console.error('加载基线失败:', error)
        console.error('加载基线数据失败: ' + error.message)
      }
    }
    
    const loadAvailableBadcases = async (planId) => {
      try {
        console.log('开始加载可用BadCase, 计划ID:', planId)
        console.log('当前所有BadCase:', badcases.value)
        console.log('当前所有计划:', projectPlans.value)
        
        // TODO: 调用API获取该计划下未在基线中的BadCase
        // 模拟数据 - 根据选择的计划类型加载相应的BadCase
        
        // 递归查找计划（包括子计划）
        const findPlan = (plans, planId) => {
          for (const plan of plans) {
            if (plan.id == planId) return plan
            if (plan.children && plan.children.length > 0) {
              const found = findPlan(plan.children, planId)
              if (found) return found
            }
          }
          return null
        }
        
        const selectedPlan = findPlan(projectPlans.value, planId)
        if (selectedPlan) {
          console.log('选中的计划:', selectedPlan)
          let planBadcases = []
          
          // 检查是否是子计划（有parent_id）
          if (selectedPlan.parent_id) {
            // 如果是子计划，只收集该子计划的BadCase
            planBadcases = badcases.value.filter(b => b.plan_id == planId)
            console.log(`选择子计划 "${selectedPlan.name}" (ID: ${planId})，加载该子计划下的BadCase`)
            console.log(`子计划BadCase过滤条件: plan_id == ${planId}`)
            console.log(`过滤结果:`, planBadcases)
          } else if (selectedPlan.children && selectedPlan.children.length > 0) {
            // 如果是父计划，收集所有子计划的BadCase
            console.log(`选择父计划 "${selectedPlan.name}"，收集所有子计划的BadCase`)
            selectedPlan.children.forEach(childPlan => {
              const childBadcases = badcases.value.filter(b => b.plan_id == childPlan.id)
              console.log(`子计划 ${childPlan.name} (ID: ${childPlan.id}) 的BadCase:`, childBadcases)
              planBadcases.push(...childBadcases)
            })
            console.log(`父计划下所有子计划的BadCase:`, planBadcases)
          } else {
            // 如果是没有子计划的父计划，收集该计划的BadCase
            planBadcases = badcases.value.filter(b => b.plan_id == planId)
            console.log(`选择父计划 "${selectedPlan.name}"，加载该计划的BadCase`)
          }
          
          availableBadcases.value = planBadcases
          console.log(`可用BadCase加载成功，共${planBadcases.length}个:`, availableBadcases.value)
        } else {
          console.log(`未找到ID为 ${planId} 的计划`)
        }
      } catch (error) {
        console.error('加载可用BadCase失败:', error)
        console.error('加载可用BadCase失败: ' + error.message)
      }
    }
    
    const manualRefreshPlans = async () => {
      console.log('=== 手动刷新页面数据 ===')
      loading.value = true
      try {
        const expandPlanId = route.query.expand_plan
        await Promise.all([
          fetchProjectInfo(),
          fetchProjectPlans(),
          fetchProjectMembers()
        ])
        if (expandPlanId) {
          selectedPlan.value = expandPlanId
          await fetchBadcases(1)
        }
        
        console.log('数据刷新完成')
      } catch (error) {
        console.error('刷新数据失败:', error)
      } finally {
        loading.value = false
        await nextTick()
        ensureWorkbenchTabForCurrentView()
      }
    }
    
    const togglePlanCollapse = () => {
      planCollapsed.value = !planCollapsed.value
      console.log('切换计划收起状态:', planCollapsed.value)
    }
    
    const searchPlans = () => {
      console.log('搜索计划:', planSearchText.value)
      filterPlans()
    }
    
    const clearSearch = () => {
      planSearchText.value = ''
      console.log('清除搜索')
      // filterPlans() 会通过 watch 自动调用
    }
    
    // 过滤计划的函数
    const filterPlans = () => {
      const searchText = planSearchText.value.toLowerCase().trim()
      
      if (!searchText) {
        // 如果没有搜索文本，显示所有计划
        filteredPlans.value = projectPlans.value
      } else {
        // 递归过滤计划（包括子计划和孙计划）
        filteredPlans.value = filterPlansRecursively(projectPlans.value, searchText)
      }
      
      console.log('过滤后的计划数量:', filteredPlans.value.length)
    }
    
    // 递归过滤计划函数
    const filterPlansRecursively = (plans, searchText) => {
      const filtered = []
      
      for (const plan of plans) {
        // 检查当前计划是否匹配
        const planMatches = plan.name.toLowerCase().includes(searchText) ||
                           (plan.description && plan.description.toLowerCase().includes(searchText))
        
        // 递归检查子计划
        let filteredChildren = []
        if (plan.children && plan.children.length > 0) {
          filteredChildren = filterPlansRecursively(plan.children, searchText)
        }
        
        // 如果当前计划匹配或有子计划匹配，则包含在结果中
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
    
    const createPlanAndContinue = async () => {
      await createPlan()
      // 成功后重置表单但保持弹框打开
      newPlan.name = ''
      newPlan.startDate = ''
      newPlan.endDate = ''
      newPlan.description = ''
      // 保持 parentId 不变，方便连续添加同级计划
    }
    
    const createPlan = async () => {
      const actionText = isEditingPlan.value ? '更新' : '创建'
      console.log(`开始${actionText}计划，表单验证状态:`, isFormValid.value)
      console.log('当前表单数据:', newPlan)
      
      if (!isFormValid.value) {
        console.log(`表单验证失败，无法${actionText}计划`)
        return
      }
      
      try {
        const planData = {
          name: newPlan.name,
          start_date: newPlan.startDate,
          end_date: newPlan.endDate,
          description: newPlan.description,
          parent_id: newPlan.parentId || null,
          project_id: projectId.value
        }
        
        console.log('发送到后端的数据:', planData)
        console.log('项目ID:', projectId.value)
        console.log('API基础URL:', BACKEND_BASE_URL)
        
        let response
        try {
          console.log('=== 开始API调用 ===')
          if (isEditingPlan.value) {
            console.log('调用更新计划API，计划ID:', editingPlanId.value)
            response = await updatePlanApi(editingPlanId.value, planData)
            console.log('更新计划API响应:', response)
          } else {
            console.log('调用创建计划API')
            console.log('API URL: POST ' + `${BACKEND_BASE_URL}/api/plans`)
            console.log('请求数据:', JSON.stringify(planData, null, 2))
            response = await createPlanApi(planData)
            console.log('创建计划API完整响应:', response)
          }
          console.log('API响应状态:', response.status)
          console.log('API响应数据:', response.data)
          console.log('API响应成功标志:', response.data?.success)
        } catch (apiError) {
          const actionText = isEditingPlan.value ? '更新' : '创建'
          console.error(`${actionText}计划API调用失败:`, apiError)
          console.error('错误详情:', {
            message: apiError.message,
            status: apiError.response?.status,
            statusText: apiError.response?.statusText,
            data: apiError.response?.data,
            config: apiError.config
          })
          throw apiError
        }
        
        if (response && response.data && response.data.success) {
          console.log('计划保存成功:', response.data.plan)
          alert(isEditingPlan.value ? t('project.updatePlanSuccess') : t('project.createPlanSuccess'))
          closeCreateModal()
          // 重新获取计划列表
          console.log('开始重新获取计划列表...')
          // 使用nextTick确保DOM更新
          await nextTick()
          await fetchProjectPlans()
          console.log('计划列表刷新完成，当前计划数量:', projectPlans.value.length)
          console.log('过滤后的计划数量:', filteredPlans.value.length)
          console.log('新计划是否在列表中:', filteredPlans.value.some(p => p.name === planData.name))
        } else {
          const errorMsg = response?.data?.error || t('common.unknownError')
          console.error('计划保存失败:', errorMsg)
          alert(
            isEditingPlan.value
              ? t('project.updatePlanFail', { msg: errorMsg })
              : t('project.createPlanFail', { msg: errorMsg })
          )
        }
      } catch (error) {
        console.error('创建计划失败 - 详细错误:', error)
        console.error('错误响应:', error.response)
        console.error('错误状态:', error.response?.status)
        console.error('错误数据:', error.response?.data)
        
        let errorMessage = isEditingPlan.value ? t('project.updatePlanErr') : t('project.createPlanErr')
        if (error.response) {
          errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
        } else if (error.request) {
          errorMessage += ': ' + t('project.networkUnreachable')
        } else {
          errorMessage += `: ${error.message}`
        }
        
        alert(errorMessage)
      }
    }
    
    // 切换计划展开状态
    const togglePlanExpansion = (planId) => {
      const index = expandedPlans.value.indexOf(planId)
      if (index > -1) {
        expandedPlans.value.splice(index, 1)
      } else {
        expandedPlans.value.push(planId)
      }
    }
    
    // 设置布局对齐
    const setLayout = (layout) => {
      console.log('切换布局:', layout)
      
      switch (layout) {
        case 'left':
          // 左侧边栏切换
          leftSidebarHidden.value = !leftSidebarHidden.value
          planCollapsed.value = leftSidebarHidden.value
          console.log('左侧边栏状态:', leftSidebarHidden.value ? '隐藏' : '显示')
          break
        case 'bottom':
          // Terminal 面板切换
          showTerminal.value = !showTerminal.value
          console.log('Terminal 面板状态:', showTerminal.value ? '显示' : '隐藏')
          break
        case 'right':
          // AI 助手面板切换
          showAIAssistant.value = !showAIAssistant.value
          console.log('AI 助手面板状态:', showAIAssistant.value ? '显示' : '隐藏')
          break
      }
    }
    
    // 左侧边栏拖拽相关方法
    const startDragLeftSidebar = (event) => {
      isDraggingLeftSidebar.value = true
      leftDragStartX.value = event.clientX
      leftDragStartWidth.value = leftSidebarWidth.value
      
      // 添加拖拽时的样式类
      document.body.classList.add('dragging')
      
      document.addEventListener('mousemove', handleDragLeftSidebar)
      document.addEventListener('mouseup', stopDragLeftSidebar)
      
      event.preventDefault()
      event.stopPropagation()
    }
    
    const handleDragLeftSidebar = (event) => {
      if (!isDraggingLeftSidebar.value) return
      
      event.preventDefault()
      event.stopPropagation()
      
      const deltaX = event.clientX - leftDragStartX.value
      const newWidth = Math.max(180, Math.min(400, leftDragStartWidth.value + deltaX))
      leftSidebarWidth.value = newWidth
    }
    
    const stopDragLeftSidebar = (event) => {
      isDraggingLeftSidebar.value = false
      
      // 移除拖拽时的样式类
      document.body.classList.remove('dragging')
      
      document.removeEventListener('mousemove', handleDragLeftSidebar)
      document.removeEventListener('mouseup', stopDragLeftSidebar)
      
      if (event) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    
    // 右侧对话框拖拽相关方法
    const startDragRightSidebar = (event) => {
      isDraggingRightSidebar.value = true
      rightDragStartX.value = event.clientX
      rightDragStartWidth.value = rightSidebarWidth.value
      
      // 添加拖拽时的样式类
      document.body.classList.add('dragging')
      
      // 给主内容区域添加拖拽类，禁用过渡动画
      const mainContent = document.querySelector('.main-content')
      if (mainContent) {
        mainContent.classList.add('dragging')
      }
      
      document.addEventListener('mousemove', handleDragRightSidebar)
      document.addEventListener('mouseup', stopDragRightSidebar)
      
      event.preventDefault()
      event.stopPropagation()
    }
    
    const handleDragRightSidebar = (event) => {
      if (!isDraggingRightSidebar.value) return
      
      event.preventDefault()
      event.stopPropagation()
      
      const deltaX = rightDragStartX.value - event.clientX
      const newWidth = Math.max(200, Math.min(600, rightDragStartWidth.value + deltaX))
      rightSidebarWidth.value = newWidth
    }
    
    const stopDragRightSidebar = (event) => {
      isDraggingRightSidebar.value = false
      
      // 移除拖拽时的样式类
      document.body.classList.remove('dragging')
      
      // 移除主内容区域的拖拽类，恢复过渡动画
      const mainContent = document.querySelector('.main-content')
      if (mainContent) {
        mainContent.classList.remove('dragging')
      }
      
      document.removeEventListener('mousemove', handleDragRightSidebar)
      document.removeEventListener('mouseup', stopDragRightSidebar)
      
      if (event) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    
    // 底部面板拖拽相关函数
    const startDragBottomPanel = (event) => {
      isDraggingBottomPanel.value = true
      dragStartY.value = event.clientY
      dragStartHeight.value = bottomPanelHeight.value
      
      document.body.classList.add('dragging')
      
      document.addEventListener('mousemove', handleDragBottomPanel)
      document.addEventListener('mouseup', stopDragBottomPanel)
      
      event.preventDefault()
      event.stopPropagation()
    }
    
    const handleDragBottomPanel = (event) => {
      if (!isDraggingBottomPanel.value) return
      
      event.preventDefault()
      event.stopPropagation()
      
      // 向上拖拽时，deltaY为负数，面板高度增加
      const deltaY = dragStartY.value - event.clientY
      const newHeight = Math.max(150, Math.min(800, dragStartHeight.value + deltaY))
      bottomPanelHeight.value = newHeight
    }
    
    const stopDragBottomPanel = (event) => {
      isDraggingBottomPanel.value = false
      
      document.body.classList.remove('dragging')
      
      document.removeEventListener('mousemove', handleDragBottomPanel)
      document.removeEventListener('mouseup', stopDragBottomPanel)
      
      if (event) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    
    const showProjectSettings = () => {
      showProjectSettingsModal.value = true
    }
    
    const showPermissionSettings = () => {
      showPermissionSettingsModal.value = true
    }
    
    // 关闭配置模态框
    const closeConfigModals = () => {
      showProjectSettingsModal.value = false
      showPermissionSettingsModal.value = false
    }
    
    // 用户下拉菜单相关方法
    const toggleUserDropdown = () => {
      showUserDropdown.value = !showUserDropdown.value
    }
    
    const openAppSettings = async (pane) => {
      showUserDropdown.value = false
      const p = typeof pane === 'string' && ['account', 'team', 'preferences'].includes(pane) ? pane : 'account'
      appSettingsInitialPane.value = p
      clearEmbeddedEditor()
      const tab = {
        id: SETTINGS_WORKBENCH_TAB_ID,
        kind: 'settings',
        title: truncateForTab(t('shell.settings'), t('shell.settings')),
        meta: { initialPane: p }
      }
      const idx = workbenchTabs.value.findIndex((x) => x.id === SETTINGS_WORKBENCH_TAB_ID)
      if (idx >= 0) {
        workbenchTabs.value[idx] = { ...workbenchTabs.value[idx], ...tab }
      } else {
        const cur = workbenchTabs.value.findIndex((x) => x.id === activeWorkbenchTabId.value)
        const insertAt = cur >= 0 ? cur + 1 : workbenchTabs.value.length
        workbenchTabs.value.splice(insertAt, 0, tab)
      }
      await activateWorkbenchTab(SETTINGS_WORKBENCH_TAB_ID)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    const closeAppSettingsWorkbenchTab = () => {
      closeWorkbenchTab(SETTINGS_WORKBENCH_TAB_ID)
    }

    const openHelpWorkbenchTab = async () => {
      showUserDropdown.value = false
      clearEmbeddedEditor()
      const tab = {
        id: HELP_WORKBENCH_TAB_ID,
        kind: 'help',
        title: truncateForTab(t('shell.help'), t('shell.help')),
        meta: {}
      }
      const idx = workbenchTabs.value.findIndex((x) => x.id === HELP_WORKBENCH_TAB_ID)
      if (idx >= 0) {
        workbenchTabs.value[idx] = { ...workbenchTabs.value[idx], ...tab }
      } else {
        const cur = workbenchTabs.value.findIndex((x) => x.id === activeWorkbenchTabId.value)
        const insertAt = cur >= 0 ? cur + 1 : workbenchTabs.value.length
        workbenchTabs.value.splice(insertAt, 0, tab)
      }
      await activateWorkbenchTab(HELP_WORKBENCH_TAB_ID)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    const openTerminalSettingsWorkbenchTab = async () => {
      clearEmbeddedEditor()
      const tab = {
        id: TERMINAL_SETTINGS_WORKBENCH_TAB_ID,
        kind: 'terminal-settings',
        title: truncateForTab(t('embeddedTerminal.terminalSettingsTab'), t('embeddedTerminal.terminalSettingsTab')),
        meta: {}
      }
      const idx = workbenchTabs.value.findIndex((x) => x.id === TERMINAL_SETTINGS_WORKBENCH_TAB_ID)
      if (idx >= 0) {
        workbenchTabs.value[idx] = { ...workbenchTabs.value[idx], ...tab }
      } else {
        const cur = workbenchTabs.value.findIndex((x) => x.id === activeWorkbenchTabId.value)
        const insertAt = cur >= 0 ? cur + 1 : workbenchTabs.value.length
        workbenchTabs.value.splice(insertAt, 0, tab)
      }
      await activateWorkbenchTab(TERMINAL_SETTINGS_WORKBENCH_TAB_ID)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    provide('openTerminalSettingsWorkbenchTab', openTerminalSettingsWorkbenchTab)

    const openProjectManagementWorkbenchTab = async () => {
      showUserDropdown.value = false
      clearEmbeddedEditor()
      const PROJECT_MANAGEMENT_WORKBENCH_TAB_ID = 'project-management'
      const tab = {
        id: PROJECT_MANAGEMENT_WORKBENCH_TAB_ID,
        kind: 'projectManagement',
        title: truncateForTab('项目管理', '项目管理'),
        meta: {}
      }
      const idx = workbenchTabs.value.findIndex((x) => x.id === PROJECT_MANAGEMENT_WORKBENCH_TAB_ID)
      if (idx >= 0) {
        workbenchTabs.value[idx] = { ...workbenchTabs.value[idx], ...tab }
      } else {
        const cur = workbenchTabs.value.findIndex((x) => x.id === activeWorkbenchTabId.value)
        const insertAt = cur >= 0 ? cur + 1 : workbenchTabs.value.length
        workbenchTabs.value.splice(insertAt, 0, tab)
      }
      await activateWorkbenchTab(PROJECT_MANAGEMENT_WORKBENCH_TAB_ID)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    const handleProjectSelected = (project) => {
      // 跳转到选中的项目详情页
      router.push({
        name: 'ProjectDetail',
        params: { id: project.id }
      })
    }

    const openNotificationsWorkbenchTab = async () => {
      showUserDropdown.value = false
      clearEmbeddedEditor()
      const tab = {
        id: NOTIFICATIONS_WORKBENCH_TAB_ID,
        kind: 'notifications',
        title: truncateForTab(t('notifInbox.tabTitle'), t('notifInbox.tabTitle')),
        meta: {}
      }
      const idx = workbenchTabs.value.findIndex((x) => x.id === NOTIFICATIONS_WORKBENCH_TAB_ID)
      if (idx >= 0) {
        workbenchTabs.value[idx] = { ...workbenchTabs.value[idx], ...tab }
      } else {
        const cur = workbenchTabs.value.findIndex((x) => x.id === activeWorkbenchTabId.value)
        const insertAt = cur >= 0 ? cur + 1 : workbenchTabs.value.length
        workbenchTabs.value.splice(insertAt, 0, tab)
      }
      await activateWorkbenchTab(NOTIFICATIONS_WORKBENCH_TAB_ID)
      await nextTick()
      scrollActiveWorkbenchTabIntoView()
    }

    const showNotifications = () => {
      openNotificationsWorkbenchTab()
    }
    
    const logout = () => {
      showUserDropdown.value = false
      // 调用store的logout函数
      import('../store/user.js').then(({ logout: logoutUser }) => {
        logoutUser()
      })
      // 跳转到登录页面
      router.push('/login')
    }
    
    // 监听搜索文本变化，实现实时搜索
    watch(planSearchText, (newValue) => {
      console.log('搜索文本变化:', newValue)
      filterPlans()
    })

    // 监听路由变化，当从新建BadCase或Bug页面返回时刷新数据
    watch(() => route.path, (newPath, oldPath) => {
      if (newPath === route.path && oldPath && (oldPath.includes('/new-badcase') || oldPath.includes('/new-bug'))) {
        console.log('从新建/编辑页面返回，刷新数据')
        // 如果路由中有expand_plan，则fetchBadcases会根据选中的计划自动过滤
        fetchBadcases()
      }
    })
    
    // 监听用户信息变化
    watch(userStore, (newUser) => {
      if (newUser) {
        currentUser.value = newUser
      }
    }, { immediate: true })
    
    // 监听项目id变化，确保在路由切换或刷新时同步加载数据
    watch(() => route.params.id, async (newId) => {
      if (newId) {
        projectId.value = newId
        console.log('项目id发生变化:', newId)
        await loadProjectLongMemoryBootstrap()
        await manualRefreshPlans()
        await restorePendingDiffReviews()
        await fetchSessions()
        console.log('[ProjectDetail] sessionHistory.length:', sessionHistory.value.length)
        if (sessionHistory.value.length > 0) {
          currentSession.value = sessionHistory.value[0].id
          sessions.value[currentSession.value] = sessionHistory.value[0]
          console.log('[ProjectDetail] 已设置currentSession:', currentSession.value)
        } else {
          console.log('[ProjectDetail] sessionHistory为空，未设置currentSession')
        }
      }
    }, { immediate: true })

    onMounted(async () => {
      console.log('=== ProjectDetail onMounted ===')
      loadProcessedCreateFromStorage(projectId.value)
                       
      // 监听 grep 导航事件
      window.addEventListener('grep-navigate', handleGrepNavigate)
      window.addEventListener('diff-review-sync', handleDiffReviewSync)

      // 监听 modify 显示事件
      window.addEventListener('show-modify-in-list', handleShowModifyInList)
      window.addEventListener('show-delete-in-list', handleShowDeleteInList)
                
      // 监听清除 pendingModifications 事件
      window.addEventListener('clear-pending-modification', handleClearPendingModification)
          
      // 监听 modify-confirmed 事件（来自对话区）
      window.addEventListener('modify-confirmed', handleModifyConfirmed)
          
      // 监听 modify-cancelled 事件（来自对话区）
      window.addEventListener('modify-cancelled', handleModifyCancelled)
      window.addEventListener('create-pending', handleCreatePending)
      window.addEventListener('show-create-in-list', handleShowCreateInList)
                  
      // 检查URL参数，如果有expand_plan参数，先设置选中的计划ID
      // 这样后续的manualRefreshPlans中的fetchBadcases就能带上正确的plan_id
      const expandPlanId = route.query.expand_plan
      if (expandPlanId) {
        console.log('检测到expand_plan参数，预设selectedPlan:', expandPlanId)
        selectedPlan.value = expandPlanId
      }
      
      // 检查URL参数，如果有content_type参数，设置当前内容类型
      const contentTypeParam = route.query.content_type
      if (contentTypeParam) {
        console.log('检测到content_type参数:', contentTypeParam)
        urlContentType.value = contentTypeParam
      }
      
      // 检查是否有bug_id参数，用于高亮显示
      const bugIdParam = route.query.bug_id
      if (bugIdParam) {
        console.log('检测到bug_id参数:', bugIdParam)
        // 稍后在加载bug列表后高亮该bug
        highlightBugId.value = bugIdParam
      }
      
      // 检查是否有 navigate_plan 和 navigate_bug 参数，用于触发 grep-navigate 事件
      const navigatePlan = route.query.navigate_plan
      const navigateBug = route.query.navigate_bug
      if (navigatePlan && navigateBug) {
        console.log('检测到导航参数，将触发 grep-navigate:', { navigatePlan, navigateBug })
        // 等待页面完全加载后触发事件
        setTimeout(() => {
          const event = new CustomEvent('grep-navigate', {
            detail: { planId: parseInt(navigatePlan), bugId: parseInt(navigateBug), target: 'bug' }
          })
          window.dispatchEvent(event)
          console.log('已触发 grep-navigate 事件')
        }, 1000)
      }
              
      // 获取当前用户信息
      if (userStore.value) {
        currentUser.value = userStore.value
      } else {
        // 如果store中没有用户信息，尝试从localStorage获取
        const userInfo = localStorage.getItem('user')
        if (userInfo) {
          try {
            currentUser.value = JSON.parse(userInfo)
          } catch (e) {
            console.error('解析用户信息失败:', e)
          }
        }
      }
              
      // 添加全局点击监听器，点击外部关闭用户下拉菜单
      document.addEventListener('click', (event) => {
        const userDropdown = document.querySelector('.user-dropdown')
        if (userDropdown && !userDropdown.contains(event.target)) {
          showUserDropdown.value = false
        }
      })
              
      // 处理计划展开逻辑
      if (expandPlanId) {
        // 等待计划数据加载完成（manualRefreshPlans会在watch中被调用）
        // 我们需要等待projectPlans被填充后再执行展开逻辑
        const waitForPlansAndExpand = async () => {
          let attempts = 0
          while (attempts < 20 && projectPlans.value.length === 0) {
            await new Promise(resolve => setTimeout(resolve, 100))
            attempts++
          }
              
          if (projectPlans.value.length > 0) {
            console.log('计划数据已加载，开始执行展开逻辑')
            // 查找并展开该计划及其父计划
            const findAndExpand = (plans, targetId, parents = []) => {
              for (const plan of plans) {
                if (plan.id == targetId) {
                  parents.forEach(parentId => {
                    if (!expandedPlans.value.includes(parentId)) {
                      expandedPlans.value.push(parentId)
                    }
                  })
                  if (!expandedPlans.value.includes(plan.id)) {
                    expandedPlans.value.push(plan.id)
                  }
                  // 再次确保选中该计划并触发数据刷新（以防之前的请求没带上plan_id）
                  selectPlan(plan.id)
                  console.log('已自动展开并刷新计划数据:', plan.name)
                  return true
                }
                if (plan.children && plan.children.length > 0) {
                  if (findAndExpand(plan.children, targetId, [...parents, plan.id])) {
                    return true
                  }
                }
              }
              return false
            }
            findAndExpand(projectPlans.value, expandPlanId)
          }
        }
        waitForPlansAndExpand()
      }

      // 首次进入按持久化状态恢复 pending diff（仅恢复 pending，不恢复 adopted/rejected）
      setTimeout(() => {
        restorePendingDiffReviews()
      }, 800)
    })
    
    // 组件卸载时清理事件监听器
    onUnmounted(() => {
      workbenchMenuOutsideCleanup?.()
      aiHistoryOutsideCleanup?.()
      aiMoreOutsideCleanup?.()
      console.log('=== ProjectDetail onUnmounted ===')
      window.removeEventListener('grep-navigate', handleGrepNavigate)
      window.removeEventListener('diff-review-sync', handleDiffReviewSync)
      window.removeEventListener('show-modify-in-list', handleShowModifyInList)
      window.removeEventListener('show-delete-in-list', handleShowDeleteInList)
      window.removeEventListener('clear-pending-modification', handleClearPendingModification)
      window.removeEventListener('modify-confirmed', handleModifyConfirmed)
      window.removeEventListener('modify-cancelled', handleModifyCancelled)
      window.removeEventListener('create-pending', handleCreatePending)
      window.removeEventListener('show-create-in-list', handleShowCreateInList)
    })

    const inferCreateTargetFromPreview = (pv, explicit) => {
      const ex0 =
        explicit != null && String(explicit).trim() !== ''
          ? String(explicit).trim().toLowerCase()
          : ''
      if (ex0 === 'card') return 'card'
      if (ex0 === 'plan') return 'plan'
      if (ex0 === 'test_case') return 'testcase'
      if (['bug', 'badcase', 'testcase'].includes(ex0)) return ex0

      if (pv && typeof pv === 'object') {
        if (pv.copy_from_card_id != null && String(pv.copy_from_card_id).trim() !== '') return 'card'
        if (pv.source_card_id != null && String(pv.source_card_id).trim() !== '') return 'card'
        if (pv.copy_from_bug_id != null && String(pv.copy_from_bug_id).trim() !== '') return 'bug'
        if (pv.source_bug_id != null && String(pv.source_bug_id).trim() !== '') return 'bug'
        if (pv.copy_from_badcase_id != null || pv.source_badcase_id != null) return 'badcase'
        if (pv.copy_from_testcase_id != null || pv.source_testcase_id != null) return 'testcase'
        // copy 失败仅靠 create 合并字段兜底时，预览里可能没有 copy_from_*，用 Bug 特征推断
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
      }
      return 'bug'
    }

    const handleCreatePending = async (event) => {
      const detail = event?.detail || {}
      const rawPreview = detail.preview
      const messageId = detail.messageId ?? null
      const hasStableMessageScope = messageId !== null && messageId !== undefined
      if (!rawPreview || typeof rawPreview !== 'object') return
      const preview = { ...rawPreview }
      const target = inferCreateTargetFromPreview(preview, detail.target)
      // 预览带错 project_id 时，不丢弃，统一归一到当前项目
      if (
        preview.project_id &&
        Number(projectId.value) &&
        Number(preview.project_id) !== Number(projectId.value)
      ) {
        preview.project_id = Number(projectId.value)
      }
      // 已采纳过（稳定键命中）：不再插入待确认行，直接定位到已创建记录
      const adoptedRowId = getStableCreatedId(projectId.value, target, preview)
      if (adoptedRowId != null) {
        const pid = preview.plan_id ?? preview.planId
        const cidNav = preview.card_id ?? preview.cardId
        window.dispatchEvent(new CustomEvent('grep-navigate', {
          detail: {
            planId: pid,
            bugId: adoptedRowId,
            recordId: adoptedRowId,
            target: target || 'bug',
            ...(cidNav != null && cidNav !== '' ? { card_id: cidNav } : {})
          },
          bubbles: true
        }))
        return
      }
      const createKey = makeCreateKey(target, preview, messageId)

      const navigateCreatePreviewToWorkbench = async () => {
        const pPlan = preview.plan_id ?? preview.planId
        const pn = Number(pPlan)
        const tgt = (target || 'badcase').toString().toLowerCase()
        if (tgt === 'card') {
          const planOk = Number.isFinite(pn) && pn > 0
          if (planOk) {
            expandPlanTreeToPlanId(pn)
            selectedPlan.value = pn
            await fetchCards()
            await nextTick()
            await upsertAndActivatePlanListTab({ planId: pn, urlContentType: null })
            urlContentType.value = null
            currentTypeFilter.value = ''
          } else {
            clearEmbeddedEditor()
            urlContentType.value = null
            currentTypeFilter.value = ''
            selectedPlan.value = null
            await nextTick()
          }
          return
        }
        const uct =
          tgt === 'badcase' ? 'badcase' : tgt === 'testcase' || tgt === 'test_case' ? 'test_case' : 'bug'
        const typeForNav =
          tgt === 'badcase'
            ? 'badcase'
            : tgt === 'testcase' || tgt === 'test_case'
              ? 'testcase'
              : 'bug'
        const planOk = Number.isFinite(pn) && pn > 0
        if (planOk) {
          expandPlanTreeToPlanId(pn)
          selectedPlan.value = pn
          let openedTypeList = false
          if (['bug', 'badcase', 'testcase', 'test_case'].includes(tgt)) {
            await fetchCards()
            await nextTick()
            let cardRow = null
            const navCopyCardId = preview.nav_copy_source_card_id ?? preview.navCopySourceCardId
            if (navCopyCardId != null && navCopyCardId !== '') {
              const ncid =
                typeof navCopyCardId === 'number'
                  ? navCopyCardId
                  : parseInt(String(navCopyCardId), 10)
              if (Number.isFinite(ncid) && ncid > 0) {
                cardRow = cards.value.find((c) => Number(c.id) === ncid) || null
              }
            }
            const explicitCardId = preview.card_id ?? preview.cardId
            if (!cardRow && explicitCardId != null && explicitCardId !== '') {
              const cid =
                typeof explicitCardId === 'number'
                  ? explicitCardId
                  : parseInt(String(explicitCardId), 10)
              if (Number.isFinite(cid) && cid > 0) {
                cardRow = cards.value.find((c) => Number(c.id) === cid) || null
                if (!cardRow?.id) {
                  try {
                    const res = await getCardDetail(cid)
                    const card = res?.data?.data
                    if (res?.data?.success && card?.id) {
                      cardRow = { id: card.id, title: card.title }
                    }
                  } catch (e) {
                    console.warn('[CREATE-NAV] getCardDetail(preview.card_id):', e)
                  }
                }
              }
            }
            if (!cardRow) {
              let srcId = null
              if (typeForNav === 'bug') {
                srcId = preview.copy_from_bug_id ?? preview.source_bug_id
              } else if (typeForNav === 'badcase') {
                srcId = preview.copy_from_badcase_id ?? preview.source_badcase_id
              } else {
                srcId = preview.copy_from_testcase_id ?? preview.source_testcase_id
              }
              if (srcId != null && srcId !== '') {
                const n = typeof srcId === 'number' ? srcId : parseInt(String(srcId), 10)
                if (Number.isFinite(n) && n > 0) {
                  cardRow = resolveCardForListNav(n, typeForNav)
                }
              }
            }
            // 分页首屏未包含源卡片时，用详情接口补齐（面包屑「迭代/卡片名」与采纳后列表上下文）
            if (!cardRow?.id && navCopyCardId != null && navCopyCardId !== '') {
              const ncid =
                typeof navCopyCardId === 'number'
                  ? navCopyCardId
                  : parseInt(String(navCopyCardId), 10)
              if (Number.isFinite(ncid) && ncid > 0) {
                try {
                  const res = await getCardDetail(ncid)
                  const card = res?.data?.data
                  if (res?.data?.success && card?.id) {
                    cardRow = { id: card.id, title: card.title }
                  }
                } catch (e) {
                  console.warn('[CREATE-NAV] getCardDetail(nav_copy):', e)
                }
              }
            }
            if (!cardRow?.id) {
              const srcRid =
                typeForNav === 'bug'
                  ? preview.copy_from_bug_id ?? preview.source_bug_id
                  : typeForNav === 'badcase'
                    ? preview.copy_from_badcase_id ?? preview.source_badcase_id
                    : preview.copy_from_testcase_id ?? preview.source_testcase_id
              if (srcRid != null && srcRid !== '') {
                const n = typeof srcRid === 'number' ? srcRid : parseInt(String(srcRid), 10)
                if (Number.isFinite(n) && n > 0) {
                  cardRow = await resolveCardRowByRecordDetailApi(n, typeForNav)
                }
              }
            }
            logListNav('createPreviewNavigate', {
              planId: pn,
              typeForNav,
              navCopySourceCardId: navCopyCardId,
              explicitCardId: preview.card_id ?? preview.cardId,
              copyFromBug: preview.copy_from_bug_id ?? preview.source_bug_id,
              copyFromBadcase: preview.copy_from_badcase_id ?? preview.source_badcase_id,
              copyFromTc: preview.copy_from_testcase_id ?? preview.source_testcase_id,
              cardsPageLen: Array.isArray(cards.value) ? cards.value.length : 0,
              cardRow: cardRow ? { id: cardRow.id, title: cardRow.title } : null,
              fallthroughToPlanTab: !cardRow?.id
            })
            if (cardRow?.id) {
              await upsertAndActivateTypeListTab({
                planId: pn,
                cardId: cardRow.id,
                type: typeForNav,
                cardTitle: cardRow.title
              })
              openedTypeList = true
            }
          }
          if (!openedTypeList) {
            await upsertAndActivatePlanListTab({ planId: pn, urlContentType: uct })
          }
        } else {
          // plan_id 缺失时 upsertAndActivatePlanListTab 不会激活 Tab，否则仍停在 Card 表 / 错误视图，待确认新建行在列表组件里
          clearEmbeddedEditor()
          urlContentType.value = uct
          currentTypeFilter.value =
            tgt === 'badcase' ? 'badcase' : tgt === 'testcase' || tgt === 'test_case' ? 'testcase' : 'bug'
          selectedPlan.value = null
          await nextTick()
        }
      }

      // 仅在带 messageId 时才应用「已确认/已取消」拦截；拦截时仍应跳到对应计划/卡片列表（否则点击预览条无反馈）
      if (hasStableMessageScope && processedCreateKeyMap[createKey]) {
        const createdFallback =
          createdIdByCreateKey[createKey] ??
          getStableCreatedId(projectId.value, target, preview)
        if (createdFallback != null) {
          const pid = preview.plan_id ?? preview.planId
          const cidFb = preview.card_id ?? preview.cardId
          window.dispatchEvent(
            new CustomEvent('grep-navigate', {
              detail: {
                planId: pid,
                bugId: createdFallback,
                recordId: createdFallback,
                target: target || 'bug',
                ...(cidFb != null && cidFb !== '' ? { card_id: cidFb } : {})
              },
              bubbles: true
            })
          )
          return
        }
        await navigateCreatePreviewToWorkbench()
        return
      }

      const tempId = `create_${Date.now()}_${Math.random().toString(16).slice(2)}`
      pendingCreates.value = [
        ...pendingCreates.value.filter(x => x.createKey !== createKey),
        { tempId, target, preview, messageId, createdAt: Date.now(), createKey }
      ]
      await navigateCreatePreviewToWorkbench()

      setTimeout(() => {
        const el = document.querySelector(`[data-create-id="${tempId}"]`)
        if (el && el.scrollIntoView) {
          el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        }
      }, 50)
    }

    const handleShowCreateInList = (event) => {
      handleCreatePending(event)
    }

    /** 采纳新建后滚动到列表中对应行（与 grep / modify 定位一致） */
    const scrollToCreatedListRow = async (createdId, opts = {}) => {
      if (createdId == null || createdId === '') return
      const id = Number(createdId)
      if (!Number.isFinite(id)) return
      const cardIdRaw = opts.cardId ?? opts.card_id
      const cid =
        cardIdRaw != null && cardIdRaw !== ''
          ? Number(cardIdRaw)
          : NaN
      const selectors = [`[data-bug-id="${id}"]`]
      if (Number.isFinite(cid) && cid > 0) {
        selectors.push(`[data-card-id="${cid}"]`, `[data-item-id="${cid}"]`)
      }
      for (let attempt = 0; attempt < 18; attempt++) {
        await nextTick()
        await new Promise((r) => setTimeout(r, attempt === 0 ? 80 : 120))
        for (const sel of selectors) {
          const el = document.querySelector(sel)
          if (el && el.scrollIntoView) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            el.classList.add('highlight-row')
            setTimeout(() => el.classList.remove('highlight-row'), 3000)
            return
          }
        }
      }
      console.warn('[CREATE] 未找到列表行，无法滚动:', selectors.join(', '))
    }

    /** 新建预览里用于导航的复制源 id，不应随 POST 提交（与落库字段无关） */
    const stripNavOnlyCreatePreview = (p) => {
      const o = { ...(p || {}) }
      delete o.copy_from_bug_id
      delete o.source_bug_id
      delete o.copy_from_badcase_id
      delete o.source_badcase_id
      delete o.copy_from_testcase_id
      delete o.source_testcase_id
      delete o.copy_from_card_id
      delete o.source_card_id
      delete o.nav_copy_source_card_id
      delete o.navCopySourceCardId
      return o
    }

    const confirmCreate = async (tempId) => {
      const item = pendingCreates.value.find(x => x.tempId === tempId)
      if (!item) return
      const target = item.target
      const preview = item.preview || {}
      const createKey = item.createKey || makeCreateKey(target, preview, item.messageId || null)
      const previewForApi = stripNavOnlyCreatePreview(preview)
      try {
        let createdId = null
        let createdCardId = null
        if (target === 'testcase' || target === 'test_case') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/testcases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(previewForApi)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建TestCase失败')
          createdId = res?.testcase?.id ?? res?.id ?? null
          createdCardId = res?.testcase?.card_id ?? res?.card_id ?? null
        } else if (target === 'bug') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/bugs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(previewForApi)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建Bug失败')
          createdId = res?.bug?.id ?? res?.id ?? null
          createdCardId = res?.bug?.card_id ?? null
        } else if (target === 'badcase') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/badcases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(previewForApi)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建BadCase失败')
          createdId = res?.badcase?.id ?? res?.id ?? null
          createdCardId = res?.badcase?.card_id ?? null
        } else if (target === 'card') {
          const rawTy = (previewForApi.type || 'bug').toString().toLowerCase()
          const body = {
            title: previewForApi.title,
            type: rawTy === 'bad_case' ? 'badcase' : rawTy,
            project_id: Number(projectId.value),
            priority: previewForApi.priority || 'p3',
            description: previewForApi.description,
            assignee_id: previewForApi.assignee_id
          }
          const pp = previewForApi.plan_id ?? previewForApi.planId
          if (pp != null && pp !== '') {
            const pNum = Number(pp)
            if (Number.isFinite(pNum) && pNum > 0) body.plan_id = pNum
          }
          const res = await fetch(`${BACKEND_BASE_URL}/api/cards`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建卡片失败')
          const row = res?.data || {}
          createdId = row.id ?? res?.id ?? null
          createdCardId = createdId
        } else {
          throw new Error(`不支持的创建类型: ${target}`)
        }
        processedCreateKeyMap[createKey] = true
        createdIdByCreateKey[createKey] = createdId
        persistProcessedCreateKey(projectId.value, createKey, { createdId, target, messageId: item.messageId || null })
        persistStableCreatedId(projectId.value, target, preview, createdId)

        pendingCreates.value = pendingCreates.value.filter(x => x.tempId !== tempId)

        window.dispatchEvent(
          new CustomEvent('create-adopted-from-list', {
            detail: {
              messageId: item.messageId ?? null,
              createKey,
              target,
              preview,
              createdId,
              tempId
            },
            bubbles: true
          })
        )

        let targetPlanId = preview.plan_id ?? preview.planId
        if (createdId != null && (target === 'bug' || target === 'testcase' || target === 'test_case' || target === 'badcase')) {
          const tt = target === 'test_case' ? 'testcase' : target
          const rp = await resolvePlanIdByRecordApi(tt, createdId)
          if (rp != null) {
            targetPlanId = rp
          }
        }
        if (targetPlanId && Number(selectedPlan.value) !== Number(targetPlanId)) {
          const expandPlanAndParents = (tid) => {
            const findAndExpand = (plans, targetId, parents = []) => {
              for (const plan of plans) {
                if (plan.id === targetId) {
                  parents.forEach((parentId) => {
                    if (!expandedPlans.value.includes(parentId)) {
                      expandedPlans.value.push(parentId)
                    }
                  })
                  return true
                }
                if (plan.children && plan.children.length > 0) {
                  if (findAndExpand(plan.children, targetId, [...parents, plan.id])) {
                    return true
                  }
                }
              }
              return false
            }
            findAndExpand(projectPlans.value, tid)
          }
          expandPlanAndParents(Number(targetPlanId))
          await selectPlan(Number(targetPlanId))
          await refreshBadcases()
        } else {
          await refreshBadcases()
        }
        await fetchProjectPlans()
        if (target === 'card') {
          await fetchCards(1).catch((e) => console.warn('[CREATE] fetchCards 失败:', e))
        }
        if (createdId != null) {
          await scrollToCreatedListRow(createdId, { cardId: createdCardId ?? createdId })
        }
      } catch (e) {
        console.error('[CREATE] 创建失败:', e)
      }
    }

    const cancelCreate = (tempId) => {
      const item = pendingCreates.value.find(x => x.tempId === tempId)
      if (item) {
        const createKey = item.createKey || makeCreateKey(item.target, item.preview, item.messageId || null)
        processedCreateKeyMap[createKey] = true
        persistProcessedCreateKey(projectId.value, createKey, { rejected: true, target: item.target, messageId: item.messageId || null })
      }
      pendingCreates.value = pendingCreates.value.filter(x => x.tempId !== tempId)
    }

    /** 新建预览跨分页：同一会话 messageId + 同 target 视为一批（可选 peerTempIds 显式顺序） */
    const uniqPreserveOrderStringIds = (arr) => {
      const seen = new Set()
      const out = []
      for (const x of arr || []) {
        const s = x == null ? '' : String(x)
        if (!s || seen.has(s)) continue
        seen.add(s)
        out.push(s)
      }
      return out
    }

    const getCreateClusterTempIds = (tempId) => {
      const list = pendingCreates.value || []
      const item = list.find((x) => x.tempId === tempId)
      if (!item) return [tempId]

      if (Array.isArray(item.peerTempIds) && item.peerTempIds.length >= 2) {
        const order = uniqPreserveOrderStringIds(item.peerTempIds)
        const filtered = order.filter((tid) => list.some((x) => x.tempId === tid))
        if (filtered.length >= 2) return filtered
      }

      const mid = item.messageId
      if (mid != null && mid !== '') {
        const cluster = list
          .filter(
            (x) =>
              String(x.messageId ?? '') === String(mid) &&
              String(x.target || '') === String(item.target || '')
          )
          .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
          .map((x) => x.tempId)
        if (cluster.length >= 2) return cluster
      }
      return [tempId]
    }

    const isLastInCreateCluster = (tempId) => {
      const g = getCreateClusterTempIds(tempId)
      return g.length > 0 && g[g.length - 1] === tempId
    }

    const getCreateClusterSize = (tempId) => {
      return getCreateClusterTempIds(tempId).length
    }

    const confirmConsecutiveCreateGroup = async (tempId) => {
      const ids = getCreateClusterTempIds(tempId)
      for (const tid of ids) {
        await confirmCreate(tid)
      }
    }

    const cancelConsecutiveCreateGroup = (tempId) => {
      for (const tid of getCreateClusterTempIds(tempId)) {
        cancelCreate(tid)
      }
    }

    // 处理 grep 导航事件
    const handleClearPendingModification = (event) => {
      const { targetId } = event.detail
      console.log('[MODIFY] 收到清除 pendingModifications 指令:', targetId)
          
      // 清除 pendingModifications 中的标记
      const newPending = { ...pendingModifications.value }
      delete newPending[targetId]
      pendingModifications.value = newPending
      console.log('[MODIFY] 已清除 pendingModifications:', pendingModifications.value)
    }
    
    // 处理 modify-confirmed 事件（来自对话区）
    const handleModifyConfirmed = async (event) => {
      const detail = event.detail || {}
      const targetId = detail.targetId
      const deletedTargetType = detail.deletedTargetType
      console.log('[MODIFY] 收到 modify-confirmed 事件:', targetId, deletedTargetType)
      
      // 清除 pendingModifications 中的标记
      const newPending = { ...pendingModifications.value }
      delete newPending[targetId]
      pendingModifications.value = newPending
      console.log('[MODIFY] 已清除 pendingModifications:', pendingModifications.value)

      if (deletedTargetType === 'card') {
        await fetchCards(1).catch((e) => console.warn('[DELETE] fetchCards 失败:', e))
      } else if (['bug', 'badcase', 'testcase'].includes(deletedTargetType)) {
        await fetchBadcases(1).catch((e) => console.warn('[DELETE] fetchBadcases 失败:', e))
      }
    }
    
    // 处理 modify-cancelled 事件（来自对话区）
    const handleModifyCancelled = (event) => {
      const { targetId } = event.detail
      console.log('[MODIFY] 收到 modify-cancelled 事件:', targetId)
      
      // 清除 pendingModifications 中的标记
      const newPending = { ...pendingModifications.value }
      delete newPending[targetId]
      pendingModifications.value = newPending
      console.log('[MODIFY] 已清除 pendingModifications:', pendingModifications.value)
    }

    // 同一条批量/合并预览里，部分记录的 diff 可能为空，导致未写入 pending；用同组 id 从已有 pending 补齐
    const applyPeerPendingSync = (currentId, peerTargetIds) => {
      if (!peerTargetIds || !Array.isArray(peerTargetIds) || peerTargetIds.length < 2) return
      const ids = [...new Set(peerTargetIds.map(Number).filter((n) => !isNaN(n)))]
      if (ids.length < 2) return
      let source = null
      for (const id of ids) {
        const p = pendingModifications.value[id]
        const realKeys = p ? Object.keys(p).filter((k) => !k.startsWith('_')) : []
        if (realKeys.length > 0) {
          source = p
          break
        }
      }
      if (!source) return
      const next = { ...pendingModifications.value }
      let changed = false
      for (const pid of ids) {
        const existing = next[pid]
        const realKeys = existing ? Object.keys(existing).filter((k) => !k.startsWith('_')) : []
        if (realKeys.length === 0) {
          next[pid] = { ...source }
          changed = true
        }
      }
      if (changed) pendingModifications.value = next
      mergePeerTargetIdsIntoPending(peerTargetIds)
    }

    /** 与 handleShowModifyInList 内逻辑一致，供批量同步写入 pending 时复用 */
    const buildModifyDataFromShowModifyDetail = (detail) => {
      const modifyData = {}
      const diff = detail?.diff
      const modifications = detail?.modifications
      const before = detail?.before && typeof detail.before === 'object' ? detail.before : null
      const after = detail?.after && typeof detail.after === 'object' ? detail.after : null
      const tgt = String(detail?.target || '').toLowerCase()
      const bugish = tgt === 'bug' || tgt === 'card'
      /** Bug/BadCase/TestCase/卡片层 status：卡片快照从源表补 status 后，与 diff 对齐 */
      const rowSnapshotTargets = ['bug', 'badcase', 'testcase', 'card'].includes(tgt)
      const snapAssignee = (row) => {
        if (!row || typeof row !== 'object') return ''
        const v = row.assignee_display ?? row.assignee ?? row.assignee_id
        return v == null ? '' : String(v)
      }
      const snapListField = (row, fieldKey) => {
        if (!row || typeof row !== 'object') return ''
        if (fieldKey === 'assignee') return snapAssignee(row)
        const v = row[fieldKey]
        return v == null ? '' : String(v)
      }
      if (diff && Array.isArray(diff) && diff.length > 0) {
        diff.forEach((fieldDiff) => {
          const rawField = fieldDiff.field ?? fieldDiff.field_label
          const fieldKey = normalizeDiffFieldKey(rawField)
          const oldLine = fieldDiff.lines?.find((l) => l.type === 'delete')
          const newLine = fieldDiff.lines?.find((l) => l.type === 'add')
          const unchangedLine = fieldDiff.lines?.find((l) => l.type === 'unchanged')
          if (oldLine && newLine) {
            let oldC = oldLine.content
            let newC = newLine.content
            /** diff 行里「优先级」常被模型/渲染成重复中文，真实值以 before/after 为准 */
            if (bugish && fieldKey === 'priority' && (before || after)) {
              const bo = before?.priority
              const ao = after?.priority
              if (bo != null && String(bo).trim() !== '') oldC = bo
              if (ao != null && String(ao).trim() !== '') newC = ao
            }
            if (
              rowSnapshotTargets &&
              ['status', 'title', 'assignee'].includes(fieldKey) &&
              (before || after)
            ) {
              if (String(oldC ?? '').trim() === '') {
                const bo = snapListField(before, fieldKey)
                if (bo) oldC = bo
              }
              if (String(newC ?? '').trim() === '') {
                const ao = snapListField(after, fieldKey)
                if (ao) newC = ao
              }
            }
            modifyData[fieldKey] = { old: oldC, new: newC }
          } else if (
            (bugish || rowSnapshotTargets) &&
            (before || after) &&
            (oldLine || newLine) &&
            !unchangedLine
          ) {
            const oldC = oldLine ? String(oldLine.content ?? '') : snapListField(before, fieldKey)
            const newC = newLine ? String(newLine.content ?? '') : snapListField(after, fieldKey)
            if (oldC !== newC) {
              modifyData[fieldKey] = { old: oldC, new: newC }
            }
          } else if (unchangedLine) {
            modifyData[fieldKey] = {
              old: unchangedLine.content,
              new: unchangedLine.content,
              unchanged: true
            }
          }
        })
      } else if (modifications && typeof modifications === 'object') {
        for (const [field, value] of Object.entries(modifications)) {
          const fk = normalizeDiffFieldKey(field)
          if (value && typeof value === 'object' && 'new' in value) {
            let entry = { ...value }
            if (
              rowSnapshotTargets &&
              (before || after) &&
              ['status', 'title', 'assignee'].includes(fk) &&
              (!entry.old || String(entry.old).trim() === '')
            ) {
              const bo = snapListField(before, fk)
              if (bo) entry = { ...entry, old: bo }
            }
            modifyData[fk] = entry
          } else {
            const bo =
              rowSnapshotTargets && before ? snapListField(before, fk) : ''
            modifyData[fk] = { old: bo || '', new: value }
          }
        }
      }
      if (rowSnapshotTargets && (before || after)) {
        for (const fk of ['status', 'title', 'assignee']) {
          if (modifyData[fk]) continue
          const bs = snapListField(before, fk)
          const as = snapListField(after, fk)
          if (bs !== as) {
            modifyData[fk] = { old: bs, new: as }
          }
        }
      }
      // card + status：payload.before 常无 status（卡片快照未带源表），用已加载 Bug/卡片列表兜底
      if (
        tgt === 'card' &&
        modifyData.status &&
        (!modifyData.status.old || String(modifyData.status.old).trim() === '')
      ) {
        const cid = parseInt(String(detail?.targetId ?? ''), 10)
        if (!Number.isNaN(cid) && cid > 0) {
          let fill = ''
          if (Array.isArray(badcases.value)) {
            const br = badcases.value.find((b) => Number(b.card_id ?? b.cardId) === cid)
            if (br?.status != null && String(br.status).trim() !== '') fill = String(br.status)
          }
          if (!fill && Array.isArray(cards.value)) {
            const cr = cards.value.find((c) => Number(c.id) === cid)
            if (cr?.status != null && String(cr.status).trim() !== '') fill = String(cr.status)
          }
          if (fill) {
            modifyData.status = { ...modifyData.status, old: fill }
          }
        }
      }
      if (
        typeof import.meta !== 'undefined' &&
        import.meta.env?.DEV &&
        tgt === 'card' &&
        modifyData.status &&
        (!modifyData.status.old || String(modifyData.status.old).trim() === '')
      ) {
        console.warn('[buildModifyData] card+status 旧值仍为空（检查 Card.source 与 bug.card_id）', {
          targetId: detail?.targetId,
          beforeKeys: before ? Object.keys(before) : [],
          afterStatus: after?.status,
          diffStatusDelete: diff?.find?.((d) => (d.field || d.field_label) === 'status')?.lines
        })
      }
      return modifyData
    }

    /**
     * 将 modify 产生的字段（含列表列 title/status/assignee 与详情字段）合并进 pendingModifications，
     * 避免「仅详情字段」分支提前 return 时列表行内不显示标题/状态/负责人 diff。
     */
    const mergePendingModifyOverlayFromModifyData = (modifyData, intTargetId, meta) => {
      if (meta?.executed === true) return
      if (intTargetId == null || Number.isNaN(Number(intTargetId))) return
      const md = modifyData && typeof modifyData === 'object' ? modifyData : {}
      const overlay = {}
      for (const [fk, v] of Object.entries(md)) {
        const nk = normalizeDiffFieldKey(fk)
        if (!v || typeof v !== 'object' || !('new' in v)) continue
        if (v.unchanged === true) continue
        overlay[nk] = v
      }
      if (Object.keys(overlay).length === 0) return
      const next = { ...pendingModifications.value }
      const prev = next[intTargetId] || {}
      next[intTargetId] = {
        ...prev,
        ...overlay,
        _target: meta.target,
        _messageId: meta.messageId,
        _naturalQuery: typeof meta.natural_query === 'string' ? meta.natural_query : ''
      }
      pendingModifications.value = next
    }

    /** 同步写入一条待确认（不 await），避免同组多条 async 交错导致黄条逐个出现 */
    const syncApplyShowModifyListPendingFromDetail = (detail, opts = {}) => {
      const writeSession = opts.sessionStorageWrite === true
      if (detail.executed === true) return
      const modifyData = buildModifyDataFromShowModifyDetail(detail)
      const fieldKeys = Object.keys(modifyData)
      if (fieldKeys.length === 0) return
      const intTargetId = parseInt(detail.targetId, 10)
      if (Number.isNaN(intTargetId)) return
      const { target, diff, messageId, batchIndex } = detail

      if (diff && Array.isArray(diff) && diff.length > 0 && writeSession) {
        sessionStorage.removeItem('pendingModifyDiff')
        sessionStorage.setItem(
          'pendingModifyDiff',
          JSON.stringify({
            targetId: intTargetId,
            target: target,
            diff: diff,
            modifications: modifyData,
            messageId: messageId,
            batchIndex: batchIndex
          })
        )
      }

      if (diff && Array.isArray(diff) && diff.length > 0) {
        mergePendingModifyOverlayFromModifyData(modifyData, intTargetId, {
          target,
          messageId,
          natural_query: typeof detail.natural_query === 'string' ? detail.natural_query : '',
          peerTargetIds: detail.peerTargetIds,
          executed: detail.executed
        })
      }
    }

    /** 批量：合并写入 pending + sessionStorage，只触发一次响应式更新，避免列表黄条连闪 */
    const syncApplyShowModifyListBatchFromDetails = (items) => {
      if (!Array.isArray(items) || items.length === 0) return
      let sessionWritten = false
      const base = { ...pendingModifications.value }
      let touched = false
      for (let i = 0; i < items.length; i++) {
        const detail = items[i]
        if (detail.executed === true) continue
        const modifyData = buildModifyDataFromShowModifyDetail(detail)
        const fieldKeys = Object.keys(modifyData)
        if (fieldKeys.length === 0) continue
        const intTargetId = parseInt(detail.targetId, 10)
        if (Number.isNaN(intTargetId)) continue
        const { target, diff, messageId, batchIndex } = detail

        if (diff && Array.isArray(diff) && diff.length > 0 && !sessionWritten) {
          try {
            sessionStorage.removeItem('pendingModifyDiff')
            sessionStorage.setItem(
              'pendingModifyDiff',
              JSON.stringify({
                targetId: intTargetId,
                target: target,
                diff: diff,
                modifications: modifyData,
                messageId: messageId,
                batchIndex: batchIndex
              })
            )
          } catch (_e) {
            /* ignore */
          }
          sessionWritten = true
        }

        if (diff && Array.isArray(diff) && diff.length > 0) {
          const prev = base[intTargetId] || {}
          const overlay = {}
          for (const [fk, v] of Object.entries(modifyData)) {
            const nk = normalizeDiffFieldKey(fk)
            if (!v || typeof v !== 'object' || !('new' in v)) continue
            if (v.unchanged === true) continue
            overlay[nk] = v
          }
          if (Object.keys(overlay).length > 0) {
            base[intTargetId] = {
              ...prev,
              ...overlay,
              _target: target,
              _messageId: messageId,
              _naturalQuery: typeof detail.natural_query === 'string' ? detail.natural_query : ''
            }
            touched = true
          }
        }
      }
      if (touched) pendingModifications.value = base
      const p0 = items[0]
      if (p0?.peerTargetIds && Array.isArray(p0.peerTargetIds) && p0.peerTargetIds.length >= 2) {
        mergePeerTargetIdsIntoPending(p0.peerTargetIds)
      }
    }

    /**
     * 将导航 record_id（可能是 Card.id 或源表 id）解析为所在卡片行。
     */
    const resolveCardForListNav = (rid, navTarget) => {
      if (rid == null || rid === '') return null
      const n = Number(rid)
      if (Number.isNaN(n) || n <= 0) return null
      const nt = (navTarget || '').toString().toLowerCase()
      const list = cards.value
      if (!Array.isArray(list) || list.length === 0) return null

      const stBug = (s) => String(s || '').toLowerCase() === 'bug'
      const stBad = (s) => {
        const t = String(s || '').toLowerCase()
        return t === 'bad_case' || t === 'badcase'
      }
      const stTc = (s) => {
        const t = String(s || '').toLowerCase()
        return t === 'test_case' || t === 'testcase'
      }

      let match = null
      if (nt === 'bug') {
        match = list.find(
          (c) =>
            String(c.type || '').toLowerCase() === 'bug' &&
            (Number(c.id) === n || (stBug(c.source_type) && Number(c.source_id) === n))
        )
      } else if (nt === 'badcase') {
        match = list.find(
          (c) =>
            String(c.type || '').toLowerCase() === 'badcase' &&
            (Number(c.id) === n || (stBad(c.source_type) && Number(c.source_id) === n))
        )
      } else if (nt === 'testcase' || nt === 'test_case') {
        match = list.find(
          (c) =>
            String(c.type || '').toLowerCase() === 'testcase' &&
            (Number(c.id) === n || (stTc(c.source_type) && Number(c.source_id) === n))
        )
      } else if (nt === 'card') {
        match = list.find((c) => Number(c.id) === n)
      }

      return match || null
    }

    /**
     * 卡片接口分页时当前页可能不含目标卡片；用 Bug/BadCase/TestCase 详情里的 card_id 补齐，
     * 避免 grep / 新建预览跳转只能落到「迭代计划」Tab、缺少卡片层。
     */
    const resolveCardRowByRecordDetailApi = async (rid, navTarget) => {
      const n = typeof rid === 'number' ? rid : parseInt(String(rid), 10)
      if (!Number.isFinite(n) || n <= 0) return null
      const nt = (navTarget || '').toString().toLowerCase()
      const ntUse = nt === 'test_case' ? 'testcase' : nt
      let cidRaw = null
      let fallbackTitle = ''
      try {
        if (ntUse === 'bug') {
          const res = await getBugDetail(n)
          const b = res?.data?.bug
          if (!res?.data?.success || !b) return null
          cidRaw = b.card_id ?? b.cardId
          fallbackTitle = b.title || ''
        } else if (ntUse === 'badcase') {
          const res = await getBadcaseDetail(n)
          const bc = res?.data?.badcase
          if (!res?.data?.success || !bc) return null
          cidRaw = bc.card_id ?? bc.cardId
          fallbackTitle = bc.title || ''
        } else if (ntUse === 'testcase') {
          const res = await getTestCaseDetail(n)
          const tc = res?.data?.testcase
          if (!res?.data?.success || !tc) return null
          cidRaw = tc.card_id ?? tc.cardId
          fallbackTitle = tc.title || tc.name || ''
        } else {
          return null
        }
      } catch (e) {
        console.warn('[NAV] resolveCardRowByRecordDetailApi failed', ntUse, n, e)
        return null
      }
      if (cidRaw == null || cidRaw === '') {
        logListNav('recordDetailNoCardId', {
          navTarget: ntUse,
          recordId: n,
          note: '详情里无 card_id，无法挂到卡片 Tab'
        })
        return null
      }
      const ci = typeof cidRaw === 'number' ? cidRaw : parseInt(String(cidRaw), 10)
      if (!Number.isFinite(ci) || ci <= 0) return null
      let cardRow =
        Array.isArray(cards.value) ? cards.value.find((c) => Number(c.id) === ci) || null : null
      if (!cardRow?.id) {
        try {
          const cr = await getCardDetail(ci)
          const cdata = cr?.data?.data
          if (cr?.data?.success && cdata?.id) {
            cardRow = { id: cdata.id, title: cdata.title }
          } else {
            cardRow = { id: ci, title: fallbackTitle || '' }
          }
        } catch (e) {
          console.warn('[NAV] getCardDetail(resolveCardRowByRecordDetailApi)', e)
          cardRow = { id: ci, title: fallbackTitle || '' }
        }
      }
      logListNav('recordDetailResolvedCard', {
        navTarget: ntUse,
        recordId: n,
        cardId: cardRow?.id,
        cardTitle: cardRow?.title
      })
      return cardRow
    }

    /**
     * 沙箱 show-modify-in-list：当前计划「卡片列表」页可能不含目标卡片或 source 映射失败时，
     * 与 grep 导航一致，用显式 card_id / before.after / 详情接口解析卡片，避免 Bug 等退化成仅「迭代计划」Tab。
     */
    const resolveCardRowForModifyListNav = async (recordId, navTarget, detail = {}) => {
      const rid =
        typeof recordId === 'number' ? recordId : parseInt(String(recordId ?? ''), 10)
      if (!Number.isFinite(rid) || rid <= 0) return null
      const ntRaw = (navTarget || '').toString().toLowerCase()
      const nt = ntRaw === 'test_case' ? 'testcase' : ntRaw
      if (!['bug', 'badcase', 'testcase'].includes(nt)) return null

      let cardRow = null
      let explicitEc = null
      const explicitCidRaw = detail.card_id ?? detail.cardId
      if (explicitCidRaw != null && explicitCidRaw !== '') {
        explicitEc =
          typeof explicitCidRaw === 'number' ? explicitCidRaw : parseInt(String(explicitCidRaw), 10)
        if (!Number.isNaN(explicitEc) && explicitEc > 0 && Array.isArray(cards.value)) {
          cardRow = cards.value.find((c) => Number(c.id) === explicitEc) || null
        }
      }
      if (!cardRow?.id && explicitEc != null && !Number.isNaN(explicitEc) && explicitEc > 0) {
        try {
          const cr = await getCardDetail(explicitEc)
          const cdata = cr?.data?.data
          if (cr?.data?.success && cdata?.id) {
            cardRow = { id: cdata.id, title: cdata.title }
          }
        } catch (e) {
          console.warn('[MODIFY-NAV] getCardDetail(card_id):', e)
        }
      }

      const before = detail.before && typeof detail.before === 'object' ? detail.before : null
      const after = detail.after && typeof detail.after === 'object' ? detail.after : null
      if (!cardRow?.id) {
        const bcid = before?.card_id ?? before?.cardId ?? after?.card_id ?? after?.cardId
        if (bcid != null && bcid !== '') {
          const ci = typeof bcid === 'number' ? bcid : parseInt(String(bcid), 10)
          if (!Number.isNaN(ci) && ci > 0) {
            if (Array.isArray(cards.value)) {
              cardRow = cards.value.find((c) => Number(c.id) === ci) || null
            }
            if (!cardRow?.id) {
              try {
                const cr = await getCardDetail(ci)
                const cdata = cr?.data?.data
                if (cr?.data?.success && cdata?.id) {
                  cardRow = { id: cdata.id, title: cdata.title }
                }
              } catch (e) {
                console.warn('[MODIFY-NAV] getCardDetail(before/after.card_id):', e)
              }
            }
            if (!cardRow?.id) {
              cardRow = { id: ci, title: '' }
            }
          }
        }
      }

      if (!cardRow) {
        cardRow = resolveCardForListNav(rid, nt)
      }
      if (!cardRow?.id) {
        cardRow = await resolveCardRowByRecordDetailApi(rid, nt)
      }
      return cardRow?.id ? cardRow : null
    }

    /**
     * grep/modify 列表定位：行上为 Card.id；源表 id 需先用 resolveCardForListNav 映射。
     * target=card：Bug 子表行用 data-card-id=Card.id，勿先用 data-bug-id（会与「Bug 主键=id」撞车且子表无 item-id）。
     */
    const findNavListRowEl = (rid, navTarget) => {
      if (rid == null || rid === '') return null
      const idStr = String(rid)
      const nt = String(navTarget || '').toLowerCase()

      if (nt === 'card') {
        const byCardAttr = document.querySelector(`[data-card-id="${idStr}"]`)
        if (byCardAttr) return byCardAttr
        const byItem = document.querySelector(`[data-item-id="${idStr}"]`)
        if (byItem) return byItem
        const match = resolveCardForListNav(rid, navTarget)
        if (!match?.id) return null
        const cid = String(match.id)
        return (
          document.querySelector(`[data-card-id="${cid}"]`) ||
          document.querySelector(`[data-item-id="${cid}"]`) ||
          document.querySelector(`[data-bug-id="${cid}"]`)
        )
      }

      let el =
        document.querySelector(`[data-bug-id="${idStr}"]`) ||
        document.querySelector(`[data-item-id="${idStr}"]`)
      if (el) return el

      const match = resolveCardForListNav(rid, navTarget)
      if (!match) return null
      const cid = String(match.id)
      return (
        document.querySelector(`[data-item-id="${cid}"]`) ||
        document.querySelector(`[data-bug-id="${cid}"]`) ||
        document.querySelector(`[data-card-id="${cid}"]`)
      )
    }

    /** delete 工具 preview（confirm=false）：左侧列表暗红「待删」高亮，与 modify 列表导航对齐 */
    const handleShowDeleteInList = async (event) => {
      const d = event?.detail || {}
      const target = String(d.target || 'bug').toLowerCase()
      const rec = d.preview?.record && typeof d.preview.record === 'object' ? d.preview.record : {}
      const rawId = d.target_id ?? rec.id
      const intTargetId = parseInt(rawId, 10)
      if (!Number.isFinite(intTargetId) || intTargetId <= 0) return

      let targetPlanId = d.plan_id != null ? parseInt(String(d.plan_id), 10) : NaN
      if (!Number.isFinite(targetPlanId) || targetPlanId <= 0) {
        targetPlanId = rec.plan_id != null ? parseInt(String(rec.plan_id), 10) : NaN
      }

      const peerRaw = d.peerTargetIds
      const idSet = uniqPreserveOrderNumeric(
        Array.isArray(peerRaw) && peerRaw.length >= 2
          ? [...peerRaw.map((x) => Number(x)), intTargetId]
          : [intTargetId]
      )
      const nextPending = { ...pendingModifications.value }
      const peerList = idSet.length >= 2 ? idSet : null
      for (const pid of idSet) {
        nextPending[pid] = {
          ...(nextPending[pid] || {}),
          _target: target,
          _pendingDelete: true,
          _messageId: d.messageId ?? null,
          ...(peerList ? { _peerTargetIds: peerList } : {})
        }
      }
      pendingModifications.value = nextPending

      try {
        /** 删除迭代计划预览：侧栏计划树选中并滚到对应行（与 bug/卡片列表跳转同源思路） */
        if (target === 'plan') {
          expandPlanTreeToPlanId(intTargetId)
          selectedPlan.value = intTargetId
          await nextTick()
          for (let i = 0; i < 14; i++) {
            await nextTick()
            if (i > 0) await new Promise((r) => setTimeout(r, 120))
            const el = document.querySelector(`[data-plan-id="${intTargetId}"]`)
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' })
              break
            }
          }
          return
        }

        if (target === 'card') {
          urlContentType.value = null
          if (Number.isFinite(targetPlanId) && targetPlanId > 0) {
            selectedPlan.value = targetPlanId
            expandPlanTreeToPlanId(targetPlanId)
            await fetchCards()
            await nextTick()
            await upsertAndActivatePlanListTab({
              planId: targetPlanId,
              urlContentType: null
            })
          }
          highlightRowId.value = intTargetId
          await nextTick()
          for (let i = 0; i < 14; i++) {
            await nextTick()
            if (i > 0) await new Promise((r) => setTimeout(r, 120))
            const el = document.querySelector(`[data-item-id="${intTargetId}"]`)
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' })
              break
            }
          }
          return
        }

        if (['bug', 'badcase', 'testcase', 'test_case'].includes(target)) {
          const nt = target === 'test_case' ? 'testcase' : target
          if (nt === 'bug') urlContentType.value = 'bug'
          else if (nt === 'badcase') urlContentType.value = 'badcase'
          else if (nt === 'testcase') urlContentType.value = 'test_case'

          if (Number.isFinite(targetPlanId) && targetPlanId > 0) {
            selectedPlan.value = targetPlanId
            expandPlanTreeToPlanId(targetPlanId)
            await fetchCards()
            await nextTick()
            const cardRow = resolveCardForListNav(intTargetId, nt)
            if (cardRow?.id) {
              await upsertAndActivateTypeListTab({
                planId: targetPlanId,
                cardId: cardRow.id,
                type: nt,
                cardTitle: cardRow.title
              })
            } else {
              await upsertAndActivatePlanListTab({
                planId: targetPlanId,
                urlContentType:
                  nt === 'bug' ? 'bug' : nt === 'badcase' ? 'badcase' : 'test_case'
              })
            }
          }
          await awaitCoalescedFetchBadcasesForModifyList()
          highlightRowId.value = intTargetId
          await nextTick()
          for (let i = 0; i < 14; i++) {
            await nextTick()
            if (i > 0) await new Promise((r) => setTimeout(r, 120))
            const el = findNavListRowEl(intTargetId, nt)
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' })
              break
            }
          }
        }
      } catch (e) {
        console.error('[DELETE-PREVIEW] handleShowDeleteInList', e)
      }
    }

    /** Card 上改 status/负责人 等实际落在源表时，应打开计划下 Bug/BadCase/测试用例子列表，而非迭代卡片总表 */
    const inferWorkbenchListTypeFromCardSnapshot = (detail) => {
      const raw = String(detail?.before?.type ?? detail?.after?.type ?? '').toLowerCase()
      if (raw.includes('test') || raw === 'test_case') return 'testcase'
      if (raw.includes('bad')) return 'badcase'
      return 'bug'
    }

    const cardModifyTouchesLinkedSourceListColumns = (fieldKeys) =>
      fieldKeys.some((f) => {
        const nk = normalizeDiffFieldKey(f)
        return ['status', 'assignee', 'title', 'priority'].includes(nk)
      })

    const listTypeToUrlContentType = (lt) => {
      if (lt === 'badcase') return 'badcase'
      if (lt === 'testcase') return 'test_case'
      return 'bug'
    }

    const handleShowModifyInList = async (event) => {
          const dtop = event.detail || {}
          if (dtop.__modifyListBatch === true && Array.isArray(dtop.items) && dtop.items.length > 0) {
            const items = dtop.items
            syncApplyShowModifyListBatchFromDetails(items)
            const p0 = items[0]
            if (p0?.peerTargetIds && Array.isArray(p0.peerTargetIds) && p0.peerTargetIds.length >= 2) {
              applyPeerPendingSync(parseInt(p0.targetId, 10), p0.peerTargetIds)
            }
            await Promise.all(
              items
                .filter((it) => it.executed !== true)
                .map(async (it) => {
                  const modifyData = buildModifyDataFromShowModifyDetail(it)
                  const tid = parseInt(it.targetId, 10)
                  await persistPendingDiffReview({
                    target: it.target,
                    targetId: tid,
                    planId: it.plan_id ?? null,
                    diff: Array.isArray(it.diff) ? it.diff : [],
                    modifications: modifyData,
                    messageId: it.messageId
                  })
                })
            )
            const navItem = items.find((x) => x.executed !== true) || items[0]
            await handleShowModifyInList({
              detail: {
                ...navItem,
                __modifyListBatchItem: true,
                __pendingSyncedBatch: true
              }
            })
            await awaitCoalescedFetchBadcasesForModifyList()
            return
          }
          const skipModifyListFetch = dtop.__modifyListBatchItem === true
          const {
            targetId,
            target,
            diff,
            modifications,
            plan_id,
            executed,
            messageId,
            batchIndex,
            peerTargetIds,
            suppressAutoOpenDetail,
            natural_query: naturalQueryFromEvent
          } = event.detail
          const natural_query =
            typeof naturalQueryFromEvent === 'string' ? naturalQueryFromEvent : ''
          const intTargetId = parseInt(targetId)

          if (dtop.__pendingSyncedBatch === true) {
            const modifyDataPre = buildModifyDataFromShowModifyDetail(dtop)
            const fieldKeysPre = Object.keys(modifyDataPre)
            const hasDetailFieldsPre = fieldKeysPre.some((field) =>
              DETAIL_FIELDS.includes(normalizeDiffFieldKey(field))
            )
            const hasListFieldChangesPre = fieldKeysPre.some((field) =>
              LIST_FIELDS.includes(normalizeDiffFieldKey(field))
            )
            if (
              diff &&
              Array.isArray(diff) &&
              diff.length > 0 &&
              hasDetailFieldsPre &&
              suppressAutoOpenDetail !== true &&
              !hasListFieldChangesPre
            ) {
              if (dtop.executed !== true) {
                mergePendingModifyOverlayFromModifyData(modifyDataPre, intTargetId, {
                  target: dtop.target,
                  messageId: dtop.messageId,
                  natural_query:
                    typeof dtop.natural_query === 'string' ? dtop.natural_query : '',
                  peerTargetIds: dtop.peerTargetIds,
                  executed: dtop.executed
                })
              }
              await openMainEditor(intTargetId, target, true)
              return
            }
            if (target === 'bug') {
              urlContentType.value = 'bug'
            } else if (target === 'badcase') {
              urlContentType.value = 'badcase'
            } else if (target === 'testcase') {
              urlContentType.value = 'test_case'
            } else if (target === 'card') {
              urlContentType.value = null
            }
            let targetPlanId = plan_id ? parseInt(plan_id) : null
            if (!targetPlanId && diff) {
              const planIdDiff = diff.find((d) => (d.field ?? d.field_label) === 'plan_id')
              if (planIdDiff) {
                const newLine = planIdDiff.lines.find((l) => l.type === 'add')
                if (newLine) targetPlanId = parseInt(newLine.content)
              }
            }
            if (!targetPlanId) {
              let item =
                target === 'card'
                  ? badcases.value.find((b) => Number(b.card_id ?? b.cardId) === intTargetId)
                  : null
              if (!item) {
                item = badcases.value.find((b) => b.id == intTargetId)
              }
              if (item) {
                targetPlanId = item.plan_id
              } else {
                const oldSelectedPlan = selectedPlan.value
                selectedPlan.value = null
                await fetchBadcases(1)
                await nextTick()
                let newItem =
                  target === 'card'
                    ? badcases.value.find((b) => Number(b.card_id ?? b.cardId) === intTargetId)
                    : null
                if (!newItem) {
                  newItem = badcases.value.find((b) => b.id == intTargetId)
                }
                if (newItem) {
                  targetPlanId = newItem.plan_id
                }
                if (targetPlanId) {
                  selectedPlan.value = targetPlanId
                } else {
                  selectedPlan.value = oldSelectedPlan
                }
              }
            }
            if (!targetPlanId) {
              const fromApi = await resolvePlanIdByRecordApi(target, intTargetId)
              if (fromApi) {
                targetPlanId = fromApi
                selectedPlan.value = targetPlanId
              }
            }
            const uctForNav =
              target === 'bug'
                ? 'bug'
                : target === 'testcase'
                  ? 'test_case'
                  : target === 'badcase'
                    ? 'badcase'
                    : target === 'card'
                      ? null
                      : 'badcase'
            const navMeta = targetPlanId
              ? { planId: targetPlanId, urlContentType: uctForNav }
              : { planId: null, urlContentType: uctForNav }
            let listLoadedByTabNavigation = false
            // suppressAutoOpenDetail：避免自动 openMainEditor 与循环；但列表列 diff 必须在列表上确认，仍须激活列表 Tab
            if (suppressAutoOpenDetail === true && !hasListFieldChangesPre) {
              if (targetPlanId) selectedPlan.value = targetPlanId
              else selectedPlan.value = null
            } else {
              let openedTypeList = false
              if (targetPlanId && target === 'card' && hasListFieldChangesPre) {
                const listType = inferWorkbenchListTypeFromCardSnapshot(dtop)
                selectedPlan.value = targetPlanId
                expandPlanTreeToPlanId(targetPlanId)
                await fetchCards()
                await nextTick()
                const cardTitle =
                  (dtop.before && dtop.before.title) ||
                  (dtop.after && dtop.after.title) ||
                  ''
                await upsertAndActivateTypeListTab({
                  planId: targetPlanId,
                  cardId: intTargetId,
                  type: listType,
                  cardTitle
                })
                urlContentType.value = listTypeToUrlContentType(listType)
                openedTypeList = true
                listLoadedByTabNavigation = true
                const linked = badcases.value.find(
                  (b) => Number(b.card_id ?? b.cardId) === intTargetId
                )
                highlightRowId.value = linked ? linked.id : intTargetId
              } else if (targetPlanId && target === 'card') {
                selectedPlan.value = targetPlanId
                expandPlanTreeToPlanId(targetPlanId)
                await fetchCards()
                await nextTick()
                await upsertAndActivatePlanListTab({
                  planId: targetPlanId,
                  urlContentType: null
                })
                openedTypeList = true
                listLoadedByTabNavigation = true
                highlightRowId.value = intTargetId
              } else if (targetPlanId && ['bug', 'badcase', 'testcase'].includes(target)) {
                selectedPlan.value = targetPlanId
                expandPlanTreeToPlanId(targetPlanId)
                await fetchCards()
                await nextTick()
                const cardRow = await resolveCardRowForModifyListNav(intTargetId, target, dtop)
                if (cardRow?.id) {
                  await upsertAndActivateTypeListTab({
                    planId: targetPlanId,
                    cardId: cardRow.id,
                    type: target,
                    cardTitle: cardRow.title
                  })
                  openedTypeList = true
                  listLoadedByTabNavigation = true
                }
              }
              if (!openedTypeList) {
                await upsertAndActivatePlanListTab(navMeta)
                listLoadedByTabNavigation = true
              }
            }
            if (!skipModifyListFetch && !listLoadedByTabNavigation) {
              await awaitCoalescedFetchBadcasesForModifyList()
            }
            if (targetPlanId) {
              await nextTick()
              await new Promise((resolve) => setTimeout(resolve, 100))
              if (!expandedPlans.value.includes(targetPlanId)) {
                expandedPlans.value.push(targetPlanId)
              }
            }
            let batchFlashIds =
              Array.isArray(peerTargetIds) && peerTargetIds.length >= 2
                ? [
                    ...new Set(
                      peerTargetIds
                        .map((x) => Number(x))
                        .filter((n) => Number.isFinite(n) && n > 0)
                    )
                  ]
                : [intTargetId]
            if (
              target === 'card' &&
              hasListFieldChangesPre &&
              batchFlashIds.length === 1
            ) {
              const lk = badcases.value.find(
                (b) => Number(b.card_id ?? b.cardId) === intTargetId
              )
              if (lk) {
                highlightRowId.value = lk.id
                batchFlashIds = [lk.id]
              } else {
                highlightRowId.value = intTargetId
              }
            } else {
              highlightRowId.value = intTargetId
            }
            let anchorRow = null
            for (let i = 0; i < 12; i++) {
              await nextTick()
              await new Promise((resolve) => setTimeout(resolve, i === 0 ? 280 : 130))
              for (const bid of batchFlashIds) {
                const el = document.querySelector(`[data-bug-id="${bid}"]`)
                if (el) {
                  anchorRow = el
                  break
                }
              }
              if (anchorRow) break
            }
            if (anchorRow) {
              anchorRow.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
            requestAnimationFrame(() => {
              const els = []
              for (const bid of batchFlashIds) {
                const el = document.querySelector(`[data-bug-id="${bid}"]`)
                if (el) els.push(el)
              }
              for (const el of els) {
                el.classList.add('highlight-row')
              }
              if (els.length) {
                setTimeout(() => {
                  els.forEach((e) => e.classList.remove('highlight-row'))
                }, 3000)
              }
            })
            return
          }

          const clearPendingForIds = (ids) => {
            const uniq = [...new Set((ids || []).map((x) => Number(x)).filter((n) => !isNaN(n)))]
            if (uniq.length === 0) return
            const next = { ...pendingModifications.value }
            let changed = false
            uniq.forEach((id) => {
              if (next[id]) {
                delete next[id]
                changed = true
              }
            })
            if (changed) pendingModifications.value = next
          }

          // 已采纳/已执行时，先清理本地 pending 与会话缓存，避免再次进入 Tab 复现旧 diff
          if (executed === true) {
            clearPendingForIds([intTargetId, ...(Array.isArray(peerTargetIds) ? peerTargetIds : [])])
            try {
              const oldDiffDataStr = sessionStorage.getItem('pendingModifyDiff')
              if (oldDiffDataStr) {
                const oldDiffData = JSON.parse(oldDiffDataStr)
                if (Number(oldDiffData?.targetId) === intTargetId) {
                  sessionStorage.removeItem('pendingModifyDiff')
                }
              }
            } catch (_e) {
              sessionStorage.removeItem('pendingModifyDiff')
            }
          }

          console.log('[DEBUG-show-modify-in-list at ProjectDetail]', JSON.stringify(event.detail, null, 2))
          console.log('[MODIFY] 收到列表显示指令 (原始事件):', event.detail)
          console.log('[MODIFY] 解析后的 targetId/intTargetId:', { targetId, intTargetId })
          console.log('[MODIFY] diff 内容:', diff)
          console.log('[MODIFY] diff 类型:', typeof diff, '是否数组:', Array.isArray(diff), '长度:', diff?.length)
          console.log('[MODIFY] modifications 内容:', modifications)
          console.log('[MODIFY] modifications 类型:', typeof modifications, 'keys:', modifications ? Object.keys(modifications) : [])
              
          // 构造待修改数据结构（与 buildModifyDataFromShowModifyDetail 单一路径，含 before/after 补全）
          const modifyData = buildModifyDataFromShowModifyDetail(event.detail)
          
          console.log('[MODIFY] 构造后的 modifyData:', modifyData)
          const fieldKeys = Object.keys(modifyData)
          console.log('[MODIFY] modifyData 的 keys:', fieldKeys)

          // 是否包含详情字段（只能在详情页编辑）；assignee_id 按 assignee 视为列表字段
          const hasDetailFields = fieldKeys.some(field => {
            const normalized = normalizeDiffFieldKey(field)
            return DETAIL_FIELDS.includes(normalized)
          })

          // 是否全部都是列表字段（可只在列表展示 diff；优先级已归入详情字段）
          const allListFields = fieldKeys.length > 0 && fieldKeys.every(field => {
            const normalized = normalizeDiffFieldKey(field)
            return LIST_FIELDS.includes(normalized)
          })

          // 是否包含「列表上可见、应用行内采纳」的列（标题/状态/负责人）
          const hasListFieldChanges =
            fieldKeys.length > 0 &&
            fieldKeys.some((field) => LIST_FIELDS.includes(normalizeDiffFieldKey(field)))

          // 只要有 diff 就先缓存到 sessionStorage，后续无论跳列表还是详情都可复用
          if (diff && Array.isArray(diff) && diff.length > 0) {
            const hasPendingModification = pendingModifications.value[intTargetId]
            if (!hasPendingModification || executed) {
              sessionStorage.removeItem('pendingModifyDiff')
              const diffData = {
                targetId: intTargetId,
                target: target,
                diff: diff,
                modifications: modifyData,
                messageId: messageId,
                batchIndex: batchIndex
              }
              sessionStorage.setItem('pendingModifyDiff', JSON.stringify(diffData))
              console.log('[MODIFY] 存储 diff 数据:', diffData)
            }

            // 先合并 pending（含列表列与详情字段）：含详情时会提前 return，否则列表上看不到 title/status/assignee diff
            if (!executed) {
              mergePendingModifyOverlayFromModifyData(modifyData, intTargetId, {
                target,
                messageId,
                natural_query,
                peerTargetIds,
                executed
              })
              if (
                typeof import.meta !== 'undefined' &&
                import.meta.env?.DEV &&
                String(target).toLowerCase() === 'card'
              ) {
                const hit = badcases.value.find(
                  (b) => Number(b.card_id ?? b.cardId) === intTargetId
                )
                console.warn('[MODIFY-CARD] 已写入 pending[' + intTargetId + ']；Bug 行请用 card_id 匹配', {
                  cardId: intTargetId,
                  listBugId: hit?.id ?? null,
                  card_idOnRow: hit?.card_id ?? hit?.cardId,
                  statusPending: pendingModifications.value[intTargetId]?.status
                })
              }
            }

            // 如果都是列表字段（例如标题/状态/负责人），只跳到列表并高亮那一行，不打开编辑详情
            if (allListFields && !hasDetailFields) {
              console.log('[MODIFY] 仅列表字段修改，跳转列表并高亮行，不打开详情')
              if (executed) {
                if (pendingModifications.value[intTargetId]) {
                  const clone = { ...pendingModifications.value }
                  delete clone[intTargetId]
                  pendingModifications.value = clone
                }
              }
              // 类型切换
              if (target === 'bug') {
                urlContentType.value = 'bug'
              } else if (target === 'badcase') {
                urlContentType.value = 'badcase'
              } else if (target === 'testcase') {
                urlContentType.value = 'test_case'
              } else if (target === 'card') {
                urlContentType.value = null
              }
              highlightRowId.value = intTargetId
              // 下面已有的 plan_id 推导和 fetchBadcases 逻辑会负责切计划和刷新列表
            } else {
              // 含详情字段：若同时改了列表列，优先留在列表用行内 ✓/✗；仅详情字段时才自动打开编辑页
              if (suppressAutoOpenDetail === true) {
                console.log('[MODIFY] 自动同步链路，抑制详情自动打开，仅同步列表状态')
              } else if (!hasListFieldChanges) {
                console.log('[MODIFY] 仅详情字段修改，打开编辑详情页')
                await openMainEditor(intTargetId, target, true)
                return
              } else {
                console.log(
                  '[MODIFY] 列表列与详情同时修改：留在列表采纳标题/状态/负责人；详情字段请点 ▶ 或打开编辑页'
                )
              }
            }
          }
          
          // 切换到正确的内容类型（无 diff 时仅切列表）
          if (target === 'bug') {
            urlContentType.value = 'bug'
          } else if (target === 'badcase') {
            urlContentType.value = 'badcase'
          } else if (target === 'testcase') {
            urlContentType.value = 'test_case'
          } else if (target === 'card') {
            urlContentType.value = null
          }
          
          // 获取 plan_id（优先使用传递过来的，其次从 diff 或列表中查找）
          let targetPlanId = plan_id ? parseInt(plan_id) : null
          console.log('[MODIFY] 传入的 plan_id:', plan_id, '解析后:', targetPlanId)
          console.log('[MODIFY] 当前 badcases 列表:', badcases.value.map(b => ({ id: b.id, plan_id: b.plan_id, title: b.title })))
          
          // 方式2: 从 diff 中查找 plan_id 字段
          if (!targetPlanId && diff) {
            const planIdDiff = diff.find(d => (d.field ?? d.field_label) === 'plan_id')
            if (planIdDiff) {
              const newLine = planIdDiff.lines.find(l => l.type === 'add')
              if (newLine) {
                targetPlanId = parseInt(newLine.content)
              }
            }
          }
          
          // 方式 3: 从当前列表中查找（target=card 时 intTargetId 为 Card.id，需按 card_id 命中 Bug 行）
          if (!targetPlanId) {
            let item =
              target === 'card'
                ? badcases.value.find((b) => Number(b.card_id ?? b.cardId) === intTargetId)
                : null
            if (!item) {
              item = badcases.value.find((b) => b.id == intTargetId)
            }
            if (item) {
              targetPlanId = item.plan_id
              console.log('[MODIFY] 从列表中找到 plan_id:', targetPlanId)
            } else {
              // 列表中找不到，说明当前列表可能不是正确的计划列表
              // 先刷新全量列表（不传 plan_id）再查找
              console.log('[MODIFY] 当前列表找不到 targetId，先刷新全量列表')
              const oldSelectedPlan = selectedPlan.value
              selectedPlan.value = null  // 清除选中状态以加载全量数据
              await fetchBadcases(1)
              await nextTick()
                        
              // 重新查找
              let newItem =
                target === 'card'
                  ? badcases.value.find((b) => Number(b.card_id ?? b.cardId) === intTargetId)
                  : null
              if (!newItem) {
                newItem = badcases.value.find((b) => b.id == intTargetId)
              }
              if (newItem) {
                targetPlanId = newItem.plan_id
                console.log('[MODIFY] 从刷新后的列表中找到 plan_id:', targetPlanId)
              }
                        
              // 恢复原来的选中状态（如果找到了 plan_id 则使用新的）
              if (targetPlanId) {
                selectedPlan.value = targetPlanId
              } else {
                selectedPlan.value = oldSelectedPlan
              }
            }
          }
          if (!targetPlanId) {
            const fromApi = await resolvePlanIdByRecordApi(target, intTargetId)
            if (fromApi) {
              targetPlanId = fromApi
              selectedPlan.value = targetPlanId
            }
          }
          
          // 按文档统一走 Tab 导航：目标不在当前 Tab 时，激活已有或新建对应 Tab
          const uctForNav =
            target === 'bug'
              ? 'bug'
              : target === 'testcase'
                ? 'test_case'
                : target === 'badcase'
                  ? 'badcase'
                  : target === 'card'
                    ? null
                    : 'badcase'
          const navMeta = targetPlanId
            ? { planId: targetPlanId, urlContentType: uctForNav }
            : { planId: null, urlContentType: uctForNav }

          let listLoadedByTabNavigation = false
          if (suppressAutoOpenDetail === true && !hasListFieldChanges) {
            console.log('[MODIFY] 自动同步链路，跳过重复 Tab 激活，避免循环触发')
            // 当前链路通常已在目标 Tab；仅兜底维护 selectedPlan
            if (targetPlanId) selectedPlan.value = targetPlanId
            else selectedPlan.value = null
          } else {
            let openedTypeList = false
            if (targetPlanId && target === 'card' && hasListFieldChanges) {
              const listType = inferWorkbenchListTypeFromCardSnapshot(event.detail || {})
              selectedPlan.value = targetPlanId
              expandPlanTreeToPlanId(targetPlanId)
              await fetchCards()
              await nextTick()
              const cardTitle =
                (event.detail?.before && event.detail.before.title) ||
                (event.detail?.after && event.detail.after.title) ||
                ''
              await upsertAndActivateTypeListTab({
                planId: targetPlanId,
                cardId: intTargetId,
                type: listType,
                cardTitle
              })
              urlContentType.value = listTypeToUrlContentType(listType)
              openedTypeList = true
              listLoadedByTabNavigation = true
              const linked = badcases.value.find(
                (b) => Number(b.card_id ?? b.cardId) === intTargetId
              )
              highlightRowId.value = linked ? linked.id : intTargetId
            } else if (targetPlanId && target === 'card') {
              selectedPlan.value = targetPlanId
              expandPlanTreeToPlanId(targetPlanId)
              await fetchCards()
              await nextTick()
              await upsertAndActivatePlanListTab({
                planId: targetPlanId,
                urlContentType: null
              })
              openedTypeList = true
              listLoadedByTabNavigation = true
              highlightRowId.value = intTargetId
            } else if (targetPlanId && ['bug', 'badcase', 'testcase'].includes(target)) {
              selectedPlan.value = targetPlanId
              expandPlanTreeToPlanId(targetPlanId)
              await fetchCards()
              await nextTick()
              const cardRow = await resolveCardRowForModifyListNav(
                intTargetId,
                target,
                event.detail || {}
              )
              if (cardRow?.id) {
                await upsertAndActivateTypeListTab({
                  planId: targetPlanId,
                  cardId: cardRow.id,
                  type: target,
                  cardTitle: cardRow.title
                })
                openedTypeList = true
                listLoadedByTabNavigation = true
              }
            }
            if (!openedTypeList) {
              await upsertAndActivatePlanListTab(navMeta)
              listLoadedByTabNavigation = true
            }
          }
          
          // 仅在未通过 Tab 导航加载列表时，才补一次列表刷新
          if (!skipModifyListFetch && !listLoadedByTabNavigation) {
            await awaitCoalescedFetchBadcasesForModifyList()
          }
          
          // fetchBadcases 完成后，展开对应的计划节点
          if (targetPlanId) {
            // 等待计划树渲染完成
            await nextTick()
            await new Promise(resolve => setTimeout(resolve, 100))
            if (!expandedPlans.value.includes(targetPlanId)) {
              expandedPlans.value.push(targetPlanId)
            }
            console.log('[MODIFY] 已展开计划节点:', targetPlanId)
          }

          function setupPendingModifications () {
            // 必须与 mergePendingModifyOverlayFromModifyData 同源，否则会覆盖掉 before/after 已补全的 old（例如 status 旧值为空）
            const built = buildModifyDataFromShowModifyDetail(event.detail)
            const fieldCount = Object.keys(built).filter((k) => !k.startsWith('_')).length
            if (fieldCount === 0) return

            const prev = pendingModifications.value[intTargetId] || {}
            const merged = {
              ...prev,
              ...built,
              _target: target
            }
            if (messageId != null) merged._messageId = messageId
            merged._naturalQuery = natural_query
            if (Array.isArray(peerTargetIds) && peerTargetIds.length >= 2) {
              merged._peerTargetIds = uniqPreserveOrderNumeric(peerTargetIds)
            } else if (Array.isArray(prev._peerTargetIds) && prev._peerTargetIds.length >= 2) {
              merged._peerTargetIds = prev._peerTargetIds
            }

            pendingModifications.value = {
              ...pendingModifications.value,
              [intTargetId]: merged
            }
            console.log('[MODIFY] setupPendingModifications（buildModifyData 合并）:', pendingModifications.value)
          }
          
          // 只有未执行时才重新设置 pendingModifications
          if (!executed) {
            // 检查 sessionStorage 中是否有旧的 diff
            const oldDiffDataStr = sessionStorage.getItem('pendingModifyDiff')
            if (oldDiffDataStr) {
              try {
                const oldDiffData = JSON.parse(oldDiffDataStr)
                // 如果 sessionStorage 中的 targetId 与当前相同，但 pendingModifications 中不存在
                // 说明已经处理过了，应该清除 sessionStorage
                if (oldDiffData.targetId === intTargetId && !pendingModifications.value[intTargetId]) {
                  console.log('[MODIFY] sessionStorage 中存在但 pendingModifications 不存在，说明已处理，清除旧数据')
                  sessionStorage.removeItem('pendingModifyDiff')
                  // 不再重新设置 pendingModifications，但继续执行后续逻辑（如展开计划等）
                  console.log('[MODIFY] 跳过重新设置 pendingModifications')
                } else {
                  // 需要重新设置 pendingModifications
                  setupPendingModifications()
                }
              } catch (e) {
                console.error('[MODIFY] 解析 sessionStorage 失败:', e)
                sessionStorage.removeItem('pendingModifyDiff')
                setupPendingModifications()
              }
            } else {
              // sessionStorage 为空，需要重新设置
              setupPendingModifications()
            }

            // pending 状态落库：同记录只保留一份（由后端 upsert 统一去重/覆盖）
            await persistPendingDiffReview({
              target,
              targetId: intTargetId,
              planId: targetPlanId ?? plan_id ?? null,
              diff: Array.isArray(diff) ? diff : [],
              modifications: modifyData,
              messageId: messageId
            })
          }

          applyPeerPendingSync(intTargetId, peerTargetIds)
          
          // 滚动到目标行并高亮（Tab 切换后列表异步渲染，需短暂重试）
          let targetRow = null
          let scrollRid = intTargetId
          let scrollNavTarget = String(target || 'bug').toLowerCase()
          if (scrollNavTarget === 'card' && hasListFieldChanges) {
            const lk = badcases.value.find((b) => Number(b.card_id ?? b.cardId) === intTargetId)
            if (lk) {
              scrollRid = lk.id
              scrollNavTarget = inferWorkbenchListTypeFromCardSnapshot(event.detail || {})
            }
          }
          if (scrollNavTarget === 'test_case') scrollNavTarget = 'testcase'

          for (let i = 0; i < 12; i++) {
            await nextTick()
            await new Promise((resolve) => setTimeout(resolve, i === 0 ? 280 : 130))
            targetRow = findNavListRowEl(scrollRid, scrollNavTarget)
            if (targetRow) break
          }
          console.log('[MODIFY] 查找目标行:', scrollRid, scrollNavTarget, targetRow)
          if (targetRow) {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' })
            targetRow.classList.add('highlight-row')
            setTimeout(() => targetRow.classList.remove('highlight-row'), 3000)
          }
        }

        const handleGrepNavigate = async (event) => {
      const detail = event.detail || {}
      const mergedFromLegacyPre = detail.merged_from_legacy
      /**
       * 沙箱/聊天仍带 target=card 时：若该行实为 Bug/BadCase/测例卡片，应进类型子列表而非「纯 Card 总表」或主区编辑器。
       * getCardDetail 可补 plan_id；有 source_id 时列表高亮用源表主键。
       */
      const maybePromoteCardNavDetail = async () => {
        const t0 = String(detail.target || '').toLowerCase()
        if (t0 !== 'card' || mergedFromLegacyPre) return
        const ridRaw =
          detail.recordId != null && detail.recordId !== ''
            ? detail.recordId
            : detail.bugId != null && detail.bugId !== ''
              ? detail.bugId
              : null
        const cid =
          typeof ridRaw === 'number' ? ridRaw : parseInt(String(ridRaw), 10)
        if (!Number.isFinite(cid) || cid <= 0) return
        try {
          const cr = await getCardDetail(cid)
          const c = cr?.data?.data
          if (!cr?.data?.success || !c) return
          const st = String(c.source_type || '').toLowerCase()
          const rowType = String(c.type || '').toLowerCase()
          let kind = null
          if (st === 'bug' || rowType === 'bug') kind = 'bug'
          else if (
            st === 'badcase' ||
            st === 'bad_case' ||
            rowType === 'badcase'
          )
            kind = 'badcase'
          else if (
            st === 'testcase' ||
            st === 'test_case' ||
            rowType === 'testcase'
          )
            kind = 'testcase'
          if (!kind) return
          const sidRaw = c.source_id
          const sid =
            sidRaw != null && sidRaw !== ''
              ? typeof sidRaw === 'number'
                ? sidRaw
                : parseInt(String(sidRaw), 10)
              : NaN
          const useRowId = Number.isFinite(sid) && sid > 0 ? sid : cid
          detail.target = kind
          detail.recordId = useRowId
          detail.bugId = useRowId
          detail.card_id = detail.card_id ?? detail.cardId ?? cid
          detail.cardId = detail.cardId ?? detail.card_id ?? cid
          const pp = c.plan_id ?? c.planId
          if (
            (detail.planId == null || detail.planId === '') &&
            pp != null &&
            pp !== ''
          ) {
            const pn = typeof pp === 'number' ? pp : parseInt(String(pp), 10)
            if (Number.isFinite(pn) && pn > 0) detail.planId = pn
          }
          if (detail.planId == null || detail.planId === '') {
            let rp = await resolvePlanIdByRecordApi(kind, useRowId)
            if (!rp && cid !== useRowId)
              rp = await resolvePlanIdByRecordApi(kind, cid)
            if (!rp) rp = await resolvePlanIdByRecordApi('card', cid)
            if (rp) detail.planId = rp
          }
          logListNav('grepNavigate.cardPromotedToTypeList', {
            cardId: cid,
            kind,
            useRowId,
            planId: detail.planId
          })
        } catch (e) {
          console.warn('[GREP-NAV] card→typeList promote getCardDetail:', e)
        }
      }
      await maybePromoteCardNavDetail()

      let rawPlanId = detail.planId
      const rawRecordIds = detail.recordIds
      const recordIdsBatch =
        Array.isArray(rawRecordIds) && rawRecordIds.length > 0
          ? [...new Set(rawRecordIds.map((x) => Number(x)).filter((n) => !Number.isNaN(n) && n > 0))]
          : null
      const recordId = detail.recordId != null ? detail.recordId : detail.bugId
      const targetRaw = (detail.target || 'bug').toString().toLowerCase()
      const target = targetRaw === 'test_case' ? 'testcase' : targetRaw
      const openDetail =
        detail.openDetail === true ||
        detail.navigateMode === 'detail' ||
        detail.context === 'detail'
      const mergedFromLegacy = detail.merged_from_legacy
      const navTitle = detail.title || detail.navTitle || ''
      const legacyRowIdRaw = detail.legacy_row_id ?? detail.source_id ?? detail.bug_id
      let legacyRowId = null
      if (legacyRowIdRaw != null && legacyRowIdRaw !== '') {
        const n = Number(legacyRowIdRaw)
        if (!Number.isNaN(n) && n > 0) legacyRowId = n
      }

      let listKind = null
      if (target === 'card' && mergedFromLegacy) {
        const ml = String(mergedFromLegacy).toLowerCase()
        listKind = ml === 'test_case' ? 'testcase' : ml
      } else if (target === 'bug' || target === 'badcase' || target === 'testcase') {
        listKind = target
      }

      const listKindToUct = (kind) => {
        if (kind === 'bug') return 'bug'
        if (kind === 'badcase') return 'badcase'
        if (kind === 'testcase' || kind === 'test_case') return 'test_case'
        return null
      }

      let uctFromTarget = listKindToUct(listKind)
      if (uctFromTarget == null) {
        if (target === 'badcase') uctFromTarget = 'badcase'
        else if (target === 'testcase') uctFromTarget = 'test_case'
        else if (target === 'bug') uctFromTarget = 'bug'
        else uctFromTarget = null
      }

      console.log('[GREP-NAV] 收到导航指令:', {
        rawPlanId,
        recordId,
        recordIdsBatch,
        bugId: detail.bugId,
        target,
        mergedFromLegacy,
        listKind
      })
      logListNav('grepNavigate.detail', {
        rawPlanId,
        card_id: detail.card_id ?? detail.cardId,
        recordId,
        recordIdsBatch,
        bugId: detail.bugId,
        target,
        listKind,
        openDetail
      })

      const resolveTargetForApi = () => listKind || target

      /** 有目标记录时以详情/卡片上的计划为准，避免预览里 plan_id=1 与真实子迭代不一致导致跳进错 Tab */
      let effectivePlanIdRaw = rawPlanId
      const ridForPlan =
        recordIdsBatch?.length > 0
          ? recordIdsBatch[0]
          : recordId != null && recordId !== ''
            ? recordId
            : detail.bugId != null && detail.bugId !== ''
              ? detail.bugId
              : null
      if (ridForPlan != null && ridForPlan !== '') {
        const ttNav =
          target === 'test_case'
            ? 'testcase'
            : target === 'card'
              ? 'card'
              : resolveTargetForApi()
        const rpNav = await resolvePlanIdByRecordApi(ttNav, ridForPlan)
        if (rpNav != null) {
          effectivePlanIdRaw = rpNav
        }
      }

      let meta = null
      if (effectivePlanIdRaw != null && effectivePlanIdRaw !== '') {
        const n = typeof effectivePlanIdRaw === 'number' ? effectivePlanIdRaw : parseInt(String(effectivePlanIdRaw), 10)
        if (!Number.isNaN(n) && n > 0) {
          expandPlanTreeToPlanId(n)
          meta = { planId: n, urlContentType: uctFromTarget }
        }
      }
      if (!meta) {
        meta = { planId: null, urlContentType: uctFromTarget }
      }

      if (
        meta &&
        meta.planId == null &&
        (recordIdsBatch?.length > 0 || (recordId != null && recordId !== ''))
      ) {
        const rid = recordIdsBatch?.length ? recordIdsBatch[0] : recordId
        const resolved = await resolvePlanIdByRecordApi(resolveTargetForApi(), rid)
        if (resolved) {
          expandPlanTreeToPlanId(resolved)
          meta = { planId: resolved, urlContentType: uctFromTarget }
        }
      }

      const numericPlanId =
        meta?.planId != null && meta.planId !== 'unplanned'
          ? typeof meta.planId === 'number'
            ? meta.planId
            : parseInt(String(meta.planId), 10)
          : NaN

      /**
       * 进入「某卡片」下的类型列表（与侧栏点进 Bug 卡片一致）；依赖已拉取 cards。
       * 纯 target=card（无 merged_from_legacy）：打开该计划下的**迭代卡片总表**并高亮 Card 行，
       * 不钻进 Bug/BadCase/用例子列表；plan 缺失时用 getCardDetail 补 plan_id。
       */
      const openGrepTypeListIfPossible = async () => {
        const ridFirstEarly = recordIdsBatch?.length ? recordIdsBatch[0] : recordId
        logListNav('grepOpenTypeList.enter', {
          target,
          mergedFromLegacy,
          numericPlanId,
          listKind,
          recordId,
          recordIdsBatch,
          ridFirst: ridFirstEarly,
          detailCardId: detail.card_id ?? detail.cardId,
          openDetail
        })
        if (target === 'card' && !mergedFromLegacy) {
          const cid =
            ridFirstEarly != null && ridFirstEarly !== ''
              ? typeof ridFirstEarly === 'number'
                ? ridFirstEarly
                : parseInt(String(ridFirstEarly), 10)
              : NaN
          if (!Number.isFinite(cid) || cid <= 0) {
            logListNav('grepOpenTypeList.abort', { reason: 'pure_card_bad_rid', ridFirstEarly })
            return false
          }
          let pid =
            !Number.isNaN(numericPlanId) && numericPlanId > 0 ? numericPlanId : null
          if (!pid) {
            pid = await resolvePlanIdByRecordApi('card', cid)
          }
          if (!pid || Number.isNaN(pid) || pid <= 0) {
            logListNav('grepOpenTypeList.fallback', {
              reason: 'pure_card_no_plan_open_editor',
              cardId: cid
            })
            await openMainEditor(cid, 'card', false)
            return true
          }
          selectedPlan.value = pid
          expandPlanTreeToPlanId(pid)
          await fetchCards()
          await nextTick()
          await upsertAndActivatePlanListTab({
            planId: pid,
            urlContentType: null
          })
          highlightRowId.value = cid
          await nextTick()
          let anyEl = null
          for (let i = 0; i < 14; i++) {
            await nextTick()
            if (i > 0) await new Promise((r) => setTimeout(r, 120))
            anyEl =
              document.querySelector(`[data-item-id="${cid}"]`) ||
              document.querySelector(`[data-card-id="${cid}"]`)
            if (anyEl) break
          }
          if (anyEl) {
            anyEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
            anyEl.classList.add('highlight-flash')
            setTimeout(() => anyEl.classList.remove('highlight-flash'), 2000)
          }
          logListNav('grepOpenTypeList.ok', {
            reason: 'pure_card_plan_list',
            planId: pid,
            cardId: cid
          })
          return true
        }
        if (!numericPlanId || Number.isNaN(numericPlanId) || numericPlanId <= 0) {
          logListNav('grepOpenTypeList.abort', { reason: 'bad_numericPlanId', numericPlanId })
          return false
        }
        const ridFirst = ridFirstEarly
        if (ridFirst == null || ridFirst === '') {
          logListNav('grepOpenTypeList.abort', { reason: 'no_ridFirst' })
          return false
        }

        selectedPlan.value = numericPlanId
        expandPlanTreeToPlanId(numericPlanId)
        await fetchCards()
        await nextTick()

        let ek = listKind
        if (!ek && (target === 'bug' || target === 'badcase' || target === 'testcase')) {
          ek = target
        }
        if (!ek || ek === 'card') {
          logListNav('grepOpenTypeList.abort', { reason: 'no_listKind', ek, target })
          return false
        }

        /** grep 项已带 bug.card_id 时优先按卡片 id 命中，避免仅依赖 source_id 映射失败而退化成「仅迭代计划 Tab」 */
        const explicitCidRaw = detail.card_id ?? detail.cardId
        let cardRow = null
        let explicitEc = null
        if (explicitCidRaw != null && explicitCidRaw !== '') {
          explicitEc =
            typeof explicitCidRaw === 'number' ? explicitCidRaw : parseInt(String(explicitCidRaw), 10)
          if (!Number.isNaN(explicitEc) && explicitEc > 0 && Array.isArray(cards.value)) {
            cardRow = cards.value.find((c) => Number(c.id) === explicitEc) || null
          }
        }
        /** 卡片列表分页时当前页可能不含目标卡片 id，需详情接口补标题 */
        if (!cardRow?.id && explicitEc != null && !Number.isNaN(explicitEc) && explicitEc > 0) {
          try {
            const cr = await getCardDetail(explicitEc)
            const cdata = cr?.data?.data
            if (cr?.data?.success && cdata?.id) {
              cardRow = { id: cdata.id, title: cdata.title }
            }
          } catch (e) {
            console.warn('[GREP-NAV] getCardDetail(explicit card_id):', e)
          }
        }
        if (!cardRow) {
          cardRow = resolveCardForListNav(ridFirst, ek)
        }
        /** 首屏 cards 不含 source 映射或记录不在当前页时，用实体详情里的 card_id 解析 */
        if (!cardRow?.id) {
          cardRow = await resolveCardRowByRecordDetailApi(ridFirst, ek)
        }
        if (!cardRow?.id) {
          logListNav('grepOpenTypeList.abort', {
            reason: 'cardRow_unresolved',
            ridFirst,
            ek,
            cardsLen: Array.isArray(cards.value) ? cards.value.length : 0,
            hadExplicitCardId: !!(detail.card_id ?? detail.cardId)
          })
          return false
        }

        const cardTitleForTab =
          cardRow.title != null && String(cardRow.title).trim() !== ''
            ? String(cardRow.title).trim()
            : navTitle || `${ek}列表`

        logListNav('grepOpenTypeList.ok', {
          cardId: cardRow.id,
          cardTitleForTab,
          planId: numericPlanId,
          ek
        })

        await upsertAndActivateTypeListTab({
          planId: numericPlanId,
          cardId: cardRow.id,
          type: ek,
          cardTitle: cardTitleForTab
        })
        await nextTick()

        const flashIds = recordIdsBatch?.length
          ? recordIdsBatch
          : [legacyRowId != null ? legacyRowId : ridFirst]
        let anyEl = null
        for (let i = 0; i < 12; i++) {
          await nextTick()
          await new Promise((r) => setTimeout(r, i === 0 ? 400 : 130))
          anyEl = findNavListRowEl(flashIds[0], ek)
          if (anyEl) break
        }
        if (anyEl) {
          anyEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        for (const id of flashIds) {
          const el = findNavListRowEl(id, ek)
          if (el) {
            el.classList.add('highlight-flash')
            setTimeout(() => el.classList.remove('highlight-flash'), 2000)
          }
        }
        return true
      }

      if (!openDetail) {
        const opened = await openGrepTypeListIfPossible()
        if (opened) return
        logListNav('grepNavigate.fallbackPlanListTab', {
          metaPlanId: meta?.planId,
          uct: meta?.urlContentType,
          note: '未打开 type-list（见上一条 grepOpenTypeList.abort）'
        })
      }

      await upsertAndActivatePlanListTab(meta)

      await nextTick()

      /** 批量列表定位：同一次闪动多条，避免逐条 dispatch 造成一行行动画 */
      if (recordIdsBatch && recordIdsBatch.length > 0 && !openDetail) {
        let anyEl = null
        for (let i = 0; i < 12; i++) {
          await nextTick()
          await new Promise((r) => setTimeout(r, i === 0 ? 400 : 130))
          anyEl = findNavListRowEl(recordIdsBatch[0], target)
          if (anyEl) break
        }
        if (anyEl) {
          anyEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        for (const id of recordIdsBatch) {
          const el = findNavListRowEl(id, target)
          if (el) {
            el.classList.add('highlight-flash')
            setTimeout(() => el.classList.remove('highlight-flash'), 2000)
          }
        }
        return
      }

      if (recordId != null && recordId !== '') {
        if (openDetail) {
          console.log('[GREP-NAV] 打开卡片/实体详情（grep 导航）')
          const ridNum = Number(recordId)
          if (!Number.isNaN(ridNum) && ridNum > 0) {
            // target=card 或 recordId 即 Card.id：不必等 cards 列表已加载，openMainEditor 内会 getCardDetail 补全
            if (target === 'card') {
              await openMainEditor(ridNum, 'card', false)
              return
            }
            if (Array.isArray(cards.value)) {
              const cardRow = cards.value.find((c) => Number(c.id) === ridNum)
              if (cardRow) {
                await openMainEditor(ridNum, 'card', false)
                return
              }
            }
          }
          const fallbackType =
            target === 'testcase' || target === 'test_case'
              ? 'test_case'
              : target === 'bug'
                ? 'bug'
                : target === 'badcase'
                  ? 'badcase'
                  : target === 'card'
                    ? 'card'
                    : target
          await openMainEditor(recordId, fallbackType, false)
          return
        }
        let bugElement = null
        for (let i = 0; i < 12; i++) {
          await nextTick()
          await new Promise((r) => setTimeout(r, i === 0 ? 400 : 130))
          bugElement = findNavListRowEl(recordId, target)
          if (bugElement) break
        }
        console.log('[GREP-NAV] 查找列表行元素:', bugElement, 'recordId=', recordId)
        if (bugElement) {
          bugElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
          bugElement.classList.add('highlight-flash')
          setTimeout(() => bugElement.classList.remove('highlight-flash'), 2000)
        } else {
          console.log('[GREP-NAV] 未找到列表行，recordId:', recordId, 'target:', target)
        }
      }
    }
    
    return {
      AppSettingsPanel,
      TerminalSettingsWorkbenchPanel,
      ProjectHelpPanel,
      WorkflowNotificationsPanel,
      ProjectManage,
      projectName,
      projectId,
      planSearchText,
      showOnlyMine,
      includeSubPlans,
      expandedSections,
      selectedPlan,
      selectAll,
      selectedTasks,
      projectPlans,
      filteredPlans,
      badcases,
      activePlans,
      archivedPlans,
      filteredBadcases,
      badcaseLoading,
      totalBadcases,
      badcasePage,
      badcasePerPage,
      // Card数据
      cards,
      filteredCards,
      cardLoading,
      totalCards,
      cardPage,
      cardPerPage,
      handleQuickCreate,
      loading,
      planTestCaseCounts,
      hoveredPlan,
      contextMenu,
      contextMenuDragActive,
      planCollapsed,
      expandedPlans,
      showCreateModal,
      showProjectSettingsModal,
      showPermissionSettingsModal,
      isCreatingSubPlan,
      isCreatingSiblingPlan,
      isEditingPlan,
      editingPlanId,
      newPlan,
      availableParentPlans,
      namePlaceholder,
      isFormValid,
      currentPlan,  // 新增：当前选中的计划
      currentPlanType,  // 新增：当前计划类型
      urlContentType,  // 新增：URL参数传递的内容类型
      pendingModifications,  // 新增：待确认的修改
      expandedDetailRows,  // 新增：展开的详情行
      hasDetailFieldModifications,  // 新增：检查是否有详情字段修改
      getDetailFieldModifications,  // 新增：获取详情字段修改
      toggleDetailExpand,  // 新增：切换详情展开状态
      getFieldLabel,  // 新增：获取字段标签
      // 主区域 Editor
      showMainEditor,
      mainEditorComponent,
      mainEditorItemId,
      mainEditorEdit,
      mainEditorPlanId,
      mainEditorShowDiff,
      mainEditorCardId,
      embeddedEditorKind,
      mainEditorCacheKey,
      listPanelCacheKey,
      workbenchTabs,
      workbenchTabsForMoreMenu,
      activeWorkbenchTabId,
      workbenchMenuRef,
      aiHistoryDropdownRef,
      aiMoreDropdownRef,
      workbenchTabsStripRef,
      workbenchTabStripDraggingUI,
      onWorkbenchTabStripMouseDown,
      onWorkbenchTabStripWheel,
      onWorkbenchTabButtonClick,
      showWorkbenchTabMenu,
      toggleWorkbenchTabMenu,
      onWorkbenchMenuSelectTab,
      closeAllWorkbenchTabs,
      activateWorkbenchTab,
      closeWorkbenchTab,
      openMainEditor,
      closeMainEditor,
      toggleSection,
      selectPlan,
      selectBadcasePlan,
      createPlanForBadcase,
      associateBadcaseWithPlan,
      filterBadcasesByPlan,
      toggleSelectAll,
      toggleTaskSelection,
      handleCardPanelRefresh,
      onCardListPage,
      onCardSearchSubmit,
      onWorkbenchListPage,
      editBadcase,
      editCard,
      handleQuickUpdate,
      goToDashboard,
      showPlanActions,
      hidePlanActions,
      showContextMenu,
      closeContextMenu,
      createSubPlan,
      createSiblingPlan,
      editPlan,
      archivePlan,
      deletePlan,
      pinPlan,
      favoritePlan,
      createBaseline,
      showCreatePlanModal,
      onContextMenuDragStart,
      closeCreateModal,
      getModalTitle,
      showBaselineManagement,
      closeBaselineManagementModal,
      selectBaselinePlan,
      toggleBadcaseSelection,
      createNewBaseline,
      compareBaselines,
      selectBaseline,
      viewBaseline,
      deleteBaseline,
      toggleBaselinePlanExpansion,
      manualRefreshPlans,
      togglePlanCollapse,
      searchPlans,
      clearSearch,
      filterPlans,
      filterPlansRecursively,
      createPlan,
      createPlanAndContinue,
      fetchBadcases,
      refreshBadcases,
      getBadcaseStatusText,
      getBadcaseTypeText,
      getBadcaseBackgroundClass,
      getBadcaseIcon,
      acceptBadcase,
      rejectBadcase,
      getPlanIcon,
      formatDate,
      getPlanTypeText,
      getAssigneeDisplayText,
      confirmModify,  // 新增：确认修改
      cancelModify,   // 新增：取消修改
      confirmDelete,
      pendingDeletePlanId,
      isLastInConsecutiveGroup,  // 新增：判断是否是连续组的最后一个
      getConsecutiveGroupSize,   // 新增：获取连续组大小
      isLastInConsecutiveCardGroup,
      getConsecutiveCardGroupSize,
      isLastInConsecutiveDeleteGroup,
      getConsecutiveDeleteGroupSize,
      isLastInConsecutiveCardDeleteGroup,
      getConsecutiveCardDeleteGroupSize,
      confirmConsecutiveGroup,   // 新增：确认连续组
      cancelConsecutiveGroup,    // 新增：取消连续组
      confirmConsecutiveDeleteGroup,
      cancelConsecutiveDeleteGroup,
      confirmConsecutiveCardDeleteGroup,
      cancelConsecutiveCardDeleteGroup,
      // 新增搜索和筛选相关
      searchText,
      selectedAssignee,
      selectedStatus,
      projectMembers,
      applyFilters,
      fetchProjectMembers,
      generateBreadcrumb,
      togglePlanExpansion,
      showProjectSettings,
      showPermissionSettings,
      closeConfigModals,
      showUserDropdown,
      currentUser,
      toggleUserDropdown,
      openAppSettings,
      openHelpWorkbenchTab,
      openProjectManagementWorkbenchTab,
      handleProjectSelected,
      openNotificationsWorkbenchTab,
      closeAppSettingsWorkbenchTab,
      isSettingsWorkbenchTab,
      // 类型过滤器和处理方法
      currentTypeFilter,
      handleOpenTypeList,
      handleOpenCreate,
      handleSearchResultSelect,
      getTypeListBreadcrumb,
      getCurrentPanelComponent,
      handleTitleLoaded,
      mountEditorComponents,
      isHelpWorkbenchTab,
      isProjectManagementWorkbenchTab,
      isNotificationsWorkbenchTab,
      isTerminalSettingsWorkbenchTab,
      activeWorkbenchTab,
      embeddedTerminalWorkspaceRef,
      appSettingsInitialPane,
      t,
      showNotifications,
      logout,
      showTerminal,
      showAIAssistant,
      setLayout,
      planCollapsed,
      activeLeftPanel,
      handlePluginAction,
      leftSidebarHidden,
      leftSidebarWidth,
      startDragLeftSidebar,
      rightSidebarWidth,
      startDragRightSidebar,
      bottomPanelHeight,
      startDragBottomPanel,
      selectedBaselinePlan,
      selectedBaseline,
      selectedBadcases,
      baselines,
      availableBadcases,
      selectedBaselinePlanName,
      hasBaselines,
      showBaselineManagementModal,
      // AI助手相关
      pendingCreates,
      pendingCreatesForCurrentView,
      confirmCreate,
      cancelCreate,
      isLastInCreateCluster,
      getCreateClusterSize,
      confirmConsecutiveCreateGroup,
      cancelConsecutiveCreateGroup,
      showDropdown,
      toggleDropdown,
      closeSession,
      exportChat,
      clearMessages,
      // 会话管理
      currentSession,
      sessions,
      showHistory,
      sessionHistory,
      historyLoading,
      toggleHistory,
      fetchSessions,
      switchSession,
      createNewSession,
      closeSessionTab,
      handleTitleUpdated,
      // Terminal相关（保留工作目录用于Terminal组件）
      currentWorkingDir,
      // 全局命令历史弹框
      showGlobalCmdHistory,
      filteredGlobalCmdHistory,
      globalCmdSelected,
      globalCmdSearchText,
      globalCmdSearchInput,
      globalCmdListRef,
      onGlobalCmdKeydown,
      pickGlobalCmd,
      // Grep导航
      handleGrepNavigate,
      // 窄条导航栏事件处理
      handleReturnToPlans,
      handleOpenGlobalSearch,
      handleOpenArchive,
      handleOpenCardCreate,
    }
  }
}
</script>

<!-- 全局命令历史弹框样式（非 scoped，Teleport 到 body） -->
<style>
.etw-global-cmd-history {
  position: fixed;
  top: 60px;
  left: 0;
  width: 100%;
  z-index: 2200;
  pointer-events: all;
}
.etw-global-cmd-panel {
  background: var(--vscode-editor-widget-background, #252526);
  border: 1px solid var(--vscode-widget-border, #454545);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  max-height: 400px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  /* 居中显示，宽度适中 */
  width: 680px;
  margin: 0 auto;
}
.etw-global-cmd-search-row {
  display: flex;
  align-items: center;
  padding: 6px 10px;
  gap: 8px;
}
.etw-global-cmd-icon {
  color: var(--vscode-foreground, #cccccc);
  font-size: 14px;
  flex-shrink: 0;
  opacity: 0.7;
}
.etw-global-cmd-search {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--vscode-editor-foreground, #cccccc);
  font-family: var(--vscode-editor-font-family, 'Cascadia Code', Consolas, monospace);
  font-size: 14px;
  padding: 2px 0;
  caret-color: var(--vscode-editor-foreground, #cccccc);
}
.etw-global-cmd-search::placeholder {
  color: var(--vscode-foreground, #cccccc);
  opacity: 0.4;
}
.etw-global-cmd-divider {
  height: 1px;
  background: var(--vscode-widget-border, #454545);
}
.etw-global-cmd-list {
  overflow-y: auto;
  max-height: 500px;
}
.etw-global-cmd-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  font-family: var(--vscode-editor-font-family, 'Cascadia Code', Consolas, monospace);
  font-size: 14px;
  gap: 12px;
  min-height: 36px;
}
.etw-global-cmd-item:hover,
.etw-global-cmd-item--selected {
  background: var(--vscode-list-hoverBackground, #2a2d2e);
}
.etw-global-cmd-num {
  color: var(--vscode-descriptionForeground, #858585);
  min-width: 22px;
  font-size: 12px;
  flex-shrink: 0;
  text-align: right;
}
.etw-global-cmd-text {
  color: var(--vscode-editor-foreground, #cccccc);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.etw-global-cmd-empty {
  padding: 20px 12px;
  color: var(--vscode-foreground, #cccccc);
  opacity: 0.45;
  font-size: 13px;
  text-align: center;
}
</style>

<style scoped>
.project-detail-wrapper {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8f9fa;
}

/* 顶部导航栏 */
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
  gap: 24px;
}

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

.edit-permission {
  font-size: 12px;
  color: #666;
  padding: 4px 8px;
  background: #f8f9fa;
  border-radius: 4px;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-btn, .notification-btn, .star-btn, .help-btn, .menu-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.search-btn:hover, .notification-btn:hover, .star-btn:hover, .help-btn:hover, .menu-btn:hover {
  background: #f8f9fa;
}

.new-card-btn {
  padding: 8px 16px;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.new-card-btn:hover {
  background: #5a6fd8;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

/* 窄条导航栏和主内容容器 */
.narrow-nav-and-main {
  display: flex;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* 主容器 */
.main-container {
  display: flex;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* 左侧导航栏 */
.left-sidebar {
  display: flex;
  width: 280px; /* 默认宽度，会被动态样式覆盖 */
  background: #fff;
  border-right: 1px solid #e9ecef;
  transition: width 0.2s ease;
  position: relative;
}

.left-sidebar.collapsed {
  width: 60px;
}

/* 左侧边栏拖拽手柄 */
.drag-handle-left {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: #e1e5e9;
  cursor: ew-resize;
  transition: background-color 0.2s ease;
  z-index: 1000;
  user-select: none;
}

.drag-handle-left:hover {
  background: #a8d4ff;
}

/* 左侧边栏完全隐藏时的主内容区域样式 */
.main-content {
  flex: 1;
  overflow: hidden;
  min-width: 0; /* 防止flex子元素溢出 */
  position: relative;
  display: flex;
  flex-direction: column;
}

.main-content-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.workbench-tabbar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  gap: 0;
  padding: 4px 0 0 8px;
  background: #eceef1;
  border-bottom: 1px solid #d0d4d8;
  /* 下拉层需露出；横向溢出由 .workbench-tabs-strip 单独处理 */
  overflow: visible;
  min-height: 0;
  position: relative;
  z-index: 20;
}

.workbench-tabs-strip {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: flex-end;
  gap: 2px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
  overscroll-behavior-x: contain;
  cursor: grab;
}

.workbench-tabs-strip.dragging {
  cursor: grabbing;
  user-select: none;
}

.workbench-tabs-strip::-webkit-scrollbar {
  display: none;
  height: 0;
  width: 0;
}

.workbench-tabbar-trailing {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  align-self: stretch;
  padding: 0 6px 0 4px;
  border-left: 1px solid #d0d4d8;
  background: #eceef1;
  position: relative;
}

.workbench-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-bottom: 2px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #555;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.workbench-more-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

.workbench-tab-dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 2px);
  z-index: 1000;
  min-width: 220px;
  max-height: min(60vh, 360px);
  overflow-y: auto;
  padding: 4px 0;
  background: #fff;
  border: 1px solid #d0d4d8;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.workbench-dropdown-item {
  display: block;
  width: 100%;
  padding: 8px 14px;
  border: none;
  border-radius: 0;
  background: transparent;
  color: #333;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.workbench-dropdown-item:hover {
  background: #f0f2f5;
}

.workbench-dropdown-item.active {
  background: #e8eef8;
  color: #1a1a1a;
}

.workbench-dropdown-item.danger {
  color: #c0392b;
}

.workbench-dropdown-item.danger:hover {
  background: #fdecea;
}

.workbench-dropdown-sep {
  height: 1px;
  margin: 4px 8px;
  background: #e9ecef;
}

.workbench-tab {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  padding: 6px 10px;
  margin-bottom: -1px;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: transparent;
  color: #444;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.workbench-tab:hover {
  background: rgba(255, 255, 255, 0.5);
}

.workbench-tab.active {
  background: #fff;
  border-color: #d0d4d8;
  border-bottom-color: #fff;
  color: #1a1a1a;
  font-weight: 500;
}

.workbench-tab-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.workbench-tab-close {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 16px;
  line-height: 1;
  opacity: 0.55;
}

.workbench-tab-close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
}

/* 拖拽时禁用过渡动画，避免布局抖动 */
.main-content.dragging {
  transition: none;
}

.main-content.full-width {
  margin-left: 0;
}

/* 主内容区域的右边距通过内联样式动态设置 */
.main-content.with-right-sidebar {
  flex: 1;
  min-width: 0;
}

.nav-icons {
  width: 60px;
  background: #f8f9fa;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 8px;
  gap: 8px;
  flex-shrink: 0;
}

.nav-toggle {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s;
}

.nav-toggle:hover {
  background: #e9ecef;
}

.toggle-icon {
  font-size: 16px;
  color: #666;
  transition: transform 0.2s;
}

.nav-icon {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.nav-icon:hover {
  background: #e9ecef;
}

.nav-icon.active {
  background: #667eea;
  color: white;
}

.sidebar-content {
  flex: 1;
  padding: 12px 16px;
  overflow-y: auto;
  min-width: 0;
}


.sidebar-header {
  margin-bottom: 16px;
}


.header-top {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  min-height: 32px;
  gap: 4px;
}


.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
  flex-shrink: 0;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.action-icon-btn {
  height: 24px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  transition: background-color 0.2s;
  padding: 0 6px;
  gap: 4px;
}


.action-icon-btn .btn-text {
  font-size: 12px;
  color: #666;
}


.action-icon-btn:hover {
  background: #f8f9fa;
}


.search-section {
  display: flex;
  gap: 8px;
  align-items: center;
}

.plan-search-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
}

.plan-search-input:focus {
  border-color: #667eea;
}

.search-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #e9ecef;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.search-btn:hover {
  border-color: #667eea;
  background: #f8f9fa;
}

.search-icon {
  font-size: 14px;
  color: #666;
}

.clear-search-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #e9ecef;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  margin-left: -8px; /* 让清除按钮更靠近输入框 */
}

.clear-search-btn:hover {
  border-color: #dc3545;
  background: #f8f9fa;
}

.clear-icon {
  font-size: 12px;
  color: #666;
}

/* 置顶图标样式 */
.pin-indicator {
  font-size: 12px;
  margin-left: 4px;
  color: #ff6b6b;
  opacity: 0.8;
}

/* 默认迭代徽章样式 */
.default-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background: #e3f2fd;
  color: #1976d2;
  margin-left: 4px;
}

/* 默认迭代项样式 */
.plan-item.default-plan {
  background: #f8f9fa;
}

/* 无活跃迭代提示 */
.empty-state {
  padding: 20px 12px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.empty-state .empty-text {
  display: block;
  line-height: 1.5;
}

.clear-search-btn:hover .clear-icon {
  color: #dc3545;
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
  width: 480px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #666;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background: #f8f9fa;
}

.modal-body {
  padding: 20px 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #333;
}

.form-label.required::after {
  content: ' *';
  color: #dc3545;
}

.form-input, .form-select, .form-textarea {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.form-input:focus, .form-select:focus, .form-textarea:focus {
  border-color: #667eea;
}

.textarea-wrapper {
  position: relative;
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
  padding-bottom: 24px;
}

.textarea-char-count {
  position: absolute;
  bottom: 6px;
  right: 12px;
  font-size: 11px;
  color: #999;
  pointer-events: none;
  background: white;
  padding: 2px 4px;
  border-radius: 2px;
}

.date-row {
  display: flex;
  gap: 16px;
}

.date-field {
  flex: 1;
}

.count-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.count-label {
  margin-bottom: 0;
  white-space: nowrap;
  flex-shrink: 0;
}

.cycle-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cycle-label {
  margin-bottom: 0;
  white-space: nowrap;
  flex-shrink: 0;
}

.cycle-row .form-select {
  flex: 1;
}

.parent-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.parent-label {
  margin-bottom: 0;
  white-space: nowrap;
  flex-shrink: 0;
}

.parent-row .form-select {
  flex: 1;
}

.date-input-wrapper, .number-input-wrapper, .name-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}

.calendar-icon {
  font-size: 16px;
  color: #666;
  pointer-events: none;
}

.helper-text {
  font-size: 11px;
  color: #666;
  white-space: nowrap;
}

.form-hint-inline {
  margin: 6px 0 0;
  font-size: 12px;
  color: #666;
  line-height: 1.4;
}

.count-input {
  width: 80px;
  flex-shrink: 0;
}

.number-input-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.char-count {
  font-size: 11px;
  color: #666;
  white-space: nowrap;
}

.name-input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.name-input {
  flex: 1;
}

.help-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #666;
  transition: background-color 0.2s;
}

.help-btn:hover {
  background: #f8f9fa;
}

.toggle-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  font-size: 13px;
  color: #333;
}

.toggle-switch {
  width: 40px;
  height: 20px;
  appearance: none;
  background: #e9ecef;
  border-radius: 10px;
  position: relative;
  cursor: pointer;
  transition: background-color 0.2s;
}

.toggle-switch:checked {
  background: #667eea;
}

.toggle-switch::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-switch:checked::before {
  transform: translateX(20px);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e9ecef;
  background: #f8f9fa;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-secondary {
  background: #e9ecef;
  color: #333;
}

.btn-secondary:hover {
  background: #dee2e6;
}

.btn-primary {
  background: #667eea;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #5a6fd8;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* 简化版新建计划弹框样式 */
.plan-modal-content {
  background: white;
  border-radius: 8px;
  width: 676px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.plan-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
}

.plan-modal-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.plan-modal-close {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  display: flex;
  align-items: center;
  justify-content: center;
}

.plan-modal-close:hover {
  background: #f5f5f5;
}

.plan-modal-body {
  padding: 20px;
}

.plan-form-row {
  margin-bottom: 16px;
}

.plan-form-row:last-child {
  margin-bottom: 0;
}

.plan-form-row-2col {
  display: flex;
  gap: 16px;
}

.plan-form-row-2col .plan-form-item {
  flex: 1;
  margin-bottom: 0;
}

.plan-form-item {
  margin-bottom: 16px;
}

.plan-form-item:last-child {
  margin-bottom: 0;
}

.plan-form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #333;
}

.plan-form-label.required::after {
  content: ' *';
  color: #ff4d4f;
}

.plan-form-input,
.plan-form-select,
.plan-form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.plan-form-input:focus,
.plan-form-select:focus,
.plan-form-textarea:focus {
  border-color: #1890ff;
}

.plan-form-textarea {
  resize: vertical;
  min-height: 104px;
}

.plan-modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid #e8e8e8;
  background: #fafafa;
  border-radius: 0 0 8px 8px;
}

.plan-modal-footer-right {
  display: flex;
  gap: 12px;
}

.plan-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.plan-btn-default {
  background: #fff;
  color: #1890ff;
  border: 1px solid #1890ff;
}

.plan-btn-default:hover:not(:disabled) {
  background: #e6f7ff;
}

.plan-btn-default:disabled {
  color: #d9d9d9;
  border-color: #d9d9d9;
  cursor: not-allowed;
}

.plan-btn-cancel {
  background: #f5f5f5;
  color: #333;
}

.plan-btn-cancel:hover {
  background: #e8e8e8;
}

.plan-btn-primary {
  background: #1890ff;
  color: white;
}

.plan-btn-primary:hover:not(:disabled) {
  background: #40a9ff;
}

.plan-btn-primary:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

.plan-tree {
  margin-top: 16px;
}


.plan-item {
  margin-bottom: 4px;
  border-radius: 4px;
  transition: all 0.2s;
  position: relative;
}


.plan-item:hover {
  background: #f8f9fa;
}


.plan-item.active {
  background: #e3f2fd;
  color: #1976d2;
}


.badcase-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.badcase-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.badcase-item:hover .badcase-actions {
  opacity: 1;
}

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  transition: all 0.3s ease;
}

.action-btn.accept {
  background: #10b981;
  color: white;
}

.action-btn.accept:hover {
  background: #059669;
  transform: scale(1.1);
}

.action-btn.reject {
  background: #ef4444;
  color: white;
}

.action-btn.reject:hover {
  background: #dc2626;
  transform: scale(1.1);
}

/* AI生成的BadCase样式 */
.badcase-item.ai-generated {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: 1px solid #5a67d8;
}

.badcase-item.ai-generated:hover {
  background: linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%);
}

/* 手动创建的BadCase样式 */
.badcase-item.manual {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
  border: 1px solid #ec4899;
}

.badcase-item.manual:hover {
  background: linear-gradient(135deg, #ec4899 0%, #db2777 100%);
}

/* 默认BadCase样式 */
.badcase-item.default {
  background: #f8fafc;
  color: #374151;
  border: 1px solid #e5e7eb;
}

.badcase-item.default:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

/* 状态相关样式 */
.badcase-item.status-new {
  border-left: 4px solid #3b82f6;
}

.badcase-item.status-pending {
  border-left: 4px solid #f59e0b;
}

.badcase-item.status-resolved {
  border-left: 4px solid #10b981;
}

.badcase-item.status-closed {
  border-left: 4px solid #6b7280;
}

/* 优先级相关样式 */
.badcase-item.priority-high {
  box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2);
}

.badcase-item.priority-medium {
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
}

.badcase-item.priority-low {
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
}

/* 已接受的BadCase样式 */
.badcase-item.ai-generated[data-ai-status="accepted"] {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border-color: #047857;
}

/* 已拒绝的BadCase样式 */
.badcase-item.ai-generated[data-ai-status="rejected"] {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  border-color: #b91c1c;
  opacity: 0.7;
}

.plan-item.parent-plan {
  border-left: 3px solid #2196f3;
}

.plan-item.child-plan {
  border-left: 3px solid #ff9800;
}

.plan-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.plan-name {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plan-date {
  font-size: 11px;
  color: #999;
  margin-left: 8px;
  flex-shrink: 0;
}

.plan-content {
  width: 100%;
}

.plan-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
}

.sub-plans {
  margin-left: 20px;
  border-left: 1px solid #e0e0e0;
}

.sub-plan-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s;
  margin-left: 12px;
}

.sub-plan-item:hover {
  background: #f5f5f5;
}

.sub-plan-item.active {
  background: #fff3e0;
  color: #f57c00;
}

.sub-plan-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
}

.sub-plan-name {
  flex: 1;
  font-size: 13px;
}

.sub-plan-count {
  padding: 2px 6px;
  background: #f0f0f0;
  border-radius: 8px;
  font-size: 10px;
  color: #666;
}

.expand-arrow {
  font-size: 8px;
  color: #888;
  transition: transform 0.15s;
  cursor: pointer;
  width: 6px;
  min-width: 6px;
  text-align: center;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 2px;
}

.expand-arrow:hover {
  color: #333;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 8px;
  min-width: 8px;
  flex-shrink: 0;
}

.plan-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-weight: 500;
}

.section-header:hover {
  background: #f8f9fa;
}

.section-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.section-title {
  flex: 1;
  font-size: 14px;
}

.section-content {
  margin-left: 20px;
  margin-top: 8px;
}

.subsection-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.subsection-title {
  flex: 1;
}

.plan-list {
  margin-left: 0;
}

.loading-state, .empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: #666;
  font-size: 14px;
}

.loading-row, .empty-row {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #666;
  font-size: 14px;
  border-bottom: 1px solid #f0f0f0;
}

.loading-text, .empty-text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-text, .empty-text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-text::before {
  content: '';
  width: 16px;
  height: 16px;
  border: 2px solid #e9ecef;
  border-top: 2px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.plan-info {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  margin-right: 8px;
}

.count-badge {
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  min-width: 16px;
  text-align: center;
}

.count-badge.badcase {
  background: #e3f2fd;
  color: #1976d2;
}

.badcase-title {
  font-weight: 500;
  color: #1976d2;
  cursor: pointer;
  position: relative;
  z-index: 10;
  user-select: none;
  padding: 2px 8px;
  border-radius: 12px;
  background: #e3f2fd;
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  transition: all 0.2s ease;
}

.badcase-title:hover {
  background: #bbdefb;
  color: #1565c0;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.count-badge.bug {
  background: #fff3cd;
  color: #856404;
}

.count-badge.testcase {
  background: #e8f5e9;
  color: #2e7d32;
}

/* 计划类型标签 */
.plan-type-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  background: #e3f2fd;
  color: #1976d2;
  margin-left: 4px;
}

.sub-plan-list {
  margin-left: 8px;
}

.sub-plan {
  padding: 2px 8px;
  font-size: 13px;
}

.sub-plan .plan-icon {
  font-size: 13px;
}

.sub-plan .plan-name {
  font-size: 13px;
}

.sub-plan-list.level-2 {
  margin-left: 8px;
}

.sub-plan.level-2 {
  padding: 2px 8px;
  font-size: 12px;
}

.sub-plan.level-2 .plan-icon {
  font-size: 12px;
}

.sub-plan.level-2 .plan-name {
  font-size: 12px;
}

/* 计划操作按钮 */
.plan-actions {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
}

.action-btn:hover {
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

/* 上下文菜单：紧凑设计 */
.context-menu {
  position: fixed;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  max-height: min(60vh, 360px);
  min-width: 150px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.context-menu.is-dragging {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
}

.context-menu-drag-handle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 11px;
  color: #888;
  background: #fafafa;
  border-bottom: 1px solid #eee;
  cursor: grab;
  user-select: none;
}

.context-menu.is-dragging .context-menu-drag-handle {
  cursor: grabbing;
}

.drag-grip {
  letter-spacing: -2px;
  opacity: 0.5;
}

.drag-label {
  font-weight: 400;
}

.context-menu-body {
  flex: 1;
  min-height: 0;
  max-height: min(50vh, 300px);
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 12px;
  color: #444;
  transition: background-color 0.15s;
}

.menu-item:hover {
  background: #f0f5ff;
}

.menu-icon {
  font-size: 12px;
  width: 14px;
  text-align: center;
}

.menu-separator {
  height: 1px;
  background: #eee;
  margin: 2px 0;
}



/* 主内容区域 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 0;
  box-shadow: none;
  overflow: hidden;
}

.content-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
}

.content-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.completion-rate {
  font-size: 14px;
  color: #666;
  background: #f8f9fa;
  padding: 4px 8px;
  border-radius: 4px;
}

.content-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #e9ecef;
  background: #f8f9fa;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.view-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #333;
}

.settings-icon {
  font-size: 12px;
  color: #999;
}

.quick-create-btn {
  padding: 6px 12px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.quick-create-btn:hover {
  background: #357abd;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 搜索输入框样式 */
.search-input-container {
  position: relative;
  display: flex;
  align-items: center;
}

.search-input {
  width: 200px;
  padding: 6px 12px 6px 32px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.search-input-container .search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #999;
  pointer-events: none;
}

/* 筛选下拉框样式 */
.filter-dropdown {
  position: relative;
}

.filter-select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  color: #333;
  cursor: pointer;
  min-width: 120px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.filter-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.filter-select:hover {
  border-color: #bbb;
}

.filter-section {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
}

.filter-icon {
  font-size: 12px;
}

.filter-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
}

.filter-checkbox input[type="checkbox"] {
  margin: 0;
}

.refresh-btn, .view-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.refresh-btn:hover, .view-btn:hover {
  background: #e9ecef;
}

.total-count {
  font-size: 13px;
  color: #666;
}

/* 任务表格 */
.task-table {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-header {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr 120px;
  gap: 16px;
  padding: 12px 24px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  font-size: 13px;
  font-weight: 600;
  color: #666;
}

.table-body {
  flex: 1;
  overflow-y: auto;
}

.table-row {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr 120px;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  align-items: center;
  cursor: pointer;
  transition: background-color 0.2s;
}

.table-row:hover {
  background: #f8f9fa;
}

.table-row.selected {
  background: #e3f2fd;
}

.table-row.pending-modify {
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
}

/* Bug导航高亮动画 */
.table-row.highlight-flash {
  animation: highlight-pulse 2s ease-in-out;
}

@keyframes highlight-pulse {
  0%, 100% {
    background: #f8f9fa;
  }
  25% {
    background: #fff3cd;
    box-shadow: 0 0 10px rgba(255, 193, 7, 0.5);
  }
  50% {
    background: #ffc107;
  }
  75% {
    background: #fff3cd;
    box-shadow: 0 0 10px rgba(255, 193, 7, 0.5);
  }
}

.row-checkbox, .header-checkbox {
  display: flex;
  align-items: center;
}

.row-title, .header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-title {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.expand-icon {
  font-size: 10px;
  color: #999;
}

.row-type, .header-type {
  display: flex;
  align-items: center;
}

.type-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.type-badge.bug {
  background: #fff3cd;
  color: #856404;
}

.type-badge.test_request {
  background: #d1ecf1;
  color: #0c5460;
}

.type-badge.badcase {
  background: #e3f2fd;
  color: #1976d2;
}

.row-status, .header-status {
  display: flex;
  align-items: center;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

/* 所有状态徽章使用统一的样式 */
.status-badge {
  background: #d4edda;
  color: #155724;
}

/* 为特定状态添加不同的样式（如果需要的话） */
.status-badge.test_passed {
  background: #d4edda;
  color: #155724;
}

.status-badge.close {
  background: #d4edda;
  color: #155724;
}

.status-badge.new {
  background: #d4edda;
  color: #155724;
}

.status-badge.hold {
  background: #d4edda;
  color: #155724;
}

.status-badge.not_a_bug {
  background: #d4edda;
  color: #155724;
}

/* 添加其他可能的状态样式 */
.status-badge.pending {
  background: #d4edda;
  color: #155724;
}

.status-badge.resolved {
  background: #d4edda;
  color: #155724;
}

.status-badge.reopen {
  background: #d4edda;
  color: #155724;
}

/* 字段对比样式 - 类似Qoder/Cursor的diff效果 */
.field-diff-inline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.old-value-inline {
  background: #fef2f2;
  color: #991b1b;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  text-decoration: line-through;
  border: 1px solid #fecaca;
}

.new-value-inline {
  background: #f0fdf4;
  color: #166534;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid #bbf7d0;
}

/* 高亮行样式 */
.highlight-row {
  animation: highlight-pulse 2s ease-out;
  background-color: #fef3c7 !important;
}

@keyframes highlight-pulse {
  0% {
    background-color: #fbbf24;
  }
  100% {
    background-color: transparent;
  }
}

/* 待修改行样式 */
.pending-modify {
  background-color: #fffbeb !important;
  border-left: 3px solid #f59e0b;
}

/* 行内操作按钮 */
.row-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn-icon-approve,
.btn-icon-reject {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
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

/* 连续组批量操作数量标签 */
.batch-count {
  font-size: 12px;
  font-weight: 600;
  color: #f59e0b;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: 10px;
  margin-right: 8px;
}

/* 详情字段展开按钮 */
.btn-expand-detail {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid #d1d5db;
  background: #f3f4f6;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  margin-right: 8px;
  transition: all 0.2s;
}

.btn-expand-detail:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

/* 详情字段修改折叠面板 */
.detail-diff-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  margin: 4px 16px 8px 16px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.detail-diff-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
}

.detail-diff-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.detail-diff-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-field-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.detail-field-label {
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
  min-width: 80px;
  flex-shrink: 0;
}

.detail-field-diff {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.detail-field-diff .old-value {
  font-size: 13px;
  color: #ef4444;
  text-decoration: line-through;
  background: #fef2f2;
  padding: 2px 6px;
  border-radius: 4px;
}

.detail-field-diff .arrow {
  color: #9ca3af;
  font-size: 12px;
}

.detail-field-diff .new-value {
  font-size: 13px;
  color: #10b981;
  background: #ecfdf5;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.status-badge.not_badcase {
  background: #d4edda;
  color: #155724;
}

.row-assignee, .header-assignee {
  display: flex;
  align-items: center;
}

.assignee-text {
  font-size: 13px;
  color: #333;
}

.row-date, .header-date {
  display: flex;
  align-items: center;
}

.date-text {
  font-size: 13px;
  color: #666;
}





/* 布局按钮组样式 */
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

.top-right .menu-icon {
  font-size: 14px;
  opacity: 0.8;
}

.top-right .menu-text {
  font-size: 13px;
  color: #333;
  font-weight: 400;
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

.baseline-modal {
  max-width: 1200px;
  width: 90%;
  height: 80vh;
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

/* 父计划信息提示样式 */
.parent-plan-info {
  margin-top: 8px;
  padding: 8px 12px;
  background: #e3f2fd;
  border-radius: 4px;
  border-left: 3px solid #2196f3;
}

.info-text {
  font-size: 12px;
  color: #1976d2;
  font-weight: 500;
}

/* 基线管理样式 */
.baseline-layout {
  display: flex;
  height: 100%;
  gap: 20px;
}

.baseline-left-panel {
  width: 250px;
  border-right: 1px solid #e1e5e9;
  display: flex;
  flex-direction: column;
}

.baseline-right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel-header {
  padding: 16px 0;
  border-bottom: 1px solid #e1e5e9;
  margin-bottom: 16px;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.baseline-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.baseline-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.baseline-btn:first-child {
  background: #007bff;
  color: white;
}

.baseline-btn:first-child:hover {
  background: #0056b3;
}

.baseline-btn:last-child {
  background: #6c757d;
  color: white;
}

.baseline-btn:last-child:hover {
  background: #545b62;
}

.baseline-btn:disabled {
  background: #e9ecef;
  color: #6c757d;
  cursor: not-allowed;
}

.plan-list {
  flex: 1;
  overflow-y: auto;
}

.plan-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  cursor: pointer;
  border-radius: 3px;
  transition: background-color 0.15s;
  min-height: 22px;
}

.plan-item:hover {
  background: #f0f0f0;
}

.plan-item.active {
  background: #e3f2fd;
  color: #1976d2;
}

.plan-icon {
  font-size: 16px;
}

.plan-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
}

.plan-count {
  background: #e9ecef;
  color: #6c757d;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badcase-section, .baseline-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.count {
  color: #6c757d;
  font-weight: 400;
}

.badcase-list, .baseline-list {
  max-height: 200px;
  overflow-y: auto;
}

.badcase-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.badcase-item:hover {
  border-color: #007bff;
}

.badcase-item.selected {
  border-color: #007bff;
  background: #e3f2fd;
}

.badcase-checkbox {
  flex-shrink: 0;
}

.badcase-info {
  flex: 1;
}

.badcase-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}

.badcase-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.assignee {
  font-size: 12px;
  color: #6c757d;
}

.baseline-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  background: white;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.baseline-item:hover {
  border-color: #007bff;
}

.baseline-item.active {
  border-color: #007bff;
  background: #e3f2fd;
}

.baseline-info {
  flex: 1;
}

.baseline-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.baseline-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #6c757d;
}

.version {
  background: #e3f2fd;
  color: #1976d2;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.baseline-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 8px;
  border: 1px solid #e1e5e9;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #f8f9fa;
}

.action-btn.delete {
  border-color: #dc3545;
  color: #dc3545;
}

.action-btn.delete:hover {
  background: #dc3545;
  color: white;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.6;
}

.empty-text {
  font-size: 14px;
}

/* 用户下拉菜单样式 */
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

/* 底部Terminal和Output面板样式 */
.bottom-panel {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  /* height: 由内联样式动态设置 */
  min-height: 150px;
  max-height: 800px;
  background: #1e1e1e;
  border-top: 1px solid #333;
  z-index: 100;
  display: flex;
  flex-direction: column;
}

/* 横向拖拽手柄（用于底部面板） */
.drag-handle-horizontal {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 6px;
  background: transparent;
  cursor: ns-resize;
  z-index: 10;
  transition: background-color 0.2s;
}

.drag-handle-horizontal:hover {
  background: linear-gradient(to bottom, 
    transparent 0%, 
    rgba(96, 165, 250, 0.3) 50%, 
    transparent 100%);
}

.drag-handle-horizontal::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 40px;
  height: 2px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.drag-handle-horizontal:hover::before {
  background: rgba(96, 165, 250, 0.6);
}

/* 底部面板位置通过内联样式动态设置 */

.panel-tabs {
  display: flex;
  background: #2d2d2d;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
  margin-top: 6px; /* 为拖拽手柄留出空间 */
}

.tab-item {
  padding: 8px 16px;
  color: #ccc;
  cursor: pointer;
  border-right: 1px solid #333;
  transition: all 0.2s ease;
}

.tab-item.active {
  background: #1e1e1e;
  color: #fff;
}

.tab-item:hover {
  background: #3d3d3d;
  color: #fff;
}

.panel-content {
  /* 终端区需要参与父级 flex 收缩；auto 滚动会破坏 xterm 的 height:100% / absolute 填满链 */
  flex: 1 1 0;
  min-height: 0;
  /* 允许终端顶栏下拉菜单向上溢出显示（例如 +⌄ 菜单） */
  overflow: visible;
  padding: 0;
  display: flex;
  flex-direction: column;
  /* 与嵌入式终端 #1e1e1e 一致，避免子树未铺满时出现纯黑缝 */
  background-color: #1e1e1e;
}

.terminal-content {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.terminal-line {
  color: #00ff00;
  margin-bottom: 4px;
}

/* 右侧 AI：全高覆盖右侧（与 Cursor 一致）；顶栏在 ProjectWorkspaceShell 中 z-index 更高，故无白条且头像可点 */
.right-sidebar {
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  height: 100vh;
  background: #252526;
  border-left: 1px solid #3e3e3e;
  box-shadow: -2px 0 10px rgba(0, 0, 0, 0.5);
  z-index: 2000; /* 低于 .top-bar 的 2100 */
  display: flex;
  flex-direction: column;
  padding: 0;
  margin: 0;
}

/* 编辑覆盖层已下线：相关样式已移除 */

.ai-assistant-panel {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  padding: 0;
  margin: 0;
}

/* AI面板头部 */
.ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  background: #2d2d2d;
  border-bottom: 1px solid #3e3e3e;
  border-top: none;
  flex-shrink: 0;
  min-height: 48px;
  min-width: 0;
  margin: 0;
}

/* 确保聊天面板容器占据剩余空间，紧贴头部 */
.ai-assistant-panel .chat-panel-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  border: none;
  margin-top: 0;
  padding-top: 0;
}

.ai-panel-tabs {
  display: flex;
  gap: 2px;
  overflow-x: hidden;
  overflow-y: visible;
  flex: 1;
  min-width: 0;
  justify-content: flex-start;
  align-items: center;
}

/* 不占满整行：过长标题省略，完整文案见 .ai-tab-title 的 title 悬停 */
.ai-tab {
  position: relative;
  padding: 6px 10px 6px 12px;
  background: #1e1e1e;
  border-radius: 4px 4px 0 0;
  font-size: 12px;
  color: #888;
  cursor: pointer;
  transition: all 0.2s;
  box-sizing: border-box;
  min-width: 0;
  max-width: min(260px, calc(100% - 8px));
  flex: 0 1 auto;
  width: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.ai-tab-title {
  display: block;
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}

.ai-tab.active {
  background: #007acc;
  color: #fff;
}

.ai-tab:hover {
  background: #2a2a2a;
}

.ai-tab.active:hover {
  background: #005a9e;
}

.tab-close {
  background: none;
  border: none;
  color: inherit;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
  margin-left: 8px;
  border-radius: 2px;
  opacity: 0.7;
  transition: all 0.2s;
}

.tab-close:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.2);
}

/* AI面板操作按钮 */
.ai-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.ai-action-btn {
  background: none;
  border: none;
  font-size: 16px;
  color: #888;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
}

.ai-action-btn:hover {
  background: #37373d;
  color: #d4d4d4;
}

.ai-action-btn:active {
  background: #2a2d2e;
}

/* 下拉菜单样式 */
.dropdown {
  position: relative;
  display: inline-block;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  background: #2d2d2d;
  border: 1px solid #3e3e3e;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  z-index: 1000;
  min-width: 120px;
  opacity: 0;
  visibility: hidden;
  transform: translateY(-10px);
  transition: all 0.2s ease;
}

.dropdown-menu.show {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

.history-menu {
  width: 240px;
  max-height: 400px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  flex-direction: column;
  padding: 10px 16px;
  border-bottom: 1px solid #3e3e3e;
  cursor: pointer;
  transition: background-color 0.2s;
}

.history-item:last-child {
  border-bottom: none;
}

.history-item:hover {
  background-color: #37373d;
}

.history-item.active {
  background-color: #0e639c;
  color: #fff;
}

.history-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-time {
  font-size: 11px;
  color: #888;
}

.history-item.active .history-time {
  color: #add6ff;
}

.dropdown-item.loading, .dropdown-item.empty {
  padding: 16px;
  text-align: center;
  color: #888;
  font-style: italic;
}

.chat-empty-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  font-size: 14px;
}

.dropdown-item {
  display: block;
  padding: 8px 16px;
  color: #d4d4d4;
  text-decoration: none;
  font-size: 13px;
  transition: background-color 0.2s;
}

.dropdown-item:hover {
  background-color: #37373d;
  color: #fff;
}

.dropdown-item:first-child {
  border-top-left-radius: 6px;
  border-top-right-radius: 6px;
}

.dropdown-item:last-child {
  border-bottom-left-radius: 6px;
  border-bottom-right-radius: 6px;
}


/* 终端工具栏 */
.terminal-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #2d2d2d;
  border-bottom: 1px solid #333;
  padding: 8px 16px;
  font-size: 12px;
}

.terminal-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.working-dir {
  color: #4fc3f7;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.terminal-status {
  color: #81c784;
  font-weight: 500;
}

.terminal-status.executing {
  color: #ffb74d;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.terminal-actions {
  display: flex;
  gap: 8px;
}

.terminal-btn {
  background: none;
  border: none;
  color: #ccc;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s;
}

.terminal-btn:hover {
  background: #404040;
}

/* 终端输出区域 */
.terminal-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 16px;
  background: #1e1e1e;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.4;
}

.terminal-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 2px;
  word-wrap: break-word;
}

.line-timestamp {
  color: #666;
  font-size: 11px;
  flex-shrink: 0;
  min-width: 60px;
}

.line-content {
  flex: 1;
  white-space: pre-wrap;
}

.terminal-command {
  color: #4fc3f7;
}

.terminal-output {
  color: #d4d4d4;
}

.terminal-error {
  color: #f48fb1;
}

.terminal-system {
  color: #81c784;
  font-style: italic;
}

/* 自动补全下拉框 */
.autocomplete-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  background: #2d2d2d;
  border: 1px solid #333;
  border-bottom: none;
  max-height: 200px;
  overflow-y: auto;
  z-index: 1000;
}

.autocomplete-item {
  padding: 8px 16px;
  cursor: pointer;
  color: #d4d4d4;
  border-bottom: 1px solid #333;
}

.autocomplete-item:hover,
.autocomplete-item.selected {
  background: #404040;
  color: #4fc3f7;
}

/* Terminal命令输入栏 */
.terminal-input-bar {
  background: #1e1e1e;
  border-top: 1px solid #333;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}

.terminal-input-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.terminal-prompt {
  color: #4ec9b0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  font-weight: bold;
}

.terminal-command-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #d4d4d4;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  outline: none;
  padding: 4px 8px;
}

.terminal-command-input::placeholder {
  color: #6c757d;
}

.terminal-input-actions {
  display: flex;
  gap: 8px;
}

.terminal-run-btn {
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}

.terminal-run-btn:hover:not(:disabled) {
  background: #0056b3;
}

.terminal-run-btn:disabled {
  background: #666;
  cursor: not-allowed;
}

.terminal-stop-btn {
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}

.terminal-stop-btn:hover {
  background: #c82333;
}

/* 终端设置面板 */
.terminal-settings {
  background: #2d2d2d;
  border-top: 1px solid #333;
  padding: 16px;
  font-size: 12px;
}

.settings-section {
  margin-bottom: 16px;
}

.settings-section label {
  display: block;
  color: #ccc;
  margin-bottom: 4px;
  font-weight: 500;
}

.settings-input {
  width: 100%;
  background: #1e1e1e;
  border: 1px solid #333;
  color: #d4d4d4;
  padding: 6px 8px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 11px;
}

.settings-input:focus {
  outline: none;
  border-color: #007bff;
}

.history-count {
  color: #81c784;
  margin-right: 8px;
}

.clear-history-btn {
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 11px;
}

.clear-history-btn:hover {
  background: #c82333;
}

.shortcuts-list {
  color: #ccc;
  line-height: 1.6;
}

.shortcuts-list div {
  margin-bottom: 2px;
}

.terminal-execute-btn {
  background: #007bff;
  color: white;
  border: none;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.terminal-execute-btn:hover {
  background: #0056b3;
}

.terminal-close-btn {
  background: none;
  border: none;
  color: #6c757d;
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  border-radius: 2px;
  transition: all 0.2s;
}

.terminal-close-btn:hover {
  color: #d4d4d4;
  background: rgba(255, 255, 255, 0.1);
}

/* 对话区域 */
.ai-chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 聊天面板容器样式 */
.chat-panel-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #1e1e1e;
  height: 100%;
  min-height: 0;
  max-height: 100%;
  position: relative;
  z-index: 1;
  margin: 0;
  padding: 0;
}

/* 确保 SimpleChatPanel 的输入框可见 */
.chat-panel-container :deep(.simple-chat-panel) {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 2;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

/* 确保消息容器不添加额外的 padding，紧贴顶部 */
.chat-panel-container :deep(.simple-chat-panel .messages-container) {
  padding-top: 0;
  margin-top: 0;
}

/* 确保输入框始终可见且不被遮挡 */
.chat-panel-container :deep(.input-container) {
  position: relative;
  z-index: 100;
  flex-shrink: 0;
  min-height: 62px;
  background: #2d2d2d;
}


/* 当左侧边栏存在时，调整主内容区域的右边距，为右侧对话框留出空间 */
/* 主内容区域的右边距通过内联样式动态设置 */

/* 拖拽手柄样式 */
.drag-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: #e1e5e9;
  cursor: ew-resize;
  transition: background-color 0.2s ease;
  z-index: 1000;
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

.drag-handle:hover {
  background: #007bff;
}

.drag-handle:active {
  background: #0056b3;
}

/* 拖拽时防止文本选择和其他干扰 */
.dragging {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  pointer-events: none;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e1e5e9;
  min-height: 48px;
}

.chat-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.close-chat-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #666;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.close-chat-btn:hover {
  background: #e9ecef;
  color: #333;
}

.chat-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.chat-message {
  display: flex;
  margin-bottom: 16px;
  gap: 12px;
}

.message-avatar {
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

.chat-message.ai .message-avatar {
  background: #e3f2fd;
}

.chat-message.user .message-avatar {
  background: #f3e5f5;
}

.message-content {
  background: #f8f9fa;
  padding: 12px 16px;
  border-radius: 12px;
  max-width: 200px;
  word-wrap: break-word;
  font-size: 14px;
  line-height: 1.4;
  color: #333;
}

.chat-message.ai .message-content {
  background: #e3f2fd;
  color: #1565c0;
}

.chat-message.user .message-content {
  background: #f3e5f5;
  color: #7b1fa2;
}

.chat-input {
  display: flex;
  padding: 16px 20px;
  border-top: 1px solid #e1e5e9;
  gap: 12px;
}

.chat-input-field {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e1e5e9;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s ease;
}

.chat-input-field:focus {
  border-color: #007bff;
}

.chat-send-btn {
  padding: 8px 16px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.chat-send-btn:hover {
  background: #0056b3;
}

</style> 
