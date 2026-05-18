<template>
  <div class="import-excel">
    <!-- 导航栏 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
      <div class="container-fluid">
        <div class="navbar-nav">
          <a class="nav-link" href="#" @click="$router.push('/project-manage')">
            <i class="bi bi-arrow-left me-1"></i>
            返回仪表板
          </a>
        </div>
        <a class="navbar-brand" href="#">
          <i class="bi bi-upload me-2"></i>
          导入Excel
        </a>
        <div class="navbar-nav ms-auto">
          <div class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
              <i class="bi bi-person-circle me-1"></i>
              {{ user?.name || '用户' }}
            </a>
            <ul class="dropdown-menu">
              <li><a class="dropdown-item" href="#" @click="logout">退出登录</a></li>
            </ul>
          </div>
        </div>
      </div>
    </nav>

    <div class="container-fluid mt-4">
      <div class="row">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-file-earmark-excel me-2"></i>
                Excel数据导入
              </h5>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-6">
                  <form @submit.prevent="handleImport">
                    <div class="mb-3">
                      <label for="project-select" class="form-label">选择项目</label>
                      <select class="form-select" id="project-select" v-model="importData.project_id" required>
                        <option value="">请选择项目</option>
                        <option v-for="project in projects" :key="project.id" :value="project.id">
                          {{ project.name }}
                        </option>
                      </select>
                    </div>
                    
                    <div class="mb-3">
                      <label for="excel-file" class="form-label">选择Excel文件</label>
                      <input
                        type="file"
                        class="form-control"
                        id="excel-file"
                        accept=".xlsx,.xls"
                        @change="handleFileSelect"
                        required
                      />
                      <div class="form-text">支持Excel文件格式（.xlsx, .xls）</div>
                    </div>
                    
                    <div class="mb-3">
                      <button type="submit" class="btn btn-primary" :disabled="importing">
                        <span v-if="importing" class="spinner-border spinner-border-sm me-2"></span>
                        <i v-else class="bi bi-upload me-2"></i>
                        {{ importing ? '导入中...' : '开始导入' }}
                      </button>
                      <button type="button" class="btn btn-outline-secondary ms-2" @click="downloadTemplate">
                        <i class="bi bi-download me-2"></i>
                        下载模板
                      </button>
                    </div>
                  </form>
                </div>
                
                <div class="col-md-6">
                  <div class="card">
                    <div class="card-header">
                      <h6 class="card-title mb-0">导入说明</h6>
                    </div>
                    <div class="card-body">
                      <h6>Excel文件格式要求：</h6>
                      <ul class="mb-3">
                        <li><strong>case_category</strong>：问题分类</li>
                        <li><strong>base_problem</strong>：具体问题</li>
                        <li><strong>badcase_result</strong>：BadCase问题结果</li>
                        <li><strong>answer</strong>：答案</li>
                        <li><strong>correct_answer</strong>：正确答案</li>
                        <li><strong>problem_reason</strong>：问题原因（可选）</li>
                        <li><strong>priority</strong>：优先级（p1/p2/p3，默认为p3）</li>
                      </ul>
                      
                      <h6>注意事项：</h6>
                      <ul>
                        <li>第一行应为列标题</li>
                        <li>必填字段不能为空</li>
                        <li>优先级只能是p1、p2、p3</li>
                        <li>文件大小不超过10MB</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 导入结果 -->
              <div v-if="importResult" class="mt-4">
                <div class="card">
                  <div class="card-header">
                    <h6 class="card-title mb-0">导入结果</h6>
                  </div>
                  <div class="card-body">
                    <div class="row">
                      <div class="col-md-3">
                        <div class="text-center">
                          <h4 class="text-success">{{ importResult.imported }}</h4>
                          <p class="text-muted">成功导入</p>
                        </div>
                      </div>
                      <div class="col-md-3">
                        <div class="text-center">
                          <h4 class="text-danger">{{ importResult.failed }}</h4>
                          <p class="text-muted">导入失败</p>
                        </div>
                      </div>
                    </div>
                    
                    <div v-if="importResult.fail_rows && importResult.fail_rows.length > 0" class="mt-3">
                      <h6>失败详情：</h6>
                      <div class="table-responsive">
                        <table class="table table-sm">
                          <thead>
                            <tr>
                              <th>行号</th>
                              <th>错误信息</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="row in importResult.fail_rows" :key="row.row">
                              <td>{{ row.row }}</td>
                              <td>{{ row.error }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getProjects, importExcel } from '../api.js'
import user, { logout } from '../store/user.js'

const router = useRouter()

// 状态
const importing = ref(false)

// 数据
const projects = ref([])
const importResult = ref(null)

// 导入数据
const importData = reactive({
  project_id: '',
  file: null
})

// 获取项目列表
async function fetchProjects() {
  try {
    const response = await getProjects()
    if (response.data.success) {
      projects.value = response.data.projects
    }
  } catch (error) {
    console.error('获取项目列表失败:', error)
    alert('获取项目列表失败')
  }
}

// 处理文件选择
function handleFileSelect(event) {
  importData.file = event.target.files[0]
}

// 处理导入
async function handleImport() {
  if (!importData.project_id) {
    alert('请选择项目')
    return
  }
  
  if (!importData.file) {
    alert('请选择文件')
    return
  }
  
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('project_id', importData.project_id)
    formData.append('file', importData.file)
    
    const response = await importExcel(formData)
    if (response.data.success) {
      importResult.value = response.data
      alert(`导入完成：成功${response.data.imported}条，失败${response.data.failed}条`)
    } else {
      alert(response.data.error || '导入失败')
    }
  } catch (error) {
    console.error('导入失败:', error)
    alert('导入失败')
  } finally {
    importing.value = false
  }
}

// 下载模板
function downloadTemplate() {
  const templateData = [
    {
      case_category: '示例分类',
      base_problem: '这是一个示例问题描述',
      badcase_result: '这是BadCase的问题结果',
      answer: '这是答案',
      correct_answer: '这是正确答案',
      problem_reason: '这是问题原因（可选）',
      priority: 'p3'
    }
  ]
  
  const csvContent = [
    'case_category,base_problem,badcase_result,answer,correct_answer,problem_reason,priority',
    ...templateData.map(row => 
      `${row.case_category},${row.base_problem},${row.badcase_result},${row.answer},${row.correct_answer},${row.problem_reason},${row.priority}`
    )
  ].join('\n')
  
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'badcase-template.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 生命周期
onMounted(() => {
  fetchProjects()
})
</script>

<style scoped>
.import-excel {
  min-height: 100vh;
  background-color: #f8f9fa;
}
</style> 