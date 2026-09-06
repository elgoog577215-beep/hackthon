/**
 * 智能体广场 API（公开接口）
 */

import { get, post } from './request'
import type { ApiResponse, PublicAgentDetail } from './types'

const API_PREFIX = '/agents'

/** GET /agents/public：拉取已上架的智能体卡片列表（首页使用） */
export async function fetchPublicAgents(): Promise<PublicAgentDetail[]> {
  const response = await get<ApiResponse<PublicAgentDetail[]>>(`${API_PREFIX}/public`, undefined, {
    skipAuth: true,
    suppressAuthRedirect: true,
  })
  if (!response.success) {
    throw new Error(response.error || '获取智能体列表失败')
  }
  return response.data ?? []
}

/** POST /agents/visit/{id}：用户点击首页智能体卡片时埋点 */
export async function visitAgent(agentId: string): Promise<void> {
  if (!agentId) return
  try {
    await post<ApiResponse<null>>(`${API_PREFIX}/visit/${encodeURIComponent(agentId)}`, undefined, {
      suppressAuthRedirect: true,
    })
  } catch (e) {
    // 埋点失败不影响跳转
    if (import.meta.env.DEV) console.warn('[agents.visit] failed', e)
  }
}
