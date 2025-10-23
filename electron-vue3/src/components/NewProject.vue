<template>
  <div class="project-detail-wrapper">
    <!-- 加载指示器 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载项目信息...</div>
                </div>
                
    <div class="back-bar">
      <span class="back-arrow" @click="goBack">←</span>
      <span class="back-title">{{ isEdit ? '编辑项目' : '新建项目' }}</span>
    </div>
    <div class="section-card">
      <div class="section-title">基础配置</div>
      <div class="form-row">
        <label class="form-label required">项目名称：</label>
        <input class="form-input" v-model="project.name" maxlength="20" placeholder="请输入项目名称" />
        <span class="input-count">{{ project.name.length }} / 20</span>
                </div>
      <div class="form-row">
        <label class="form-label">项目描述：</label>
        <textarea class="form-textarea" v-model="project.description" maxlength="150" placeholder="请输入项目描述" />
        <span class="input-count">{{ project.description.length }} / 150</span>
                </div>
                </div>
    <div class="section-card">
      <div class="section-title">能力配置</div>
      <div class="form-row">
        <label class="form-label required">上传项目头像：</label>
        <input type="file" class="avatar-upload" @change="onAvatarChange" :disabled="avatarUploading" />
        <span v-if="avatarUploading" class="upload-status">上传中...</span>
        
                      <img v-if="avatarUrl && !project.imageError" 
                   :src="avatarUrl" 
                   class="avatar-preview" 
                   @error="handleImageError" 
                   @load="handleImageLoad" />
      </div>
          </div>
    <div class="section-card">
      <div class="section-title">其他配置</div>
      <div class="form-row">
        <label class="form-label">负责人名称：</label>
        <input class="form-input" v-model="project.owner" maxlength="20" placeholder="请输入负责人名称" />
        <span class="input-count">{{ project.owner.length }} / 20</span>
        </div>
      <div class="form-row">
        <label class="form-label">项目初始介绍语：</label>
        <textarea class="form-textarea" v-model="project.intro" maxlength="150" placeholder="请输入项目介绍语" />
        <span class="input-count">{{ project.intro.length }} / 150</span>
      </div>
    </div>
    <div class="action-bar">
      <button class="action-btn save-btn" @click="saveProject" :disabled="saveLoading || publishLoading || revokeLoading">
        {{ saveLoading ? '保存中...' : '保存' }}
      </button>
      <!-- 编辑模式：根据项目状态显示不同按钮 -->
      <button v-if="isEdit && project.status === 'unpublished'" class="action-btn publish-btn" @click="handlePublish" :disabled="saveLoading || publishLoading || revokeLoading">
        {{ publishLoading ? '发布中...' : '发布' }}
      </button>
      <button v-if="isEdit && project.status === 'published'" class="action-btn revoke-btn" @click="handleRevoke" :disabled="saveLoading || publishLoading || revokeLoading">
        {{ revokeLoading ? '撤销中...' : '撤销发布' }}
      </button>
      <!-- 新建模式：显示发布按钮 -->
      <button v-if="!isEdit" class="action-btn publish-btn" @click="handlePublish" :disabled="saveLoading || publishLoading || revokeLoading">
        {{ publishLoading ? '发布中...' : '发布' }}
      </button>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { createProject, publishProject, revokeProject, getProjectDetail, updateProject, uploadAvatar } from '../api.js'
import api from '../api.js' // 导入axios实例

export default {
  name: 'NewProject',
  setup() {
    const router = useRouter()
    const loading = ref(false)
    const saveLoading = ref(false)
    const publishLoading = ref(false)
    const revokeLoading = ref(false)
    const avatarUploading = ref(false)  // 头像上传状态
    const isEdit = ref(false)
    const projectId = ref(null)
    
    const project = ref({
      name: '',
      description: '',
      avatar: '',
      owner: '',
      intro: '',
      status: 'unpublished',  // 添加状态字段
      imageError: false,  // 添加图片错误状态
      retryCount: 0 // 添加重试计数
    })
    
    // 添加头像预览URL
    const avatarPreview = ref('')
    
    // 添加头像URL计算属性
    const avatarUrl = computed(() => {
      if (avatarPreview.value) {
        return avatarPreview.value
      }
      if (project.value.avatar) {
        // 如果是MinIO URL，转换为API URL
        if (project.value.avatar.includes('117.72.33.38:9901')) {
          const urlParts = project.value.avatar.split('/')
          const fileName = urlParts[urlParts.length - 1].split('?')[0]
          return `/api/avatar/${encodeURIComponent(fileName)}`
        }
        return project.value.avatar
      }
      return ''
    })

    // 图片错误处理
    const handleImageError = async () => {
      console.log('图片加载失败')
      project.value.imageError = true
      
      // 如果头像URL是API URL，尝试获取新的预签名URL
      if (avatarPreview.value && avatarPreview.value.startsWith('/api/avatar/')) {
        // 检查是否已经重试过多次，避免无限循环
        if (!project.value.retryCount) {
          project.value.retryCount = 0
        }
        
        if (project.value.retryCount >= 3) {
          console.log('头像加载重试次数已达上限，停止重试')
          return
        }
        
        project.value.retryCount++
        console.log(`第${project.value.retryCount}次重试获取头像`)
        
        try {
          console.log('尝试获取新的预签名URL:', avatarPreview.value)
          const response = await api.get(avatarPreview.value)
          console.log('API响应:', response.data)
          if (response.data.success && response.data.url) {
            console.log('获取到新的头像URL:', response.data.url)
            avatarPreview.value = response.data.url
            project.value.imageError = false
            project.value.retryCount = 0 // 重置重试计数
            console.log('头像URL已更新，应该重新加载图片')
          } else {
            console.error('API返回失败:', response.data)
          }
        } catch (error) {
          console.error('获取新头像URL失败:', error)
          if (error.response) {
            console.error('错误响应状态:', error.response.status)
            console.error('错误响应数据:', error.response.data)
          }
        }
      }
    }
    
    // 图片加载成功处理
    const handleImageLoad = () => {
      console.log('图片加载成功')
      project.value.imageError = false
    }
    
    const onAvatarChange = async (e) => {
      const file = e.target.files[0]
      if (file) {
        try {
          console.log('开始上传头像:', file.name, file.size)
          
          // 检查文件大小（1MB限制）
          const maxSize = 1 * 1024 * 1024 // 1MB
          if (file.size > maxSize) {
            alert(`头像文件大小不能超过1MB，当前大小: ${(file.size / 1024 / 1024).toFixed(2)}MB`)
            return
          }
          
          // 检查文件类型
          const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp']
          if (!allowedTypes.includes(file.type)) {
            alert('只支持 JPG、PNG、GIF、BMP 格式的图片文件')
            return
          }
          
          // 显示上传中状态
          avatarUploading.value = true
          
          // 显示本地预览（仅用于UI显示）
          const reader = new FileReader()
          reader.onload = (ev) => {
            // 使用响应式数据设置预览
            avatarPreview.value = ev.target.result
          }
          reader.readAsDataURL(file)
          
          // 上传到MinIO，传递项目ID（如果是编辑模式）
          const startTime = Date.now()
          const response = await uploadAvatar(file, isEdit.value ? projectId.value : null)
          const endTime = Date.now()
          const uploadTime = (endTime - startTime) / 1000
          
          console.log('头像上传响应:', response)
          console.log(`上传耗时: ${uploadTime.toFixed(2)}秒`)
          
          if (response.data.success) {
            // 只保存MinIO的URL，不保存base64数据
            project.value.avatar = response.data.url
            // 更新预览为上传后的URL - 使用我们的API获取头像
            const avatarFileName = response.data.filename
            avatarPreview.value = `/api/avatar/${encodeURIComponent(avatarFileName)}`
            console.log('头像URL已设置:', response.data.url)
            console.log('头像预览URL已设置:', avatarPreview.value)
            console.log('项目头像URL:', project.value.avatar)
            console.log('计算的头像URL:', avatarUrl.value)
            alert(`头像上传成功！耗时: ${uploadTime.toFixed(2)}秒`)
          } else {
            console.error('头像上传失败:', response.data.error)
            alert(`头像上传失败: ${response.data.error}`)
          }
        } catch (error) {
          console.error('头像上传异常:', error)
          if (error.response) {
            console.error('错误响应:', error.response.data)
            alert(`头像上传失败: ${error.response.data?.error || error.response.statusText}`)
          } else {
            alert(`头像上传失败: ${error.message}`)
          }
        } finally {
          // 恢复按钮状态
          avatarUploading.value = false
        }
      }
    }
    
    // 检查是否是编辑模式并加载项目数据
    const initProject = async () => {
      const query = router.currentRoute.value.query
      if (query.edit === 'true' && query.id) {
        isEdit.value = true
        projectId.value = query.id
      loading.value = true
        
      try {
          console.log('开始获取项目详情:', query.id)
          const response = await getProjectDetail(query.id)
          console.log('项目详情响应:', response.data)
          
          if (response.data.success && response.data.project) {
            project.value = { ...project.value, ...response.data.project }
            // 设置头像预览 - 使用API URL
            if (response.data.project.avatar) {
              // 从MinIO URL中提取文件名
              const avatarUrl = response.data.project.avatar
              const urlParts = avatarUrl.split('/')
              const fileName = urlParts[urlParts.length - 1].split('?')[0]
              avatarPreview.value = `/api/avatar/${encodeURIComponent(fileName)}`
            }
            console.log('项目信息加载成功:', project.value)
          } else {
            console.error('获取项目信息失败:', response.data.error)
            alert(`获取项目信息失败: ${response.data.error || '未知错误'}`)
            router.go(-1)
          }
        } catch (error) {
          console.error('获取项目信息异常:', error)
          if (error.response) {
            console.error('错误响应:', error.response.data)
            alert(`获取项目信息失败: ${error.response.data?.error || error.response.statusText}`)
          } else {
            alert(`获取项目信息失败: ${error.message}`)
          }
          router.go(-1)
        } finally {
          loading.value = false
        }
      }
    }
    
    const saveProject = async () => {
      if (!project.value.name.trim()) {
        alert('请输入项目名称')
        return
      }
      saveLoading.value = true
      try {
        let result
        if (isEdit.value) {
          // 编辑模式
          result = await updateProject(projectId.value, {
            name: project.value.name,
            description: project.value.description,
            avatar: project.value.avatar,  // 添加头像URL
            owner: project.value.owner,
            intro: project.value.intro
        })
        
          if (result.data.success) {
            alert('项目更新成功')
            router.push({
              name: 'ProjectDetail',
              params: { id: projectId.value }
            })
          } else {
            alert(`更新失败: ${result.data.error || '未知错误'}`)
          }
        } else {
          // 创建模式
          result = await createProject({
            name: project.value.name,
            description: project.value.description,
            avatar: project.value.avatar,  // 添加头像URL
            owner: project.value.owner,
            intro: project.value.intro
          })
          
          if (result.data.success) {
            console.log('项目创建成功，项目信息:', result.data.project)
            alert('项目创建成功')
            console.log('准备跳转到项目详情页面，ID:', result.data.project.id)
          router.push({
            name: 'ProjectDetail',
              params: { id: result.data.project.id }
          })
          } else {
            alert(`创建失败: ${result.data.error || '未知错误'}`)
          }
        }
      } catch (error) {
        console.error(isEdit.value ? '更新项目失败:' : '创建项目失败:', error)
        if (error.response) {
          alert(`${isEdit.value ? '更新' : '创建'}项目失败: ${error.response.data?.error || error.response.statusText}`)
        } else {
          alert(`${isEdit.value ? '更新' : '创建'}项目失败: ${error.message}`)
        }
      } finally {
        saveLoading.value = false
      }
    }
    
    const handlePublish = async () => {
      if (!project.value.name.trim()) {
        alert('请输入项目名称')
        return
      }
      publishLoading.value = true
      try {
        if (isEdit.value) {
          // 编辑模式：发布现有项目
          const result = await publishProject(projectId.value)
          if (result.data.success) {
            alert('发布成功')
            project.value.status = 'published'
          } else {
            alert(`发布失败: ${result.data.error || '未知错误'}`)
          }
        } else {
          // 新建模式：先创建项目再发布
          const result = await createProject({
            name: project.value.name,
            description: project.value.description,
            avatar: project.value.avatar,
            owner: project.value.owner,
            intro: project.value.intro
          })
          
          if (result.data.success && result.data.project && result.data.project.id) {
            // 创建成功后立即发布
            try {
              const pubRes = await publishProject(result.data.project.id)
              if (pubRes.data.success) {
                alert('发布成功')
                router.push({
                  name: 'ProjectDetail',
                  params: { id: result.data.project.id }
                })
              } else {
                alert('发布失败，但项目已创建')
                router.push({
                  name: 'ProjectDetail',
                  params: { id: result.data.project.id }
                })
              }
            } catch (error) {
              console.error('发布失败:', error)
              alert('发布失败，但项目已创建')
              router.push({
                name: 'ProjectDetail',
                params: { id: result.data.project.id }
              })
            }
          } else {
            alert(`创建失败: ${result.data.error || '未知错误'}`)
          }
        }
      } catch (error) {
        console.error('发布项目失败:', error)
        if (error.response) {
          alert(`发布项目失败: ${error.response.data?.error || error.response.statusText}`)
        } else {
          alert(`发布项目失败: ${error.message}`)
        }
      } finally {
        publishLoading.value = false
      }
    }

    const handleRevoke = async () => {
      if (!projectId.value) {
        alert('项目ID不存在')
        return
      }
      revokeLoading.value = true
      try {
        const result = await revokeProject(projectId.value)
        if (result.data.success) {
          alert('撤销发布成功')
          project.value.status = 'unpublished'
        } else {
          alert(`撤销发布失败: ${result.data.error || '未知错误'}`)
        }
      } catch (error) {
        console.error('撤销发布失败:', error)
        if (error.response) {
          alert(`撤销发布失败: ${error.response.data?.error || error.response.statusText}`)
        } else {
          alert(`撤销发布失败: ${error.message}`)
        }
      } finally {
        revokeLoading.value = false
      }
    }
    
    const goBack = () => {
      router.go(-1)
    }
    
    onMounted(() => {
      initProject()
    })
    
    return {
      project,
      loading,
      saveLoading,
      publishLoading,
      revokeLoading,
      avatarUploading,
      avatarPreview,
      avatarUrl,
      isEdit,
      onAvatarChange,
      saveProject,
      handlePublish,
      handleRevoke,
      goBack,
      handleImageError,
      handleImageLoad
    }
  }
}
</script>

<style scoped>
.project-detail-wrapper {
  padding: 32px 24px;
  background: #f6f8fa;
  min-height: 100vh;
}
.back-bar {
  display: flex;
  align-items: center;
  font-size: 18px;
  margin-bottom: 24px;
  color: #333;
}
.back-arrow {
  cursor: pointer;
  font-size: 22px;
  margin-right: 8px;
  color: #667eea;
  font-weight: bold;
}
.back-title {
  font-weight: 600;
}
.section-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  padding: 28px 32px 18px 32px;
  margin-bottom: 28px;
}
.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin-bottom: 18px;
}
.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 18px;
  gap: 12px;
}
.form-label {
  width: 120px;
  color: #333;
  font-size: 15px;
  font-weight: 500;
  text-align: right;
}
.form-label.required::before {
  content: '*';
  color: #f56565;
  margin-right: 4px;
}
.form-input {
  flex: 1;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 15px;
}
.form-textarea {
  flex: 1;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 15px;
  min-height: 60px;
  resize: vertical;
}
.input-count {
  color: #999;
  font-size: 13px;
  min-width: 60px;
  text-align: right;
}
.avatar-upload {
  margin-left: 8px;
}
.upload-status {
  margin-left: 8px;
  color: #667eea;
  font-size: 14px;
  font-weight: 500;
}
.avatar-preview {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  margin-left: 16px;
  object-fit: cover;
  border: 1.5px solid #e9ecef;
}
.action-bar {
  display: flex;
  gap: 18px;
  justify-content: flex-end;
  margin-top: 32px;
}
.action-btn {
  padding: 10px 28px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.save-btn {
  background: #667eea;
  color: #fff;
}
.save-btn:hover:not(:disabled) {
  background: #5a6fd8;
}
.publish-btn {
  background: #42b983;
  color: #fff;
}
.publish-btn:hover:not(:disabled) {
  background: #2ea36c;
}
.revoke-btn {
  background: #f56565;
  color: #fff;
}
.revoke-btn:hover:not(:disabled) {
  background: #e53e3e;
}

/* 加载指示器样式 */
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
@media (max-width: 900px) {
  .section-card {
    padding: 18px 8px 12px 8px;
  }
  .form-label {
    width: 90px;
  }
}
</style> 