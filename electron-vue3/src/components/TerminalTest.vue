<template>
  <div class="terminal-test-container">
    <h2>终端执行引擎测试</h2>
    <div class="test-info">
      <p><strong>执行模式:</strong> {{ engineMode }}</p>
      <p><strong>工作目录:</strong> {{ currentWorkingDir }}</p>
      <p><strong>环境检测:</strong></p>
      <ul>
        <li>Electron环境: {{ isElectron ? '是' : '否' }}</li>
        <li>Node.js环境: {{ isNode ? '是' : '否' }}</li>
        <li>浏览器环境: {{ isBrowser ? '是' : '否' }}</li>
      </ul>
    </div>
    
    <div class="terminal-wrapper">
      <Terminal 
        :initial-working-dir="currentWorkingDir"
        session-id="test-session"
      />
    </div>
    
    <div class="test-commands">
      <h3>本地执行测试命令</h3>
      <div class="command-buttons">
        <button @click="runTestCommand('pwd')" class="test-btn">pwd</button>
        <button @click="runTestCommand('ls -la')" class="test-btn">ls -la</button>
        <button @click="runTestCommand('echo Hello World')" class="test-btn">echo</button>
        <button @click="runTestCommand('date')" class="test-btn">date</button>
        <button @click="runTestCommand('whoami')" class="test-btn">whoami</button>
        <button @click="runTestCommand('cat app.py')" class="test-btn">cat</button>
        <button @click="runTestCommand('mkdir test')" class="test-btn">mkdir</button>
        <button @click="runTestCommand('touch test.txt')" class="test-btn">touch</button>
        <button @click="runTestCommand('ps')" class="test-btn">ps</button>
        <button @click="runTestCommand('help')" class="test-btn">help</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import Terminal from './Terminal.vue'
import terminalEngine from '../utils/terminalEngine.js'

export default {
  name: 'TerminalTest',
  components: {
    Terminal
  },
  setup() {
    const currentWorkingDir = ref('/Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor')
    
    // 环境检测
    const isElectron = computed(() => terminalEngine.isElectronEnvironment())
    const isNode = computed(() => terminalEngine.isNodeEnvironment())
    const isBrowser = computed(() => !isElectron.value && !isNode.value)
    
    const engineMode = computed(() => {
      if (isElectron.value) return 'Electron本地执行'
      if (isNode.value) return 'Node.js本地执行'
      return '浏览器本地模拟'
    })
    
    const runTestCommand = async (command) => {
      console.log('执行测试命令:', command)
      
      try {
        // 直接调用终端引擎执行命令
        const result = await terminalEngine.executeCommand(command, {
          cwd: currentWorkingDir.value,
          timeout: 10000,
          sessionId: 'test-session'
        })
        
        console.log('执行结果:', result)
        
        if (result.success) {
          console.log('✅ 命令执行成功')
          if (result.stdout) console.log('输出:', result.stdout)
          if (result.stderr) console.log('错误:', result.stderr)
        } else {
          console.log('❌ 命令执行失败:', result.error)
        }
      } catch (error) {
        console.error('❌ 执行异常:', error.message)
      }
    }
    
    onMounted(() => {
      console.log('终端测试页面已加载')
      console.log('执行引擎模式:', engineMode.value)
    })
    
    return {
      currentWorkingDir,
      isElectron,
      isNode,
      isBrowser,
      engineMode,
      runTestCommand
    }
  }
}
</script>

<style scoped>
.terminal-test-container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.test-info {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.test-info p {
  margin: 5px 0;
}

.test-info ul {
  margin: 10px 0;
  padding-left: 20px;
}

.terminal-wrapper {
  height: 400px;
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 20px;
}

.test-commands {
  background: #f9f9f9;
  padding: 15px;
  border-radius: 8px;
}

.command-buttons {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.test-btn {
  padding: 8px 16px;
  background: #007acc;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.test-btn:hover {
  background: #005a9e;
}
</style>
