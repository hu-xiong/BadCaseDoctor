import http from 'node:http'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/** 开发代理复用 TCP（Keep-Alive），避免每次 /api 请求重新握手导致编辑页 300–600ms/次 */
const devProxyAgent = new http.Agent({
  keepAlive: true,
  keepAliveMsecs: 30_000,
  maxSockets: 64
})

const devApiProxy = {
  target: 'http://127.0.0.1:5000',
  changeOrigin: true,
  secure: false,
  agent: devProxyAgent
}

// https://vite.dev/config/
export default defineConfig({
  // Electron file:// 加载需要相对资源路径
  base: './',
  plugins: [vue()],
  server: {
    port: 5173,
    // 显式绑 IPv4：Windows 上 host:localhost 常只听 [::1]，CDP/Chrome 走 127.0.0.1 会连不上
    host: '127.0.0.1',
    strictPort: true,
    open: false,
    proxy: {
      '/api': devApiProxy,
      '/upload': devApiProxy,
      '/__badcase_local_go': {
        target: 'http://127.0.0.1:8794',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/__badcase_local_go/, '') || '/'
      }
    }
  },
  optimizeDeps: {
    include: ['monaco-editor'],
    exclude: [
      '@xterm/xterm',
      '@xterm/addon-fit',
      '@xterm/addon-webgl',
      '@xterm/addon-unicode11',
      '@xterm/addon-clipboard'
    ]
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          monaco: ['monaco-editor']
        }
      }
    }
  }
})
