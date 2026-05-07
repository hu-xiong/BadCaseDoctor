<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import SectionHeader from '@/components/SectionHeader.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const selectedCategory = ref('')
const showCreateDialog = ref(false)
const newPost = ref({
  title: '',
  content: '',
  category: '',
  tags: []
})

const categories = [
  { value: 'general', label: 'General Discussion' },
  { value: 'help', label: 'Help & Support' },
  { value: 'showcase', label: 'Project Showcase' },
  { value: 'tutorials', label: 'Tutorials' },
  { value: 'jobs', label: 'Jobs & Opportunities' }
]

const posts = ref([
  {
    id: 1,
    title: 'Best practices for MySQL query optimization',
    summary: 'I wanted to share some tips I have learned over the years for optimizing MySQL queries...',
    author: { username: 'dbadmin', avatar: '' },
    category: 'tutorials',
    tags: ['optimization', 'performance'],
    createdAt: '2024-04-15',
    viewCount: 1234,
    replyCount: 23
  },
  {
    id: 2,
    title: 'MySQL 8.4 LTS - First impressions',
    summary: 'Just upgraded to MySQL 8.4 LTS. Here are my initial thoughts on the new features...',
    author: { username: 'techlead', avatar: '' },
    category: 'general',
    tags: ['mysql84', 'review'],
    createdAt: '2024-04-14',
    viewCount: 856,
    replyCount: 15
  },
  {
    id: 3,
    title: 'Help: Replication lag issues',
    summary: 'I am experiencing significant replication lag on my MySQL Cluster. Looking for advice...',
    author: { username: 'dba_newbie', avatar: '' },
    category: 'help',
    tags: ['replication', 'cluster'],
    createdAt: '2024-04-13',
    viewCount: 432,
    replyCount: 8
  },
  {
    id: 4,
    title: 'Showcase: Real-time analytics dashboard',
    summary: 'Built a real-time analytics dashboard using MySQL and Node.js. Sharing the architecture...',
    author: { username: 'fullstack_dev', avatar: '' },
    category: 'showcase',
    tags: ['analytics', 'nodejs'],
    createdAt: '2024-04-12',
    viewCount: 2341,
    replyCount: 45
  }
])

const filteredPosts = computed(() => {
  if (!selectedCategory.value) return posts.value
  return posts.value.filter(p => p.category === selectedCategory.value)
})

const handleCreatePost = () => {
  if (!authStore.isAuthenticated) {
    ElMessage.warning('Please login to create a post')
    return
  }
  showCreateDialog.value = true
}

const submitPost = () => {
  ElMessage.success('Post created successfully!')
  showCreateDialog.value = false
  newPost.value = { title: '', content: '', category: '', tags: [] }
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
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
            <div class="posts-list">
              <div
                v-for="post in filteredPosts"
                :key="post.id"
                class="post-card card"
              >
                <div class="post-avatar">
                  {{ post.author.username.charAt(0).toUpperCase() }}
                </div>
                <div class="post-content">
                  <div class="post-meta">
                    <span class="post-category">{{ post.category }}</span>
                    <span class="post-date">{{ formatDate(post.createdAt) }}</span>
                  </div>
                  <h3 class="post-title">{{ post.title }}</h3>
                  <p class="post-summary">{{ post.summary }}</p>
                  <div class="post-tags">
                    <el-tag
                      v-for="tag in post.tags"
                      :key="tag"
                      size="small"
                      type="info"
                    >
                      {{ tag }}
                    </el-tag>
                  </div>
                  <div class="post-stats">
                    <span><i class="el-icon-view"></i> {{ post.viewCount }}</span>
                    <span><i class="el-icon-chat-line-square"></i> {{ post.replyCount }}</span>
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
        <el-form-item label="Tags">
          <el-select
            v-model="newPost.tags"
            multiple
            filterable
            allow-create
            placeholder="Add tags"
          >
            <el-option
              v-for="tag in ['mysql', 'performance', 'optimization', 'replication']"
              :key="tag"
              :label="tag"
              :value="tag"
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
