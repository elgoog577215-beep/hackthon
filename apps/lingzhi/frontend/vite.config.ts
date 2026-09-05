/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'path'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
const frontendRoot = path.resolve(__dirname)
const localNodeModules = path.resolve(frontendRoot, 'node_modules')
const resolvedNodeModules = fs.existsSync(localNodeModules)
  ? fs.realpathSync(localNodeModules)
  : localNodeModules

// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
    host: '0.0.0.0',
    port: 5173,
    fs: {
      // Git worktrees may share node_modules through a symlink. Allow the
      // resolved dependency root so KaTeX fonts and other static assets still
      // render during local demo recording.
      allow: [frontendRoot, resolvedNodeModules],
    },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/ws': {
        target: apiProxyTarget.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true
      }
    }
  }
})
