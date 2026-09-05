/**
 * 登录 token 读写（供 request 与 user API 共用，避免循环依赖）
 */

export const AUTH_TOKEN_KEY = 'auth_token'
export const AUTH_TOKEN_SET_AT_KEY = 'auth_token_set_at'
export const AUTH_TOKEN_TTL_MS = 7 * 24 * 60 * 60 * 1000

/** 获取当前存储的 token；空或过期则视为未登录 */
export function getStoredToken(): string | null {
  try {
    const setAtStr = localStorage.getItem(AUTH_TOKEN_SET_AT_KEY)
    if (setAtStr) {
      const setAt = Number(setAtStr)
      if (Number.isFinite(setAt) && Date.now() - setAt > AUTH_TOKEN_TTL_MS) {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
        return null
      }
    }
    let t = localStorage.getItem(AUTH_TOKEN_KEY)
    if (!t || !t.trim()) {
      try {
        t = sessionStorage.getItem(AUTH_TOKEN_KEY)
      } catch {
        // ignore
      }
    }
    return t && t.trim() ? t.trim() : null
  } catch {
    return null
  }
}

/** 存储登录返回的 token */
export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      const trimmed = token.trim()
      if (!trimmed) {
        localStorage.removeItem(AUTH_TOKEN_KEY)
        localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
        return
      }
      localStorage.setItem(AUTH_TOKEN_KEY, trimmed)
      localStorage.setItem(AUTH_TOKEN_SET_AT_KEY, String(Date.now()))
      try {
        sessionStorage.setItem(AUTH_TOKEN_KEY, trimmed)
        sessionStorage.setItem(AUTH_TOKEN_SET_AT_KEY, String(Date.now()))
      } catch {
        // ignore
      }
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      localStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
      try {
        sessionStorage.removeItem(AUTH_TOKEN_KEY)
        sessionStorage.removeItem(AUTH_TOKEN_SET_AT_KEY)
      } catch {
        // ignore
      }
    }
  } catch {
    //
  }
}

/** 构造 Authorization 头；无 token 时返回 null */
export function buildAuthorizationHeader(): string | null {
  const token = getStoredToken()
  if (!token) return null
  return token.startsWith('Bearer ') ? token : `Bearer ${token}`
}
