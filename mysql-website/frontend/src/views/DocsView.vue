<script setup lang="ts">
import { ref, computed } from 'vue'

interface DocNode {
  id: string
  title: string
  children?: DocNode[]
}

const searchQuery = ref('')
const expandedNodes = ref<Set<string>>(new Set(['getting-started']))

const docsTree = ref<DocNode[]>([
  {
    id: 'getting-started',
    title: 'Getting Started',
    children: [
      { id: 'introduction', title: 'Introduction to MySQL' },
      { id: 'installation', title: 'Installation' },
      { id: 'quick-start', title: 'Quick Start Guide' },
      { id: 'connecting', title: 'Connecting to MySQL' }
    ]
  },
  {
    id: 'tutorials',
    title: 'Tutorials',
    children: [
      { id: 'tutorial-basics', title: 'MySQL Basics' },
      { id: 'tutorial-sql', title: 'SQL Statements' },
      { id: 'tutorial-optimization', title: 'Query Optimization' }
    ]
  },
  {
    id: 'reference',
    title: 'Reference',
    children: [
      { id: 'ref-data-types', title: 'Data Types' },
      { id: 'ref-functions', title: 'Functions' },
      { id: 'ref-commands', title: 'SQL Commands' },
      { id: 'ref-config', title: 'Configuration Options' }
    ]
  },
  {
    id: 'administration',
    title: 'Administration',
    children: [
      { id: 'admin-users', title: 'User Management' },
      { id: 'admin-backup', title: 'Backup & Recovery' },
      { id: 'admin-replication', title: 'Replication' },
      { id: 'admin-security', title: 'Security' }
    ]
  },
  {
    id: 'dev-guide',
    title: 'Developer Guide',
    children: [
      { id: 'dev-connectors', title: 'MySQL Connectors' },
      { id: 'dev-apis', title: 'APIs' },
      { id: 'dev-best-practices', title: 'Best Practices' }
    ]
  }
])

const currentDoc = ref({
  id: 'introduction',
  title: 'Introduction to MySQL',
  content: `
# Introduction to MySQL

MySQL is the world's most popular open-source relational database management system (RDBMS). 

## Key Features

- **High Performance**: MySQL delivers lightning-fast performance with optimized query processing.
- **Scalability**: From embedded applications to data warehouses serving millions of requests.
- **Reliability**: Proven technology with extensive testing and robust transaction support.
- **Security**: Enterprise-grade security features including SSL encryption and granular permissions.
- **ACID Compliance**: Full ACID transaction support for critical data operations.
- **Cross-Platform**: Runs on Windows, Linux, macOS, and many other platforms.

## MySQL Editions

MySQL is available in several editions:

1. **MySQL Community Edition**: Free, open-source version with core database features.
2. **MySQL Enterprise Edition**: Commercial edition with advanced features, tools, and support.
3. **MySQL Cluster**: Distributed database combining linear scalability and high availability.

## Getting Help

- [Official Documentation](/docs)
- [MySQL Forums](https://forums.mysql.com/)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/mysql)
  `
})

const toggleNode = (nodeId: string) => {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)
  }
}

const selectDoc = (nodeId: string, title: string) => {
  currentDoc.value = {
    id: nodeId,
    title,
    content: `# ${title}\n\nContent for this documentation page is being loaded...`
  }
}
</script>

<template>
  <div class="docs-page">
    <!-- Sidebar -->
    <aside class="docs-sidebar">
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          placeholder="Search documentation..."
          :prefix-icon="Search"
          clearable
        />
      </div>
      
      <nav class="docs-nav">
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
              @click="selectDoc(child.id, child.title)"
            >
              {{ child.title }}
            </div>
          </div>
        </div>
      </nav>
    </aside>

    <!-- Main Content -->
    <main class="docs-content">
      <div class="docs-breadcrumb">
        <span>Documentation</span>
        <span class="separator">/</span>
        <span>{{ currentDoc.title }}</span>
      </div>
      
      <article class="docs-article">
        <div class="markdown-body" v-html="currentDoc.content"></div>
      </article>
      
      <aside class="docs-toc">
        <h4>On This Page</h4>
        <ul>
          <li><a href="#key-features">Key Features</a></li>
          <li><a href="#mysql-editions">MySQL Editions</a></li>
          <li><a href="#getting-help">Getting Help</a></li>
        </ul>
      </aside>
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

.markdown-body {
  line-height: 1.8;
}

.markdown-body :deep(h1) {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 24px;
  color: var(--text-primary);
}

.markdown-body :deep(h2) {
  font-size: 24px;
  font-weight: 600;
  margin: 32px 0 16px;
  color: var(--text-primary);
}

.markdown-body :deep(p) {
  margin-bottom: 16px;
  color: var(--text-secondary);
}

.docs-toc {
  margin-top: 32px;
  padding: 20px;
  background: var(--bg-light);
  border-radius: 8px;
}

.docs-toc h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.docs-toc ul {
  list-style: none;
  padding: 0;
}

.docs-toc li {
  margin-bottom: 8px;
}

.docs-toc a {
  font-size: 13px;
  color: var(--mysql-blue);
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
