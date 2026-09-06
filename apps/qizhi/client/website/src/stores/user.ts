import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { getCurrentUser, setStoredToken } from '../api/user'
import { normalizeAppRole, type AppUserRole, type UserResponse } from '../api/types'

export const useUserStore = defineStore('user', () => {
  const currentUser = ref<UserResponse | null>(null)
  const token = ref<string | null>(null)
  // currentUser.role 是唯一真值源；isAdmin / isTeacher / isStudent 全部从它推导，
  // 避免多源同步问题（旧版 isAdmin 是单独 ref，容易和 currentUser.role 不一致）
  const role = computed<AppUserRole>(() => normalizeAppRole(currentUser.value?.role))
  const isAdmin = computed(() => role.value === 'admin')
  const isTeacher = computed(() => role.value === 'teacher')
  const isStudent = computed(() => role.value === 'student')
  // 现有路由守卫还在用 adminChecked 做"是否已拉过用户"的标志，保留兼容
  const adminChecked = ref<boolean>(false)

  const isLoggedIn = computed(() => !!currentUser.value)

  /** 从本地 token 拉取当前用户信息（用于刷新页面或 Navbar 展示；登录仅通过 OAuth 完成） */
  async function fetchCurrentUser(): Promise<UserResponse | null> {
    try {
      const user = await getCurrentUser()
      currentUser.value = user
      adminChecked.value = true
      return user
    } catch {
      currentUser.value = null
      adminChecked.value = true
      setStoredToken(null)
      return null
    }
  }

  /** 兼容旧调用：重新拉取 currentUser（role 自动跟随更新） */
  async function refreshAdminStatus(): Promise<boolean> {
    await fetchCurrentUser()
    return isAdmin.value
  }

  function isLocalhost(): boolean {
    try {
      const h = window.location.hostname
      return h === 'localhost' || h === '127.0.0.1'
    } catch {
      return false
    }
  }

  /**
   * 统一身份认证（CAS）注销：清除 CAS cookie，并回跳到本应用首页。
   *
   * 后端同事要求：前端直接跳转该链接，不再调用后端 /auth/logout。
   * 示例：https://zjuam.zju.edu.cn/cas/logout?service=redirect_url
   */
  function buildCasLogoutUrl(redirectUrl: string): string {
    const base = 'https://zjuam.zju.edu.cn/cas/logout'
    const sep = base.includes('?') ? '&' : '?'
    return `${base}${sep}service=${encodeURIComponent(redirectUrl)}`
  }

  /** 登出：清空 token 与当前用户；非本机环境再跳 CAS 注销清 cookie */
  async function logout(): Promise<void> {
    setStoredToken(null)
    currentUser.value = null
    adminChecked.value = false
    try {
      sessionStorage.removeItem('oauth_post_login_redirect')
      sessionStorage.removeItem('zju_post_login_redirect')
    } catch {
      // ignore
    }

    // 本机开发不跳外站，避免调试时被带走；直接回首页即可
    if (import.meta.env.DEV && isLocalhost()) return

    // 统一认证 cookie 只能通过访问 zjuam 域名的 logout 清除
    try {
      const home = `${window.location.origin}/`
      window.location.href = buildCasLogoutUrl(home)
    } catch {
      // ignore
    }
  }

  return {
    currentUser,
    token,
    role,
    isAdmin,
    isTeacher,
    isStudent,
    adminChecked,
    isLoggedIn,
    fetchCurrentUser,
    refreshAdminStatus,
    logout,
  }
})
