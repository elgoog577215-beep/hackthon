<template>
  <transition name="slide-up">
    <div v-if="visible" class="fixed bottom-5 left-1/2 -translate-x-1/2 w-[92%] max-w-4xl z-50 flex flex-col font-sans">
      
      <!-- Playlist Panel -->
      <transition name="expand">
        <div v-if="showDetails" class="glass-panel-tech mb-3 !rounded-lg !bg-white/85 flex flex-col max-h-[360px]">
            <!-- Header -->
            <div class="flex items-center px-4 py-2.5 border-b border-white/30 bg-gradient-to-r from-primary-50/60 to-primary-50/40">
                <div class="flex items-center gap-2">
                    <el-icon class="text-primary-500"><List /></el-icon>
                    <span class="text-xs font-bold text-slate-600 uppercase tracking-wider">Generation Queue</span>
                </div>
                <div class="ml-auto flex gap-3">
                     <span class="text-xxs font-bold px-2 py-0.5 bg-white rounded-full text-slate-500 shadow-sm border border-slate-100">
                        PENDING: {{ queue.filter(i => i.status === 'pending').length }}
                     </span>
                     <span class="text-xxs font-bold px-2 py-0.5 bg-emerald-50 rounded-full text-emerald-600 shadow-sm border border-emerald-100">
                        DONE: {{ queue.filter(i => i.status === 'completed').length }}
                     </span>
                </div>
            </div>
            
            <div class="px-4 py-2.5 border-b border-white/20">
                <div class="text-xxs font-bold text-slate-500 uppercase tracking-wider mb-2">Status Overview</div>
                <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    <div v-for="item in meta" :key="item.label" class="flex items-center justify-between px-2.5 py-1.5 rounded-lg border text-xxs font-semibold"
                         :class="{
                            'bg-primary-50 border-primary-100 text-primary-700': item.tone === 'primary',
                            'bg-emerald-50 border-emerald-100 text-emerald-700': item.tone === 'success',
                            'bg-amber-50 border-amber-100 text-amber-700': item.tone === 'warning',
                            'bg-red-50 border-red-100 text-red-700': item.tone === 'danger',
                            'bg-slate-50 border-slate-100 text-slate-600': !item.tone || item.tone === 'muted'
                         }"
                    >
                        <span class="truncate">{{ item.label }}</span>
                        <span class="ml-2 text-slate-500 truncate">{{ item.value }}</span>
                    </div>
                </div>
            </div>
            
            <div class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1.5">
                <div v-if="queue.length === 0" class="flex flex-col items-center justify-center h-32 text-slate-400 gap-2">
                    <el-icon class="text-2xl opacity-50"><FolderChecked /></el-icon>
                    <span class="text-xs">Queue is empty</span>
                </div>
                
                <div v-for="(item, idx) in queue" :key="item.uuid" 
                     class="group flex items-center gap-3 p-2 rounded-xl transition-all border border-transparent relative overflow-hidden"
                     :class="[
                        item.status === 'running' ? 'bg-primary-50/80 border-primary-100' : 'hover:bg-white/60',
                        item.status === 'completed' ? 'opacity-70 grayscale-[0.5]' : '',
                        item.status === 'error' ? 'bg-red-50/80 border-red-100' : ''
                     ]"
                >
                    <!-- Active Indicator -->
                    <div v-if="item.status === 'running'" class="absolute left-0 top-0 bottom-0 w-1 bg-primary-500"></div>

                    <!-- Status Icon -->
                    <div class="w-7 h-7 flex items-center justify-center rounded-lg shrink-0 text-sm transition-colors"
                         :class="{
                             'bg-emerald-100 text-emerald-600': item.status === 'completed',
                             'bg-primary-500 text-white shadow-md shadow-primary-500/30': item.status === 'running',
                             'bg-slate-100 text-slate-400': item.status === 'pending',
                             'bg-red-100 text-red-600': item.status === 'error'
                         }"
                    >
                        <el-icon v-if="item.status === 'completed'"><Check /></el-icon>
                        <el-icon v-else-if="item.status === 'running'" class="animate-spin"><Loading /></el-icon>
                        <el-icon v-else-if="item.status === 'error'"><Close /></el-icon>
                        <span v-else class="font-mono text-xs">{{ idx + 1 }}</span>
                    </div>
                    
                    <!-- Content -->
                    <div class="flex-1 min-w-0 flex flex-col justify-center">
                        <div class="text-sm font-bold text-slate-700 truncate leading-tight mb-0.5"
                             :class="{'text-primary-700': item.status === 'running'}">
                            {{ item.title }}
                        </div>
                        <div class="text-xxs text-slate-500 truncate flex items-center gap-2">
                            <span class="uppercase tracking-wider font-bold opacity-70 bg-slate-100 px-1.5 rounded">{{ item.type }}</span>
                            <span v-if="item.errorMsg" class="text-red-500">{{ item.errorMsg }}</span>
                        </div>
                    </div>
                    
                    <!-- Running Animation -->
                    <div v-if="item.status === 'running'" class="flex gap-0.5 items-end h-4 mr-2">
                        <div class="w-1 bg-primary-400 animate-[music-bar_0.6s_ease-in-out_infinite] h-2"></div>
                        <div class="w-1 bg-primary-400 animate-[music-bar_0.8s_ease-in-out_infinite_0.1s] h-4"></div>
                        <div class="w-1 bg-primary-400 animate-[music-bar_0.5s_ease-in-out_infinite_0.2s] h-3"></div>
                    </div>
                </div>
            </div>
        </div>
      </transition>

      <!-- Main Player Bar -->
      <div 
        @click="$emit('click')"
        class="glass-noise h-[64px] bg-white/80 backdrop-blur-3xl rounded-xl border border-white/60 shadow-[0_6px_24px_rgba(0,0,0,0.08)] flex items-center px-2 pr-4 relative overflow-visible group hover:bg-white/90 transition-all z-50 select-none cursor-pointer"
      >
        
        <!-- Glow Effect -->
        <div v-if="status === 'generating'" class="absolute inset-0 rounded-xl ring-2 ring-primary-500/20 animate-pulse pointer-events-none"></div>

        <!-- Album Art / Progress Circle -->
        <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-white shadow-lg shadow-primary-500/30 ml-2 relative overflow-hidden shrink-0 group-hover:scale-105 transition-transform duration-300">
            <div v-if="status === 'generating'" class="absolute inset-0 bg-white/20 animate-pulse"></div>
            
            <!-- Center Icon -->
            <el-icon class="text-xl relative z-10" :class="{'animate-spin': status === 'generating'}"><Loading /></el-icon>
            
            <!-- Circular Progress -->
            <svg class="absolute inset-0 w-full h-full -rotate-90 pointer-events-none z-0" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="10" />
                <circle cx="50" cy="50" r="45" fill="none" stroke="white" stroke-width="10" stroke-dasharray="283" :stroke-dashoffset="283 - (283 * progress / 100)" class="transition-all duration-300" />
            </svg>
        </div>

        <!-- Info Area -->
        <div class="flex-1 ml-4 min-w-0 flex flex-col justify-center h-full py-1">
             <div class="flex items-center gap-2 mb-0.5">
                 <span class="px-2 py-0.5 rounded-full text-xxs font-black uppercase tracking-widest shadow-sm border"
                    :class="{
                        'bg-primary-500 border-primary-400 text-white': status === 'generating',
                        'bg-amber-400 border-amber-300 text-white': status === 'paused',
                        'bg-slate-100 border-slate-200 text-slate-500': status === 'idle',
                        'bg-red-500 border-red-400 text-white': status === 'error'
                    }"
                 >
                     {{ status === 'generating' ? 'PLAYING' : status }}
                 </span>
                 <span class="text-xxs font-bold text-slate-400">QUEUE: {{ queue.length - queue.filter(i => i.status === 'completed').length }} LEFT</span>
             </div>
             
             <div class="flex items-center">
                 <div class="text-sm font-bold text-slate-800 truncate">{{ currentTask || 'Waiting for tasks...' }}</div>
             </div>
             <div v-if="hint" class="text-xxs text-slate-500 truncate mt-0.5">{{ hint }}</div>
             
             <!-- Mini Linear Progress -->
             <div class="mt-1 h-1 bg-slate-200/60 rounded-full overflow-hidden w-full max-w-56">
                 <div class="h-full bg-gradient-to-r from-primary-500 to-primary-400 transition-all duration-300" :style="{ width: progress + '%' }"></div>
             </div>
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-2 ml-4" @click.stop>
            <div class="h-8 w-px bg-slate-200 mx-1"></div>
            
            <button @click="toggleDetails" 
                class="glass-icon-btn"
                :class="{'!bg-primary-50 !border-primary-100 !text-primary-600': showDetails}"
            >
                <el-icon :class="{'rotate-180': showDetails}" class="transition-transform duration-300"><ArrowUp /></el-icon>
            </button>
            
            <button @click="$emit('close')" 
                class="glass-icon-btn danger group/stop"
            >
                <el-icon class="group-hover/stop:scale-110 transition-transform"><CircleClose /></el-icon>
            </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Loading, ArrowUp, CircleClose, Check, Close, List, FolderChecked } from '@element-plus/icons-vue'

// Import QueueItem type locally or define it
interface QueueItem {
    uuid: string
    courseId: string
    type: 'structure' | 'content' | 'subchapter'
    targetNodeId: string
    title: string
    status: 'pending' | 'running' | 'completed' | 'error'
    errorMsg?: string
}

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

defineEmits(['close', 'click'])

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
  transform: translate(-50%, 100%);
  opacity: 0;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.4s cubic-bezier(0.19, 1, 0.22, 1);
  max-height: 400px;
  opacity: 1;
  transform: translateY(0);
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(20px);
}

@keyframes music-bar {
    0%, 100% { height: 20%; }
    50% { height: 100%; }
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
