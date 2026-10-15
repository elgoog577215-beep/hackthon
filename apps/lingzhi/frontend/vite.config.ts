/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'path'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
const frontendRoot = path.resolve(__dirname)
const localNodeModules = path.resolve(frontendRoot, 'node_modules')
const resolvedNodeModules = fs.existsSync(localNodeModules)
  ? fs.realpathSync(localNodeModules)
  : localNodeModules

// https://vite.dev/config/
export default defineConfig(({ command, isPreview }) => ({
  base: process.env.VITE_BASE_PATH || '/',
  // Worktrees can share node_modules, and separate dev servers can optimize
  // different dependency sets. Never let one replace another live server's
  // hashed chunks. Keep HMR restarts in this process on the same cache.
  cacheDir: command === 'serve' && !isPreview
    ? path.join(localNodeModules, '.vite-servers',
      createHash('sha256').update(frontendRoot).digest('hex').slice(0, 12),
      String(process.pid))
    : undefined,
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
}))
