/**
 * 统一API客户端
 * 
 * 所有API调用都应该通过这个客户端进行，确保：
 * 1. 统一的错误处理
 * 2. 自动添加认证头
 * 3. 请求重试机制
 * 4. 响应格式标准化
 * 5. 请求取消支持
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export interface APIResponse<T = any> {
  status: 'success' | 'error'
  data: T | null
  message?: string
  error?: {
    code: string
    details?: any
  }
}

export interface PaginatedResponse<T> {
  items: T[]
  pagination: {
    total: number
    page: number
    page_size: number
    total_pages: number
    has_next: boolean
    has_prev: boolean
  }
}

export class APIClient {
  private client: AxiosInstance
  private pendingRequests: Map<string, AbortController> = new Map()

  constructor(baseURL: string = API_BASE) {
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.setupInterceptors()
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('auth_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<APIResponse>) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('auth_token')
          window.dispatchEvent(new CustomEvent('auth:logout'))
        }
        return Promise.reject(error)
      }
    )
  }

  private generateRequestKey(config: AxiosRequestConfig): string {
    return `${config.method}:${config.url}:${JSON.stringify(config.params)}`
  }

  private cancelPendingRequest(key: string) {
    const controller = this.pendingRequests.get(key)
    if (controller) {
      controller.abort()
      this.pendingRequests.delete(key)
    }
  }

  async request<T = any>(config: AxiosRequestConfig): Promise<APIResponse<T>> {
    const key = this.generateRequestKey(config)
    
    this.cancelPendingRequest(key)
    
    const controller = new AbortController()
    this.pendingRequests.set(key, controller)

    try {
      const response: AxiosResponse<APIResponse<T>> = await this.client.request({
        ...config,
        signal: controller.signal,
      })

      this.pendingRequests.delete(key)
      return response.data
    } catch (error) {
      this.pendingRequests.delete(key)
      
      if (axios.isCancel(error)) {
        return {
          status: 'error',
          data: null,
          error: { code: 'REQUEST_CANCELLED', details: '请求已取消' }
        }
      }

      if (axios.isAxiosError(error)) {
        const response = error.response?.data
        
        if (response) {
          return response
        }

        return {
          status: 'error',
          data: null,
          message: this.getErrorMessage(error),
          error: { code: 'NETWORK_ERROR', details: error.message }
        }
      }

      return {
        status: 'error',
        data: null,
        message: '未知错误',
        error: { code: 'UNKNOWN_ERROR' }
      }
    }
  }

  private getErrorMessage(error: AxiosError): string {
    if (error.code === 'ECONNABORTED') {
      return '请求超时，请稍后重试'
    }
    if (!error.response) {
      return '网络连接失败，请检查网络'
    }
    
    const status = error.response.status
    const messages: Record<number, string> = {
      400: '请求参数错误',
      401: '未授权，请重新登录',
      403: '没有权限访问',
      404: '请求的资源不存在',
      500: '服务器内部错误',
      502: '网关错误',
      503: '服务暂时不可用',
      504: '网关超时',
    }
    
    return messages[status] || `请求失败 (${status})`
  }

  async get<T = any>(url: string, params?: Record<string, any>): Promise<APIResponse<T>> {
    return this.request<T>({ method: 'GET', url, params })
  }

  async post<T = any>(url: string, data?: any): Promise<APIResponse<T>> {
    return this.request<T>({ method: 'POST', url, data })
  }

  async put<T = any>(url: string, data?: any): Promise<APIResponse<T>> {
    return this.request<T>({ method: 'PUT', url, data })
  }

  async patch<T = any>(url: string, data?: any): Promise<APIResponse<T>> {
    return this.request<T>({ method: 'PATCH', url, data })
  }

  async delete<T = any>(url: string): Promise<APIResponse<T>> {
    return this.request<T>({ method: 'DELETE', url })
  }

  cancelAll() {
    this.pendingRequests.forEach((controller) => controller.abort())
    this.pendingRequests.clear()
  }
}

export const apiClient = new APIClient()

export default apiClient
