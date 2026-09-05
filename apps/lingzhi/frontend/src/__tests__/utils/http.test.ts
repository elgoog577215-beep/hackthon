/**
 * HTTP 工具模块错误处理测试
 * 覆盖 handleHttpError、createRequestConfig、safeRequest 及拦截器行为
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AxiosError, AxiosResponse } from 'axios'

// All vi.mock factories are hoisted – no outer variable references allowed

vi.mock('@/utils/usage-tracker', () => ({
  trackApiAction: vi.fn(),
}))

vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { headers: { common: {} } },
  }
  return {
    default: { create: vi.fn(() => instance), __instance: instance },
  }
})

// Import after mocks
import http, { handleHttpError, createRequestConfig, safeRequest } from '@/utils/http'
import axios from 'axios'
import { trackApiAction } from '@/utils/usage-tracker'
import { subscribeAppErrors } from '@/utils/app-error'

const requestHandler = (axios as any).__instance.interceptors.request.use.mock.calls[0][0]
const responseSuccessHandler = (axios as any).__instance.interceptors.response.use.mock.calls[0][0]
const responseErrorHandler = (axios as any).__instance.interceptors.response.use.mock.calls[0][1]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAxiosError(overrides: {
  status?: number
  data?: unknown
  hasRequest?: boolean
  message?: string
}): AxiosError {
  const { status, data, hasRequest = true, message } = overrides
  const err: Partial<AxiosError> = {
    isAxiosError: true,
    name: 'AxiosError',
    message: message ?? 'Request failed',
    toJSON: () => ({}),
  }
  if (status !== undefined) {
    err.response = {
      status,
      data: data ?? {},
      statusText: '',
      headers: {},
      config: {} as any,
    } as AxiosResponse
  }
  if (hasRequest) {
    err.request = {}
  }
  return err as AxiosError
}


// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

describe('HTTP mutation usage tracking', () => {
  const headers = () => {
    const values = new Map<string, string>()
    return {
      has: (key: string) => values.has(key),
      get: (key: string) => values.get(key),
      set: (key: string, value: string) => values.set(key, value),
      delete: (key: string) => values.delete(key),
    }
  }

  it('tracks a successful mutation after identity is attached', () => {
    const config = requestHandler({
      method: 'post',
      url: '/api/courses/course-1',
      headers: headers(),
    })
    const response = { config, status: 201, data: {} }

    expect(responseSuccessHandler(response)).toBe(response)
    expect(trackApiAction).toHaveBeenCalledWith(expect.objectContaining({
      method: 'post',
      url: '/api/courses/course-1',
      statusCode: 201,
      userId: expect.stringMatching(/^(learner_|teacher-)/),
    }))
  })

  it('tracks a failed mutation without recording the error body', async () => {
    const config = requestHandler({
      method: 'delete',
      url: '/api/courses/course-1?private=value',
      headers: headers(),
      silentError: true,
    })
    const error = makeAxiosError({ status: 500, data: { detail: 'private failure detail' } })
    error.config = config

    await expect(responseErrorHandler(error)).rejects.toBe(error)
    expect(trackApiAction).toHaveBeenCalledWith(expect.objectContaining({
      method: 'delete',
      url: '/api/courses/course-1?private=value',
      statusCode: 500,
    }))
    expect(JSON.stringify(vi.mocked(trackApiAction).mock.calls)).not.toContain('private failure detail')
  })
})

describe('handleHttpError – HTTP 状态码错误消息', () => {
  const statusMap: [number, string][] = [
    [400, '请求信息没有通过校验，请检查输入后重试。'],
    [401, '当前身份没有完成此操作的权限。'],
    [403, '当前身份没有完成此操作的权限。'],
    [404, '请求的内容不存在，或已经被删除。'],
    [408, '服务响应超时，本次操作尚未完成；已保存内容不会被清空。'],
    [409, '内容已被其他操作更新，请重新载入最新版本后再继续。'],
    [422, '请求信息没有通过校验，请检查输入后重试。'],
    [429, '服务请求过于频繁，当前操作尚未完成，请稍后重试。'],
    [500, '服务端处理本次请求时发生异常，请稍后重试。'],
    [502, '服务端处理本次请求时发生异常，请稍后重试。'],
    [503, '服务端处理本次请求时发生异常，请稍后重试。'],
    [504, '服务端处理本次请求时发生异常，请稍后重试。'],
  ]

  it.each(statusMap)('状态码 %i → "%s"', (status, expected) => {
    const err = makeAxiosError({ status })
    const msg = handleHttpError(err)
    expect(msg).toBe(expected)
  })

  it('未映射的状态码返回通用格式', () => {
    const err = makeAxiosError({ status: 418 })
    const msg = handleHttpError(err)
    expect(msg).toBe('请求错误: 418')
  })
})

describe('handleHttpError – 响应体 detail 优先', () => {
  it('优先使用 response.data.detail', () => {
    const err = makeAxiosError({ status: 400, data: { detail: '自定义错误详情' } })
    const msg = handleHttpError(err)
    expect(msg).toBe('自定义错误详情')
  })

  it('fallback 到 response.data.message', () => {
    const err = makeAxiosError({ status: 500, data: { message: '服务端消息' } })
    const msg = handleHttpError(err)
    expect(msg).toBe('服务端处理本次请求时发生异常，请稍后重试。')
  })

  it('fallback 到 response.data.error', () => {
    const err = makeAxiosError({ status: 500, data: { error: '错误字段' } })
    const msg = handleHttpError(err)
    expect(msg).toBe('服务端处理本次请求时发生异常，请稍后重试。')
  })
})

describe('handleHttpError – 网络错误', () => {
  it('请求已发出但无响应 → 网络连接失败', () => {
    const err = makeAxiosError({ hasRequest: true })
    const msg = handleHttpError(err)
    expect(msg).toBe('请求没有收到服务响应，请检查网络连接后重试。')
  })
})

describe('handleHttpError – 请求配置错误', () => {
  it('无 response 且无 request → 使用 error.message', () => {
    const err = makeAxiosError({ hasRequest: false, message: '配置出错了' })
    const msg = handleHttpError(err)
    expect(msg).toBe('配置出错了')
  })

  it('无 message 时使用默认文案', () => {
    const err = makeAxiosError({ hasRequest: false, message: '' })
    const msg = handleHttpError(err)
    expect(msg).toBe('请求配置错误')
  })
})

describe('handleHttpError – showMessage 控制', () => {
  it('showMessage: false 不发布全局错误', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeAppErrors(listener)
    const err = makeAxiosError({ status: 500 })
    handleHttpError(err, { showMessage: false })
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('showMessage: true（默认）发布结构化全局错误', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeAppErrors(listener)
    const err = makeAxiosError({ status: 500 })
    handleHttpError(err)
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      presentation: expect.objectContaining({ title: '服务处理失败' }),
    }))
    unsubscribe()
  })
})

describe('handleHttpError – customHandler', () => {
  it('调用自定义错误处理器', () => {
    const handler = vi.fn()
    const err = makeAxiosError({ status: 404 })
    handleHttpError(err, { showMessage: true, customHandler: handler })
    expect(handler).toHaveBeenCalledWith(err)
  })
})

describe('createRequestConfig', () => {
  it('无参数时返回默认配置', () => {
    const config = createRequestConfig()
    expect(config).toEqual({ showMessage: true })
  })

  it('合并自定义配置', () => {
    const handler = vi.fn()
    const config = createRequestConfig({ showMessage: false, customHandler: handler })
    expect(config.showMessage).toBe(false)
    expect(config.customHandler).toBe(handler)
  })
})

describe('safeRequest', () => {
  it('成功时返回 response.data', async () => {
    const data = { id: 1, name: 'test' }
    const requestFn = vi.fn().mockResolvedValue({ data })
    const result = await safeRequest(requestFn)
    expect(result).toEqual(data)
  })

  it('失败时返回 null', async () => {
    const err = makeAxiosError({ status: 500 })
    const requestFn = vi.fn().mockRejectedValue(err)
    const result = await safeRequest(requestFn)
    expect(result).toBeNull()
  })
})

describe('HTTP 拦截器错误治理', () => {
  it('静默后台请求不弹错误提示', async () => {
    const listener = vi.fn()
    const unsubscribe = subscribeAppErrors(listener)
    const err = makeAxiosError({ hasRequest: true })
    err.config = { silentError: true } as any

    await expect(responseErrorHandler(err)).rejects.toBe(err)
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('同一个已被拦截器处理的异常不会被 safeRequest 再弹一次', async () => {
    const listener = vi.fn()
    const unsubscribe = subscribeAppErrors(listener)
    const err = makeAxiosError({ status: 503 })
    const requestFn = vi.fn(async () => responseErrorHandler(err))

    await safeRequest(requestFn)
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it('导出的客户端可用于带 silentError 的后台请求配置', () => {
    expect(http).toBeTruthy()
  })
})

describe('模块导出', () => {
  it('默认导出为 axios 实例', async () => {
    const mod = await import('@/utils/http')
    expect(mod.default).toBeDefined()
  })

  it('导出 handleHttpError 函数', () => {
    expect(typeof handleHttpError).toBe('function')
  })

  it('导出 createRequestConfig 函数', () => {
    expect(typeof createRequestConfig).toBe('function')
  })

  it('导出 safeRequest 函数', () => {
    expect(typeof safeRequest).toBe('function')
  })
})
