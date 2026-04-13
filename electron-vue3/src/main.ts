import { createApp } from 'vue'
import 'vue3-tiptap-editor/editor.css'
import './style.css'
import { i18n } from './i18n/index.js'
import App from './App.vue'
import router from './router/index.js'

const app = createApp(App)

app.use(router)
app.use(i18n)

app.mount('#app')
