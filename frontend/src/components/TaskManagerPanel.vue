<template>
  <div class="task-manager-panel">
    <div class="panel-header">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-violet-500 flex items-center justify-center">
          <el-icon :size="16" class="text-white"><List /></el-icon>
        </div>
        <div>
          <h3 class="font-semibold text-slate-800 text-sm">任务管理</h3>
          <p class="text-xs text-slate-400">{{ activeTasksCount }} 个活跃任务</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div 
          class="w-2 h-2 rounded-full transition-colors"
          :class="connectionStatus === 'connected' ? 'bg-green-500' : connectionStatus === 'connecting' ? 'bg-amber-500 animate-pulse' : 'bg-red-500'"
        ></div>
        <span class="text-xs text-slate-400">{{ connectionStatusText }}</span>
      </div>
    </div>

    <div class="panel-content">
      <div v-if="tasks.length === 0" class="empty-state">
        <div class="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-3">
          <el-icon :size="24" class="text-slate-400"><Document /></el-icon>
        </div>
        <p class="text-sm text-slate-500">暂无活跃任务</p>
        <p class="text-xs text-slate-400 mt-1">创建新课程开始生成</p>
      </div>

      <TransitionGroup name="task-list" tag="div" class="task-list">
        <div 
          v-for="task in sortedTasks" 
          :key="task.id"
          class="task-item"
          :class="{
            'task-running': task.status === 'running',
            'task-paused': task.status === 'paused',
            'task-error': task.status === 'error',
            'task-completed': task.status === 'completed'
          }"
        >
          <div class="task-header">
            <div class="flex items-center gap-2 flex-1 min-w-0">
              <div 
                class="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
                :class="statusBgClass(task.status)"
              >
                <el-icon :size="12" :class="statusTextClass(task.status)">
                  <component :is="statusIcon(task.status)" />
                </el-icon>
              </div>
              <div class="min-w-0">
                <div class="font-medium text-slate-700 text-sm truncate">{{ task.courseName }}</div>
                <div class="text-xs text-slate-400 truncate">{{ task.currentStep || statusText(task.status) }}</div>
              </div>
            </div>
            
            <div class="flex items-center gap-1">
              <button 
                v-if="task.status === 'running'"
                class="control-btn"
                @click="handlePause(task.id)"
                title="暂停"
              >
                <el-icon :size="14"><VideoPause /></el-icon>
              </button>
              <button 
                v-if="task.status === 'paused'"
                class="control-btn control-btn-play"
                @click="handleResume(task.id)"
                title="继续"
              >
                <el-icon :size="14"><VideoPlay /></el-icon>
              </button>
              <button 
                v-if="task.status === 'error'"
                class="control-btn control-btn-retry"
                @click="handleRetry(task.id)"
                title="重试"
              >
                <el-icon :size="14"><RefreshRight /></el-icon>
              </button>
              <button 
                v-if="['running', 'paused', 'pending'].includes(task.status)"
                class="control-btn control-btn-cancel"
                @click="handleCancel(task.id)"
                title="取消"
              >
                <el-icon :size="14"><Close /></el-icon>
              </button>
              <button 
                v-if="task.status === 'completed'"
                class="control-btn control-btn-check"
                @click="handleViewCourse(task.id)"
                title="查看课程"
              >
                <el-icon :size="14"><View /></el-icon>
              </button>
            </div>
          </div>

          <TaskProgressBar 
            v-if="task.status !== 'completed'"
            :progress="task.progress"
            :current-node="task.currentStep"
            :status="task.status"
            :estimated-time="taskProgress[task.id]?.estimatedTimeRemaining"
          />

          <div v-if="task.logs && task.logs.length > 0" class="task-logs">
            <div 
              v-for="(log, idx) in task.logs.slice(-3)" 
              :key="idx"
              class="log-item"
            >
              {{ log }}
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  List, Document, VideoPause, VideoPlay, RefreshRight, Close, View,
  Loading, CircleCheck, CircleClose, Clock
} from '@element-plus/icons-vue'
import { useGenerationStore } from '../stores/generation'
import type { Task } from '../stores/types'
import { useTaskWebSocket } from '../composables/useTaskWebSocket'
import TaskProgressBar from './TaskProgressBar.vue'

const router = useRouter()
const genStore = useGenerationStore()
const { 
  connectionStatus, 
  pauseTask: wsPauseTask, 
  resumeTask: wsResumeTask, 
  cancelTask: wsCancelTask 
} = useTaskWebSocket()

const tasks = computed((): Task[] => {
  return Array.from(genStore.tasks.values())
})

const taskProgress = computed(() => genStore.taskProgress || {})

const activeTasksCount = computed(() => {
  return tasks.value.filter(t => ['pending', 'running', 'paused'].includes(t.status)).length
})

const sortedTasks = computed(() => {
  const statusPriority: Record<string, number> = {
    running: 0,
    pending: 1,
    paused: 2,
    error: 3,
    completed: 4,
    idle: 5
  }
  
  return [...tasks.value].sort((a, b) => {
    return (statusPriority[a.status] || 5) - (statusPriority[b.status] || 5)
  })
})

const connectionStatusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'error': return '连接错误'
    default: return '未连接'
  }
})

const statusIcon = (status: string) => {
  switch (status) {
    case 'running': return Loading
    case 'completed': return CircleCheck
    case 'error': return CircleClose
    case 'paused': return VideoPause
    case 'pending': return Clock
    default: return Document
  }
}

const statusBgClass = (status: string) => {
  switch (status) {
    case 'running': return 'bg-primary-100'
    case 'completed': return 'bg-green-100'
    case 'error': return 'bg-red-100'
    case 'paused': return 'bg-amber-100'
    default: return 'bg-slate-100'
  }
}

const statusTextClass = (status: string) => {
  switch (status) {
    case 'running': return 'text-primary-500'
    case 'completed': return 'text-green-500'
    case 'error': return 'text-red-500'
    case 'paused': return 'text-amber-500'
    default: return 'text-slate-500'
  }
}

const statusText = (status: string) => {
  switch (status) {
    case 'running': return '正在生成...'
    case 'completed': return '生成完成'
    case 'error': return '生成失败'
    case 'paused': return '已暂停'
    case 'pending': return '等待中...'
    default: return '空闲'
  }
}

const handlePause = (courseId: string) => {
  wsPauseTask(courseId)
}

const handleResume = (courseId: string) => {
  wsResumeTask(courseId)
}

const handleCancel = async (courseId: string) => {
  try {
    await ElMessageBox.confirm(
      '确定要取消此任务吗？已生成的内容将被保留。',
      '取消任务',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    wsCancelTask(courseId)
  } catch {
    // User cancelled
  }
}

const handleRetry = (courseId: string) => {
  wsResumeTask(courseId)
  ElMessage.info('正在重试任务...')
}

const handleViewCourse = (courseId: string) => {
  router.push(`/course/${courseId}`)
}
</script>

<style scoped>
.task-manager-panel {
  @apply flex flex-col h-full;
}

.panel-header {
  @apply flex items-center justify-between p-3 border-b border-slate-100 bg-white/50;
}

.panel-content {
  @apply flex-1 overflow-auto p-2;
}

.empty-state {
  @apply flex flex-col items-center justify-center py-8 text-center;
}

.task-list {
  @apply flex flex-col gap-2;
}

.task-item {
  @apply bg-white rounded-xl border border-slate-100 p-3 transition-all duration-200;
}

.task-item:hover {
  @apply shadow-md border-slate-200;
}

.task-item.task-running {
  @apply border-primary-200 bg-primary-50/30;
}

.task-item.task-paused {
  @apply border-amber-200 bg-amber-50/30;
}

.task-item.task-error {
  @apply border-red-200 bg-red-50/30;
}

.task-item.task-completed {
  @apply border-green-200 bg-green-50/30;
}

.task-header {
  @apply flex items-center justify-between gap-2;
}

.control-btn {
  @apply w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-all;
}

.control-btn-play {
  @apply hover:bg-green-50 hover:text-green-500;
}

.control-btn-retry {
  @apply hover:bg-amber-50 hover:text-amber-500;
}

.control-btn-cancel {
  @apply hover:bg-red-50 hover:text-red-500;
}

.control-btn-check {
  @apply hover:bg-primary-50 hover:text-primary-500;
}

.task-logs {
  @apply mt-2 p-2 bg-slate-50 rounded-lg text-xs text-slate-500 font-mono max-h-20 overflow-auto;
}

.log-item {
  @apply py-0.5 truncate;
}

.task-list-enter-active,
.task-list-leave-active {
  transition: all 0.3s ease;
}

.task-list-enter-from,
.task-list-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}
</style>
