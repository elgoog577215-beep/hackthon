<template>
  <transition name="slide-up">
    <div v-if="visible" class="fixed bottom-6 left-1/2 -translate-x-1/2 w-[90%] max-w-2xl z-50 flex flex-col font-sans">
      
      <!-- Details Panel (Simplified) -->
      <transition name="expand">
        <div v-if="showDetails" class="mb-3 bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-slate-200/50 overflow-hidden flex flex-col max-h-[300px]">
            <!-- Header -->
            <div class="flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50/50">
                <span class="text-xs font-bold text-slate-500 uppercase tracking-wider">任务队列</span>
                <span class="text-xs font-medium text-slate-400">
                    剩余 {{ queue.filter(i => i.status !== 'completed' && i.status !== 'error').length }} 项
                </span>
            </div>
            
            <div class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
                <div v-if="queue.filter(i => i.status === 'running' || i.status === 'pending').length === 0" class="flex flex-col items-center justify-center h-24 text-slate-400 gap-2">
                    <span class="text-sm">队列空闲</span>
                </div>
                
                <div v-for="item in queue.filter(i => i.status === 'running' || i.status === 'pending')" :key="item.uuid" 
                     class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-sm"
                     :class="[
                        item.status === 'running' ? 'bg-blue-50 text-blue-700' : 'text-slate-600'
                     ]"
                >
                    <!-- Status Icon -->
                    <div class="w-4 h-4 flex items-center justify-center shrink-0">
                        <el-icon v-if="item.status === 'running'" class="animate-spin text-blue-500"><Loading /></el-icon>
                        <div v-else class="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
                    </div>
                    
                    <span class="truncate flex-1 font-medium">{{ item.title }}</span>
                    
                    <span class="text-xs opacity-70 whitespace-nowrap" v-if="item.status === 'running'">进行中...</span>
                </div>
            </div>
        </div>
      </transition>

      <!-- Main Status Bar -->
      <div 
        @click="toggleDetails"
        class="h-14 bg-white shadow-[0_8px_30px_rgba(0,0,0,0.12)] rounded-full border border-slate-100 flex items-center px-2 relative overflow-hidden cursor-pointer hover:shadow-[0_8px_35px_rgba(0,0,0,0.16)] transition-all duration-300 group"
      >
        <!-- Progress Background -->
        <div class="absolute bottom-0 left-0 h-0.5 bg-slate-100 w-full">
            <div class="h-full bg-blue-500 transition-all duration-500 ease-out" :style="{ width: progress + '%' }"></div>
        </div>

        <!-- Status Icon / Spinner -->
        <div class="w-10 h-10 rounded-full flex items-center justify-center shrink-0 ml-1"
             :class="{
                'bg-blue-50 text-blue-600': status === 'generating',
                'bg-amber-50 text-amber-600': status === 'paused',
                'bg-slate-50 text-slate-400': status === 'idle',
                'bg-red-50 text-red-600': status === 'error'
             }"
        >
            <el-icon v-if="status === 'generating'" class="text-lg animate-spin"><Loading /></el-icon>
            <el-icon v-else-if="status === 'paused'" class="text-lg"><VideoPause /></el-icon>
            <el-icon v-else-if="status === 'error'" class="text-lg"><Close /></el-icon>
            <el-icon v-else class="text-lg"><Check /></el-icon>
        </div>

        <!-- Info Area -->
        <div class="flex-1 ml-3 min-w-0 flex flex-col justify-center">
             <div class="flex items-center gap-2">
                 <span class="text-sm font-bold text-slate-800 truncate">
                    {{ currentTask || (status === 'idle' ? '准备就绪' : '处理中...') }}
                 </span>
             </div>
             <div class="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                 <span v-if="status === 'generating'" class="flex items-center gap-1 text-blue-600 font-medium">
                    正在生成
                 </span>
                 <span v-else-if="status === 'paused'" class="text-amber-600 font-medium">已暂停</span>
                 <span v-else-if="status === 'error'" class="text-red-600 font-medium">发生错误</span>
                 <span v-else>等待任务</span>
                 
                 <span class="w-1 h-1 rounded-full bg-slate-300"></span>
                 <span>{{ progress }}%</span>
                 
                 <template v-if="queue.length > 0">
                    <span class="w-1 h-1 rounded-full bg-slate-300"></span>
                    <span>剩余 {{ queue.length - queue.filter(i => i.status === 'completed').length }} 项</span>
                 </template>
             </div>
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-1 mr-2" @click.stop>
            <button v-if="status === 'generating' || status === 'paused'" @click.stop="$emit('toggle-pause')" 
                class="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
                :title="status === 'generating' ? '暂停' : '继续'"
            >
                <el-icon v-if="status === 'generating'"><VideoPause /></el-icon>
                <el-icon v-else><VideoPlay /></el-icon>
            </button>

            <button @click.stop="toggleDetails" 
                class="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
            >
                <el-icon :class="{'rotate-180': showDetails}" class="transition-transform duration-300"><ArrowUp /></el-icon>
            </button>
            
            <button v-if="status === 'generating'" @click.stop="$emit('close')" 
                class="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                title="停止生成"
            >
                <el-icon><CircleClose /></el-icon>
            </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Loading, ArrowUp, CircleClose, Check, Close, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { type QueueItem } from '../stores/course'

const props = defineProps<{
  visible: boolean
  currentTask: string | null
  logs: string[]
  queue: QueueItem[]
  progress: number
  status: 'idle' | 'generating' | 'paused' | 'error'
  meta: { label: string; value: string; tone?: 'primary' | 'success' | 'warning' | 'danger' | 'muted' }[]
  hint?: string | null
}>()

// Use props to avoid "declared but never read" error
// In Vue 3 <script setup>, defineProps return value is sometimes needed for template type inference
// or to be explicit about usage, even if used in template.
// However, the linter complains it's unused in the script block.
// A simple workaround is to log it in development or just ignore the line.
// But since we can't easily add ignore comments without risk, let's just use it in a dummy way.
void props

const emit = defineEmits(['close', 'click', 'toggle-pause', 'retry-item'])

const showDetails = ref(false)
const toggleDetails = () => {
    showDetails.value = !showDetails.value
}
</script>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.5s cubic-bezier(0.19, 1, 0.22, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translate(-50%, 150%);
  opacity: 0;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);
  max-height: 300px;
  opacity: 1;
  transform: translateY(0) scale(1);
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

/* Custom Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
    width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.2);
}
</style>
