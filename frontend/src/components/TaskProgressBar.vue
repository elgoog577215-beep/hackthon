<template>
  <div class="task-progress-bar">
    <div class="progress-header">
      <span class="text-xs font-medium text-slate-600">{{ progressText }}</span>
      <span v-if="estimatedTime" class="text-xs text-slate-400">
        预计剩余 {{ formatTime(estimatedTime) }}
      </span>
    </div>
    
    <div class="progress-track">
      <div 
        class="progress-fill"
        :class="progressClass"
        :style="{ width: `${progress}%` }"
      >
        <div v-if="status === 'running'" class="progress-shimmer"></div>
      </div>
    </div>
    
    <div v-if="currentNode" class="current-node">
      <el-icon :size="10" class="text-slate-400"><Document /></el-icon>
      <span class="text-xs text-slate-500 truncate">{{ currentNode }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'

interface Props {
  progress: number
  currentNode?: string
  status?: string
  estimatedTime?: number
}

const props = withDefaults(defineProps<Props>(), {
  progress: 0,
  currentNode: '',
  status: 'pending',
  estimatedTime: 0
})

const progressText = computed(() => {
  return `${Math.round(props.progress)}%`
})

const progressClass = computed(() => {
  switch (props.status) {
    case 'running': return 'progress-running'
    case 'paused': return 'progress-paused'
    case 'error': return 'progress-error'
    case 'completed': return 'progress-completed'
    default: return 'progress-pending'
  }
})

const formatTime = (seconds: number): string => {
  if (seconds <= 0) return '--'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${Math.round(seconds / 3600)}小时`
}
</script>

<style scoped>
.task-progress-bar {
  @apply mt-2;
}

.progress-header {
  @apply flex items-center justify-between mb-1;
}

.progress-track {
  @apply h-1.5 bg-slate-100 rounded-full overflow-hidden relative;
}

.progress-fill {
  @apply h-full rounded-full transition-all duration-300 relative overflow-hidden;
}

.progress-running {
  @apply bg-gradient-to-r from-primary-500 to-violet-500;
}

.progress-paused {
  @apply bg-amber-400;
}

.progress-error {
  @apply bg-red-400;
}

.progress-completed {
  @apply bg-green-400;
}

.progress-pending {
  @apply bg-slate-300;
}

.progress-shimmer {
  @apply absolute inset-0;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.4),
    transparent
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.current-node {
  @apply flex items-center gap-1 mt-1.5;
}
</style>
