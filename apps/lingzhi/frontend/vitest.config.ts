import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue() as any],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // 时钟相关断言（如"最后更新 12:17"）走 Intl.DateTimeFormat，不带 timeZone
    // 时用的是运行环境本地时区。产品行为如此是对的——教师应当看到自己的本地
    // 时间——但测试不能因此依赖跑在哪台机器上：同一份代码在 UTC 的服务器上
    // 渲染 04:17、在开发者机器上渲染 12:17，用例就会无故转红。
    // 把测试时区钉死在产品的主要使用地，断言才既确定又有意义。
    env: {
      TZ: 'Asia/Shanghai',
    },
  },
})
