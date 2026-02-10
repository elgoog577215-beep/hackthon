import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'markdown': ['markdown-it', 'markdown-it-katex', 'katex'],
          'mermaid': ['mermaid'],
          'icons': ['lucide-vue-next']
        }
      }
    },
    chunkSizeWarningLimit: 1000
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/courses': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/generate_course': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/annotations': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/generate_quiz': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/summarize_chat': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ask': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
