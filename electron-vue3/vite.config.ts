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
  plugins: [vue()],
  server: {
    port: 5173,
    host: 'localhost',
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
