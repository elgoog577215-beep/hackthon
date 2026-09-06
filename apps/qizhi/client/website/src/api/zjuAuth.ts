import { get, post } from './request'
import type {
  ApiResponse,
  OAuthAuthUrlApiResponse,
  OAuthCallbackApiResponse,
  OAuthCallbackRequest,
  OAuthDevTestLoginApiResponse,
  OAuthDevTestLoginRequest,
  OAuthTestLoginApiResponse,
  OAuthLogoutApiResponse,
} from './types'

export type { OAuthCallbackRequest } from './types'

/**
 * 统一身份认证（浙大 IdP）
 *
 * - GET /auth/url → 跳转 data 中的授权地址
 * - GET /auth/callback?code= → data 为 JWT
 * - POST /auth/logout → 退出（需 Bearer）
 */

/** 从 /auth/url 多种回参形态中取出授权页地址（兼容 data 字符串或 data.redirect_url 等） */
function extractAuthorizeUrlFromAuthUrlResponse(resp: Record<string, unknown>): string | null {
  const data = resp.data
  if (typeof data === 'string' && data.trim()) return data.trim()
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const o = data as Record<string, unknown>
    for (const key of ['redirect_url', 'url', 'authorize_url', 'authorizeUrl']) {
      const v = o[key]
      if (typeof v === 'string' && v.trim()) return v.trim()
    }
  }
  for (const key of ['redirect_url', 'url']) {
    const v = resp[key]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return null
}

/**
 * 【获取 OAuth 授权地址】GET /auth/url（无参数）
 * 响应 ApiResponse[str]，data 为浙大 OAuth 登录授权地址。
 */
export async function getAuthAuthorizeUrl(): Promise<string> {
  // 未登录也要能拿授权地址；不可走 requireAuthorizationHeader（否则会抛「请先登录」）
  const resp = (await get<OAuthAuthUrlApiResponse>('/auth/url', undefined, { skipAuth: true })) as unknown as Record<
    string,
    unknown
  >
  if (!resp || typeof resp !== 'object') {
    throw new Error('获取统一身份认证地址失败：服务返回非 JSON（请检查代理/后端地址是否正确）')
  }
  if (resp.success === false) throw new Error(String(resp.error || '获取统一身份认证地址失败'))
  const url = extractAuthorizeUrlFromAuthUrlResponse(resp)
  if (!url) {
    throw new Error('获取统一身份认证地址失败：未解析到授权 URL（请确认回参为 data 字符串或含 redirect_url）')
  }
  if (import.meta.env.DEV && typeof console !== 'undefined') {
    try {
      const u = new URL(url)
      const host = u.hostname
      if (!/zjuam\.zju\.edu\.cn$/i.test(host) && !/zju\.edu\.cn$/i.test(host)) {
        console.warn('[OAuth] 授权地址不含 zjuam.zju.edu.cn，若未出现浙大登录页请核对后端拼链')
      }
    } catch {
      // ignore
    }
  }
  return url
}

/**
 * 【处理 OAuth 回调并签发 Token】GET /auth/callback?code=...
 * 请求参数 Request：{ code }；响应 ApiResponse[str]，data 为系统访问 token。
 * 使用 skipAuth：换 token 前若带上错误 Bearer 可能导致无法签发新 token。
 */
export async function oauthCallback(params: OAuthCallbackRequest): Promise<string> {
  const resp = await get<OAuthCallbackApiResponse>(
    '/auth/callback',
    {
      code: params.code,
    },
    { skipAuth: true },
  )
  if (!resp || typeof resp !== 'object') {
    throw new Error('统一身份认证登录失败：服务返回非 JSON（请检查代理/后端地址是否正确）')
  }
  if (resp.success === false) throw new Error(resp.error || '统一身份认证登录失败')
  const token = typeof resp.data === 'string' ? resp.data.trim() : ''
  if (!token) throw new Error('统一身份认证登录失败：未返回 token')
  return token
}

/**
 * 测试登录（仅开发环境）
 * GET /auth/test-login（无参数）
 * 使用 skipAuth：签发新 token 前不带旧 token，避免后端拒绝
 */
export async function testLogin(): Promise<string> {
  const resp = await get<OAuthTestLoginApiResponse>('/auth/test-login', undefined, { skipAuth: true })
  if (!resp || typeof resp !== 'object') {
    throw new Error('开发登录失败：服务返回非 JSON')
  }
  if (resp.success === false) throw new Error(String(resp.error || '开发登录失败'))
  const token = typeof resp.data === 'string' ? resp.data.trim() : ''
  if (!token) throw new Error('开发登录失败：未返回 token')
  return token
}

/**
 * DEV 服务器测试登录（姓名 + 工号）
 * POST /auth/test-login
 */
export async function devTestLogin(params: { name: string; workId: string }): Promise<string> {
  const body: OAuthDevTestLoginRequest = {
    name: String(params.name || '').trim(),
    zju_id: String(params.workId || '').trim(),
  }
  if (!body.name) throw new Error('请输入姓名')
  if (!body.zju_id) throw new Error('请输入工号')

  const tryParseToken = (resp: ApiResponse<string | null> | unknown, errHint: string): string => {
    if (!resp || typeof resp !== 'object') throw new Error(errHint)
    const r = resp as ApiResponse<string | null>
    if (r.success === false) throw new Error(String(r.error || errHint))
    const token = typeof r.data === 'string' ? r.data.trim() : ''
    if (!token) throw new Error(`${errHint}：未返回 token`)
    return token
  }

  const resp = await post<OAuthDevTestLoginApiResponse>('/auth/test-login', body, { skipAuth: true })
  return tryParseToken(resp, '测试登录失败')
}

/**
 * 【退出登录】POST /auth/logout（无请求参数，需 Authorization: Bearer）
 * 响应 ApiResponse[NoneType]
 */
export async function authLogout(): Promise<void> {
  // 登出时若 token 已失效，后端可能返回 401；这里不应触发全局 auth:unauthorized 自动跳转
  const resp = await post<OAuthLogoutApiResponse>('/auth/logout', undefined, { suppressAuthRedirect: true })
  if (!resp || typeof resp !== 'object') {
    throw new Error('退出登录失败：服务返回非 JSON（请检查代理/后端地址是否正确）')
  }
  if (resp.success === false) throw new Error(resp.error || '退出登录失败')
}
