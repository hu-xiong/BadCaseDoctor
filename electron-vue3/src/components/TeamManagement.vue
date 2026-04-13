<template>
  <div class="team-management">
    <div class="header" :class="{ 'header-compact': hideTopHeading }">
      <h2 v-if="!hideTopHeading">团队管理</h2>
      <button class="create-team-btn" @click="showCreateTeamModal = true">
        <span class="plus-icon">+</span>
        创建团队
      </button>
    </div>

    <!-- 团队列表 -->
    <div class="teams-container">
      <div v-if="teams.length === 0" class="no-teams">
        <div class="no-teams-icon">👥</div>
        <div class="no-teams-text">暂无团队</div>
        <div class="no-teams-desc">点击上方按钮创建您的第一个团队</div>
      </div>
      
      <div v-else class="teams-list">
        <div v-for="team in teams" :key="team.id" class="team-card">
          <div class="team-header">
            <div class="team-info">
              <h3 class="team-name">{{ team.name }}</h3>
              <p class="team-description">{{ team.description || '暂无描述' }}</p>
            </div>
            <div class="team-actions">
              <button class="add-member-btn" @click="showAddMemberModalHandler(team)">
                <span class="plus-icon">+</span>
                添加成员
              </button>
            </div>
          </div>
          
          <div class="team-members">
            <h4>团队成员 ({{ team.members.length }})</h4>
            <div class="members-list">
              <div v-for="member in team.members" :key="member.id" class="member-item">
                <div class="member-avatar">👤</div>
                <div class="member-info">
                  <div class="member-name">{{ member.user_name }}</div>
                  <div class="member-email">{{ member.user_email }}</div>
                  <div class="member-role">{{ member.role === 'leader' ? '组长' : '成员' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建团队模态框 -->
    <div v-if="showCreateTeamModal" class="modal-overlay" @click="showCreateTeamModal = false">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>创建团队</h3>
          <button class="close-btn" @click="showCreateTeamModal = false">×</button>
        </div>
        
        <div class="modal-body">
          <div class="form-group">
            <label>团队名称</label>
            <input v-model="newTeam.name" type="text" placeholder="请输入团队名称" />
          </div>
          
          <div class="form-group">
            <label>团队描述</label>
            <textarea v-model="newTeam.description" placeholder="请输入团队描述（可选）"></textarea>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="cancel-btn" @click="showCreateTeamModal = false">取消</button>
          <button class="confirm-btn" @click="createTeam" :disabled="!newTeam.name.trim()">
            创建团队
          </button>
        </div>
      </div>
    </div>

    <!-- 添加成员模态框 -->
    <div v-if="showAddMemberModal" class="modal-overlay" @click="showAddMemberModal = false">
      <div class="modal-content add-member-modal" @click.stop>
        <div class="modal-header">
          <h3>添加团队成员</h3>
          <button class="close-btn" @click="showAddMemberModal = false">×</button>
        </div>
        
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">选择用户 <span class="required">*</span></label>
            <div class="user-selector">
              <div class="search-box">
                <input 
                  v-model="memberSearchText" 
                  type="text" 
                  placeholder="搜索用户名或邮箱..." 
                  @input="filterAvailableUsers"
                />
                <span class="search-icon">🔍</span>
              </div>
              <div class="search-hint">
                💡 支持用户名和邮箱搜索，输入任意字符即可实时过滤
              </div>
              <div class="users-list">
                <!-- 搜索提示 -->
                <div v-if="memberSearchText && filteredUsers.length === 0" class="search-no-results">
                  <div class="no-results-icon">🔍</div>
                  <div class="no-results-text">未找到匹配的用户</div>
                  <div class="no-results-hint">请尝试其他关键词或检查拼写</div>
                </div>
                
                <!-- 用户列表 -->
                <div 
                  v-for="user in filteredUsers" 
                  :key="user.id" 
                  class="user-option"
                  :class="{ 'selected': newMember.user_id === user.id }"
                  @click="selectUser(user)"
                >
                  <div class="user-avatar">👤</div>
                  <div class="user-info">
                    <div class="user-name">{{ user.name }}</div>
                    <div class="user-email">{{ user.email }}</div>
                  </div>
                  <div class="user-role" v-if="user.role">{{ user.role }}</div>
                </div>
                
                <!-- 空状态 -->
                <div v-if="!memberSearchText && filteredUsers.length === 0" class="users-empty">
                  <div class="empty-icon">👥</div>
                  <div class="empty-text">暂无可用用户</div>
                </div>
              </div>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">角色 <span class="required">*</span></label>
            <div class="role-selector">
              <label class="role-option">
                <input type="radio" v-model="newMember.role" value="member" />
                <span class="role-label">
                  <span class="role-icon">👤</span>
                  <span class="role-text">成员</span>
                </span>
              </label>
              <label class="role-option">
                <input type="radio" v-model="newMember.role" value="leader" />
                <span class="role-label">
                  <span class="role-icon">👑</span>
                  <span class="role-text">组长</span>
                </span>
              </label>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">权限设置</label>
            <div class="permissions-grid">
              <label class="permission-item">
                <input type="checkbox" v-model="newMember.permissions" value="view_project" />
                <span class="permission-label">查看项目</span>
              </label>
              <label class="permission-item">
                <input type="checkbox" v-model="newMember.permissions" value="edit_badcase" />
                <span class="permission-label">编辑BadCase</span>
              </label>
              <label class="permission-item">
                <input type="checkbox" v-model="newMember.permissions" value="manage_plans" />
                <span class="permission-label">管理计划</span>
              </label>
              <label class="permission-item">
                <input type="checkbox" v-model="newMember.permissions" value="manage_team" />
                <span class="permission-label">管理团队</span>
              </label>
              <label class="permission-item">
                <input type="checkbox" v-model="newMember.permissions" value="admin_project" />
                <span class="permission-label">项目管理员</span>
              </label>
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="cancel-btn" @click="showAddMemberModal = false">取消</button>
          <button class="confirm-btn" @click="addTeamMember" :disabled="!newMember.user_id || !newMember.role">
            添加成员
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { getProjectTeams, createTeam, addTeamMember, getProjectMembers, getAvailableUsers } from '../api.js'

export default {
  name: 'TeamManagement',
  props: {
    projectId: {
      type: [String, Number],
      required: true
    },
    hideTopHeading: {
      type: Boolean,
      default: false
    }
  },
  
  setup(props) {
    const teams = ref([])
    const availableUsers = ref([])
    const showCreateTeamModal = ref(false)
    const showAddMemberModal = ref(false)
    const currentTeam = ref(null)
    
    const newTeam = reactive({
      name: '',
      description: ''
    })
    
    const newMember = reactive({
      user_id: '',
      role: 'member',
      permissions: ['view_project']
    })
    
    const memberSearchText = ref('')
    const filteredUsers = ref([])

    // 获取团队列表
    const fetchTeams = async () => {
      try {
        console.log('获取团队列表，项目ID:', props.projectId)
        const response = await getProjectTeams(props.projectId)
        console.log('团队列表响应:', response)
        if (response.data.success) {
          teams.value = response.data.teams || []
          console.log('设置团队列表:', teams.value)
        }
      } catch (error) {
        console.error('获取团队列表失败:', error)
      }
    }

    // 获取可用用户列表
    const fetchAvailableUsers = async () => {
      try {
        console.log('获取可用用户列表')
        const response = await getAvailableUsers()
        console.log('可用用户响应:', response)
        if (response.data.success) {
          availableUsers.value = response.data.users || []
          filteredUsers.value = [...availableUsers.value]
          console.log('设置可用用户:', availableUsers.value)
        }
      } catch (error) {
        console.error('获取可用用户失败:', error)
      }
    }

    // 创建团队
    const createTeamHandler = async () => {
      try {
        const response = await createTeam({
          name: newTeam.name,
          description: newTeam.description,
          project_id: props.projectId
        })
        
        if (response.data.success) {
          showCreateTeamModal.value = false
          newTeam.name = ''
          newTeam.description = ''
          await fetchTeams()
        }
      } catch (error) {
        console.error('创建团队失败:', error)
      }
    }

    // 显示添加成员模态框
    const showAddMemberModalHandler = (team) => {
      console.log('显示添加成员模态框，团队:', team)
      currentTeam.value = team
      showAddMemberModal.value = true
      newMember.user_id = ''
      newMember.role = 'member'
      newMember.permissions = ['view_project']
      memberSearchText.value = ''
      filteredUsers.value = [...availableUsers.value]
      console.log('模态框状态:', showAddMemberModal.value)
      console.log('可用用户数量:', availableUsers.value.length)
      console.log('过滤后用户数量:', filteredUsers.value.length)
    }
    
    // 过滤可用用户
    const filterAvailableUsers = () => {
      const searchText = memberSearchText.value.trim().toLowerCase()
      
      console.log('开始搜索，搜索文本:', searchText)
      console.log('可用用户总数:', availableUsers.value.length)
      console.log('可用用户数据:', availableUsers.value)
      
      if (!searchText) {
        filteredUsers.value = [...availableUsers.value]
        console.log('无搜索文本，显示所有用户:', filteredUsers.value.length)
        return
      }
      
      // 支持用户名和邮箱搜索，支持部分匹配
      filteredUsers.value = availableUsers.value.filter(user => {
        const nameMatch = user.name && user.name.toLowerCase().includes(searchText)
        const emailMatch = user.email && user.email.toLowerCase().includes(searchText)
        
        console.log(`用户 ${user.name} (${user.email}): nameMatch=${nameMatch}, emailMatch=${emailMatch}`)
        
        // 如果搜索的是邮箱格式，优先显示邮箱匹配的结果
        if (searchText.includes('@')) {
          return emailMatch || nameMatch
        }
        
        return nameMatch || emailMatch
      })
      
      console.log(`搜索 "${searchText}" 找到 ${filteredUsers.value.length} 个用户`)
      console.log('搜索结果:', filteredUsers.value)
    }
    
    // 选择用户
    const selectUser = (user) => {
      newMember.user_id = user.id
    }

    // 添加团队成员
    const addTeamMemberHandler = async () => {
      try {
        const memberData = {
          user_id: newMember.user_id,
          role: newMember.role,
          permissions: newMember.permissions
        }
        
        console.log('添加团队成员数据:', memberData)
        console.log('当前团队ID:', currentTeam.value.id)
        
        const response = await addTeamMember(currentTeam.value.id, memberData)
        
        if (response.data.success) {
          showAddMemberModal.value = false
          await fetchTeams()
          // 重置表单
          newMember.user_id = ''
          newMember.role = 'member'
          newMember.permissions = ['view_project']
        } else {
          alert(`添加成员失败: ${response.data.error || '未知错误'}`)
        }
      } catch (error) {
        console.error('添加团队成员失败:', error)
        console.error('错误详情:', error.response?.data)
        console.error('错误状态:', error.response?.status)
        console.error('错误头:', error.response?.headers)
        
        if (error.response?.data?.error) {
          alert(`添加成员失败: ${error.response.data.error}`)
        } else {
          alert(`添加成员失败: ${error.message || '请重试'}`)
        }
      }
    }

    onMounted(() => {
      fetchTeams()
      fetchAvailableUsers()
    })

    return {
      teams,
      availableUsers,
      filteredUsers,
      memberSearchText,
      showCreateTeamModal,
      showAddMemberModal,
      newTeam,
      newMember,
      createTeam: createTeamHandler,
      showAddMemberModalHandler,
      addTeamMember: addTeamMemberHandler,
      filterAvailableUsers,
      selectUser
    }
  }
}
</script>

<style scoped>
.team-management {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.header h2 {
  margin: 0;
  color: #333;
}

.header.header-compact {
  justify-content: flex-end;
  margin-bottom: 16px;
}

.create-team-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.create-team-btn:hover {
  background: #0056b3;
}

.plus-icon {
  font-size: 16px;
  font-weight: bold;
}

.teams-container {
  min-height: 400px;
}

.no-teams {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.no-teams-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.no-teams-text {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
}

.no-teams-desc {
  font-size: 14px;
}

.teams-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

.team-card {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 20px;
  background: white;
}

.team-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.team-name {
  margin: 0 0 8px 0;
  color: #333;
  font-size: 18px;
}

.team-description {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.add-member-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.add-member-btn:hover {
  background: #218838;
}

.team-members h4 {
  margin: 0 0 16px 0;
  color: #333;
  font-size: 16px;
}

.members-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.member-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.member-avatar {
  font-size: 20px;
}

.member-info {
  flex: 1;
}

.member-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}

.member-email {
  font-size: 12px;
  color: #666;
  margin-bottom: 2px;
}

.member-role {
  font-size: 11px;
  color: #007bff;
  background: #e3f2fd;
  padding: 2px 8px;
  border-radius: 10px;
  display: inline-block;
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
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
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

.form-group {
  margin-bottom: 24px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #333;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-group textarea {
  height: 80px;
  resize: vertical;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  padding: 24px;
  border-top: 1px solid #e0e0e0;
  background: #f8f9fa;
  border-radius: 0 0 12px 12px;
}

.cancel-btn,
.confirm-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  min-width: 100px;
}

.cancel-btn {
  background: #6c757d;
  color: white;
}

.cancel-btn:hover {
  background: #5a6268;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(108, 117, 125, 0.3);
}

.confirm-btn {
  background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
  color: white;
}

.confirm-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #0056b3 0%, #004085 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
}

.confirm-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* 添加成员模态框特定样式 */
.add-member-modal {
  max-width: 600px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border-radius: 12px;
}

.modal-header {
  background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
  color: white;
  border-radius: 12px 12px 0 0;
}

.modal-header h3 {
  margin: 0;
  color: white;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.8);
  transition: color 0.2s;
}

.close-btn:hover {
  color: white;
}

.form-label {
  display: block;
  margin-bottom: 12px;
  font-weight: 600;
  color: #2c3e50;
  font-size: 14px;
}

.required {
  color: #dc3545;
  margin-left: 4px;
  font-weight: bold;
}

.user-selector {
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.search-box {
  position: relative;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-bottom: 1px solid #e0e0e0;
}

.search-box input {
  width: 100%;
  padding: 10px 40px 10px 16px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  background: white;
  transition: border-color 0.2s;
}

.search-box input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}

.search-icon {
  position: absolute;
  right: 24px;
  top: 50%;
  transform: translateY(-50%);
  color: #666;
  font-size: 16px;
}

.search-hint {
  padding: 8px 16px;
  background: #e8f4fd;
  color: #0056b3;
  font-size: 12px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.users-list {
  max-height: 200px;
  overflow-y: auto;
  background: white;
}

.user-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: all 0.2s;
}

.user-option:hover {
  background: #f8f9fa;
  transform: translateX(2px);
}

.user-option.selected {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border-left: 4px solid #007bff;
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.user-avatar {
  font-size: 20px;
}

.user-info {
  flex: 1;
}

.user-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 2px;
}

.user-email {
  font-size: 12px;
  color: #666;
}

.user-role {
  font-size: 11px;
  color: #007bff;
  background: #e3f2fd;
  padding: 2px 8px;
  border-radius: 10px;
}

.role-selector {
  display: flex;
  flex-direction: row;
  gap: 20px;
  margin-top: 8px;
}

.role-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  flex: 1;
  justify-content: flex-start;
  background: #fafafa;
}

.role-option:hover {
  border-color: #007bff;
  background: #f0f8ff;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.role-option input[type="radio"] {
  margin: 0;
  width: 18px;
  height: 18px;
  accent-color: #007bff;
}

.role-label {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-direction: row;
}

.role-icon {
  font-size: 20px;
}

.role-text {
  font-weight: 600;
  color: #2c3e50;
  font-size: 15px;
}

.permissions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  max-height: 200px;
  overflow-y: auto;
  padding: 4px;
}

.permission-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}

.permission-item:hover {
  border-color: #007bff;
  background: #f0f8ff;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.permission-item input[type="checkbox"] {
  margin: 0;
  width: 16px;
  height: 16px;
  accent-color: #007bff;
}

.permission-label {
  font-size: 13px;
  color: #333;
  cursor: pointer;
  font-weight: 500;
}

/* 搜索结果状态样式 */
.search-no-results,
.users-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
  color: #666;
}

.no-results-icon,
.empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.6;
}

.no-results-text,
.empty-text {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #333;
}

.no-results-hint {
  font-size: 13px;
  color: #999;
  line-height: 1.4;
}

/* 搜索高亮效果 */
.user-option .user-name,
.user-option .user-email {
  position: relative;
}

.user-option .user-name::before,
.user-option .user-email::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 0, 0.3);
  opacity: 0;
  transition: opacity 0.2s;
}

.user-option:hover .user-name::before,
.user-option:hover .user-email::before {
  opacity: 1;
}
</style>
