<script setup lang="ts">
import { ref, computed } from 'vue'
import SectionHeader from '@/components/SectionHeader.vue'
import DownloadCard from '@/components/DownloadCard.vue'

type DownloadType = 'enterprise' | 'community' | 'cluster'
type OS = 'windows' | 'linux' | 'macos' | 'all'

const selectedType = ref<DownloadType>('community')
const selectedOS = ref<OS>('all')

const versions = ref([
  {
    id: 1,
    version: '8.4.0 LTS',
    type: 'community' as const,
    date: '2024-04-15',
    size: '243 MB',
    platforms: ['Windows', 'Linux', 'macOS'],
    sha256: 'a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456'
  },
  {
    id: 2,
    version: '8.0.36',
    type: 'community' as const,
    date: '2024-02-20',
    size: '238 MB',
    platforms: ['Windows', 'Linux', 'macOS'],
    sha256: 'b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567a'
  },
  {
    id: 3,
    version: '8.4.0 LTS',
    type: 'enterprise' as const,
    date: '2024-04-15',
    size: '312 MB',
    platforms: ['Windows', 'Linux', 'macOS'],
    sha256: 'c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567ab'
  },
  {
    id: 4,
    version: '8.0.36',
    type: 'cluster' as const,
    date: '2024-02-20',
    size: '198 MB',
    platforms: ['Linux', 'Windows'],
    sha256: 'd4e5f6789012345678901234567890abcdef1234567890abcdef1234567abc'
  }
])

const filteredVersions = computed(() => {
  return versions.value.filter(v => {
    const typeMatch = v.type === selectedType.value
    const osMatch = selectedOS.value === 'all' || v.platforms.some(p => 
      p.toLowerCase().includes(selectedOS.value)
    )
    return typeMatch && osMatch
  })
})

const typeOptions = [
  { value: 'enterprise', label: 'MySQL Enterprise' },
  { value: 'community', label: 'MySQL Community' },
  { value: 'cluster', label: 'MySQL Cluster' }
]

const osOptions = [
  { value: 'all', label: 'All Platforms' },
  { value: 'windows', label: 'Windows' },
  { value: 'linux', label: 'Linux' },
  { value: 'macos', label: 'macOS' }
]
</script>

<template>
  <div class="downloads-page">
    <!-- Hero -->
    <section class="page-hero">
      <div class="container">
        <h1 class="page-title">Download MySQL</h1>
        <p class="page-subtitle">
          Get the world's most popular open source database for your platform
        </p>
      </div>
    </section>

    <!-- Filters -->
    <section class="filters-section">
      <div class="container">
        <div class="filters">
          <div class="filter-group">
            <label class="filter-label">Edition:</label>
            <el-radio-group v-model="selectedType" size="large">
              <el-radio-button
                v-for="opt in typeOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
          <div class="filter-group">
            <label class="filter-label">Operating System:</label>
            <el-select v-model="selectedOS" size="large">
              <el-option
                v-for="opt in osOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
        </div>
      </div>
    </section>

    <!-- Downloads List -->
    <section class="downloads-section">
      <div class="container">
        <SectionHeader
          title="Available Versions"
          :subtitle="`Showing ${filteredVersions.length} version(s)`"
        />
        <div class="downloads-grid">
          <DownloadCard
            v-for="v in filteredVersions"
            :key="v.id"
            :version="v.version"
            :type="v.type"
            :date="v.date"
            :size="v.size"
            :platforms="v.platforms"
            :sha256="v.sha256"
          />
        </div>
      </div>
    </section>

    <!-- Info Section -->
    <section class="info-section">
      <div class="container">
        <div class="info-grid">
          <div class="info-card card">
            <h3>Installation Guides</h3>
            <p>Step-by-step installation guides for all supported platforms.</p>
            <router-link to="/docs/installation" class="info-link">
              View Installation Guide →
            </router-link>
          </div>
          <div class="info-card card">
            <h3>Verify Your Download</h3>
            <p>Learn how to verify the integrity of your download using SHA256 checksums.</p>
            <router-link to="/docs/verify" class="info-link">
              Learn More →
            </router-link>
          </div>
          <div class="info-card card">
            <h3>Release Notes</h3>
            <p>Read about new features, improvements, and bug fixes in each release.</p>
            <router-link to="/docs/release-notes" class="info-link">
              View Release Notes →
            </router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.downloads-page {
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

.filters-section {
  background: #ffffff;
  padding: 24px 0;
  border-bottom: 1px solid var(--border-color);
  position: sticky;
  top: 64px;
  z-index: 100;
}

.filters {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.downloads-section {
  padding: 64px 0;
  background: var(--bg-light);
  min-height: 400px;
}

.downloads-grid {
  display: grid;
  gap: 24px;
}

.info-section {
  padding: 64px 0;
  background: #ffffff;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.info-card {
  padding: 32px;
}

.info-card h3 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.info-card p {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
  line-height: 1.6;
}

.info-link {
  font-size: 14px;
  font-weight: 500;
  color: var(--mysql-blue);
}

@media (max-width: 992px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  
  .filters {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
