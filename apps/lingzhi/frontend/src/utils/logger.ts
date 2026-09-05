/**
 * 结构化日志工具
 * 
 * 开发环境输出到 console，生产环境静默。
 * 替代散布在代码中的 console.log/warn/error。
 */

const isDev = import.meta.env.DEV

export const logger = {
  info(...args: unknown[]) {
    if (isDev) console.log(...args)
  },
  warn(...args: unknown[]) {
    if (isDev) console.warn(...args)
  },
  error(...args: unknown[]) {
    // 生产环境也输出 error，便于排查
    console.error(...args)
  },
  debug(...args: unknown[]) {
    if (isDev) console.debug(...args)
  },
}

export default logger
