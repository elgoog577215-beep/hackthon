<template>
  <div class="h-full flex flex-col bg-gradient-to-br from-slate-50/50 to-white/30">
    <!-- Header -->
    <div class="mx-3 mt-3 mb-2 px-4 py-3 flex items-center justify-between glass-panel-tech-floating rounded-xl">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white shadow-md">
          <el-icon :size="18"><TrendCharts /></el-icon>
        </div>
        <span class="font-bold text-slate-700">学习统计</span>
      </div>
      <div class="flex items-center gap-1.5 text-xs text-slate-500">
        <div class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></div>
        <span>实时更新</span>
      </div>
    </div>

    <!-- Stats Content -->
    <div class="flex-1 overflow-y-auto p-3 space-y-3 sidebar-scroll">
      <!-- Streak Card -->
      <div class="bg-white/70 backdrop-blur-sm rounded-xl p-4 border border-slate-100/60 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <el-icon class="text-amber-500" :size="20"><Trophy /></el-icon>
            <span class="text-sm font-semibold text-slate-700">连续学习</span>
          </div>
          <span class="text-2xl font-bold text-amber-500">{{ learningStats.streakDays }}<span class="text-xs font-normal text-slate-400 ml-1">天</span></span>
        </div>
        <div class="flex gap-1">
          <div v-for="day in last7Days" :key="day.date"
               class="flex-1 flex flex-col items-center gap-1">
            <div class="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-medium transition-colors"
                 :class="day.hasStudy ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-300'">
              <el-icon v-if="day.hasStudy" :size="12"><Check /></el-icon>
              <span v-else>·</span>
            </div>
            <span class="text-[9px] text-slate-400">{{ day.label }}</span>
          </div>
        </div>
      </div>

      <!-- Time Stats Grid -->
      <div class="grid grid-cols-2 gap-3">
        <!-- Today -->
        <div class="bg-white/70 backdrop-blur-sm rounded-xl p-3 border border-slate-100/60 shadow-sm">
          <div class="flex items-center gap-1.5 mb-2">
            <el-icon class="text-primary-500" :size="14"><Clock /></el-icon>
            <span class="text-xs text-slate-500">今日学习</span>
          </div>
          <div class="text-xl font-bold text-slate-800">{{ formatTime(todayTime) }}</div>
          <div class="text-[10px] text-slate-400 mt-1">目标: 30分钟</div>
          <div class="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-primary-400 to-primary-500 rounded-full transition-all duration-500"
                 :style="{ width: Math.min((todayTime / 30) * 100, 100) + '%' }"></div>
          </div>
        </div>

        <!-- Weekly -->
        <div class="bg-white/70 backdrop-blur-sm rounded-xl p-3 border border-slate-100/60 shadow-sm">
          <div class="flex items-center gap-1.5 mb-2">
            <el-icon class="text-indigo-500" :size="14"><Calendar /></el-icon>
            <span class="text-xs text-slate-500">本周累计</span>
          </div>
          <div class="text-xl font-bold text-slate-800">{{ formatTime(weeklyTime) }}</div>
          <div class="text-[10px] text-slate-400 mt-1">日均 {{ formatTime(Math.round(weeklyTime / 7)) }}</div>
        </div>

        <!-- Total -->
        <div class="bg-white/70 backdrop-blur-sm rounded-xl p-3 border border-slate-100/60 shadow-sm">
          <div class="flex items-center gap-1.5 mb-2">
            <el-icon class="text-emerald-500" :size="14"><Timer /></el-icon>
            <span class="text-xs text-slate-500">总学习时长</span>
          </div>
          <div class="text-xl font-bold text-slate-800">{{ formatTime(totalTime) }}</div>
          <div class="text-[10px] text-slate-400 mt-1">{{ totalNodes }} 个知识点</div>
        </div>

        <!-- Completion Rate -->
        <div class="bg-white/70 backdrop-blur-sm rounded-xl p-3 border border-slate-100/60 shadow-sm">
          <div class="flex items-center gap-1.5 mb-2">
            <el-icon class="text-amber-500" :size="14"><CircleCheck /></el-icon>
            <span class="text-xs text-slate-500">完成进度</span>
          </div>
          <div class="text-xl font-bold text-slate-800">{{ completionRate }}%</div>
          <div class="text-[10px] text-slate-400 mt-1">{{ completedCount }}/{{ totalNodes }} 章节</div>
        </div>
      </div>

      <!-- Weekly Chart -->
      <div class="bg-white/70 backdrop-blur-sm rounded-xl p-4 border border-slate-100/60 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <span class="text-sm font-semibold text-slate-700">本周学习趋势</span>
          <span class="text-xs text-slate-400">单位: 分钟</span>
        </div>
        <div class="flex items-end gap-2 h-24">
          <div v-for="day in weeklyData" :key="day.date" class="flex-1 flex flex-col items-center gap-1">
            <div class="w-full bg-slate-100 rounded-t-md relative overflow-hidden" style="height: 80px;">
              <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-primary-400 to-primary-300 rounded-t-md transition-all duration-500"
                   :style="{ height: day.percentage + '%' }"></div>
            </div>
            <span class="text-[9px] text-slate-400">{{ day.label }}</span>
          </div>
        </div>
      </div>

      <!-- Quiz Statistics -->
      <div class="bg-white/70 backdrop-blur-sm rounded-xl p-4 border border-slate-100/60 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <el-icon class="text-purple-500" :size="16"><DocumentChecked /></el-icon>
            <span class="text-sm font-semibold text-slate-700">测验统计</span>
          </div>
          <div class="flex gap-2">
            <button
              @click="showLearningReport = true"
              class="text-[10px] px-2 py-1 bg-purple-50 text-purple-600 rounded-full hover:bg-purple-100 transition-colors"
            >
              学习报告
            </button>
            <button
              v-if="quizStats.wrongAnswerCount > 0"
              @click="startWrongAnswerReview"
              class="text-[10px] px-2 py-1 bg-red-50 text-red-600 rounded-full hover:bg-red-100 transition-colors"
            >
              复习错题 ({{ quizStats.wrongAnswerCount }})
            </button>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div class="text-center p-2 bg-slate-50/50 rounded-lg">
            <div class="text-lg font-bold text-slate-700">{{ quizStats.totalQuizzes }}</div>
            <div class="text-[10px] text-slate-400">完成测验</div>
          </div>
          <div class="text-center p-2 bg-slate-50/50 rounded-lg">
            <div class="text-lg font-bold" :class="quizStats.accuracy >= 80 ? 'text-emerald-500' : 'text-slate-700'">
              {{ quizStats.accuracy }}%
            </div>
            <div class="text-[10px] text-slate-400">正确率</div>
          </div>
        </div>
        <div v-if="quizStats.totalQuestions > 0" class="mt-3 pt-3 border-t border-slate-100">
          <div class="flex items-center justify-between text-xs">
            <span class="text-slate-500">总答题数</span>
            <span class="font-medium text-slate-700">{{ quizStats.totalQuestions }}</span>
          </div>
          <div class="flex items-center justify-between text-xs mt-1">
            <span class="text-slate-500">正确数</span>
            <span class="font-medium text-emerald-600">{{ quizStats.totalCorrect }}</span>
          </div>
          <!-- Difficulty Progress -->
          <div class="mt-3">
            <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
              <span>难度适应</span>
              <span>{{ difficultyLevel }}</span>
            </div>
            <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-400 rounded-full transition-all duration-500"
                   :style="{ width: difficultyProgress + '%' }"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Knowledge Graph Preview -->
      <div class="bg-white/70 backdrop-blur-sm rounded-xl p-4 border border-slate-100/60 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <el-icon class="text-indigo-500" :size="16"><Connection /></el-icon>
            <span class="text-sm font-semibold text-slate-700">知识图谱</span>
          </div>
          <button
            @click="showKnowledgeGraphModal = true"
            class="text-[10px] px-2 py-1 bg-indigo-50 text-indigo-600 rounded-full hover:bg-indigo-100 transition-colors"
          >
            查看图谱
          </button>
        </div>
        <div class="relative h-32 bg-gradient-to-br from-slate-50 to-indigo-50/30 rounded-lg overflow-hidden cursor-pointer group"
             @click="showKnowledgeGraphModal = true">
          <!-- Mini Knowledge Graph Visualization -->
          <div class="absolute inset-0 flex items-center justify-center">
            <div class="relative w-full h-full">
              <!-- Central Node -->
              <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/30 flex items-center justify-center text-white text-xs font-bold z-10 transition-transform duration-300 group-hover:scale-110">
                {{ completionRate }}%
              </div>
              <!-- Satellite Nodes -->
              <div v-for="(node, idx) in knowledgeNodes.slice(0, 6)" :key="idx"
                   class="absolute w-5 h-5 rounded-full flex items-center justify-center text-[8px] transition-all duration-500"
                   :class="node.completed ? 'bg-emerald-400 text-white' : 'bg-slate-300 text-slate-500'"
                   :style="getNodePosition(idx, 6)">
                <el-icon v-if="node.completed" :size="8"><Check /></el-icon>
                <span v-else>{{ idx + 1 }}</span>
              </div>
              <!-- Connection Lines (SVG) -->
              <svg class="absolute inset-0 w-full h-full pointer-events-none">
                <line v-for="(line, idx) in connectionLines" :key="idx"
                      :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2"
                      stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3,2"/>
              </svg>
            </div>
          </div>
          <div class="absolute bottom-2 left-2 right-2 flex justify-between text-[9px] text-slate-400">
            <span>已掌握: {{ completedCount }}</span>
            <span>待学习: {{ totalNodes - completedCount }}</span>
          </div>
          <!-- Hover Overlay -->
          <div class="absolute inset-0 bg-indigo-500/5 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <span class="text-xs text-indigo-600 font-medium">点击查看完整图谱</span>
          </div>
        </div>
      </div>

      <!-- Learning Suggestions -->
      <div class="bg-gradient-to-br from-amber-50 to-orange-50/50 rounded-xl p-4 border border-amber-100/60 shadow-sm">
        <div class="flex items-center gap-2 mb-3">
          <el-icon class="text-amber-500" :size="16"><StarFilled /></el-icon>
          <span class="text-sm font-semibold text-slate-700">学习建议</span>
        </div>
        <div class="space-y-2">
          <div v-for="(suggestion, idx) in learningSuggestions" :key="idx"
               class="flex items-start gap-2 text-xs">
            <div class="w-5 h-5 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
              <span class="text-amber-600 font-bold">{{ idx + 1 }}</span>
            </div>
            <p class="text-slate-600 leading-relaxed">{{ suggestion }}</p>
          </div>
          <div v-if="learningSuggestions.length === 0" class="text-xs text-slate-500 text-center py-2">
            继续学习，我们会为你提供个性化建议
          </div>
        </div>
      </div>

      <!-- Recent Achievements -->
      <div class="bg-white/70 backdrop-blur-sm rounded-xl p-4 border border-slate-100/60 shadow-sm">
        <div class="flex items-center gap-2 mb-3">
          <el-icon class="text-amber-500" :size="16"><Medal /></el-icon>
          <span class="text-sm font-semibold text-slate-700">最近成就</span>
        </div>
        <div class="space-y-2">
          <div v-for="achievement in recentAchievements" :key="achievement.id"
               class="flex items-center gap-3 p-2 rounded-lg bg-slate-50/50">
            <div class="w-8 h-8 rounded-lg flex items-center justify-center text-lg">
              {{ achievement.icon }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-xs font-medium text-slate-700">{{ achievement.title }}</div>
              <div class="text-[10px] text-slate-400">{{ achievement.desc }}</div>
            </div>
            <span class="text-[10px] text-slate-400">{{ achievement.time }}</span>
          </div>
          <div v-if="recentAchievements.length === 0" class="text-center py-4 text-xs text-slate-400">
            继续学习，解锁更多成就！
          </div>
        </div>
      </div>
    </div>

    <!-- Knowledge Graph Modal - Full Component -->
    <el-dialog
      v-model="showKnowledgeGraphModal"
      title="📊 知识图谱"
      width="90%"
      :fullscreen="isMobile"
      class="knowledge-graph-full-dialog"
      destroy-on-close
    >
      <div class="h-[70vh]">
        <KnowledgeGraph />
      </div>
    </el-dialog>

    <!-- Learning Report Modal -->
    <el-dialog
      v-model="showLearningReport"
      title="📊 学习报告"
      width="90%"
      :fullscreen="isMobile"
      class="learning-report-dialog"
      destroy-on-close
    >
      <div class="h-[70vh] overflow-y-auto custom-scrollbar p-4 space-y-6">
        <!-- Report Header -->
        <div class="text-center pb-6 border-b border-slate-100">
          <div class="text-3xl font-black text-slate-800 mb-2">{{ courseStore.currentCourse?.course_name || '学习报告' }}</div>
          <div class="text-sm text-slate-500">生成时间: {{ dayjs().format('YYYY年MM月DD日 HH:mm') }}</div>
        </div>

        <!-- Overall Score -->
        <div class="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl p-6 text-white">
          <div class="text-center">
            <div class="text-sm opacity-80 mb-2">综合学习评分</div>
            <div class="text-5xl font-black mb-2">{{ overallScore }}</div>
            <div class="text-sm opacity-90">{{ scoreEvaluation }}</div>
          </div>
          <div class="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-white/20">
            <div class="text-center">
              <div class="text-2xl font-bold">{{ completionRate }}%</div>
              <div class="text-xs opacity-80">完成度</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold">{{ quizStats.accuracy }}%</div>
              <div class="text-xs opacity-80">正确率</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold">{{ learningStats.streakDays }}</div>
              <div class="text-xs opacity-80">连续天数</div>
            </div>
          </div>
        </div>

        <!-- Learning Progress Analysis -->
        <div class="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
          <div class="flex items-center gap-2 mb-4">
            <el-icon class="text-primary-500" :size="18"><TrendCharts /></el-icon>
            <span class="font-bold text-slate-700">学习进度分析</span>
          </div>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-sm text-slate-600">已完成章节</span>
              <span class="font-semibold text-slate-800">{{ completedCount }} / {{ totalNodes }}</span>
            </div>
            <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full bg-emerald-400 rounded-full transition-all duration-500" :style="{ width: completionRate + '%' }"></div>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-slate-500">预计剩余学习时间</span>
              <span class="font-medium text-slate-700">{{ estimatedRemainingTime }}</span>
            </div>
          </div>
        </div>

        <!-- Quiz Analysis -->
        <div class="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
              <el-icon class="text-purple-500" :size="18"><DocumentChecked /></el-icon>
              <span class="font-bold text-slate-700">测验分析</span>
            </div>
            <span class="text-xs px-2 py-1 rounded-full" :class="difficultyColorClass">{{ difficultyLevel }}</span>
          </div>
          
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div class="bg-slate-50 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-slate-800">{{ quizStats.totalQuizzes }}</div>
              <div class="text-xs text-slate-500">完成测验</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold" :class="quizStats.accuracy >= 80 ? 'text-emerald-500' : 'text-amber-500'">
                {{ quizStats.accuracy }}%
              </div>
              <div class="text-xs text-slate-500">平均正确率</div>
            </div>
          </div>

          <!-- Weak Areas -->
          <div v-if="weakAreas.length > 0" class="mt-4">
            <div class="text-sm font-medium text-slate-700 mb-2">需要加强的知识点</div>
            <div class="flex flex-wrap gap-2">
              <span v-for="area in weakAreas" :key="area.nodeId" 
                    class="px-2 py-1 bg-red-50 text-red-600 text-xs rounded-full border border-red-100">
                {{ area.name }} ({{ area.wrongCount }}错)
              </span>
            </div>
          </div>

          <!-- Strength Areas -->
          <div v-if="strengthAreas.length > 0" class="mt-4">
            <div class="text-sm font-medium text-slate-700 mb-2">掌握较好的知识点</div>
            <div class="flex flex-wrap gap-2">
              <span v-for="area in strengthAreas" :key="area.nodeId" 
                    class="px-2 py-1 bg-emerald-50 text-emerald-600 text-xs rounded-full border border-emerald-100">
                {{ area.name }} ({{ area.accuracy }}%正确)
              </span>
            </div>
          </div>
        </div>

        <!-- Study Habits -->
        <div class="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
          <div class="flex items-center gap-2 mb-4">
            <el-icon class="text-amber-500" :size="18"><Clock /></el-icon>
            <span class="font-bold text-slate-700">学习习惯</span>
          </div>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-sm text-slate-600">总学习时长</span>
              <span class="font-semibold text-slate-800">{{ formatTime(totalTime) }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-slate-600">日均学习时长</span>
              <span class="font-semibold text-slate-800">{{ formatTime(Math.round(totalTime / Math.max(learningStats.streakDays, 1))) }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-slate-600">学习最活跃时段</span>
              <span class="font-semibold text-slate-800">{{ peakStudyTime }}</span>
            </div>
          </div>
        </div>

        <!-- Recommendations -->
        <div class="bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl p-4 border border-amber-100">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-lg">💡</span>
            <span class="font-bold text-slate-700">学习建议</span>
          </div>
          <ul class="space-y-2">
            <li v-for="(tip, idx) in studyTips" :key="idx" class="flex items-start gap-2 text-sm text-slate-600">
              <span class="text-amber-500 mt-0.5">•</span>
              <span>{{ tip }}</span>
            </li>
          </ul>
        </div>

        <!-- Export Button -->
        <div class="flex justify-center pt-4">
          <button 
            @click="exportReport"
            class="px-6 py-2.5 bg-slate-800 text-white rounded-xl font-medium hover:bg-slate-700 transition-colors flex items-center gap-2"
          >
            <el-icon><Download /></el-icon>
            导出报告
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCourseStore } from '../stores/course'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { TrendCharts, Trophy, Check, Clock, Calendar, Timer, CircleCheck, Medal, DocumentChecked, Connection, Download, StarFilled } from '@element-plus/icons-vue'
import KnowledgeGraph from './KnowledgeGraph.vue'

const courseStore = useCourseStore()

const learningStats = computed(() => courseStore.learningStats)

const todayTime = computed(() => courseStore.getTodayStudyTime())
const weeklyTime = computed(() => courseStore.getWeeklyStudyTime())
const totalTime = computed(() => learningStats.value.totalStudyTime)

const totalNodes = computed(() => courseStore.courseTree.length)
const completedCount = computed(() => learningStats.value.completedNodes.length)
const completionRate = computed(() => {
  if (totalNodes.value === 0) return 0
  return Math.round((completedCount.value / totalNodes.value) * 100)
})

const last7Days = computed(() => {
  const days = []
  for (let i = 6; i >= 0; i--) {
    const date = dayjs().subtract(i, 'day')
    const dateStr = date.format('YYYY-MM-DD')
    days.push({
      date: dateStr,
      label: date.format('ddd'),
      hasStudy: (learningStats.value.dailyStudyTime[dateStr] || 0) > 0
    })
  }
  return days
})

const weeklyData = computed(() => {
  const data = []
  const maxValue = Math.max(...Object.values(learningStats.value.dailyStudyTime), 30)

  for (let i = 6; i >= 0; i--) {
    const date = dayjs().subtract(i, 'day')
    const dateStr = date.format('YYYY-MM-DD')
    const minutes = learningStats.value.dailyStudyTime[dateStr] || 0
    data.push({
      date: dateStr,
      label: date.format('dd'),
      minutes,
      percentage: maxValue > 0 ? (minutes / maxValue) * 100 : 0
    })
  }
  return data
})

const recentAchievements = computed(() => {
  const achievements = []

  // Streak achievement
  if (learningStats.value.streakDays >= 3) {
    achievements.push({
      id: 'streak-3',
      icon: '🔥',
      title: '连续学习达人',
      desc: `已连续学习 ${learningStats.value.streakDays} 天`,
      time: '进行中'
    })
  }

  // Time achievement
  if (totalTime.value >= 60) {
    achievements.push({
      id: 'time-1h',
      icon: '⏰',
      title: '学习先锋',
      desc: '累计学习超过1小时',
      time: '已达成'
    })
  }

  // Completion achievement
  if (completionRate.value >= 50) {
    achievements.push({
      id: 'complete-50',
      icon: '📚',
      title: '知识探索者',
      desc: '完成50%以上内容',
      time: '已达成'
    })
  }

  return achievements.slice(0, 3)
})

// Quiz stats - safely access quiz data with defaults
const quizStats = computed(() => {
  const wrongAnswers = courseStore.wrongAnswers || []
  const quizHistory = courseStore.quizHistory || []
  const totalQuizzes = quizHistory.length
  const totalQuestions = quizHistory.reduce((sum: number, h: any) => sum + (h.totalQuestions || 0), 0)
  const totalCorrect = quizHistory.reduce((sum: number, h: any) => sum + (h.correctCount || 0), 0)
  const accuracy = totalQuestions > 0 ? Math.round((totalCorrect / totalQuestions) * 100) : 0

  return {
    totalQuizzes,
    totalQuestions,
    totalCorrect,
    accuracy,
    wrongAnswerCount: wrongAnswers.length
  }
})

// Start wrong answer review
const startWrongAnswerReview = async () => {
  const wrongAnswers = courseStore.wrongAnswers || []
  if (wrongAnswers.length === 0) return

  // Sort by review count and time
  const toReview = wrongAnswers
    .sort((a: any, b: any) => {
      if (a.reviewCount !== b.reviewCount) {
        return a.reviewCount - b.reviewCount
      }
      return a.timestamp - b.timestamp
    })
    .slice(0, 5)

  if (toReview.length === 0) {
    ElMessage.info('暂无需要复习的错题')
    return
  }

  // Add review quiz to chat
  const title = '### 🔄 错题回顾\n根据你之前的错题，我们精选了一些题目帮助你巩固：'
  courseStore.chatHistory.push({
    type: 'ai',
    content: {
      core_answer: title,
      answer: title,
      quiz_list: toReview.map((w: any) => ({
        question: w.question,
        options: w.options,
        answer: w.options[w.correctIndex] || '',
        correct_index: w.correctIndex,
        explanation: w.explanation,
        node_id: w.nodeId,
        isReview: true
      }))
    }
  })

  // Switch to chat tab
  ElMessage.success('已生成错题回顾测验')
}

function formatTime(minutes: number): string {
  if (minutes < 60) {
    return `${minutes}分钟`
  }
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (mins === 0) {
    return `${hours}小时`
  }
  return `${hours}小时${mins}分钟`
}

// Knowledge Graph Logic
const isMobile = ref(window.innerWidth < 768)

// Learning Suggestions
const learningSuggestions = computed(() => {
  const suggestions = []
  const stats = learningStats.value
  const quizStatsValue = quizStats.value

  // Suggestion based on streak
  if (stats.streakDays < 3) {
    suggestions.push('保持每日学习习惯，连续学习3天可建立稳定的学习节奏')
  } else if (stats.streakDays >= 7) {
    suggestions.push(`太棒了！已连续学习${stats.streakDays}天，保持良好的学习习惯`)
  }

  // Suggestion based on completion rate
  if (completionRate.value < 30) {
    suggestions.push('建议每天完成1-2个章节，循序渐进地推进学习进度')
  } else if (completionRate.value >= 80) {
    suggestions.push('课程即将完成，建议复习重点内容，准备总结性测验')
  }

  // Suggestion based on quiz accuracy
  if (quizStatsValue.totalQuestions > 5 && quizStatsValue.accuracy < 60) {
    suggestions.push('测验正确率偏低，建议多花时间在错题回顾上，巩固薄弱知识点')
  } else if (quizStatsValue.accuracy >= 90 && quizStatsValue.totalQuestions > 10) {
    suggestions.push('测验表现优秀！可以尝试挑战更高难度的内容')
  }

  // Suggestion based on study time
  const avgDailyTime = totalTime.value / Math.max(stats.studyDays || 1, 1)
  if (avgDailyTime < 15) {
    suggestions.push('建议每天学习至少20-30分钟，保持知识的连贯性和记忆效果')
  }

  // Suggestion based on wrong answers
  if (quizStatsValue.wrongAnswerCount > 0) {
    suggestions.push(`你有${quizStatsValue.wrongAnswerCount}道错题待复习，定期回顾错题能有效提升学习效果`)
  }

  // Limit to 3 suggestions
  return suggestions.slice(0, 3)
})

// Handle window resize
onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

// Knowledge nodes for mini preview
const knowledgeNodes = computed(() => {
  return courseStore.courseTree.map((node: any) => ({
    id: node.node_id,
    name: node.node_name,
    completed: learningStats.value.completedNodes.includes(node.node_id),
    quizScore: node.quiz_score
  }))
})

// Get position for mini graph nodes
const getNodePosition = (index: number, total: number) => {
  const radius = 45 // percentage from center
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2
  const x = 50 + radius * Math.cos(angle)
  const y = 50 + radius * Math.sin(angle)
  return {
    left: `${x}%`,
    top: `${y}%`,
    transform: 'translate(-50%, -50%)'
  }
}

// Connection lines for mini preview
const connectionLines = computed(() => {
  const lines = []
  const center = { x: 50, y: 50 }
  for (let i = 0; i < Math.min(knowledgeNodes.value.length, 6); i++) {
    const angle = (i / 6) * 2 * Math.PI - Math.PI / 2
    const radius = 45
    const x = 50 + radius * Math.cos(angle)
    const y = 50 + radius * Math.sin(angle)
    lines.push({
      x1: `${center.x}%`,
      y1: `${center.y}%`,
      x2: `${x}%`,
      y2: `${y}%`
    })
  }
  return lines
})

// Learning Report Logic
const showKnowledgeGraphModal = ref(false)
const showLearningReport = ref(false)

// Overall score calculation (0-100)
const overallScore = computed(() => {
  const completionWeight = 0.4
  const accuracyWeight = 0.4
  const streakWeight = 0.2

  const completionScore = completionRate.value
  const accuracyScore = quizStats.value.accuracy
  const streakScore = Math.min(learningStats.value.streakDays * 10, 100)

  return Math.round(
    completionScore * completionWeight +
    accuracyScore * accuracyWeight +
    streakScore * streakWeight
  )
})

// Score evaluation text
const scoreEvaluation = computed(() => {
  const score = overallScore.value
  if (score >= 90) return '优秀！学习状态非常好'
  if (score >= 80) return '良好，继续保持'
  if (score >= 60) return '及格，还有提升空间'
  return '需要加油，建议制定学习计划'
})

// Difficulty level based on accuracy
const difficultyLevel = computed(() => {
  const accuracy = quizStats.value.accuracy
  if (accuracy >= 90) return '困难模式'
  if (accuracy >= 70) return '进阶模式'
  if (accuracy >= 50) return '标准模式'
  return '入门模式'
})

const difficultyProgress = computed(() => {
  const accuracy = quizStats.value.accuracy
  return Math.min(accuracy, 100)
})

const difficultyColorClass = computed(() => {
  const accuracy = quizStats.value.accuracy
  if (accuracy >= 90) return 'bg-red-100 text-red-600'
  if (accuracy >= 70) return 'bg-amber-100 text-amber-600'
  if (accuracy >= 50) return 'bg-blue-100 text-blue-600'
  return 'bg-emerald-100 text-emerald-600'
})

// Estimated remaining time
const estimatedRemainingTime = computed(() => {
  const remaining = totalNodes.value - completedCount.value
  const avgTimePerNode = 15 // minutes
  const totalMinutes = remaining * avgTimePerNode
  return formatTime(totalMinutes)
})

// Weak areas analysis
const weakAreas = computed(() => {
  const wrongAnswers = courseStore.wrongAnswers || []
  const nodeWrongCounts = new Map<string, { name: string; count: number }>()

  wrongAnswers.forEach((w: any) => {
    const nodeId = w.nodeId
    const nodeName = w.nodeName || '未知章节'
    const existing = nodeWrongCounts.get(nodeId)
    if (existing) {
      existing.count++
    } else {
      nodeWrongCounts.set(nodeId, { name: nodeName, count: 1 })
    }
  })

  return Array.from(nodeWrongCounts.entries())
    .map(([nodeId, data]) => ({
      nodeId,
      name: data.name,
      wrongCount: data.count
    }))
    .sort((a, b) => b.wrongCount - a.wrongCount)
    .slice(0, 5)
})

// Strength areas analysis
const strengthAreas = computed(() => {
  const quizHistory = courseStore.quizHistory || []
  const nodeScores = new Map<string, { name: string; correct: number; total: number }>()

  quizHistory.forEach((h: any) => {
    if (h.nodeId && h.nodeName) {
      const existing = nodeScores.get(h.nodeId)
      if (existing) {
        existing.correct += h.correctCount || 0
        existing.total += h.totalQuestions || 0
      } else {
        nodeScores.set(h.nodeId, {
          name: h.nodeName,
          correct: h.correctCount || 0,
          total: h.totalQuestions || 0
        })
      }
    }
  })

  return Array.from(nodeScores.entries())
    .map(([nodeId, data]) => ({
      nodeId,
      name: data.name,
      accuracy: data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0
    }))
    .filter(a => a.accuracy >= 80)
    .sort((a, b) => b.accuracy - a.accuracy)
    .slice(0, 5)
})

// Peak study time (mock data - could be enhanced with actual time tracking)
const peakStudyTime = computed(() => {
  return '晚上 20:00-22:00'
})

// Study tips based on performance
const studyTips = computed(() => {
  const tips = []

  if (completionRate.value < 50) {
    tips.push('建议每天安排固定时间学习，保持学习节奏')
  }

  if (quizStats.value.accuracy < 70) {
    tips.push('测验正确率偏低，建议多复习错题，加强理解')
  }

  if (weakAreas.value.length > 0) {
    tips.push(`重点关注薄弱知识点：${weakAreas.value.slice(0, 3).map(a => a.name).join('、')}`)
  }

  if (learningStats.value.streakDays < 3) {
    tips.push('连续学习天数较少，建议坚持每日学习，养成习惯')
  }

  if (tips.length === 0) {
    tips.push('学习状态很好！继续保持，可以尝试挑战更高难度的内容')
    tips.push('建议定期回顾已学内容，巩固记忆')
  }

  return tips
})

// Export report
const exportReport = () => {
  const report = {
    courseName: courseStore.currentCourse?.course_name,
    generatedAt: dayjs().format('YYYY-MM-DD HH:mm:ss'),
    overallScore: overallScore.value,
    completionRate: completionRate.value,
    quizAccuracy: quizStats.value.accuracy,
    totalStudyTime: totalTime.value,
    streakDays: learningStats.value.streakDays,
    weakAreas: weakAreas.value,
    strengthAreas: strengthAreas.value,
    recommendations: studyTips.value
  }

  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `学习报告_${dayjs().format('YYYYMMDD')}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)

  ElMessage.success('学习报告已导出')
}
</script>
