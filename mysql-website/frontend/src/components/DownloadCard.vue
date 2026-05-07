<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  version: string
  type: 'enterprise' | 'community' | 'cluster'
  date: string
  size: string
  platforms: string[]
  sha256?: string
}

const props = defineProps<Props>()

const isExpanded = ref(false)

const typeLabel = computed(() => {
  const labels = {
    enterprise: 'Enterprise',
    community: 'Community',
    cluster: 'Cluster'
  }
  return labels[props.type]
})

const typeClass = computed(() => `type-${props.type}`)
</script>

<template>
  <div class="download-card card">
    <div class="card-header">
      <div class="version-info">
        <span class="version-badge" :class="typeClass">{{ typeLabel }}</span>
        <h3 class="version-name">MySQL Community Server {{ version }}</h3>
      </div>
      <span class="release-date">Released: {{ date }}</span>
    </div>
    
    <div class="card-body">
      <div class="platforms">
        <span class="label">Platforms:</span>
        <el-tag v-for="platform in platforms" :key="platform" size="small">
          {{ platform }}
        </el-tag>
      </div>
      <div class="meta-info">
        <span>Size: {{ size }}</span>
      </div>
    </div>

    <div v-if="sha256" class="sha256-section">
      <div class="sha256-header" @click="isExpanded = !isExpanded">
        <span>SHA256 Checksum</span>
        <i :class="isExpanded ? 'el-icon-arrow-up' : 'el-icon-arrow-down'"></i>
      </div>
      <div v-if="isExpanded" class="sha256-value">
        {{ sha256 }}
      </div>
    </div>

    <div class="card-footer">
      <a href="#" class="btn btn-primary">
        <i class="el-icon-download"></i>
        Download
      </a>
      <router-link to="/downloads" class="btn btn-outline">
        View All Versions
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.download-card {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.version-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #ffffff;
  width: fit-content;
}

.type-enterprise {
  background: #b8860b;
}

.type-community {
  background: var(--mysql-blue);
}

.type-cluster {
  background: #2e8b57;
}

.version-name {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.release-date {
  font-size: 13px;
  color: var(--text-secondary);
}

.card-body {
  margin-bottom: 16px;
}

.platforms {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.label {
  font-size: 14px;
  color: var(--text-secondary);
}

.meta-info {
  font-size: 14px;
  color: var(--text-secondary);
}

.sha256-section {
  background: var(--bg-light);
  border-radius: 4px;
  margin-bottom: 16px;
}

.sha256-header {
  padding: 12px 16px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
}

.sha256-value {
  padding: 12px 16px;
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  border-top: 1px solid var(--border-color);
}

.card-footer {
  display: flex;
  gap: 12px;
}

.card-footer .btn {
  flex: 1;
  text-align: center;
}
</style>
