/**
 * 复习 Store - 错题记录、测验历史、间隔复习
 * 从 course.ts 抽取的复习相关状态和方法。
 */
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'

export const useReviewStore = defineStore('review', {
  state: () => ({
    wrongAnswers: [] as Array<{
      question: string
      options: string[]
      correctIndex: number
      userIndex: number
      explanation: string
      nodeId: string
      nodeName: string
      timestamp: number
      reviewCount: number
      reflection?: string
    }>,
    quizHistory: [] as Array<{
      nodeId: string
      nodeName: string
      totalQuestions: number
      correctCount: number
      timestamp: number
    }>,
  }),
  actions: {
    recordWrongAnswer(quizData: {
      question: string
      options: string[]
      correctIndex: number
      userIndex: number
      explanation: string
      nodeId: string
      nodeName: string
      reflection?: string
    }) {
      const existingIndex = this.wrongAnswers.findIndex(
        w => w.question === quizData.question && w.nodeId === quizData.nodeId
      )
      if (existingIndex >= 0) {
        const existing = this.wrongAnswers[existingIndex]
        if (existing) {
          existing.reviewCount += 1
          existing.timestamp = Date.now()
        }
      } else {
        this.wrongAnswers.push({
          ...quizData,
          timestamp: Date.now(),
          reviewCount: 1
        })
      }
      this.persistQuizData()
    },

    recordQuizResult(nodeId: string, nodeName: string, total: number, correct: number) {
      this.quizHistory.push({
        nodeId,
        nodeName,
        totalQuestions: total,
        correctCount: correct,
        timestamp: Date.now()
      })
      this.persistQuizData()
    },

    persistQuizData() {
      try {
        localStorage.setItem('quiz_wrong_answers', JSON.stringify(this.wrongAnswers))
        localStorage.setItem('quiz_history', JSON.stringify(this.quizHistory))
      } catch (e) {
        logger.error('Failed to persist quiz data:', e)
      }
    },

    restoreQuizData() {
      try {
        const wrongRaw = localStorage.getItem('quiz_wrong_answers')
        const historyRaw = localStorage.getItem('quiz_history')
        if (wrongRaw) {
          this.wrongAnswers = JSON.parse(wrongRaw)
        }
        if (historyRaw) {
          this.quizHistory = JSON.parse(historyRaw)
        }
      } catch (e) {
        logger.error('Failed to restore quiz data:', e)
      }
    },

    getWrongAnswersForReview(limit: number = 10) {
      return this.wrongAnswers
        .sort((a, b) => {
          if (a.reviewCount !== b.reviewCount) {
            return a.reviewCount - b.reviewCount
          }
          return a.timestamp - b.timestamp
        })
        .slice(0, limit)
    },

    markWrongAnswerReviewed(question: string, nodeId: string, remove: boolean = false) {
      const index = this.wrongAnswers.findIndex(
        w => w.question === question && w.nodeId === nodeId
      )
      if (index >= 0) {
        const wrongAnswer = this.wrongAnswers[index]
        if (remove) {
          this.wrongAnswers.splice(index, 1)
        } else if (wrongAnswer) {
          wrongAnswer.reviewCount += 1
          wrongAnswer.timestamp = Date.now()
        }
        this.persistQuizData()
      }
    },

    /**
     * 生成错题回顾测验。
     * 返回错题列表，调用方可将其推送到 chatHistory。
     */
    generateSmartQuizFromMistakes(): Array<{
      question: string
      options: string[]
      correctIndex: number
      explanation: string
      nodeId: string
      nodeName: string
    }> | null {
      const wrongAnswersToReview = this.getWrongAnswersForReview(5)
      if (wrongAnswersToReview.length === 0) {
        ElMessage.info('暂无需要复习的错题')
        return null
      }
      return wrongAnswersToReview.map(w => ({
        question: w.question,
        options: w.options,
        correctIndex: w.correctIndex,
        explanation: w.explanation,
        nodeId: w.nodeId,
        nodeName: w.nodeName,
      }))
    },

    getQuizStats() {
      const totalQuizzes = this.quizHistory.length
      const totalQuestions = this.quizHistory.reduce((sum, h) => sum + h.totalQuestions, 0)
      const totalCorrect = this.quizHistory.reduce((sum, h) => sum + h.correctCount, 0)
      const accuracy = totalQuestions > 0 ? Math.round((totalCorrect / totalQuestions) * 100) : 0
      return {
        totalQuizzes,
        totalQuestions,
        totalCorrect,
        accuracy,
        wrongAnswerCount: this.wrongAnswers.length
      }
    },
  },
})
