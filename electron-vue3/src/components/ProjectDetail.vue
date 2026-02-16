<template>
  <div class="project-detail-wrapper">
    <!-- 顶部导航栏 -->
    <div class="top-bar">
              <div class="top-left">
                 <div class="logo" @click="goToDashboard" style="cursor: pointer;">
           <span class="logo-text">BadCase Doctor</span>
           <span class="star-icon">⭐</span>
         </div>
                 <div class="breadcrumb">
           <span class="breadcrumb-item">{{ projectName }}</span>
           <span class="breadcrumb-separator">/</span>
           <span class="breadcrumb-item">迭代管理</span>
           <span class="dropdown-arrow">▼</span>
         </div>
        <span class="edit-permission">编辑权限</span>
      </div>
      
      <div class="top-right">
        <!-- 布局控制按钮组 -->
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
          
          <!-- 用户下拉菜单 -->
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

    <div class="main-container">
      <!-- 左侧导航栏 -->
      <div class="left-sidebar" :class="{ 'collapsed': planCollapsed }" v-show="!leftSidebarHidden">
       
       
      
        
        
        <div class="sidebar-content" v-show="!planCollapsed">
          <div class="sidebar-header">
            <div class="header-top">
              <h3>迭代计划</h3>
                            <div class="header-actions">
                <button class="action-icon-btn" @click="manualRefreshPlans" title="刷新所有数据">
                  <span class="icon">🔄</span>
                </button>
                <button class="action-icon-btn" @click="showCreatePlanModal" title="新增计划">
                  <span class="icon">➕</span>
                </button>
                <button class="action-icon-btn" @click="showBaselineManagement" title="基线管理">
                  <span class="icon">📋</span>
                </button>
              
              </div>
            </div>
            <div class="search-section">
              <input 
                type="text" 
                v-model="planSearchText"
                placeholder="输入计划名称"
                class="plan-search-input"
                @keyup.enter="searchPlans"
              />
              <button class="search-btn" @click="searchPlans">
                <span class="search-icon">🔍</span>
              </button>
              <button v-if="planSearchText" class="clear-search-btn" @click="clearSearch" title="清除搜索">
                <span class="clear-icon">✕</span>
              </button>
            </div>
          </div>
          
          <div class="plan-tree">
            <div class="plan-section">
              <div class="section-header" @click="toggleSection('unplanned')">
                <span class="section-icon">📄</span>
                <span class="section-title">未计划的卡片</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.unplanned }">▶</span>
            </div>
            
              <div v-if="expandedSections.unplanned" class="section-content">
                <!-- 未计划卡片的badcase目录结构 -->
                <div class="unplanned-badcase-section">
                  <div class="section-header" @click="selectUnplannedBadcase">
                    <span class="section-icon">📋</span>
                    <span class="section-title">BadCase</span>
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
                        @click.stop="togglePlanExpansion(plan.id)"
                      >▶</span>
                      <span v-else class="expand-placeholder"></span>
                      <span class="plan-icon">{{ getPlanIcon(plan.content_type || plan.plan_type || 'badcase') }}</span>
                      <span class="plan-name">
                        {{ plan.name }}
                        <span v-if="plan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                      </span>
                      <span class="plan-info">
                        <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                        <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
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
                <span class="section-title">进行中计划</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.inProgress }">▶</span>
              </div>
              
              <div v-if="expandedSections.inProgress" class="section-content">
                <div v-if="loading" class="loading-state">
                  <span class="loading-text">加载中...</span>
                </div>
                
                <div v-else-if="inProgressPlans.length === 0" class="empty-state">
                  <span class="empty-text">暂无进行中计划</span>
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
                          @click.stop="togglePlanExpansion(plan.id)"
                        >▶</span>
                        <span v-else class="expand-placeholder"></span>
                        <span class="plan-icon">{{ getPlanIcon(plan.content_type || 'badcase') }}</span>
                        <span class="plan-name">
                          {{ plan.name }}
                          <span v-if="plan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                        </span>
                        <span class="plan-info">
                          <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                          <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
                        </span>
                        
                        <!-- 操作按钮 -->
                        <div v-show="hoveredPlan === plan.id" class="plan-actions">
                          <button class="action-btn" @click.stop="showContextMenu(plan, $event)">
                            ⚙️
                          </button>
                        </div>
                        
                        <!-- 上下文菜单 -->
                        <div 
                          v-if="contextMenu.visible && contextMenu.planId === plan.id"
                          class="context-menu"
                          :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                        >
                          <div class="menu-item" @click="createSubPlan(plan)">
                            <span class="menu-icon">➕</span>
                            <span>新建子计划</span>
                          </div>
                          <div class="menu-item" @click="createSiblingPlan(plan)">
                            <span class="menu-icon">📝</span>
                            <span>新建同级计划</span>
                          </div>
                          <div class="menu-item" @click="editPlan(plan)">
                            <span class="menu-icon">✏️</span>
                            <span>编辑</span>
                          </div>
                          <div class="menu-item" @click="archivePlan(plan)">
                            <span class="menu-icon">📦</span>
                            <span>归档</span>
                          </div>
                          <div class="menu-item" @click="deletePlan(plan)">
                            <span class="menu-icon">🗑️</span>
                            <span>删除</span>
                          </div>
                          <div class="menu-item" @click="pinPlan(plan)">
                            <span class="menu-icon">📌</span>
                            <span>{{ plan.is_pinned ? '取消置顶' : '置顶' }}</span>
                          </div>
                          <div class="menu-item" @click="favoritePlan(plan)">
                            <span class="menu-icon">⭐</span>
                            <span>收藏</span>
                          </div>
                          <div class="menu-separator"></div>
                          <div class="menu-item" @click="createBaseline(plan)">
                            <span class="menu-icon">📋</span>
                            <span>新建基线</span>
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
                              @click.stop="togglePlanExpansion(childPlan.id)"
                            >▶</span>
                            <span v-else class="expand-placeholder"></span>
                            <span class="plan-icon">{{ getPlanIcon(childPlan.content_type || childPlan.plan_type || 'badcase') }}</span>
                            <span class="plan-name">
                              {{ childPlan.name }}
                              <span v-if="childPlan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                            </span>
                            <span class="plan-info">
                              <span v-if="childPlan.badcase_count > 0" class="count-badge badcase">{{ childPlan.badcase_count }}</span>
                              <span v-if="childPlan.bug_count > 0" class="count-badge bug">{{ childPlan.bug_count }}</span>
                            </span>
                            
                            <!-- 操作按钮 -->
                            <div v-show="hoveredPlan === childPlan.id" class="plan-actions">
                              <button class="action-btn" @click.stop="showContextMenu(childPlan, $event)">
                                ⚙️
                              </button>
                            </div>
                            
                            <!-- 上下文菜单 -->
                            <div 
                              v-if="contextMenu.visible && contextMenu.planId === childPlan.id"
                              class="context-menu"
                              :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                            >
                              <div class="menu-item" @click="createSubPlan(childPlan)">
                                <span class="menu-icon">➕</span>
                                <span>新建子计划</span>
                              </div>
                              <div class="menu-item" @click="createSiblingPlan(childPlan)">
                                <span class="menu-icon">📝</span>
                                <span>新建同级计划</span>
                              </div>
                              <div class="menu-item" @click="editPlan(childPlan)">
                                <span class="menu-icon">✏️</span>
                                <span>编辑</span>
                              </div>
                              <div class="menu-item" @click="archivePlan(childPlan)">
                                <span class="menu-icon">📦</span>
                                <span>归档</span>
                              </div>
                              <div class="menu-item" @click="deletePlan(childPlan)">
                                <span class="menu-icon">🗑️</span>
                                <span>删除</span>
                              </div>
                              <div class="menu-item" @click="pinPlan(childPlan)">
                                <span class="menu-icon">📌</span>
                                <span>{{ childPlan.is_pinned ? '取消置顶' : '置顶' }}</span>
                              </div>
                              <div class="menu-item" @click="favoritePlan(childPlan)">
                                <span class="menu-icon">⭐</span>
                                <span>收藏</span>
                              </div>
                              <div class="menu-separator"></div>
                              <div class="menu-item" @click="createBaseline(childPlan)">
                                <span class="menu-icon">📋</span>
                                <span>新建基线</span>
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
                                <span v-if="grandChildPlan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                              </span>
                              <span class="plan-info">
                                <span v-if="grandChildPlan.badcase_count > 0" class="count-badge badcase">{{ grandChildPlan.badcase_count }}</span>
                                <span v-if="grandChildPlan.bug_count > 0" class="count-badge bug">{{ grandChildPlan.bug_count }}</span>
                              </span>
                              
                              <!-- 操作按钮 -->
                              <div v-show="hoveredPlan === grandChildPlan.id" class="plan-actions">
                                <button class="action-btn" @click.stop="showContextMenu(grandChildPlan, $event)">
                                  ⚙️
                                </button>
                              </div>
                              
                              <!-- 上下文菜单 -->
                              <div 
                                v-if="contextMenu.visible && contextMenu.planId === grandChildPlan.id"
                                class="context-menu"
                                :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
                              >
                                <div class="menu-item" @click="createSubPlan(grandChildPlan)">
                                  <span class="menu-icon">➕</span>
                                  <span>新建子计划</span>
                                </div>
                                <div class="menu-item" @click="createSiblingPlan(grandChildPlan)">
                                  <span class="menu-icon">📝</span>
                                  <span>新建同级计划</span>
                                </div>
                                <div class="menu-item" @click="editPlan(grandChildPlan)">
                                  <span class="menu-icon">✏️</span>
                                  <span>编辑</span>
                                </div>
                                <div class="menu-item" @click="archivePlan(grandChildPlan)">
                                  <span class="menu-icon">📦</span>
                                  <span>归档</span>
                                </div>
                                <div class="menu-item" @click="deletePlan(grandChildPlan)">
                                  <span class="menu-icon">🗑️</span>
                                  <span>删除</span>
                                </div>
                                <div class="menu-item" @click="pinPlan(grandChildPlan)">
                                  <span class="menu-icon">📌</span>
                                  <span>{{ grandChildPlan.is_pinned ? '取消置顶' : '置顶' }}</span>
                                </div>
                                <div class="menu-item" @click="favoritePlan(grandChildPlan)">
                                  <span class="menu-icon">⭐</span>
                                  <span>收藏</span>
                                </div>
                                <div class="menu-separator"></div>
                                <div class="menu-item" @click="createBaseline(grandChildPlan)">
                                  <span class="menu-icon">📋</span>
                                  <span>新建基线</span>
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
                <span class="section-title">已归档计划</span>
                <span class="expand-arrow" :class="{ 'expanded': expandedSections.archived }">▶</span>
              </div>
              
              <div v-if="expandedSections.archived" class="section-content">
                <div v-if="loading" class="loading-state">
                  <span class="loading-text">加载中...</span>
            </div>
                
                <div v-else-if="archivedPlans.length === 0" class="empty-state">
                  <span class="empty-text">暂无已归档计划</span>
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
                          <span v-if="plan.is_pinned" class="pin-indicator" title="已置顶">📌</span>
                        </span>
                        <span class="plan-info">
                          <span v-if="plan.badcase_count > 0" class="count-badge badcase">{{ plan.badcase_count }}</span>
                          <span v-if="plan.bug_count > 0" class="count-badge bug">{{ plan.bug_count }}</span>
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
        <div class="content-header">
          <div class="content-title">
            <span>{{ generateBreadcrumb() }}</span>
            <span class="completion-rate">{{ filteredBadcases.length }}/{{ totalBadcases }}</span>
          </div>
        </div>
        
        <div class="content-toolbar">
          <div class="toolbar-left">
            <button @click="createNewBadcase" class="quick-create-btn">
              +快速新建{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}
            </button>
          </div>
          
          <div class="toolbar-right">
            <!-- 搜索输入框 -->
            <div class="search-input-container">
              <input 
                type="text" 
                v-model="searchText"
                placeholder="搜索标题或负责人..."
                class="search-input"
                @input="applyFilters"
                @keyup.enter="applyFilters"
              />
              <span class="search-icon">🔍</span>
            </div>
            
            <!-- 负责人筛选下拉框 -->
            <div class="filter-dropdown">
              <select v-model="selectedAssignee" @change="applyFilters" class="filter-select">
                <option value="">全部负责人</option>
                <option value="mine">只看自己</option>
                <option v-for="member in projectMembers" :key="member.id" :value="member.id">
                  {{ member.name }}
                </option>
              </select>
            </div>
            
            <!-- 状态筛选下拉框 -->
            <div class="filter-dropdown">
              <select v-model="selectedStatus" @change="applyFilters" class="filter-select">
                <option value="">全部状态</option>
                <option value="new">新建</option>
                <option value="pending">待处理</option>
                <option value="resolved">已解决</option>
                <option value="close">已关闭</option>
                <option value="hold">暂停</option>
                <option value="reopen">重新打开</option>
                <option value="not_badcase">非{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}</option>
              </select>
            </div>
            

            <button class="refresh-btn" @click="refreshBadcases" :disabled="badcaseLoading">🔄</button>
            <button class="view-btn">📋</button>
            <span class="total-count">共{{ filteredBadcases.length }}条</span>
          </div>
        </div>
        
        <div class="task-table">
          <div class="table-header">
            <div class="header-checkbox">
              <input type="checkbox" v-model="selectAll" @change="toggleSelectAll" />
            </div>
            <div class="header-title">{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}标题</div>
            <div class="header-type">类型</div>
            <div class="header-status">状态</div>
            <div class="header-assignee">负责人</div>
            <div class="header-date">创建时间</div>
          </div>
          
          <div class="table-body">
            <div v-if="badcaseLoading" class="loading-row">
              <div class="loading-text">加载中...</div>
            </div>
            <div v-else-if="filteredBadcases.length === 0" class="empty-row">
              <div class="empty-text">暂无{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}数据</div>
            </div>
            <div 
              v-else
              v-for="badcase in filteredBadcases" 
              :key="badcase.id"
              class="table-row"
              :class="{ 'selected': selectedTasks.includes(badcase.id) }"
              @click="editBadcase(badcase.id)"
              style="cursor: pointer;"
            >
              <div class="row-checkbox">
                <input 
                  type="checkbox" 
                  :checked="selectedTasks.includes(badcase.id)"
                  @change="toggleTaskSelection(badcase.id)"
                  @click.stop
                />
              </div>
              <div class="row-title">
                <span class="badcase-title">{{ badcase.title }}</span>
              </div>
              <div class="row-type">
                <span class="type-badge" :class="currentPlanType">{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}</span>
              </div>
              <div class="row-status">
                <span class="status-badge" :class="badcase.status">{{ getBadcaseStatusText(badcase.status) }}</span>
              </div>
              <div class="row-assignee">
                <span class="assignee-text">{{ getAssigneeDisplayText(badcase.assignee) }}</span>
              </div>
              <div class="row-date">
                <span class="date-text">{{ new Date(badcase.created_at).toLocaleDateString() }}</span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 底部Terminal和Output区域 -->
        <div v-if="showTerminal" class="bottom-panel" :class="{
          'with-left-sidebar': !leftSidebarHidden && !planCollapsed,
          'with-collapsed-sidebar': !leftSidebarHidden && planCollapsed
        }" :style="{ 
          height: bottomPanelHeight + 'px',
          zIndex: 100
        }">
          <!-- 拖拽手柄 -->
          <div class="drag-handle-horizontal" @mousedown="startDragBottomPanel"></div>
          
          <div class="panel-tabs">
            <div class="tab-item active">Terminal</div>
            <div class="tab-item">Output</div>
          </div>
          <div class="panel-content">
            <!-- 使用XTerminal组件 -->
            <XTerminal />
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
              {{ sessions[currentSession].title || '未命名会话' }}
              <button class="tab-close" @click.stop="closeSessionTab(currentSession)">×</button>
            </div>
            <div v-else-if="currentSession" class="ai-tab active">
              会话加载中...
            </div>
          </div>
          <div class="ai-panel-actions">
            <button class="ai-action-btn" title="新增会话" @click="createNewSession">+</button>
            <div class="dropdown">
              <button class="ai-action-btn" title="会话历史" @click="toggleHistory">🕐</button>
              <div class="dropdown-menu history-menu" :class="{ 'show': showHistory }">
                <div v-if="historyLoading" class="dropdown-item loading">加载中...</div>
                <div v-else-if="sessionHistory.length === 0" class="dropdown-item empty">暂无历史会话</div>
                <template v-else>
                  <div 
                    v-for="session in sessionHistory" 
                    :key="session.id" 
                    class="dropdown-item history-item"
                    :class="{ 'active': currentSession === session.id }"
                    @click="switchSession(session.id)"
                  >
                    <div class="history-title">{{ session.title || '未命名会话' }}</div>
                    <div class="history-time">{{ new Date(session.created_at).toLocaleString() }}</div>
                  </div>
                </template>
              </div>
            </div>
            <div class="dropdown">
              <button class="ai-action-btn dropdown-toggle" title="更多选项" @click="toggleDropdown">⋯</button>
              <div class="dropdown-menu" :class="{ 'show': showDropdown }">
                <a class="dropdown-item" href="#" @click="closeSession">关闭会话</a>
                <a class="dropdown-item" href="#" @click="exportChat">导出对话</a>
                <a class="dropdown-item" href="#" @click="clearMessages">清空对话</a>
              </div>
            </div>
          </div>
        </div>
        <!-- 聊天面板区域 -->
        <div class="chat-panel-container">
          <SimpleChatPanel v-if="currentSession" :sessionId="currentSession" :projectId="projectId" />
          <div v-else class="chat-empty-placeholder">
            <p>选择或创建一个会话开始聊天</p>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 基线管理模态框 -->
    <div v-show="showBaselineManagementModal" class="modal-overlay" @click="closeBaselineManagementModal">
      <div class="modal-content baseline-modal" @click.stop>
        <div class="modal-header">
          <h3>基线管理</h3>
          <button class="close-btn" @click="closeBaselineManagementModal">✕</button>
        </div>
        
        <div class="modal-body">
          <div class="baseline-layout">
            <!-- 左侧：BadCase计划列表 -->
            <div class="baseline-left-panel">
              <div class="panel-header">
                <h4>BadCase计划</h4>
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
                <h4>{{ selectedBaselinePlanName || '选择计划' }}</h4>
                <div class="baseline-actions">
                  <button class="baseline-btn" @click="createNewBaseline" :disabled="!selectedBaselinePlan || selectedBadcases.length === 0">
                    创建基线
                  </button>
                  <button class="baseline-btn" @click="compareBaselines" :disabled="!hasBaselines">
                    基线对比
                  </button>
                </div>
              </div>
              
              <div class="badcase-section">
                <div class="section-header">
                  <span>未在基线中的BadCase</span>
                  <span class="count">({{ availableBadcases.length }})</span>
                </div>
                
                <div class="badcase-list">
                  <div v-if="availableBadcases.length === 0" class="empty-state">
                    <div class="empty-icon">📋</div>
                    <div class="empty-text">该计划下暂无BadCase</div>
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
                  <span>基线列表</span>
                  <span class="count">({{ baselines.length }})</span>
                </div>
                
                <div class="baseline-list">
                  <div v-if="baselines.length === 0" class="empty-state">
                    <div class="empty-icon">📊</div>
                    <div class="empty-text">暂无基线</div>
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
                        <span class="count">{{ baseline.badcase_count }}个BadCase</span>
                      </div>
                    </div>
                    <div class="baseline-actions">
                      <button class="action-btn" @click.stop="viewBaseline(baseline.id)">查看</button>
                      <button class="action-btn delete" @click.stop="deleteBaseline(baseline.id)">删除</button>
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
            <label class="form-label cycle-label required">计划周期</label>
            <select v-model="newPlan.cycle" class="form-select">
              <option value="one_week">一周</option>
              <option value="two_weeks">两周</option>
              <option value="one_month">一个月</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          
          <div class="form-group date-row">
            <div class="date-field">
              <label class="form-label required">开始时间</label>
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
              <label class="form-label required">结束时间</label>
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
            <label class="form-label count-label">计划个数</label>
            <div class="number-input-wrapper">
              <input 
                type="number" 
                v-model="newPlan.count" 
                min="1" 
                class="form-input count-input"
              />
              <span class="helper-text">(完成{{ newPlan.count }}次迭代时间为{{ calculateEndDate() }})</span>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label required">计划名</label>
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
                <button class="help-btn" title="命名规则说明">❓</button>
              </div>
            </div>
          </div>
          
          <div class="form-group parent-row">
            <label class="form-label parent-label">父计划</label>
            <select v-model="newPlan.parentId" class="form-select" :disabled="isCreatingSubPlan || isCreatingSiblingPlan">
              <option value="">请选择一个计划</option>
              <option v-for="plan in availableParentPlans" :key="plan.id" :value="plan.id">
                {{ plan.name }}
              </option>
            </select>
            <div v-if="isCreatingSubPlan && newPlan.parentId" class="parent-plan-info">
              <span class="info-text">当前计划将作为父计划</span>
            </div>
            <div v-if="isCreatingSiblingPlan" class="parent-plan-info">
              <span class="info-text">{{ newPlan.parentId ? '将在同一父计划下创建同级计划' : '将创建顶级计划' }}</span>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">描述</label>
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
            <label class="form-label required">计划状态</label>
            <select v-model="newPlan.statusType" class="form-select">
              <option value="in_progress">进行中</option>
              <option value="unplanned">未计划</option>
              <option value="archived">已归档</option>
            </select>
          </div>
          
          <!-- 新增：内容类型选择 -->
          <div class="form-group">
            <label class="form-label required">内容类型</label>
            <select v-model="newPlan.contentType" class="form-select">
              <option value="badcase">BadCase类型</option>
              <option value="bug">Bug类型</option>
              <option value="test_case">测试用例类型</option>
            </select>
          </div>
          
          <div class="form-group">
            <label class="toggle-label">
              <span>范围变更通知</span>
              <input 
                type="checkbox" 
                v-model="newPlan.scopeNotification" 
                class="toggle-switch"
              />
            </label>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeCreateModal">取消</button>
          <button class="btn btn-primary" @click="createPlan" :disabled="!isFormValid">
            {{ isEditingPlan ? '更新' : '确定' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 团队管理模态框 -->
    <div v-if="showTeamManagementModal" class="modal-overlay" @click="closeConfigModals">
      <div class="modal-content team-management-modal" @click.stop>
        <div class="modal-header">
          <h3>团队管理</h3>
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
          <h3>项目设置</h3>
          <button class="close-btn" @click="closeConfigModals">×</button>
        </div>
        
        <div class="modal-body">
          <p>项目设置功能开发中...</p>
        </div>
      </div>
    </div>
    
    <!-- 权限设置模态框 -->
    <div v-if="showPermissionSettingsModal" class="modal-overlay" @click="closeConfigModals">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>权限设置</h3>
          <button class="close-btn" @click="closeConfigModals">×</button>
        </div>
        
        <div class="modal-body">
          <p>权限设置功能开发中...</p>
        </div>
      </div>
    </div>

    <!-- 个人资料弹窗 -->
    <UserProfile 
      v-if="showProfileModal" 
      :user="currentUser" 
      @close="showProfileModal = false"
    />
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getProjectPlans, getProjectDetail, createPlan as createPlanApi, updatePlan as updatePlanApi, deletePlan as deletePlanApi, pinPlan as pinPlanApi, getProjectBadcases, getProjectBugs, updateBadcasePlan, getProjectMembers, getChatSessions, createChatSession, getChatSession } from '../api.js'
import TeamManagement from './TeamManagement.vue'
import XTerminal from './XTerminal.vue'
import SimpleChatPanel from './SimpleChatPanel.vue'
import UserProfile from './UserProfile.vue'
import userStore from '../store/user.js'

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
    TeamManagement,
    XTerminal,
    SimpleChatPanel,
    UserProfile
  },
  setup() {
    const router = useRouter()
    const route = useRoute()
    
    // 项目信息
    const projectName = ref('项目详情')
    const projectId = ref(null)
    // 工作目录（保留用于Terminal组件）
    const currentWorkingDir = ref('/Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor')
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
    
    const selectAll = ref(false)
    const selectedTasks = ref([])

    // 项目计划数据
    const projectPlans = ref([])
    const filteredPlans = ref([])
    const loading = ref(false)

    // 悬停和上下文菜单状态
    const hoveredPlan = ref(null)
    const contextMenu = reactive({
      visible: false,
      planId: null,
      x: 0,
      y: 0
    })

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
    const currentUser = ref(null)
    
    // 布局控制状态
    const showTerminal = ref(false)
    const showAIAssistant = ref(false)
    const leftSidebarHidden = ref(false)
    
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
    
    // 根据状态类型过滤计划
    const inProgressPlans = computed(() => {
      // 兼容更多可能的状态值
      const plans = projectPlans.value.filter(plan => 
        (plan.status_type === 'in_progress') || 
        (plan.status === 'active') || 
        (plan.status === 'in_progress') ||
        (plan.status === 'running') ||
        (plan.status === 'open') ||
        (plan.status === 'doing')
      )
      console.log('🔍 进行中计划过滤结果:', {
        total: projectPlans.value.length,
        filtered: plans.length,
        plans: plans.map(p => ({ id: p.id, name: p.name, status: p.status, status_type: p.status_type }))
      })
      return plans
    })
    
    const unplannedPlans = computed(() => {
      // 兼容更多可能的状态值，包括新创建和待处理状态
      const plans = projectPlans.value.filter(plan => 
        (plan.status_type === 'unplanned') || 
        (plan.status === 'unplanned') || 
        (plan.status === 'new') ||
        (!plan.status && !plan.status_type)
      )

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
      const statusMap = {
        'active': '进行中',
        'archived': '已归档',
        'completed': '已完成'
      }
      return statusMap[status] || status
    }

    // 获取BadCase状态文本
    const getBadcaseStatusText = (status) => {
      const statusMap = {
        'new': '新建',
        'unpublished': '未发布',
        'pending': '待处理',
        'resolved': '已解决',
        'close': '已关闭',
        'hold': 'hold',
        'reopen': '重新打开',
        'not_badcase': 'not a badcase'
      }
      return statusMap[status] || status
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
          sessions.value[sessionId] = { id: sessionId, title: '加载中...' }
        }
      }
    }
    
    const createNewSession = async () => {
      if (!projectId.value) {
        alert('错误：项目 ID 不存在')
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
          alert('新建会话失败: ' + (response.data.error || '未知错误'))
        }
      } catch (error) {
        console.error('新建会话异常:', error)
        alert('新建会话异常')
      }
    }
    
    const closeSessionTab = (sessionId) => {
      // 这里的逻辑改为关闭右侧面板
      setLayout('left')
    }
    

    // 当显示terminal输入时，自动聚焦到输入框（已由新的终端实现）


    // 获取BadCase类型文本
    const getBadcaseTypeText = (type) => {
      const typeMap = {
        'badcase': 'BadCase',
        'bug': 'Bug',
        'test_request': '提测单'
      }
      return typeMap[type] || type
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
        'badcase': 'BadCase类型',
        'bug': 'Bug类型',
        'test_case': '测试用例类型'
      }
      return typeMap[contentType] || '未知类型'
    }
    
    // 获取负责人显示文本
    const getAssigneeDisplayText = (assignee) => {
      if (!assignee || assignee === '') {
        return '未指派'
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
      const managementLabel = currentPlanType.value === 'bug' ? 'Bug管理' : (currentPlanType.value === 'test_case' ? '测试用例管理' : 'BadCase管理')
      
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
      breadcrumb.unshift(projectName.value)
      
      return breadcrumb.join(' / ')
    }
    
    // 处理计划数据，添加图标和格式化
    const processPlanData = (plans) => {
      if (!plans) return []
      return plans.map(plan => {
        const contentType = plan.content_type || plan.plan_type || 'badcase'
        console.log('🔍 处理计划:', plan.name, '，plan_type:', plan.plan_type, '，content_type:', plan.content_type, '，最终使用:', contentType)
        return {
          ...plan,
          // 兼容后端返回的 plan_type 和前端使用的 content_type
          content_type: contentType,
          icon: getPlanIcon(contentType),
          statusText: getPlanStatusText(plan.status),
          children: plan.children ? processPlanData(plan.children) : []
        }
      })
    }
    
    // 计算属性
    const availableParentPlans = computed(() => {
      return projectPlans.value.filter(plan => plan.status === 'active')
    })
    
    const namePlaceholder = computed(() => {
      if (!newPlan.startDate || !newPlan.endDate) return '请输入计划名称'
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
        console.log('API URL:', `http://localhost:5000/api/projects/${projectId.value}/plans`)
        
        const response = await getProjectPlans(projectId.value)
        console.log('获取项目计划完整响应:', response)
        console.log('响应状态:', response.status)
        console.log('响应数据:', response.data)
        if (response && response.data && response.data.success) {
          projectPlans.value = processPlanData(response.data.plans)
          console.log('处理后的计划数据:', projectPlans.value)
          console.log('计划层级结构检查:')
          projectPlans.value.forEach((plan, index) => {
            console.log(`计划${index + 1}: ${plan.name} (ID: ${plan.id})`)
            if (plan.children && plan.children.length > 0) {
              plan.children.forEach((child, childIndex) => {
                console.log(`  子计划${childIndex + 1}: ${child.name} (ID: ${child.id}, 父ID: ${child.parent_id})`)
              })
            }
          })
          // 初始化过滤后的计划列表
          filterPlans()
          console.log('过滤后的计划数据:', filteredPlans.value)
          
          // 强制触发Vue响应式更新
          console.log('强制更新响应式数据...')
          projectPlans.value = [...projectPlans.value]
          filteredPlans.value = [...filteredPlans.value]
          
          // 检查并确保有未计划的BadCase类型计划
          await ensureUnplannedBadcasePlan()
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
    
    // 确保有未计划的BadCase类型计划
    let isEnsuringUnplannedPlan = false
    const ensureUnplannedBadcasePlan = async () => {
      if (isEnsuringUnplannedPlan) return
      
      try {
        isEnsuringUnplannedPlan = true
        console.log('🔍 检查未计划的BadCase类型计划...')
        
        // 检查是否已有未计划的BadCase类型计划
        const existingUnplannedBadcasePlan = projectPlans.value.find(plan => 
          (plan.status_type === 'unplanned' || plan.status === 'unplanned') && 
          (plan.content_type === 'badcase' || plan.plan_type === 'badcase' || plan.name === '未计划BadCase')
        )
        
        if (existingUnplannedBadcasePlan) {
          console.log('✅ 已存在未计划的BadCase类型计划:', existingUnplannedBadcasePlan.name)
          return
        }
        
        console.log('⚠️ 未找到未计划的BadCase类型计划，开始创建...')
        
        // 创建未计划的BadCase类型计划
        const newUnplannedPlan = {
          name: '未计划BadCase',
          description: '自动创建的未计划BadCase类型计划',
          project_id: projectId.value,
          status_type: 'unplanned',
          content_type: 'badcase',
          plan_type: 'badcase',
          status: 'unplanned',
          cycle: 'one_week',
          start_date: new Date().toISOString().split('T')[0],
          end_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          count: 1,
          scope_notification: false
        }
        
        console.log('📋 新计划数据:', newUnplannedPlan)
        
        // 调用API创建计划
        const response = await createPlanApi(newUnplannedPlan)
        
        if (response && response.data && response.data.success) {
          const createdPlan = response.data.plan
          console.log('✅ 未计划的BadCase类型计划创建成功:', createdPlan.name, '(ID:', createdPlan.id, ')')
          
          // 刷新计划列表（不直接在此递归调用 fetchProjectPlans，避免循环）
          const freshResponse = await getProjectPlans(projectId.value)
          if (freshResponse && freshResponse.data && freshResponse.data.success) {
             projectPlans.value = processPlanData(freshResponse.data.plans)
             filterPlans()
          }
          
          // 自动展开未计划section
          expandedSections.unplanned = true
          expandedUnplannedBadcase.value = true
          
          console.log('🎉 未计划的BadCase类型计划已创建并展开')
        } else {
          console.error('❌ 创建未计划的BadCase类型计划失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('❌ 确保未计划的BadCase类型计划时发生错误:', error)
      } finally {
        isEnsuringUnplannedPlan = false
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
    
    // 切换未计划badcase展开状态
    const toggleUnplannedBadcaseSection = () => {
      expandedUnplannedBadcase.value = !expandedUnplannedBadcase.value
    }
    
    const selectPlan = async (planId) => {
      selectedPlan.value = planId
      console.log('选择计划:', planId)
      
      // 调用API获取对应计划的BadCase
      await fetchBadcasesByPlan(planId, 1)
      
      // API调用完成后，根据选择的计划过滤BadCase
      console.log('API调用完成，开始过滤BadCase')
      filterBadcasesByPlan(planId)
    }
    
    // 选择未计划的卡片
    const selectUnplanned = async () => {
      selectedPlan.value = 'unplanned'
      console.log('选择未计划的卡片')
      
      // 自动展开未计划section和badcase目录
      expandedSections.unplanned = true
      expandedUnplannedBadcase.value = true
      
      // 调用API获取未计划且BadCase类型的BadCase（使用status_type和content_type筛选）
      console.log('🔍 未计划卡片：调用API获取未计划且BadCase类型的BadCase（使用status_type和content_type筛选）')
      await fetchUnplannedBadcases(1)
      
      // API调用完成后，根据未计划状态过滤BadCase
      console.log('API调用完成，开始过滤BadCase')
      filterBadcasesByPlan('unplanned')
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
          
          // 如果查询结果为空，自动创建未计划的BadCase类型计划
          if (badcases.value.length === 0 && totalBadcases.value === 0) {
            console.log('⚠️ 未计划BadCase查询结果为空，开始创建未计划的BadCase类型计划...')
            await createUnplannedBadcasePlan()
          }
          
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
    
    // 创建未计划的BadCase类型计划（当查询结果为空时调用）
    const createUnplannedBadcasePlan = async () => {
      try {
        console.log('🔍 开始创建未计划的BadCase类型计划...')
        
        // 创建未计划的BadCase类型计划
        const newUnplannedPlan = {
          name: '未计划BadCase',
          description: '自动创建的未计划BadCase类型计划',
          project_id: projectId.value,
          status_type: 'unplanned',
          content_type: 'badcase',
          plan_type: 'badcase',
          status: 'unplanned',
          cycle: 'one_week',
          start_date: new Date().toISOString().split('T')[0],
          end_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          count: 1,
          scope_notification: false
        }
        
        console.log('📋 新计划数据:', newUnplannedPlan)
        
        // 调用API创建计划
        const response = await createPlanApi(newUnplannedPlan)
        
        if (response && response.data && response.data.success) {
          const createdPlan = response.data.plan
          console.log('✅ 未计划的BadCase类型计划创建成功:', createdPlan.name, '(ID:', createdPlan.id, ')')
          
          // 刷新计划列表
          await fetchProjectPlans()
          
          // 自动展开未计划section
          expandedSections.unplanned = true
          expandedUnplannedBadcase.value = true
          
          console.log('🎉 未计划的BadCase类型计划已创建并展开')
        } else {
          console.error('❌ 创建未计划的BadCase类型计划失败:', response?.data?.error || '未知错误')
        }
      } catch (error) {
        console.error('❌ 创建未计划的BadCase类型计划异常:', error)
        console.error('错误详情:', error.message)
      }
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
        
        let response
        if (currentPlanType.value === 'bug') {
          console.log(`🔍 调用 getProjectBugs，检索计划ID: ${planId}`)
          response = await getProjectBugs(projectId.value, page, badcasePerPage.value, params)
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
      // 根据当前计划类型决定跳转到哪个路由
      const basePath = currentPlanType.value === 'bug' ? '/new-bug' : '/new-badcase'
      let url = `${basePath}?project_id=${projectId.value}`
      
      // 如果选中了具体计划，传递 plan_id
      if (selectedPlan.value && selectedPlan.value !== 'unplanned') {
        url += `&plan_id=${selectedPlan.value}`
      }
      
      router.push(url)
    }

    // 编辑BadCase
    const editBadcase = (badcaseId) => {
      console.log('=== editBadcase函数被调用 ===')
      console.log('BadCase/Bug ID:', badcaseId)
      console.log('项目ID:', projectId.value)
      console.log('当前路由:', route.path)
      
      try {
        const basePath = currentPlanType.value === 'bug' ? '/new-bug' : '/new-badcase'
        const targetUrl = `${basePath}?id=${badcaseId}&project_id=${projectId.value}&edit=true`
        console.log('目标URL:', targetUrl)
        router.push(targetUrl)
        console.log('路由跳转成功')
      } catch (error) {
        console.error('路由跳转失败:', error)
      }
    }
    
    const goToDashboard = () => {
      router.push('/dashboard')
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
    
    // 显示上下文菜单
    const showContextMenu = (plan, event) => {
      event.preventDefault()
      event.stopPropagation()
      
      contextMenu.visible = true
      contextMenu.planId = plan.id
      contextMenu.x = event.clientX
      contextMenu.y = event.clientY
      
      // 点击其他地方关闭菜单
      setTimeout(() => {
        document.addEventListener('click', closeContextMenu, { once: true })
      }, 0)
    }
    
    // 关闭上下文菜单
    const closeContextMenu = () => {
      contextMenu.visible = false
      contextMenu.planId = null
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
        filtered = filtered.filter(b => !b.plan_id || b.plan_id === 0)
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
      if (confirm(`确定要删除计划"${plan.name}"吗？此操作无法撤销。`)) {
        try {
          console.log('开始删除计划:', plan.name, 'ID:', plan.id)
          
          const response = await deletePlanApi(plan.id)
          console.log('删除计划响应:', response)
          
          if (response && response.data && response.data.success) {
            console.log('计划删除成功:', plan.name)
            alert('计划删除成功!')
            
            // 重新获取计划列表
            await fetchProjectPlans()
          } else {
            const errorMsg = response?.data?.error || '未知错误'
            console.error('删除计划失败:', errorMsg)
            alert('删除计划失败: ' + errorMsg)
          }
        } catch (error) {
          console.error('删除计划失败 - 详细错误:', error)
          console.error('错误响应:', error.response)
          console.error('错误状态:', error.response?.status)
          console.error('错误数据:', error.response?.data)
          
          let errorMessage = '删除计划失败'
          if (error.response) {
            // 服务器返回了错误响应
            errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
          } else if (error.request) {
            // 请求已发出但没有收到响应
            errorMessage += ': 无法连接到服务器，请检查网络连接'
          } else {
            // 其他错误
            errorMessage += `: ${error.message}`
          }
          
          alert(errorMessage)
        }
      }
    }
    
    const pinPlan = async (plan) => {
      closeContextMenu()
      const action = plan.is_pinned ? '取消置顶' : '置顶'
      console.log(`${action}计划:`, plan.name)
      
      try {
        const response = await pinPlanApi(plan.id)
        console.log('置顶API响应:', response)
        
        if (response && response.data && response.data.success) {
          console.log(`计划${action}成功:`, plan.name)
          alert(`计划${action}成功!`)
          
          // 重新获取计划列表以更新排序
          await fetchProjectPlans()
        } else {
          const errorMsg = response?.data?.error || '未知错误'
          console.error(`${action}计划失败:`, errorMsg)
          alert(`${action}计划失败: ` + errorMsg)
        }
      } catch (error) {
        console.error(`${action}计划失败 - 详细错误:`, error)
        
        let errorMessage = `${action}计划失败`
        if (error.response) {
          errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
        } else if (error.request) {
          errorMessage += ': 无法连接到服务器，请检查网络连接'
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
        return '编辑计划'
      } else if (isCreatingSubPlan.value) {
        return '新建子计划'
      } else if (isCreatingSiblingPlan.value) {
        return '新建同级计划'
      } else {
        return '新建计划'
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
      if (window.confirm('确定要删除这个基线吗？')) {
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
        await Promise.all([
          fetchProjectInfo(),
          fetchProjectPlans(),
          fetchBadcases(),
          fetchProjectMembers()
        ])
        
        // 确保有未计划的BadCase类型计划
        await ensureUnplannedBadcasePlan()
        
        console.log('数据刷新完成')
      } catch (error) {
        console.error('刷新数据失败:', error)
      } finally {
        loading.value = false
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
        console.log('API基础URL:', 'http://localhost:5000')
        
        let response
        try {
          console.log('=== 开始API调用 ===')
          if (isEditingPlan.value) {
            console.log('调用更新计划API，计划ID:', editingPlanId.value)
            response = await updatePlanApi(editingPlanId.value, planData)
            console.log('更新计划API响应:', response)
          } else {
            console.log('调用创建计划API')
            console.log('API URL: POST http://localhost:5000/api/plans')
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
          const actionText = isEditingPlan.value ? '更新' : '创建'
          console.log(`计划${actionText}成功:`, response.data.plan)
          alert(`计划${actionText}成功!`)
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
          const errorMsg = response?.data?.error || '未知错误'
          const actionText = isEditingPlan.value ? '更新' : '创建'
          console.error(`${actionText}计划失败:`, errorMsg)
          alert(`${actionText}计划失败: ` + errorMsg)
        }
      } catch (error) {
        console.error('创建计划失败 - 详细错误:', error)
        console.error('错误响应:', error.response)
        console.error('错误状态:', error.response?.status)
        console.error('错误数据:', error.response?.data)
        
        const actionText = isEditingPlan.value ? '更新' : '创建'
        let errorMessage = `${actionText}计划失败`
        if (error.response) {
          // 服务器返回了错误响应
          errorMessage += `: ${error.response.status} - ${error.response.data?.error || error.response.statusText}`
        } else if (error.request) {
          // 请求已发出但没有收到响应
          errorMessage += ': 无法连接到服务器，请检查网络连接'
        } else {
          // 其他错误
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
    
    const showNotifications = () => {
      showUserDropdown.value = false
      // TODO: 实现通知页面
      alert('通知功能开发中...')
    }
    
    const showHelp = () => {
      showUserDropdown.value = false
      // TODO: 实现帮助页面
      alert('帮助功能开发中...')
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
    
    // 监听项目ID变化，确保在路由切换或刷新时同步加载数据
    watch(() => route.params.id, async (newId) => {
      if (newId) {
        projectId.value = newId
        console.log('项目ID发生变化:', newId)
        await manualRefreshPlans()
        await fetchSessions()
        if (sessionHistory.value.length > 0) {
          currentSession.value = sessionHistory.value[0].id
          sessions.value[currentSession.value] = sessionHistory.value[0]
        }
      }
    }, { immediate: true })

    onMounted(async () => {
      console.log('=== ProjectDetail onMounted ===')
          
      // 检查URL参数，如果有expand_plan参数，先设置选中的计划ID
      // 这样后续的manualRefreshPlans中的fetchBadcases就能带上正确的plan_id
      const expandPlanId = route.query.expand_plan
      if (expandPlanId) {
        console.log('检测到expand_plan参数，预设selectedPlan:', expandPlanId)
        selectedPlan.value = expandPlanId
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
    })
    
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
      toggleSection,
      toggleUnplannedBadcaseSection,
      selectPlan,
      selectUnplanned,
      selectUnplannedBadcase,
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
      // Terminal相关（保留工作目录用于Terminal组件）
      currentWorkingDir
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

/* 上下文菜单 */
.context-menu {
  position: fixed;
  z-index: 1000;
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 160px;
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
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr;
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
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr;
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

/* 右侧AI助手面板样式 */
.right-sidebar {
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  height: 100vh;
  background: #252526;
  border-left: 1px solid #3e3e3e;
  box-shadow: -2px 0 10px rgba(0, 0, 0, 0.5);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  padding: 0;
  margin: 0;
}

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
</style> 