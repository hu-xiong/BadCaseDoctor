<template>
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
    @showHelp="showHelp"
    @showTeamManagement="showTeamManagement"
    @showUserProfile="showUserProfile"
    @showPreferences="openPreferences"
    @logout="logout"
  >

    <div class="main-container">
      <!-- 左侧导航栏 -->
      <div class="left-sidebar" :class="{ 'collapsed': planCollapsed }" v-show="!leftSidebarHidden">
       
       
      
        
        
        <div class="sidebar-content" v-show="!planCollapsed">
          <div class="sidebar-header">
            <div class="header-top">
              <h3>{{ t('project.sidebarTitle') }}</h3>
                            <div class="header-actions">
                <button class="action-icon-btn" @click="manualRefreshPlans" :title="t('project.refreshAll')">
                  <span class="icon">🔄</span>
                </button>
                <button class="action-icon-btn" @click="showCreatePlanModal" :title="t('project.addPlan')">
                  <span class="icon">➕</span>
                </button>
                <button class="action-icon-btn" @click="showBaselineManagement" :title="t('project.baselineMgmt')">
                  <span class="icon">📋</span>
                </button>
              
              </div>
            </div>
            <div class="search-section">
              <input 
                type="text" 
                v-model="planSearchText"
                :placeholder="t('project.searchPlanPlaceholder')"
                class="plan-search-input"
                @keyup.enter="searchPlans"
              />
              <button class="search-btn" @click="searchPlans">
                <span class="search-icon">🔍</span>
              </button>
              <button v-if="planSearchText" class="clear-search-btn" @click="clearSearch" :title="t('project.clearSearch')">
                <span class="clear-icon">✕</span>
              </button>
            </div>
          </div>
          
          <div class="plan-tree">
            <div class="plan-section">
              <div class="section-header" @click="toggleSection('unplanned')">
                <span class="section-icon">📄</span>
                <span class="section-title">{{ t('project.sectionUnplanned') }}</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.unplanned }">▶</span>
            </div>
            
              <div v-if="expandedSections.unplanned" class="section-content">
                <!-- 未计划卡片的类型选择 -->
                <div class="unplanned-type-section">
                  <!-- BadCase -->
                  <div class="type-item" :class="{ 'active': isUnplannedTypeChipActive('badcase') }" @click="selectUnplannedType('badcase')">
                    <span class="type-icon">📋</span>
                    <span class="type-title">BadCase</span>
                  </div>
                  <!-- Bug -->
                  <div class="type-item" :class="{ 'active': isUnplannedTypeChipActive('bug') }" @click="selectUnplannedType('bug')">
                    <span class="type-icon">🐛</span>
                    <span class="type-title">Bug</span>
                  </div>
                  <!-- 测试用例 -->
                  <div class="type-item" :class="{ 'active': isUnplannedTypeChipActive('test_case') }" @click="selectUnplannedType('test_case')">
                    <span class="type-icon">🧪</span>
                    <span class="type-title">{{ t('project.typeTestCase') }}</span>
                  </div>
                </div>

                <!-- 渲染未计划类型的计划 -->
                <div v-if="unplannedPlans.length > 0" class="plan-list">
                  <template v-for="plan in unplannedPlans" :key="plan.id">
                    <div 
                      class="plan-item"
                      :class="{ 'active': selectedPlan === plan.id }"
                      @click="selectPlan(plan.id)"
                      @mouseenter="showPlanActions(plan.id)"
                      @mouseleave="hidePlanActions(plan.id)"
                    >
                      <span 
                        v-if="plan.children && plan.children.length > 0" 
                        class="expand-arrow"
                        :class="{ 'expanded': expandedPlans.includes(plan.id) }"
                        @click="togglePlanExpansion(plan.id)"
                      >▶</span>
                      <span v-else class="expand-placeholder"></span>
                      <span class="plan-icon">{{ getPlanIcon(plan.content_type || plan.plan_type || 'badcase') }}</span>
                      <span class="plan-name">
                        {{ plan.name }}
                        <span v-if="plan.is_pinned" class="pin-indicator" :title="t('project.pinned')">📌</span>
                      </span>
                      <span class="plan-info">
                        <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                        <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
                        <span v-if="(plan.content_type || plan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count ?? 0 }}</span>
                      </span>
                      
                      <!-- 操作按钮 -->
                      <div v-show="hoveredPlan === plan.id" class="plan-actions">
                        <button class="action-btn" @click.stop="showContextMenu(plan, $event)">
                          ⚙️
                        </button>
                      </div>
                    </div>

                    <!-- 子计划 -->
                    <div v-if="plan.children && plan.children.length > 0 && expandedPlans.includes(plan.id)" class="sub-plan-list">
                      <div 
                        v-for="childPlan in plan.children" 
                        :key="childPlan.id"
                        class="plan-item sub-plan"
                        :class="{ 'active': selectedPlan === childPlan.id }"
                        @click="selectPlan(childPlan.id)"
                        @mouseenter="showPlanActions(childPlan.id)"
                        @mouseleave="hidePlanActions(childPlan.id)"
                      >
                        <span class="expand-placeholder"></span>
                        <span class="plan-icon">{{ getPlanIcon(childPlan.content_type || childPlan.plan_type || 'badcase') }}</span>
                        <span class="plan-name">{{ childPlan.name }}</span>
                        <span class="plan-info">
                          <span v-if="childPlan.badcase_count > 0" class="count-badge badcase">{{ childPlan.badcase_count }}</span>
                          <span v-if="childPlan.bug_count > 0" class="count-badge bug">{{ childPlan.bug_count }}</span>
                          <span v-if="(childPlan.content_type || childPlan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(childPlan.id)] ?? childPlan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(childPlan.id)] ?? childPlan.test_case_count ?? 0 }}</span>
                        </span>
                        
                        <!-- 操作按钮 -->
                        <div v-show="hoveredPlan === childPlan.id" class="plan-actions">
                          <button class="action-btn" @click.stop="showContextMenu(childPlan, $event)">
                            ⚙️
                          </button>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
            
            <!-- 进行中计划 -->
            <div class="plan-section">
              <div class="section-header" @click="toggleSection('inProgress')">
                <span class="section-icon">📁</span>
                <span class="section-title">{{ t('project.sectionInProgress') }}</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.inProgress }">▶</span>
              </div>
              
              <div v-if="expandedSections.inProgress" class="section-content">
                <div v-if="loading" class="loading-state">
                  <span class="loading-text">{{ t('common.loading') }}</span>
                </div>
                
                <div v-else-if="inProgressPlans.length === 0" class="empty-state">
                  <span class="empty-text">{{ t('project.emptyInProgress') }}</span>
                </div>
                
                <div v-else>
                  <div class="plan-list">
                    <!-- 渲染计划和其子计划 -->
                    <template v-for="plan in inProgressPlans" :key="plan.id">
                      <!-- 父计划 -->
                      <div 
                        class="plan-item"
                        :class="{ 'active': selectedPlan === plan.id }"
                        @click="selectPlan(plan.id)"
                        @mouseenter="showPlanActions(plan.id)"
                        @mouseleave="hidePlanActions(plan.id)"
                      >
                        <span 
                          v-if="plan.children && plan.children.length > 0" 
                          class="expand-arrow"
                          :class="{ 'expanded': expandedPlans.includes(plan.id) }"
                          @click="togglePlanExpansion(plan.id)"
                        >▶</span>
                        <span v-else class="expand-placeholder"></span>
                        <span class="plan-icon">{{ getPlanIcon(plan.content_type || plan.plan_type || 'badcase') }}</span>
                        <span class="plan-name">
                          {{ plan.name }}
                          <span v-if="plan.is_pinned" class="pin-indicator" :title="t('project.pinned')">📌</span>
                        </span>
                        <span class="plan-info">
                          <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                          <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
                          <span v-if="(plan.content_type || plan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count ?? 0 }}</span>
                        </span>
                        
                        <!-- 操作按钮 -->
                        <div v-show="hoveredPlan === plan.id" class="plan-actions">
                          <button class="action-btn" @click.stop="showContextMenu(plan, $event)">
                            ⚙️
                          </button>
                        </div>
                        
                        <!-- 上下文菜单（可拖动标题条 + 内容区滚动） -->
                        <div 
                          v-if="contextMenu.visible && contextMenu.planId === plan.id"
                          class="context-menu"
                          :class="{ 'is-dragging': contextMenuDragActive }"
                          :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                          @mousedown.stop
                        >
                          <div
                            class="context-menu-drag-handle"
                            :title="t('project.contextMenuDragHint')"
                            @mousedown.stop="onContextMenuDragStart"
                          >
                            <span class="drag-grip">⋮⋮</span>
                            <span class="drag-label">{{ t('project.contextMenuDrag') }}</span>
                          </div>
                          <div class="context-menu-body">
                          <div class="menu-item" @click="createSubPlan(plan)">
                            <span class="menu-icon">➕</span>
                            <span>{{ t('project.menuSubPlan') }}</span>
                          </div>
                          <div class="menu-item" @click="createSiblingPlan(plan)">
                            <span class="menu-icon">📝</span>
                            <span>{{ t('project.menuSiblingPlan') }}</span>
                          </div>
                          <div class="menu-item" @click="editPlan(plan)">
                            <span class="menu-icon">✏️</span>
                            <span>{{ t('project.menuEdit') }}</span>
                          </div>
                          <div class="menu-item" @click="archivePlan(plan)">
                            <span class="menu-icon">📦</span>
                            <span>{{ t('project.menuArchive') }}</span>
                          </div>
                          <div class="menu-item" @click="deletePlan(plan)">
                            <span class="menu-icon">🗑️</span>
                            <span>{{ t('project.menuDelete') }}</span>
                          </div>
                          <div class="menu-item" @click="pinPlan(plan)">
                            <span class="menu-icon">📌</span>
                            <span>{{ plan.is_pinned ? t('project.unpin') : t('project.pin') }}</span>
                          </div>
                          <div class="menu-item" @click="favoritePlan(plan)">
                            <span class="menu-icon">⭐</span>
                            <span>{{ t('project.favorite') }}</span>
                          </div>
                          <div class="menu-separator"></div>
                          <div class="menu-item" @click="createBaseline(plan)">
                            <span class="menu-icon">📋</span>
                            <span>{{ t('project.menuNewBaseline') }}</span>
                          </div>
                          </div>
                        </div>
                      </div>
                      
                      <!-- 子计划 - 紧跟在父计划后面 -->
                      <div v-if="plan.children && plan.children.length > 0 && expandedPlans.includes(plan.id)" class="sub-plan-list">
                        <template v-for="childPlan in plan.children" :key="childPlan.id">
                          <div 
                            class="plan-item sub-plan"
                            :class="{ 'active': selectedPlan === childPlan.id }"
                            @click="selectPlan(childPlan.id)"
                            @mouseenter="showPlanActions(childPlan.id)"
                            @mouseleave="hidePlanActions(childPlan.id)"
                          >
                            <span 
                              v-if="childPlan.children && childPlan.children.length > 0" 
                              class="expand-arrow"
                              :class="{ 'expanded': expandedPlans.includes(childPlan.id) }"
                              @click="togglePlanExpansion(childPlan.id)"
                            >▶</span>
                            <span v-else class="expand-placeholder"></span>
                            <span class="plan-icon">{{ getPlanIcon(childPlan.content_type || childPlan.plan_type || 'badcase') }}</span>
                            <span class="plan-name">
                              {{ childPlan.name }}
                              <span v-if="childPlan.is_pinned" class="pin-indicator" :title="t('project.pinned')">📌</span>
                            </span>
                            <span class="plan-info">
                              <span v-if="childPlan.badcase_count > 0" class="count-badge badcase">{{ childPlan.badcase_count }}</span>
                              <span v-if="childPlan.bug_count > 0" class="count-badge bug">{{ childPlan.bug_count }}</span>
                              <span v-if="(childPlan.content_type || childPlan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(childPlan.id)] ?? childPlan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(childPlan.id)] ?? childPlan.test_case_count ?? 0 }}</span>
                            </span>
                            
                            <!-- 操作按钮 -->
                            <div v-show="hoveredPlan === childPlan.id" class="plan-actions">
                              <button class="action-btn" @click.stop="showContextMenu(childPlan, $event)">
                                ⚙️
                              </button>
                            </div>
                            
                            <!-- 上下文菜单（可拖动标题条 + 内容区滚动） -->
                            <div 
                              v-if="contextMenu.visible && contextMenu.planId === childPlan.id"
                              class="context-menu"
                              :class="{ 'is-dragging': contextMenuDragActive }"
                              :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                              @mousedown.stop
                            >
                              <div
                                class="context-menu-drag-handle"
                                :title="t('project.contextMenuDragHint')"
                                @mousedown.stop="onContextMenuDragStart"
                              >
                                <span class="drag-grip">⋮⋮</span>
                                <span class="drag-label">{{ t('project.contextMenuDrag') }}</span>
                              </div>
                              <div class="context-menu-body">
                              <div class="menu-item" @click="createSubPlan(childPlan)">
                                <span class="menu-icon">➕</span>
                                <span>{{ t('project.menuSubPlan') }}</span>
                              </div>
                              <div class="menu-item" @click="createSiblingPlan(childPlan)">
                                <span class="menu-icon">📝</span>
                                <span>{{ t('project.menuSiblingPlan') }}</span>
                              </div>
                              <div class="menu-item" @click="editPlan(childPlan)">
                                <span class="menu-icon">✏️</span>
                                <span>{{ t('project.menuEdit') }}</span>
                              </div>
                              <div class="menu-item" @click="archivePlan(childPlan)">
                                <span class="menu-icon">📦</span>
                                <span>{{ t('project.menuArchive') }}</span>
                              </div>
                              <div class="menu-item" @click="deletePlan(childPlan)">
                                <span class="menu-icon">🗑️</span>
                                <span>{{ t('project.menuDelete') }}</span>
                              </div>
                              <div class="menu-item" @click="pinPlan(childPlan)">
                                <span class="menu-icon">📌</span>
                                <span>{{ childPlan.is_pinned ? t('project.unpin') : t('project.pin') }}</span>
                              </div>
                              <div class="menu-item" @click="favoritePlan(childPlan)">
                                <span class="menu-icon">⭐</span>
                                <span>{{ t('project.favorite') }}</span>
                              </div>
                              <div class="menu-separator"></div>
                              <div class="menu-item" @click="createBaseline(childPlan)">
                                <span class="menu-icon">📋</span>
                                <span>{{ t('project.menuNewBaseline') }}</span>
                              </div>
                              </div>
                            </div>
                          </div>
                          
                          <!-- 孙计划 - 紧跟在子计划后面 -->
                          <div v-if="childPlan.children && childPlan.children.length > 0 && expandedPlans.includes(childPlan.id)" class="sub-plan-list level-2">
                            <div 
                              v-for="grandChildPlan in childPlan.children" 
                              :key="grandChildPlan.id"
                              class="plan-item sub-plan level-2"
                              :class="{ 'active': selectedPlan === grandChildPlan.id }"
                              @click="selectPlan(grandChildPlan.id)"
                              @mouseenter="showPlanActions(grandChildPlan.id)"
                              @mouseleave="hidePlanActions(grandChildPlan.id)"
                            >
                              <span class="expand-placeholder"></span>
                              <span class="plan-icon">{{ getPlanIcon(grandChildPlan.content_type || grandChildPlan.plan_type || 'badcase') }}</span>
                              <span class="plan-name">
                                {{ grandChildPlan.name }}
                                <span v-if="grandChildPlan.is_pinned" class="pin-indicator" :title="t('project.pinned')">📌</span>
                              </span>
                              <span class="plan-info">
                                <span v-if="grandChildPlan.badcase_count > 0" class="count-badge badcase">{{ grandChildPlan.badcase_count }}</span>
                                <span v-if="grandChildPlan.bug_count > 0" class="count-badge bug">{{ grandChildPlan.bug_count }}</span>
                                <span v-if="(grandChildPlan.content_type || grandChildPlan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(grandChildPlan.id)] ?? grandChildPlan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(grandChildPlan.id)] ?? grandChildPlan.test_case_count ?? 0 }}</span>
                              </span>
                              
                              <!-- 操作按钮 -->
                              <div v-show="hoveredPlan === grandChildPlan.id" class="plan-actions">
                                <button class="action-btn" @click.stop="showContextMenu(grandChildPlan, $event)">
                                  ⚙️
                                </button>
                              </div>
                              
                              <!-- 上下文菜单（可拖动标题条 + 内容区滚动） -->
                              <div 
                                v-if="contextMenu.visible && contextMenu.planId === grandChildPlan.id"
                                class="context-menu"
                                :class="{ 'is-dragging': contextMenuDragActive }"
                                :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                                @mousedown.stop
                              >
                                <div
                                  class="context-menu-drag-handle"
                                  :title="t('project.contextMenuDragHint')"
                                  @mousedown.stop="onContextMenuDragStart"
                                >
                                  <span class="drag-grip">⋮⋮</span>
                                  <span class="drag-label">{{ t('project.contextMenuDrag') }}</span>
                                </div>
                                <div class="context-menu-body">
                                <div class="menu-item" @click="createSubPlan(grandChildPlan)">
                                  <span class="menu-icon">➕</span>
                                  <span>{{ t('project.menuSubPlan') }}</span>
                                </div>
                                <div class="menu-item" @click="createSiblingPlan(grandChildPlan)">
                                  <span class="menu-icon">📝</span>
                                  <span>{{ t('project.menuSiblingPlan') }}</span>
                                </div>
                                <div class="menu-item" @click="editPlan(grandChildPlan)">
                                  <span class="menu-icon">✏️</span>
                                  <span>{{ t('project.menuEdit') }}</span>
                                </div>
                                <div class="menu-item" @click="archivePlan(grandChildPlan)">
                                  <span class="menu-icon">📦</span>
                                  <span>{{ t('project.menuArchive') }}</span>
                                </div>
                                <div class="menu-item" @click="deletePlan(grandChildPlan)">
                                  <span class="menu-icon">🗑️</span>
                                  <span>{{ t('project.menuDelete') }}</span>
                                </div>
                                <div class="menu-item" @click="pinPlan(grandChildPlan)">
                                  <span class="menu-icon">📌</span>
                                  <span>{{ grandChildPlan.is_pinned ? t('project.unpin') : t('project.pin') }}</span>
                                </div>
                                <div class="menu-item" @click="favoritePlan(grandChildPlan)">
                                  <span class="menu-icon">⭐</span>
                                  <span>{{ t('project.favorite') }}</span>
                                </div>
                                <div class="menu-separator"></div>
                                <div class="menu-item" @click="createBaseline(grandChildPlan)">
                                  <span class="menu-icon">📋</span>
                                  <span>{{ t('project.menuNewBaseline') }}</span>
                                </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </template>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 已归档计划 -->
            <div class="plan-section">
              <div class="section-header" @click="toggleSection('archived')">
                <span class="section-icon">📦</span>
                <span class="section-title">{{ t('project.sectionArchived') }}</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.archived }">▶</span>
              </div>
              
              <div v-if="expandedSections.archived" class="section-content">
                <div v-if="loading" class="loading-state">
                  <span class="loading-text">{{ t('common.loading') }}</span>
            </div>
                
                <div v-else-if="archivedPlans.length === 0" class="empty-state">
                  <span class="empty-text">{{ t('project.emptyArchived') }}</span>
                </div>
                
                <div v-else>
                  <div class="plan-list">
                    <template v-for="plan in archivedPlans" :key="plan.id">
                      <div 
                        class="plan-item"
                        :class="{ 'active': selectedPlan === plan.id }"
                        @click="selectPlan(plan.id)"
                        @mouseenter="showPlanActions(plan.id)"
                        @mouseleave="hidePlanActions(plan.id)"
                      >
                        <span class="expand-placeholder"></span>
                        <span class="plan-icon">📦</span>
                        <span class="plan-name">
                          {{ plan.name }}
                          <span v-if="plan.is_pinned" class="pin-indicator" :title="t('project.pinned')">📌</span>
                        </span>
                        <span class="plan-info">
                          <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                          <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
                          <span v-if="(plan.content_type || plan.plan_type) === 'test_case' || ((planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count) ?? 0) > 0" class="count-badge testcase">{{ planTestCaseCounts[Number(plan.id)] ?? plan.test_case_count ?? 0 }}</span>
                        </span>
                        
                        <!-- 操作按钮 -->
                        <div v-show="hoveredPlan === plan.id" class="plan-actions">
                          <button class="action-btn" @click.stop="showContextMenu(plan, $event)">
                            ⚙️
                          </button>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
            
           
          </div>
        </div>
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
              <span class="workbench-tab-title">{{ tab.title }}</span>
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
        <keep-alive :max="16">
          <component
            v-if="showMainEditor"
            :is="mainEditorComponent"
            :key="mainEditorCacheKey"
            :project_id="projectId"
            :plan_id="mainEditorPlanId"
            :id="mainEditorItemId"
            :edit="mainEditorEdit"
            :show_diff="mainEditorShowDiff"
            :embedded="true"
            @close="closeMainEditor"
          />
        </keep-alive>
        <keep-alive :max="16">
          <component
            v-if="!showMainEditor"
            :key="listPanelCacheKey"
            :is="currentPlanType === 'bug' ? 'BugListPanel' : (currentPlanType === 'test_case' ? 'TestCaseListPanel' : 'BadcaseListPanel')"
          v-model:searchText="searchText"
          v-model:selectedAssignee="selectedAssignee"
          v-model:selectedStatus="selectedStatus"
          :generateBreadcrumb="generateBreadcrumb"
          :show-long-breadcrumb="workbenchTabs.length === 0"
          :currentPlanType="currentPlanType"
          :totalBadcases="totalBadcases"
          :projectMembers="projectMembers"
          :applyFilters="applyFilters"
          :refreshBadcases="refreshBadcases"
          :badcaseLoading="badcaseLoading"
          :filteredBadcases="filteredBadcases"
          :selectedTasks="selectedTasks"
          :selectAll="selectAll"
          :toggleSelectAll="toggleSelectAll"
          :toggleTaskSelection="toggleTaskSelection"
          :editItem="editBadcase"
          :pendingModifications="pendingModifications"
          :pendingCreates="pendingCreatesForCurrentView"
          :expandedDetailRows="expandedDetailRows"
          :hasDetailFieldModifications="hasDetailFieldModifications"
          :toggleDetailExpand="toggleDetailExpand"
          :isLastInConsecutiveGroup="isLastInConsecutiveGroup"
          :getConsecutiveGroupSize="getConsecutiveGroupSize"
          :confirmModify="confirmConsecutiveGroup"
          :cancelModify="cancelConsecutiveGroup"
          :confirmCreate="confirmCreate"
          :cancelCreate="cancelCreate"
          :getBadcaseStatusText="getBadcaseStatusText"
          :getAssigneeDisplayText="getAssigneeDisplayText"
          :createNewBadcase="createNewBadcase"
          />
        </keep-alive>
        </div>
        
        <!-- 底部Terminal和Output区域 -->
        <div v-if="showTerminal" class="bottom-panel" :class="{
          'with-left-sidebar': !leftSidebarHidden && !planCollapsed,
          'with-collapsed-sidebar': !leftSidebarHidden && planCollapsed
        }" :style="{ 
          height: bottomPanelHeight + 'px',
          right: showAIAssistant ? rightSidebarWidth + 'px' : '0px',
          zIndex: 100
        }">
          <!-- 拖拽手柄 -->
          <div class="drag-handle-horizontal" @mousedown="startDragBottomPanel"></div>
          
          <div class="panel-content">
            <EmbeddedTerminalWorkspace
              :working-directory="currentWorkingDir"
              :project-id="projectId"
            />
          </div>
        </div>
      </div>
      
      <!-- 右侧AI助手面板 -->
      <div v-if="showAIAssistant" class="right-sidebar ai-assistant-panel" :style="{ width: rightSidebarWidth + 'px' }">
        <!-- 拖拽手柄 -->
        <div class="drag-handle" @mousedown="startDragRightSidebar"></div>
        
        <!-- 面板头部 -->
        <div class="ai-panel-header">
          <div class="ai-panel-tabs">
            <div v-if="currentSession && sessions[currentSession]" class="ai-tab active">
              {{ sessions[currentSession].title || t('common.unnamedSession') }}
              <button class="tab-close" @click.stop="closeSessionTab(currentSession)">×</button>
            </div>
            <div v-else-if="currentSession" class="ai-tab active">
              {{ t('common.sessionLoading') }}
            </div>
          </div>
          <div class="ai-panel-actions">
            <button class="ai-action-btn" :title="t('common.newSession')" @click="createNewSession">+</button>
            <div class="dropdown">
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
            <div class="dropdown">
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
          <SimpleChatPanel v-if="currentSession" :sessionId="currentSession" :projectId="Number(projectId)" @title-updated="handleTitleUpdated" />
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
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ getModalTitle() }}</h3>
          <button class="close-btn" @click="closeCreateModal">✕</button>
        </div>
        
        <div class="modal-body">
          <div class="form-group cycle-row">
            <label class="form-label cycle-label required">{{ t('project.planCycle') }}</label>
            <select v-model="newPlan.cycle" class="form-select">
              <option value="one_week">{{ t('project.cycleOneWeek') }}</option>
              <option value="two_weeks">{{ t('project.cycleTwoWeeks') }}</option>
              <option value="one_month">{{ t('project.cycleOneMonth') }}</option>
              <option value="custom">{{ t('project.cycleCustom') }}</option>
            </select>
          </div>
          
          <div class="form-group date-row">
            <div class="date-field">
              <label class="form-label required">{{ t('project.startDate') }}</label>
              <div class="date-input-wrapper">
                <input 
                  type="date" 
                  v-model="newPlan.startDate" 
                  class="form-input"
                />
                <span class="calendar-icon">📅</span>
              </div>
            </div>
            
            <div class="date-field">
              <label class="form-label required">{{ t('project.endDate') }}</label>
              <div class="date-input-wrapper">
                <input 
                  type="date" 
                  v-model="newPlan.endDate" 
                  class="form-input"
                />
                <span class="calendar-icon">📅</span>
              </div>
            </div>
          </div>
          
          <div class="form-group count-row">
            <label class="form-label count-label">{{ t('project.planCount') }}</label>
            <div class="number-input-wrapper">
              <input 
                type="number" 
                v-model="newPlan.count" 
                min="1" 
                class="form-input count-input"
              />
              <span class="helper-text">{{ t('project.planCountHint', { count: newPlan.count, end: calculateEndDate() }) }}</span>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label required">{{ t('project.planName') }}</label>
            <div class="name-input-wrapper">
              <input 
                type="text" 
                v-model="newPlan.name" 
                :placeholder="namePlaceholder"
                class="form-input name-input"
                maxlength="50"
              />
              <div class="name-input-actions">
                <span class="char-count">{{ newPlan.name.length }}/50</span>
                <button class="help-btn" :title="t('project.namingHelp')">❓</button>
              </div>
            </div>
          </div>
          
          <div class="form-group parent-row">
            <label class="form-label parent-label">{{ t('project.parentPlan') }}</label>
            <select v-model="newPlan.parentId" class="form-select" :disabled="isCreatingSubPlan || isCreatingSiblingPlan">
              <option value="">{{ t('project.selectParentPlaceholder') }}</option>
              <option v-for="plan in availableParentPlans" :key="plan.id" :value="plan.id">
                {{ plan.name }}
              </option>
            </select>
            <div v-if="isCreatingSubPlan && newPlan.parentId" class="parent-plan-info">
              <span class="info-text">{{ t('project.parentAsCurrent') }}</span>
            </div>
            <div v-if="isCreatingSiblingPlan" class="parent-plan-info">
              <span class="info-text">{{ newPlan.parentId ? t('project.siblingUnderParent') : t('project.topLevelPlan') }}</span>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">{{ t('common.description') }}</label>
            <div class="textarea-wrapper">
              <textarea 
                v-model="newPlan.description" 
                class="form-textarea"
                maxlength="500"
              ></textarea>
              <span class="textarea-char-count">{{ newPlan.description.length }}/500</span>
            </div>
          </div>
          
          <!-- 新增：计划状态类型选择 -->
          <div class="form-group">
            <label class="form-label required">{{ t('project.planStatus') }}</label>
            <select v-model="newPlan.statusType" class="form-select">
              <option value="in_progress">{{ t('project.planStatusInProgress') }}</option>
              <option value="unplanned">{{ t('project.planStatusUnplanned') }}</option>
              <option value="archived">{{ t('project.planStatusArchived') }}</option>
            </select>
          </div>
          
          <!-- 新增：内容类型选择（子计划/同级计划必须与所选计划同类型，不可混选） -->
          <div class="form-group">
            <label class="form-label required">{{ t('project.contentType') }}</label>
            <select
              v-model="newPlan.contentType"
              class="form-select"
              :disabled="isCreatingSubPlan || isCreatingSiblingPlan"
            >
              <option value="badcase">{{ t('project.contentBadcase') }}</option>
              <option value="bug">{{ t('project.contentBug') }}</option>
              <option value="test_case">{{ t('project.contentTestCase') }}</option>
            </select>
            <p v-if="isCreatingSubPlan || isCreatingSiblingPlan" class="form-hint-inline">
              {{ t('project.contentTypeLocked') }}
            </p>
          </div>
          
          <div class="form-group">
            <label class="toggle-label">
              <span>{{ t('project.scopeNotify') }}</span>
              <input 
                type="checkbox" 
                v-model="newPlan.scopeNotification" 
                class="toggle-switch"
              />
            </label>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeCreateModal">{{ t('prefs.cancel') }}</button>
          <button class="btn btn-primary" @click="createPlan" :disabled="!isFormValid">
            {{ isEditingPlan ? t('common.update') : t('common.confirm') }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 团队管理模态框 -->
    <div v-if="showTeamManagementModal" class="modal-overlay" @click="closeConfigModals">
      <div class="modal-content team-management-modal" @click.stop>
        <div class="modal-header">
          <h3>{{ t('project.teamMgmt') }}</h3>
          <button class="close-btn" @click="closeConfigModals">×</button>
        </div>
        
        <div class="modal-body">
          <TeamManagement :project-id="projectId" />
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

    <!-- 个人资料弹窗 -->
    <UserProfile 
      v-if="showProfileModal" 
      :user="currentUser" 
      @close="showProfileModal = false"
    />

    <Teleport to="body">
      <div
        v-if="showPreferencesModal"
        class="prefs-modal-overlay"
        @click.self="showPreferencesModal = false"
      >
        <div class="prefs-modal">
          <h3 class="prefs-modal-title">{{ t('prefs.title') }}</h3>
          <label class="prefs-lang-label">{{ t('prefs.language') }}</label>
          <select v-model="preferenceLocaleDraft" class="prefs-lang-select">
            <option value="zh-CN">{{ t('prefs.zh') }}</option>
            <option value="en">{{ t('prefs.en') }}</option>
          </select>
          <div class="prefs-actions">
            <button type="button" class="prefs-btn prefs-btn-cancel" @click="showPreferencesModal = false">
              {{ t('prefs.cancel') }}
            </button>
            <button type="button" class="prefs-btn prefs-btn-save" @click="savePreferences">{{ t('prefs.save') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </ProjectWorkspaceShell>
</template>

<script>
import { ref, reactive, onMounted, onUnmounted, computed, watch, nextTick, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { persistLocale } from '../i18n/index.js'
import { BACKEND_BASE_URL, getProjectPlans, getProjectDetail, createPlan as createPlanApi, updatePlan as updatePlanApi, deletePlan as deletePlanApi, pinPlan as pinPlanApi, getProjectBadcases, getProjectBugs, getProjectTestCases, updateBadcasePlan, getProjectMembers, getChatSessions, createChatSession, getChatSession } from '../api.js'
import { getBadCaseStatusText } from '../constants/status.js'
import TeamManagement from './TeamManagement.vue'
import EmbeddedTerminalWorkspace from './EmbeddedTerminalWorkspace.vue'
import SimpleChatPanel from './SimpleChatPanel.vue'
import UserProfile from './UserProfile.vue'
import ProjectWorkspaceShell from './ProjectWorkspaceShell.vue'
import BadcaseListPanel from './panels/BadcaseListPanel.vue'
import BugListPanel from './panels/BugListPanel.vue'
import TestCaseListPanel from './panels/TestCaseListPanel.vue'
import NewBadcase from './NewBadcase.vue'
import NewBug from './NewBug.vue'
import NewTestCase from './NewTestCase.vue'
import userStore from '../store/user.js'
import { persistStableCreatedId, getStableCreatedId } from '../utils/createPreviewKeys.js'

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
    BadcaseListPanel,
    BugListPanel,
    TestCaseListPanel,
    TeamManagement,
    EmbeddedTerminalWorkspace,
    SimpleChatPanel,
    UserProfile
  },
  setup() {
    const router = useRouter()
    const route = useRoute()
    const { t, locale } = useI18n()

    // 项目信息
    const projectName = ref('')
    const projectId = ref(null)
    // 嵌入式终端初始 cwd：空则后端在进程默认目录下开 shell（勿写死他人机器路径）
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
      archived: false,
      unplanned: true
    })

    // 未计划badcase展开状态
    const expandedUnplannedBadcase = ref(false)

    // 选择状态
    const selectedPlan = ref(null)
    const highlightBugId = ref(null) // 用于高亮显示的bug ID
    const urlContentType = ref(null) // URL参数传递的内容类型，优先级高于计划类型
    const currentPlan = computed(() => {
      if (!selectedPlan.value || selectedPlan.value === 'unplanned') {
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
      // 优先使用 URL 参数传递的内容类型
      if (urlContentType.value) {
        console.log('🐛 currentPlanType: 使用URL参数类型:', urlContentType.value)
        return urlContentType.value
      }
      
      if (selectedPlan.value === 'unplanned') {
        console.log('🐛 currentPlanType: unplanned → badcase')
        return 'badcase'
      }
      if (!currentPlan.value) {
        console.log('🐛 currentPlanType: no currentPlan → badcase')
        return 'badcase'
      }
      const planType = currentPlan.value.content_type || currentPlan.value.plan_type || 'badcase'
      console.log('🐛 currentPlanType:', {
        planId: selectedPlan.value,
        planName: currentPlan.value.name,
        content_type: currentPlan.value.content_type,
        plan_type: currentPlan.value.plan_type,
        finalType: planType
      })
      return planType
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

    /** 未计划区 BadCase/Bug/测试用例 三枚入口高亮（需与 fetch 后 selectedPlan 可为 unplanned 共存） */
    const isUnplannedTypeChipActive = (type) => {
      if (selectedPlan.value != null && typeof selectedPlan.value === 'number') return false
      if (type === 'badcase') {
        return (
          urlContentType.value === 'badcase' ||
          (!urlContentType.value && selectedPlan.value === 'unplanned')
        )
      }
      return urlContentType.value === type
    }
    
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

    const showTeamManagementModal = ref(false)
    const showProjectSettingsModal = ref(false)
    const showPermissionSettingsModal = ref(false)
    const showBaselineManagementModal = ref(false)

    // 用户下拉菜单状态
    const showUserDropdown = ref(false)
    const showProfileModal = ref(false)
    const showPreferencesModal = ref(false)
    const preferenceLocaleDraft = ref('zh-CN')
    const currentUser = ref(null)
    
    // 布局控制状态
    const showTerminal = ref(false)
    const showAIAssistant = ref(false)

    const terminalCtl = ref(null)
    provide('terminalCtl', terminalCtl)
    const chatComposerPreset = ref({ token: 0, text: '' })
    provide('chatComposerPreset', chatComposerPreset)

    const badcaseDraftPreset = ref({ token: 0, description: '' })
    provide('badcaseDraftPreset', badcaseDraftPreset)

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
    const mainEditorComponent = ref(null)
    const mainEditorItemId = ref(null)
    const mainEditorEdit = ref(true)
    const mainEditorPlanId = ref(null)
    const mainEditorShowDiff = ref(false)
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

    /** Cursor 式工作区：计划列表 / 未计划 / 详情 各为一个 Tab，标题为短名 */
    const workbenchTabs = ref([])
    /** ⋯ 下拉不展示「未计划 BadCase」列表 Tab（与 Tab 条切换即可，避免重复一项） */
    const workbenchTabsForMoreMenu = computed(() =>
      workbenchTabs.value.filter((t) => t.id !== 'unplanned-badcase')
    )
    const activeWorkbenchTabId = ref(null)
    const workbenchMenuRef = ref(null)
    const workbenchTabsStripRef = ref(null)
    /** Tab 条左键拖拽平移时用于样式（抓手 / 禁止选中文本） */
    const workbenchTabStripDraggingUI = ref(false)
    /** 拖拽滑动与单击切换 Tab 互斥 */
    const _tabStripDrag = { active: false, startX: 0, startScroll: 0, dragged: false }
    const showWorkbenchTabMenu = ref(false)
    let workbenchMenuOutsideCleanup = null
    
    // 右侧对话框拖拽状态
    const rightSidebarWidth = ref(320)
    const isDraggingRightSidebar = ref(false)
    const dragStartX = ref(0)
    const dragStartWidth = ref(320)
    
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
    
    // 计划展开状态
    const expandedPlans = ref([])
    
    // 新建计划模态框状态
    const showCreateModal = ref(false)
    const isCreatingSubPlan = ref(false) // 区分是创建普通计划还是子计划
    const isCreatingSiblingPlan = ref(false) // 是否创建同级计划
    const isEditingPlan = ref(false) // 是否处于编辑模式
    const editingPlanId = ref(null) // 正在编辑的计划ID
    const newPlan = reactive({
      cycle: 'one_week',
      startDate: '',
      endDate: '',
      count: 1,
      name: '',
      parentId: '',
      description: '',
      scopeNotification: false,
      // 新增：计划状态类型
      statusType: 'in_progress', // 'in_progress' | 'unplanned' | 'archived'
      // 新增：内容类型
      contentType: 'badcase' // 'badcase' | 'bug' | 'test_case'
    })
    
    // BadCase数据
    const badcases = ref([])
    const filteredBadcases = ref([]) // 根据选择的计划过滤后的BadCase
    const badcaseLoading = ref(false)
    const badcasePage = ref(1)
    const badcasePerPage = ref(20)
    const totalBadcases = ref(0)
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
      return s
    }
    const normalizeViewType = (ct) => {
      const s = (ct || '').toString().toLowerCase()
      if (s === 'testcase' || s === 'test_case') return 'test_case'
      if (s === 'bug') return 'bug'
      if (s === 'badcase') return 'badcase'
      return s
    }
    /**
     * 仅在「当前视图」展示待确认新建行：内容类型一致，且 plan_id 与当前选中的迭代计划一致（未计划视图只显示无 plan 的预览）。
     */
    const pendingCreatesForCurrentView = computed(() => {
      const list = pendingCreates.value || []
      const ct = normalizeViewType(currentPlanType.value)
      const sp = selectedPlan.value
      return list.filter((pc) => {
        const t = normalizeCreateTarget(pc.target)
        if (t !== ct) return false
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
    
    // 详情字段列表（不在列表中显示的字段）
    // 详情字段列表（不在列表中显示的字段）
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
      'reproduce_steps'
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

    // 列表字段（在表格列中即可直接看到/编辑的字段）
    const LIST_FIELDS = [
      'title',
      'status',
      'priority',
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
    
    // 计算未计划的BadCase数量
    const unplannedBadcaseCount = computed(() => {
      return badcases.value.filter(b => !b.plan_id || b.plan_id === null).length
    })
    
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
    
    const unplannedPlans = computed(() => {
      // 兼容更多可能的状态值，包括新创建和待处理状态
      const plans = projectPlans.value.filter(plan => {
        const st = String(plan.status ?? '').toLowerCase()
        const mistypedUnplanned =
          plan.status_type === 'unplanned' &&
          st &&
          !['unplanned', 'new'].includes(st)
        if (mistypedUnplanned) return false
        return (
          (plan.status_type === 'unplanned') ||
          (plan.status === 'unplanned') ||
          (plan.status === 'new') ||
          (!plan.status && !plan.status_type)
        )
      })

      // 去重逻辑：针对名称为“未计划BadCase”的自动创建计划，只保留第一个
      const seenUnplannedSystemPlan = new Set()
      return plans.filter(plan => {
        if (plan.name === '未计划BadCase') {
          if (seenUnplannedSystemPlan.has(plan.name)) {
            return false
          }
          seenUnplannedSystemPlan.add(plan.name)
        }
        return true
      })
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
        if (selectedPlan.value && selectedPlan.value !== 'unplanned') {
          // 确保是数字类型传递给后端
          const planId = parseInt(selectedPlan.value)
          if (!isNaN(planId)) {
            additionalParams.plan_id = planId
          }
        } else if (selectedPlan.value === 'unplanned') {
          additionalParams.status_type = 'unplanned'
        }
        
        // 如果有特定的内容类型，也传递给后端
        if (currentPlanType.value) {
          additionalParams.content_type = currentPlanType.value
        }
        
        let response
        if (currentPlanType.value === 'bug') {
          console.log('🔍 检测到当前计划类型为 bug，调用 getProjectBugs')
          response = await getProjectBugs(projectId.value, page, badcasePerPage.value, additionalParams)
        } else if (currentPlanType.value === 'test_case') {
          console.log('🔍 检测到当前计划类型为 test_case，调用 getProjectTestCases')
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
            message_id: messageId ?? null,
            session_id: currentSession.value ?? null
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
            message_id: messageId ?? null,
            session_id: currentSession.value ?? null
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

        await handleShowModifyInList({ detail: { __modifyListBatch: true, items: batchItems } })

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

    // 刷新BadCase数据
    const refreshBadcases = () => {
      fetchBadcases(1)
    }

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
      console.log('📦 getPlanIcon 被调用:', contentType)
      const iconMap = {
        'badcase': '📋',
        'bug': '🐛',
        'test_case': '🧪'
      }
      const icon = iconMap[contentType] || '📋'
      console.log('📦 返回图标:', icon, '（contentType:', contentType, '）')
      return icon
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
    
    // 获取负责人显示文本
    const getAssigneeDisplayText = (assignee) => {
      if (!assignee || assignee === '') {
        return t('list.unassigned')
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
        const contentType = plan.content_type || plan.plan_type || 'badcase'
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
      return newPlan.cycle && newPlan.startDate && newPlan.endDate && newPlan.name.trim()
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
    
    // 确保有未计划的BadCase类型计划 - 已禁用
    let isEnsuringUnplannedPlan = false
    const ensureUnplannedBadcasePlan = async () => {
      // 已禁用自动创建未计划BadCase计划
      console.log('⚠️ ensureUnplannedBadcasePlan 已禁用')
      return
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
    
    // 切换未计划badcase展开状态
    const toggleUnplannedBadcaseSection = () => {
      expandedUnplannedBadcase.value = !expandedUnplannedBadcase.value
    }

    /** 切换侧栏计划/未计划视图时关闭主区域嵌入详情，否则会一直盖在列表上 */
    const clearEmbeddedEditor = () => {
      if (!showMainEditor.value) return
      showMainEditor.value = false
      mainEditorComponent.value = null
      mainEditorItemId.value = null
      mainEditorEdit.value = true
      mainEditorPlanId.value = null
      mainEditorShowDiff.value = false
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

    const mountEditorComponents = (itemId, editorPlanType, showDiff, edit = true, planId = null) => {
      if (editorPlanType === 'bug') {
        mainEditorComponent.value = NewBug
      } else if (editorPlanType === 'test_case') {
        mainEditorComponent.value = NewTestCase
      } else {
        mainEditorComponent.value = NewBadcase
      }
      embeddedEditorKind.value = editorPlanType
      mainEditorItemId.value = itemId
      mainEditorEdit.value = !!edit
      mainEditorPlanId.value = planId
      mainEditorShowDiff.value = showDiff
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
        meta: { planId: pid, urlContentType: null }
      })
      activeWorkbenchTabId.value = `plan-${pid}`
      console.log('选择计划:', planId)
      await applyPlanListTabState({ planId: pid, urlContentType: null })
    }
    
    // 选择未计划的卡片
    const selectUnplanned = async () => {
      clearEmbeddedEditor()
      upsertWorkbenchTab({
        id: 'unplanned-badcase',
        kind: 'plan-list',
        title: truncateForTab(t('tab.unplannedBadcase'), t('tab.unplannedShort')),
        meta: { planId: 'unplanned', urlContentType: null }
      })
      activeWorkbenchTabId.value = 'unplanned-badcase'
      console.log('选择未计划的卡片')
      expandedSections.unplanned = true
      expandedUnplannedBadcase.value = true
      await applyPlanListTabState({ planId: 'unplanned', urlContentType: null })
    }
    
    // 选择未计划卡片中的BadCase
    const selectUnplannedBadcase = async () => {
      console.log('=== 点击未计划卡片中的BadCase ===')
      
      try {
        // 检查现有的BadCase数据
        console.log('🔍 检查现有BadCase数据')
        
        // 检查是否有BadCase数据
        if (badcases.value.length === 0) {
          console.log('⚠️ 没有BadCase数据，需要先获取数据')
          // 如果没有数据，才调用API获取
          // 直接调用fetchUnplannedBadcases方法，使用status_type和content_type筛选
          await fetchUnplannedBadcases(1)
        }
        
        // 检查每个BadCase是否有关联的plan
        const badcaseWithPlan = badcases.value.find(b => b.plan_id && b.plan_id !== 0)
        const badcaseWithoutPlan = badcases.value.find(b => !b.plan_id || b.plan_id === 0)
        
        console.log('🔍 BadCase检查结果:')
        console.log('- 有关联计划的BadCase:', badcaseWithPlan)
        console.log('- 无关联计划的BadCase:', badcaseWithoutPlan)
        
        if (badcaseWithPlan) {
          // 如果有BadCase关联了plan，但仍然使用status_type和content_type查询
          console.log(`✅ 找到关联plan的BadCase: "${badcaseWithPlan.title}" -> plan_id: ${badcaseWithPlan.plan_id}`)
          selectedPlan.value = 'unplanned'
          
          // 始终使用status_type和content_type查询，不使用plan_id
          console.log(`🔍 调用API: /api/projects/${projectId.value}/badcases?page=1&per_page=20&status_type=unplanned&content_type=badcase`)
          await fetchUnplannedBadcases(1)
          
          // 展开未计划section
          expandedSections.unplanned = true
          expandedUnplannedBadcase.value = true
          
          // 应用筛选条件
          applyFilters()
          
        } else if (badcaseWithoutPlan) {
          // 如果没有BadCase关联plan，创建一个新plan
          console.log(`⚠️ BadCase "${badcaseWithoutPlan.title}" 没有关联plan，开始创建新plan...`)
          await createPlanForBadcase(badcaseWithoutPlan)
          
        } else {
          // 所有BadCase都没有关联plan
          console.log('📊 所有BadCase都没有关联plan，使用status_type和content_type查询')
          selectedPlan.value = 'unplanned'
          
          // 使用status_type和content_type查询未计划的BadCase
          console.log(`🔍 调用API: /api/projects/${projectId.value}/badcases?page=1&per_page=20&status_type=unplanned&content_type=badcase`)
          await fetchUnplannedBadcases(1)
          
          // 展开未计划section
          expandedSections.unplanned = true
          expandedUnplannedBadcase.value = true
          
          // 应用筛选条件
          applyFilters()
          console.log(`📊 显示所有未关联计划的BadCase，共${filteredBadcases.value.length}个`)
        }
        
        // 确保右侧主内容区显示BadCase数据
        console.log('📊 右侧主内容区将显示BadCase数据')
        
        // 强制更新右侧主内容区的显示
        nextTick(() => {
          console.log('✅ 右侧主内容区已更新')
          console.log(`📊 当前BadCase数据: ${filteredBadcases.value.length} 个`)
        })
        
      } catch (error) {
        console.error('❌ 处理BadCase时发生错误:', error)
      }
    }
    
    // 选择未计划的类型（BadCase/Bug/测试用例）
    const selectUnplannedType = async (type) => {
      console.log(`=== 点击未计划类型: ${type} ===`)
      clearEmbeddedEditor()
      const shortTitles = {
        badcase: t('tab.unplannedBadcase'),
        bug: t('tab.unplannedBug'),
        test_case: t('tab.unplannedTestCase')
      }
      upsertWorkbenchTab({
        id: `unplanned-${type}`,
        kind: 'plan-list',
        title: truncateForTab(shortTitles[type] || String(type), t('tab.unplannedShort')),
        meta: { planId: null, urlContentType: type }
      })
      activeWorkbenchTabId.value = `unplanned-${type}`
      try {
        await applyPlanListTabState({ planId: null, urlContentType: type })
        expandedSections.unplanned = true
      } catch (error) {
        console.error(`❌ 处理${type}时发生错误:`, error)
      }
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
    
    // 获取未计划且BadCase类型的BadCase
    const fetchUnplannedBadcases = async (page = 1) => {
      console.log(`=== fetchUnplannedBadcases 开始 ===`)
      console.log('页码:', page)
      console.log('项目ID:', projectId.value)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取BadCase数据')
        return
      }
      
      badcaseLoading.value = true
      try {
        // 构建API参数：使用status_type和content_type筛选
        const params = {
          status_type: 'unplanned',
          content_type: 'badcase'
        }
        
        console.log('📋 未计划BadCase筛选参数:', params)
        console.log('调用API: getProjectBadcases，参数:', params)
        console.log(`🔍 检索条件: 项目ID=${projectId.value}, 页码=${page}, 每页数量=${badcasePerPage.value}`)
        
        const response = await getProjectBadcases(projectId.value, page, badcasePerPage.value, params)
        console.log('API响应:', response)
        
        if (response && response.data && response.data.success) {
          badcases.value = response.data.badcases || []
          filteredBadcases.value = [...badcases.value]
          totalBadcases.value = response.data.total || 0
          badcasePage.value = page
          
          console.log(`✅ 未计划且BadCase类型的BadCase检索成功，共${badcases.value.length}个`)
          console.log(`📊 检索结果: 总数=${totalBadcases.value}, 当前页=${badcasePage.value}`)
          
          // 已禁用自动创建未计划BadCase计划
          // if (badcases.value.length === 0 && totalBadcases.value === 0) {
          //   console.log('⚠️ 未计划BadCase查询结果为空，开始创建未计划的BadCase类型计划...')
          //   await createUnplannedBadcasePlan()
          // }
          
          // 检查每个BadCase的数据
          badcases.value.forEach((badcase, index) => {
            console.log(`BadCase ${index + 1}:`, {
              id: badcase.id,
              title: badcase.title,
              status: badcase.status,
              assignee: badcase.assignee,
              plan_id: badcase.plan_id,
              created_at: badcase.created_at
            })
          })
          
          // 设置selectedPlan为'unplanned'，确保UI状态正确
          selectedPlan.value = 'unplanned'
          
          // 应用筛选条件
          applyFilters()
          
          console.log('📊 未计划BadCase数据已获取，右侧主内容区将显示数据')
          console.log(`📊 获取到 ${badcases.value.length} 个BadCase`)
          
        } else {
          console.error('获取未计划BadCase数据失败:', response?.data?.error || '未知错误')
          badcases.value = []
          totalBadcases.value = 0
        }
      } catch (error) {
        console.error('获取未计划BadCase数据异常:', error)
        console.error('错误详情:', error.message)
        console.error('错误堆栈:', error.stack)
      } finally {
        badcaseLoading.value = false
        console.log('=== fetchUnplannedBadcases 完成 ===')
      }
    }
    
    // 获取未计划的Bug
    const fetchUnplannedBugs = async (page = 1) => {
      console.log(`=== fetchUnplannedBugs 开始 ===`)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取Bug数据')
        return
      }
      
      badcaseLoading.value = true
      try {
        const params = {
          status_type: 'unplanned'
        }
        
        console.log('🐛 未计划Bug筛选参数:', params)
        
        // 调用Bug专用API
        const response = await getProjectBugs(projectId.value, page, badcasePerPage.value, params)
        
        if (response && response.data && response.data.success) {
          badcases.value = response.data.badcases || []
          filteredBadcases.value = [...badcases.value]
          totalBadcases.value = response.data.total || 0
          badcasePage.value = page
          selectedPlan.value = 'unplanned'
          
          applyFilters()
          console.log(`✅ 未计划Bug检索成功，共${badcases.value.length}个`)
        } else {
          console.error('获取未计划Bug数据失败:', response?.data?.error || '未知错误')
          badcases.value = []
          totalBadcases.value = 0
        }
      } catch (error) {
        console.error('获取未计划Bug数据异常:', error)
      } finally {
        badcaseLoading.value = false
      }
    }
    
    // 获取未计划的测试用例
    const fetchUnplannedTestCases = async (page = 1) => {
      console.log(`=== fetchUnplannedTestCases 开始 ===`)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取测试用例数据')
        return
      }
      
      badcaseLoading.value = true
      try {
        const params = {
          status_type: 'unplanned'
        }
        
        console.log('🧪 未计划测试用例筛选参数:', params)
        
        // 调用TestCase专用API
        const response = await getProjectTestCases(projectId.value, page, badcasePerPage.value, params)
        
        if (response && response.data && response.data.success) {
          badcases.value = response.data.badcases || []
          filteredBadcases.value = [...badcases.value]
          totalBadcases.value = response.data.total || 0
          badcasePage.value = page
          selectedPlan.value = 'unplanned'
          
          applyFilters()
          console.log(`✅ 未计划测试用例检索成功，共${badcases.value.length}个`)
        } else {
          console.error('获取未计划测试用例数据失败:', response?.data?.error || '未知错误')
          badcases.value = []
          totalBadcases.value = 0
        }
      } catch (error) {
        console.error('获取未计划测试用例数据异常:', error)
      } finally {
        badcaseLoading.value = false
      }
    }
    
    // 创建未计划的BadCase类型计划（当查询结果为空时调用）
    const createUnplannedBadcasePlan = async () => {
      // 已禁用自动创建"未计划BadCase"计划
      console.log('⚠️ 自动创建未计划BadCase计划已禁用')
      return
    }

    /** 按 planId 解析应使用的列表 API（切换计划时 selectedPlan 可能仍是上一个计划，不能依赖 currentPlanType） */
    const getPlanListApiKindByPlanId = (planId) => {
      const numericPlanId = typeof planId === 'number' ? planId : parseInt(String(planId), 10)
      if (Number.isNaN(numericPlanId)) {
        return currentPlanType.value
      }
      const planObj = findPlanRecursive(projectPlans.value, numericPlanId)
      if (!planObj) {
        return currentPlanType.value
      }
      const raw = (planObj.content_type || planObj.plan_type || 'badcase').toString().toLowerCase()
      if (raw === 'bug') return 'bug'
      if (raw === 'testcase' || raw === 'test_case') return 'test_case'
      return 'badcase'
    }
    
    // 根据计划ID调用API获取BadCase
    const fetchBadcasesByPlan = async (planId, page = 1) => {
      console.log(`=== fetchBadcasesByPlan 开始 ===`)
      console.log('计划ID:', planId)
      console.log('页码:', page)
      console.log('项目ID:', projectId.value)
      
      if (!projectId.value) {
        console.error('项目ID为空，无法获取BadCase数据')
        return
      }
      
      // 如果传入的是'unplanned'，调用专门的未计划BadCase查询方法
      if (planId === 'unplanned') {
        console.log('🔍 检测到unplanned标识，调用fetchUnplannedBadcases方法')
        return await fetchUnplannedBadcases(page)
      }
      
      badcaseLoading.value = true
      try {
        // 构建API参数 - 处理数字或字符串类型的planId
        const params = {}
        
        // 转换为数字，如果有效则设置参数
        const numericPlanId = typeof planId === 'number' ? planId : parseInt(planId)
        
        if (planId && !isNaN(numericPlanId)) {
          params.plan_id = numericPlanId
          console.log(`🔍 检索计划ID: ${numericPlanId} 的数据`)
        } else {
          console.error('❌ 无效的计划ID:', planId, '类型:', typeof planId)
          return
        }
        
        console.log('📋 API参数:', params)

        const listKind = getPlanListApiKindByPlanId(planId)
        let response
        if (listKind === 'bug') {
          console.log(`🔍 调用 getProjectBugs，检索计划ID: ${planId}`)
          response = await getProjectBugs(projectId.value, page, badcasePerPage.value, params)
        } else if (listKind === 'test_case') {
          console.log(`🔍 调用 getProjectTestCases，检索计划ID: ${planId}`)
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

    /** 按 Tab 元数据恢复列表状态（需在 fetchBadcasesByPlan / fetchUnplanned* 之后定义） */
    const applyPlanListTabState = async (meta) => {
      const m = meta || {}
      const { planId, urlContentType: uct } = m
      if (planId != null && planId !== 'unplanned' && typeof planId === 'number') {
        // 与侧栏点计划一致时 meta.urlContentType 为 null；grep/modify 可按记录类型覆盖
        urlContentType.value = uct !== undefined ? uct : null
        selectedPlan.value = planId
        await fetchBadcasesByPlan(planId, 1)
        filterBadcasesByPlan(planId)
        await nextTick()
        window.dispatchEvent(
          new CustomEvent('request-pending-modify-for-plan', {
            detail: { planId, suppressAutoOpenDetail: true }
          })
        )
      } else if (planId === 'unplanned') {
        urlContentType.value = null
        selectedPlan.value = 'unplanned'
        expandedSections.unplanned = true
        expandedUnplannedBadcase.value = true
        await fetchUnplannedBadcases(1)
        filterBadcasesByPlan('unplanned')
      } else if (uct) {
        urlContentType.value = uct
        selectedPlan.value = null
        if (uct === 'badcase') {
          await fetchUnplannedBadcases(1)
        } else if (uct === 'bug') {
          await fetchUnplannedBugs(1)
        } else if (uct === 'test_case') {
          await fetchUnplannedTestCases(1)
        }
        expandedSections.unplanned = true
        applyFilters()
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
      // 未计划 BadCase（含首次进入：selectedPlan/url 尚未就绪时的兜底）
      if (!uct && (st === 'unplanned' || st == null)) {
        upsertWorkbenchTab({
          id: 'unplanned-badcase',
          kind: 'plan-list',
          title: truncateForTab(t('tab.unplannedBadcase'), t('tab.unplannedShort')),
          meta: { planId: 'unplanned', urlContentType: null }
        })
        activeWorkbenchTabId.value = 'unplanned-badcase'
        return
      }
      if (uct) {
        const shortTitles = {
          badcase: t('tab.unplannedBadcase'),
          bug: t('tab.unplannedBug'),
          test_case: t('tab.unplannedTestCase')
        }
        upsertWorkbenchTab({
          id: `unplanned-${uct}`,
          kind: 'plan-list',
          title: truncateForTab(shortTitles[uct] || String(uct), t('tab.unplannedShort')),
          meta: { planId: null, urlContentType: uct }
        })
        activeWorkbenchTabId.value = `unplanned-${uct}`
      }
    }

    const activateWorkbenchTab = async (tabId) => {
      const tab = workbenchTabs.value.find((t) => t.id === tabId)
      if (!tab) return
      activeWorkbenchTabId.value = tabId
      if (tab.kind === 'detail') {
        const { entityId, editorPlanType, showDiff } = tab.meta || {}
        mountEditorComponents(entityId, editorPlanType, !!showDiff, true, null)
        return
      }
      if (tab.kind === 'create') {
        const { editorPlanType, planId } = tab.meta || {}
        mountEditorComponents(null, editorPlanType, false, false, planId ?? null)
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
      const wasDetail = workbenchTabs.value[idx].kind === 'detail'
      workbenchTabs.value.splice(idx, 1)
      if (wasDetail && wasActive) clearEmbeddedEditor()
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
      if (targetId == null || targetId === 'unplanned') return
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

      if (planId != null && planId !== 'unplanned' && typeof planId === 'number') {
        const planObj = findPlanRecursive(projectPlans.value, planId)
        const title = truncateForTab(planObj?.name, t('tab.planFallback', { id: planId }))
        upsertWorkbenchTab({
          id: `plan-${planId}`,
          kind: 'plan-list',
          title,
          meta: { planId, urlContentType: uct !== undefined ? uct : null }
        })
        await activateWorkbenchTab(`plan-${planId}`)
        await nextTick()
        scrollActiveWorkbenchTabIntoView()
        return
      }
      if (planId === 'unplanned') {
        upsertWorkbenchTab({
          id: 'unplanned-badcase',
          kind: 'plan-list',
          title: truncateForTab(t('tab.unplannedBadcase'), t('tab.unplannedShort')),
          meta: { planId: 'unplanned', urlContentType: null }
        })
        await activateWorkbenchTab('unplanned-badcase')
        await nextTick()
        scrollActiveWorkbenchTabIntoView()
        return
      }
      if (uct) {
        const shortTitles = {
          badcase: t('tab.unplannedBadcase'),
          bug: t('tab.unplannedBug'),
          test_case: t('tab.unplannedTestCase')
        }
        upsertWorkbenchTab({
          id: `unplanned-${uct}`,
          kind: 'plan-list',
          title: truncateForTab(shortTitles[uct] || String(uct), t('tab.unplannedShort')),
          meta: { planId: null, urlContentType: uct }
        })
        await activateWorkbenchTab(`unplanned-${uct}`)
        await nextTick()
        scrollActiveWorkbenchTabIntoView()
      }
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

    watch(activeWorkbenchTabId, () => {
      nextTick(() => scrollActiveWorkbenchTabIntoView())
    })
    
    const toggleSelectAll = () => {
      if (selectAll.value) {
        selectedTasks.value = filteredBadcases.value.map(badcase => badcase.id)
      } else {
        selectedTasks.value = []
      }
    }
    
    const toggleTaskSelection = (taskId) => {
      const index = selectedTasks.value.indexOf(taskId)
      if (index > -1) {
        selectedTasks.value.splice(index, 1)
      } else {
        selectedTasks.value.push(taskId)
      }
      
      // 更新全选状态
      selectAll.value = selectedTasks.value.length === filteredBadcases.value.length
    }
    
    const createNewBadcase = () => {
      // 新建也走工作区 Tab（不离开 ProjectDetail）
      const pid =
        selectedPlan.value && selectedPlan.value !== 'unplanned'
          ? typeof selectedPlan.value === 'number'
            ? selectedPlan.value
            : parseInt(String(selectedPlan.value), 10)
          : null
      openMainCreateEditor(currentPlanType.value, Number.isFinite(pid) ? pid : null)
    }

    // 编辑 BadCase/Bug/TestCase（统一入口）
    const editBadcase = (badcaseId) => {
      console.log('=== editBadcase函数被调用 ===')
      console.log('BadCase/Bug/TestCase ID:', badcaseId)
      console.log('项目ID:', projectId.value)

      // 统一改为主区域挂载编辑，避免 overlay 顶栏/布局重复
      openMainEditor(badcaseId, currentPlanType.value, false)
    }
    
    // 打开编辑覆盖层
    // 在主区域挂载 Editor（替代 overlay）
    const openMainEditor = (itemId, itemType, showDiff = false) => {
      console.log('[MAIN-EDITOR] 打开主区域编辑:', { itemId, itemType, showDiff })
      const et = mapToEditorPlanType(itemType)
      const returnTo = activeWorkbenchTabId.value
      const tid = `detail-${et}-${itemId}`
      const row = badcases.value.find((b) => b.id == itemId)
      const title = truncateForTab(row?.title, '编辑')
      upsertWorkbenchTab({
        id: tid,
        kind: 'detail',
        title,
        meta: { entityId: itemId, editorPlanType: et, showDiff: !!showDiff, returnTo }
      })
      activeWorkbenchTabId.value = tid
      mountEditorComponents(itemId, et, showDiff, true, null)
      console.log('[MAIN-EDITOR] 设置后 mainEditorItemId:', mainEditorItemId.value)
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

        // 先切换 active 到来源 Tab，让 closeWorkbenchTab 走“非 active 关闭”的分支
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
        if (field === '_target' || field === '_messageId') continue  // 跳过内部字段
        if (typeof value === 'object' && 'new' in value) {
          modifications[field] = value.new
          oldValues[field] = value.old
        } else {
          modifications[field] = value
        }
      }
      
      // ======== 乐观更新：立即更新 UI ========
      // 1. 立即更新本地数据
      const item = badcases.value.find(b => b.id === bugId)
      if (item) {
        for (const [field, value] of Object.entries(modifications)) {
          if (item.hasOwnProperty(field)) {
            item[field] = value
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
          message_id: modifyData._messageId
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
          }
          return result
        }
        console.error('[MODIFY] 后端修改失败，回滚 UI:', result.error)
        if (item) {
          for (const [field, value] of Object.entries(oldValues)) {
            if (item.hasOwnProperty(field)) {
              item[field] = value
            }
          }
        }
        pendingModifications.value[bugId] = modifyData
        return result
      })
      .catch((error) => {
        console.error('[MODIFY] 后端请求失败，回滚 UI:', error)
        if (item) {
          for (const [field, value] of Object.entries(oldValues)) {
            if (item.hasOwnProperty(field)) {
              item[field] = value
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
          if (field === '_target' || field === '_messageId') continue
          if (typeof value === 'object' && value !== null && 'new' in value) {
            modifications[field] = value.new
            oldValues[field] = value.old
          } else {
            modifications[field] = value
          }
        }
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
        modifications: s.modifications
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
          for (const [field, value] of Object.entries(s.modifications)) {
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
      if (!skipRestore) {
        await restorePendingDiffReviews()
      }
    }
    
    
    // 获取连续相邻的待修改记录组
    const getConsecutiveGroups = () => {
      const pendingIds = Object.keys(pendingModifications.value).map(Number)
      const result = []
      let currentGroup = []
      
      // 遍历 filteredBadcases 找出连续的待修改记录
      filteredBadcases.value.forEach((badcase, index) => {
        if (pendingIds.includes(badcase.id)) {
          currentGroup.push(badcase.id)
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
    
    // 判断是否是连续组的最后一个
    const isLastInConsecutiveGroup = (id) => {
      const groups = getConsecutiveGroups()
      for (const group of groups) {
        if (group[group.length - 1] === id) {
          return true
        }
      }
      return false
    }
    
    // 获取连续组的大小
    const getConsecutiveGroupSize = (id) => {
      const groups = getConsecutiveGroups()
      for (const group of groups) {
        if (group.includes(id)) {
          return group.length
        }
      }
      return 1
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
    
    // 获取记录所在的连续组
    const getConsecutiveGroup = (id) => {
      const groups = getConsecutiveGroups()
      for (const group of groups) {
        if (group.includes(id)) {
          return group
        }
      }
      return [id]
    }
    
    // 批量确认所有修改
    const confirmAllModify = async () => {
      const pendingIds = Object.keys(pendingModifications.value).map(Number)
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
      if (selectedPlan.value && selectedPlan.value !== 'unplanned') {
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
      } else if (selectedPlan.value === 'unplanned') {
        // 未计划 + Bug/测试用例/BadCase 专用接口已按类型筛好，勿再按 plan_id 过滤（否则带 plan_id 的项会被误清空）
        if (!urlContentType.value) {
          filtered = filtered.filter(b => !b.plan_id || b.plan_id === 0)
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
      // 子计划必须与父计划同一内容类型（BadCase / Bug / 测试用例）
      newPlan.contentType = plan.content_type || plan.plan_type || 'badcase'
      
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
      // 同级计划与当前所选计划同一内容类型
      newPlan.contentType = plan.content_type || plan.plan_type || 'badcase'
      
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
      newPlan.contentType = plan.content_type || plan.plan_type || 'badcase'  // 重要：从计划中加载 plan_type
      
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
      newPlan.cycle = 'one_week'
      newPlan.startDate = ''
      newPlan.endDate = ''
      newPlan.count = 1
      newPlan.name = ''
      newPlan.parentId = ''
      newPlan.description = ''
      newPlan.scopeNotification = false
      newPlan.statusType = 'in_progress'
      newPlan.contentType = 'badcase'
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
        // TODO: 调用API创建基线
        const baselineName = `基线_${new Date().toLocaleDateString()}`
        console.log('创建基线:', baselineName, '包含BadCase:', selectedBadcases.value)
        
        // 模拟创建成功
        const newBaseline = {
          id: Date.now(),
          name: baselineName,
          version: baselines.value.length + 1,
          created_at: new Date().toISOString(),
          badcase_count: selectedBadcases.value.length,
          plan_id: selectedBaselinePlan.value
        }
        
        baselines.value.unshift(newBaseline)
        selectedBadcases.value = []
        
        console.log(`基线创建成功！包含${newBaseline.badcase_count}个BadCase`)
      } catch (error) {
        console.error('创建基线失败:', error)
        console.error('错误详情:', error.message)
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
    
    const viewBaseline = (baselineId) => {
      // TODO: 实现查看基线详情
      console.log('查看基线详情功能开发中...')
    }
    
    const deleteBaseline = (baselineId) => {
      if (window.confirm(t('project.deleteBaselineConfirm'))) {
        const index = baselines.value.findIndex(b => b.id === baselineId)
        if (index > -1) {
          baselines.value.splice(index, 1)
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
        // TODO: 调用API获取基线列表
        // 模拟数据
        baselines.value = [
          {
            id: 1,
            name: '基线_v1.0',
            version: 1,
            created_at: '2025-08-15T10:00:00Z',
            badcase_count: 5,
            plan_id: 1
          },
          {
            id: 2,
            name: '基线_v1.1',
            version: 2,
            created_at: '2025-08-16T14:30:00Z',
            badcase_count: 8,
            plan_id: 1
          }
        ]
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
        } else {
          expandedSections.unplanned = true
          expandedUnplannedBadcase.value = true
          await fetchUnplannedBadcases(1)
        }
        
        // 确保有未计划的BadCase类型计划
        await ensureUnplannedBadcasePlan()
        
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
    
    const calculateEndDate = () => {
      if (!newPlan.startDate || !newPlan.count) return ''
      const start = new Date(newPlan.startDate)
      const end = new Date(start)
      end.setDate(start.getDate() + (newPlan.count * 7))
      return end.toISOString().split('T')[0]
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
          cycle: newPlan.cycle,
          start_date: newPlan.startDate,
          end_date: newPlan.endDate,
          count: newPlan.count,
          description: newPlan.description,
          scope_notification: newPlan.scopeNotification,
          parent_id: newPlan.parentId || null,
          project_id: projectId.value,
          // 计划状态类型和内容类型
          status_type: newPlan.statusType,
          plan_type: newPlan.contentType,  // 使用用户选择的内容类型
          status: 'active'       // 明确设置状态
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
    
    // 右侧对话框拖拽相关方法
    const startDragRightSidebar = (event) => {
      isDraggingRightSidebar.value = true
      dragStartX.value = event.clientX
      dragStartWidth.value = rightSidebarWidth.value
      
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
      
      const deltaX = dragStartX.value - event.clientX
      const newWidth = Math.max(200, Math.min(600, dragStartWidth.value + deltaX))
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
    
    const showTeamManagement = () => {
      showUserDropdown.value = false
      showTeamManagementModal.value = true
    }
    
    const showProjectSettings = () => {
      showProjectSettingsModal.value = true
    }
    
    const showPermissionSettings = () => {
      showPermissionSettingsModal.value = true
    }
    
    // 关闭配置模态框
    const closeConfigModals = () => {
      showTeamManagementModal.value = false
      showProjectSettingsModal.value = false
      showPermissionSettingsModal.value = false
    }
    
    // 用户下拉菜单相关方法
    const toggleUserDropdown = () => {
      showUserDropdown.value = !showUserDropdown.value
    }
    
    const showUserProfile = () => {
      showUserDropdown.value = false
      showProfileModal.value = true
    }

    const openPreferences = () => {
      showUserDropdown.value = false
      preferenceLocaleDraft.value = locale.value
      showPreferencesModal.value = true
    }

    const savePreferences = () => {
      persistLocale(preferenceLocaleDraft.value)
      showPreferencesModal.value = false
    }
    
    const showNotifications = () => {
      showUserDropdown.value = false
      // TODO: 实现通知页面
      alert(t('project.notificationsDev'))
    }
    
    const showHelp = () => {
      showUserDropdown.value = false
      // TODO: 实现帮助页面
      alert(t('project.helpDev'))
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
          
      // 监听 modify 显示事件
      window.addEventListener('show-modify-in-list', handleShowModifyInList)
                
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
      console.log('=== ProjectDetail onUnmounted ===')
      window.removeEventListener('grep-navigate', handleGrepNavigate)
      window.removeEventListener('show-modify-in-list', handleShowModifyInList)
      window.removeEventListener('clear-pending-modification', handleClearPendingModification)
      window.removeEventListener('modify-confirmed', handleModifyConfirmed)
      window.removeEventListener('modify-cancelled', handleModifyCancelled)
      window.removeEventListener('create-pending', handleCreatePending)
      window.removeEventListener('show-create-in-list', handleShowCreateInList)
    })

    const handleCreatePending = async (event) => {
      const detail = event?.detail || {}
      const target = detail.target
      const rawPreview = detail.preview
      const messageId = detail.messageId ?? null
      const hasStableMessageScope = messageId !== null && messageId !== undefined
      if (!target || !rawPreview) return
      const preview = { ...rawPreview }
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
        window.dispatchEvent(new CustomEvent('grep-navigate', {
          detail: { planId: pid, bugId: adoptedRowId, target: target || 'bug' },
          bubbles: true
        }))
        return
      }
      const createKey = makeCreateKey(target, preview, messageId)
      // 仅在带 messageId 时才应用“已处理”拦截；无 messageId 场景避免误吞新预览
      if (hasStableMessageScope && processedCreateKeyMap[createKey]) return
      // 生成临时 id
      const tempId = `create_${Date.now()}_${Math.random().toString(16).slice(2)}`
      pendingCreates.value = [
        ...pendingCreates.value.filter(x => x.createKey !== createKey),
        { tempId, target, preview, messageId, createdAt: Date.now(), createKey }
      ]
      const pPlan = preview.plan_id ?? preview.planId
      const pn = Number(pPlan)
      const tgt = (target || 'badcase').toString().toLowerCase()
      const uct =
        tgt === 'badcase' ? 'badcase' : tgt === 'testcase' || tgt === 'test_case' ? 'test_case' : 'bug'
      if (Number.isInteger(pn) && pn > 0) {
        expandPlanTreeToPlanId(pn)
        await upsertAndActivatePlanListTab({ planId: pn, urlContentType: uct })
      } else {
        await upsertAndActivatePlanListTab({ planId: null, urlContentType: uct })
      }

      // 轻量定位：滚动到该「待新增」行
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
    const scrollToCreatedListRow = async (createdId) => {
      if (createdId == null || createdId === '') return
      const id = Number(createdId)
      if (!Number.isFinite(id)) return
      const sel = `[data-bug-id="${id}"]`
      for (let attempt = 0; attempt < 12; attempt++) {
        await nextTick()
        await new Promise((r) => setTimeout(r, attempt === 0 ? 60 : 100))
        const el = document.querySelector(sel)
        if (el && el.scrollIntoView) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          el.classList.add('highlight-row')
          setTimeout(() => el.classList.remove('highlight-row'), 3000)
          return
        }
      }
      console.warn('[CREATE] 未找到列表行，无法滚动:', sel)
    }

    const confirmCreate = async (tempId) => {
      const item = pendingCreates.value.find(x => x.tempId === tempId)
      if (!item) return
      const target = item.target
      const preview = item.preview || {}
      const createKey = item.createKey || makeCreateKey(target, preview, item.messageId || null)
      // 先乐观移除
      pendingCreates.value = pendingCreates.value.filter(x => x.tempId !== tempId)
      try {
        let createdId = null
        if (target === 'testcase' || target === 'test_case') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/testcases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(preview)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建TestCase失败')
          createdId = res?.testcase?.id ?? res?.id ?? null
        } else if (target === 'bug') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/bugs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(preview)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建Bug失败')
          createdId = res?.bug?.id ?? res?.id ?? null
        } else if (target === 'badcase') {
          const res = await fetch(`${BACKEND_BASE_URL}/api/badcases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(preview)
          }).then(r => r.json())
          if (!res?.success) throw new Error(res?.error || '创建BadCase失败')
          createdId = res?.badcase?.id ?? res?.id ?? null
        }
        processedCreateKeyMap[createKey] = true
        createdIdByCreateKey[createKey] = createdId
        persistProcessedCreateKey(projectId.value, createKey, { createdId, target, messageId: item.messageId || null })
        persistStableCreatedId(projectId.value, target, preview, createdId)

        const targetPlanId = preview.plan_id ?? preview.planId
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
        } else {
          await refreshBadcases()
        }
        await fetchProjectPlans()
        if (createdId != null) {
          await scrollToCreatedListRow(createdId)
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
    const handleModifyConfirmed = (event) => {
      const { targetId } = event.detail
      console.log('[MODIFY] 收到 modify-confirmed 事件:', targetId)
      
      // 清除 pendingModifications 中的标记
      const newPending = { ...pendingModifications.value }
      delete newPending[targetId]
      pendingModifications.value = newPending
      console.log('[MODIFY] 已清除 pendingModifications:', pendingModifications.value)
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
      for (const pid of ids) {
        const existing = next[pid]
        const realKeys = existing ? Object.keys(existing).filter((k) => !k.startsWith('_')) : []
        if (realKeys.length === 0) {
          next[pid] = { ...source }
        }
      }
      pendingModifications.value = next
    }

    /** 与 handleShowModifyInList 内逻辑一致，供批量同步写入 pending 时复用 */
    const buildModifyDataFromShowModifyDetail = (detail) => {
      const modifyData = {}
      const diff = detail?.diff
      const modifications = detail?.modifications
      if (diff && Array.isArray(diff) && diff.length > 0) {
        diff.forEach((fieldDiff) => {
          const rawField = fieldDiff.field ?? fieldDiff.field_label
          const fieldKey = normalizeDiffFieldKey(rawField)
          const oldLine = fieldDiff.lines?.find((l) => l.type === 'delete')
          const newLine = fieldDiff.lines?.find((l) => l.type === 'add')
          const unchangedLine = fieldDiff.lines?.find((l) => l.type === 'unchanged')
          if (oldLine && newLine) {
            modifyData[fieldKey] = { old: oldLine.content, new: newLine.content }
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
            modifyData[fk] = value
          } else {
            modifyData[fk] = { old: '', new: value }
          }
        }
      }
      return modifyData
    }

    /** 同步写入一条待确认（不 await），避免同组多条 async 交错导致黄条逐个出现 */
    const syncApplyShowModifyListPendingFromDetail = (detail, opts = {}) => {
      const writeSession = opts.sessionStorageWrite === true
      if (detail.executed === true) return
      const modifyData = buildModifyDataFromShowModifyDetail(detail)
      const fieldKeys = Object.keys(modifyData)
      if (fieldKeys.length === 0) return
      const hasDetailFields = fieldKeys.some((field) =>
        DETAIL_FIELDS.includes(normalizeDiffFieldKey(field))
      )
      const allListFields = fieldKeys.every((field) =>
        LIST_FIELDS.includes(normalizeDiffFieldKey(field))
      )
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

      if (diff && Array.isArray(diff) && diff.length > 0 && allListFields && !hasDetailFields) {
        const newModifyData = {
          ...Object.fromEntries(
            fieldKeys.map((field) => {
              const v = modifyData[field]
              return [field, typeof v === 'object' && v && 'new' in v ? v : { old: '', new: v }]
            })
          ),
          _target: target,
          _messageId: messageId
        }
        const next = { ...pendingModifications.value }
        next[intTargetId] = { ...(next[intTargetId] || {}), ...newModifyData }
        pendingModifications.value = next
      }
    }

    const handleShowModifyInList = async (event) => {
          const dtop = event.detail || {}
          if (dtop.__modifyListBatch === true && Array.isArray(dtop.items) && dtop.items.length > 0) {
            const items = dtop.items
            for (let i = 0; i < items.length; i++) {
              if (items[i].executed === true) continue
              syncApplyShowModifyListPendingFromDetail(items[i], { sessionStorageWrite: i === 0 })
            }
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
          const { targetId, target, diff, modifications, plan_id, executed, messageId, batchIndex, peerTargetIds, suppressAutoOpenDetail } = event.detail
          const intTargetId = parseInt(targetId)

          if (dtop.__pendingSyncedBatch === true) {
            const modifyDataPre = buildModifyDataFromShowModifyDetail(dtop)
            const fieldKeysPre = Object.keys(modifyDataPre)
            const hasDetailFieldsPre = fieldKeysPre.some((field) =>
              DETAIL_FIELDS.includes(normalizeDiffFieldKey(field))
            )
            if (
              diff &&
              Array.isArray(diff) &&
              diff.length > 0 &&
              hasDetailFieldsPre &&
              suppressAutoOpenDetail !== true
            ) {
              openMainEditor(intTargetId, target, true)
              return
            }
            if (target === 'bug') {
              urlContentType.value = 'bug'
            } else if (target === 'badcase') {
              urlContentType.value = 'badcase'
            } else if (target === 'testcase') {
              urlContentType.value = 'test_case'
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
              const item = badcases.value.find((b) => b.id == intTargetId)
              if (item) {
                targetPlanId = item.plan_id
              } else {
                const oldSelectedPlan = selectedPlan.value
                selectedPlan.value = null
                await fetchBadcases(1)
                await nextTick()
                const newItem = badcases.value.find((b) => b.id == intTargetId)
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
            const uctForNav =
              target === 'bug' ? 'bug' : target === 'testcase' ? 'test_case' : 'badcase'
            const navMeta = targetPlanId
              ? { planId: targetPlanId, urlContentType: uctForNav }
              : { planId: null, urlContentType: uctForNav }
            let listLoadedByTabNavigation = false
            if (suppressAutoOpenDetail === true) {
              if (targetPlanId) selectedPlan.value = targetPlanId
              else selectedPlan.value = null
            } else {
              await upsertAndActivatePlanListTab(navMeta)
              listLoadedByTabNavigation = true
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
            highlightRowId.value = intTargetId
            const rowSel = `[data-bug-id="${intTargetId}"]`
            let targetRow = null
            for (let i = 0; i < 12; i++) {
              await nextTick()
              await new Promise((resolve) => setTimeout(resolve, i === 0 ? 280 : 130))
              targetRow = document.querySelector(rowSel)
              if (targetRow) break
            }
            if (targetRow) {
              targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' })
              targetRow.classList.add('highlight-row')
              setTimeout(() => targetRow.classList.remove('highlight-row'), 3000)
            }
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
              
          // 构造待修改数据结构
          const modifyData = {}
          
          // 优先使用 diff，如果没有 diff 则从 modifications 生成
          if (diff && Array.isArray(diff) && diff.length > 0) {
            console.log('[MODIFY] 使用 diff 构造 modifyData, diff.length:', diff.length)
            diff.forEach(fieldDiff => {
              const rawField = fieldDiff.field ?? fieldDiff.field_label
              const fieldKey = normalizeDiffFieldKey(rawField)
              console.log('[MODIFY] diff 字段:', rawField, '-> key:', fieldKey)
              const oldLine = fieldDiff.lines?.find(l => l.type === 'delete')
              const newLine = fieldDiff.lines?.find(l => l.type === 'add')
              const unchangedLine = fieldDiff.lines?.find(l => l.type === 'unchanged')
              
              if (oldLine && newLine) {
                modifyData[fieldKey] = {
                  old: oldLine.content,
                  new: newLine.content
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
            console.log('[MODIFY] 使用 modifications 构造 modifyData')
            for (const [field, value] of Object.entries(modifications)) {
              const fk = normalizeDiffFieldKey(field)
              if (value && typeof value === 'object' && 'new' in value) {
                modifyData[fk] = value
              } else {
                modifyData[fk] = {
                  old: '',
                  new: value
                }
              }
            }
          }
          
          console.log('[MODIFY] 构造后的 modifyData:', modifyData)
          const fieldKeys = Object.keys(modifyData)
          console.log('[MODIFY] modifyData 的 keys:', fieldKeys)

          // 是否包含详情字段（只能在详情页编辑）；assignee_id 按 assignee 视为列表字段
          const hasDetailFields = fieldKeys.some(field => {
            const normalized = normalizeDiffFieldKey(field)
            return DETAIL_FIELDS.includes(normalized)
          })

          // 是否全部都是列表字段（可只在列表展示 diff，跳转列表不高亮详情）
          const allListFields = fieldKeys.length > 0 && fieldKeys.every(field => {
            const normalized = normalizeDiffFieldKey(field)
            return LIST_FIELDS.includes(normalized)
          })

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

            // 如果都是列表字段（例如标题/状态/优先级/负责人），只跳到列表并高亮那一行，不打开编辑详情
            if (allListFields && !hasDetailFields) {
              console.log('[MODIFY] 仅列表字段修改，跳转列表并高亮行，不打开详情')
              // 只有在「尚未采纳」（executed === false）时，才在列表上展示 diff
              // 一旦采纳成功（executed === true），列表应只显示最新值，不再有黄色 diff 行
              if (!executed) {
                const newModifyData = {
                  ...Object.fromEntries(
                    fieldKeys.map(field => {
                      const v = modifyData[field]
                      return [field, typeof v === 'object' && 'new' in v ? v : { old: '', new: v }]
                    })
                  ),
                  _target: target,
                  _messageId: messageId
                }
                const next = { ...pendingModifications.value }
                next[intTargetId] = {
                  ...(next[intTargetId] || {}),
                  ...newModifyData
                }
                pendingModifications.value = next
                if (peerTargetIds && Array.isArray(peerTargetIds) && peerTargetIds.length >= 2) {
                  applyPeerPendingSync(intTargetId, peerTargetIds)
                }
              } else {
                // executed === true：若列表上还有残留的 pendingModifications，清理掉
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
              }
              highlightRowId.value = intTargetId
              // 下面已有的 plan_id 推导和 fetchBadcases 逻辑会负责切计划和刷新列表
            } else {
              // 包含详情字段：需要在详情页里编辑
              if (suppressAutoOpenDetail === true) {
                console.log('[MODIFY] 自动同步链路，抑制详情自动打开，仅同步列表状态')
              } else {
                console.log('[MODIFY] 包含详情字段，打开编辑详情页')
                openMainEditor(intTargetId, target, true)
                return
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
          
          // 方式 3: 从当前列表中查找
          if (!targetPlanId) {
            const item = badcases.value.find(b => b.id == intTargetId)
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
              const newItem = badcases.value.find(b => b.id == intTargetId)
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
          
          // 按文档统一走 Tab 导航：目标不在当前 Tab 时，激活已有或新建对应 Tab
          const uctForNav =
            target === 'bug' ? 'bug' : target === 'testcase' ? 'test_case' : 'badcase'
          const navMeta = targetPlanId
            ? { planId: targetPlanId, urlContentType: uctForNav }
            : { planId: null, urlContentType: uctForNav }

          let listLoadedByTabNavigation = false
          if (suppressAutoOpenDetail === true) {
            console.log('[MODIFY] 自动同步链路，跳过重复 Tab 激活，避免循环触发')
            // 当前链路通常已在目标 Tab；仅兜底维护 selectedPlan
            if (targetPlanId) selectedPlan.value = targetPlanId
            else selectedPlan.value = null
          } else {
            await upsertAndActivatePlanListTab(navMeta)
            listLoadedByTabNavigation = true
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
            const modifyDataLocal = {}
            
            // 优先使用 diff，如果没有 diff 则从 modifications 生成
            if (diff && Array.isArray(diff)) {
              diff.forEach(fieldDiff => {
                const rawField = fieldDiff.field ?? fieldDiff.field_label
                const fieldKey = normalizeDiffFieldKey(rawField)
                const oldLine = fieldDiff.lines?.find(l => l.type === 'delete')
                const newLine = fieldDiff.lines?.find(l => l.type === 'add')
                const unchangedLine = fieldDiff.lines?.find(l => l.type === 'unchanged')
                if (oldLine && newLine) {
                  modifyDataLocal[fieldKey] = { old: oldLine.content, new: newLine.content }
                } else if (unchangedLine) {
                  modifyDataLocal[fieldKey] = {
                    old: unchangedLine.content,
                    new: unchangedLine.content,
                    unchanged: true
                  }
                }
              })
            } else if (modifications && typeof modifications === 'object') {
              for (const [field, value] of Object.entries(modifications)) {
                const fieldKey = normalizeDiffFieldKey(field)
                modifyDataLocal[fieldKey] = { old: '', new: value }
              }
            }
            
            if (Object.keys(modifyDataLocal).length > 0) {
              modifyDataLocal._target = target  // 保存目标类型
              pendingModifications.value = {
                ...pendingModifications.value,
                [intTargetId]: modifyDataLocal
              }
              console.log('[MODIFY] setupPendingModifications 设置 pendingModifications:', pendingModifications.value)
            }
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
          const rowSel = `[data-bug-id="${intTargetId}"]`
          let targetRow = null
          for (let i = 0; i < 12; i++) {
            await nextTick()
            await new Promise((resolve) => setTimeout(resolve, i === 0 ? 280 : 130))
            targetRow = document.querySelector(rowSel)
            if (targetRow) break
          }
          console.log('[MODIFY] 查找目标行:', rowSel, targetRow)
          if (targetRow) {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' })
            targetRow.classList.add('highlight-row')
            setTimeout(() => targetRow.classList.remove('highlight-row'), 3000)
          }
        }
        
        const handleGrepNavigate = async (event) => {
      const detail = event.detail || {}
      const rawPlanId = detail.planId
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
      console.log('[GREP-NAV] 收到导航指令:', {
        rawPlanId,
        recordId,
        recordIdsBatch,
        bugId: detail.bugId,
        target
      })

      const uctFromTarget =
        target === 'badcase' ? 'badcase' : target === 'testcase' ? 'test_case' : 'bug'

      let meta = null
      if (rawPlanId === 'unplanned') {
        meta = { planId: 'unplanned', urlContentType: null }
      } else if (rawPlanId != null && rawPlanId !== '') {
        const n = typeof rawPlanId === 'number' ? rawPlanId : parseInt(String(rawPlanId), 10)
        if (!Number.isNaN(n) && n > 0) {
          expandPlanTreeToPlanId(n)
          meta = { planId: n, urlContentType: uctFromTarget }
        }
      }
      if (!meta) {
        meta = { planId: null, urlContentType: uctFromTarget }
      }

      await upsertAndActivatePlanListTab(meta)

      await nextTick()

      /** 批量列表定位：同一次闪动多条，避免逐条 dispatch 造成一行行动画 */
      if (recordIdsBatch && recordIdsBatch.length > 0 && !openDetail) {
        let anyEl = null
        for (let i = 0; i < 12; i++) {
          await nextTick()
          await new Promise((r) => setTimeout(r, i === 0 ? 400 : 130))
          anyEl = document.querySelector(`[data-bug-id="${recordIdsBatch[0]}"]`)
          if (anyEl) break
        }
        if (anyEl) {
          anyEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        for (const id of recordIdsBatch) {
          const el = document.querySelector(`[data-bug-id="${id}"]`)
          if (el) {
            el.classList.add('highlight-flash')
            setTimeout(() => el.classList.remove('highlight-flash'), 2000)
          }
        }
        return
      }

      if (recordId != null && recordId !== '') {
        if (openDetail) {
          console.log('[GREP-NAV] 详情上下文命中，打开/激活详情 Tab')
          openMainEditor(recordId, target, false)
          return
        }
        const sel = `[data-bug-id="${recordId}"]`
        let bugElement = null
        for (let i = 0; i < 12; i++) {
          await nextTick()
          await new Promise((r) => setTimeout(r, i === 0 ? 400 : 130))
          bugElement = document.querySelector(sel)
          if (bugElement) break
        }
        console.log('[GREP-NAV] 查找列表行元素:', bugElement, sel)
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
      projectName,
      projectId,
      planSearchText,
      showOnlyMine,
      includeSubPlans,
      expandedSections,
      expandedUnplannedBadcase,
      selectedPlan,
      selectAll,
      selectedTasks,
      projectPlans,
      filteredPlans,
      badcases,
      unplannedBadcaseCount,
      inProgressPlans,
      unplannedPlans,
      archivedPlans,
      filteredBadcases,
      badcaseLoading,
      totalBadcases,
      loading,
      planTestCaseCounts,
      hoveredPlan,
      contextMenu,
      planCollapsed,
      expandedPlans,
      showCreateModal,
      showTeamManagementModal,
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
      isUnplannedTypeChipActive,
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
      embeddedEditorKind,
      mainEditorCacheKey,
      listPanelCacheKey,
      workbenchTabs,
      workbenchTabsForMoreMenu,
      activeWorkbenchTabId,
      workbenchMenuRef,
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
      toggleUnplannedBadcaseSection,
      selectPlan,
      selectUnplanned,
      selectUnplannedBadcase,
      selectUnplannedType,
      selectBadcasePlan,
      createPlanForBadcase,
      associateBadcaseWithPlan,
      filterBadcasesByPlan,
      toggleSelectAll,
      toggleTaskSelection,
      createNewBadcase,
      editBadcase,
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
      calculateEndDate,
      createPlan,
      fetchBadcases,
      fetchUnplannedBadcases,
      refreshBadcases,
      getBadcaseStatusText,
      getBadcaseTypeText,
      getBadcaseBackgroundClass,
      getBadcaseIcon,
      acceptBadcase,
      rejectBadcase,
      getPlanIcon,
      getPlanTypeText,
      ensureUnplannedBadcasePlan,
      createUnplannedBadcasePlan,
      getAssigneeDisplayText,
      confirmModify,  // 新增：确认修改
      cancelModify,   // 新增：取消修改
      isLastInConsecutiveGroup,  // 新增：判断是否是连续组的最后一个
      getConsecutiveGroupSize,   // 新增：获取连续组大小
      confirmConsecutiveGroup,   // 新增：确认连续组
      cancelConsecutiveGroup,    // 新增：取消连续组
      // 新增搜索和筛选相关
      searchText,
      selectedAssignee,
      selectedStatus,
      projectMembers,
      applyFilters,
      fetchProjectMembers,
      generateBreadcrumb,
      togglePlanExpansion,
      showTeamManagement,
      showProjectSettings,
      showPermissionSettings,
      closeConfigModals,
      showUserDropdown,
      currentUser,
      toggleUserDropdown,
      showUserProfile,
      showProfileModal,
      showPreferencesModal,
      preferenceLocaleDraft,
      openPreferences,
      savePreferences,
      t,
      showNotifications,
      showHelp,
      logout,
      showTerminal,
      showAIAssistant,
      setLayout,
      planCollapsed,
      leftSidebarHidden,
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
      // Grep导航
      handleGrepNavigate
    }
  }
}
</script>

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

/* 主容器 */
.main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 左侧导航栏 */
.left-sidebar {
  display: flex;
  width: 300px;
  background: #fff;
  border-right: 1px solid #e9ecef;
  transition: all 0.3s ease;
}

.left-sidebar.collapsed {
  width: 60px;
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
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  min-height: 32px;
  gap: 8px;
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
  width: 24px;
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
  padding: 0;
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

.plan-item.unplanned {
  color: #666;
}

.plan-item.unplanned.active {
  background: #e3f2fd;
  color: #1976d2;
  border-left: 3px solid #ff9800;
}

.plan-item.unplanned {
  margin-left: 0;
  border-left: 3px solid #ff9800;
}

.unplanned-badcase-section {
  margin: 0;
  padding: 0;
}

.unplanned-type-section {
  margin: 8px 0;
  padding: 4px 0;
}

.unplanned-type-section .type-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
  color: #666;
  background: transparent;
  margin-bottom: 2px;
}

.unplanned-type-section .type-item:hover {
  background: #e9ecef;
}

.unplanned-type-section .type-item.active {
  background: #e3f2fd;
  color: #1976d2;
  border-left: 3px solid #1976d2;
}

.unplanned-type-section .type-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.unplanned-type-section .type-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.unplanned-badcase-section .section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.2s;
  color: #666;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  margin-bottom: 8px;
}

.unplanned-badcase-section .section-header:hover {
  background: #e9ecef;
  border-color: #dee2e6;
}

.unplanned-badcase-section .section-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.unplanned-badcase-section .section-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.unplanned-badcase-section .expand-arrow {
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
  width: 16px;
  text-align: center;
}

.unplanned-badcase-section .expand-arrow.expanded {
  transform: rotate(90deg);
}

        .unplanned-badcase-section .section-content {
          margin-left: 0;
          border-left: none;
          padding-left: 0;
          margin-top: 8px;
          padding: 12px;
          text-align: center;
          color: #666;
          font-size: 14px;
        }

        .unplanned-badcase-section .empty-state {
          padding: 20px;
          text-align: center;
          color: #999;
          font-size: 13px;
        }

        .unplanned-badcase-section .empty-text {
          font-style: italic;
        }

.unplanned-badcase-section .badcase-list {
  margin-top: 8px;
}

.unplanned-badcase-section .badcase-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.3s ease;
  margin-bottom: 6px;
  border: 1px solid transparent;
  position: relative;
  overflow: hidden;
}

.unplanned-badcase-section .badcase-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
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

.unplanned-badcase-section .badcase-icon {
  font-size: 12px;
  width: 14px;
  text-align: center;
}

.unplanned-badcase-section .badcase-title {
  flex: 1;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.unplanned-badcase-section .badcase-status {
  font-size: 11px;
  padding: 2px 6px;
  background: #f0f0f0;
  border-radius: 8px;
  color: #666;
}

.plan-item.parent-plan {
  border-left: 3px solid #2196f3;
}

.plan-item.child-plan {
  border-left: 3px solid #ff9800;
}

.plan-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.plan-name {
  flex: 1;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
  cursor: pointer;
  width: 16px;
  text-align: center;
}

.expand-arrow:hover {
  color: #666;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 16px;
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

.count-badge.unplanned {
  background: #f8f9fa;
  color: #6c757d;
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
  margin-left: 16px;
  margin-top: 4px;
}

.sub-plan {
  padding: 8px 12px;
  font-size: 13px;
  border-bottom: 1px solid #f8f8f8;
}

.sub-plan .plan-icon {
  font-size: 14px;
}

.sub-plan .plan-name {
  font-size: 13px;
}

.sub-plan-list.level-2 {
  margin-left: 16px;
}

.sub-plan.level-2 {
  padding: 6px 12px;
  font-size: 12px;
}

.sub-plan.level-2 .plan-icon {
  font-size: 13px;
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

/* 上下文菜单：顶栏可拖动，下方列表过高时内部滚动 */
.context-menu {
  position: fixed;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  max-height: min(85vh, 520px);
  min-width: 180px;
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.context-menu.is-dragging {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.context-menu-drag-handle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 12px;
  color: #666;
  background: linear-gradient(180deg, #f8f9fa 0%, #f0f2f5 100%);
  border-bottom: 1px solid #e9ecef;
  cursor: grab;
  user-select: none;
}

.context-menu.is-dragging .context-menu-drag-handle {
  cursor: grabbing;
}

.drag-grip {
  letter-spacing: -2px;
  opacity: 0.6;
}

.drag-label {
  font-weight: 500;
}

.context-menu-body {
  flex: 1;
  min-height: 0;
  max-height: min(60vh, 380px);
  overflow-x: hidden;
  overflow-y: auto;
  padding: 4px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: background-color 0.2s;
}

.menu-item:hover {
  background: #f8f9fa;
}

.menu-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.menu-separator {
  height: 1px;
  background: #e9ecef;
  margin: 4px 0;
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
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s ease;
  margin-bottom: 8px;
}

.plan-item:hover {
  background: #f8f9fa;
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

/* 当左侧边栏存在时，调整底部面板的左边距 */
.bottom-panel.with-left-sidebar {
  left: 300px;
}

/* 当左侧边栏折叠时，调整底部面板的左边距 */
.bottom-panel.with-collapsed-sidebar {
  left: 60px;
}

/* 底部面板的右边距通过内联样式动态设置 */

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
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
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
  overflow-x: auto;
  flex: 1;
}

.ai-tab {
  position: relative;
  padding: 6px 12px 6px 16px;
  background: #1e1e1e;
  border-radius: 4px 4px 0 0;
  font-size: 12px;
  color: #888;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  min-width: 120px;
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.prefs-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 12000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.prefs-modal {
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  min-width: 320px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.prefs-modal-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.prefs-lang-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  color: #555;
}

.prefs-lang-select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  margin-bottom: 20px;
}

.prefs-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.prefs-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #ddd;
  background: #fff;
}

.prefs-btn-save {
  background: #007bff;
  color: #fff;
  border-color: #007bff;
}
</style> 
