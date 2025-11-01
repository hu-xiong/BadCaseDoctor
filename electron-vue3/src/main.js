import { createApp } from 'vue'
import './style.css'
// vue3-beautiful-chat 样式导入 - 请先安装包：pnpm install vue3-beautiful-chat
// 安装后检查 node_modules/vue3-beautiful-chat 目录中的实际 CSS 路径
// import 'vue3-beautiful-chat/dist/vue3-beautiful-chat.css'
// 如果上述路径不存在，可能的路径有：
// import 'vue3-beautiful-chat/src/assets/style.css'
// 或者包可能自带样式，无需单独导入

import App from './App.vue'
import router from './router/index.js'

const app = createApp(App)

app.use(router)

app.mount('#app')
