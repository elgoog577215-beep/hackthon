/**
 * 统一复习系统 - 整合本地存储和API通信
 * 
 * 本模块提供统一的复习系统接口，支持两种模式：
 * 1. 本地模式：使用localStorage存储，适用于离线场景
 * 2. API模式：与后端通信，支持跨设备同步
 * 
 * 默认使用API模式，当API不可用时自动降级到本地模式
 * 
 * @author AI Learning Assistant
 * @version 3.0
 */

import dayjs from 'dayjs'
import type {
  ReviewItem,
  ReviewStats,
  ReviewResult,
  ReviewScheduleResponse,
  SubmitReviewRequest
} from '../api/smartReview'
import {
  getReviewSchedule,
  submitReviewResults,
  getReviewProgress,
  getReviewStats
} from '../api/smartReview'

// =============================================================================
// 类型定义
// =============================================================================

/** 复习系统模式 */
export type ReviewMode = 'local' | 'api' | 'auto'

/** 本地复习项（与后端ReviewItem兼容的扩展） */
export interface LocalReviewItem extends ReviewItem {
  /** 本地唯一ID */
  local_id: string
  /** 创建时间 */
  created_at: string
  /** 标签 */
  tags?: string[]
  /** 内容类型 */
  content_type?: 'wrong_answer' | 'note' | 'knowledge_point' | 'quiz'
  /** 掌握度 0.0 - 1.0 */
  mastery_level?: number
}

/** 本地复习计划 */
export interface LocalReviewPlan {
  /** 今日复习项 */
  today: LocalReviewItem[]
  /** 即将到期 */
  upcoming: LocalReviewItem[]
  /** 已逾期 */
  overdue: LocalReviewItem[]
  /** 已掌握 */
  mastered: LocalReviewItem[]
}

/** 复习会话 */
export interface ReviewSession {
  /** 会话ID */
  session_id: string
  /** 课程ID */
  course_id: string
  /** 开始时间 */
  start_time: number
  /** 复习项列表 */
  items: LocalReviewItem[]
  /** 当前索引 */
  current_index: number
  /** 正确数 */
  correct_count: number
}

/** 复习配置 */
export interface ReviewConfig {
  /** 运行模式 */
  mode: ReviewMode
  /** 最大复习项数 */
  max_items: number
  /** 是否优先薄弱点 */
  focus_on_weak: boolean
  /** 本地存储键名 */
  storage_key: string
}

// =============================================================================
// 默认配置
// =============================================================================

const DEFAULT_CONFIG: ReviewConfig = {
  mode: 'auto',
  max_items: 20,
  focus_on_weak: true,
  storage_key: 'unified_review_items'
}

// 复习间隔配置（天数）- 艾宾浩斯遗忘曲线
const REVIEW_INTERVALS = [1, 2, 4, 7, 15, 30, 60, 90]

// 难度系数映射
const DIFFICULTY_MULTIPLIER: Record<string, number> = {
  high: 0.8,    // 困难 - 缩短间隔
  medium: 1.0,  // 中等 - 标准间隔
  low: 1.3      // 简单 - 延长间隔
}

// =============================================================================
// 本地存储管理
// =============================================================================

/**
 * 从localStorage加载复习项
 * @param storageKey 存储键名
 * @returns 复习项列表
 */
function loadLocalItems(storageKey: string): LocalReviewItem[] {
  try {
    const raw = localStorage.getItem(storageKey)
    if (raw) {
      return JSON.parse(raw)
    }
  } catch (e) {
    console.error('Failed to load local review items:', e)
  }
  return []
}

/**
 * 保存复习项到localStorage
 * @param items 复习项列表
 * @param storageKey 存储键名
 */
function saveLocalItems(items: LocalReviewItem[], storageKey: string): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify(items))
  } catch (e) {
    console.error('Failed to save local review items:', e)
  }
}

// =============================================================================
// 核心算法
// =============================================================================

/**
 * 计算下一次复习时间（基于SM-2算法和艾宾浩斯遗忘曲线）
 * @param reviewCount 已复习次数
 * @param difficulty 难度等级
 * @returns 下一次复习的ISO时间字符串
 */
function calculateNextReview(
  reviewCount: number,
  difficulty: string = 'intermediate'
): string {
  const baseInterval = REVIEW_INTERVALS[Math.min(reviewCount, REVIEW_INTERVALS.length - 1)] ?? 1
  const multiplier = DIFFICULTY_MULTIPLIER[difficulty] ?? 1.0
  const finalInterval = Math.round(baseInterval * multiplier)
  
  return dayjs().add(finalInterval, 'day').toISOString()
}

/**
 * 计算掌握度
 * @param reviewCount 复习次数
 * @param avgQuality 平均质量评分
 * @returns 掌握度 0.0 - 1.0
 */
function calculateMastery(reviewCount: number, avgQuality: number): number {
  if (reviewCount === 0) return 0
  const baseMastery = Math.min(1, reviewCount * 0.15)
  const qualityBonus = (avgQuality / 5) * 0.4
  return Math.min(1, baseMastery + qualityBonus)
}

/**
 * 更新复习项状态（SM-2算法）
 * @param item 复习项
 * @param quality 质量评分 0-5
 * @returns 更新后的复习项
 */
function updateItemWithSM2(item: LocalReviewItem, quality: number): LocalReviewItem {
  const now = dayjs().toISOString()
  
  // 根据质量调整简易度因子
  let newEaseFactor = item.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
  if (newEaseFactor < 1.3) newEaseFactor = 1.3
  
  // 计算新的间隔天数
  let newInterval: number
  if (quality < 3) {
    // 答错了，重置间隔
    newInterval = 1
  } else if (item.review_count === 0) {
    newInterval = 1
  } else if (item.review_count === 1) {
    newInterval = 6
  } else {
    newInterval = Math.round(item.interval_days * newEaseFactor)
  }
  
  // 限制最大间隔
  newInterval = Math.min(newInterval, 365)
  
  // 计算新的掌握度
  const newMastery = calculateMastery(item.review_count + 1, quality)
  
  // 确定优先级
  let newPriority = item.priority
  if (quality < 3) {
    newPriority = 'high'
  } else if (newMastery > 0.8) {
    newPriority = 'low'
  }
  
  return {
    ...item,
    last_reviewed: now,
    next_review: dayjs().add(newInterval, 'day').toISOString(),
    review_count: item.review_count + 1,
    interval_days: newInterval,
    ease_factor: newEaseFactor,
    priority: newPriority,
    mastery_level: newMastery,
    status: newMastery > 0.9 ? 'completed' : 'due'
  }
}

// =============================================================================
// 复习计划生成
// =============================================================================

/**
 * 生成本地复习计划
 * @param items 所有复习项
 * @returns 分类的复习计划
 */
function generateLocalPlan(items: LocalReviewItem[]): LocalReviewPlan {
  const today = dayjs().startOf('day')
  const tomorrow = dayjs().endOf('day')
  
  const plan: LocalReviewPlan = {
    today: [],
    upcoming: [],
    overdue: [],
    mastered: []
  }
  
  items.forEach(item => {
    const nextReview = dayjs(item.next_review)
    
    // 已掌握的项目
    if (item.status === 'completed' || (item.mastery_level && item.mastery_level > 0.9)) {
      plan.mastered.push(item)
      return
    }
    
    // 逾期的项目
    if (nextReview.isBefore(today)) {
      plan.overdue.push(item)
      return
    }
    
    // 今天需要复习的项目
    if (nextReview.isBetween(today, tomorrow, null, '[]')) {
      plan.today.push(item)
      return
    }
    
    // 即将到期的项目
    if (nextReview.isAfter(tomorrow)) {
      plan.upcoming.push(item)
    }
  })
  
  // 按优先级排序
  const sortByPriority = (a: LocalReviewItem, b: LocalReviewItem) => {
    const priorityWeight = { high: 3, medium: 2, low: 1 }
    return (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0)
  }
  
  plan.today.sort(sortByPriority)
  plan.overdue.sort(sortByPriority)
  
  return plan
}

/**
 * 计算本地统计
 * @param items 所有复习项
 * @returns 统计数据
 */
function calculateLocalStats(items: LocalReviewItem[]): ReviewStats {
  const plan = generateLocalPlan(items)
  const today = dayjs().format('YYYY-MM-DD')
  
  // 计算今日已完成数
  const completedToday = items.filter(item => {
    if (!item.last_reviewed) return false
    return dayjs(item.last_reviewed).format('YYYY-MM-DD') === today
  }).length
  
  // 计算记忆保留率
  const retentionRate = items.length > 0
    ? items.reduce((sum, item) => sum + (item.mastery_level || 0), 0) / items.length
    : 0
  
  return {
    total_items: items.length,
    due_today: plan.today.length,
    overdue: plan.overdue.length,
    completed_today: completedToday,
    streak_days: calculateStreak(items),
    retention_rate: Math.round(retentionRate * 100) / 100
  }
}

/**
 * 计算连续学习天数
 * @param items 复习项列表
 * @returns 连续天数
 */
function calculateStreak(items: LocalReviewItem[]): number {
  if (items.length === 0) return 0
  
  let streak = 0
  let currentDate = dayjs()
  
  while (true) {
    const dateStr = currentDate.format('YYYY-MM-DD')
    const hasReview = items.some(item => {
      if (!item.last_reviewed) return false
      return dayjs(item.last_reviewed).format('YYYY-MM-DD') === dateStr
    })
    
    if (hasReview) {
      streak++
      currentDate = currentDate.subtract(1, 'day')
    } else {
      break
    }
  }
  
  return streak
}

// =============================================================================
// 统一复习系统类
// =============================================================================

export class UnifiedReviewSystem {
  private config: ReviewConfig
  private currentMode: 'local' | 'api'
  private localItems: LocalReviewItem[]
  
  constructor(config: Partial<ReviewConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.currentMode = this.config.mode === 'auto' ? 'api' : this.config.mode
    this.localItems = loadLocalItems(this.config.storage_key)
  }
  
  /**
   * 获取当前模式
   * @returns 当前运行模式
   */
  getMode(): 'local' | 'api' {
    return this.currentMode
  }
  
  /**
   * 切换到指定模式
   * @param mode 目标模式
   */
  setMode(mode: ReviewMode): void {
    if (mode === 'auto') {
      this.currentMode = 'api'
    } else {
      this.currentMode = mode
    }
  }
  
  /**
   * 降级到本地模式（当API失败时调用）
   */
  private fallbackToLocal(): void {
    if (this.config.mode === 'auto') {
      console.warn('API mode failed, falling back to local mode')
      this.currentMode = 'local'
    }
  }
  
  // ---------------------------------------------------------------------------
  // 复习项管理
  // ---------------------------------------------------------------------------
  
  /**
   * 创建新的复习项
   * @param data 复习项数据
   * @returns 创建的复习项
   */
  createItem(data: Partial<LocalReviewItem>): LocalReviewItem {
    const now = dayjs().toISOString()
    const newItem: LocalReviewItem = {
      local_id: `review_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      node_id: data.node_id || '',
      node_name: data.node_name || '未命名',
      node_content: data.node_content || '',
      next_review: now,
      review_count: 0,
      interval_days: 1,
      ease_factor: 2.5,
      priority: data.priority || 'medium',
      status: 'due',
      created_at: now,
      tags: data.tags || [],
      content_type: data.content_type || 'knowledge_point',
      mastery_level: 0
    }
    
    // 添加到本地存储
    this.localItems.push(newItem)
    saveLocalItems(this.localItems, this.config.storage_key)
    
    return newItem
  }
  
  /**
   * 删除复习项
   * @param localId 本地ID
   */
  deleteItem(localId: string): void {
    this.localItems = this.localItems.filter(item => item.local_id !== localId)
    saveLocalItems(this.localItems, this.config.storage_key)
  }
  
  /**
   * 获取所有复习项
   * @returns 复习项列表
   */
  getAllItems(): LocalReviewItem[] {
    return [...this.localItems]
  }
  
  // ---------------------------------------------------------------------------
  // 复习计划
  // ---------------------------------------------------------------------------
  
  /**
   * 获取复习计划
   * @param courseId 课程ID
   * @returns 复习计划
   */
  async getSchedule(courseId: string): Promise<LocalReviewPlan> {
    if (this.currentMode === 'api') {
      try {
        const response = await getReviewSchedule(courseId, {
          max_items: this.config.max_items,
          focus_on_weak: this.config.focus_on_weak
        })
        
        // 将API响应转换为本地格式
        const items: LocalReviewItem[] = response.items.map(item => ({
          ...item,
          local_id: `api_${item.node_id}`,
          created_at: item.last_reviewed || dayjs().toISOString(),
          tags: [],
          content_type: 'knowledge_point',
          mastery_level: item.review_count > 0 ? item.ease_factor / 2.5 : 0
        }))
        
        return generateLocalPlan(items)
      } catch (error) {
        this.fallbackToLocal()
      }
    }
    
    // 本地模式
    return generateLocalPlan(this.localItems)
  }
  
  /**
   * 获取今日复习计划
   * @returns 今日需要复习的项
   */
  getTodayPlan(): LocalReviewItem[] {
    const plan = generateLocalPlan(this.localItems)
    return [...plan.overdue, ...plan.today]
  }
  
  // ---------------------------------------------------------------------------
  // 提交复习结果
  // ---------------------------------------------------------------------------
  
  /**
   * 提交复习结果
   * @param courseId 课程ID
   * @param localId 复习项本地ID
   * @param quality 质量评分 0-5
   * @param timeSpent 花费时间（秒）
   * @returns 更新后的复习项
   */
  async submitResult(
    courseId: string,
    localId: string,
    quality: number,
    timeSpent: number = 0
  ): Promise<LocalReviewItem | null> {
    const itemIndex = this.localItems.findIndex(item => item.local_id === localId)
    if (itemIndex === -1) return null
    
    const item = this.localItems[itemIndex]
    
    if (this.currentMode === 'api') {
      try {
        const request: SubmitReviewRequest = {
          course_id: courseId,
          results: [{
            node_id: item.node_id,
            quality,
            time_spent_seconds: timeSpent
          }]
        }
        
        await submitReviewResults(courseId, request)
      } catch (error) {
        this.fallbackToLocal()
      }
    }
    
    // 本地更新（无论API模式还是本地模式）
    const updatedItem = updateItemWithSM2(item, quality)
    this.localItems[itemIndex] = updatedItem
    saveLocalItems(this.localItems, this.config.storage_key)
    
    return updatedItem
  }
  
  // ---------------------------------------------------------------------------
  // 统计数据
  // ---------------------------------------------------------------------------
  
  /**
   * 获取复习统计
   * @param courseId 课程ID
   * @returns 统计数据
   */
  async getStats(courseId: string): Promise<ReviewStats> {
    if (this.currentMode === 'api') {
      try {
        return await getReviewStats(courseId)
      } catch (error) {
        this.fallbackToLocal()
      }
    }
    
    return calculateLocalStats(this.localItems)
  }
  
  /**
   * 获取复习进度
   * @param courseId 课程ID
   * @returns 进度数据
   */
  async getProgress(courseId: string) {
    if (this.currentMode === 'api') {
      try {
        return await getReviewProgress(courseId)
      } catch (error) {
        this.fallbackToLocal()
      }
    }
    
    // 本地模式返回简化版进度
    const items = this.localItems
    const totalReviews = items.reduce((sum, item) => sum + item.review_count, 0)
    const avgRetention = items.length > 0
      ? items.reduce((sum, item) => sum + (item.mastery_level || 0), 0) / items.length
      : 0
    
    return {
      total_reviews: totalReviews,
      average_retention: avgRetention,
      memory_curve: [],
      weak_nodes: [],
      mastery_trend: []
    }
  }
  
  // ---------------------------------------------------------------------------
  // 会话管理
  // ---------------------------------------------------------------------------
  
  /**
   * 开始复习会话
   * @param courseId 课程ID
   * @returns 复习会话
   */
  async startSession(courseId: string): Promise<ReviewSession | null> {
    const plan = await this.getSchedule(courseId)
    const itemsToReview = [...plan.overdue, ...plan.today]
    
    if (itemsToReview.length === 0) {
      return null
    }
    
    // 智能排序：优先复习逾期和高优先级的
    itemsToReview.sort((a, b) => {
      const priorityWeight = { high: 3, medium: 2, low: 1 }
      return (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0)
    })
    
    const session: ReviewSession = {
      session_id: `session_${Date.now()}`,
      course_id: courseId,
      start_time: Date.now(),
      items: itemsToReview,
      current_index: 0,
      correct_count: 0
    }
    
    return session
  }
  
  /**
   * 结束复习会话
   * @param session 复习会话
   * @returns 会话总结
   */
  endSession(session: ReviewSession): {
    totalItems: number
    correctCount: number
    accuracy: number
    duration: number
    completed: boolean
  } {
    const duration = Math.round((Date.now() - session.start_time) / 60000)
    const accuracy = session.items.length > 0
      ? Math.round((session.correct_count / session.items.length) * 100)
      : 0
    
    return {
      totalItems: session.items.length,
      correctCount: session.correct_count,
      accuracy,
      duration,
      completed: session.current_index >= session.items.length
    }
  }
  
  // ---------------------------------------------------------------------------
  // 数据同步
  // ---------------------------------------------------------------------------
  
  /**
   * 同步本地数据到服务器（当从本地模式切换到API模式时）
   * @param courseId 课程ID
   */
  async syncToServer(courseId: string): Promise<void> {
    if (this.currentMode !== 'api') {
      console.warn('Not in API mode, skipping sync')
      return
    }
    
    // 只同步未同步过的项目（以local_开头的ID）
    const unsyncedItems = this.localItems.filter(item => 
      item.local_id.startsWith('local_') && item.node_id
    )
    
    if (unsyncedItems.length === 0) return
    
    console.log(`Syncing ${unsyncedItems.length} items to server...`)
    
    // 逐个提交复习结果（如果已经复习过）
    for (const item of unsyncedItems) {
      if (item.review_count > 0 && item.last_reviewed) {
        try {
          const quality = Math.round((item.mastery_level || 0.5) * 5)
          await this.submitResult(courseId, item.local_id, quality, 0)
        } catch (error) {
          console.error(`Failed to sync item ${item.local_id}:`, error)
        }
      }
    }
  }
  
  /**
   * 清空本地数据
   */
  clearLocalData(): void {
    this.localItems = []
    localStorage.removeItem(this.config.storage_key)
  }
}

// =============================================================================
// 便捷函数
// =============================================================================

let globalReviewSystem: UnifiedReviewSystem | null = null

/**
 * 获取全局复习系统实例
 * @param config 配置
 * @returns 复习系统实例
 */
export function getReviewSystem(config?: Partial<ReviewConfig>): UnifiedReviewSystem {
  if (!globalReviewSystem) {
    globalReviewSystem = new UnifiedReviewSystem(config)
  }
  return globalReviewSystem
}

/**
 * 重置全局复习系统实例
 */
export function resetReviewSystem(): void {
  globalReviewSystem = null
}

export default UnifiedReviewSystem
