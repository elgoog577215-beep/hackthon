<template>
  <div class="smart-review-container">
    <!-- 复习系统主界面 -->
    <div class="review-dashboard" v-if="!isReviewing">
      <!-- 顶部统计卡片 - 玻璃拟态效果 -->
      <div class="stats-header">
        <div class="stat-card glass" v-motion-slide-bottom>
          <div class="stat-icon pulse">
            <el-icon><Calendar /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ reviewStats.dueToday }}</span>
            <span class="stat-label">今日待复习</span>
          </div>
          <div class="stat-glow"></div>
        </div>
        
        <div class="stat-card glass" v-motion-slide-bottom :delay="100">
          <div class="stat-icon warning">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ reviewStats.overdue }}</span>
            <span class="stat-label">已逾期</span>
          </div>
          <div class="stat-glow warning"></div>
        </div>
        
        <div class="stat-card glass" v-motion-slide-bottom :delay="200">
          <div class="stat-icon success">
            <el-icon><CircleCheck /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ reviewStats.mastered }}</span>
            <span class="stat-label">已掌握</span>
          </div>
          <div class="stat-glow success"></div>
        </div>
        
        <div class="stat-card glass" v-motion-slide-bottom :delay="300">
          <div class="stat-icon info">
            <el-icon><DataLine /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ reviewStats.retentionRate }}%</span>
            <span class="stat-label">记忆保持率</span>
          </div>
          <div class="stat-glow info"></div>
        </div>
      </div>

      <!-- 记忆曲线可视化 -->
      <div class="memory-curve-section glass" v-motion-slide-bottom :delay="400">
        <div class="section-header">
          <h3>
            <el-icon><TrendCharts /></el-icon>
            记忆遗忘曲线
          </h3>
          <el-tooltip content="基于艾宾浩斯遗忘曲线算法">
            <el-icon class="info-icon"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="curve-chart" ref="curveChartRef">
          <svg viewBox="0 0 800 200" class="curve-svg">
            <!-- 网格线 -->
            <g class="grid">
              <line v-for="i in 5" :key="i" 
                :x1="0" :y1="i * 40" :x2="800" :y2="i * 40" />
            </g>
            
            <!-- 遗忘曲线 -->
            <path class="forgetting-curve" 
              :d="forgettingCurvePath"
              fill="none"
              stroke="url(#curveGradient)"
              stroke-width="3"
              v-motion
              :initial="{ pathLength: 0 }"
              :enter="{ pathLength: 1, transition: { duration: 2000, ease: 'easeOut' } }"
            />
            
            <!-- 复习点标记 -->
            <g v-for="(point, index) in reviewPoints" :key="index">
              <circle 
                :cx="point.x" 
                :cy="point.y" 
                r="8"
                class="review-point"
                v-motion
                :initial="{ scale: 0, opacity: 0 }"
                :enter="{ scale: 1, opacity: 1, transition: { delay: 2000 + index * 200 } }"
              />
              <text :x="point.x" :y="point.y - 15" class="point-label">
                {{ point.label }}
              </text>
            </g>
            
            <!-- 渐变定义 -->
            <defs>
              <linearGradient id="curveGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#f43f5e" />
                <stop offset="50%" stop-color="#f59e0b" />
                <stop offset="100%" stop-color="#10b981" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>

      <!-- 复习列表 -->
      <div class="review-list-section glass" v-motion-slide-bottom :delay="500">
        <div class="section-header">
          <h3>
            <el-icon><List /></el-icon>
            复习计划
          </h3>
          <div class="header-actions">
            <el-button 
              type="primary" 
              size="small"
              @click="syncWrongAnswers"
              :loading="syncing"
              class="sync-btn"
            >
              <el-icon><Refresh /></el-icon>
              同步错题
            </el-button>
            <el-button 
              type="success" 
              size="large"
              @click="startReview"
              :disabled="reviewStats.dueToday === 0"
              class="start-review-btn"
              v-motion-pop
            >
              <el-icon><VideoPlay /></el-icon>
              开始复习
              <span class="btn-badge" v-if="reviewStats.dueToday > 0">
                {{ reviewStats.dueToday }}
              </span>
            </el-button>
          </div>
        </div>

        <div class="review-items-list" v-if="todayReviewItems.length > 0">
          <div 
            v-for="(item, index) in todayReviewItems" 
            :key="item.id"
            class="review-item-card"
            :class="{ 
              'overdue': isOverdue(item),
              'new': item.reviewCount === 0 
            }"
            v-motion-slide-right
            :delay="600 + index * 100"
          >
            <div class="item-status-indicator">
              <div class="status-ring" :class="getStatusClass(item)">
                <el-icon v-if="isOverdue(item)"><Warning /></el-icon>
                <el-icon v-else-if="item.reviewCount === 0"><Star /></el-icon>
                <span v-else>{{ item.reviewCount }}</span>
              </div>
            </div>
            
            <div class="item-content">
              <div class="item-header">
                <el-tag :type="getTypeTag(item.type)" size="small" effect="dark">
                  {{ getTypeLabel(item.type) }}
                </el-tag>
                <span class="item-name">{{ item.nodeName }}</span>
              </div>
              <div class="item-meta">
                <span class="difficulty-stars">
                  <el-icon v-for="n in getDifficultyLevel(item.difficulty)" :key="n">
                    <StarFilled />
                  </el-icon>
                </span>
                <span class="next-review">
                  <el-icon><Clock /></el-icon>
                  {{ formatNextReview(item.nextReviewAt) }}
                </span>
              </div>
              <div class="item-tags" v-if="item.tags?.length">
                <el-tag 
                  v-for="tag in item.tags.slice(0, 3)" 
                  :key="tag"
                  size="small"
                  effect="plain"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </div>
            
            <div class="item-forgetting-risk" v-if="getForgettingRisk(item)">
              <el-progress
                type="dashboard"
                :percentage="Math.round((getForgettingRisk(item)?.probability || 0) * 100)"
                :color="getRiskColor(Math.round((getForgettingRisk(item)?.probability || 0) * 100))"
                :width="60"
                :stroke-width="4"
              />
              <span class="risk-label">遗忘风险</span>
            </div>
            
            <div class="item-actions">
              <el-button 
                circle
                size="small"
                @click="previewItem(item)"
              >
                <el-icon><View /></el-icon>
              </el-button>
              <el-button 
                circle
                size="small"
                type="danger"
                @click="deleteItem(item.id)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
        
        <el-empty 
          v-else 
          description="今天没有需要复习的内容"
          class="empty-state"
        >
          <template #image>
            <div class="empty-illustration">
              <el-icon class="empty-icon"><Sunny /></el-icon>
            </div>
          </template>
          <p>继续保持学习，系统会自动为你安排复习计划</p>
        </el-empty>
      </div>
    </div>

    <!-- 复习会话界面 -->
    <div class="review-session" v-else>
      <!-- 进度条 -->
      <div class="session-progress">
        <div class="progress-info">
          <span class="progress-text">
            进度 {{ currentSession?.currentIndex || 0 }} / {{ currentSession?.items.length || 0 }}
          </span>
          <span class="accuracy-text">
            正确率 {{ sessionAccuracy }}%
          </span>
        </div>
        <div class="progress-bar">
          <div 
            class="progress-fill"
            :style="{ width: progressPercentage + '%' }"
            v-motion
            :initial="{ width: 0 }"
            :enter="{ width: progressPercentage + '%' }"
          />
        </div>
      </div>

      <!-- 复习卡片 -->
      <div class="review-card-container" v-if="currentItem">
        <div 
          class="review-card"
          :class="{ 'flipped': showAnswer }"
          v-motion
          :initial="{ opacity: 0, y: 50, rotateY: -90 }"
          :enter="{ opacity: 1, y: 0, rotateY: 0 }"
          :leave="{ opacity: 0, y: -50, rotateY: 90 }"
        >
          <!-- 卡片正面 - 问题 -->
          <div class="card-front">
            <div class="card-header">
              <el-tag :type="getTypeTag(currentItem.type)" effect="dark">
                {{ getTypeLabel(currentItem.type) }}
              </el-tag>
              <span class="card-counter">
                {{ currentSession?.currentIndex || 0 }} / {{ currentSession?.items.length || 0 }}
              </span>
            </div>
            
            <div class="card-content">
              <div v-if="currentItem.type === 'wrong_answer'" class="quiz-content">
                <h4 class="question-text">{{ parsedContent.question }}</h4>
                <div class="options-list">
                  <div 
                    v-for="(option, idx) in parsedContent.options" 
                    :key="idx"
                    class="option-item"
                    :class="{ 
                      'correct': showAnswer && idx === parsedContent.correctIndex,
                      'wrong': showAnswer && idx === parsedContent.userIndex && idx !== parsedContent.correctIndex
                    }"
                  >
                    <span class="option-label">{{ ['A', 'B', 'C', 'D'][idx as number] }}</span>
                    <span class="option-text">{{ option }}</span>
                    <el-icon v-if="showAnswer && idx === parsedContent.correctIndex" class="correct-icon">
                      <CircleCheck />
                    </el-icon>
                    <el-icon v-if="showAnswer && idx === parsedContent.userIndex && idx !== parsedContent.correctIndex" class="wrong-icon">
                      <CircleClose />
                    </el-icon>
                  </div>
                </div>
              </div>
              
              <div v-else class="note-content">
                <h4>{{ currentItem.nodeName }}</h4>
                <div class="note-preview" v-html="formatContent(currentItem.content)"></div>
              </div>
            </div>
            
            <div class="card-actions" v-if="!showAnswer">
              <el-button type="primary" size="large" @click="showAnswer = true">
                <el-icon><View /></el-icon>
                查看答案
              </el-button>
            </div>
          </div>
          
          <!-- 卡片背面 - 答案/解释 -->
          <div class="card-back" v-if="showAnswer">
            <div class="answer-section" v-if="currentItem.type === 'wrong_answer'">
              <div class="answer-header">
                <el-icon class="answer-icon"><CircleCheck /></el-icon>
                <span>正确答案：{{ ['A', 'B', 'C', 'D'][parsedContent.correctIndex as number] }}</span>
              </div>
              <div class="explanation">
                <h5>解析</h5>
                <p>{{ parsedContent.explanation }}</p>
              </div>
            </div>
            
            <div class="rating-section">
              <h5>你对这个内容的掌握程度如何？</h5>
              <div class="rating-buttons">
                <el-button
                  v-for="rating in ratings"
                  :key="rating.value"
                  :type="rating.type"
                  size="large"
                  @click="submitRating(rating.value)"
                  class="rating-btn"
                  v-motion-pop
                  :delay="rating.value * 100"
                >
                  <el-icon><component :is="rating.icon" /></el-icon>
                  {{ rating.label }}
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 会话完成界面 -->
      <div class="session-complete" v-if="sessionComplete">
        <div class="complete-animation">
          <div class="celebration-icon" v-motion-pop>
            <el-icon><Trophy /></el-icon>
          </div>
          <div class="confetti-container">
            <div v-for="n in 20" :key="n" class="confetti" :style="getConfettiStyle(n)"></div>
          </div>
        </div>
        
        <h2 class="complete-title" v-motion-slide-bottom>🎉 复习完成！</h2>
        
        <div class="complete-stats" v-motion-slide-bottom :delay="200">
          <div class="stat-item">
            <span class="stat-number">{{ sessionSummary?.totalItems }}</span>
            <span class="stat-label">复习项目</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">{{ sessionSummary?.correctCount }}</span>
            <span class="stat-label">正确掌握</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">{{ sessionSummary?.accuracy }}%</span>
            <span class="stat-label">正确率</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">{{ sessionSummary?.duration }}分</span>
            <span class="stat-label">用时</span>
          </div>
        </div>
        
        <div class="complete-actions" v-motion-slide-bottom :delay="400">
          <el-button type="primary" size="large" @click="finishSession">
            <el-icon><House /></el-icon>
            返回主页
          </el-button>
        </div>
      </div>
    </div>

    <!-- 预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      title="内容预览"
      width="600px"
      class="preview-dialog"
    >
      <div class="preview-content" v-if="previewItemData">
        <h4>{{ previewItemData.nodeName }}</h4>
        <el-divider />
        <div v-if="previewItemData.type === 'wrong_answer'">
          <p><strong>问题：</strong>{{ JSON.parse(previewItemData.content).question }}</p>
        </div>
        <div v-else>
          <MarkdownRenderer :content="previewItemData.content" />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useCourseStore } from '../stores/course'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownRenderer from './MarkdownRenderer.vue'
import {
  Calendar, Warning, CircleCheck, DataLine, TrendCharts,
  InfoFilled, List, Refresh, VideoPlay, Star, StarFilled,
  Clock, View, Delete, Sunny, CircleClose, Trophy, House
} from '@element-plus/icons-vue'
import type { ReviewItem } from '../utils/spacedRepetition'
import { smartReviewApi, type ReviewItem as ApiReviewItem } from '../api/smartReview'

const store = useCourseStore()
const courseId = computed(() => store.currentCourseId)

// 状态
const isReviewing = ref(false)
const showAnswer = ref(false)
const sessionComplete = ref(false)
const syncing = ref(false)
const previewVisible = ref(false)
const previewItemData = ref<ReviewItem | null>(null)
const currentSession = ref<{
  items: ReviewItem[]
  currentIndex: number
  startTime: number
  correctCount: number
} | null>(null)

// 统计数据
const reviewStats = computed(() => store.reviewStats)
const reviewItems = computed(() => store.reviewItems)

// 今日复习项目
const todayReviewItems = computed(() => {
  const now = Date.now()
  return reviewItems.value
    .filter(item => item.nextReviewAt <= now)
    .sort((a, b) => a.nextReviewAt - b.nextReviewAt)
})

// 当前复习项
const currentItem = computed(() => {
  if (!currentSession.value) return null
  return currentSession.value.items[currentSession.value.currentIndex]
})

// 解析内容
const parsedContent = computed(() => {
  if (!currentItem.value || currentItem.value.type !== 'wrong_answer') {
    return {}
  }
  try {
    return JSON.parse(currentItem.value.content)
  } catch {
    return {}
  }
})

// 进度
const progressPercentage = computed(() => {
  if (!currentSession.value || currentSession.value.items.length === 0) return 0
  return (currentSession.value.currentIndex / currentSession.value.items.length) * 100
})

const sessionAccuracy = computed(() => {
  if (!currentSession.value || currentSession.value.currentIndex === 0) return 0
  return Math.round(
    (currentSession.value.correctCount / currentSession.value.currentIndex) * 100
  )
})

// 评分选项
const ratings = [
  { value: 1, label: '完全忘记', type: 'danger', icon: 'CircleClose' },
  { value: 2, label: '有些困难', type: 'warning', icon: 'Warning' },
  { value: 3, label: '基本记得', type: 'info', icon: 'Star' },
  { value: 4, label: '记得清楚', type: 'success', icon: 'CircleCheck' },
  { value: 5, label: '完全掌握', type: 'primary', icon: 'Trophy' }
]

// 会话总结
const sessionSummary = ref<any>(null)

// 遗忘曲线路径
const forgettingCurvePath = computed(() => {
  const points = []
  for (let x = 0; x <= 800; x += 10) {
    const t = x / 800 * 30 // 30天
    const retention = Math.exp(-t / 5) * 100 // 简化的遗忘曲线
    const y = 200 - retention * 1.8
    points.push(`${x},${y}`)
  }
  return `M ${points.join(' L ')}`
})

// 复习点
const reviewPoints = ref([
  { x: 53, y: 164, label: '20分钟' },
  { x: 133, y: 128, label: '1天' },
  { x: 266, y: 92, label: '2天' },
  { x: 400, y: 74, label: '6天' },
  { x: 600, y: 56, label: '14天' }
])

// 方法
const isOverdue = (item: ReviewItem) => {
  return item.nextReviewAt < Date.now()
}

// 从后端加载复习计划
const loadReviewSchedule = async () => {
  if (!courseId.value) return
  
  try {
    const data = await smartReviewApi.getReviewSchedule(courseId.value, 20, true)
    // 转换后端数据格式为前端格式
    const convertedItems: ReviewItem[] = (data.items || []).map((item: ApiReviewItem) => {
      // const difficultyMap: Record<string, 'beginner' | 'intermediate' | 'advanced' | 'expert'> = {
      //   'easy': 'beginner',
      //   'medium': 'intermediate',
      //   'hard': 'advanced',
      //   'very_hard': 'expert'
      // }
      // const typeMap: Record<string, 'wrong_answer' | 'note' | 'knowledge_point' | 'quiz'> = {
      //   'wrong_answer': 'wrong_answer',
      //   'note': 'note',
      //   'highlight': 'note',
      //   'concept': 'knowledge_point'
      // }
      return {
        id: item.node_id,
        nodeId: item.node_id,
        nodeName: item.node_name,
        courseId: courseId.value!,
        content: item.node_content,
        type: 'note',
        createdAt: Date.now(),
        lastReviewedAt: item.last_reviewed ? new Date(item.last_reviewed).getTime() : null,
        nextReviewAt: new Date(item.next_review).getTime(),
        reviewCount: item.review_count,
        difficulty: 'intermediate',
        retentionRate: item.retention_rate || 0.8,
        masteryLevel: Math.min(item.review_count / 5, 1),
        isForgotten: item.status === 'overdue',
        tags: []
      }
    })
    // 更新store中的复习项目
    store.setReviewItems(convertedItems)
  } catch (error) {
    console.error('加载复习计划失败:', error)
  }
}

// 从后端加载复习进度
const loadReviewProgress = async () => {
  if (!courseId.value) return
  
  try {
    const data = await smartReviewApi.getReviewProgress(courseId.value)
    // 更新记忆曲线数据
    if (data.memory_curve && data.memory_curve.length > 0) {
      store.setMemoryCurve({
        dates: data.memory_curve.map(d => d.date),
        retention_rates: data.memory_curve.map(d => d.retention)
      })
    }
  } catch (error) {
    console.error('加载复习进度失败:', error)
  }
}

const getStatusClass = (item: ReviewItem) => {
  if (isOverdue(item)) return 'overdue'
  if (item.reviewCount === 0) return 'new'
  if (item.reviewCount >= 5) return 'mastered'
  return 'normal'
}

const getTypeTag = (type: string) => {
  const map: Record<string, string> = {
    'wrong_answer': 'danger',
    'note': 'success',
    'highlight': 'warning',
    'concept': 'primary'
  }
  return map[type] || 'info'
}

const getTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    'wrong_answer': '错题',
    'note': '笔记',
    'highlight': '重点',
    'concept': '概念'
  }
  return map[type] || type
}

const getDifficultyLevel = (difficulty?: string) => {
  const map: Record<string, number> = {
    'beginner': 1,
    'intermediate': 2,
    'advanced': 3,
    'expert': 4
  }
  return map[difficulty || 'intermediate'] || 2
}

const formatNextReview = (timestamp: number) => {
  const now = Date.now()
  const diff = timestamp - now
  
  if (diff < 0) return '已逾期'
  if (diff < 3600000) return '1小时内'
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时后`
  return `${Math.floor(diff / 86400000)}天后`
}

const getForgettingRisk = (item: ReviewItem) => {
  return store.getForgettingRisk(item.id)
}

const getRiskColor = (percentage: number) => {
  if (percentage >= 80) return '#f43f5e'
  if (percentage >= 50) return '#f59e0b'
  return '#10b981'
}

const formatContent = (content: string) => {
  // 简单的Markdown格式化
  return content
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

const syncWrongAnswers = async () => {
  syncing.value = true
  try {
    const count = store.syncWrongAnswersToReview()
    if (count === 0) {
      ElMessage.info('没有新的错题需要同步')
    }
  } finally {
    syncing.value = false
  }
}

const startReview = () => {
  const session = store.startReviewSession()
  if (session) {
    currentSession.value = session
    isReviewing.value = true
    showAnswer.value = false
    sessionComplete.value = false
  }
}

const submitRating = async (rating: number) => {
  if (!currentItem.value || !courseId.value) return
  
  // 本地更新
  store.submitReviewResult(currentItem.value.id, rating)
  showAnswer.value = false
  
  // 提交到后端
  try {
    await smartReviewApi.submitReviewResults(courseId.value, [
      {
        node_id: currentItem.value.nodeId,
        quality: rating,
        time_spent_seconds: 30,
        notes: ''
      }
    ])
  } catch (error) {
    console.error('提交复习结果失败:', error)
  }
  
  // 检查是否完成
  if (currentSession.value && 
      currentSession.value.currentIndex >= currentSession.value.items.length) {
    completeSession()
  }
}

const completeSession = () => {
  sessionSummary.value = store.endReviewSession()
  sessionComplete.value = true
}

const finishSession = () => {
  isReviewing.value = false
  sessionComplete.value = false
  currentSession.value = null
  sessionSummary.value = null
}

const previewItem = (item: ReviewItem) => {
  previewItemData.value = item
  previewVisible.value = true
}

const deleteItem = async (itemId: string) => {
  try {
    await ElMessageBox.confirm('确定要删除这个复习项吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    store.deleteReviewItem(itemId)
    ElMessage.success('已删除')
  } catch {
    // 取消删除
  }
}

const getConfettiStyle = (_index: number) => {
  const colors = ['#f43f5e', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b']
  return {
    left: `${Math.random() * 100}%`,
    animationDelay: `${Math.random() * 2}s`,
    backgroundColor: colors[Math.floor(Math.random() * colors.length)]
  }
}

// 生命周期
onMounted(async () => {
  store.restoreReviewItems()
  // 加载后端数据
  await loadReviewSchedule()
  await loadReviewProgress()
})

// 监听错题变化，自动同步
watch(() => store.wrongAnswers.length, (newVal, oldVal) => {
  if (newVal > oldVal) {
    store.syncWrongAnswersToReview()
  }
})

// 监听课程变化，重新加载复习计划
watch(courseId, async (newId, oldId) => {
  if (newId && newId !== oldId) {
    await loadReviewSchedule()
    await loadReviewProgress()
  }
})
</script>

<style scoped lang="scss">
.smart-review-container {
  padding: 24px;
  min-height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
  color: #e2e8f0;
}

// 玻璃拟态效果
.glass {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
}

// 统计头部
.stats-header {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  position: relative;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  overflow: hidden;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-4px);
    background: rgba(255, 255, 255, 0.08);
  }
  
  .stat-icon {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    color: white;
    
    &.pulse {
      animation: pulse 2s infinite;
    }
    
    &.warning {
      background: linear-gradient(135deg, #f59e0b, #f97316);
    }
    
    &.success {
      background: linear-gradient(135deg, #10b981, #22c55e);
    }
    
    &.info {
      background: linear-gradient(135deg, #06b6d4, #3b82f6);
    }
  }
  
  .stat-info {
    display: flex;
    flex-direction: column;
    
    .stat-value {
      font-size: 32px;
      font-weight: 700;
      background: linear-gradient(135deg, #fff, #94a3b8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .stat-label {
      font-size: 14px;
      color: #94a3b8;
    }
  }
  
  .stat-glow {
    position: absolute;
    top: -50%;
    right: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
    pointer-events: none;
    
    &.warning {
      background: radial-gradient(circle, rgba(245, 158, 11, 0.15) 0%, transparent 70%);
    }
    
    &.success {
      background: radial-gradient(circle, rgba(16, 185, 129, 0.15) 0%, transparent 70%);
    }
    
    &.info {
      background: radial-gradient(circle, rgba(6, 182, 212, 0.15) 0%, transparent 70%);
    }
  }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  50% { transform: scale(1.05); box-shadow: 0 0 0 10px rgba(59, 130, 246, 0); }
}

// 记忆曲线
.memory-curve-section {
  padding: 24px;
  margin-bottom: 24px;
  
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    
    h3 {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 18px;
      color: #e2e8f0;
      
      .el-icon {
        color: #3b82f6;
      }
    }
    
    .info-icon {
      color: #64748b;
      cursor: help;
    }
  }
  
  .curve-chart {
    .curve-svg {
      width: 100%;
      height: 200px;
      
      .grid line {
        stroke: rgba(255, 255, 255, 0.05);
        stroke-dasharray: 4, 4;
      }
      
      .forgetting-curve {
        filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.5));
      }
      
      .review-point {
        fill: #3b82f6;
        stroke: #fff;
        stroke-width: 2;
        filter: drop-shadow(0 0 6px rgba(59, 130, 246, 0.8));
        animation: pointPulse 2s infinite;
      }
      
      .point-label {
        fill: #94a3b8;
        font-size: 12px;
        text-anchor: middle;
      }
    }
  }
}

@keyframes pointPulse {
  0%, 100% { r: 6; }
  50% { r: 10; }
}

// 复习列表
.review-list-section {
  padding: 24px;
  
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    
    h3 {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 18px;
      color: #e2e8f0;
      
      .el-icon {
        color: #3b82f6;
      }
    }
    
    .header-actions {
      display: flex;
      gap: 12px;
      
      .sync-btn {
        background: rgba(245, 158, 11, 0.2);
        border-color: rgba(245, 158, 11, 0.3);
        color: #f59e0b;
        
        &:hover {
          background: rgba(245, 158, 11, 0.3);
        }
      }
      
      .start-review-btn {
        position: relative;
        background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        border: none;
        padding: 12px 24px;
        font-size: 16px;
        
        .btn-badge {
          position: absolute;
          top: -8px;
          right: -8px;
          background: #f43f5e;
          color: white;
          font-size: 12px;
          padding: 2px 8px;
          border-radius: 10px;
          animation: badgePulse 1.5s infinite;
        }
      }
    }
  }
  
  .review-items-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    
    .review-item-card {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px 20px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      transition: all 0.3s ease;
      
      &:hover {
        background: rgba(255, 255, 255, 0.06);
        transform: translateX(4px);
      }
      
      &.overdue {
        border-left: 3px solid #f43f5e;
        background: rgba(244, 63, 94, 0.05);
      }
      
      &.new {
        border-left: 3px solid #3b82f6;
      }
      
      .item-status-indicator {
        .status-ring {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          font-weight: 600;
          
          &.overdue {
            background: rgba(244, 63, 94, 0.2);
            color: #f43f5e;
            animation: ringPulse 1.5s infinite;
          }
          
          &.new {
            background: rgba(59, 130, 246, 0.2);
            color: #3b82f6;
          }
          
          &.mastered {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
          }
          
          &.normal {
            background: rgba(148, 163, 184, 0.2);
            color: #94a3b8;
          }
        }
      }
      
      .item-content {
        flex: 1;
        
        .item-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          
          .item-name {
            font-weight: 500;
            color: #e2e8f0;
          }
        }
        
        .item-meta {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 8px;
          
          .difficulty-stars {
            color: #f59e0b;
            display: flex;
            gap: 2px;
          }
          
          .next-review {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 13px;
            color: #94a3b8;
          }
        }
        
        .item-tags {
          display: flex;
          gap: 6px;
        }
      }
      
      .item-forgetting-risk {
        display: flex;
        flex-direction: column;
        align-items: center;
        
        .risk-label {
          font-size: 11px;
          color: #64748b;
          margin-top: 4px;
        }
      }
      
      .item-actions {
        display: flex;
        gap: 8px;
        opacity: 0;
        transition: opacity 0.3s;
      }
      
      &:hover .item-actions {
        opacity: 1;
      }
    }
  }
  
  .empty-state {
    padding: 60px 0;
    
    .empty-illustration {
      .empty-icon {
        font-size: 80px;
        color: #f59e0b;
        animation: sunRotate 20s linear infinite;
      }
    }
    
    p {
      color: #64748b;
      margin-top: 16px;
    }
  }
}

@keyframes ringPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(244, 63, 94, 0); }
}

@keyframes badgePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

@keyframes sunRotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

// 复习会话
.review-session {
  max-width: 800px;
  margin: 0 auto;
  
  .session-progress {
    margin-bottom: 40px;
    
    .progress-info {
      display: flex;
      justify-content: space-between;
      margin-bottom: 12px;
      
      .progress-text, .accuracy-text {
        font-size: 14px;
        color: #94a3b8;
      }
    }
    
    .progress-bar {
      height: 8px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
      overflow: hidden;
      
      .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #3b82f6, #8b5cf6);
        border-radius: 4px;
        transition: width 0.5s ease;
      }
    }
  }
  
  .review-card-container {
    perspective: 1000px;
    
    .review-card {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      padding: 40px;
      min-height: 400px;
      transition: transform 0.6s;
      transform-style: preserve-3d;
      
      &.flipped {
        transform: rotateY(180deg);
      }
      
      .card-front, .card-back {
        backface-visibility: hidden;
      }
      
      .card-back {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        padding: 40px;
        transform: rotateY(180deg);
      }
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        
        .card-counter {
          font-size: 14px;
          color: #64748b;
        }
      }
      
      .card-content {
        .question-text {
          font-size: 20px;
          line-height: 1.6;
          color: #e2e8f0;
          margin-bottom: 24px;
        }
        
        .options-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
          
          .option-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 2px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            transition: all 0.3s;
            
            &.correct {
              background: rgba(16, 185, 129, 0.1);
              border-color: #10b981;
            }
            
            &.wrong {
              background: rgba(244, 63, 94, 0.1);
              border-color: #f43f5e;
            }
            
            .option-label {
              width: 32px;
              height: 32px;
              display: flex;
              align-items: center;
              justify-content: center;
              background: rgba(59, 130, 246, 0.2);
              border-radius: 8px;
              font-weight: 600;
              color: #3b82f6;
            }
            
            .option-text {
              flex: 1;
              color: #e2e8f0;
            }
            
            .correct-icon {
              color: #10b981;
              font-size: 24px;
            }
            
            .wrong-icon {
              color: #f43f5e;
              font-size: 24px;
            }
          }
        }
        
        .note-content {
          h4 {
            font-size: 20px;
            color: #e2e8f0;
            margin-bottom: 16px;
          }
          
          .note-preview {
            line-height: 1.8;
            color: #cbd5e1;
            
            code {
              background: rgba(59, 130, 246, 0.2);
              padding: 2px 6px;
              border-radius: 4px;
              font-family: monospace;
            }
          }
        }
      }
      
      .card-actions {
        margin-top: 32px;
        text-align: center;
      }
      
      .answer-section {
        margin-bottom: 32px;
        
        .answer-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 18px;
          color: #10b981;
          margin-bottom: 16px;
          
          .answer-icon {
            font-size: 24px;
          }
        }
        
        .explanation {
          background: rgba(16, 185, 129, 0.05);
          border-left: 3px solid #10b981;
          padding: 16px 20px;
          border-radius: 0 12px 12px 0;
          
          h5 {
            margin: 0 0 8px 0;
            color: #10b981;
          }
          
          p {
            margin: 0;
            line-height: 1.7;
            color: #cbd5e1;
          }
        }
      }
      
      .rating-section {
        text-align: center;
        
        h5 {
          font-size: 16px;
          color: #94a3b8;
          margin-bottom: 20px;
        }
        
        .rating-buttons {
          display: flex;
          justify-content: center;
          gap: 12px;
          flex-wrap: wrap;
          
          .rating-btn {
            min-width: 120px;
            
            .el-icon {
              margin-right: 6px;
            }
          }
        }
      }
    }
  }
  
  .session-complete {
    text-align: center;
    padding: 60px 0;
    
    .complete-animation {
      position: relative;
      margin-bottom: 32px;
      
      .celebration-icon {
        font-size: 80px;
        color: #f59e0b;
        animation: trophyBounce 1s ease infinite;
      }
      
      .confetti-container {
        position: absolute;
        top: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 100%;
        height: 200px;
        pointer-events: none;
        
        .confetti {
          position: absolute;
          width: 10px;
          height: 10px;
          animation: confettiFall 3s linear infinite;
        }
      }
    }
    
    .complete-title {
      font-size: 32px;
      background: linear-gradient(135deg, #f59e0b, #f43f5e);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 32px;
    }
    
    .complete-stats {
      display: flex;
      justify-content: center;
      gap: 40px;
      margin-bottom: 40px;
      
      .stat-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        
        .stat-number {
          font-size: 36px;
          font-weight: 700;
          color: #e2e8f0;
        }
        
        .stat-label {
          font-size: 14px;
          color: #64748b;
          margin-top: 4px;
        }
      }
    }
  }
}

@keyframes trophyBounce {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-10px) scale(1.1); }
}

@keyframes confettiFall {
  0% { transform: translateY(-100%) rotate(0deg); opacity: 1; }
  100% { transform: translateY(200px) rotate(720deg); opacity: 0; }
}

// 响应式
@media (max-width: 1024px) {
  .stats-header {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-header {
    grid-template-columns: 1fr;
  }
  
  .review-list-section {
    .section-header {
      flex-direction: column;
      gap: 16px;
      align-items: flex-start;
    }
    
    .review-item-card {
      flex-wrap: wrap;
      
      .item-actions {
        opacity: 1;
        width: 100%;
        justify-content: flex-end;
        margin-top: 12px;
      }
    }
  }
  
  .review-session {
    .review-card {
      padding: 24px;
      
      .rating-buttons {
        .rating-btn {
          min-width: 100px;
          padding: 8px 16px;
        }
      }
    }
    
    .complete-stats {
      flex-wrap: wrap;
      gap: 20px;
    }
  }
}
</style>