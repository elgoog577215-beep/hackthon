import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  // 启智本地后端默认使用 8010，避免与灵知的 8000 端口冲突。
  const proxyTarget = process.env.VITE_PROXY_TARGET || env.VITE_PROXY_TARGET || 'http://127.0.0.1:8010'
  // 某些后端部署会把 API 挂在 /api 前缀下（例如 http://host:8000/api/...）
  // 这时如果把 /api 重写掉，会导致路径不匹配（常见表现：405/404 且返回 Nginx HTML）
  // 默认行为保持兼容旧后端：开发代理会去掉 /api 前缀；需要保留时把该值设为 0/false
  const shouldRewriteApiPrefix = !/^(0|false|no)$/i.test(String(env.VITE_PROXY_REWRITE_API_PREFIX || '1'))

  return {
    envDir: __dirname,
    envPrefix: ['VITE_', 'ENV'],
    plugins: [
      vue(),
      //vueDevTools(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    // 开发时把 /api 代理到远程后端，避免跨域 CORS；并显式转发 Authorization 避免 401
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          /** 慢网/VPN 下适当拉长，避免误判为失败（无法解决「目标主机完全不可达」的 ETIMEDOUT） */
          timeout: 120_000,
          proxyTimeout: 120_000,
          rewrite: (path) => (shouldRewriteApiPrefix ? path.replace(/^\/api/, '') : path),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq, req: { headers?: { authorization?: string } }) => {
              const auth = req.headers?.authorization
              if (auth) proxyReq.setHeader('Authorization', auth)
            })
            proxy.on('error', (err) => {
              // eslint-disable-next-line no-console
              console.error(
                '\n[Vite 代理] 无法连到后端:',
                err.message,
                '\n  当前 VITE_PROXY_TARGET =',
                proxyTarget,
                '\n  若出现 ETIMEDOUT：多为校园网/VPN 未连、IP 不可达或后端未监听。',
                '\n  可改 .env.local 为可访问地址，例如本机后端：VITE_PROXY_TARGET=http://127.0.0.1:8000\n',
              )
            })
          },
        },
      },
    },
  }
})
