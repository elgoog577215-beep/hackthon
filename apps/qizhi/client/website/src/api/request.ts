/**
 * API 请求配置
 */

import {
  AUTH_TOKEN_KEY,
  AUTH_TOKEN_SET_AT_KEY,
  buildAuthorizationHeader,
} from './authToken'

// 优先使用 .env.development / .env.local 中的 VITE_API_BASE_URL
// 开发推荐 /api（同源，由 Vite 代理到 VITE_PROXY_TARGET）；空串表示生产同源 /api
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

/**
 * 拼接 API 完整路径：避免 base 已以 `/api` 结尾时 path 再以 `/api/` 开头变成 `/api/api/...`；
 * base 为空使用前缀 `/api` 时，若 path 误带 `/api/` 前缀同样去重。
 */
export function buildApiFullUrl(url: string): string {
  const prefix = API_BASE_URL === '' ? '/api' : ''
  let pathPart = url.startsWith('/') ? url : `/${url}`
  const baseTrim = API_BASE_URL.replace(/\/+$/, '')
  if (/\/api$/i.test(baseTrim) && pathPart.toLowerCase().startsWith('/api/')) {
    pathPart = pathPart.slice(4)
  }
  if (API_BASE_URL === '' && prefix === '/api' && pathPart.toLowerCase().startsWith('/api/')) {
    pathPart = pathPart.slice(4)
  }
  return `${API_BASE_URL}${prefix}${pathPart}`
}

function isApiDisabled(): boolean {
  // 线下排查开关：localStorage.disable_api=1 时不发出任何网络请求
  // 目的：验证“页面自身无跳转逻辑”，避免因接口返回（如 302/Location）导致外站跳转
  if (!import.meta.env.DEV) return false
  try {
    return localStorage.getItem('disable_api') === '1'
  } catch {
    return false
  }
}

/** 鉴权失败时清除本地 token 并派发事件，由 main.ts 监听并跳转登录页 */
function clearTokenAndRedirectToLogin() {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
  } catch {
    //
  }
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
}

function isAuthErrorMessage(message: string): boolean {
  const m = String(message)
  return (
    /请先登录|无效的\s*token|token\s*无效|未登录|登录已过期|未提供认证令牌|认证令牌|expired|unauthorized|not authenticated/i.test(
      m,
    )
  )
}

function requireAuthorizationHeader(skipAuth: boolean): string {
  if (skipAuth) return ''
  const authorization = buildAuthorizationHeader()
  if (!authorization) {
    throw new Error('请先登录')
  }
  return authorization
}

type RequestOptions = RequestInit & { skipAuth?: boolean; suppressAuthRedirect?: boolean }

type UploadProgressHandler = (percentage: number) => void

// 简单的 fetch 封装（带登录 token 时自动附加 Authorization）
async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  if (isApiDisabled()) {
    throw new Error('已启用本地调试模式：API 调用已禁用（localStorage.disable_api=1）')
  }
  const { skipAuth, suppressAuthRedirect, ...restOptions } = options
  const skipAuthorization = skipAuth === true

  const fullUrl = buildApiFullUrl(url)

  const defaultHeaders: HeadersInit = {
    'Content-Type': 'application/json',
  }
  if (!skipAuthorization) {
    ;(defaultHeaders as Record<string, string>)['Authorization'] =
      requireAuthorizationHeader(false)
  }

  const config: RequestInit = {
    ...restOptions,
    headers: {
      ...defaultHeaders,
      ...restOptions.headers,
    },
  }
  // FormData 时由浏览器自动设置 Content-Type（含 boundary），不要覆盖为 application/json
  if (options.body instanceof FormData && (config.headers as Record<string, string>)['Content-Type']) {
    delete (config.headers as Record<string, string>)['Content-Type']
  }

  try {
    const response = await fetch(fullUrl, config)
    const text = await response.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        // 非 JSON（如 HTML 错误页），保持 null
      }
    }

    // fetch 成功但 body 为空或非 JSON 时，data 为 null；避免调用方访问 .success 报错
    if (response.ok && data == null) {
      throw new Error('服务器返回空响应，请检查后端服务状态')
    }

    if (!response.ok) {
      const bodyStr = typeof config.body === 'string' ? config.body : '(无)'
      // 5xx 时输出摘要，便于排查
      if (response.status >= 500) {
        const summary = [
          '---------- 后端 5xx 错误摘要（调试用） ----------',
          `接口: ${config.method || 'GET'} ${fullUrl}`,
          `状态码: ${response.status}`,
          `请求体: ${bodyStr}`,
          `响应内容片段: ${text.slice(0, 500)}`,
          '------------------------------------------------------',
        ].join('\n')
        console.error(summary)
      }
      let message = `HTTP error! status: ${response.status}`
      if (data && typeof data === 'object') {
        const body = data as { error?: string; detail?: string | { msg?: string }[] }
        if (body.error && typeof body.error === 'string') {
          message = body.error
        } else if (body.detail) {
          if (typeof body.detail === 'string') {
            message = body.detail
          } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
            message = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ') || message
          }
        }
      } else if (response.status === 500 && /Internal Server Error/i.test(text)) {
        message = '服务器内部错误(500)，请检查服务器日志（常见原因：鉴权失败、数据库异常等）'
      }
      if (import.meta.env.DEV && !data && text) {
        console.warn('[API] 服务器返回非 JSON，响应片段:', text.slice(0, 500))
      }
      if (response.status === 401 || isAuthErrorMessage(message)) {
        message = '请先登录'
        if (suppressAuthRedirect === true) {
          try {
            localStorage.removeItem(AUTH_TOKEN_KEY)
            localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
          } catch {
            // ignore
          }
        } else {
          clearTokenAndRedirectToLogin()
        }
      }
      throw new Error(message)
    }

    // 后端返回 200 但 success: false 且错误为鉴权相关（如「无效的 token」）时，清除 token 并跳转登录
    if (data && typeof data === 'object') {
      const body = data as { success?: boolean; error?: string }
      if (body.success === false && body.error && isAuthErrorMessage(body.error)) {
        if (suppressAuthRedirect === true) {
          try {
            localStorage.removeItem(AUTH_TOKEN_KEY)
            localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
          } catch {
            // ignore
          }
        } else {
          clearTokenAndRedirectToLogin()
        }
        throw new Error('请先登录')
      }
    }

    return data as T
  } catch (error) {
    // 主动中断（AbortController.abort）不是异常，原样抛出，避免污染控制台
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    console.error('API request error:', error)
    // 处理网络连接错误
    if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
      const isConnectionRefused = error.message.includes('ERR_CONNECTION_REFUSED') ||
                                  error.message.includes('fetch failed')
      if (isConnectionRefused) {
        throw new Error('无法连接到后端服务器，请检查：1) 后端服务是否已启动；2) 代理配置是否正确（.env.local 中的 VITE_PROXY_TARGET）')
      }
      throw new Error('网络请求失败，请检查网络连接或后端服务状态')
    }
    throw error
  }
}

// GET 请求（opts.skipAuth：不附加本地 Bearer，用于 OAuth code 换 token 等场景）
export function get<T>(
  url: string,
  params?: Record<string, any>,
  opts?: { skipAuth?: boolean; suppressAuthRedirect?: boolean },
): Promise<T> {
  let queryString = ''
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        searchParams.append(key, String(value))
      }
    })
    queryString = searchParams.toString()
    if (queryString) {
      url += `?${queryString}`
    }
  }

  return request<T>(url, {
    method: 'GET',
    skipAuth: opts?.skipAuth === true,
    suppressAuthRedirect: opts?.suppressAuthRedirect === true,
  })
}

// DELETE 请求
export function del<T>(url: string, params?: Record<string, any>): Promise<T> {
  let queryString = ''
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        searchParams.append(key, String(value))
      }
    })
    queryString = searchParams.toString()
    if (queryString) {
      url += `?${queryString}`
    }
  }

  return request<T>(url, {
    method: 'DELETE',
  })
}

// POST 请求（JSON）
export function post<T>(
  url: string,
  data?: any,
  opts?: { skipAuth?: boolean; suppressAuthRedirect?: boolean; signal?: AbortSignal },
): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
    skipAuth: opts?.skipAuth === true,
    suppressAuthRedirect: opts?.suppressAuthRedirect === true,
    signal: opts?.signal,
  })
}

// PATCH 请求（JSON）
export function patch<T>(
  url: string,
  data?: any,
  opts?: { skipAuth?: boolean; suppressAuthRedirect?: boolean },
): Promise<T> {
  return request<T>(url, {
    method: 'PATCH',
    body: data ? JSON.stringify(data) : undefined,
    skipAuth: opts?.skipAuth === true,
    suppressAuthRedirect: opts?.suppressAuthRedirect === true,
  })
}

/**
 * POST 请求并返回原始 Response（不读取 body），用于流式响应
 * 调用方需自行读取 response.body（ReadableStream）
 */
export function postStream(url: string, data?: unknown): Promise<Response> {
  const fullUrl = buildApiFullUrl(url)
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    Authorization: requireAuthorizationHeader(false),
  }
  return fetch(fullUrl, {
    method: 'POST',
    headers,
    body: data ? JSON.stringify(data) : undefined,
  })
}

// POST 请求（FormData，用于文件上传）
export function postFormData<T>(
  url: string,
  formData: FormData,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  return postFormDataWithProgress<T>(url, formData, undefined, opts?.signal)
}

export async function postFormDataWithProgress<T>(
  url: string,
  formData: FormData,
  onUploadProgress?: UploadProgressHandler,
  signal?: AbortSignal,
): Promise<T> {
  if (isApiDisabled()) {
    throw new Error('已启用本地调试模式：API 调用已禁用（localStorage.disable_api=1）')
  }

  const fullUrl = buildApiFullUrl(url)
  const authorization = requireAuthorizationHeader(false)

  // 需要进度时仍用 XHR（fetch 无 upload progress）；否则用 fetch 与 JSON 请求鉴权一致
  if (onUploadProgress) {
    return postFormDataWithXhr<T>(fullUrl, formData, authorization, onUploadProgress, signal)
  }

  const response = await fetch(fullUrl, {
    method: 'POST',
    headers: { Authorization: authorization },
    body: formData,
    mode: 'cors',
    credentials: 'omit',
    signal,
  })

  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    let message = `HTTP error! status: ${response.status}`
    if (data && typeof data === 'object') {
      const body = data as { error?: string; detail?: string | { msg?: string }[] }
      if (body.error && typeof body.error === 'string') message = body.error
      else if (body.detail && typeof body.detail === 'string') message = body.detail
    }
    if (response.status === 401 || isAuthErrorMessage(message)) {
      clearTokenAndRedirectToLogin()
      throw new Error('请先登录')
    }
    throw new Error(message)
  }

  if (data == null) {
    throw new Error('服务器返回空响应，请检查后端服务状态')
  }
  if (data && typeof data === 'object') {
    const body = data as { success?: boolean; error?: string }
    if (body.success === false) {
      const errMsg = body.error || '请求失败'
      if (isAuthErrorMessage(errMsg)) {
        clearTokenAndRedirectToLogin()
        throw new Error('请先登录')
      }
      throw new Error(errMsg)
    }
  }
  return data as T
}

function postFormDataWithXhr<T>(
  fullUrl: string,
  formData: FormData,
  authorization: string,
  onUploadProgress: UploadProgressHandler,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }

    const xhr = new XMLHttpRequest()
    xhr.open('POST', fullUrl, true)
    xhr.setRequestHeader('Authorization', authorization)

    const onAbort = () => xhr.abort()
    if (signal) signal.addEventListener('abort', onAbort)
    const cleanup = () => {
      if (signal) signal.removeEventListener('abort', onAbort)
    }

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percentage = Math.min(100, Math.max(0, Math.round((event.loaded / event.total) * 100)))
      onUploadProgress(percentage)
    }

    xhr.onabort = () => {
      cleanup()
      reject(new DOMException('Aborted', 'AbortError'))
    }

    xhr.onerror = () => {
      cleanup()
      reject(new Error('网络请求失败，请检查网络连接或后端服务状态'))
    }

    xhr.onload = () => {
      cleanup()
      const text = xhr.responseText || ''
      let data: unknown = null
      if (text) {
        try {
          data = JSON.parse(text)
        } catch {
          data = null
        }
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        if (data == null) {
          reject(new Error('服务器返回空响应，请检查后端服务状态'))
          return
        }
        if (data && typeof data === 'object') {
          const body = data as { success?: boolean; error?: string }
          if (body.success === false) {
            const errMsg = body.error || '请求失败'
            if (isAuthErrorMessage(errMsg)) {
              clearTokenAndRedirectToLogin()
              reject(new Error('请先登录'))
              return
            }
            reject(new Error(errMsg))
            return
          }
        }
        resolve(data as T)
        return
      }

      let message = `HTTP error! status: ${xhr.status}`
      if (data && typeof data === 'object') {
        const body = data as { error?: string; detail?: string | { msg?: string }[] }
        if (body.error && typeof body.error === 'string') {
          message = body.error
        } else if (body.detail) {
          if (typeof body.detail === 'string') {
            message = body.detail
          } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
            message = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ') || message
          }
        }
      }

      if (xhr.status === 401 || isAuthErrorMessage(message)) {
        message = '请先登录'
        clearTokenAndRedirectToLogin()
      }

      reject(new Error(message))
    }

    xhr.send(formData)
  })
}

/** POST 请求（application/x-www-form-urlencoded），用于后端 Form 参数校验 */
export function postFormUrlEncoded<T>(
  url: string,
  data: Record<string, string | number>,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const body = new URLSearchParams()
  Object.entries(data).forEach(([key, value]) => body.append(key, String(value)))
  return request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
    signal: opts?.signal,
  })
}

/**
 * GET 请求并返回 Blob（用于文件下载，不解析 JSON；带登录 token 时自动附加 Authorization）
 */
export async function getBlob(url: string, params?: Record<string, string>): Promise<Blob> {
  let fullUrl = buildApiFullUrl(url)
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        searchParams.append(key, String(value))
      }
    })
    const queryString = searchParams.toString()
    if (queryString) fullUrl += `?${queryString}`
  }
  const headers: HeadersInit = {
    Authorization: requireAuthorizationHeader(false),
  }
  const response = await fetch(fullUrl, { method: 'GET', headers })
  if (!response.ok) {
    const text = await response.text()
    let message = `HTTP error! status: ${response.status}`
    try {
      const data = JSON.parse(text)
      if (data?.error) message = data.error
      else if (data?.detail) message = typeof data.detail === 'string' ? data.detail : String(data.detail)
    } catch {
      if (text) message = text.slice(0, 200)
    }
    if (response.status === 401 || /not authenticated/i.test(String(message))) {
      message = '请先登录'
    }
    throw new Error(message)
  }
  return response.blob()
}
