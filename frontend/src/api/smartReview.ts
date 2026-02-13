const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 复习项目接口
 * 与后端 models.py 的 ReviewItem 模型保持一致
 */
export interface ReviewItem {
  /** 节点ID */
  node_id: string
  /** 节点名称 */
  node_name: string
  /** 节点内容摘要 */
  node_content: string
  /** 测验分数 */
  quiz_score?: number
  /** 上次复习时间 */
  last_reviewed?: string
  /** 下次复习时间 */
  next_review: string
  /** 复习次数 */
  review_count: number
  /** 复习间隔天数 */
  interval_days: number
  /** 简易度因子 (SM-2算法) */
  ease_factor: number
  /** 优先级: high, medium, low */
  priority: 'high' | 'medium' | 'low'
  /** 状态: due, completed, overdue, scheduled */
  status: 'due' | 'completed' | 'overdue' | 'scheduled'
  /** 记忆保留率 (0.0 - 1.0) */
  retention_rate?: number
}

/**
 * 复习结果接口
 * 与后端 models.py 的 ReviewResult 模型保持一致
 */
export interface ReviewResult {
  /** 节点ID */
  node_id: string
  /** 质量评分 (0-5, SM-2算法) */
  quality: number
  /** 花费时间(秒) */
  time_spent_seconds: number
  /** 备注 */
  notes?: string
}

/**
 * 复习统计数据接口
 * 与后端 models.py 的 ReviewStats 模型保持一致
 */
export interface ReviewStats {
  /** 总项目数 */
  total_items: number
  /** 今日到期数 */
  due_today: number
  /** 逾期数 */
  overdue: number
  /** 今日已完成数 */
  completed_today: number
  /** 连续学习天数 */
  streak_days: number
  /** 平均记忆保留率 (0.0 - 1.0) */
  retention_rate: number
}

/**
 * 记忆曲线数据点接口
 */
export interface MemoryCurveData {
  /** 相对天数 */
  day: number
  /** 日期字符串 */
  date: string
  /** 记忆保留率 (0.0 - 1.0) */
  retention: number
  /** 复习次数 */
  review_count: number
}

/**
 * 薄弱节点分析接口
 */
export interface WeakNode {
  /** 节点ID */
  node_id: string
  /** 节点名称 */
  node_name: string
  /** 测验分数 */
  quiz_score: number
  /** 复习次数 */
  review_count: number
  /** 简易度因子 */
  ease_factor: number
}

/**
 * 掌握度趋势数据接口
 */
export interface MasteryTrend {
  /** 日期 */
  date: string
  /** 平均掌握度 (0.0 - 1.0) */
  mastery: number
}

/**
 * 复习计划响应接口
 */
export interface ReviewScheduleResponse {
  /** 复习项目列表 */
  items: ReviewItem[]
  /** 统计数据 */
  stats: ReviewStats
  /** 预计所需时间(分钟) */
  estimated_time_minutes: number
}

/**
 * 复习进度响应接口
 */
export interface ReviewProgressResponse {
  /** 记忆曲线数据 */
  memory_curve: MemoryCurveData[]
  /** 总复习次数 */
  total_reviews: number
  /** 平均记忆保留率 */
  average_retention: number
  /** 薄弱节点列表 */
  weak_nodes: WeakNode[]
  /** 掌握度趋势 */
  mastery_trend: MasteryTrend[]
}

/**
 * 提交复习结果响应接口
 */
export interface SubmitReviewResponse {
  /** 更新数量 */
  updated_count: number
  /** 正确率 (0.0 - 1.0) */
  accuracy: number
  /** 下次复习日期 */
  next_review_date: string
}

/**
 * 生成复习计划请求参数
 */
export interface ReviewScheduleRequest {
  /** 最大复习项数量 */
  max_items?: number
  /** 是否重点关注薄弱环节 */
  focus_on_weak?: boolean
}

/**
 * 提交复习结果请求参数
 */
export interface SubmitReviewRequest {
  /** 课程ID */
  course_id: string
  /** 复习结果列表 */
  results: ReviewResult[]
}

// =============================================================================
// 独立导出函数（供统一复习系统使用）
// =============================================================================

/**
 * 获取智能复习计划
 * 
 * 基于SM-2算法和艾宾浩斯遗忘曲线生成个性化复习计划
 * 
 * @param courseId - 课程ID
 * @param params - 请求参数
 * @returns 复习计划响应
 */
export async function getReviewSchedule(
  courseId: string,
  params: ReviewScheduleRequest = {}
): Promise<ReviewScheduleResponse> {
  const maxItems = params.max_items ?? 20
  const focusOnWeak = params.focus_on_weak ?? true
  
  const response = await fetch(
    `${API_BASE_URL}/courses/${courseId}/review/schedule?max_items=${maxItems}&focus_on_weak=${focusOnWeak}`
  )
  if (!response.ok) {
    throw new Error('获取复习计划失败')
  }
  return response.json()
}

/**
 * 提交复习结果
 * 
 * 使用SM-2算法更新复习间隔和记忆强度
 * 
 * @param courseId - 课程ID
 * @param request - 提交请求
 * @returns 提交结果响应
 */
export async function submitReviewResults(
  courseId: string,
  request: SubmitReviewRequest
): Promise<SubmitReviewResponse> {
  const response = await fetch(
    `${API_BASE_URL}/courses/${courseId}/review/submit`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  )
  if (!response.ok) {
    throw new Error('提交复习结果失败')
  }
  return response.json()
}

/**
 * 获取复习进度
 * 
 * 返回过去30天的记忆保留率曲线和掌握度趋势
 * 
 * @param courseId - 课程ID
 * @returns 复习进度响应
 */
export async function getReviewProgress(courseId: string): Promise<ReviewProgressResponse> {
  const response = await fetch(
    `${API_BASE_URL}/courses/${courseId}/review/progress`
  )
  if (!response.ok) {
    throw new Error('获取复习进度失败')
  }
  return response.json()
}

/**
 * 获取复习统计（快速查询）
 * 
 * @param courseId - 课程ID
 * @returns 复习统计数据
 */
export async function getReviewStats(courseId: string): Promise<ReviewStats> {
  const response = await fetch(
    `${API_BASE_URL}/courses/${courseId}/review/stats`
  )
  if (!response.ok) {
    throw new Error('获取复习统计失败')
  }
  const data = await response.json()
  // 返回时去掉course_id，只保留ReviewStats字段
  const { course_id, ...stats } = data
  return stats
}

/**
 * 重置复习历史
 * 
 * 用于调试或重新开始学习
 * 
 * @param courseId - 课程ID
 * @returns 重置结果
 */
export async function resetReviewHistory(courseId: string): Promise<{ status: string; message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/courses/${courseId}/review/reset`,
    {
      method: 'POST',
    }
  )
  if (!response.ok) {
    throw new Error('重置复习历史失败')
  }
  return response.json()
}

// =============================================================================
// API对象导出（向后兼容）
// =============================================================================

/**
 * 智能复习系统 API
 * 
 * 提供基于SM-2算法的智能复习功能，包括：
 * - 生成个性化复习计划
 * - 提交复习结果并更新记忆曲线
 * - 获取复习进度和统计数据
 * - 重置复习历史
 */
export const smartReviewApi = {
  getReviewSchedule: async (
    courseId: string,
    maxItems: number = 20,
    focusOnWeak: boolean = true
  ): Promise<ReviewScheduleResponse> => {
    return getReviewSchedule(courseId, { max_items: maxItems, focus_on_weak: focusOnWeak })
  },

  submitReviewResults: async (
    courseId: string,
    results: ReviewResult[]
  ): Promise<SubmitReviewResponse> => {
    return submitReviewResults(courseId, { course_id: courseId, results })
  },

  getReviewProgress,
  getReviewStats,
  resetReviewHistory,
}

export default smartReviewApi