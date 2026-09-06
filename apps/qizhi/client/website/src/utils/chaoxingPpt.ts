/**
 * 超星「AI课件」演示入口（临时外链方案）。
 *
 * 说明：本站 JWT 不能作为查询参数传给 mobilelearn.chaoxing.com——对方不会校验、且会出现在
 * 历史记录/Referer 中造成泄露。用户在超星页需使用超星/学校账号登录（与统一身份认证是两套体系，
 * 除非通过校方对接的 CAS 跳转链，见 PptEmbedView 内历史 embed 方案）。
 */
import { getStoredToken } from '../api/user'

export const CHAOXING_PPT_COURSEWARE_URL =
  'http://aiassistant-cx.zju.edu.cn/cassso/tozju?refer=https%3A%2F%2Fmobilelearn.chaoxing.com%2Fpage%2Fppt%2FcoursewareAI%3FserviceId%3Djsfzai' as const

function shouldPassTokenInUrl(): boolean {
  // 演示用开关：只有显式开启才拼接 token（避免生产环境误泄露）
  return String(import.meta.env.VITE_PPT_PASS_TOKEN || '') === '1'
}

export function buildChaoxingPptCoursewareUrl(): string {
  if (!shouldPassTokenInUrl()) return CHAOXING_PPT_COURSEWARE_URL
  const token = getStoredToken()
  if (!token) return CHAOXING_PPT_COURSEWARE_URL
  const sep = CHAOXING_PPT_COURSEWARE_URL.includes('?') ? '&' : '?'
  // 注意：仅为“看起来传了 token”的演示效果，目标站点大概率不会使用该参数进行登录校验。
  return `${CHAOXING_PPT_COURSEWARE_URL}${sep}qzwj_token=${encodeURIComponent(token)}`
}

export function openChaoxingPptCoursewareDemo(): void {
  window.open(buildChaoxingPptCoursewareUrl(), '_blank', 'noopener,noreferrer')
}
