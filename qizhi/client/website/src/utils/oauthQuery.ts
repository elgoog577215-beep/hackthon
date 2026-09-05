import type { RouteLocationNormalizedLoaded } from 'vue-router'

/** 从路由 query 或浏览器 URL 解析 OAuth 授权码 */
export function extractOAuthCodeFromRoute(route: RouteLocationNormalizedLoaded): string {
  const q = route.query.code
  if (typeof q === 'string' && q.trim()) return q.trim()
  if (Array.isArray(q) && typeof q[0] === 'string' && q[0].trim()) return q[0].trim()
  return extractOAuthCodeFromWindow()
}

/**
 * 从当前页 URL 解析 OAuth 授权码（query 或 hash）
 */
export function extractOAuthCodeFromWindow(): string {
  if (typeof window === 'undefined') return ''

  const search = new URLSearchParams(window.location.search)
  const fromSearch =
    search.get('code') || search.get('auth_code') || search.get('oauth_code')
  if (fromSearch) return fromSearch

  const hash = window.location.hash
  if (hash && hash.length > 1) {
    const h = hash.startsWith('#') ? hash.slice(1) : hash
    const hp = new URLSearchParams(h)
    return hp.get('code') || hp.get('auth_code') || hp.get('oauth_code') || ''
  }

  return ''
}
