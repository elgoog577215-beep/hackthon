<template>
  <div class="zju-callback">
    <div class="card">
      <h2 class="title">统一身份认证登录</h2>
      <p class="desc" v-if="status === 'loading'">正在完成登录，请稍候...</p>
      <p class="desc ok" v-else-if="status === 'success'">登录成功，正在跳转...</p>
      <p class="desc err" v-else>登录失败：{{ errorMsg }}</p>
      <div v-if="status === 'error'" class="actions">
        <router-link class="link" to="/auth">返回登录页</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { exchangeOAuthCodeForSession } from '../composables/useOAuthSession'
import { extractOAuthCodeFromRoute } from '../utils/oauthQuery'

const route = useRoute()
const router = useRouter()

const status = ref<'loading' | 'success' | 'error'>('loading')
const errorMsg = ref('')

function readSessionItem(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}
function removeSessionItem(key: string) {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // ignore
  }
}

onMounted(async () => {
  const oauthErr = typeof route.query.error === 'string' ? route.query.error : ''
  const oauthErrDesc =
    typeof route.query.error_description === 'string' ? route.query.error_description : ''
  if (oauthErr) {
    status.value = 'error'
    errorMsg.value = oauthErrDesc ? `${oauthErr}：${oauthErrDesc}` : oauthErr
    return
  }

  const code = extractOAuthCodeFromRoute(route)

  const redirect =
    readSessionItem('oauth_post_login_redirect') ||
    readSessionItem('zju_post_login_redirect') ||
    '/'

  if (!code) {
    status.value = 'error'
    errorMsg.value = '缺少 code（回调参数不完整）'
    return
  }

  try {
    await exchangeOAuthCodeForSession(code)

    status.value = 'success'
    removeSessionItem('oauth_post_login_redirect')
    removeSessionItem('zju_post_login_redirect')
    router.replace(redirect)
  } catch (err) {
    status.value = 'error'
    errorMsg.value = err instanceof Error ? err.message : '统一身份认证登录失败'
  }
})
</script>

<style scoped>
.zju-callback {
  min-height: calc(100vh - 64px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.card {
  width: 100%;
  max-width: 520px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  padding: 28px 24px;
}
.title {
  margin: 0 0 10px 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}
.desc {
  margin: 0;
  font-size: 14px;
  color: #666;
  line-height: 1.6;
}
.ok {
  color: #2e7d32;
}
.err {
  color: #d32f2f;
}
.actions {
  margin-top: 14px;
}
.link {
  font-size: 14px;
  color: #1a73e8;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
</style>
