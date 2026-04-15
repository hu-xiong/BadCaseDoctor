<template>
  <div class="project-manage">
    <!-- 顶部操作栏 -->
    <div class="projects-header">
      <h2 class="projects-title">{{ t('projectList.title') }}</h2>
      <div class="projects-actions">
        <div class="search-box">
          <input type="text" :placeholder="t('projectList.searchPlaceholder')" v-model="searchKeyword" class="search-input">
          <span class="search-icon">🔍</span>
        </div>
        <button class="refresh-btn" @click="refreshProjects">
          <span class="refresh-icon">🔄</span>
        </button>
      </div>
    </div>

    <!-- 新建项目按钮 -->
    <div class="new-project-section">
      <button class="new-project-btn" @click="createNewProject">
        <span class="new-project-icon">+</span>
        <span class="new-project-text">{{ t('projectList.newProject') }}</span>
      </button>
    </div>

    <!-- 项目卡片网格 -->
    <div class="projects-grid">
      <div v-for="project in filteredProjects" :key="project.id" class="project-card" @click="viewProject(project)">
        <div class="project-header">
          <div class="project-avatar">
            <img v-if="project.avatar && !project.imageError" 
                 :src="project.avatar" 
                 :alt="t('projectList.avatarAlt')" 
                 @error="handleImageError(project)" 
                 @load="handleImageLoad(project)"
                 loading="lazy"
                 crossorigin="anonymous"
                 class="project-avatar-img" />
            <div v-else class="avatar-placeholder">
              {{ project.name ? project.name.charAt(0).toUpperCase() : 'P' }}
            </div>
          </div>
          <div class="project-info">
            <h3 class="project-title">{{ project.name }}</h3>
            <span class="project-status" :class="project.status">{{ getStatusText(project.status) }}</span>
                      </div>
                    </div>
        <div class="project-tags">
          <span class="project-tag">{{ project.owner || t('projectList.noOwner') }}</span>
          <span class="project-tag">{{ project.status === 'published' ? t('projectList.published') : t('projectList.unpublished') }}</span>
        </div>
        <div class="project-description">{{ project.description || t('projectList.noDescription') }}</div>
        <div class="project-footer">
          <span class="project-date">{{ formatDate(project.created_at) }}</span>
          <div class="project-actions" @click.stop>
            <button class="action-btn" @click="viewProject(project)" :title="t('projectList.viewDetail')">
              <span class="action-icon">👁️</span>
            </button>
            <button class="action-btn" @click="editProject(project)" :title="t('projectList.editProject')">
              <span class="action-icon">✏️</span>
            </button>
            <button v-if="project.status === 'unpublished'" class="action-btn delete-btn" @click="deleteProject(project.id)" :title="t('projectList.deleteProject')">
              <span class="action-icon">🗑️</span>
            </button>
                  </div>
                </div>
              </div>
            </div>

    <!-- 分页控件 -->
    <div class="pagination">
      <div class="pagination-info">
        {{ t('projectList.pageRange', { from: (currentPage - 1) * pageSize + 1, to: Math.min(currentPage * pageSize, totalProjects), total: totalProjects }) }}
      </div>
      <div class="pagination-controls">
        <button class="page-btn" :disabled="currentPage === 1" @click="currentPage--">
          ‹
        </button>
        <button class="page-btn" :class="{active: currentPage === 1}" @click="currentPage = 1">1</button>
        <button v-if="totalPages > 1" class="page-btn" :class="{active: currentPage === 2}" @click="currentPage = 2">2</button>
        <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage++">
          ›
        </button>
          </div>
      <div class="pagination-settings">
        <select v-model="pageSize" class="page-size-select">
          <option value="12">{{ t('projectList.perPage', { n: 12 }) }}</option>
          <option value="24">{{ t('projectList.perPage', { n: 24 }) }}</option>
          <option value="48">{{ t('projectList.perPage', { n: 48 }) }}</option>
        </select>
        <div class="jump-to">
          <input type="number" v-model="jumpPage" class="jump-input" min="1" :max="totalPages">
          <button class="jump-btn" @click="jumpToPage">{{ t('projectList.pageJump') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getProjects } from '../api.js'
import api from '../api.js'

export default {
  name: 'ProjectManage',
  emits: ['projectSelected'],
  setup(props, { emit }) {
    const router = useRouter()
    const { t, locale } = useI18n()
    const projects = ref([])
    // 搜索关键字
    const searchKeyword = ref('')
    const currentPage = ref(1)
    const pageSize = ref(12)
    const jumpPage = ref(1)
    
    // 图片缓存管理
    const imageCache = new Map()
    
             // 预加载图片到缓存
         const preloadImage = async (project) => {
           if (!project.avatar || project.imageError) {
             return
           }
           
           // 如果avatar是API URL，需要先获取base64数据
           if (project.avatar.includes('/api/avatar/base64/')) {
             try {
               console.log(`正在获取项目 ${project.id} 的头像base64数据: ${project.avatar}`)
               const response = await fetch(project.avatar, {
                 credentials: 'include', // 包含cookies
                 headers: {
                   'Accept': 'application/json'
                 }
               })
               
               console.log(`项目 ${project.id} 头像API响应状态:`, response.status)
               
               if (response.ok) {
                 const data = await response.json()
                 console.log(`项目 ${project.id} 头像API响应数据:`, data)
                 if (data.data) {
                   // 将base64数据设置为avatar
                   project.avatar = data.data
                   console.log(`项目 ${project.id} 头像base64数据获取成功`)
                 } else {
                   console.warn(`项目 ${project.id} 头像API响应中没有data字段:`, data)
                   project.imageError = true
                 }
               } else {
                 const errorText = await response.text()
                 console.warn(`获取项目 ${project.id} 头像失败:`, response.status, errorText)
                 project.imageError = true
               }
             } catch (error) {
               console.warn(`获取项目 ${project.id} 头像失败:`, error)
               project.imageError = true
             }
           }
           
           // 如果avatar是base64数据，直接缓存
           if (project.avatar.startsWith('data:image/')) {
             if (imageCache.has(project.avatar)) {
               return Promise.resolve(imageCache.get(project.avatar))
             }
             
             return new Promise((resolve, reject) => {
               const img = new Image()
               img.onload = () => {
                 imageCache.set(project.avatar, img)
                 resolve(img)
               }
               img.onerror = () => {
                 reject(new Error(`Failed to load image: ${project.avatar}`))
               }
               img.src = project.avatar
             })
           }
         }

    const fetchProjects = async () => {
      try {
        console.log('开始获取项目列表...')
        const response = await getProjects()
        if (response.data.success) {
          // 预处理项目数据，添加图像状态标记
          projects.value = (response.data.projects || []).map(project => ({
            ...project,
            imageError: false,
            imageLoaded: false
          }))
          console.log(`成功获取 ${projects.value.length} 个项目`)
          
          // 为每个有头像的项目处理头像URL
          for (const project of projects.value) {
            if (project.avatar) {
              console.log(`处理项目 ${project.id} 的头像: ${project.avatar}`)
              
                             // 检查avatar是否已经是完整的URL
               if (project.avatar.startsWith('http://') || project.avatar.startsWith('https://')) {
                 // 已经是完整URL，需要转换为我们的缓存API
                 console.log(`项目 ${project.id} 头像已经是完整URL: ${project.avatar}`)
                 
                 // 从URL中提取文件名，需要处理查询参数
                 let filename
                 if (project.avatar.includes('?')) {
                   // 如果有查询参数，先分割
                   const urlWithoutParams = project.avatar.split('?')[0]
                   const urlParts = urlWithoutParams.split('/')
                   filename = urlParts[urlParts.length - 1]
                 } else {
                   // 没有查询参数，直接分割
                   const urlParts = project.avatar.split('/')
                   filename = urlParts[urlParts.length - 1]
                 }
                 
                 if (filename) {
                   // 使用我们的base64缓存API
                   project.avatar = `http://localhost:5000/api/avatar/base64/${encodeURIComponent(filename)}`
                   console.log(`项目 ${project.id} 头像URL转换为base64缓存API: ${project.avatar}`)
                 }
               } else {
                 // 是文件名，直接使用base64缓存API
                 project.avatar = `http://localhost:5000/api/avatar/base64/${encodeURIComponent(project.avatar)}`
                 console.log(`项目 ${project.id} 头像URL使用base64缓存API: ${project.avatar}`)
               }
            }
          }
          
                         // 预加载所有头像到缓存
               console.log('开始预加载头像...')
               const preloadPromises = projects.value
                 .filter(project => project.avatar && !project.imageError)
                 .map(project => preloadImage(project).catch(error => {
                   console.warn(`预加载头像失败: ${project.avatar}`, error)
                   project.imageError = true
                 }))
               
               await Promise.allSettled(preloadPromises)
               console.log('头像预加载完成')
        } else {
          console.error('获取项目列表失败:', response.data)
          projects.value = []
        }
      } catch (error) {
        console.error('获取项目列表失败:', error)
        projects.value = []
      }
    }

    const createNewProject = () => {
      router.push('/new-project')
    }

    const viewProject = (project) => {
      // 发出项目选择事件，让父组件处理跳转逻辑
      emit('projectSelected', project)
    }

    const editProject = (project) => {
      router.push({
        name: 'NewProject',
        query: { edit: 'true', id: project.id }
      })
    }

    const deleteProject = (id) => {
      if (confirm(t('projectList.deleteConfirm'))) {
        console.log('删除项目:', id)
        // 这里添加删除逻辑
      }
    }

    const handleImageError = (project) => {
      console.error('图片加载失败:', project.avatar)
      project.imageError = true
    }

    const handleImageLoad = (project) => {
      console.log('图片加载成功:', project.avatar)
      // 标记项目图像加载成功
      project.imageLoaded = true
    }



    const formatDate = (dateString) => {
      return new Date(dateString).toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      }).replace(/\//g, '/')
    }

    const getStatusText = (status) => {
      return status === 'published' ? t('projectList.published') : t('projectList.unpublished')
    }

    const refreshProjects = () => {
      // 清理图片缓存
      imageCache.clear()
      fetchProjects()
    }

    const filteredProjects = computed(() => {
      let filtered = projects.value
      
      if (searchKeyword.value) {
        filtered = filtered.filter(project => 
          project.name.toLowerCase().includes(searchKeyword.value.toLowerCase())
        )
      }
      
      return filtered
    })

    const totalProjects = computed(() => filteredProjects.value.length)
    const totalPages = computed(() => Math.ceil(totalProjects.value / pageSize.value))

    const jumpToPage = () => {
      if (jumpPage.value >= 1 && jumpPage.value <= totalPages.value) {
        currentPage.value = jumpPage.value
      }
    }

    onMounted(() => {
      fetchProjects()
    })
    
    // 组件卸载时清理缓存
    onUnmounted(() => {
      imageCache.clear()
    })

    return {
      t,
      projects,
      searchKeyword,
      currentPage,
      pageSize,
      jumpPage,
      filteredProjects,
      totalProjects,
      totalPages,
      createNewProject,
      viewProject,
      editProject,
      deleteProject,
      formatDate,
      getStatusText,
      refreshProjects,
      jumpToPage,
      handleImageError,
      handleImageLoad
    }
  }
}
</script>

<style scoped>
.project-manage {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
}

/* 顶部操作栏 */
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

/* 新建项目按钮 */
.new-project-section {
  margin-bottom: 24px;
}

.new-project-btn {
  background: #667eea;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 3px 8px rgba(102, 126, 234, 0.3);
}

.new-project-btn:hover {
  background: #5a6fd8;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.new-project-icon {
  font-size: 16px;
  font-weight: bold;
}

.new-project-text {
  font-weight: 600;
}

/* 项目卡片网格 */
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
  cursor: pointer;
}

.project-card:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.project-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}
.project-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}
.project-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: opacity 0.3s ease;
}

.project-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: opacity 0.3s ease;
  will-change: opacity;
}
.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: bold;
}
.project-info {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  margin-top: 48px;
  padding-top: 24px;
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
  .project-manage {
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
  
  .search-box {
    width: 100%;
    max-width: none;
  }
  
  .projects-grid {
    grid-template-columns: 1fr;
  }
}
</style> 