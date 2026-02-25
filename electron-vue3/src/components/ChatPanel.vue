<template>
  <div class="chat-panel-wrapper">
    <vue-advanced-chat
      :current-user-id="currentUserId"
      :rooms="rooms"
      :messages="messages"
      :room-id="roomId"
      :loading-rooms="loadingRooms"
      :rooms-loaded="roomsLoaded"
      :messages-loaded="messagesLoaded"
      :room-actions="roomActions"
      :menu-actions="menuActions"
      :message-actions="messageActions"
      :show-audio="false"
      :show-files="true"
      :show-emojis="true"
      :show-reaction-emojis="true"
      :text-messages="textMessages"
      :theme="theme"
      :styles="customStyles"
      @send-message="sendMessage"
      @fetch-messages="fetchMessages"
      @send-message-reaction="sendMessageReaction"
      @typing-message="typingMessage"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { register } from 'vue-advanced-chat'

register()

// 当前用户ID（从用户store中获取）
const currentUserId = ref('1')

// 聊天室列表
const rooms = ref([
  {
    roomId: 'badcase-analysis',
    roomName: 'BadCase 分析讨论',
    avatar: '🐛',
    unreadCount: 0,
    lastMessage: {
      content: '开始讨论当前的BadCase问题',
      senderId: '2',
      timestamp: new Date().toString()
    },
    users: [
      {
        _id: '1',
        username: '我',
        avatar: '👤',
        status: {
          state: 'online',
          lastChanged: new Date()
        }
      },
      {
        _id: '2',
        username: 'AI助手',
        avatar: '🤖',
        status: {
          state: 'online',
          lastChanged: new Date()
        }
      }
    ]
  },
  {
    roomId: 'code-review',
    roomName: '代码审查',
    avatar: '💻',
    unreadCount: 0,
    lastMessage: {
      content: '欢迎来到代码审查频道',
      senderId: '2',
      timestamp: new Date().toString()
    },
    users: [
      {
        _id: '1',
        username: '我',
        avatar: '👤',
        status: {
          state: 'online',
          lastChanged: new Date()
        }
      },
      {
        _id: '2',
        username: 'AI助手',
        avatar: '🤖',
        status: {
          state: 'online',
          lastChanged: new Date()
        }
      }
    ]
  }
])

// 当前聊天室ID
const roomId = ref('badcase-analysis')

// 消息列表
const messages = ref([
  {
    _id: '1',
    content: '你好！我是BadCase Doctor的AI助手。我可以帮你：\n\n1. 分析BadCase的根本原因\n2. 提供代码修复建议\n3. 解答测试相关问题\n4. 协助文档编写\n\n请告诉我你需要什么帮助？',
    senderId: '2',
    username: 'AI助手',
    avatar: '🤖',
    date: new Date().toString(),
    timestamp: new Date().toLocaleTimeString(),
    system: false,
    saved: true,
    distributed: true,
    seen: true,
    new: false
  }
])

// 加载状态
const loadingRooms = ref(false)
const roomsLoaded = ref(true)
const messagesLoaded = ref(true)

// 聊天室操作
const roomActions = ref([
  { name: 'inviteUser', title: '邀请成员' },
  { name: 'removeUser', title: '移除成员' },
  { name: 'deleteRoom', title: '删除频道' }
])

// 菜单操作
const menuActions = ref([
  { name: 'clearMessages', title: '清空消息' },
  { name: 'exportChat', title: '导出聊天记录' }
])

// 消息操作
const messageActions = ref([
  { name: 'replyMessage', title: '回复' },
  { name: 'editMessage', title: '编辑', onlyMe: true },
  { name: 'deleteMessage', title: '删除', onlyMe: true },
  { name: 'selectMessages', title: '选择' }
])

// 文本配置
const textMessages = ref({
  ROOMS_EMPTY: '暂无聊天室',
  ROOM_EMPTY: '没有选择聊天室',
  NEW_MESSAGES: '新消息',
  MESSAGE_DELETED: '消息已删除',
  MESSAGES_EMPTY: '暂无消息',
  CONVERSATION_STARTED: '对话开始于:',
  TYPE_MESSAGE: '输入消息...',
  SEARCH: '搜索',
  IS_ONLINE: '在线',
  LAST_SEEN: '最后上线时间:',
  IS_TYPING: '正在输入...',
  CANCEL_SELECT_MESSAGE: '取消选择'
})

// 主题配置
const theme = ref('dark')

// 自定义样式
const customStyles = computed(() => ({
  general: {
    color: '#d4d4d4',
    backgroundInput: '#2d2d2d',
    colorPlaceholder: '#888',
    colorCaret: '#007acc'
  },
  container: {
    borderRadius: '8px'
  },
  header: {
    background: '#2d2d2d',
    colorRoomName: '#ffffff',
    colorRoomInfo: '#aaa'
  },
  content: {
    background: '#1e1e1e'
  },
  sidemenu: {
    background: '#252526',
    backgroundHover: '#2a2d2e',
    backgroundActive: '#37373d',
    colorActive: '#ffffff',
    borderColorSearch: '#3e3e3e'
  },
  footer: {
    background: '#2d2d2d',
    borderStyleInput: '1px solid #3e3e3e',
    borderInputSelected: '#007acc',
    backgroundReply: '#37373d'
  },
  message: {
    background: '#37373d',
    backgroundMe: '#0e639c',
    color: '#d4d4d4',
    colorStarted: '#888',
    backgroundDeleted: '#1e1e1e'
  },
  markdown: {
    background: '#2d2d2d',
    border: '1px solid #3e3e3e',
    color: '#d4d4d4',
    colorMulti: '#888'
  },
  room: {
    colorUsername: '#ffffff',
    colorMessage: '#aaa',
    colorTimestamp: '#888',
    colorStateOnline: '#4caf50',
    colorStateOffline: '#9e9e9e'
  },
  emoji: {
    background: '#2d2d2d'
  },
  icons: {
    search: '#888',
    add: '#007acc',
    toggle: '#888',
    menu: '#888',
    close: '#888',
    closeImage: '#ffffff',
    file: '#007acc',
    paperclip: '#888',
    send: '#007acc',
    sendDisabled: '#555',
    emoji: '#888',
    emojiReaction: '#888',
    document: '#007acc',
    pencil: '#888',
    checkmark: '#4caf50',
    eye: '#888',
    dropdownMessage: '#888',
    dropdownMessageBackground: '#2d2d2d',
    dropdownRoom: '#888',
    dropdownScroll: '#0e639c',
    microphone: '#888',
    audioPlay: '#4caf50',
    audioPause: '#888',
    audioDownload: '#007acc',
    audioCancel: '#f44336'
  }
}))

// 发送消息
const sendMessage = ({ content, roomId, files, replyMessage }) => {
  const newMessage = {
    _id: Date.now().toString(),
    content,
    senderId: currentUserId.value,
    username: '我',
    avatar: '👤',
    date: new Date().toString(),
    timestamp: new Date().toLocaleTimeString(),
    system: false,
    saved: true,
    distributed: true,
    seen: false,
    new: true
  }

  if (replyMessage) {
    newMessage.replyMessage = replyMessage
  }

  if (files && files.length) {
    newMessage.files = files
  }

  messages.value.push(newMessage)

  // 模拟AI回复
  setTimeout(() => {
    const aiResponse = {
      _id: (Date.now() + 1).toString(),
      content: generateAIResponse(content),
      senderId: '2',
      username: 'AI助手',
      avatar: '🤖',
      date: new Date().toString(),
      timestamp: new Date().toLocaleTimeString(),
      system: false,
      saved: true,
      distributed: true,
      seen: false,
      new: true
    }
    messages.value.push(aiResponse)
  }, 1000)
}

// 生成AI回复（简单示例）
const generateAIResponse = (userMessage) => {
  const lowerMsg = userMessage.toLowerCase()
  
  if (lowerMsg.includes('badcase') || lowerMsg.includes('问题')) {
    return '我理解你遇到了一个BadCase。让我帮你分析一下：\n\n1. **问题描述**：请详细说明问题的表现\n2. **重现步骤**：提供复现问题的步骤\n3. **预期行为**：说明应该是什么样的正确行为\n4. **实际行为**：描述实际发生的情况\n\n请提供更多细节，我会给出具体的分析和建议。'
  } else if (lowerMsg.includes('代码') || lowerMsg.includes('code')) {
    return '关于代码问题，我可以：\n\n```python\n# 示例：BadCase分析函数\ndef analyze_badcase(case):\n    # 提取关键信息\n    error_type = case.get("error_type")\n    stack_trace = case.get("stack_trace")\n    \n    # 分析根本原因\n    root_cause = identify_root_cause(error_type, stack_trace)\n    \n    return {\n        "cause": root_cause,\n        "suggestion": get_fix_suggestion(root_cause)\n    }\n```\n\n请告诉我具体需要分析什么代码？'
  } else if (lowerMsg.includes('帮助') || lowerMsg.includes('help')) {
    return '我可以帮你：\n\n📋 **BadCase分析**\n- 根本原因分析\n- 影响范围评估\n- 修复方案建议\n\n💻 **代码支持**\n- 代码审查\n- Bug定位\n- 重构建议\n\n📝 **文档协助**\n- 测试用例编写\n- 技术文档整理\n- 问题报告生成\n\n有什么我可以帮助你的吗？'
  }
  
  return '收到你的消息！有什么我可以帮助你的吗？你可以问我关于BadCase分析、代码问题或测试相关的问题。'
}

// 获取更多消息（滚动加载）
const fetchMessages = ({ room, options = {} }) => {
  // 实现消息分页加载逻辑
  console.log('Fetching more messages for room:', room.roomId)
}

// 添加消息反应
const sendMessageReaction = ({ messageId, reaction, remove }) => {
  const message = messages.value.find(m => m._id === messageId)
  if (message) {
    if (!message.reactions) {
      message.reactions = {}
    }
    
    if (remove) {
      delete message.reactions[currentUserId.value]
    } else {
      message.reactions[currentUserId.value] = reaction
    }
  }
}

// 正在输入提示
const typingMessage = ({ message, roomId }) => {
  console.log('User typing:', message, 'in room:', roomId)
}
</script>

<style scoped>
.chat-panel-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>

<style>
/* 覆盖vue-advanced-chat的默认样式以适应暗色主题 */
.vac-card-window {
  background: #1e1e1e !important;
}
</style>

