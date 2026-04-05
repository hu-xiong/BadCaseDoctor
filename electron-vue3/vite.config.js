import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: 'localhost', // 只监听本地，不对外暴露
    strictPort: true, // 如果端口被占用则退出
    open: false, // 不自动打开浏览器
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      },
      '/socket.io': {
        target: 'http://127.0.0.1:5000',
        ws: true,
        changeOrigin: true,
        secure: false
      }
    }
  },
  optimizeDeps: {
    include: ['monaco-editor', 'socket.io-client', 'xterm', 'xterm-addon-fit']
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
