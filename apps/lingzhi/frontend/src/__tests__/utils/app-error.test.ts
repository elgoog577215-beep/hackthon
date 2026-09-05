import { describe, expect, it, vi } from 'vitest'
import {
  publishAppError,
  subscribeAppErrors,
  toAppError,
  type AppErrorEvent,
} from '@/utils/app-error'

function axiosError(overrides: Record<string, unknown> = {}) {
  return {
    isAxiosError: true,
    message: 'Request failed',
    config: { method: 'patch', url: '/api/teacher/courses/course-1/lessons/lesson-1/plan/draft' },
    response: {
      status: 409,
      headers: { 'x-request-id': 'req_browser_1234' },
      data: {
        detail: {
          code: 'revision_conflict',
          message: 'revision changed on server',
        },
      },
    },
    ...overrides,
  }
}

describe('application error presentation', () => {
  it('提供预设中文名、归纳原因和可追踪技术详情', () => {
    const result = toAppError(axiosError(), { title: '教案保存失败' })

    expect(result.title).toBe('教案保存失败')
    expect(result.summary).toContain('重新载入最新版本')
    expect(result.technicalDetail).toContain('错误码: revision_conflict')
    expect(result.technicalDetail).toContain('请求编号: req_browser_1234')
    expect(result.technicalDetail).toContain('HTTP 状态: 409')
    expect(result.technicalDetail).toContain('PATCH /api/teacher/courses/course-1/lessons/lesson-1/plan/draft')
    expect(result.technicalDetail).toContain('revision changed on server')
  })

  it('按接口域和方法为未知错误生成稳定中文名', () => {
    const result = toAppError(axiosError({
      response: { status: 418, headers: {}, data: {} },
    }))

    expect(result.title).toBe('教案保存失败')
    expect(result.summary).not.toBe('Request failed')
  })

  it('批量教案和讲义接口不会被误报为课程生成', () => {
    const lessonPlan = toAppError(axiosError({
      config: { method: 'post', url: '/api/teacher/courses/course-1/lesson-plans/generate-all' },
      response: { status: 500, headers: {}, data: {} },
    }))
    const script = toAppError(axiosError({
      config: { method: 'post', url: '/api/teacher/courses/course-1/lesson-scripts/generate-all' },
      response: { status: 500, headers: {}, data: {} },
    }))

    expect(lessonPlan.title).toBe('教案生成失败')
    expect(script.title).toBe('讲义生成失败')
  })

  it('技术详情会隐藏密钥和服务器绝对路径', () => {
    const result = toAppError(axiosError({
      response: {
        status: 500,
        headers: {},
        data: { detail: 'RuntimeError at /Users/dev/private.py api_key=secret-value Bearer abc.def' },
      },
    }))

    expect(result.technicalDetail).not.toContain('/Users/dev/private.py')
    expect(result.technicalDetail).not.toContain('secret-value')
    expect(result.technicalDetail).not.toContain('abc.def')
    expect(result.technicalDetail).toContain('[hidden]')
  })

  it('将普通网络失败归纳为可恢复原因', () => {
    const result = toAppError({
      isAxiosError: true,
      message: 'Network Error',
      request: {},
      config: { method: 'get', url: '/api/courses/course-1' },
    })

    expect(result.title).toBe('课程读取失败')
    expect(result.summary).toContain('检查网络连接')
    expect(result.code).toBe('network_error')
  })

  it('业务错误码优先于通用 HTTP 冲突状态归因', () => {
    const result = toAppError(axiosError({
      response: {
        status: 409,
        headers: { 'x-request-id': 'req_lesson_1234' },
        data: {
          detail: {
            code: 'lesson_sections_empty',
            message: '当前讲次没有可生成教案的小节。',
          },
        },
      },
    }))

    expect(result.title).toBe('教案生成条件不足')
    expect(result.summary).toContain('补全课程大纲或课次小节')
  })

  it('不会把课程源缺失的 409 误报为内容版本冲突', () => {
    const result = toAppError(axiosError({
      config: { method: 'post', url: '/api/courses/course-1/evolution/course-plans' },
      response: {
        status: 409,
        headers: {},
        data: { detail: {
          code: 'course_change_source_unavailable',
          message: '当前课程尚未形成可分析的大纲或教学资产',
        } },
      },
    }))

    expect(result.title).toBe('课程修改条件不足')
    expect(result.summary).toContain('先完成课程大纲')
    expect(result.title).not.toContain('版本冲突')
  })

  it('发布结构化错误事件供全局错误层消费', () => {
    const listener = vi.fn<(event: AppErrorEvent) => void>()
    const unsubscribe = subscribeAppErrors(listener)

    const result = publishAppError(axiosError(), { title: '教案保存失败' })

    expect(result.title).toBe('教案保存失败')
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      signature: expect.stringContaining('revision_conflict'),
      presentation: expect.objectContaining({ title: '教案保存失败' }),
    }))
    unsubscribe()
  })
})
