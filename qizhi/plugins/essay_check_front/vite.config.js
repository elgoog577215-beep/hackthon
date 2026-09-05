import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api/v1': {
        target: process.env.ESSAY_CHECK_PROXY_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
