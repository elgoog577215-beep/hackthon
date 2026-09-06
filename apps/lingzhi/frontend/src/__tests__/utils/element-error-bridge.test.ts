import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { installElementErrorBridge } from '@/utils/element-error-bridge'
import { publishAppError, subscribeAppErrors, type AppErrorEvent } from '@/utils/app-error'

describe('Element Plus error bridge', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-24T08:00:00Z'))
  })

  afterEach(() => vi.useRealTimers())

  it('把旧式错误消息升级为结构化中文异常', () => {
    const message = { error: vi.fn() }
    const notification = { error: vi.fn() }
    const listener = vi.fn<(event: AppErrorEvent) => void>()
    const unsubscribe = subscribeAppErrors(listener)
    installElementErrorBridge(message, notification)

    vi.setSystemTime(new Date('2026-08-24T08:00:01Z'))
    message.error('课程删除失败')

    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      presentation: expect.objectContaining({
        title: '课程删除失败',
        summary: expect.stringContaining('没有完成'),
        technicalDetail: expect.stringContaining('课程删除失败'),
      }),
    }))
    unsubscribe()
  })

  it('抑制紧随结构化请求错误出现的旧式重复提示', () => {
    const message = { error: vi.fn() }
    const notification = { error: vi.fn() }
    const listener = vi.fn<(event: AppErrorEvent) => void>()
    const unsubscribe = subscribeAppErrors(listener)
    installElementErrorBridge(message, notification)

    publishAppError('服务反馈', { title: '课程读取失败' })
    message.error('加载课程失败')

    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
  })
})
