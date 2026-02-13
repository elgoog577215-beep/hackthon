/**
 * 艾宾浩斯遗忘曲线算法实现 - 智能复习系统核心
 * 
 * 基于艾宾浩斯遗忘曲线的间隔重复算法
 * 复习间隔: 1天, 2天, 4天, 7天, 15天, 30天
 * 
 * @author AI Learning Assistant
 * @version 2.0
 */

import dayjs from 'dayjs'

// 复习间隔配置（天数）- 艾宾浩斯遗忘曲线优化版
export const REVIEW_INTERVALS = [1, 2, 4, 7, 15, 30, 60, 90]

// 记忆保留率阈值
export const RETENTION_THRESHOLD = 0.7

// 难度系数映射
export const DIFFICULTY_MULTIPLIER = {
  beginner: 1.3,      // 入门 - 延长间隔
  intermediate: 1.0,  // 进阶 - 标准间隔
  advanced: 0.8,      // 精通 - 缩短间隔
  expert: 0.6         // 专家 - 大幅缩短间隔
}

// 复习项接口
export interface ReviewItem {
  id: string
  nodeId: string
  nodeName: string
  courseId: string
  content: string
  type: 'wrong_answer' | 'note' | 'knowledge_point' | 'quiz'
  createdAt: number
  lastReviewedAt: number | null
  nextReviewAt: number
  reviewCount: number
  difficulty: 'beginner' | 'intermediate' | 'advanced' | 'expert'
  retentionRate: number  // 0.0 - 1.0
  masteryLevel: number   // 0.0 - 1.0
  isForgotten: boolean
  tags: string[]
}

// 复习计划接口
export interface ReviewPlan {
  today: ReviewItem[]
  upcoming: ReviewItem[]
  overdue: ReviewItem[]
  mastered: ReviewItem[]
}

// 复习统计接口
export interface ReviewStats {
  totalItems: number
  dueToday: number
  overdue: number
  mastered: number
  streakDays: number
  retentionRate: number
  weeklyProgress: number[]
}

/**
 * 计算下一次复习时间
 * @param reviewCount 已复习次数
 * @param difficulty 难度等级
 * @param retentionRate 记忆保留率
 * @returns 下一次复习的时间戳
 */
export function calculateNextReview(
  reviewCount: number,
  difficulty: 'beginner' | 'intermediate' | 'advanced' | 'expert' = 'intermediate',
  retentionRate: number = 1.0
): number {
  // 获取基础间隔
  const baseInterval = REVIEW_INTERVALS[Math.min(reviewCount, REVIEW_INTERVALS.length - 1)] ?? 1
  
  // 应用难度系数
  const multiplier = DIFFICULTY_MULTIPLIER[difficulty]
  
  // 根据记忆保留率调整（保留率低则缩短间隔）
  const retentionFactor = Math.max(0.5, retentionRate)
  
  // 计算最终间隔
  const finalInterval = Math.round(baseInterval * multiplier * retentionFactor)
  
  return dayjs().add(finalInterval, 'day').valueOf()
}

/**
 * 计算记忆保留率（基于艾宾浩斯遗忘曲线公式）
 * R = e^(-t/S) 其中 t是时间，S是记忆强度
 * @param lastReviewTime 上次复习时间
 * @param reviewCount 复习次数
 * @returns 记忆保留率 0.0 - 1.0
 */
export function calculateRetentionRate(
  lastReviewTime: number,
  reviewCount: number
): number {
  const daysSinceReview = dayjs().diff(dayjs(lastReviewTime), 'day', true)
  
  // 记忆强度随复习次数增加
  const memoryStrength = 1 + reviewCount * 0.5
  
  // 艾宾浩斯遗忘曲线公式
  const retention = Math.exp(-daysSinceReview / memoryStrength)
  
  return Math.max(0, Math.min(1, retention))
}

/**
 * 更新复习项状态
 * @param item 复习项
 * @param performance 表现评分 (0-5)
 * @returns 更新后的复习项
 */
export function updateReviewItem(
  item: ReviewItem,
  performance: number
): ReviewItem {
  const now = Date.now()
  
  // 根据表现调整难度
  let newDifficulty = item.difficulty
  if (performance >= 4) {
    newDifficulty = 'beginner'
  } else if (performance >= 3) {
    newDifficulty = 'intermediate'
  } else if (performance >= 2) {
    newDifficulty = 'advanced'
  } else {
    newDifficulty = 'expert'
  }
  
  // 计算新的记忆保留率
  const newRetentionRate = performance / 5
  
  // 计算掌握度
  const newMasteryLevel = Math.min(1, item.masteryLevel + (performance / 5) * 0.2)
  
  // 计算下一次复习时间
  const nextReviewAt = calculateNextReview(
    item.reviewCount + 1,
    newDifficulty,
    newRetentionRate
  )
  
  return {
    ...item,
    lastReviewedAt: now,
    nextReviewAt,
    reviewCount: item.reviewCount + 1,
    difficulty: newDifficulty,
    retentionRate: newRetentionRate,
    masteryLevel: newMasteryLevel,
    isForgotten: performance < 3
  }
}

/**
 * 生成复习计划
 * @param items 所有复习项
 * @returns 分类的复习计划
 */
export function generateReviewPlan(items: ReviewItem[]): ReviewPlan {
  const today = dayjs().startOf('day').valueOf()
  const tomorrow = dayjs().endOf('day').valueOf()
  
  const plan: ReviewPlan = {
    today: [],
    upcoming: [],
    overdue: [],
    mastered: []
  }
  
  items.forEach(item => {
    // 已掌握的项目（掌握度>0.9且连续3次表现良好）
    if (item.masteryLevel > 0.9 && item.reviewCount >= 3) {
      plan.mastered.push(item)
      return
    }
    
    // 逾期的项目
    if (item.nextReviewAt < today) {
      plan.overdue.push(item)
      return
    }
    
    // 今天需要复习的项目
    if (item.nextReviewAt >= today && item.nextReviewAt <= tomorrow) {
      plan.today.push(item)
      return
    }
    
    // 即将到期的项目
    if (item.nextReviewAt > tomorrow) {
      plan.upcoming.push(item)
    }
  })
  
  // 按优先级排序
  const sortByPriority = (a: ReviewItem, b: ReviewItem) => {
    // 遗忘的项目优先
    if (a.isForgotten !== b.isForgotten) {
      return a.isForgotten ? -1 : 1
    }
    // 逾期天数多的优先
    const overdueDiff = (a.nextReviewAt - b.nextReviewAt)
    if (Math.abs(overdueDiff) > 86400000) { // 1天的毫秒数
      return overdueDiff
    }
    // 掌握度低的优先
    return a.masteryLevel - b.masteryLevel
  }
  
  plan.today.sort(sortByPriority)
  plan.overdue.sort(sortByPriority)
  
  return plan
}

/**
 * 计算复习统计
 * @param items 所有复习项
 * @returns 复习统计数据
 */
export function calculateReviewStats(items: ReviewItem[]): ReviewStats {
  const plan = generateReviewPlan(items)
  
  // 计算平均记忆保留率
  const avgRetention = items.length > 0
    ? items.reduce((sum, item) => sum + item.retentionRate, 0) / items.length
    : 0
  
  // 计算本周进度（最近7天）
  const weeklyProgress: number[] = []
  for (let i = 6; i >= 0; i--) {
    const date = dayjs().subtract(i, 'day')
    const count = items.filter(item => 
      item.lastReviewedAt && 
      dayjs(item.lastReviewedAt).isSame(date, 'day')
    ).length
    weeklyProgress.push(count)
  }
  
  return {
    totalItems: items.length,
    dueToday: plan.today.length,
    overdue: plan.overdue.length,
    mastered: plan.mastered.length,
    streakDays: calculateReviewStreak(items),
    retentionRate: Math.round(avgRetention * 100),
    weeklyProgress
  }
}

/**
 * 计算复习连续天数
 * @param items 所有复习项
 * @returns 连续天数
 */
function calculateReviewStreak(items: ReviewItem[]): number {
  if (items.length === 0) return 0
  
  let streak = 0
  let currentDate = dayjs()
  
  while (true) {
    const hasReview = items.some(item => 
      item.lastReviewedAt && 
      dayjs(item.lastReviewedAt).isSame(currentDate, 'day')
    )
    
    if (hasReview) {
      streak++
      currentDate = currentDate.subtract(1, 'day')
    } else {
      break
    }
  }
  
  return streak
}

/**
 * 创建新的复习项
 * @param data 复习项数据
 * @returns 新的复习项
 */
export function createReviewItem(data: Partial<ReviewItem>): ReviewItem {
  const now = Date.now()
  
  return {
    id: data.id || `review_${now}_${Math.random().toString(36).substr(2, 9)}`,
    nodeId: data.nodeId || '',
    nodeName: data.nodeName || '未命名',
    courseId: data.courseId || '',
    content: data.content || '',
    type: data.type || 'knowledge_point',
    createdAt: data.createdAt || now,
    lastReviewedAt: null,
    nextReviewAt: calculateNextReview(0),
    reviewCount: 0,
    difficulty: data.difficulty || 'intermediate',
    retentionRate: 0,
    masteryLevel: 0,
    isForgotten: false,
    tags: data.tags || []
  }
}

/**
 * 获取复习优先级标签
 * @param item 复习项
 * @returns 优先级标签
 */
export function getReviewPriorityLabel(item: ReviewItem): {
  label: string
  color: string
  icon: string
} {
  if (item.isForgotten) {
    return { label: '已遗忘', color: '#ef4444', icon: '⚠️' }
  }
  if (item.nextReviewAt < Date.now()) {
    return { label: '已逾期', color: '#f97316', icon: '⏰' }
  }
  if (item.masteryLevel < 0.3) {
    return { label: '需强化', color: '#eab308', icon: '📚' }
  }
  if (item.masteryLevel > 0.8) {
    return { label: '已熟练', color: '#22c55e', icon: '✨' }
  }
  return { label: '复习中', color: '#3b82f6', icon: '🔄' }
}

/**
 * 预测遗忘风险
 * @param item 复习项
 * @returns 遗忘风险等级
 */
export function predictForgettingRisk(item: ReviewItem): {
  level: 'low' | 'medium' | 'high' | 'critical'
  probability: number
  daysUntilForgotten: number
} {
  const retention = calculateRetentionRate(
    item.lastReviewedAt || item.createdAt,
    item.reviewCount
  )
  
  const daysSinceReview = dayjs().diff(
    dayjs(item.lastReviewedAt || item.createdAt), 
    'day', 
    true
  )
  
  // 预测完全遗忘的时间（保留率<0.2）
  const memoryStrength = 1 + item.reviewCount * 0.5
  const daysUntilForgotten = Math.round(-Math.log(0.2) * memoryStrength - daysSinceReview)
  
  let level: 'low' | 'medium' | 'high' | 'critical'
  if (retention < 0.3) {
    level = 'critical'
  } else if (retention < 0.5) {
    level = 'high'
  } else if (retention < RETENTION_THRESHOLD) {
    level = 'medium'
  } else {
    level = 'low'
  }
  
  return {
    level,
    probability: Math.round((1 - retention) * 100),
    daysUntilForgotten: Math.max(0, daysUntilForgotten)
  }
}

/**
 * 智能推荐复习顺序
 * @param items 待复习项目
 * @returns 排序后的复习项目
 */
export function smartReviewOrder(items: ReviewItem[]): ReviewItem[] {
  return [...items].sort((a, b) => {
    // 1. 遗忘风险高的优先
    const riskA = predictForgettingRisk(a)
    const riskB = predictForgettingRisk(b)
    
    const riskWeight = { critical: 4, high: 3, medium: 2, low: 1 }
    if (riskWeight[riskA.level] !== riskWeight[riskB.level]) {
      return riskWeight[riskB.level] - riskWeight[riskA.level]
    }
    
    // 2. 逾期时间长的优先
    const overdueA = Date.now() - a.nextReviewAt
    const overdueB = Date.now() - b.nextReviewAt
    if (Math.abs(overdueA - overdueB) > 3600000) { // 1小时
      return overdueB - overdueA
    }
    
    // 3. 掌握度低的优先
    return a.masteryLevel - b.masteryLevel
  })
}

export default {
  REVIEW_INTERVALS,
  DIFFICULTY_MULTIPLIER,
  calculateNextReview,
  calculateRetentionRate,
  updateReviewItem,
  generateReviewPlan,
  calculateReviewStats,
  createReviewItem,
  getReviewPriorityLabel,
  predictForgettingRisk,
  smartReviewOrder
}