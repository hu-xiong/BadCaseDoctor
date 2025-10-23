<template>
  <div class="import-database">
    <!-- 导航栏 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
      <div class="container-fluid">
        <div class="navbar-nav">
          <a class="nav-link" href="#" @click="$router.push('/dashboard')">
            <i class="bi bi-arrow-left me-1"></i>
            返回仪表板
          </a>
        </div>
        <a class="navbar-brand" href="#">
          <i class="bi bi-database me-2"></i>
          导入数据库
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
                <i class="bi bi-database me-2"></i>
                数据库数据导入
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
                      <label for="host" class="form-label">数据库主机</label>
                      <input
                        type="text"
                        class="form-control"
                        id="host"
                        v-model="importData.host"
                        required
                        placeholder="localhost"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <label for="port" class="form-label">端口</label>
                      <input
                        type="number"
                        class="form-control"
                        id="port"
                        v-model="importData.port"
                        required
                        placeholder="3306"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <label for="username" class="form-label">用户名</label>
                      <input
                        type="text"
                        class="form-control"
                        id="username"
                        v-model="importData.username"
                        required
                        placeholder="请输入数据库用户名"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <label for="password" class="form-label">密码</label>
                      <input
                        type="password"
                        class="form-control"
                        id="password"
                        v-model="importData.password"
                        required
                        placeholder="请输入数据库密码"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <label for="database" class="form-label">数据库名</label>
                      <input
                        type="text"
                        class="form-control"
                        id="database"
                        v-model="importData.database"
                        required
                        placeholder="请输入数据库名"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <label for="table" class="form-label">表名</label>
                      <input
                        type="text"
                        class="form-control"
                        id="table"
                        v-model="importData.table"
                        required
                        placeholder="请输入表名"
                      />
                    </div>
                    
                    <div class="mb-3">
                      <button type="submit" class="btn btn-primary" :disabled="importing">
                        <span v-if="importing" class="spinner-border spinner-border-sm me-2"></span>
                        <i v-else class="bi bi-database me-2"></i>
                        {{ importing ? '导入中...' : '开始导入' }}
                      </button>
                      <button type="button" class="btn btn-outline-secondary ms-2" @click="testConnection">
                        <i class="bi bi-plug me-2"></i>
                        测试连接
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
                      <h6>数据库表结构要求：</h6>
                      <ul class="mb-3">
                        <li><strong>case_category</strong>：问题分类</li>
                        <li><strong>base_problem</strong>：具体问题</li>
                        <li><strong>badcase_result</strong>：BadCase问题结果</li>
                        <li><strong>correct_answer</strong>：应该得到的正确答案</li>
                        <li><strong>problem_reason</strong>：问题原因（可选）</li>
                        <li><strong>priority</strong>：优先级（p1/p2/p3，默认为p3）</li>
                      </ul>
                      
                      <h6>注意事项：</h6>
                      <ul>
                        <li>确保数据库连接信息正确</li>
                        <li>表必须包含必要的字段</li>
                        <li>必填字段不能为空</li>
                        <li>优先级只能是p1、p2、p3</li>
                        <li>建议先测试连接再导入</li>
                      </ul>
                      
                      <h6>支持的数据库：</h6>
                      <ul>
                        <li>MySQL</li>
                        <li>MariaDB</li>
                        <li>PostgreSQL（需要调整连接参数）</li>
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
import { getProjects, importDatabase } from '../api.js'
import user, { logout } from '../store/user.js'

const router = useRouter()

// 状态
const importing = ref(false)
const testing = ref(false)

// 数据
const projects = ref([])
const importResult = ref(null)

// 导入数据
const importData = reactive({
  project_id: '',
  host: 'localhost',
  port: 3306,
  username: '',
  password: '',
  database: '',
  table: ''
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

// 测试连接
async function testConnection() {
  if (!importData.host || !importData.port || !importData.username || !importData.password || !importData.database) {
    alert('请填写完整的数据库连接信息')
    return
  }
  
  testing.value = true
  try {
    const response = await fetch('/api/test_database_connection', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        host: importData.host,
        port: importData.port,
        username: importData.username,
        password: importData.password,
        database: importData.database
      })
    })
    const data = await response.json()
    
    if (data.success) {
      alert('数据库连接成功！')
    } else {
      alert(data.error || '数据库连接失败')
    }
  } catch (error) {
    console.error('测试连接失败:', error)
    alert('测试连接失败')
  } finally {
    testing.value = false
  }
}

// 处理导入
async function handleImport() {
  if (!importData.project_id) {
    alert('请选择项目')
    return
  }
  
  if (!importData.host || !importData.port || !importData.username || !importData.password || !importData.database || !importData.table) {
    alert('请填写完整的数据库连接信息')
    return
  }
  
  importing.value = true
  try {
    const response = await importDatabase(importData)
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

// 生命周期
onMounted(() => {
  fetchProjects()
})
</script>

<style scoped>
.import-database {
  min-height: 100vh;
  background-color: #f8f9fa;
}
</style> 