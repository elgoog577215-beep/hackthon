/**
 * 学习路径 Store - 学习统计、学习路径、知识掌握度
 * 从 course.ts 抽取的学习相关状态和方法。
 */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import logger from '../utils/logger'

export const useLearningStore = defineStore('learning', {
  state: () => ({
    learningStats: {
      totalStudyTime: 0,
      dailyStudyTime: {} as Record<string, number>,
      nodeReadTime: {} as Record<string, number>,
      lastReadPosition: {} as Record<string, { nodeId: string; scrollTop: number }>,
      completedNodes: [] as string[],
      streakDays: 0,
      lastStudyDate: null as string | null,
      studyDays: 0,
    },
    learningPath: null as {
      recommended_nodes: Array<{
        node_id: string
        node_name: string
        reason: string
        priority: number
        estimated_time: number
      }>
      weak_areas: string[]
      suggestions: string[]
      generated_at: string
    } | null,
    knowledgeMastery: null as {
      knowledge_points: Array<{
        point_name: string
        mastery_level: number
        related_nodes: string[]
        last_reviewed: string
        review_count: number
      }>
      overall_mastery: number
      weak_areas: string[]
      strong_areas: string[]
    } | null,
    learningPathLoading: false,
  }),
  actions: {
    /** Record study time in seconds. Internally stores seconds. */
    recordStudyTime(seconds: number, nodeId?: string) {
      const today = dayjs().format('YYYY-MM-DD')
      this.learningStats.totalStudyTime += seconds
      if (!this.learningStats.dailyStudyTime[today]) {
        this.learningStats.dailyStudyTime[today] = 0
      }
      this.learningStats.dailyStudyTime[today] += seconds
      if (nodeId) {
        if (!this.learningStats.nodeReadTime[nodeId]) {
          this.learningStats.nodeReadTime[nodeId] = 0
        }
        this.learningStats.nodeReadTime[nodeId] += seconds
      }
      const todayStr = dayjs().format('YYYY-MM-DD')
      const lastDate = this.learningStats.lastStudyDate
      if (lastDate) {
        const diff = dayjs(todayStr).diff(dayjs(lastDate), 'day')
        if (diff === 1) {
          this.learningStats.streakDays += 1
        } else if (diff > 1) {
          this.learningStats.streakDays = 1
        }
      } else {
        this.learningStats.streakDays = 1
      }
      this.learningStats.lastStudyDate = todayStr
      this.persistLearningStats()
    },

    saveReadingPosition(courseId: string, nodeId: string, scrollTop: number) {
      this.learningStats.lastReadPosition[courseId] = { nodeId, scrollTop }
      this.persistLearningStats()
    },

    getReadingPosition(courseId: string): { nodeId: string; scrollTop: number } | null {
      return this.learningStats.lastReadPosition[courseId] || null
    },

    markNodeAsCompleted(nodeId: string) {
      if (!this.learningStats.completedNodes.includes(nodeId)) {
        this.learningStats.completedNodes.push(nodeId)
        this.persistLearningStats()
      }
    },

    isNodeCompleted(nodeId: string): boolean {
      return this.learningStats.completedNodes.includes(nodeId)
    },

    getNodeReadTime(nodeId: string): number {
      return this.learningStats.nodeReadTime[nodeId] || 0
    },

    /** Returns today's study time in minutes (stored as seconds internally). */
    getTodayStudyTime(): number {
      const today = dayjs().format('YYYY-MM-DD')
      const seconds = this.learningStats.dailyStudyTime[today] || 0
      return Math.floor(seconds / 60)
    },

    /** Returns weekly study time in minutes. */
    getWeeklyStudyTime(): number {
      let total = 0
      for (let i = 0; i < 7; i++) {
        const date = dayjs().subtract(i, 'day').format('YYYY-MM-DD')
        total += this.learningStats.dailyStudyTime[date] || 0
      }
      return Math.floor(total / 60)
    },

    persistLearningStats() {
      try {
        const data = { ...this.learningStats, _version: 2 }
        localStorage.setItem('learning_stats', JSON.stringify(data))
      } catch (e) {
        logger.error('Failed to persist learning stats:', e)
      }
    },

    restoreLearningStats() {
      try {
        const raw = localStorage.getItem('learning_stats')
        if (raw) {
          const stats = JSON.parse(raw)
          // Migrate v1 (minutes) → v2 (seconds)
          if (!stats._version || stats._version < 2) {
            if (stats.totalStudyTime) stats.totalStudyTime *= 60
            if (stats.dailyStudyTime) {
              for (const key of Object.keys(stats.dailyStudyTime)) {
                stats.dailyStudyTime[key] *= 60
              }
            }
            if (stats.nodeReadTime) {
              for (const key of Object.keys(stats.nodeReadTime)) {
                stats.nodeReadTime[key] *= 60
              }
            }
            stats._version = 2
          }
          delete stats._version
          this.learningStats = { ...this.learningStats, ...stats }
          this.persistLearningStats()
        }
      } catch (e) {
        logger.error('Failed to restore learning stats:', e)
      }
    },

    async generateLearningPath(courseId: string, goal: string, availableTime: number, focusAreas?: string[], weakAreas?: string[]) {
      if (!courseId) {
        ElMessage.warning('请先选择一个课程')
        return null
      }
      this.learningPathLoading = true
      try {
        const res = await http.post(`/api/courses/${courseId}/learning_path`, {
          goal,
          available_time: availableTime,
          focus_areas: focusAreas || [],
          weak_areas: weakAreas || []
        })
        this.learningPath = res.data.learning_path
        ElMessage.success('学习路径生成成功')
        return this.learningPath
      } catch (error) {
        logger.error('Failed to generate learning path:', error)
        ElMessage.error('学习路径生成失败')
        return null
      } finally {
        this.learningPathLoading = false
      }
    },

    async fetchKnowledgeMastery(courseId: string) {
      if (!courseId) return null
      this.learningPathLoading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/knowledge_mastery`)
        this.knowledgeMastery = res.data.knowledge_mastery
        return this.knowledgeMastery
      } catch (error) {
        logger.error('Failed to fetch knowledge mastery:', error)
        return null
      } finally {
        this.learningPathLoading = false
      }
    },

    async fetchLearningStats(courseId: string) {
      if (!courseId) return null
      try {
        const res = await http.get(`/api/courses/${courseId}/learning_stats`)
        return res.data
      } catch (error) {
        logger.error('Failed to fetch learning stats:', error)
        return null
      }
    },

    clearLearningPath() {
      this.learningPath = null
    },

    clearKnowledgeMastery() {
      this.knowledgeMastery = null
    },
  },
})
