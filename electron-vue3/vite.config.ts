import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: 'localhost',
    strictPort: true,
    open: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      },
      '/upload': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      },
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
