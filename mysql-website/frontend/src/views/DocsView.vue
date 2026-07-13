<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getDocCategories, getDocPages, getDocPage, searchDocs, type DocCategory, type DocPage } from '@/api/docs'

interface DocNode {
  id: string
  docId?: number
  title: string
  children?: DocNode[]
}

const searchQuery = ref('')
const loading = ref(true)
const docsTree = ref<DocNode[]>([])
const expandedNodes = ref<Set<string>>(new Set())
const currentDoc = ref({
  id: '',
  title: 'Documentation',
  content: 'Select a topic from the sidebar to view documentation.'
})

function buildTree(categories: DocCategory[], pages: DocPage[]): DocNode[] {
  const pagesByCategory = new Map<number, DocPage[]>()
  for (const page of pages) {
    const list = pagesByCategory.get(page.category_id) || []
    list.push(page)
    pagesByCategory.set(page.category_id, list)
  }

  return categories.map(category => ({
    id: `cat-${category.id}`,
    title: category.name,
    children: (pagesByCategory.get(category.id) || []).map(page => ({
      id: `doc-${page.id}`,
      docId: page.id,
      title: page.title
    }))
  }))
}

async function loadDocs() {
  loading.value = true
  try {
    const [categories, pagesData] = await Promise.all([
      getDocCategories(),
      getDocPages({ page: 1, page_size: 100 })
    ])
    docsTree.value = buildTree(categories, pagesData.list)
    if (docsTree.value.length) {
      expandedNodes.value.add(docsTree.value[0].id)
      const firstDoc = docsTree.value[0].children?.[0]
      if (firstDoc?.docId) {
        await selectDoc(firstDoc.id, firstDoc.docId, firstDoc.title)
      }
    }
  } catch {
    docsTree.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadDocs)

const toggleNode = (nodeId: string) => {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)
  }
}

const selectDoc = async (nodeId: string, docId: number, title: string) => {
  currentDoc.value = { id: nodeId, title, content: 'Loading...' }
  try {
    const page = await getDocPage(docId)
    currentDoc.value = {
      id: nodeId,
      title: page.title,
      content: page.content
    }
  } catch {
    currentDoc.value = {
      id: nodeId,
      title,
      content: 'Failed to load document content.'
    }
  }
}

watch(searchQuery, async (keyword) => {
  if (!keyword.trim()) {
    await loadDocs()
    return
  }
  try {
    const results = await searchDocs(keyword.trim())
    docsTree.value = [{
      id: 'search-results',
      title: 'Search Results',
      children: results.map(item => ({
        id: `doc-${item.id}`,
        docId: item.id,
        title: item.title
      }))
    }]
    expandedNodes.value = new Set(['search-results'])
  } catch {
    docsTree.value = []
  }
})
</script>

<template>
  <div class="docs-page">
    <aside class="docs-sidebar">
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          placeholder="Search documentation..."
          :prefix-icon="Search"
          clearable
        />
      </div>

      <LoadingSpinner v-if="loading" />
      <nav v-else class="docs-nav">
        <div
          v-for="section in docsTree"
          :key="section.id"
          class="doc-section"
        >
          <div
            class="doc-section-header"
            :class="{ 'is-active': expandedNodes.has(section.id) }"
            @click="toggleNode(section.id)"
          >
            <span>{{ section.title }}</span>
            <i :class="expandedNodes.has(section.id) ? 'el-icon-arrow-down' : 'el-icon-arrow-right'"></i>
          </div>

          <div v-if="expandedNodes.has(section.id) && section.children" class="doc-children">
            <div
              v-for="child in section.children"
              :key="child.id"
              class="doc-item"
              :class="{ 'is-active': currentDoc.id === child.id }"
              @click="child.docId && selectDoc(child.id, child.docId, child.title)"
            >
              {{ child.title }}
            </div>
          </div>
        </div>
      </nav>
    </aside>

    <main class="docs-content">
      <div class="docs-breadcrumb">
        <span>Documentation</span>
        <span class="separator">/</span>
        <span>{{ currentDoc.title }}</span>
      </div>

      <article class="docs-article">
        <h1>{{ currentDoc.title }}</h1>
        <div class="markdown-body">{{ currentDoc.content }}</div>
      </article>
    </main>
  </div>
</template>

<script lang="ts">
import { Search } from '@element-plus/icons-vue'
export default {
  components: { Search }
}
</script>

<style scoped>
.docs-page {
  display: flex;
  padding-top: 64px;
  min-height: calc(100vh - 64px);
}

.docs-sidebar {
  width: 280px;
  background: #ffffff;
  border-right: 1px solid var(--border-color);
  padding: 24px;
  position: sticky;
  top: 64px;
  height: calc(100vh - 64px);
  overflow-y: auto;
}

.search-box {
  margin-bottom: 24px;
}

.docs-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-section {
  margin-bottom: 8px;
}

.doc-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.2s;
}

.doc-section-header:hover,
.doc-section-header.is-active {
  background: var(--bg-light);
}

.doc-children {
  padding-left: 16px;
  margin-top: 4px;
}

.doc-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.doc-item:hover {
  color: var(--mysql-blue);
  background: var(--bg-light);
}

.doc-item.is-active {
  color: var(--mysql-blue);
  background: rgba(0, 117, 143, 0.1);
  font-weight: 500;
}

.docs-content {
  flex: 1;
  padding: 32px 48px;
  max-width: 900px;
}

.docs-breadcrumb {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.docs-breadcrumb .separator {
  margin: 0 8px;
}

.docs-article {
  background: #ffffff;
  padding: 32px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.docs-article h1 {
  font-size: 32px;
  margin-bottom: 24px;
}

.markdown-body {
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

@media (max-width: 992px) {
  .docs-sidebar {
    display: none;
  }

  .docs-content {
    padding: 24px;
  }
}
</style>
