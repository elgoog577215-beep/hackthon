/**
 * 运营后台 API
 */

import { get, getBlob, patch, post } from './request'
import type {
  AdminAgentDetail,
  AdminAgentOperationParams,
  AdminAgentReorderParams,
  AdminAgentToggleParams,
  AdminFeedbackDetail,
  AdminUserDetail,
  AgentUsageItem,
  ApiResponse,
  AppUserRole,
  AuditLogDetail,
  AuditLogListParams,
  AuditReportParams,
  DashboardStats,
  FeatureUsageItem,
} from './types'

const API_PREFIX = '/admin'

// ---------- 通用 ----------

/** GET /admin/check：检查当前登录用户是否为管理员（非管理员返回 false 而非 401） */
export async function checkIsAdmin(): Promise<boolean> {
  try {
    const response = await get<ApiResponse<{ is_admin: boolean }>>(`${API_PREFIX}/check`, undefined, {
      suppressAuthRedirect: true,
    })
    return Boolean(response.success && response.data?.is_admin)
  } catch {
    return false
  }
}

// ---------- 智能体广场 ----------

/** GET /admin/agents：后台拉取全量智能体（含未上架） */
export async function fetchAdminAgents(): Promise<AdminAgentDetail[]> {
  const response = await get<ApiResponse<AdminAgentDetail[]>>(`${API_PREFIX}/agents`)
  if (!response.success) {
    throw new Error(response.error || '获取智能体列表失败')
  }
  return response.data ?? []
}

/** POST /admin/agents/operation：创建/更新/删除 智能体 */
export async function operateAdminAgent(params: AdminAgentOperationParams): Promise<string | null> {
  const response = await post<ApiResponse<string | null>>(`${API_PREFIX}/agents/operation`, params)
  if (!response.success) {
    throw new Error(response.error || '操作智能体失败')
  }
  return response.data ?? null
}

/** POST /admin/agents/toggle：上下架开关 */
export async function toggleAdminAgent(params: AdminAgentToggleParams): Promise<void> {
  const response = await post<ApiResponse<null>>(`${API_PREFIX}/agents/toggle`, params)
  if (!response.success) {
    throw new Error(response.error || '切换上下架失败')
  }
}

/** POST /admin/agents/reorder：拖拽后批量提交新顺序 */
export async function reorderAdminAgents(params: AdminAgentReorderParams): Promise<void> {
  const response = await post<ApiResponse<null>>(`${API_PREFIX}/agents/reorder`, params)
  if (!response.success) {
    throw new Error(response.error || '排序保存失败')
  }
}

// ---------- 用户反馈 ----------

export interface AdminFeedbackListParams {
  rating_type?: 'positive' | 'neutral' | 'negative' | null
  min_length?: number | null
}

/** GET /admin/feedbacks：后台反馈列表（含用户姓名/学院等冗余字段） */
export async function fetchAdminFeedbacks(
  params: AdminFeedbackListParams = {},
): Promise<AdminFeedbackDetail[]> {
  const query: Record<string, string | number> = {}
  if (params.rating_type) query.rating_type = params.rating_type
  if (params.min_length != null) query.min_length = params.min_length
  const response = await get<ApiResponse<AdminFeedbackDetail[]>>(`${API_PREFIX}/feedbacks`, query)
  if (!response.success) {
    throw new Error(response.error || '获取反馈列表失败')
  }
  return response.data ?? []
}

/** GET /admin/feedbacks/export：返回 xlsx Blob */
export async function exportAdminFeedbacks(
  params: AdminFeedbackListParams = {},
): Promise<Blob> {
  const query: Record<string, string> = {}
  if (params.rating_type) query.rating_type = params.rating_type
  if (params.min_length != null) query.min_length = String(params.min_length)
  return getBlob(`${API_PREFIX}/feedbacks/export`, query)
}

// ---------- 数据驾驶舱 ----------

/** GET /admin/dashboard/stats：累计/日活/周活 */
export async function fetchDashboardStats(): Promise<DashboardStats> {
  const response = await get<ApiResponse<DashboardStats>>(`${API_PREFIX}/dashboard/stats`)
  if (!response.success || !response.data) {
    throw new Error(response.error || '获取驾驶舱指标失败')
  }
  return response.data
}

/** GET /admin/dashboard/feature-usage：功能使用排序（常驻 + 上架智能体） */
export async function fetchFeatureUsage(days: number): Promise<FeatureUsageItem[]> {
  const response = await get<ApiResponse<FeatureUsageItem[]>>(
    `${API_PREFIX}/dashboard/feature-usage`,
    { days },
  )
  if (!response.success) {
    throw new Error(response.error || '获取功能使用数据失败')
  }
  return response.data ?? []
}

/** GET /admin/dashboard/agent-usage：智能体使用 Top N */
export async function fetchAgentUsage(days: number, limit: number = 10): Promise<AgentUsageItem[]> {
  const response = await get<ApiResponse<AgentUsageItem[]>>(
    `${API_PREFIX}/dashboard/agent-usage`,
    { days, limit },
  )
  if (!response.success) {
    throw new Error(response.error || '获取智能体使用数据失败')
  }
  return response.data ?? []
}

export interface AdminUserListParams {
  keyword?: string | null
  role?: AppUserRole | null
  limit?: number
  offset?: number
}

/** GET /admin/dashboard/users：后台用户列表（分页 + 关键词 + 角色筛选） */
export async function fetchAdminUsers(
  params: AdminUserListParams = {},
): Promise<AdminUserDetail[]> {
  const query: Record<string, string | number> = {}
  if (params.keyword && params.keyword.trim()) query.keyword = params.keyword.trim()
  if (params.role) query.role = params.role
  if (params.limit != null) query.limit = params.limit
  if (params.offset != null) query.offset = params.offset
  const response = await get<ApiResponse<AdminUserDetail[]>>(`${API_PREFIX}/dashboard/users`, query)
  if (!response.success) {
    throw new Error(response.error || '获取用户列表失败')
  }
  return response.data ?? []
}

/** GET /admin/dashboard/users/export：返回 xlsx Blob */
export async function exportAdminUsers(keyword?: string | null, role?: AppUserRole | null): Promise<Blob> {
  const query: Record<string, string> = {}
  if (keyword && keyword.trim()) query.keyword = keyword.trim()
  if (role) query.role = role
  return getBlob(`${API_PREFIX}/dashboard/users/export`, query)
}

/** PATCH /admin/users/{id}/role：修改用户角色（管理员/教师/学生） */
export async function updateUserRole(userId: string, role: AppUserRole): Promise<void> {
  const response = await patch<ApiResponse<null>>(`${API_PREFIX}/users/${encodeURIComponent(userId)}/role`, { role })
  if (!response.success) {
    throw new Error(response.error || '修改角色失败')
  }
}

// ---------- 审计日志 ----------

function buildAuditQuery(params: AuditLogListParams): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  if (params.actor_type) query.actor_type = String(params.actor_type)
  if (params.actor_id) query.actor_id = params.actor_id
  if (params.action) query.action = params.action
  if (params.target_type) query.target_type = params.target_type
  if (params.target_id) query.target_id = params.target_id
  if (params.time_from) query.time_from = params.time_from
  if (params.time_to) query.time_to = params.time_to
  if (params.limit != null) query.limit = params.limit
  if (params.offset != null) query.offset = params.offset
  return query
}

/** GET /admin/audit-logs：审计日志列表（带筛选 + 分页） */
export async function fetchAuditLogs(
  params: AuditLogListParams = {},
): Promise<AuditLogDetail[]> {
  const response = await get<ApiResponse<AuditLogDetail[]>>(
    `${API_PREFIX}/audit-logs`,
    buildAuditQuery(params),
  )
  if (!response.success) {
    throw new Error(response.error || '获取审计日志失败')
  }
  return response.data ?? []
}

/** GET /admin/audit-logs/export：返回 xlsx Blob（沿用当前筛选条件） */
export async function exportAuditLogs(params: AuditLogListParams = {}): Promise<Blob> {
  const { limit: _l, offset: _o, ...rest } = params
  const query: Record<string, string> = {}
  for (const [k, v] of Object.entries(buildAuditQuery(rest))) {
    query[k] = String(v)
  }
  return getBlob(`${API_PREFIX}/audit-logs/export`, query)
}

/** POST /admin/audit/report：管理员手动补录一条审计事件（actor 由后端从当前 admin 强制覆盖） */
export async function reportAuditByAdmin(params: AuditReportParams): Promise<void> {
  const response = await post<ApiResponse<null>>(`${API_PREFIX}/audit/report`, params)
  if (!response.success) {
    throw new Error(response.error || '上报审计事件失败')
  }
}

// ---------- Excel 下载工具 ----------

/** 触发浏览器下载：从 Blob 与文件名构造 <a> 点击 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 给浏览器一点时间触发下载
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
