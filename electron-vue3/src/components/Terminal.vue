<template>
  <div class="terminal-container">
    <!-- 终端工具栏 -->
    <div class="terminal-toolbar">
      <div class="terminal-info">
        <span class="working-dir">{{ currentWorkingDir }}</span>
        <span class="terminal-status" :class="{ 'executing': isExecuting }">
          {{ isExecuting ? '执行中...' : '就绪' }}
        </span>
        <span v-if="engineMode" class="engine-mode">{{ engineMode }}</span>
      </div>
      <div class="terminal-actions">
        <button class="terminal-btn" @click="clearTerminal" title="清屏">🗑️</button>
        <button class="terminal-btn" @click="showSettings = !showSettings" title="设置">⚙️</button>
        <button v-if="isExecuting" class="terminal-btn stop-btn" @click="stopCurrentCommand" title="终止命令">⏹️</button>
      </div>
    </div>
    
    <!-- 终端输出区域 -->
    <div class="terminal-content" ref="terminalOutput">
      <div v-for="line in terminalHistory" :key="line.id" :class="['terminal-line', `terminal-${line.type}`]">
        <span class="line-timestamp">{{ line.timestamp }}</span>
        <span class="line-content" v-html="formatLineContent(line.content)"></span>
      </div>
      <div v-if="isExecuting" class="terminal-line terminal-system">
        <span class="line-timestamp">{{ new Date().toLocaleTimeString() }}</span>
        <span class="line-content">执行中...</span>
      </div>
    </div>
    
    <!-- 终端设置面板 -->
    <div v-if="showSettings" class="terminal-settings">
      <div class="settings-section">
        <label>工作目录:</label>
        <input type="text" v-model="currentWorkingDir" class="settings-input" @keydown.enter="changeWorkingDir" />
        <button @click="changeWorkingDir" class="settings-btn">应用</button>
      </div>
      <div class="settings-section">
        <label>执行模式:</label>
        <select v-model="executionMode" class="settings-select">
          <option value="auto">自动选择</option>
          <option value="local">本地执行</option>
        </select>
      </div>
      <div class="settings-section">
        <label>实时输出:</label>
        <input type="checkbox" v-model="realTimeOutput" class="settings-checkbox" />
      </div>
    </div>
    
    <!-- 命令自动补全 -->
    <div v-if="showAutocomplete && autocompleteOptions.length > 0" class="autocomplete-panel">
      <div 
        v-for="(option, index) in autocompleteOptions" 
        :key="index"
        :class="['autocomplete-item', { 'selected': index === selectedAutocompleteIndex }]"
        @click="selectAutocomplete(option)"
      >
        {{ option }}
      </div>
    </div>
    
    <!-- 终端输入区域 -->
    <div class="terminal-input-bar">
      <span class="terminal-prompt">{{ isMultilineMode ? '>' : '$' }}</span>
      <input 
        type="text" 
        v-model="inputCommand" 
        class="terminal-command-input" 
        :placeholder="isMultilineMode ? '继续输入多行命令...' : '输入命令并按回车执行'" 
        @keydown="handleKeydown"
        @keydown.enter="executeCommand"
        @input="handleInput"
        ref="terminalInput"
        :disabled="isExecuting"
      />
      <div class="terminal-input-actions">
        <button 
          class="terminal-run-btn" 
          :disabled="isExecuting" 
          @click="executeCommand"
          :title="isExecuting ? '执行中...' : '执行命令'"
        >
          {{ isExecuting ? '⏳' : '▶️' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
import terminalEngine from '../utils/terminalEngine.js'

export default {
  name: 'Terminal',
  props: {
    initialWorkingDir: {
      type: String,
      default: () => terminalEngine.getCurrentWorkingDirectory()
    },
    sessionId: {
      type: String,
      default: 'default'
    }
  },
  setup(props) {
    // 响应式数据
    const terminalHistory = ref([])
    const inputCommand = ref('')
    const isExecuting = ref(false)
    const currentWorkingDir = ref(props.initialWorkingDir)
    const showSettings = ref(false)
    const executionMode = ref('auto')
    const realTimeOutput = ref(true)
    const isMultilineMode = ref(false)
    const multilineBuffer = ref('')
    
    // 自动补全相关
    const showAutocomplete = ref(false)
    const autocompleteOptions = ref([])
    const selectedAutocompleteIndex = ref(0)
    
    // DOM引用
    const terminalOutput = ref(null)
    const terminalInput = ref(null)
    
    // 计算属性
    const engineMode = computed(() => {
      if (terminalEngine.isElectronEnvironment()) return 'Electron本地执行'
      if (terminalEngine.isNodeEnvironment()) return 'Node.js本地执行'
      return '浏览器本地模拟'
    })
    
    // 添加历史记录
    const addToHistory = (content, type = 'output') => {
      const timestamp = new Date().toLocaleTimeString()
      const lines = (content || '').split('\n')
      
      for (const line of lines) {
        if (line !== '' || type === 'command') {
          terminalHistory.value.push({
            content: line,
            type: type,
            timestamp: timestamp,
            id: Date.now() + Math.random()
          })
        }
      }
      
      // 自动滚动到底部
      nextTick(() => {
        if (terminalOutput.value) {
          terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight
        }
      })
    }
    
    // 清屏
    const clearTerminal = () => {
      terminalHistory.value = []
      addToHistory('Terminal cleared', 'system')
    }
    
    // 改变工作目录
    const changeWorkingDir = () => {
      if (terminalEngine.changeWorkingDirectory(currentWorkingDir.value)) {
        addToHistory(`Changed directory to: ${currentWorkingDir.value}`, 'system')
      } else {
        addToHistory(`Failed to change directory to: ${currentWorkingDir.value}`, 'error')
      }
    }
    
    // 处理特殊命令（本地处理）
    const handleSpecialCommands = (cmd) => {
      const trimmed = cmd.trim()
      
      // clear 命令
      if (trimmed === 'clear' || trimmed === 'cls') {
        clearTerminal()
        return true
      }
      
      // help 命令
      if (trimmed === 'help') {
        addToHistory(`可用命令:
  pwd     - 显示当前目录
  ls      - 列出文件
  echo    - 显示文本
  date    - 显示日期
  whoami  - 显示用户名
  clear   - 清屏
  cd      - 改变目录
  cat     - 显示文件内容
  mkdir   - 创建目录
  touch   - 创建文件
  grep    - 搜索文本
  ps      - 显示进程
  top     - 显示系统状态
  help    - 显示帮助`, 'output')
        return true
      }
      
      return false
    }
    
    // 处理多行输入
    const handleMultilineInput = (cmd) => {
      if (cmd.endsWith('\\')) {
        multilineBuffer.value += cmd.slice(0, -1) + '\n'
        isMultilineMode.value = true
        inputCommand.value = '> '
        return true
      } else if (isMultilineMode.value) {
        multilineBuffer.value += cmd
        const fullCommand = multilineBuffer.value
        multilineBuffer.value = ''
        isMultilineMode.value = false
        inputCommand.value = ''
        return fullCommand
      }
      return false
    }
    
    // 执行命令（完全前端执行）
    const executeCommand = async () => {
      let cmd = inputCommand.value.trim()
      if (!cmd || isExecuting.value) return
      
      // 重置自动补全
      showAutocomplete.value = false
      terminalEngine.resetHistoryIndex()
      
      // 处理多行输入
      const multilineResult = handleMultilineInput(cmd)
      if (multilineResult === true) return // 继续多行输入
      if (multilineResult) cmd = multilineResult // 使用完整的多行命令
      
      // 处理特殊命令
      if (handleSpecialCommands(cmd)) {
        inputCommand.value = ''
        return
      }
      
      // 添加到历史记录
      addToHistory(`$ ${cmd}`, 'command')
      terminalEngine.addToHistory(cmd)
      inputCommand.value = ''
      isExecuting.value = true
      
      try {
        // 设置实时输出回调
        if (realTimeOutput.value) {
          terminalEngine.setOutputCallback((output, type) => {
            addToHistory(output, type === 'stderr' ? 'error' : 'output')
          })
        }
        
        // 使用前端执行引擎执行命令
        const result = await terminalEngine.executeCommand(cmd, {
          cwd: currentWorkingDir.value,
          timeout: 30000,
          sessionId: props.sessionId,
          realTime: realTimeOutput.value
        })
        
        // 处理结果
        if (result.success) {
          if (result.stdout) addToHistory(result.stdout, 'output')
          if (result.stderr) addToHistory(result.stderr, 'error')
          if (result.code !== 0) {
            addToHistory(`[exit ${result.code}]`, 'system')
          }
          
          // 更新工作目录（如果命令改变了目录）
          if (result.cwd && result.cwd !== currentWorkingDir.value) {
            currentWorkingDir.value = result.cwd
          }
        } else {
          addToHistory(`Error: ${result.error}`, 'error')
        }
        
      } catch (error) {
        addToHistory(`Execution failed: ${error.message}`, 'error')
      } finally {
        isExecuting.value = false
        terminalEngine.setOutputCallback(null)
      }
    }
    
    // 停止当前命令
    const stopCurrentCommand = async () => {
      try {
        const result = await terminalEngine.killProcess(props.sessionId)
        if (result.success) {
          addToHistory('Command terminated', 'system')
        } else {
          addToHistory(`Failed to terminate: ${result.error}`, 'error')
        }
      } catch (error) {
        addToHistory(`Termination failed: ${error.message}`, 'error')
      }
      isExecuting.value = false
    }
    
    // 处理键盘输入
    const handleKeydown = (event) => {
      // 上下箭头键处理历史记录
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        const prevCmd = terminalEngine.getPreviousCommand()
        if (prevCmd) {
          inputCommand.value = prevCmd
        }
      } else if (event.key === 'ArrowDown') {
        event.preventDefault()
        const nextCmd = terminalEngine.getNextCommand()
        inputCommand.value = nextCmd
      }
      // Tab键处理自动补全
      else if (event.key === 'Tab') {
        event.preventDefault()
        if (showAutocomplete.value && autocompleteOptions.value.length > 0) {
          selectAutocomplete(autocompleteOptions.value[selectedAutocompleteIndex.value])
        }
      }
      // 自动补全导航
      else if (showAutocomplete.value) {
        if (event.key === 'ArrowUp') {
          event.preventDefault()
          selectedAutocompleteIndex.value = Math.max(0, selectedAutocompleteIndex.value - 1)
        } else if (event.key === 'ArrowDown') {
          event.preventDefault()
          selectedAutocompleteIndex.value = Math.min(autocompleteOptions.value.length - 1, selectedAutocompleteIndex.value + 1)
        }
      }
    }
    
    // 处理输入变化（自动补全）
    const handleInput = () => {
      const cmd = inputCommand.value.trim()
      if (cmd.length >= 2) {
        // 这里可以实现自动补全逻辑
        // 暂时禁用自动补全，因为需要额外的命令支持
        showAutocomplete.value = false
      } else {
        showAutocomplete.value = false
      }
    }
    
    // 选择自动补全
    const selectAutocomplete = (option) => {
      inputCommand.value = option
      showAutocomplete.value = false
    }
    
    // 格式化行内容
    const formatLineContent = (content) => {
      // 简单的ANSI颜色代码处理
      return content
        .replace(/\x1b\[31m/g, '<span class="ansi-red">')
        .replace(/\x1b\[32m/g, '<span class="ansi-green">')
        .replace(/\x1b\[33m/g, '<span class="ansi-yellow">')
        .replace(/\x1b\[34m/g, '<span class="ansi-blue">')
        .replace(/\x1b\[0m/g, '</span>')
    }
    
    // 生命周期
    onMounted(() => {
      // 初始化终端
      addToHistory('Terminal initialized', 'system')
      addToHistory(`Working directory: ${currentWorkingDir.value}`, 'system')
      
      // 设置执行模式
      if (executionMode.value === 'auto') {
        if (terminalEngine.isElectronEnvironment()) {
          addToHistory('✅ 使用Electron本地执行引擎 - 完全本地化', 'system')
        } else if (terminalEngine.isNodeEnvironment()) {
          addToHistory('✅ 使用Node.js本地执行引擎 - 完全本地化', 'system')
        } else {
          addToHistory('✅ 使用浏览器本地模拟引擎 - 完全本地化', 'system')
        }
        addToHistory('🚀 终端功能完全本地执行，无需后端支持', 'system')
      }
      
      // 聚焦输入框
      nextTick(() => {
        if (terminalInput.value) {
          terminalInput.value.focus()
        }
      })
    })
    
    onUnmounted(() => {
      // 清理资源
      terminalEngine.cleanup()
    })
    
    return {
      // 数据
      terminalHistory,
      inputCommand,
      isExecuting,
      currentWorkingDir,
      showSettings,
      executionMode,
      realTimeOutput,
      isMultilineMode,
      showAutocomplete,
      autocompleteOptions,
      selectedAutocompleteIndex,
      engineMode,
      
      // DOM引用
      terminalOutput,
      terminalInput,
      
      // 方法
      addToHistory,
      clearTerminal,
      changeWorkingDir,
      executeCommand,
      stopCurrentCommand,
      handleKeydown,
      handleInput,
      selectAutocomplete,
      formatLineContent
    }
  }
}
</script>

<style scoped>
.terminal-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  border-radius: 4px;
  overflow: hidden;
}

.terminal-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  min-height: 40px;
}

.terminal-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.working-dir {
  color: #569cd6;
  font-weight: bold;
}

.terminal-status {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  background: #0e639c;
  color: white;
}

.terminal-status.executing {
  background: #f14c4c;
  animation: pulse 1s infinite;
}

.engine-mode {
  padding: 2px 6px;
  border-radius: 8px;
  font-size: 11px;
  background: #007acc;
  color: white;
}

.terminal-actions {
  display: flex;
  gap: 8px;
}

.terminal-btn {
  background: none;
  border: none;
  color: #d4d4d4;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 16px;
  transition: background-color 0.2s;
}

.terminal-btn:hover {
  background: #3e3e42;
}

.terminal-btn.stop-btn {
  color: #f14c4c;
}

.terminal-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  background: #1e1e1e;
  font-family: 'Courier New', monospace;
  line-height: 1.4;
}

.terminal-line {
  display: flex;
  margin-bottom: 2px;
  word-break: break-all;
}

.line-timestamp {
  color: #6a9955;
  margin-right: 8px;
  min-width: 80px;
  font-size: 12px;
}

.line-content {
  flex: 1;
}

.terminal-command {
  color: #9cdcfe;
}

.terminal-output {
  color: #d4d4d4;
}

.terminal-error {
  color: #f44747;
}

.terminal-system {
  color: #6a9955;
  font-style: italic;
}

.terminal-settings {
  padding: 12px;
  background: #2d2d30;
  border-top: 1px solid #3e3e42;
}

.settings-section {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
}

.settings-section label {
  min-width: 80px;
  color: #d4d4d4;
}

.settings-input,
.settings-select {
  flex: 1;
  padding: 4px 8px;
  background: #3c3c3c;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  color: #d4d4d4;
}

.settings-btn {
  padding: 4px 12px;
  background: #0e639c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.settings-checkbox {
  margin: 0;
}

.autocomplete-panel {
  position: absolute;
  bottom: 50px;
  left: 12px;
  right: 12px;
  background: #2d2d30;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 1000;
}

.autocomplete-item {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #3e3e42;
}

.autocomplete-item:hover,
.autocomplete-item.selected {
  background: #0e639c;
}

.terminal-input-bar {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #2d2d30;
  border-top: 1px solid #3e3e42;
}

.terminal-prompt {
  color: #569cd6;
  margin-right: 8px;
  font-weight: bold;
}

.terminal-command-input {
  flex: 1;
  background: none;
  border: none;
  color: #d4d4d4;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  outline: none;
  padding: 4px 0;
}

.terminal-command-input:disabled {
  opacity: 0.6;
}

.terminal-input-actions {
  display: flex;
  gap: 8px;
  margin-left: 8px;
}

.terminal-run-btn {
  background: #0e639c;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.terminal-run-btn:disabled {
  background: #3e3e42;
  cursor: not-allowed;
}

/* ANSI颜色支持 */
.ansi-red { color: #f44747; }
.ansi-green { color: #6a9955; }
.ansi-yellow { color: #dcdcaa; }
.ansi-blue { color: #569cd6; }

/* 动画 */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 滚动条样式 */
.terminal-content::-webkit-scrollbar {
  width: 8px;
}

.terminal-content::-webkit-scrollbar-track {
  background: #2d2d30;
}

.terminal-content::-webkit-scrollbar-thumb {
  background: #3e3e42;
  border-radius: 4px;
}

.terminal-content::-webkit-scrollbar-thumb:hover {
  background: #4e4e52;
}
</style>
