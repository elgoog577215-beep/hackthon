<template>
  <nav class="navbar" :class="{ 'is-home': route.path === '/' }">
    <div class="navbar-left">
      <!-- 移动端汉堡按钮：仅在 ≤640px 显示，首页也展示（让访客能进入功能页） -->
      <button
        type="button"
        class="nav-hamburger"
        aria-label="打开导航菜单"
        :aria-expanded="showMobileMenu"
        @click.stop="showMobileMenu = !showMobileMenu"
      >
        <span class="hamburger-bar" :class="{ 'is-open': showMobileMenu }"></span>
        <span class="hamburger-bar" :class="{ 'is-open': showMobileMenu }"></span>
        <span class="hamburger-bar" :class="{ 'is-open': showMobileMenu }"></span>
      </button>

      <!-- 非首页：显示 MentorAI logo；首页：保持空占位以维持居中 -->
      <router-link
        v-if="route.path !== '/'"
        to="/"
        class="brand"
        aria-label="返回首页"
      >
        <span class="trial-badge">内测版</span>
        <img class="brand-logo" :src="mentorLogoUrl" alt="MentorAI" />
        <img class="brand-logo-zju" :src="zjuLogoUrl" alt="浙江大学" />
      </router-link>
    </div>

    <!-- 导航菜单（居中，桌面端） -->
    <div class="nav-menu" aria-label="主导航">
      <router-link
        v-for="item in visibleNav"
        :key="item.to"
        :to="item.to"
        class="nav-item"
        :class="{ active: item.isActive(route.path) }"
      >
        {{ item.label }}
      </router-link>
    </div>

    <!-- 移动端下拉菜单（≤640px 下汉堡按钮展开） -->
    <div
      v-show="showMobileMenu"
      class="mobile-nav-overlay"
      role="dialog"
      aria-modal="false"
      @click.self="showMobileMenu = false"
    >
      <div class="mobile-nav-panel" ref="mobileMenuRef">
        <router-link
          v-for="item in visibleNav"
          :key="item.to"
          :to="item.to"
          class="mobile-nav-item"
          :class="{ active: item.isActive(route.path) }"
          @click="showMobileMenu = false"
        >{{ item.label }}</router-link>
      </div>
    </div>

    <div class="navbar-right">
      <button type="button" class="feedback-entry-btn" aria-label="意见反馈" @click="showFeedbackModal = true">
        <svg class="feedback-entry-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M21 11.5C21 16.7467 16.7467 21 11.5 21C9.93358 21 8.45611 20.6204 7.15397 19.9489L3 21L4.05113 16.846C3.37956 15.5439 3 14.0664 3 12.5C3 7.25329 7.25329 3 12.5 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="feedback-entry-text">意见反馈</span>
      </button>

      <!-- 开发环境：模拟登录按钮（设置 disable_api 后跳转 /auth） -->
      <button
        v-if="isDev"
        type="button"
        class="dev-login-btn"
        @click="handleDevLogin"
        title="开发模式：模拟登录"
      >
        点我模拟登录
      </button>
      <!-- 已登录：用户名 + 下拉退出；未登录：登录/注册 -->
      <template v-if="userStore.isLoggedIn">
        <div class="user-info-wrapper" ref="userMenuRef">
          <button type="button" class="user-info user-info-btn" @click="showUserMenu = !showUserMenu">
            <div class="user-details">
              <div class="user-name">{{ displayName }}</div>
              <div class="user-date">{{ currentDate }}</div>
            </div>
            <div class="user-avatar">
              <div class="avatar-placeholder">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" fill="currentColor"/>
                </svg>
              </div>
            </div>
          </button>
          <div v-show="showUserMenu" class="user-dropdown">
            <button type="button" class="user-dropdown-item" @click="handleLogout">退出登录</button>
          </div>
        </div>
      </template>
      <button v-else type="button" class="user-info user-info-btn" @click="handleLoginRegisterClick">
        <div class="user-avatar">
          <div class="avatar-placeholder">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" fill="currentColor"/>
            </svg>
          </div>
        </div>
        <div class="user-details">
          <div class="user-name">统一身份认证登录</div>
        </div>
      </button>
    </div>

    <FeedbackModal v-model="showFeedbackModal" />
  </nav>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../../stores/user'
import { getStoredToken, setStoredToken } from '../../api/user'
import { getAuthAuthorizeUrl } from '../../api/zjuAuth'
import { post } from '../../api/request'
import FeedbackModal from '../feedback/FeedbackModal.vue'
import mentorLogoUrl from '../../../image_materials/MentorAI_logo.png'
import zjuLogoUrl from '../../../image_materials/ZJU_logo.png'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const isDev = import.meta.env.DEV
const displayName = computed(() => {
  const u = userStore.currentUser
  if (!u) return '用户'
  const n = u.name?.trim()
  if (n) return n
  const legacy = u.username?.trim()
  if (legacy) return legacy
  return '用户'
})
const showUserMenu = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)
const showFeedbackModal = ref(false)
const showMobileMenu = ref(false)
const mobileMenuRef = ref<HTMLElement | null>(null)

// 路由切换时自动关闭移动端下拉
watch(() => route.fullPath, () => {
  showMobileMenu.value = false
})

onMounted(() => {
  // 开发环境可选：localStorage.disable_api=1 时不发起请求（排查跳转等问题）
  try {
    const apiOff = import.meta.env.DEV && localStorage.getItem('disable_api') === '1'
    if (!apiOff && getStoredToken() && !userStore.currentUser) {
      userStore.fetchCurrentUser()
    }
  } catch {
    // ignore
  }
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  showUserMenu.value = false
  document.removeEventListener('click', handleClickOutside)
})

async function handleLogout() {
  showUserMenu.value = false
  await userStore.logout()
  // logout 内部在非本机环境会跳转 CAS 注销并回到首页
  // 本机开发环境：不跳外站，此处回首页即可
  try {
    const h = window.location.hostname
    const isLocal = h === 'localhost' || h === '127.0.0.1'
    if (import.meta.env.DEV && isLocal) {
      router.replace('/')
    }
  } catch {
    // ignore
  }
}

async function handleLoginRegisterClick() {
  if (import.meta.env.DEV) {
    try {
      if (localStorage.getItem('disable_api') === '1') {
        await router.push('/auth')
        return
      }
    } catch {
      // ignore
    }
  }

  // 记录”从哪里来”，回调后回到当前页面
  try {
    sessionStorage.setItem('oauth_post_login_redirect', route.fullPath)
  } catch {
    // ignore
  }

  try {
    const url = await getAuthAuthorizeUrl()
    window.location.href = url
  } catch {
    // 失败则回退到 /auth，让用户手动重试（并可看到错误提示）
    await router.push({ path: '/auth', query: { redirect: route.fullPath } })
  }
}

async function handleDevLogin() {
  try {
    const resp = await post<{ data: string | null; success: boolean; error?: string }>(
      '/auth/test-login?name=' + encodeURIComponent('测试用户') + '&zju_id=' + encodeURIComponent('0010759'),
      undefined,
      { skipAuth: true },
    )
    const token = resp.data?.trim() ?? ''
    if (!token) throw new Error('未返回 token')
    setStoredToken(token)
    await userStore.fetchCurrentUser()
  } catch (err) {
    console.error('[Navbar] 模拟登录失败', err)
  }
}

// 点击外部关闭下拉
function handleClickOutside(e: MouseEvent) {
  if (userMenuRef.value && !userMenuRef.value.contains(e.target as Node)) {
    showUserMenu.value = false
  }
  // 移动端下拉：点击非汉堡按钮且非面板内部时关闭
  if (showMobileMenu.value) {
    const target = e.target as Node | null
    const insidePanel = mobileMenuRef.value?.contains(target as Node)
    const isHamburger = target instanceof Element && target.closest('.nav-hamburger')
    if (!insidePanel && !isHamburger) {
      showMobileMenu.value = false
    }
  }
}
// 获取当前日期
const currentDate = computed(() => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
})

/** 主导航（全员展示；进入各页后的权限由路由 meta / 守卫控制） */
type NavLink = {
  to: string
  label: string
  isActive: (path: string) => boolean
  hidden?: boolean
}

const ALL_NAV: NavLink[] = [
  {
    to: '/my-courses',
    label: '我的课程',
    // 资源工作台（/resource/*）与大纲表单（/outline-form）已并入「我的课程」层级，归属此入口高亮
    isActive: (p) =>
      p === '/my-courses' ||
      p === '/newcourse-form' ||
      p.startsWith('/course/') ||
      p.startsWith('/resource/') ||
      p === '/outline-form',
  },
  {
    to: '/chat',
    label: '智能对话',
    isActive: (p) => p === '/chat',
  },
  {
    to: '/resource-analysis',
    label: '资源分析',
    isActive: (p) => p.startsWith('/resource-analysis'),
  },
]

const visibleNav = computed(() => ALL_NAV.filter((item) => !item.hidden))

</script>

<style scoped>
.navbar {
  background-color: transparent;
  height: 64px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 24px;
  box-shadow: none;
  position: relative;
  /* 提升到比页面内容里出现的所有 z-index（收藏按钮 10、章节按钮 1000 等）
     都高，确保移动端下拉抽屉（z 50 in this SC）盖过页面元素 */
  z-index: var(--z-navbar, 1100);
}

/* 首页需要让导航栏叠在背景图上，而不是显示在白色页面背景上 */
.navbar.is-home {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  /* 隐藏中间四个入口后，仅用两列：左侧占位 + 右侧操作区靠右 */
  grid-template-columns: auto 1fr;
}

.navbar.is-home .nav-menu {
  display: none;
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.brand {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0;
  text-decoration: none;
  padding: 0;
  min-width: 0;
}

.brand-logo {
  width: auto;
  height: 40px;
  object-fit: contain;
  display: block;
  flex-shrink: 0;
}

.brand-logo-zju {
  height: 40px;
  width: auto;
  max-height: 40px;
  object-fit: contain;
  display: block;
  flex-shrink: 0;
  margin-left: 6px;
}

.trial-badge {
  display: inline-flex;
  align-items: center;
  align-self: center;
  margin-right: 4px;
  height: 18px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 600;
  color: #e67e22;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(230, 126, 34, 0.4);
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
  letter-spacing: 0.5px;
  line-height: 1;
}

.nav-menu {
  justify-self: center;
  width: 512px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0;
  padding: 0;
}

.nav-item {
  width: 104px;
  height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: #757575;
  font-size: 16px;
  border-radius: 8px;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.nav-item:hover {
  background-color: rgba(255, 255, 255, 0.3);
}

.nav-item.active {
  background-color: rgba(255, 255, 255, 0.5);
  font-weight: 600;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-self: end;
  justify-content: flex-end;
}

.dev-login-btn {
  box-sizing: border-box;
  height: 40px;
  padding: 0 12px;
  border: 1px dashed #999;
  border-radius: 9999px;
  background-color: #f0f0f0;
  color: #666;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
  white-space: nowrap;
}

.dev-login-btn:hover {
  background-color: #e0e0e0;
  border-color: #666;
  color: #333;
}

.feedback-entry-btn {
  box-sizing: border-box;
  width: 88px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0 10px;
  background-color: #ffffff;
  border: 1px solid #0069b5;
  border-radius: 9999px;
  font-size: 14px;
  font-weight: 400;
  color: #0069b5;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
}

.feedback-entry-btn:hover {
  background-color: rgba(0, 105, 181, 0.06);
}

.feedback-entry-text {
  display: block;
  transform: translateY(1.5px);
}

.divider {
  width: 1px;
  height: 40px;
  background-color: rgba(0, 0, 0, 0.2);
  margin: 0 8px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  border-radius: 8px;
  padding: 4px 8px;
  transition: background-color 0.2s;
}
.user-info:hover {
  background-color: rgba(0, 0, 0, 0.05);
}
.user-info .avatar-placeholder {
  color: #666;
}

.user-info-wrapper {
  position: relative;
}

.user-info-btn {
  border: none;
  background: none;
  font: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  color: inherit;
  border-radius: 8px;
  padding: 4px 8px;
  transition: background-color 0.2s;
}

.user-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  min-width: 120px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  z-index: 100;
}

.user-dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  font-size: 14px;
  color: #333;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.2s;
}

.user-dropdown-item:hover {
  background-color: #f5f5f5;
}

.user-details {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: #757575;
  line-height: 1.4;
}

.user-avatar {
  width: 40px;
  height: 40px;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.6);
  border: 2px solid rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 汉堡按钮（仅移动端展示） */
.nav-hamburger {
  display: none;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 5px;
  width: 40px;
  height: 40px;
  padding: 0;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(0, 63, 137, 0.12);
  border-radius: 10px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.2s;
}
.nav-hamburger:hover {
  background: rgba(255, 255, 255, 0.85);
}
.hamburger-bar {
  display: block;
  width: 18px;
  height: 2px;
  background: #1f2937;
  border-radius: 2px;
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.hamburger-bar.is-open:nth-child(1) {
  transform: translateY(7px) rotate(45deg);
}
.hamburger-bar.is-open:nth-child(2) {
  opacity: 0;
}
.hamburger-bar.is-open:nth-child(3) {
  transform: translateY(-7px) rotate(-45deg);
}

/* 移动端导航下拉面板 */
.mobile-nav-overlay {
  display: none;
  position: fixed;
  inset: 64px 0 0 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.18);
}
.mobile-nav-panel {
  width: 100%;
  background: #ffffff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mobile-nav-item {
  display: block;
  padding: 12px 14px;
  border-radius: 10px;
  text-decoration: none;
  color: #1f2937;
  font-size: 16px;
  font-weight: 500;
  transition: background-color 0.15s;
}
.mobile-nav-item:hover {
  background: rgba(0, 105, 181, 0.06);
}
.mobile-nav-item.active {
  background: rgba(0, 105, 181, 0.1);
  color: #0069b5;
  font-weight: 600;
}

.feedback-entry-icon {
  display: none;
  flex-shrink: 0;
}

/* 响应式设计 */
@media (max-width: 960px) {
  .navbar {
    padding: 0 16px;
  }

  .brand {
    gap: 0;
  }

  .brand-logo {
    width: auto;
    height: 36px;
  }

  .brand-logo-zju {
    height: 36px;
    max-height: 36px;
  }

  .nav-menu {
    width: auto;
    max-width: 440px;
    gap: 2px;
  }

  .nav-item {
    width: auto;
    flex: 1 1 0;
    min-width: 64px;
    font-size: 14px;
  }
}

@media (max-width: 768px) {
  .navbar {
    padding: 0 12px;
  }

  .brand-logo {
    width: auto;
    height: 32px;
  }

  .brand-logo-zju {
    height: 32px;
    max-height: 32px;
  }

  .user-details {
    display: none;
  }
}

/* ≤640px：用汉堡按钮替代中间四个 nav-item */
@media (max-width: 640px) {
  .navbar {
    grid-template-columns: auto 1fr;
    padding: 0 12px;
    height: 56px;
  }
  .navbar.is-home {
    height: 56px;
    grid-template-columns: auto 1fr;
  }
  .nav-hamburger {
    display: inline-flex;
  }
  .nav-menu {
    display: none !important;
  }
  .mobile-nav-overlay {
    display: block;
    inset: 56px 0 0 0;
  }
  .navbar-left {
    gap: 10px;
  }
  .navbar-right {
    gap: 6px;
  }
  .brand-logo {
    width: auto;
    height: 28px;
  }
  .brand-logo-zju {
    display: none;
  }
  .trial-badge {
    margin-right: 0;
    font-size: 8px;
    height: 14px;
    padding: 0 3px;
  }
  .feedback-entry-btn {
    width: 40px;
    height: 40px;
    padding: 0;
    border-radius: 50%;
  }
  .feedback-entry-text {
    display: none;
  }
  .feedback-entry-icon {
    display: block;
  }
  .dev-login-btn {
    display: none;
  }
  .user-info, .user-info-btn {
    padding: 4px;
  }
  .user-avatar {
    width: 36px;
    height: 36px;
  }
}

@media (max-width: 360px) {
  .navbar {
    padding: 0 8px;
  }
  .navbar-right {
    gap: 4px;
  }
  .feedback-entry-btn {
    width: 36px;
    height: 36px;
  }
  .user-avatar {
    width: 32px;
    height: 32px;
  }
}
</style>
