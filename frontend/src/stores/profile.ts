/**
 * 学习者画像 Store
 * 管理 AI 画像、Agent 评论、自评、精简摘要的状态和持久化。
 * 提供防抖增量更新和队列机制。
 */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'

const STORAGE_KEYS = {
  profile: 'learner_profile',
  commentary: 'learner_commentary',
  persona: 'learner_persona_summary',
  selfEval: 'learner_self_evaluation',
  lastUpdated: 'learner_profile_updated',
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const DEBOUNCE_MS = 30000

/** 生成按课程隔离的 localStorage key */
function courseKey(base: string, courseId: string): string {
  return courseId ? `${base}_${courseId}` : base
}

export const useProfileStore = defineStore('profile', {
  state: () => ({
    aiProfile: '',
    agentCommentary: '',
    personaSummary: '',
    selfEvaluation: '',
    isGenerating: false,
    lastUpdated: null as number | null,
    pendingUpdate: false,
    _pendingContentDesc: '' as string,
    _currentCourseId: '' as string,
  }),

  getters: {
    hasProfile: (state) => !!state.aiProfile,
  },

  actions: {
    // ========== 初始化：从 localStorage 恢复（按课程隔离） ==========
    restore(courseId?: string) {
      if (courseId !== undefined) this._currentCourseId = courseId
      const cid = this._currentCourseId
      try {
        this.aiProfile = localStorage.getItem(courseKey(STORAGE_KEYS.profile, cid)) || ''
        this.agentCommentary = localStorage.getItem(courseKey(STORAGE_KEYS.commentary, cid)) || ''
        this.personaSummary = localStorage.getItem(courseKey(STORAGE_KEYS.persona, cid)) || ''
        this.selfEvaluation = localStorage.getItem(courseKey(STORAGE_KEYS.selfEval, cid)) || ''
        const ts = localStorage.getItem(courseKey(STORAGE_KEYS.lastUpdated, cid))
        this.lastUpdated = ts ? Number(ts) : null
      } catch (e) {
        logger.warn('画像数据恢复失败，已清空', e)
        this._clearState()
      }
    },

    // ========== 持久化 ==========
    _persist() {
      const cid = this._currentCourseId
      try {
        localStorage.setItem(courseKey(STORAGE_KEYS.profile, cid), this.aiProfile)
        localStorage.setItem(courseKey(STORAGE_KEYS.commentary, cid), this.agentCommentary)
        localStorage.setItem(courseKey(STORAGE_KEYS.persona, cid), this.personaSummary)
        localStorage.setItem(courseKey(STORAGE_KEYS.selfEval, cid), this.selfEvaluation)
        localStorage.setItem(courseKey(STORAGE_KEYS.lastUpdated, cid), String(this.lastUpdated))
      } catch (e) {
        logger.error('画像数据持久化失败', e)
      }
    },

    _clearState() {
      this.aiProfile = ''
      this.agentCommentary = ''
      this.personaSummary = ''
      this.selfEvaluation = ''
      this.lastUpdated = null
    },

    // ========== 全量生成 ==========
    async generateFull(wrongAnswers: any[], notes: any[], chatSummary: string) {
      if (this.isGenerating) return
      this.isGenerating = true
      try {
        const res = await http.post('/api/profile/generate', {
          wrong_answers: wrongAnswers,
          notes: notes,
          chat_summary: chatSummary,
          self_evaluation: this.selfEvaluation,
          mode: 'full',
        })
        this.aiProfile = res.data.ai_profile
        this.agentCommentary = res.data.agent_commentary
        this.personaSummary = res.data.persona_summary
        this.lastUpdated = Date.now()
        this._persist()
      } catch (e) {
        logger.error('画像生成失败', e)
        ElMessage.error('画像生成失败，请稍后重试')
      } finally {
        this.isGenerating = false
        this._processPending()
      }
    },

    // ========== 增量更新 ==========
    async incrementalUpdate(newContentDesc: string) {
      if (this.isGenerating) {
        this.pendingUpdate = true
        this._pendingContentDesc = newContentDesc
        return
      }
      this.isGenerating = true
      try {
        const res = await http.post('/api/profile/generate', {
          current_profile: this.aiProfile,
          self_evaluation: this.selfEvaluation,
          mode: 'incremental',
          new_content: newContentDesc,
        })
        this.aiProfile = res.data.ai_profile
        this.agentCommentary = res.data.agent_commentary
        this.personaSummary = res.data.persona_summary
        this.lastUpdated = Date.now()
        this._persist()
      } catch (e) {
        logger.error('画像增量更新失败', e)
        // 静默失败，不打断用户工作流
      } finally {
        this.isGenerating = false
        this._processPending()
      }
    },

    // ========== 自评提交 ==========
    async submitSelfEvaluation(text: string) {
      this.selfEvaluation = text
      this._persist()
      if (!this.aiProfile) return
      // 自评提交触发增量更新
      await this.incrementalUpdate('用户更新了自我评价')
    },

    // ========== 防抖调度 ==========
    scheduleUpdate(newContentDesc: string) {
      if (!this.aiProfile) return // 没有画像时不触发增量更新
      if (this.isGenerating) {
        this.pendingUpdate = true
        this._pendingContentDesc = newContentDesc
        return
      }
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        debounceTimer = null
        this.incrementalUpdate(newContentDesc)
      }, DEBOUNCE_MS)
    },

    // ========== 处理排队的更新 ==========
    _processPending() {
      if (this.pendingUpdate) {
        this.pendingUpdate = false
        const desc = this._pendingContentDesc || '新增学习内容'
        this._pendingContentDesc = ''
        this.scheduleUpdate(desc)
      }
    },
  },
})
