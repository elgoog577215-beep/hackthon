import { oauthCallback } from '../api/zjuAuth'
import { setStoredToken } from '../api/user'
import { useUserStore } from '../stores/user'

/** 用授权码换平台 token 并拉取当前用户（与 /auth/callback 页逻辑一致） */
export async function exchangeOAuthCodeForSession(code: string): Promise<void> {
  const token = await oauthCallback({ code })
  setStoredToken(token)
  const userStore = useUserStore()
  await userStore.fetchCurrentUser()
}
