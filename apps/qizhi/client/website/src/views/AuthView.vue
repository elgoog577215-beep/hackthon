<template>
  <div class="auth-view">
    <div class="auth-card">
      <template v-if="isDevServer">
        <p class="hint">开发服务器测试登录</p>
        <p v-if="authError" class="hint hint-err">登录失败，请稍后重试</p>

        <form class="dev-form" @submit.prevent="handleDevServerLogin">
          <label class="field">
            <span class="label">姓名</span>
            <input v-model.trim="devName" class="input" type="text" autocomplete="name" placeholder="请输入姓名" />
          </label>
          <label class="field">
            <span class="label">学工号</span>
            <input v-model.trim="devWorkId" class="input" type="text" autocomplete="username" placeholder="请输入工号" />
          </label>
          <button type="submit" class="submit-btn" :disabled="devSubmitting">
            {{ devSubmitting ? '登录中...' : '登录' }}
          </button>
          <router-link to="/" class="back-link">返回首页</router-link>
        </form>
      </template>

      <template v-else>
        <p v-if="status === 'loading'" class="hint">正在跳转统一身份认证…</p>
        <p v-else class="hint hint-err">
          {{ isFromLogout ? '已退出登录，请点击下方按钮重新登录' : '跳转失败，请稍后重试' }}
        </p>

        <div v-if="status === 'error'" class="auth-actions">
          <button type="button" class="submit-btn" :disabled="oauthSubmitting" @click="handleOAuthRedirect">
            {{ oauthSubmitting ? '跳转中...' : (isFromLogout ? '重新登录' : '重试跳转') }}
          </button>
          <router-link to="/" class="back-link">返回首页</router-link>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { devTestLogin, getAuthAuthorizeUrl } from '../api/zjuAuth'
import { getStoredToken, setStoredToken } from '../api/user'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const authError = ref('')
const oauthSubmitting = ref(false)
const devSubmitting = ref(false)
const status = ref<'loading' | 'error'>('loading')
const devName = ref('')
const devWorkId = ref('')
const isFromLogout = (() => {
  const v = route.query.logged_out
  if (typeof v === 'string') return v === '1' || v.toLowerCase() === 'true'
  if (Array.isArray(v)) {
    const first = v[0]
    return typeof first === 'string' && (first === '1' || first.toLowerCase() === 'true')
  }
  return false
})()

const isDevServer = (() => {
  // Vite 本地开发天然是 DEV；部署到测试服务器时仍可用 ENV=DEV 打开测试登录。
  return import.meta.env.DEV || String(import.meta.env.ENV || '').toUpperCase() === 'DEV'
})()

async function tryUseExistingTokenAndRedirect(): Promise<boolean> {
  const token = getStoredToken()
  if (!token) return false
  const user = await userStore.fetchCurrentUser()
  if (!user) return false
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  await router.replace(redirect)
  return true
}

onMounted(() => {
  // 已有 token 时，优先尝试拉取用户信息并回跳，避免重复进入统一认证
  tryUseExistingTokenAndRedirect().catch(() => {
    // ignore
  })
  // DEV 服务器：展示测试登录表单，不自动跳统一认证
  if (!isDevServer && !isFromLogout) {
    // 进入 /auth 即直接跳统一认证
    handleOAuthRedirect().catch(() => {
      // ignore
    })
  } else if (!isDevServer && isFromLogout) {
    status.value = 'error'
  }
})

async function handleDevServerLogin() {
  authError.value = ''
  devSubmitting.value = true
  try {
    const token = await devTestLogin({ name: devName.value, workId: devWorkId.value })
    setStoredToken(token)
    const user = await userStore.fetchCurrentUser()
    if (user) {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
      await router.replace(redirect)
      return
    }
    throw new Error('获取用户信息失败')
  } catch (err) {
    console.error('[Auth] 测试登录失败', err)
    authError.value = 'failed'
  } finally {
    devSubmitting.value = false
  }
}

async function handleOAuthRedirect() {
  authError.value = ''
  oauthSubmitting.value = true
  try {
    if (import.meta.env.DEV && localStorage.getItem('disable_api') === '1') {
      throw new Error('当前已禁用 API（localStorage.disable_api=1），不会发起统一认证跳转')
    }
    // 若已有有效 token，直接使用并返回来源页
    if (await tryUseExistingTokenAndRedirect()) return

    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    const url = await getAuthAuthorizeUrl()

    try {
      sessionStorage.setItem('oauth_post_login_redirect', redirect)
    } catch {
      // ignore
    }

    window.location.href = url
  } catch (err) {
    console.error('[Auth] 统一身份认证跳转失败', err)
    authError.value = 'failed'
    status.value = 'error'
  } finally {
    oauthSubmitting.value = false
  }
}
</script>

<style scoped>
.auth-view {
  min-height: calc(100vh - 64px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: transparent;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  padding: 40px 36px;
}

.hint {
  margin: 0;
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  text-align: center;
}
.hint-err {
  color: #d32f2f;
}

.auth-actions {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  font-size: 15px;
  font-weight: 600;
  color: #333;
  background: #c5d9ff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s, opacity 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #b0caff;
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.back-link {
  font-size: 14px;
  color: #666;
  text-decoration: none;
  transition: color 0.2s;
}

.back-link:hover {
  color: #1a73e8;
}

.dev-form {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.label {
  font-size: 12px;
  color: #666;
}

.input {
  width: 100%;
  padding: 12px;
  font-size: 14px;
  border: 1px solid #ddd;
  border-radius: 8px;
  outline: none;
}

.input:focus {
  border-color: #9bbcff;
  box-shadow: 0 0 0 3px rgba(155, 188, 255, 0.3);
}
</style>
