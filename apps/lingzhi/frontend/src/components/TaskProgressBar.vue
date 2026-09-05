<template>
  <div class="task-progress-bar">
    <div class="progress-header">
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium text-slate-600">{{ progressText }}</span>
        <span v-if="phaseProgress" class="text-xs text-slate-400">
          ({{ phaseProgress }})
        </span>
      </div>
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
    
    <div v-if="currentPhase" class="phase-indicator">
      <div class="phase-badge" :class="phaseClass">
        {{ currentPhase }}
      </div>
    </div>

    <div v-if="currentNodes && currentNodes.length > 0" class="current-nodes">
      <div 
        v-for="(node, idx) in currentNodes" 
        :key="idx"
        class="current-node-item"
      >
        <div class="node-action-badge">
          {{ node.action }}
        </div>
        <el-icon :size="10" class="text-slate-400"><Document /></el-icon>
        <span class="text-xs text-slate-600 truncate flex-1">{{ node.node_name || node.name }}</span>
        <span v-if="node.type === 'subnodes'" class="text-xs text-violet-500">📚</span>
        <span v-else class="text-xs text-primary-500">📝</span>
      </div>
    </div>
    
    <div v-else-if="currentNode" class="current-node">
      <el-icon :size="10" class="text-slate-400"><Document /></el-icon>
      <span class="text-xs text-slate-500 truncate">{{ currentNode }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'

interface CurrentNode {
  name: string
  action: string
  type: string
  node_name?: string
}

interface Props {
  progress: number
  currentNode?: string
  currentNodes?: CurrentNode[]
  currentPhase?: string
  phaseProgress?: string
  status?: string
  estimatedTime?: number
}

const props = withDefaults(defineProps<Props>(), {
  progress: 0,
  currentNode: '',
  currentNodes: () => [],
  currentPhase: '',
  phaseProgress: '',
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

const phaseClass = computed(() => {
  if (props.currentPhase?.includes('结构')) return 'phase-structure'
  if (props.currentPhase?.includes('正文')) return 'phase-content'
  return 'phase-default'
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

.phase-indicator {
  @apply mt-2;
}

.phase-badge {
  @apply inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium;
}

.phase-structure {
  @apply bg-violet-100 text-violet-700;
}

.phase-content {
  @apply bg-primary-100 text-primary-700;
}

.phase-default {
  @apply bg-slate-100 text-slate-600;
}

.current-nodes {
  @apply mt-2 flex flex-col gap-1;
}

.current-node-item {
  @apply flex items-center gap-1.5 px-2 py-1 bg-slate-50 rounded-md;
}

.node-action-badge {
  @apply text-xs px-1.5 py-0.5 rounded bg-white text-slate-500 border border-slate-200;
}

.current-node {
  @apply flex items-center gap-1 mt-1.5;
}
</style>
