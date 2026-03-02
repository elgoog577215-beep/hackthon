import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '../utils/http'

export interface KnowledgeState {
  node_id: string
  node_title: string
  mastery_level: number
  confidence: number
  last_study_time: string | null
  study_count: number
  correct_rate: number
  time_spent: number
  forgetting_score: number
}

export interface LearningGoal {
  id: string
  title: string
  description: string
  goal_type: string
  status: string
  target_value: number
  current_value: number
  unit: string
  progress_percentage: number
  deadline: string | null
  created_at: string
  related_nodes: string[]
  priority: number
  is_overdue: boolean
  days_remaining: number | null
}

export interface TutorAction {
  type: string
  label: string
  data: any
}

export interface TutorGreeting {
  greeting: string
  actions: TutorAction[]
  stats: {
    streak_days: number
    total_study_time: number
    total_sessions: number
    weaknesses_count: number
    review_items_count: number
  }
}

export const useTutorStore = defineStore('tutor', () => {
  const profile = ref<any>(null)
  const weaknesses = ref<any[]>([])
  const strengths = ref<any[]>([])
  const goals = ref<LearningGoal[]>([])
  const reviewItems = ref<any[]>([])
  const wrongAnswers = ref<any[]>([])
  const greeting = ref<TutorGreeting | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const hasWeaknesses = computed(() => weaknesses.value.length > 0)
  const hasReviewItems = computed(() => reviewItems.value.length > 0)
  const hasWrongAnswers = computed(() => wrongAnswers.value.length > 0)
  const activeGoals = computed(() => goals.value.filter(g => g.status === 'in_progress'))

  async function fetchGreeting(courseId?: string, nodeId?: string) {
    try {
      const params = new URLSearchParams()
      if (courseId) params.append('course_id', courseId)
      if (nodeId) params.append('node_id', nodeId)
      
      const response = await http.get(`/api/tutor/greeting?${params.toString()}`)
      greeting.value = response.data
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function fetchProfile() {
    try {
      const response = await http.get('/api/tutor/profile')
      profile.value = response.data.profile
      weaknesses.value = response.data.weaknesses || []
      strengths.value = response.data.strengths || []
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function recordLearning(data: {
    node_id: string
    node_title: string
    is_correct?: boolean
    time_spent: number
    question_data?: any
  }) {
    try {
      const response = await http.post('/api/tutor/record-learning', data)
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function createSessionSummary(data: {
    duration: number
    questions_answered: number
    correct_count: number
    nodes_studied: string[]
  }) {
    try {
      const response = await http.post('/api/tutor/session-summary', data)
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function fetchReviewItems(limit: number = 5) {
    try {
      const response = await http.get(`/api/tutor/review-items?limit=${limit}`)
      reviewItems.value = response.data.review_items
      return response.data.review_items
    } catch (e: any) {
      error.value = e.message
      return []
    }
  }

  async function fetchWrongAnswers(limit: number = 5) {
    try {
      const response = await http.get(`/api/tutor/wrong-answers?limit=${limit}`)
      wrongAnswers.value = response.data.wrong_answers
      return response.data.wrong_answers
    } catch (e: any) {
      error.value = e.message
      return []
    }
  }

  async function fetchGoals(status?: string) {
    try {
      const params = status ? `?status=${status}` : ''
      const response = await http.get(`/api/tutor/goals${params}`)
      goals.value = response.data.goals
      return response.data.goals
    } catch (e: any) {
      error.value = e.message
      return []
    }
  }

  async function createGoal(data: {
    title: string
    description: string
    goal_type: string
    target_value: number
    unit: string
    deadline?: string
    related_nodes?: string[]
    priority?: number
  }) {
    try {
      const response = await http.post('/api/tutor/goals', data)
      if (response.data.success) {
        await fetchGoals()
      }
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function updateGoalProgress(goalId: string, delta: number) {
    try {
      const response = await http.put(`/api/tutor/goals/${goalId}/progress`, {
        progress_delta: delta
      })
      if (response.data.success) {
        await fetchGoals()
      }
      return response.data
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function getSuggestion(context: {
    time_stuck?: number
    consecutive_wrong?: number
    current_node_id?: string
  }) {
    try {
      const response = await http.post('/api/tutor/suggestion', context)
      return response.data
    } catch (e: any) {
      error.value = e.message
      return { suggestions: [] }
    }
  }

  async function initialize() {
    isLoading.value = true
    try {
      await Promise.all([
        fetchGreeting(),
        fetchProfile(),
        fetchReviewItems(),
        fetchWrongAnswers(),
        fetchGoals()
      ])
    } finally {
      isLoading.value = false
    }
  }

  return {
    profile,
    weaknesses,
    strengths,
    goals,
    reviewItems,
    wrongAnswers,
    greeting,
    isLoading,
    error,
    hasWeaknesses,
    hasReviewItems,
    hasWrongAnswers,
    activeGoals,
    fetchGreeting,
    fetchProfile,
    recordLearning,
    createSessionSummary,
    fetchReviewItems,
    fetchWrongAnswers,
    fetchGoals,
    createGoal,
    updateGoalProgress,
    getSuggestion,
    initialize
  }
})
