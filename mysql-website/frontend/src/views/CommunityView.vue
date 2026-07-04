<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { useAuthStore } from '@/stores/auth'
import { getPosts, createPost, type CommunityPost } from '@/api/community'
import { formatDate as formatDateUtil } from '@/utils/format'

const authStore = useAuthStore()

const selectedCategory = ref('')
const showCreateDialog = ref(false)
const loading = ref(true)
const posts = ref<CommunityPost[]>([])
const newPost = ref({
  title: '',
  content: '',
  category: ''
})

const categories = [
  { value: 'general', label: 'General Discussion' },
  { value: 'help', label: 'Help & Support' },
  { value: 'showcase', label: 'Project Showcase' },
  { value: 'tutorials', label: 'Tutorials' },
  { value: 'jobs', label: 'Jobs & Opportunities' }
]

async function loadPosts() {
  loading.value = true
  try {
    const params: Record<string, string | number> = { page: 1, page_size: 20 }
    if (selectedCategory.value) {
      params.category = selectedCategory.value
    }
    const data = await getPosts(params)
    posts.value = data.list
  } catch {
    posts.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadPosts)
watch(selectedCategory, loadPosts)

const filteredPosts = computed(() => posts.value)

const handleCreatePost = () => {
  if (!authStore.isAuthenticated) {
    ElMessage.warning('Please login to create a post')
    return
  }
  showCreateDialog.value = true
}

const submitPost = async () => {
  if (!newPost.value.title.trim() || !newPost.value.content.trim()) {
    ElMessage.warning('Title and content are required')
    return
  }
  try {
    await createPost({
      title: newPost.value.title,
      content: newPost.value.content,
      category: newPost.value.category || 'general'
    })
    ElMessage.success('Post created successfully!')
    showCreateDialog.value = false
    newPost.value = { title: '', content: '', category: '' }
    await loadPosts()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || 'Failed to create post')
  }
}

const formatDate = (dateStr: string) => formatDateUtil(dateStr)
</script>

<template>
  <div class="community-page">
    <!-- Hero -->
    <section class="page-hero">
      <div class="container">
        <h1 class="page-title">MySQL Community</h1>
        <p class="page-subtitle">
          Connect with fellow MySQL users, share knowledge, and get help from the community
        </p>
      </div>
    </section>

    <section class="community-content">
      <div class="container">
        <div class="content-layout">
          <!-- Main Content -->
          <main class="posts-section">
            <div class="posts-header">
              <h2>Recent Discussions</h2>
              <el-button type="primary" @click="handleCreatePost">
                <i class="el-icon-plus"></i>
                New Post
              </el-button>
            </div>

            <!-- Category Filter -->
            <div class="category-filter">
              <el-radio-group v-model="selectedCategory" size="large">
                <el-radio-button value="">All</el-radio-button>
                <el-radio-button
                  v-for="cat in categories"
                  :key="cat.value"
                  :value="cat.value"
                >
                  {{ cat.label }}
                </el-radio-button>
              </el-radio-group>
            </div>

            <!-- Posts List -->
            <LoadingSpinner v-if="loading" />
            <div v-else class="posts-list">
              <el-empty v-if="!filteredPosts.length" description="No posts yet" />
              <div
                v-for="post in filteredPosts"
                :key="post.id"
                class="post-card card"
              >
                <div class="post-avatar">
                  {{ (post.user?.username || 'U').charAt(0).toUpperCase() }}
                </div>
                <div class="post-content">
                  <div class="post-meta">
                    <span class="post-category">{{ post.category }}</span>
                    <span class="post-date">{{ formatDate(post.created_at) }}</span>
                  </div>
                  <h3 class="post-title">{{ post.title }}</h3>
                  <p class="post-summary">{{ post.content }}</p>
                  <div class="post-stats">
                    <span><i class="el-icon-view"></i> {{ post.view_count }}</span>
                    <span><i class="el-icon-star-off"></i> {{ post.like_count }}</span>
                  </div>
                </div>
              </div>
            </div>
          </main>

          <!-- Sidebar -->
          <aside class="sidebar">
            <div class="sidebar-card card">
              <h3>Community Guidelines</h3>
              <ul>
                <li>Be respectful and constructive</li>
                <li>Search before posting</li>
                <li>Use descriptive titles</li>
                <li>Include relevant details</li>
              </ul>
            </div>

            <div class="sidebar-card card">
              <h3>Quick Links</h3>
              <ul>
                <li><a href="#">MySQL Forums</a></li>
                <li><a href="#">Stack Overflow</a></li>
                <li><a href="#">GitHub Issues</a></li>
                <li><a href="#">MySQL Blog</a></li>
              </ul>
            </div>
          </aside>
        </div>
      </div>
    </section>

    <!-- Create Post Dialog -->
    <el-dialog v-model="showCreateDialog" title="Create New Post" width="600px">
      <el-form :model="newPost" label-position="top">
        <el-form-item label="Title">
          <el-input v-model="newPost.title" placeholder="Enter post title" />
        </el-form-item>
        <el-form-item label="Category">
          <el-select v-model="newPost.category" placeholder="Select category">
            <el-option
              v-for="cat in categories"
              :key="cat.value"
              :label="cat.label"
              :value="cat.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Content">
          <el-input
            v-model="newPost.content"
            type="textarea"
            :rows="6"
            placeholder="Write your post content..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">Cancel</el-button>
        <el-button type="primary" @click="submitPost">Publish</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.community-page {
  padding-top: 64px;
}

.page-hero {
  background: linear-gradient(135deg, var(--mysql-blue), var(--mysql-dark-blue));
  padding: 80px 0;
  text-align: center;
  color: #ffffff;
}

.page-title {
  font-size: 42px;
  font-weight: 700;
  margin-bottom: 16px;
}

.page-subtitle {
  font-size: 18px;
  opacity: 0.9;
}

.community-content {
  padding: 48px 0;
  background: var(--bg-light);
  min-height: calc(100vh - 300px);
}

.content-layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 32px;
}

.posts-section {
  background: #ffffff;
  padding: 24px;
  border-radius: 8px;
}

.posts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.posts-header h2 {
  font-size: 24px;
  font-weight: 600;
}

.category-filter {
  margin-bottom: 24px;
  overflow-x: auto;
}

.posts-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.post-card {
  display: flex;
  gap: 16px;
  padding: 20px;
}

.post-avatar {
  width: 48px;
  height: 48px;
  background: var(--mysql-blue);
  color: #ffffff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
}

.post-content {
  flex: 1;
}

.post-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
}

.post-category {
  background: var(--bg-light);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--mysql-blue);
  font-weight: 500;
}

.post-date {
  color: var(--text-secondary);
}

.post-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.post-summary {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 12px;
}

.post-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.post-stats {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.post-stats span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.sidebar-card {
  padding: 20px;
}

.sidebar-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.sidebar-card ul {
  list-style: none;
  padding: 0;
}

.sidebar-card li {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-card li:last-child {
  border-bottom: none;
}

.sidebar-card a {
  color: var(--mysql-blue);
  font-size: 14px;
}

@media (max-width: 992px) {
  .content-layout {
    grid-template-columns: 1fr;
  }
  
  .sidebar {
    order: -1;
  }
}
</style>
