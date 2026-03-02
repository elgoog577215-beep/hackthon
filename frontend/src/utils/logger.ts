type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LoggerConfig {
  enabled: boolean
  level: LogLevel
  showTimestamp: boolean
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3
}

class Logger {
  private config: LoggerConfig

  constructor() {
    this.config = {
      enabled: import.meta.env.DEV,
      level: import.meta.env.DEV ? 'debug' : 'error',
      showTimestamp: true
    }
  }

  private shouldLog(level: LogLevel): boolean {
    if (!this.config.enabled) return false
    return LOG_LEVELS[level] >= LOG_LEVELS[this.config.level]
  }

  private formatMessage(level: LogLevel, ...args: unknown[]): unknown[] {
    if (!this.config.showTimestamp) return args
    const timePart = new Date().toISOString().split('T')[1]
    const timestamp = timePart ? timePart.slice(0, 12) : '00:00:00.000'
    return [`[${timestamp}] [${level.toUpperCase()}]`, ...args]
  }

  debug(...args: unknown[]): void {
    if (this.shouldLog('debug')) {
      console.log(...this.formatMessage('debug', ...args))
    }
  }

  info(...args: unknown[]): void {
    if (this.shouldLog('info')) {
      console.info(...this.formatMessage('info', ...args))
    }
  }

  warn(...args: unknown[]): void {
    if (this.shouldLog('warn')) {
      console.warn(...this.formatMessage('warn', ...args))
    }
  }

  error(...args: unknown[]): void {
    if (this.shouldLog('error')) {
      console.error(...this.formatMessage('error', ...args))
    }
  }

  group(label: string): void {
    if (this.config.enabled) {
      console.group(label)
    }
  }

  groupEnd(): void {
    if (this.config.enabled) {
      console.groupEnd()
    }
  }
}

export const logger = new Logger()

export default logger
