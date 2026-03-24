<template>
  <div class="dashboard-container">
    <!-- 顶部导航栏 -->
    <header class="top-navbar">
      <div class="navbar-brand">
        <h1 class="app-title">BadCase Doctor</h1>
      </div>
      <div class="user-dropdown" @click="toggleUserDropdown">
        <div class="user-avatar">👤</div>
        
        <!-- 用户下拉菜单 -->
        <div v-if="showUserDropdown" class="user-menu" @click.stop>
          <div class="user-detail">
            <div class="user-name">{{ currentUser?.name || t('shell.userFallback') }}</div>
            <div class="user-email">{{ currentUser?.email || t('shell.emailFallback') }}</div>
          </div>
          <div class="menu-divider"></div>
          <div class="menu-item" @click="showUserProfile">
            <span class="menu-icon">👤</span>
            <span class="menu-text">{{ t('dashboard.profile') }}</span>
          </div>
          <div class="menu-item" @click="showNotifications">
            <span class="menu-icon">🔔</span>
            <span class="menu-text">{{ t('dashboard.notifications') }}</span>
          </div>
          <div class="menu-item" @click="showHelp">
            <span class="menu-icon">❓</span>
            <span class="menu-text">{{ t('dashboard.help') }}</span>
          </div>
          <div class="menu-item" @click="showTeamManagement">
            <span class="menu-icon">👥</span>
            <span class="menu-text">{{ t('dashboard.team') }}</span>
          </div>
          <div class="menu-divider"></div>
          <div class="menu-item logout-item" @click="logout">
            <span class="menu-icon">🚪</span>
            <span class="menu-text">{{ t('dashboard.logout') }}</span>
          </div>
        </div>
      </div>
    </header>

    <div class="main-layout">
      <!-- 左侧边栏 -->
      <aside class="left-sidebar" :style="{ width: sidebarWidth + 'px' }">
        <!-- 删除新建项目按钮 -->
        <!--
        <div class="new-project-section">
          <button class="new-project-btn" @click="createNewProject">
            <span class="new-project-icon">+</span>
            <span class="new-project-text">新建项目</span>
          </button>
        </div>
        -->
        
        <div class="sidebar-menu">
          <button class="sidebar-item" :class="{active: currentView === 'overview'}" @click="currentView = 'overview'">
            <span class="sidebar-icon">🏠</span>
            <span class="sidebar-text">{{ t('dashboard.overview') }}</span>
          </button>
          <button class="sidebar-item" :class="{active: currentView === 'projects'}" @click="currentView = 'projects'">
            <span class="sidebar-icon">📁</span>
            <span class="sidebar-text">{{ t('dashboard.projectManage') }}</span>
          </button>

        </div>
      </aside>

      <!-- 拖拽分隔条 -->
      <div class="resize-handle" @mousedown="startResize"></div>

      <!-- 主内容区域 -->
      <main class="main-content">
        <!-- 概览内容（只显示统计卡片） -->
        <div v-if="currentView === 'overview'" class="overview-content">
          <div class="stats-section" style="flex-direction: row; gap: 24px; justify-content: center; margin-bottom: 32px;">
          <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">{{ t('dashboard.statPending') }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">{{ t('dashboard.statResolved') }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">{{ t('dashboard.statTotal') }}</div>
          </div>
          </div>
        </div>

        <!-- 项目管理内容 -->
        <div v-else-if="currentView === 'projects'" class="projects-content">
          <ProjectManage />
        </div>



        <!-- 浮动操作按钮 -->
        <!-- 删除以下浮动按钮 -->
        <!--
        <div class="floating-actions">
          <button class="floating-btn purple-btn">
            <span class="btn-icon">◊</span>
          </button>
          <button class="floating-btn purple-btn">
            <span class="btn-icon">A</span>
          </button>
          <button class="floating-btn pink-btn">
            <span class="btn-icon">⚙️</span>
          </button>
        </div>
        -->
      </main>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ProjectManage from './ProjectManage.vue'
import Chat from './Chat.vue'
import UserProfile from './UserProfile.vue'
import userStore from '../store/user.js'

export default {
  name: 'Dashboard',
  components: {
    ProjectManage,
    Chat,
    UserProfile
  },
  setup() {
    const router = useRouter()
    const { t } = useI18n()
    const currentView = ref('overview')
    const sidebarWidth = ref(280)
    const isResizing = ref(false)
    
    // 用户下拉菜单状态
    const showUserDropdown = ref(false)
    const showProfileModal = ref(false)
    const currentUser = ref(null)
    
    // 获取当前用户信息
    const fetchCurrentUser = () => {
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
    }

    const createNewProject = () => {
      router.push('/new-project')
    }
    
    // 用户下拉菜单相关方法
    const toggleUserDropdown = () => {
      showUserDropdown.value = !showUserDropdown.value
    }
    
    const showUserProfile = () => {
      showUserDropdown.value = false
      showProfileModal.value = true
    }
    
    const showTeamManagement = () => {
      showUserDropdown.value = false
      // TODO: 实现团队管理页面
      alert(t('dashboard.teamDev'))
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

    const startResize = (e) => {
      isResizing.value = true
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', stopResize)
      e.preventDefault()
    }

    const handleMouseMove = (e) => {
      if (isResizing.value) {
        const newWidth = e.clientX
        if (newWidth >= 200 && newWidth <= 600) {
          sidebarWidth.value = newWidth
        }
      }
    }

    const stopResize = () => {
      isResizing.value = false
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', stopResize)
    }
    
    // 初始化
    onMounted(() => {
      fetchCurrentUser()
      
      // 添加全局点击监听器，点击外部关闭用户下拉菜单
      document.addEventListener('click', (event) => {
        const userDropdown = document.querySelector('.user-dropdown')
        if (userDropdown && !userDropdown.contains(event.target)) {
          showUserDropdown.value = false
        }
      })
    })
    
    // 监听用户信息变化
    watch(userStore, (newUser) => {
      if (newUser) {
        currentUser.value = newUser
      }
    }, { immediate: true })

    return {
      t,
      currentView,
      sidebarWidth,
      isResizing,
      createNewProject,
      startResize,
      showUserDropdown,
      currentUser,
      toggleUserDropdown,
      showUserProfile,
      showProfileModal,
      showTeamManagement,
      showNotifications,
      showHelp,
      logout
    }
  }
}
</script>

<style scoped>
.dashboard-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8f9fa;
}

/* 顶部导航栏 */
.top-navbar {
  background: white;
  border-bottom: 1px solid #e9ecef;
  padding: 0 24px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  position: relative;
}

.navbar-brand {
  display: flex;
  align-items: center;
}

.app-title {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  text-align: right;
}

.user-label {
  color: #666;
}

.username {
  color: #333;
  font-weight: 500;
}

/* 拖拽分隔条 */
.resize-handle {
  width: 4px;
  background: #e9ecef;
  cursor: col-resize;
  transition: background 0.2s;
  position: relative;
}

.resize-handle:hover {
  background: #667eea;
}

.resize-handle::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 20px;
  background: #ccc;
  border-radius: 1px;
}

.resize-handle:hover::after {
  background: #667eea;
}

/* 主布局 */
.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 左侧边栏 */
.left-sidebar {
  min-width: 200px;
  max-width: 600px;
  background: #f8f9fa;
  border-right: 1px solid #e9ecef;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border-radius: 0 0 12px 0;
  transition: width 0.1s ease;
}

/* 新建项目按钮 */
.new-project-section {
  margin-bottom: 24px;
}

.new-project-btn {
  width: 100%;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.new-project-btn:hover {
  background: #5a6fd8;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
}

.new-project-icon {
  font-size: 20px;
  font-weight: bold;
}

.new-project-text {
  font-weight: 600;
}

/* 新增侧边栏样式 */
.sidebar-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 16px;
  color: #333;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
  font-weight: 500;
}

.sidebar-item .sidebar-icon {
  font-size: 20px;
  display: flex;
  align-items: center;
}

.sidebar-item.active {
  background: #e6edfd;
  color: #2563eb;
}

.sidebar-item.active .sidebar-icon {
  color: #2563eb;
}

.sidebar-item:hover {
  background: #f0f4fa;
}

.sidebar-text {
  flex: 1;
  text-align: left;
}

/* 统计信息 */
.stats-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-card {
  text-align: center;
  padding: 20px;
  background: white;
  border-radius: 12px;
  border: 1px solid #e9ecef;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.stat-card:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

.stat-number {
  font-size: 36px;
  font-weight: 700;
  color: #667eea;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 12px;
  color: #666;
  line-height: 1.4;
}

/* 导航按钮 */
.nav-buttons {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.nav-btn {
  padding: 12px 16px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  text-align: center;
  width: 100%;
}

.primary-btn {
  background: #667eea;
  color: white;
}

.primary-btn:hover {
  background: #5a6fd8;
}

.overview-btn {
  background: #667eea;
  color: white;
  font-weight: 600;
  padding: 16px 20px;
  font-size: 16px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.overview-btn:hover {
  background: #5a6fd8;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
}

.overview-btn.active {
  background: #5a6fd8;
  color: white;
  border-color: #5a6fd8;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.5);
}

.nav-links {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.nav-link-btn {
  background: #f8f9fa;
  color: #333;
  border: 1px solid #e9ecef;
  font-weight: 500;
  padding: 14px 18px;
  font-size: 15px;
  transition: all 0.3s ease;
}

.nav-link-btn:hover {
  background: #667eea;
  color: white;
  border-color: #667eea;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
}

.nav-link {
  color: #667eea;
  text-decoration: none;
  font-size: 14px;
  padding: 8px 0;
  transition: color 0.2s ease;
}

.nav-link:hover {
  color: #5a6fd8;
}

/* 概览区域 */
.overview-section {
  margin-bottom: 24px;
}

/* 主内容区域 */
.main-content {
  flex: 1;
  background: white;
  position: relative;
  overflow: hidden;
}

.overview-content {
  height: 100%;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.projects-content {
  height: 100%;
  padding: 24px;
}

.chat-content {
  height: 100%;
  padding: 24px;
}

.other-content {
  height: 100%;
  padding: 24px;
}

.content-placeholder {
  text-align: center;
  color: #666;
}

/* 红框注释区域 */
.annotation-box {
  background: #fff5f5;
  border: 2px solid #feb2b2;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}

.annotation-text {
  color: #c53030;
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
  font-weight: 500;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  flex: 1;
  max-width: 400px;
  margin: 0 auto;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
  opacity: 0.6;
}

.empty-state h3 {
  font-size: 24px;
  color: #333;
  margin-bottom: 8px;
  font-weight: 500;
}

.empty-state p {
  color: #666;
  margin-bottom: 24px;
  font-size: 14px;
}

/* 浮动操作按钮 */
.floating-actions {
  position: absolute;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.floating-btn {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  transition: all 0.2s ease;
}

.floating-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.2);
}

.purple-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.pink-btn {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
}

.btn-icon {
  font-size: 20px;
  font-weight: 600;
}

/* 按钮样式 */
.btn {
  padding: 12px 24px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  text-decoration: none;
  display: inline-block;
}

.btn-primary {
  background: #667eea;
  color: white;
}

.btn-primary:hover {
  background: #5a6fd8;
  transform: translateY(-1px);
}

/* 项目管理相关样式 */
.projects-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e9ecef;
}

.projects-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.projects-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  background: #f0f4fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 8px 12px;
  flex: 1;
  max-width: 300px;
}

.search-input {
  border: none;
  background: transparent;
  padding: 8px 10px;
  font-size: 14px;
  color: #333;
  flex: 1;
}

.search-input:focus {
  outline: none;
}

.search-icon {
  font-size: 18px;
  color: #666;
  margin-right: 8px;
}

.filter-dropdown {
  position: relative;
  display: flex;
  align-items: center;
  background: #f0f4fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  min-width: 150px;
}

.status-select {
  border: none;
  background: transparent;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  flex: 1;
  padding-right: 10px;
}

.status-select:focus {
  outline: none;
}

.dropdown-icon {
  font-size: 18px;
  color: #666;
  margin-left: 8px;
}

.refresh-btn {
  background: #f0f4fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  background: #e9ecef;
  border-color: #667eea;
  color: #667eea;
}

.refresh-icon {
  font-size: 18px;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
  margin-bottom: 24px;
}

.project-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.project-card:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.project-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.project-status {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: white;
}

.project-status.published {
  background-color: #42b983;
}

.project-status.unpublished {
  background-color: #f56565;
}

.project-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.project-tag {
  background: #e6edfd;
  color: #2563eb;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.project-description {
  font-size: 14px;
  color: #555;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.project-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
  font-size: 12px;
  color: #666;
}

.project-date {
  font-weight: 500;
}

.project-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  background: #f0f4fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #e9ecef;
  border-color: #667eea;
  color: #667eea;
}

.action-btn.delete-btn {
  background: #fef5f5;
  border: 1px solid #feb2b2;
  color: #c53030;
}

.action-btn.delete-btn:hover {
  background: #fef5f5;
  border-color: #feb2b2;
  color: #c53030;
}

.action-icon {
  font-size: 16px;
}

/* 分页控件 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e9ecef;
}

.pagination-info {
  font-size: 14px;
  color: #666;
}

.pagination-controls {
  display: flex;
  gap: 8px;
}

.page-btn {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s ease;
}

.page-btn:hover {
  background: #e9ecef;
  border-color: #667eea;
  color: #667eea;
}

.page-btn:disabled {
  background: #e9ecef;
  color: #ccc;
  cursor: not-allowed;
}

.page-btn.active {
  background: #667eea;
  color: white;
  border-color: #667eea;
}

.pagination-settings {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-size-select {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
}

.page-size-select:focus {
  outline: none;
}

.jump-to {
  display: flex;
  align-items: center;
  gap: 8px;
}

.jump-input {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  color: #333;
  width: 60px;
  text-align: center;
}

.jump-input:focus {
  outline: none;
}

.jump-btn {
  background: #667eea;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.jump-btn:hover {
  background: #5a6fd8;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .left-sidebar {
    width: 240px;
    padding: 16px;
  }
  
  .overview-content {
    padding: 16px;
  }

  .projects-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .projects-actions {
    width: 100%;
    justify-content: space-between;
  }

  .search-box, .filter-dropdown, .refresh-btn {
    width: 100%;
    max-width: none;
  }

  .projects-grid {
    grid-template-columns: 1fr;
  }
}

/* 用户下拉菜单样式 */
.user-dropdown {
  position: relative;
  cursor: pointer;
  display: flex;
  align-items: center;
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

.user-detail {
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
  font-size: 14px;
  opacity: 0.8;
}

.menu-text {
  font-size: 13px;
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
</style> 