/**
 * 用户相关 API
 * 登录/注册时对密码做前端 SHA-256 哈希后再传后端（后端需按相同方式校验/存储）
 */

import { get, post } from './request'
import type { ApiResponse, UserResponse, UserLoginParams, UserOperationParams } from './types'
import { sha256Hex } from '../utils/crypto'
import { setStoredToken } from './authToken'

export { getStoredToken, setStoredToken } from './authToken'

const API_PREFIX = '/user'

/**
 * 登录 POST /user/login（JSON）
 * @deprecated 产品侧已改为仅 OAuth；保留供特殊调试或与旧后端对接
 */
export async function login(params: UserLoginParams): Promise<string> {
  const passwordHash = await sha256Hex(params.password)
  const response = await post<ApiResponse<string>>(`${API_PREFIX}/login`, {
    username: params.username,
    password: passwordHash,
  })
  if (!response.success) {
    throw new Error(response.error || '登录失败')
  }
  const token = response.data ?? ''
  if (token) setStoredToken(token)
  return token
}

/**
 * 获取当前登录用户（需 Authorization: Bearer）
 * GET /user/current（按最新接口文档）
 */
export async function getCurrentUser(): Promise<UserResponse | null> {
  const response = await get<ApiResponse<UserResponse>>(`${API_PREFIX}/current`)
  if (!response.success) return null
  return response.data ?? null
}

/**
 * 根据 id 查询用户 GET /user/?id=xxx
 */
export async function getUser(id: string): Promise<UserResponse> {
  const response = await get<ApiResponse<UserResponse>>(API_PREFIX, { id })
  if (!response.success || !response.data) {
    throw new Error(response.error || '获取用户信息失败')
  }
  return response.data
}

/**
 * 注册 POST /user/register（无需登录）
 * @deprecated 产品侧已改为仅 OAuth；保留供特殊调试
 */
export async function register(params: UserOperationParams): Promise<string> {
  const body: Record<string, unknown> = {
    operation: params.operation,
  }
  if (params.username != null) body.username = params.username
  if (params.password != null) body.password = await sha256Hex(params.password)
  if (params.phone != null) body.phone = params.phone
  if (params.email != null) body.email = params.email
  if (params.role != null) body.role = params.role

  const response = await post<ApiResponse<string>>(`${API_PREFIX}/register`, body)
  if (!response.success) {
    throw new Error(response.error || '注册失败')
  }
  return response.data ?? ''
}

/**
 * 用户操作 POST /user/operation（需 Authorization: Bearer）
 * 文档回参 data 可为 null
 */
export async function userOperation(params: UserOperationParams): Promise<string | null> {
  const body: Record<string, unknown> = {
    operation: params.operation,
  }
  if (params.id != null) body.id = params.id
  if (params.username != null) body.username = params.username
  if (params.password != null) body.password = await sha256Hex(params.password)
  if (params.phone != null) body.phone = params.phone
  if (params.email != null) body.email = params.email
  if (params.role != null) body.role = params.role

  const response = await post<ApiResponse<string | null>>(`${API_PREFIX}/operation`, body)
  if (!response.success) {
    throw new Error(response.error || '操作失败')
  }
  return response.data ?? null
}
