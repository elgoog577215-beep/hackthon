/**
 * HTTP 工具模块错误处理测试
 * 覆盖 handleHttpError、createRequestConfig、safeRequest 及拦截器行为
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AxiosError, AxiosResponse } from 'axios'

// All vi.mock factories are hoisted – no outer variable references allowed

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() },
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
import { handleHttpError, createRequestConfig, safeRequest } from '@/utils/http'
import { ElMessage } from 'element-plus'

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

describe('handleHttpError – HTTP 状态码错误消息', () => {
  const statusMap: [number, string][] = [
    [400, '请求参数错误'],
    [401, '未授权，请重新登录'],
    [403, '拒绝访问'],
    [404, '请求资源未找到'],
    [408, '请求超时'],
    [409, '资源冲突'],
    [422, '请求格式错误'],
    [429, '请求过于频繁，请稍后再试'],
    [500, '服务器内部错误'],
    [502, '网关错误'],
    [503, '服务暂时不可用'],
    [504, '网关超时'],
  ]

  it.each(statusMap)('状态码 %i → "%s"', (status, expected) => {
    const err = makeAxiosError({ status })
    const msg = handleHttpError(err)
    expect(msg).toBe(expected)
    expect(ElMessage.error).toHaveBeenCalledWith(expected)
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
    expect(msg).toBe('服务端消息')
  })

  it('fallback 到 response.data.error', () => {
    const err = makeAxiosError({ status: 500, data: { error: '错误字段' } })
    const msg = handleHttpError(err)
    expect(msg).toBe('错误字段')
  })
})

describe('handleHttpError – 网络错误', () => {
  it('请求已发出但无响应 → 网络连接失败', () => {
    const err = makeAxiosError({ hasRequest: true })
    const msg = handleHttpError(err)
    expect(msg).toBe('网络连接失败，请检查网络设置')
    expect(ElMessage.error).toHaveBeenCalledWith('网络连接失败，请检查网络设置')
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
  it('showMessage: false 不调用 ElMessage', () => {
    const err = makeAxiosError({ status: 500 })
    handleHttpError(err, { showMessage: false })
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('showMessage: true（默认）调用 ElMessage', () => {
    const err = makeAxiosError({ status: 500 })
    handleHttpError(err)
    expect(ElMessage.error).toHaveBeenCalled()
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
