import { get, post } from './request'
import type {
  ApiResponse,
  FeedbackDetail,
  FeedbackListRequest,
  FeedbackStatistics,
  SubmitFeedbackRequest,
} from './types'

const API_PREFIX = '/feedback'

/** 【提交用户反馈】POST /feedback（需 Authorization: Bearer） */
export async function submitFeedback(params: SubmitFeedbackRequest): Promise<string | null> {
  const body: Record<string, unknown> = {
    content: params.content,
    star: params.star,
  }
  if (params.image_paths != null && params.image_paths.length > 0) {
    body.image_paths = params.image_paths
  }
  const response = await post<ApiResponse<string | null>>(API_PREFIX, body)
  if (!response.success) throw new Error(response.error || '提交反馈失败')
  return response.data ?? null
}

/** 【查询反馈列表】GET /feedback/list（需 Authorization: Bearer） */
export async function getFeedbackList(params: FeedbackListRequest = {}): Promise<FeedbackDetail[]> {
  const response = await get<ApiResponse<FeedbackDetail[] | null>>(`${API_PREFIX}/list`, params)
  if (!response.success) throw new Error(response.error || '获取反馈列表失败')
  return response.data ?? []
}

/** 【反馈统计】GET /feedback/statistics（需 Authorization: Bearer） */
export async function getFeedbackStatistics(): Promise<FeedbackStatistics | null> {
  const response = await get<ApiResponse<FeedbackStatistics | null>>(`${API_PREFIX}/statistics`)
  if (!response.success) throw new Error(response.error || '获取反馈统计失败')
  return response.data ?? null
}
