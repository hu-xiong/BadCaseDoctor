<template>
  <div class="testcase-detail-wrapper">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载项目信息...</div>
    </div>
    
    <!-- 顶部标题栏 -->
    <div class="header-bar">
      <div class="header-left">
        <span class="back-arrow" @click="goBack">←</span>
        <span class="header-title">{{ isEdit ? '编辑测试用例' : '新建测试用例' }}</span>
        <span class="project-name" v-if="projectInfo.name">/ {{ projectInfo.name }}</span>
      </div>
      <div class="header-right">
        <button class="header-btn" @click="toggleRequiredOnly">
          <span class="checkbox-icon" :class="{ checked: showRequiredOnly }">✓</span>
          只看必填项
        </button>
        <button class="header-btn close-btn" @click="goBack">
          <span class="close-icon">×</span>
        </button>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧主要内容区 -->
      <div class="content-left">
        <!-- 标题区域 -->
        <div class="title-section">
          <input 
            v-model="testcase.title" 
            class="title-input" 
            placeholder="请输入测试用例标题"
            maxlength="100"
          />
          <div class="title-count">{{ testcase.title.length }} / 100</div>
        </div>

        <!-- 状态和维护人信息 -->
        <div class="status-section">
          <div class="status-item">
            <span class="status-label">状态:</span>
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
                      <div class="assignee-name">{{ currentUser.name }}</div>
                      <div class="assignee-id">({{ currentUser.email }})</div>
                    </div>
                  </div>
                  <div v-else class="no-user-tip">
                    <span class="tip-icon">⚠️</span>
                    <span class="tip-text">未获取到当前用户信息</span>
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
                      <div class="assignee-name">{{ member.name }}</div>
                      <div class="assignee-id">({{ member.email }})</div>
                    </div>
                  </div>
                </div>
                
                <!-- 无项目成员时的提示 -->
                <div v-else-if="testcase.project_id && projectMembers.length === 0" class="assignee-section">
                  <div class="section-title">项目成员 (0人)</div>
                  <div class="no-members-tip">
                    <span class="tip-icon">ℹ️</span>
                    <span class="tip-text">该项目暂无成员，请先添加项目成员</span>
                  </div>
                </div>
                
                <!-- 未选择项目时的提示 -->
                <div v-else-if="!testcase.project_id" class="assignee-section">
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
              <div class="plan-selected-display">
                <span class="refresh-icon" @click.stop="refreshProjectPlans">🔄</span>
                <span class="plan-selected-text">
                  所属计划 {{ getSelectedPlanDisplayText() }}
                </span>
                <span class="arrow-icon" :class="{ 'rotated': showPlanDropdown }">▼</span>
              </div>
              <div v-if="showPlanDropdown" class="plan-dropdown-menu">
                <div 
                  v-for="plan in testcasePlans" 
                  :key="plan.value"
                  class="plan-option"
                  :class="{ 'selected': testcase.plan_id === plan.value }"
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
            <div class="form-group">
              <label class="field-label">前置条件</label>
              <div class="editor-section">
                <div class="editor-toolbar">
                  <button class="toolbar-btn" type="button" title="撤销" @click="formatPreconditions('undo')">↶</button>
                  <button class="toolbar-btn" type="button" title="重做" @click="formatPreconditions('redo')">↷</button>
                  <div class="toolbar-divider"></div>
                  <button class="toolbar-btn" type="button" title="粗体" @click="formatPreconditions('bold')">B</button>
                  <button class="toolbar-btn" type="button" title="斜体" @click="formatPreconditions('italic')">I</button>
                  <button class="toolbar-btn" type="button" title="下划线" @click="formatPreconditions('underline')">U</button>
                  <button class="toolbar-btn" type="button" title="删除线" @click="formatPreconditions('strikeThrough')">S</button>
                  <div class="toolbar-divider"></div>
                  <button class="toolbar-btn" type="button" title="左对齐" @click="formatPreconditions('justifyLeft')">⫷</button>
                  <button class="toolbar-btn" type="button" title="居中" @click="formatPreconditions('justifyCenter')">⫸</button>
                  <button class="toolbar-btn" type="button" title="右对齐" @click="formatPreconditions('justifyRight')">⫹</button>
                  <div class="toolbar-divider"></div>
                  <button class="toolbar-btn" type="button" title="无序列表" @click="formatPreconditions('insertUnorderedList')">•</button>
                  <button class="toolbar-btn" type="button" title="有序列表" @click="formatPreconditions('insertOrderedList')">1.</button>
                </div>
                <div 
                  ref="preconditionsEditor" 
                  class="editor-textarea"
                  contenteditable="true"
                  @input="updatePreconditions"
                  placeholder="请输入前置条件..."
                ></div>
              </div>
            </div>

            <!-- 用例步骤 -->
            <div class="form-group">
              <label class="field-label">用例步骤</label>
              <div class="steps-table">
                <div class="steps-header">
                  <div class="step-col-number">#</div>
                  <div class="step-col-desc">步骤描述</div>
                  <div class="step-col-expected">预期结果</div>
                  <div class="step-col-actions">操作</div>
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
                      placeholder="输入步骤描述"
                    />
                  </div>
                  <div class="step-col-expected">
                    <input 
                      v-model="step.expected" 
                      class="step-input"
                      placeholder="输入预期结果"
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
                    + 添加步骤
                  </button>
                </div>
              </div>
            </div>

            <!-- 属性区域 -->
            <div class="properties-container">
              <h3 class="properties-title">属性</h3>
              <div class="properties-grid">
                <!-- 用例类型 -->
                <div class="property-field">
                  <label class="field-label">用例类型</label>
                  <select v-model="testcase.case_type" class="field-select">
                    <option value="功能测试">功能测试</option>
                    <option value="接口测试">接口测试</option>
                    <option value="性能测试">性能测试</option>
                    <option value="安全测试">安全测试</option>
                  </select>
                </div>

                <!-- 重要程度 -->
                <div class="property-field">
                  <label class="field-label">重要程度</label>
                  <select v-model="testcase.priority" class="field-select">
                    <option value="P0">P0</option>
                    <option value="P1">P1</option>
                    <option value="P2">P2</option>
                    <option value="P3">P3</option>
                  </select>
                </div>

                <!-- 测试类型 -->
                <div class="property-field">
                  <label class="field-label">测试类型</label>
                  <select v-model="testcase.test_type" class="field-select">
                    <option value="手动">手动</option>
                    <option value="自动">自动</option>
                    <option value="探索">探索</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- 备注 -->
            <div class="form-group">
              <label class="field-label">备注</label>
              <textarea 
                v-model="testcase.remark" 
                class="form-textarea"
                placeholder="输入备注信息"
                rows="4"
              ></textarea>
            </div>
          </div>
          
          <!-- 缺陷 Tab -->
          <div v-if="activeTab === 'defects'" class="tab-pane">
            <div class="form-group">
              <label class="field-label">关联缺陷</label>
              <div class="related-defects">
                <div 
                  v-for="(defect, index) in testcase.related_defects" 
                  :key="index"
                  class="defect-item"
                >
                  <div class="defect-info" @click="navigateToDefect(defect)">
                    <span class="defect-id">Bug-{{ defect.id }}</span>
                    <span class="defect-title">{{ defect.title }}</span>
                  </div>
                  <button @click="removeDefect(index)" class="remove-defect-btn">×</button>
                </div>
                <button @click="openAddDefectDialog" class="add-defect-btn">
                  + 添加缺陷
                </button>
              </div>
            </div>
          </div>

          <!-- 执行 Tab -->
          <div v-if="activeTab === 'execution'" class="tab-pane">
            <div class="form-group">
              <label class="field-label">执行结果</label>
              <select v-model="testcase.execution_result" class="form-select">
                <option value="">未执行</option>
                <option value="pass">通过</option>
                <option value="fail">失败</option>
                <option value="blocked">阻塞</option>
                <option value="skip">跳过</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 保存和取消按钮 -->
        <div class="save-actions">
          <button @click="saveTestCase" class="btn-save" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
          <button @click="goBack" class="btn-cancel">取消</button>
        </div>
      </div>

      <!-- 右侧边栏 -->
      <div class="sidebar-right">
        <!-- 所属项目 -->
        <div class="sidebar-section">
          <h3 class="sidebar-title">所属项目</h3>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" v-model="testcase.associate_project" :value="true" />
              <span class="radio-text">关联所属项目</span>
            </label>
            <label class="radio-item">
              <input type="radio" v-model="testcase.associate_project" :value="false" />
              <span class="radio-text">暂不关联所属项目</span>
            </label>
          </div>
          <div v-if="testcase.associate_project" class="project-select">
            <label class="select-label">项目名称:</label>
            <select v-model="testcase.project_id" class="form-select" @change="handleProjectChange">
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
              <span class="field-value">{{ testcase.document_type || '其他文档' }}</span>
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
            <div v-for="(attachment, index) in (testcase.attachments || [])" :key="index" class="attachment-item">
              <span class="attachment-name">{{ attachment.name }}</span>
              <button class="remove-attachment-btn" @click="removeAttachment(index)">×</button>
            </div>
            <div v-if="!testcase.attachments || testcase.attachments.length === 0" class="no-attachments">
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

        <!-- 输入评论 -->
        <div class="sidebar-section">
          <h3 class="sidebar-title">输入评论</h3>
          <div class="comment-input-container">
            <!-- 普通输入框 -->
            <textarea 
              v-if="!commentEditorActive"
              class="comment-textarea-simple" 
              placeholder="请输入评论"
              @click="activateCommentEditor"
              readonly
            >{{ commentText || '' }}</textarea>
            <div v-if="!commentEditorActive" class="comment-count">{{ (commentText || '').length }} / 500</div>
            
            <!-- 富文本编辑器 -->
            <div v-if="commentEditorActive" class="rich-editor">
              <div class="editor-toolbar" @click="preventDeactivate">
                <button class="toolbar-btn" title="画笔" @click="togglePenTool">
                  <span class="pen-icon">✏️</span>
                </button>
                <div class="toolbar-divider"></div>
                <button class="toolbar-btn" title="粗体" @click="formatText('bold')">
                  <strong>B</strong>
                </button>
                <button class="toolbar-btn" title="斜体" @click="formatText('italic')">
                  <em>I</em>
                </button>
                <button class="toolbar-btn" title="下划线" @click="formatText('underline')">
                  <u>U</u>
                </button>
                <div class="toolbar-divider"></div>
                <button class="toolbar-btn" title="无序列表" @click="formatText('unorderedList')">
                  <span class="list-icon">•</span>
                </button>
                <button class="toolbar-btn" title="有序列表" @click="formatText('orderedList')">
                  <span class="list-icon">1.</span>
                </button>
                <div class="toolbar-divider"></div>
                <button class="toolbar-btn" title="插入图片" @click="insertImage">
                  <span class="image-icon">🏞️</span>
                </button>
                <button class="toolbar-btn" title="插入链接" @click="insertLink">
                  <span class="link-icon">🔗</span>
                </button>
              </div>
              <div 
                ref="commentEditor" 
                class="editor-content" 
                contenteditable="true"
                @input="updateComment"
                @blur="deactivateCommentEditor"
                @click="preventDeactivate"
                placeholder="请输入"
              ></div>
              <div class="editor-count">{{ (commentText || '').length }} / 500</div>
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
            <button @click="searchDefects" class="search-btn">搜索</button>
          </div>

          <!-- Bug 树形列表 -->
          <div class="bug-tree-container">
            <div class="tree-header">
              <span class="tree-title">缺陷列表</span>
              <button @click="loadAllBugs" class="refresh-btn" title="刷新">
                🔄
              </button>
            </div>
            <div class="bug-tree">
              <!-- 使用递归组件展示计划树 -->
              <template v-for="plan in bugPlans" :key="plan.value">
                <div class="tree-node">
                  <div class="tree-node-header" @click="togglePlanExpand(plan.value)">
                    <span class="expand-icon" :class="{ expanded: plan.expanded }">▶</span>
                    <span class="plan-icon">{{ plan.icon }}</span>
                    <span class="plan-name">{{ plan.label }}</span>
                    <span class="bug-count">({{ plan.bugs?.length || 0 }})</span>
                  </div>
                  <div v-if="plan.expanded" class="tree-children">
                    <!-- 子计划 -->
                    <template v-if="plan.children && plan.children.length > 0">
                      <div v-for="childPlan in plan.children" :key="childPlan.value" class="tree-node sub-plan">
                        <div class="tree-node-header" @click="togglePlanExpand(childPlan.value)">
                          <span class="expand-icon" :class="{ expanded: childPlan.expanded }">▶</span>
                          <span class="plan-icon">{{ childPlan.icon }}</span>
                          <span class="plan-name">{{ childPlan.label }}</span>
                          <span class="bug-count">({{ childPlan.bugs?.length || 0 }})</span>
                        </div>
                        <div v-if="childPlan.expanded && childPlan.bugs !== null" class="tree-children">
                          <div v-if="childPlan.bugs && childPlan.bugs.length > 0">
                            <div 
                              v-for="bug in childPlan.bugs" 
                              :key="bug.id"
                              class="bug-item"
                              :class="{ selected: isDefectSelected(bug.id.toString()) }"
                              @click="toggleDefectSelection(bug, childPlan.value)"
                            >
                              <div class="checkbox" :class="{ checked: isDefectSelected(bug.id.toString()) }">
                                <span v-if="isDefectSelected(bug.id.toString())" class="checkmark">✓</span>
                              </div>
                              <div class="bug-info">
                                <span class="bug-id">Bug-{{ bug.id }}</span>
                                <span class="bug-title">{{ bug.title }}</span>
                              </div>
                            </div>
                          </div>
                          <div v-else class="no-bugs-tip">
                            暂无缺陷
                          </div>
                        </div>
                        <div v-if="childPlan.expanded && childPlan.bugs === null" class="tree-children loading">
                          <span class="loading-text">加载中...</span>
                        </div>
                      </div>
                    </template>
                    <!-- Bug 列表 -->
                    <div v-if="plan.bugs !== null && plan.bugs && plan.bugs.length > 0">
                      <div 
                        v-for="bug in plan.bugs" 
                        :key="bug.id"
                        class="bug-item"
                        :class="{ selected: isDefectSelected(bug.id.toString()) }"
                        @click="toggleDefectSelection(bug, plan.value)"
                      >
                        <div class="checkbox" :class="{ checked: isDefectSelected(bug.id.toString()) }">
                          <span v-if="isDefectSelected(bug.id.toString())" class="checkmark">✓</span>
                        </div>
                        <div class="bug-info">
                          <span class="bug-id">Bug-{{ bug.id }}</span>
                          <span class="bug-title">{{ bug.title }}</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="plan.bugs !== null && (!plan.bugs || plan.bugs.length === 0) && (!plan.children || plan.children.length === 0)" class="no-bugs-tip">
                      暂无缺陷
                    </div>
                  </div>
                  <div v-if="plan.expanded && plan.bugs === null" class="tree-children loading">
                    <span class="loading-text">加载中...</span>
                  </div>
                </div>
              </template>
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
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createTestCase, getTestCaseDetail, updateTestCase, deleteTestCase, getProjects, getProjectPlans, getPlanBugs, getProjectMembers, getCurrentUser } from '../api'

export default {
  name: 'NewTestCase',
  setup() {
    const route = useRoute()
    const router = useRouter()

    const projectId = route.query.project_id ? Number(route.query.project_id) : null
    const testcaseId = route.query.id ? Number(route.query.id) : null
    const isEdit = !!testcaseId

    const loading = ref(false)
    const saving = ref(false)
    const showRequiredOnly = ref(false)
    const showStatusDropdown = ref(false)
    const showAssigneeDropdown = ref(false)
    const showAddDefectDialog = ref(false)
    const activeTab = ref('basic')
    const preconditionsEditor = ref(null)
    const fileInput = ref(null)
    const commentEditor = ref(null)
    const commentEditorActive = ref(false)
    const defectSearchText = ref('')
    const bugPlans = ref([])

    const projectInfo = reactive({
      name: ''
    })

    const testcase = reactive({
      title: '',
      status: 'draft',
      case_type: '功能测试',
      priority: 'P3',
      test_type: '手动',
      preconditions: '',
      steps: [{ step: '', expected: '' }],
      remark: '',
      requirement_id: null,
      related_defects: [],
      baseline: '',
      estimated_time: 0,
      version: 'v1',
      plan_id: null,
      assignee: [],
      assignee_id: null,
      execution_result: '',
      associate_project: true,
      project_id: projectId,
      plan: 'unplanned',
      document_type: '',
      attachments: [],
      comment: ''
    })

    const currentUser = ref(null)
    const testcasePlans = ref([{ value: 'unplanned', label: '未计划', icon: '📋' }])
    const availableProjects = ref([])
    const projectMembers = ref([])
    const assigneeSearchText = ref('')
    const showPlanDropdown = ref(false)

    const availableStatuses = [
      { value: 'ready', label: '就绪' },
      { value: 'abandoned', label: '废弃' },
      { value: 'design', label: '设计' }
    ]

    const getStatusText = (status) => {
      const statusObj = availableStatuses.find(s => s.value === status)
      return statusObj ? statusObj.label : status
    }

    const getAssigneeDisplayText = () => {
      if (!testcase.assignee || testcase.assignee.length === 0) {
        return '未指派'
      }
      
      const ids = Array.isArray(testcase.assignee) ? testcase.assignee : [testcase.assignee]
      const names = ids.map(id => {
        const member = projectMembers.value.find(m => m.id.toString() === id.toString())
        return member ? member.name : id
      })
      
      if (names.length === 1) {
        return names[0]
      } else {
        return `${names[0]} 等 ${names.length} 人`
      }
    }

    const isAssigneeSelected = (assigneeValue) => {
      return testcase.assignee && testcase.assignee.includes(assigneeValue)
    }

    const toggleAssignee = (assigneeValue) => {
      if (!testcase.assignee) {
        testcase.assignee = []
      }
      
      const index = testcase.assignee.indexOf(assigneeValue)
      if (index > -1) {
        testcase.assignee.splice(index, 1)
      } else {
        testcase.assignee.push(assigneeValue)
      }
    }

    const togglePlanDropdown = () => {
      showPlanDropdown.value = !showPlanDropdown.value
    }

    const selectPlan = (planValue) => {
      testcase.plan = planValue
      testcase.plan_id = planValue === 'unplanned' ? null : planValue
      showPlanDropdown.value = false
    }

    const getSelectedPlanDisplayText = () => {
      if (!testcase.plan || testcase.plan === 'unplanned') {
        return '未计划'
      }
      const plan = testcasePlans.value.find(p => p.value === testcase.plan || p.value === testcase.plan.toString())
      return plan ? plan.label : testcase.plan
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
          const plans = allPlans.filter(p => p.plan_type === 'test_case')
          console.log('fetchProjectPlans: 过滤后的test_case类型计划:', plans)
          testcasePlans.value = [
            { value: 'unplanned', label: '未计划', icon: '📋' },
            ...plans.map(p => ({
              value: p.id.toString(),
              label: p.name,
              icon: '🧪'
            }))
          ]
          console.log('fetchProjectPlans: 最终testcasePlans:', testcasePlans.value)
        }
      } catch (error) {
        console.error('获取项目计划失败:', error)
      }
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

    const toggleRequiredOnly = () => {
      showRequiredOnly.value = !showRequiredOnly.value
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
      return testcase.related_defects.some(d => d.id.toString() === defectId)
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
      
      // 如果 planId 无效（如 'unplanned'），不传递 navigate_plan 参数
      if (!planId || planId === 'unplanned' || isNaN(parseInt(planId))) {
        console.log('navigateToDefect: 无有效计划ID，跳转到项目详情页')
        router.push(`/project-detail/${testcase.project_id}`)
        return
      }
      
      // 跳转到项目详情页，带上参数
      router.push(`/project-detail/${testcase.project_id}?navigate_plan=${planId}&navigate_bug=${bugId}`)
    }

    const searchDefects = async () => {
      try {
        console.log('搜索缺陷:', defectSearchText.value)
        // TODO: 调用搜索 API
      } catch (error) {
        console.error('搜索失败:', error)
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

    const togglePlanExpand = (planValue) => {
      const plan = findPlanById(bugPlans.value, planValue)
      if (plan) {
        plan.expanded = !plan.expanded
        // 如果第一次展开，加载 Bug 列表
        if (plan.expanded && plan.bugs === null) {
          loadBugsForPlan(planValue)
        }
      }
    }

    const fetchBugPlans = async (projectId) => {
      try {
        console.log('fetchBugPlans: 开始加载 Bug 计划，projectId:', projectId)
        const response = await getProjectPlans(projectId)
        console.log('fetchBugPlans: API 响应:', response.data)
        if (response.data.success) {
          const allPlans = response.data.plans || []
          
          // 递归处理计划树
          const processPlanTree = (plans) => {
            return plans.filter(p => p.plan_type === 'bug').map(p => ({
              value: p.id.toString(),
              label: p.name,
              icon: '📋',
              expanded: false,
              bugs: null,
              children: p.children && p.children.length > 0 ? processPlanTree(p.children) : []
            }))
          }
          
          bugPlans.value = processPlanTree(allPlans)
          console.log('fetchBugPlans: bugPlans 初始化完成:', bugPlans.value)
        }
      } catch (error) {
        console.error('获取 Bug 计划失败:', error)
      }
    }

    const loadBugsForPlan = async (planId) => {
      try {
        console.log('loadBugsForPlan: 加载计划下的 Bug, planId:', planId)
        const response = await getPlanBugs(planId)
        console.log('loadBugsForPlan: API 响应:', response.data)
        if (response.data.success) {
          const plan = findPlanById(bugPlans.value, planId)
          if (plan) {
            plan.bugs = response.data.bugs || []
          }
        }
        console.log('loadBugsForPlan: Bug 加载完成')
      } catch (error) {
        console.error('加载 Bug 失败:', error)
      }
    }

    const loadAllBugs = async () => {
      console.log('loadAllBugs: 刷新所有 Bug 列表')
      
      const loadBugsForExpandedPlans = async (plans) => {
        for (const plan of plans) {
          if (plan.expanded) {
            await loadBugsForPlan(plan.value)
          }
          if (plan.children && plan.children.length > 0) {
            await loadBugsForExpandedPlans(plan.children)
          }
        }
      }
      
      await loadBugsForExpandedPlans(bugPlans.value)
    }

    const commentText = computed(() => {
      if (!testcase.comment) return ''
      const tempDiv = document.createElement('div')
      tempDiv.innerHTML = testcase.comment
      return tempDiv.textContent || tempDiv.innerText || ''
    })

    const handleProjectChange = () => {
      const projectId = parseInt(testcase.project_id)
      if (projectId) {
        fetchProjectPlans(projectId)
        fetchProjectMembers(projectId)
      } else {
        testcasePlans.value = [{ value: 'unplanned', label: '未计划', icon: '📋' }]
        projectMembers.value = []
        testcase.assignee = []
      }
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

    const activateCommentEditor = () => {
      commentEditorActive.value = true
    }

    const deactivateCommentEditor = () => {
      commentEditorActive.value = false
    }

    const preventDeactivate = (event) => {
      event.stopPropagation()
    }

    const togglePenTool = () => {
      console.log('Toggle pen tool')
    }

    const formatText = (command) => {
      if (!commentEditor.value) return
      commentEditor.value.focus()
      
      switch (command) {
        case 'bold':
          document.execCommand('bold', false, null)
          break
        case 'italic':
          document.execCommand('italic', false, null)
          break
        case 'underline':
          document.execCommand('underline', false, null)
          break
        case 'unorderedList':
          document.execCommand('insertUnorderedList', false, null)
          break
        case 'orderedList':
          document.execCommand('insertOrderedList', false, null)
          break
      }
      
      updateComment()
    }

    const insertImage = () => {
      console.log('Insert image')
    }

    const insertLink = () => {
      console.log('Insert link')
    }

    const updateComment = () => {
      if (commentEditor.value) {
        testcase.comment = commentEditor.value.innerHTML
      }
    }

    const updatePreconditions = () => {
      if (preconditionsEditor.value) {
        testcase.preconditions = preconditionsEditor.value.innerHTML
      }
    }

    const formatPreconditions = (command) => {
      if (!preconditionsEditor.value) return
      
      preconditionsEditor.value.focus()
      
      switch (command) {
        case 'bold':
          document.execCommand('bold', false, null)
          break
        case 'italic':
          document.execCommand('italic', false, null)
          break
        case 'underline':
          document.execCommand('underline', false, null)
          break
        case 'strikeThrough':
          document.execCommand('strikeThrough', false, null)
          break
        case 'justifyLeft':
          document.execCommand('justifyLeft', false, null)
          break
        case 'justifyCenter':
          document.execCommand('justifyCenter', false, null)
          break
        case 'justifyRight':
          document.execCommand('justifyRight', false, null)
          break
        case 'insertUnorderedList':
          document.execCommand('insertUnorderedList', false, null)
          break
        case 'insertOrderedList':
          document.execCommand('insertOrderedList', false, null)
          break
        case 'undo':
          document.execCommand('undo', false, null)
          break
        case 'redo':
          document.execCommand('redo', false, null)
          break
        default:
          document.execCommand(command, false, null)
      }
      
      updatePreconditions()
    }

    const saveTestCase = async () => {
      if (!testcase.title.trim()) {
        alert('请输入测试用例标题')
        return
      }

      saving.value = true
      try {
        // 处理 related_defects：提取 bug id 数组
        const relatedDefectIds = testcase.related_defects.map(d => d.id)
        
        // 处理 assignee：取第一个作为 assignee_id
        const assigneeId = testcase.assignee && testcase.assignee.length > 0 
          ? testcase.assignee[0] 
          : testcase.assignee_id
        
        // 处理 plan：如果是 'unplanned' 则 plan_id 为 null
        const planId = testcase.plan && testcase.plan !== 'unplanned' 
          ? parseInt(testcase.plan) 
          : testcase.plan_id
        
        const payload = {
          title: testcase.title,
          status: testcase.status,
          case_type: testcase.case_type,
          priority: testcase.priority,
          test_type: testcase.test_type,
          preconditions: testcase.preconditions,
          steps: testcase.steps,
          remark: testcase.remark,
          requirement_id: testcase.requirement_id,
          related_defects: relatedDefectIds,
          baseline: testcase.baseline,
          estimated_time: testcase.estimated_time,
          version: testcase.version,
          plan_id: planId,
          project_id: projectId,
          assignee_id: assigneeId,
          execution_result: testcase.execution_result
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
        alert('保存失败')
      } finally {
        saving.value = false
      }
    }

    const goBack = () => {
      router.push(`/project-detail/${projectId}`)
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

    const fetchProjects = async () => {
      try {
        const response = await getProjects()
        if (response.data.success) {
          availableProjects.value = response.data.projects || []
          console.log('fetchProjects: 项目列表加载完成')
        }
      } catch (error) {
        console.error('获取项目列表失败:', error)
      }
    }

    onMounted(async () => {
      console.log('=== NewTestCase onMounted 开始 ===')
      console.log('route.query:', route.query)
      console.log('projectId:', projectId)
      console.log('testcase.project_id:', testcase.project_id)
      
      loading.value = true
      try {
        // 加载当前用户
        await fetchCurrentUser()
        
        // 加载项目列表
        await fetchProjects()
        
        // 如果有项目 ID，加载项目相关数据
        if (testcase.project_id) {
          console.log('开始加载项目相关数据, project_id:', testcase.project_id)
          await fetchProjectPlans(testcase.project_id)
          await fetchProjectMembers(testcase.project_id)
        } else {
          console.warn('没有project_id，跳过加载计划和成员')
        }
        
        // 加载项目信息和计划列表
        // 简化处理，实际应调用API
        projectInfo.name = '项目名称'
        
        // 如果是编辑模式，加载测试用例详情
        if (isEdit) {
          const response = await getTestCaseDetail(testcaseId)
          console.log('loadTestCase: 响应:', response)
          if (response.success || (response.data && response.data.success)) {
            const data = response.testcase || response.data.testcase
            // 基本字段赋值
            testcase.title = data.title || ''
            testcase.status = data.status || 'draft'
            testcase.case_type = data.case_type || '功能测试'
            testcase.priority = data.priority || 'P3'
            testcase.test_type = data.test_type || '手动'
            testcase.preconditions = data.preconditions || ''
            testcase.steps = data.steps || [{ step: '', expected: '' }]
            testcase.remark = data.remark || ''
            testcase.requirement_id = data.requirement_id
            testcase.baseline = data.baseline || ''
            testcase.estimated_time = data.estimated_time || 0
            testcase.version = data.version || 'v1'
            testcase.plan_id = data.plan_id
            testcase.project_id = data.project_id
            testcase.execution_result = data.execution_result || ''
            
            // 处理负责人
            if (data.assignee_id) {
              testcase.assignee = [data.assignee_id.toString()]
              testcase.assignee_id = data.assignee_id
            }
            
            // 处理所属计划
            if (data.plan_id) {
              testcase.plan = data.plan_id.toString()
            }
            
            // 处理关联缺陷：后端返回的是 [id1, id2]，前端需要 [{id, title}]
            if (data.related_defects && Array.isArray(data.related_defects)) {
              testcase.related_defects = data.related_defects.map(id => ({
                id: typeof id === 'object' ? id.id : id,
                title: typeof id === 'object' ? id.title : `Bug-${id}`
              }))
            }
          }
        }
      } catch (error) {
        console.error('加载失败:', error)
      } finally {
        loading.value = false
        console.log('=== NewTestCase onMounted 完成 ===')
      }
    })

    return {
      loading,
      saving,
      showRequiredOnly,
      showStatusDropdown,
      showAssigneeDropdown,
      showAddDefectDialog,
      activeTab,
      projectInfo,
      testcase,
      currentUser,
      testcasePlans,
      availableProjects,
      projectMembers,
      assigneeSearchText,
      showPlanDropdown,
      bugPlans,
      defectSearchText,
      availableStatuses,
      isEdit,
      getStatusText,
      getAssigneeDisplayText,
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
      searchDefects,
      togglePlanExpand,
      loadAllBugs,
      toggleStatusDropdown,
      selectStatus,
      toggleAssigneeDropdown,
      toggleRequiredOnly,
      addStep,
      removeStep,
      removeDefect,
      updatePreconditions,
      formatPreconditions,
      preconditionsEditor,
      fileInput,
      commentEditor,
      commentEditorActive,
      commentText,
      handleProjectChange,
      copyDocumentLink,
      addAttachment,
      removeAttachment,
      handleFileUpload,
      activateCommentEditor,
      deactivateCommentEditor,
      preventDeactivate,
      togglePenTool,
      formatText,
      insertImage,
      insertLink,
      updateComment,
      saveTestCase,
      goBack
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
  overflow: hidden;
}

.content-left {
  flex: 1;
  background: #fff;
  padding: 24px;
  overflow-y: auto;
}

.sidebar-right {
  width: 320px;
  background: #fff;
  border-left: 1px solid #e9ecef;
  overflow-y: auto;
  padding: 24px;
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
  flex-wrap: wrap;
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

.field-select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
}

/* 保存按钮样式 */
.save-actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-save,
.btn-cancel {
  padding: 12px 24px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  font-weight: 500;
}

.btn-save {
  background: #409eff;
  color: #fff;
}

.btn-save:hover {
  background: #66b1ff;
}

.btn-save:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}

.btn-cancel {
  background: #fff;
  border: 1px solid #dcdfe6;
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
  overflow: hidden;
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
  
  .sidebar-right {
    width: 100%;
    border-left: none;
    border-top: 1px solid #e9ecef;
  }
  
  .status-section {
    flex-direction: column;
    gap: 12px;
  }
}

@media (min-width: 769px) {
  .main-content {
    flex-direction: row !important;
  }
  
  .sidebar-right {
    width: 320px !important;
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

.btn-cancel,
.btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-cancel {
  background: #fff;
  border: 1px solid #dcdfe6;
  color: #606266;
}

.btn-cancel:hover {
  background: #f5f7fa;
}

.btn-confirm {
  background: #409eff;
  color: #fff;
}

.btn-confirm:hover {
  background: #66b1ff;
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
</style>
