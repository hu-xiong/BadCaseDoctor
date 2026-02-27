<template>
  <div class="badcase-detail-wrapper">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载项目信息...</div>
    </div>
    
    <!-- 顶部标题栏 -->
    <div class="header-bar">
      <div class="header-left">
        <span class="back-arrow" @click="goBack">←</span>
        <span class="header-title">{{ isEdit ? '编辑BadCase' : '新建BadCase' }}</span>
        <span class="project-name" v-if="projectInfo.name">/ {{ projectInfo.name }}</span>
      </div>
      <div class="header-right">
        <button class="header-btn" @click="toggleRequiredOnly">
          <span class="checkbox-icon" :class="{ checked: showRequiredOnly }">✓</span>
          只看必填项
        </button>
        <button class="header-btn">
          <span class="gear-icon">⚙</span>
          配置
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
                      <div class="assignee-name">{{ currentUser.name }}</div>
                      <div class="assignee-id">({{ currentUser.email }})</div>
                      <div class="assignee-dept">{{ currentUser.department || '未设置部门' }}</div>
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
                      <div class="assignee-name">{{ assignee.name }}</div>
                      <div class="assignee-id">({{ assignee.id }})</div>
                      <div class="assignee-dept">{{ assignee.department }}</div>
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
                      <div class="assignee-name">{{ member.name }}</div>
                      <div class="assignee-id">({{ member.email }})</div>
                      <div class="assignee-dept">{{ member.role }} - {{ member.source }}</div>
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
                  <div class="debug-info">
                    <small>调试信息: 项目ID {{ badcase.project_id }}, projectMembers长度: {{ projectMembers.length }}</small>
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
                
                <!-- 调试信息 -->
                <div class="debug-section" style="padding: 8px; background: #f0f0f0; margin: 8px 0; border-radius: 4px; font-size: 12px; color: #666;">
                  <div>调试信息:</div>
                  <div>项目ID: {{ badcase.project_id || '未选择' }}</div>
                  <div>项目成员数量: {{ projectMembers.length }}</div>
                  <div>项目成员数据: {{ JSON.stringify(projectMembers) }}</div>
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
                  所属计划 {{ getSelectedPlanDisplayText() }}
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
                        'selected': badcase.plan === plan.value, 
                        'expandable': plan.children && plan.children.length > 0,
                        'pinned': plan.is_pinned,
                        'unplanned': plan.value === 'unplanned'
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
                          'selected': badcase.plan === childPlan.value,
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
                            :class="{ 'selected': badcase.plan === grandChildPlan.value }"
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
        
        <!-- 相似问题 -->
        <div class="problem-section">
          <h3 class="problem-title">相似问题:</h3>
          <textarea 
            v-model="badcase.base_problem" 
            class="problem-textarea" 
            placeholder="请详细描述相似问题..."
            maxlength="500"
            required
          ></textarea>
          <div class="problem-count">{{ badcase.base_problem.length }} / 500</div>
        </div>
                
        <!-- 复现步骤编辑器 -->
        <div class="editor-section">
          <div class="editor-toolbar">
            <button class="toolbar-btn" title="插入" @click="addAttachment">📎</button>
            <button class="toolbar-btn" title="撤销" @click="formatSteps('undo')">↶</button>
            <button class="toolbar-btn" title="重做" @click="formatSteps('redo')">↷</button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" title="粗体" @click="formatSteps('bold')">B</button>
            <button class="toolbar-btn" title="斜体" @click="formatSteps('italic')">I</button>
            <button class="toolbar-btn" title="下划线" @click="formatSteps('underline')">U</button>
            <button class="toolbar-btn" title="删除线" @click="formatSteps('strikeThrough')">S</button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" title="左对齐" @click="formatSteps('justifyLeft')">⫷</button>
            <button class="toolbar-btn" title="居中" @click="formatSteps('justifyCenter')">⫸</button>
            <button class="toolbar-btn" title="右对齐" @click="formatSteps('justifyRight')">⫹</button>
            <button class="toolbar-btn" title="两端对齐" @click="formatSteps('justifyFull')">⫺</button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" title="无序列表" @click="formatSteps('insertUnorderedList')">•</button>
            <button class="toolbar-btn" title="有序列表" @click="formatSteps('insertOrderedList')">1.</button>
            <button class="toolbar-btn" title="链接" @click="insertStepsLink">🔗</button>
            <button class="toolbar-btn" title="图片" @click="insertStepsImage">🖼</button>
            <button class="toolbar-btn" title="表格" @click="insertStepsTable">⊞</button>
            <button class="toolbar-btn" title="更多" @click="showMoreOptions">⋯</button>
          </div>
                
          <div class="editor-content">
            <h3 class="editor-title">BadCase复现步骤:</h3>
            <div 
              ref="stepsEditor" 
              class="editor-textarea" 
              contenteditable="true"
              @input="updateSteps"
              placeholder="请详细描述BadCase的复现步骤..."
            ></div>
            <div class="editor-count">{{ stepsLength }} / 2000</div>
          </div>
        </div>
        
        <!-- 答案输入框 -->
        <div class="answer-section">
          <h3 class="answer-title">答案:</h3>
          <textarea 
            v-model="badcase.correct_answer" 
            class="answer-textarea" 
            placeholder="请输入答案..."
            maxlength="1000"
          ></textarea>
          <div class="answer-count">{{ badcase.correct_answer.length }} / 1000</div>
        </div>
        
        <!-- 正确答案输入框 -->
        <div class="correct-answer-section">
          <h3 class="correct-answer-title">正确答案:</h3>
          <textarea 
            v-model="badcase.correct_answer_final" 
            class="correct-answer-textarea" 
            placeholder="请输入正确答案..."
            maxlength="1000"
          ></textarea>
          <div class="correct-answer-count">{{ badcase.correct_answer_final.length }} / 1000</div>
        </div>
                
        <!-- 问题分类和优先级 -->
        <div class="category-section">
          <div class="form-row">
            <label class="form-label required">问题分类:</label>
            <select v-model="badcase.case_category" class="form-select">
              <option value="">请选择问题分类</option>
              <option value="功能缺陷">功能缺陷</option>
              <option value="性能问题">性能问题</option>
              <option value="界面问题">界面问题</option>
              <option value="兼容性问题">兼容性问题</option>
              <option value="安全问题">安全问题</option>
              <option value="其他">其他</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label required">优先级:</label>
            <select v-model="badcase.priority" class="form-select">
              <option value="">请选择优先级</option>
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
                
      <!-- 右侧边栏 -->
      <div class="sidebar-right">
        <!-- 所属项目 -->
        <div class="sidebar-section">
          <h3 class="sidebar-title">所属项目</h3>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" v-model="badcase.associate_project" :value="true" />
              <span class="radio-text">关联所属项目</span>
            </label>
            <label class="radio-item">
              <input type="radio" v-model="badcase.associate_project" :value="false" />
              <span class="radio-text">暂不关联所属项目</span>
            </label>
          </div>
          <div v-if="badcase.associate_project" class="project-select">
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
             >{{ commentText }}</textarea>
             <div v-if="!commentEditorActive" class="comment-count">{{ commentText.length }} / 500</div>
             
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
                   <span class="image-icon">🏔️</span>
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
               <div class="editor-count">{{ commentText.length }} / 500</div>
             </div>
           </div>
         </div>
      </div>
    </div>
    

  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { createBadcase, getBadcaseDetail, updateBadcase, getProjects, getProjectPlans, getProjectMembers, getCurrentUser } from '../api.js'
import user from '../store/user.js'


export default {
  name: 'NewBadcase',
  setup() {
    const router = useRouter()
    const route = useRoute()
    const loading = ref(false)
    const saveLoading = ref(false)
    const isEdit = ref(false)
    const badcaseId = ref(null)
    const showRequiredOnly = ref(false)
    
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
    
    // 最近选择的用户列表（暂时为空，后续可以从历史记录中获取）
    const recentAssignees = ref([])
    
    const assigneeSearchText = ref('')
    const planSearchText = ref('')
    const showPlanDropdown = ref(false)
    
    // 已展开的计划ID列表
    const expandedPlans = ref([])
    
    // 可用计划列表 - 将从当前项目动态获取
    const availablePlans = ref([
      // 默认显示"未计划"选项，确保下拉框至少有一个选项
      { value: 'unplanned', label: '未计划', icon: '📋' },
      // 临时添加一些测试数据，确保下拉框能正常显示
      { value: 'test1', label: '测试计划1', icon: '📁' },
      { value: 'test2', label: '测试计划2', icon: '📁' }
    ])
    
    // 过滤后的计划列表（用于搜索）
    const filteredPlans = computed(() => {
      const searchText = planSearchText.value.toLowerCase().trim()
      console.log('filteredPlans计算属性被调用，searchText:', searchText)
      console.log('availablePlans.value:', availablePlans.value)
      
      if (!searchText) {
        console.log('没有搜索文本，返回所有计划:', availablePlans.value)
        return availablePlans.value
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
      
      const result = searchPlansRecursively(availablePlans.value)
      console.log('搜索结果:', result)
      return result
    })
    
    const badcase = reactive({
      title: '',
      case_category: '',
      base_problem: '',
      badcase_result: '',
      correct_answer: '',
      correct_answer_final: '',
      problem_reason: '',
      solution: '',
      priority: '',
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

    // 获取状态文本
    const getStatusText = (status) => {
      const statusMap = {
        'new': '新建'
      }
      return statusMap[status] || status
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
          // 清空计划选择
          badcase.plan = ''
          // 清空负责人选择
          badcase.assignee = []
          // 重置计划列表
          availablePlans.value = [
            { value: 'unplanned', label: '未计划', icon: '📋' }
          ]
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
    
    // 获取可用项目列表
    const fetchProjects = async () => {
      try {
        const response = await getProjects()
        if (response.data.success) {
          availableProjects.value = response.data.projects || []
          console.log('fetchProjects: 项目列表加载完成')
          console.log('项目数量:', availableProjects.value.length)
          console.log('项目数据结构:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
        }
      } catch (error) {
        console.error('获取项目列表失败:', error)
      }
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
    const getSelectedPlanDisplayText = () => {
      console.log('getSelectedPlanDisplayText: badcase.plan =', badcase.plan)
      console.log('getSelectedPlanDisplayText: availablePlans =', availablePlans.value)
      
      if (!badcase.plan || badcase.plan === 'unplanned') {
        return '未选择计划'
      }
      
      // 查找选中的计划
      const findPlan = (plans, planId) => {
        for (const plan of plans) {
          if (plan.value === planId) {
            return plan.label
          }
          if (plan.children && plan.children.length > 0) {
            const found = findPlan(plan.children, planId)
            if (found) return found
          }
        }
        return null
      }
      
      const planName = findPlan(availablePlans.value, badcase.plan)
      console.log('getSelectedPlanDisplayText: 找到的计划名称 =', planName)
      return planName || '未选择计划'
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
          const plans = response.data.plans || []
          console.log('获取到的原始计划数据:', plans)
          console.log('计划数量:', plans.length)
          
          // 转换计划数据格式：第一个是"未计划"，后面是项目实际计划
          const formattedPlans = [
            { value: 'unplanned', label: '未计划', icon: '📋' }
          ]
          
          // 递归处理项目计划树，保持树结构
          const processPlans = (planList, level = 0) => {
            const processedPlans = []
            planList.forEach(plan => {
              console.log(`处理计划: ${plan.name} (ID: ${plan.id}, 状态: ${plan.status}, 类型: ${plan.plan_type})`)
              // 只显示进行中的计划，且必须是 badcase 类型计划
              if (plan.status === 'active') {
                // 如果是 badcase 类型计划，或者是包含 badcase 类型子计划的父计划
                const children = plan.children && plan.children.length > 0 ? processPlans(plan.children, level + 1) : []
                
                if (plan.plan_type === 'badcase' || children.length > 0) {
                  const planOption = {
                    value: plan.id.toString(),
                    label: plan.name,
                    level: level,
                    is_pinned: plan.is_pinned || false,
                    icon: plan.icon || '📁',
                    plan_type: plan.plan_type,
                    badcase_count: plan.badcase_count || 0
                  }
                  
                  if (children.length > 0) {
                    planOption.children = children
                  }
                  
                  processedPlans.push(planOption)
                  console.log(`添加计划: ${plan.name} (类型: ${plan.plan_type})`)
                } else {
                  console.log(`跳过计划: ${plan.name} (非badcase类型且无badcase子计划)`)
                }
              }
            })
            return processedPlans
          }
          
          // 添加项目实际计划（保持树结构）
          const projectPlans = processPlans(plans)
          console.log('处理后的项目计划:', projectPlans)
          
          formattedPlans.push(...projectPlans)
          availablePlans.value = formattedPlans
          
          console.log('=== 最终的计划选项 ===')
          console.log('availablePlans:', availablePlans.value)
          console.log('filteredPlans计算值:', filteredPlans.value)
          console.log('计划总数:', availablePlans.value.length)
          
          // 强制触发响应式更新
          await nextTick()
        } else {
          console.error('API返回失败:', response.data)
          // 如果API失败，至少显示"未计划"选项
          availablePlans.value = [
            { value: 'unplanned', label: '未计划', icon: '📋' }
          ]
        }
      } catch (error) {
        console.error('获取项目计划失败:', error)
        // 如果获取失败，至少显示"未计划"选项
        availablePlans.value = [
          { value: 'unplanned', label: '未计划', icon: '📋' }
        ]
      }
    }
    
    // 初始化BadCase数据
    const initBadcase = async () => {
      try {
        const query = route.query
        console.log('=== 初始化BadCase开始 ===')
        console.log('路由查询参数:', query)
        
        if (query.edit === 'true' && query.id) {
          console.log('编辑模式，BadCase ID:', query.id)
          isEdit.value = true
          badcaseId.value = query.id
          loading.value = true
        
        try {
          const response = await getBadcaseDetail(query.id)
          if (response.data.success && response.data.badcase) {
            console.log('=== BadCase详情API响应 ===')
            console.log('完整响应:', response.data)
            console.log('BadCase数据:', response.data.badcase)
            console.log('复现步骤字段:', response.data.badcase.reproduction_steps)
            console.log('复现步骤类型:', typeof response.data.badcase.reproduction_steps)
            
            Object.assign(badcase, response.data.badcase)
            console.log('BadCase信息加载成功:', badcase)
            console.log('加载后的复现步骤:', badcase.reproduction_steps)
            console.log('原始数据中的项目ID:', response.data.badcase.project_id, '类型:', typeof response.data.badcase.project_id)
            console.log('原始数据中的计划ID:', response.data.badcase.plan, '类型:', typeof response.data.badcase.plan)
            
            // 确保数据类型一致
            if (badcase.project_id) {
              badcase.project_id = badcase.project_id.toString()
              console.log('编辑模式：项目ID类型转换后:', badcase.project_id, '类型:', typeof badcase.project_id)
            }
            
            if (badcase.plan) {
              badcase.plan = badcase.plan.toString()
              console.log('编辑模式：计划ID类型转换后:', badcase.plan, '类型:', typeof badcase.plan)
            }
            
            // 确保编辑模式下正确设置关联项目状态
            if (badcase.project_id) {
              badcase.associate_project = true
              console.log('编辑模式：设置associate_project为true，项目ID:', badcase.project_id)
              
              // 初始化_previousProjectId，避免handleProjectChange误判
              badcase._previousProjectId = badcase.project_id
              console.log('编辑模式：初始化_previousProjectId:', badcase._previousProjectId)
            }
            
            // 评论内容会在激活编辑器时设置
            
            // 设置步骤编辑器内容
            if (stepsEditor.value && badcase.reproduction_steps) {
              console.log('设置步骤编辑器内容:', badcase.reproduction_steps)
              stepsEditor.value.innerHTML = badcase.reproduction_steps
            } else {
              console.log('步骤编辑器或复现步骤为空')
              console.log('stepsEditor.value:', stepsEditor.value)
              console.log('badcase.reproduction_steps:', badcase.reproduction_steps)
            }
            
            // 延迟设置编辑器内容，确保DOM已准备好
            setTimeout(() => {
              if (stepsEditor.value && badcase.reproduction_steps) {
                console.log('延迟设置步骤编辑器内容:', badcase.reproduction_steps)
                stepsEditor.value.innerHTML = badcase.reproduction_steps
              }
            }, 200)
            
            // 获取项目计划列表和成员列表（编辑模式）
            if (badcase.project_id) {
              console.log('编辑模式，获取项目计划，项目ID:', badcase.project_id)
              
              // 确保项目列表已加载
              if (availableProjects.value.length === 0) {
                console.log('编辑模式：项目列表为空，先加载项目列表')
                await fetchProjects()
              }
              
              // 设置项目信息
              const project = availableProjects.value.find(p => p.id == badcase.project_id)
              if (project) {
                projectInfo.value = project
                console.log('编辑模式：设置项目信息:', project.name)
              } else {
                console.log('编辑模式：未找到项目信息，availableProjects:', availableProjects.value)
                console.log('尝试查找项目，badcase.project_id:', badcase.project_id)
                console.log('availableProjects中的项目ID类型:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
              }
              
              // 等待数据加载完成
              await Promise.all([
                fetchProjectPlans(badcase.project_id),
                fetchProjectMembers(badcase.project_id)
              ])
              
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
        }
      } else if (query.project_id) {
        console.log('新建模式，项目ID:', query.project_id)
        console.log('query.project_id类型:', typeof query.project_id)
        console.log('availableProjects:', availableProjects.value)
        
        // 新建模式，设置项目ID
        badcase.project_id = query.project_id
        console.log('设置badcase.project_id:', badcase.project_id)
        console.log('设置后badcase.project_id类型:', typeof badcase.project_id)
        
        // 获取项目信息
        const project = availableProjects.value.find(p => p.id == query.project_id)
        if (project) {
          projectInfo.value = project
          console.log('找到项目信息:', project.name)
        } else {
          console.log('未找到项目信息，availableProjects:', availableProjects.value)
          console.log('尝试查找项目，query.project_id:', query.project_id)
          console.log('availableProjects中的项目ID类型:', availableProjects.value.map(p => ({ id: p.id, type: typeof p.id, name: p.name })))
        }
        
        // 获取当前项目的计划列表和成员列表
        console.log('开始获取项目计划，项目ID:', query.project_id)
        await fetchProjectPlans(query.project_id)
        await fetchProjectMembers(query.project_id)
        
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
      
      // 在保存前更新复现步骤
      if (stepsEditor.value) {
        const editorContent = stepsEditor.value.innerHTML.trim()
        console.log('编辑器内容:', editorContent)
        if (editorContent && editorContent !== '<br>') {
          badcase.reproduction_steps = editorContent
          console.log('从编辑器更新复现步骤:', badcase.reproduction_steps)
        }
      }
      
      if (!badcase.title.trim()) {
        alert('请输入BadCase标题')
        return
      }
      if (!badcase.case_category) {
        alert('请选择问题分类')
        return
      }
      if (!badcase.base_problem.trim()) {
        alert('请输入相似问题')
        return
      }
      if (!badcase.priority) {
        alert('请选择优先级')
        return
      }
      
      // 检查复现步骤是否为空
      if (!badcase.reproduction_steps || !badcase.reproduction_steps.trim()) {
        // 尝试从编辑器获取内容
        if (stepsEditor.value) {
          const editorContent = stepsEditor.value.innerHTML.trim()
          if (editorContent && editorContent !== '<br>') {
            badcase.reproduction_steps = editorContent
            console.log('从编辑器获取复现步骤:', badcase.reproduction_steps)
          } else {
            alert('请输入复现步骤')
            return
          }
        } else {
          alert('请输入复现步骤')
          return
        }
      }

      saveLoading.value = true
      try {
        const badcaseData = {
          title: badcase.title,
          case_category: badcase.case_category,
          base_problem: badcase.base_problem || '',
          reproduction_steps: badcase.reproduction_steps || '',
          badcase_result: badcase.badcase_result || '待确认',
          correct_answer: badcase.correct_answer || '待确认',
          correct_answer_final: badcase.correct_answer_final || '待确认',
          problem_reason: badcase.problem_reason || '',
          solution: badcase.solution || '',
          priority: badcase.priority,
          status: badcase.status,
          assignee: Array.isArray(badcase.assignee) ? badcase.assignee.join(',') : badcase.assignee,
          plan: badcase.plan,
          project_id: badcase.project_id,
          assigned_users: Array.isArray(badcase.assigned_users) ? badcase.assigned_users.join(',') : badcase.assigned_users,
          document_type: badcase.document_type,
          attachments: badcase.attachments.map(att => ({
            name: att.name,
            size: att.size
          }))
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

    // 切换必填项显示
    const toggleRequiredOnly = () => {
      showRequiredOnly.value = !showRequiredOnly.value
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

    // 富文本编辑器方法
    const commentEditor = ref(null)
    const stepsEditor = ref(null)
    const fileInput = ref(null)
    const commentEditorActive = ref(false)
    
    // 计算步骤编辑器字符长度
    const stepsLength = computed(() => {
      if (!stepsEditor.value) return 0
      return stepsEditor.value.innerText.length
    })
    
    // 计算评论文本（去除HTML标签）
    const commentText = computed(() => {
      if (!badcase.comment) return ''
      // 创建一个临时div来解析HTML并获取纯文本
      const tempDiv = document.createElement('div')
      tempDiv.innerHTML = badcase.comment
      return tempDiv.textContent || tempDiv.innerText || ''
    })

    // 切换画笔工具
    const togglePenTool = () => {
      // 实现画笔功能
      console.log('切换画笔工具')
    }

    // 格式化文本
    const formatText = (command) => {
      if (!commentEditor.value) return
      
      // 确保编辑器获得焦点
      commentEditor.value.focus()
      
      // 执行格式化命令
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
        default:
          document.execCommand(command, false, null)
      }
      
      // 更新内容
      updateComment()
    }

    // 插入图片
    const insertImage = () => {
      if (!commentEditor.value) return
      
      commentEditor.value.focus()
      const url = prompt('请输入图片URL:')
      if (url) {
        document.execCommand('insertImage', false, url)
        updateComment()
      }
    }

    // 插入链接
    const insertLink = () => {
      if (!commentEditor.value) return
      
      commentEditor.value.focus()
      const url = prompt('请输入链接URL:')
      if (url) {
        document.execCommand('createLink', false, url)
        updateComment()
      }
    }

    // 激活评论编辑器
    const activateCommentEditor = () => {
      commentEditorActive.value = true
      // 在下一个tick中设置编辑器内容
      nextTick(() => {
        if (commentEditor.value) {
          // 如果有HTML内容，直接使用；否则使用纯文本
          if (badcase.comment && badcase.comment.includes('<')) {
            commentEditor.value.innerHTML = badcase.comment
          } else {
            commentEditor.value.textContent = badcase.comment || ''
          }
          commentEditor.value.focus()
        }
      })
    }
    
    // 停用评论编辑器
    const deactivateCommentEditor = () => {
      // 延迟停用，避免点击工具栏按钮时立即停用
      setTimeout(() => {
        // 检查是否真的失去了焦点（不是点击了工具栏）
        if (!commentEditor.value || !commentEditor.value.contains(document.activeElement)) {
          // 保存当前内容
          if (commentEditor.value) {
            badcase.comment = commentEditor.value.innerHTML
          }
          commentEditorActive.value = false
        }
      }, 100)
    }
    
    // 防止编辑器停用
    const preventDeactivate = () => {
      // 阻止停用
    }
    
    // 更新评论内容
    const updateComment = () => {
      if (commentEditor.value) {
        badcase.comment = commentEditor.value.innerHTML
      }
    }
    
    // 更新步骤内容
    const updateSteps = () => {
      if (stepsEditor.value) {
        badcase.reproduction_steps = stepsEditor.value.innerHTML
      }
    }
    
    // 格式化步骤编辑器
    const formatSteps = (command) => {
      if (!stepsEditor.value) return
      
      // 确保编辑器获得焦点
      stepsEditor.value.focus()
      
      // 执行格式化命令
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
        case 'justifyFull':
          document.execCommand('justifyFull', false, null)
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
      
      // 更新内容
      updateSteps()
    }
    
    // 插入步骤链接
    const insertStepsLink = () => {
      if (!stepsEditor.value) return
      
      stepsEditor.value.focus()
      const url = prompt('请输入链接URL:')
      if (url) {
        document.execCommand('createLink', false, url)
        updateSteps()
      }
    }
    
    // 插入步骤图片
    const insertStepsImage = () => {
      if (!stepsEditor.value) return
      
      stepsEditor.value.focus()
      const url = prompt('请输入图片URL:')
      if (url) {
        document.execCommand('insertImage', false, url)
        updateSteps()
      }
    }
    
    // 插入步骤表格
    const insertStepsTable = () => {
      if (!stepsEditor.value) return
      
      stepsEditor.value.focus()
      const rows = prompt('请输入表格行数:', '3')
      const cols = prompt('请输入表格列数:', '3')
      if (rows && cols) {
        const table = document.createElement('table')
        table.style.border = '1px solid #ccc'
        table.style.borderCollapse = 'collapse'
        
        for (let i = 0; i < parseInt(rows); i++) {
          const tr = document.createElement('tr')
          for (let j = 0; j < parseInt(cols); j++) {
            const td = document.createElement('td')
            td.style.border = '1px solid #ccc'
            td.style.padding = '4px'
            td.textContent = `单元格 ${i+1}-${j+1}`
            tr.appendChild(td)
          }
          table.appendChild(tr)
        }
        
        document.execCommand('insertHTML', false, table.outerHTML)
        updateSteps()
      }
    }
    
    // 显示更多选项
    const showMoreOptions = () => {
      alert('更多功能开发中...')
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
      if (!badcase.assignee || badcase.assignee.length === 0) {
        return '未指派'
      }
      
      // 如果assignee是字符串（单个值），直接返回
      if (typeof badcase.assignee === 'string') {
        return badcase.assignee
      }
      
      // 如果是数组
      if (Array.isArray(badcase.assignee)) {
        if (badcase.assignee.length === 1) {
          return badcase.assignee[0]
        } else {
          return `${badcase.assignee.length}...`
        }
      }
      
      return badcase.assignee
    }

    // 检查负责人是否被选中
    const isAssigneeSelected = (assigneeValue) => {
      return badcase.assignee && badcase.assignee.includes(assigneeValue)
    }

    // 切换负责人选择状态
    const toggleAssignee = (assigneeValue) => {
      if (!badcase.assignee) {
        badcase.assignee = []
      }
      
      const index = badcase.assignee.indexOf(assigneeValue)
      if (index > -1) {
        badcase.assignee.splice(index, 1)
      } else {
        badcase.assignee.push(assigneeValue)
      }
    }

    // 切换计划下拉框显示
    const togglePlanDropdown = () => {
      showPlanDropdown.value = !showPlanDropdown.value
    }

    // 选择计划
    const selectPlan = (planValue) => {
      badcase.plan = planValue
      showPlanDropdown.value = false
    }

    // 返回上一页
    const goBack = () => {
      // 如果有项目ID和计划ID，返回到项目详情页并展开对应计划
      if (badcase.project_id) {
        const targetUrl = `/project-detail/${badcase.project_id}`
        // 如果有计划ID，添加到URL参数中，让ProjectDetail自动展开
        if (badcase.plan && badcase.plan !== 'unplanned') {
          router.push(`${targetUrl}?expand_plan=${badcase.plan}`)
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
        // 先获取当前用户信息
        console.log('开始获取当前用户信息...')
        await fetchCurrentUser()
        console.log('当前用户信息获取完成')
        
        // 再获取项目列表
        console.log('开始获取项目列表...')
        await fetchProjects()
        console.log('项目列表获取完成，数量:', availableProjects.value.length)
        console.log('项目列表:', availableProjects.value)
        
        // 等待一下确保数据完全加载
        await new Promise(resolve => setTimeout(resolve, 100))
        
        // 然后初始化BadCase
        console.log('开始初始化BadCase...')
        await initBadcase()
        console.log('BadCase初始化完成')
        
        // 等待DOM更新完成后再设置步骤编辑器内容
        await nextTick()
        console.log('DOM更新完成，开始设置编辑器内容')
        console.log('stepsEditor.value:', stepsEditor.value)
        console.log('badcase.reproduction_steps:', badcase.reproduction_steps)
        
        if (stepsEditor.value && badcase.reproduction_steps) {
          console.log('设置步骤编辑器内容:', badcase.reproduction_steps)
          stepsEditor.value.innerHTML = badcase.reproduction_steps
        } else {
          console.log('编辑器或复现步骤为空，无法设置内容')
        }
        
        // 添加一个监听器，当复现步骤变化时自动更新编辑器
        const checkAndUpdateEditor = () => {
          if (stepsEditor.value && badcase.reproduction_steps) {
            console.log('检查并更新步骤编辑器内容:', badcase.reproduction_steps)
            stepsEditor.value.innerHTML = badcase.reproduction_steps
          }
        }
        
        // 延迟检查并更新编辑器内容
        setTimeout(checkAndUpdateEditor, 500)
        setTimeout(checkAndUpdateEditor, 1000)
        
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
      badcase,
      projectInfo,
      availableProjects,
      projectMembers,
      showRequiredOnly,
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
      saveBadcase,
      toggleRequiredOnly,
      toggleStatusDropdown,
      selectStatus,
      handleProjectChange,
      toggleAssigneeDropdown,
      getAssigneeDisplayText,
      isAssigneeSelected,
      toggleAssignee,
      togglePlanDropdown,
      selectPlan,
      searchPlans,
      clearPlanSearch,
      getSelectedPlanDisplayText,
      refreshProjectPlans,
      togglePlanExpansion,
      goBack,
      copyDocumentLink,
      addAttachment,
      handleFileUpload,
      removeAttachment,
      commentEditor,
      stepsEditor,
      fileInput,
      stepsLength,
      commentText,
      commentEditorActive,
      togglePenTool,
      formatText,
      formatSteps,
      insertImage,
      insertLink,
      insertStepsLink,
      insertStepsImage,
      insertStepsTable,
      showMoreOptions,
      activateCommentEditor,
      deactivateCommentEditor,
      preventDeactivate,
      updateComment,
      updateSteps
    }
  }
}
</script>

<style scoped>
.badcase-detail-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f9fa;
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
  overflow: hidden;
}

/* 左侧内容区 */
.content-left {
  flex: 1;
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

.editor-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}

.editor-textarea {
  width: 100%;
  min-height: 200px;
  border: none;
  outline: none;
  resize: vertical;
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
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 24px;
  border-top: 1px solid #e9ecef;
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

/* 右侧边栏 */
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

@media (max-width: 768px) {
  .header-bar {
    padding: 12px 16px;
  }
  
  .content-left {
    margin: 8px;
    padding: 16px;
  }
  
  .sidebar-right {
    padding: 16px;
  }
  
  .title-input {
    font-size: 20px;
  }
}

/* 开发者工具打开时的布局优化 */
@media (max-width: 1200px) and (min-width: 769px) {
  .sidebar-right {
    width: 280px;
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
  
  .sidebar-right {
    width: 320px !important;
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
</style> 