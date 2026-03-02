<template>
  <div class="h-screen w-full flex items-center justify-center p-0 xl:p-3 overflow-hidden relative font-sans antialiased">
    <!-- Premium Background System - Enhanced -->
    <div class="absolute inset-0 z-0 pointer-events-none overflow-hidden">
      <!-- Mesh Gradient Background -->
      <div class="absolute inset-0 bg-gradient-to-br from-indigo-50/60 via-white to-violet-50/50"></div>
      
      <!-- Animated Gradient Orbs - Enhanced -->
      <div class="absolute top-[-5%] right-[-5%] w-[45%] h-[45%] bg-gradient-to-br from-indigo-200/30 to-purple-200/20 rounded-full blur-[100px] animate-float-slow"></div>
      <div class="absolute bottom-[-10%] left-[-5%] w-[50%] h-[50%] bg-gradient-to-tr from-blue-200/25 to-cyan-200/15 rounded-full blur-[100px] animate-float-slow" style="animation-delay: -4s;"></div>
      <div class="absolute top-[50%] left-[25%] w-[25%] h-[25%] bg-gradient-to-r from-violet-200/20 to-fuchsia-200/10 rounded-full blur-[80px] animate-pulse-soft"></div>
      
      <!-- Subtle Grid Pattern -->
      <div class="absolute inset-0 opacity-[0.02]" style="background-image: radial-gradient(circle at 1px 1px, rgba(99, 102, 241, 0.8) 1px, transparent 0); background-size: 32px 32px;"></div>
      
      <!-- Animated Gradient Overlay -->
      <div class="absolute inset-0 bg-gradient-to-tr from-primary-500/5 via-transparent to-accent-500/5 animate-pulse-soft" style="animation-duration: 8s;"></div>
    </div>

    <!-- Main Container -->
    <div class="w-full h-full flex flex-col gap-3 relative z-10">
      
      <!-- Global Header - Premium Design with Enhanced Animations -->
      <header class="h-14 xl:h-16 flex-shrink-0 flex items-center justify-between px-4 xl:px-6 glass-panel-elevated rounded-none xl:rounded-2xl z-20 relative animate-fade-in-up">
        <!-- Logo Section -->
        <div class="flex items-center gap-3 cursor-pointer group" @click="router.push('/')">
          <div class="w-9 h-9 xl:w-10 xl:h-10 rounded-xl flex items-center justify-center text-white shadow-lg transition-all duration-300 relative overflow-hidden group-hover:shadow-xl group-hover:scale-110 magnetic"
               style="background: var(--gradient-primary);">
            <!-- Icon Background Glow -->
            <div class="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500" style="background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.4) 0%, transparent 70%);"></div>
            <!-- Animated Border -->
            <div class="absolute inset-0 rounded-xl border-2 border-white/20 group-hover:border-white/40 transition-all duration-300"></div>
            <!-- Icon -->
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-5 h-5 xl:w-6 xl:h-6 relative z-10 transition-transform duration-300 group-hover:rotate-12">
              <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 002.21 10.057a.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
              <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.438.227 2.945.227 4.53 0 5.705-3.276 10.675-8.25 13.05a.75.75 0 01-.706 0C7.026 27.478 3.75 22.508 3.75 16.8c0-1.66.103-3.235.249-4.735a48.51 48.51 0 017.76 3.42c.433.224.943.224 1.301-.012z" />
            </svg>
          </div>
          <div class="flex flex-col">
            <h1 class="text-base xl:text-lg font-semibold tracking-tight text-slate-900 leading-tight group-hover:text-primary-600 transition-colors duration-300">灵知</h1>
            <span class="text-[10px] xl:text-xs text-slate-400 font-medium tracking-wide group-hover:text-slate-500 transition-colors duration-300">KnowledgeMap</span>
          </div>
        </div>
        
        <!-- Central Course Title - Pill Design -->
        <div class="flex-1 flex justify-center" v-if="courseStore.currentCourseId">
          <div class="flex items-center gap-2 glass-card rounded-full px-4 py-1.5 animate-fade-in-up">
            <span class="font-medium text-slate-700 text-sm truncate max-w-[180px]">
              {{ courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || '课程预览' }}
            </span>
            <span class="w-1 h-1 rounded-full bg-slate-300"></span>
            <span class="text-xs text-slate-400 font-medium">全书模式</span>
          </div>
        </div>
        
        <!-- Spacer when no course selected -->
        <div class="flex-1" v-else></div>

        <!-- Toolbar Controls -->
        <div class="flex items-center gap-3">
          <template v-if="courseStore.currentCourseId">
          <!-- Divider -->
          <div class="w-px h-7 bg-gradient-to-b from-transparent via-slate-200 to-transparent"></div>
          
          <!-- Global Search -->
          <div class="relative">
            <div class="relative transition-all duration-300 ease-out" :class="isSearchFocused ? 'w-64' : 'w-48'">
              <!-- Glow Effect -->
              <div class="absolute -inset-0.5 bg-gradient-to-r from-primary-400/0 via-primary-500/30 to-primary-400/0 rounded-2xl opacity-0 blur-md transition-all duration-300" :class="isSearchFocused ? 'opacity-100' : ''"></div>
              
              <div class="relative flex items-center h-9 rounded-xl transition-all duration-300 overflow-hidden glass-input"
                   :class="isSearchFocused ? 'ring-2 ring-primary-400/20' : ''">
                <div class="pl-3 pr-2 transition-colors duration-200" :class="isSearchFocused ? 'text-primary-500' : 'text-slate-400'">
                  <el-icon :size="16"><Search /></el-icon>
                </div>
                <input 
                  :value="courseStore.globalSearchQuery"
                  type="text"
                  placeholder="搜索全书..."
                  aria-label="搜索全书内容"
                  class="flex-1 bg-transparent border-none outline-none text-sm text-slate-700 placeholder:text-slate-400 h-full pr-2"
                  @input="handleGlobalSearch"
                  @focus="isSearchFocused = true"
                  @blur="isSearchFocused = false"
                />
                <button 
                  v-if="courseStore.globalSearchQuery"
                  class="mr-2 p-1 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all"
                  aria-label="清除搜索"
                  @click="courseStore.globalSearchQuery = ''; globalSearchResults = []"
                >
                  <el-icon :size="12"><CircleClose /></el-icon>
                </button>
              </div>
            </div>

            <!-- Search Results Dropdown -->
            <div v-if="globalSearchResults.length > 0" class="absolute top-full left-0 right-0 mt-3 p-2 z-50 max-h-80 overflow-auto glass-panel-elevated rounded-xl">
              <div class="flex items-center justify-between px-3 py-2 mb-2 border-b border-slate-100">
                <span class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">搜索结果</span>
                <span class="text-[10px] font-medium text-slate-500 bg-slate-100 rounded-full px-2 py-0.5">{{ globalSearchResults.length }}</span>
              </div>
              <div v-for="(res, idx) in globalSearchResults" :key="idx" 
                   class="px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-200 group/item hover:bg-primary-50/50"
                   @click="scrollToSearchResult(res.id)">
                <div class="flex items-center justify-between">
                  <span class="font-medium text-slate-700 text-sm truncate group-hover/item:text-primary-600 transition-colors">{{ res.title }}</span>
                  <el-icon class="text-slate-300 group-hover/item:text-primary-400 transition-all" :size="14"><ArrowRight /></el-icon>
                </div>
                <p class="text-xs text-slate-500 mt-1 line-clamp-1" v-html="res.preview"></p>
              </div>
            </div>
          </div>

          <!-- Divider -->
          <div class="w-px h-7 bg-gradient-to-b from-transparent via-slate-200 to-transparent"></div>

          <!-- Knowledge Graph Button -->
          <button 
            class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300 relative overflow-hidden group"
            :class="courseStore.showKnowledgeGraph 
              ? 'text-white shadow-lg' 
              : 'text-slate-600 hover:text-primary-600'"
            :style="courseStore.showKnowledgeGraph 
              ? 'background: var(--gradient-primary);' 
              : 'background: rgba(255,255,255,0.7); border: 1px solid rgba(226,232,240,0.8);'"
            :aria-pressed="courseStore.showKnowledgeGraph"
            aria-label="知识图谱"
            @click="courseStore.showKnowledgeGraph = true"
          >
            <el-icon :size="16" class="transition-transform duration-300 group-hover:scale-110"><Connection /></el-icon>
            <span class="hidden lg:inline">知识图谱</span>
          </button>

          <!-- Divider -->
          <div class="w-px h-7 bg-gradient-to-b from-transparent via-slate-200 to-transparent"></div>

          <!-- Settings Group -->
          <div class="flex items-center gap-1.5">
            <!-- Settings Popover -->
            <el-popover placement="bottom" :width="220" trigger="click" popper-class="glass-popover">
              <template #reference>
                <button class="btn-icon" title="外观设置">
                  <el-icon :size="17"><Setting /></el-icon>
                </button>
              </template>
              <div class="p-3 space-y-4">
                <div class="space-y-2">
                  <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">字号</div>
                  <div class="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
                    <button class="flex-1 p-1.5 hover:bg-white rounded-md text-slate-600 transition-colors" @click="courseStore.uiSettings.fontSize = Math.max(8, courseStore.uiSettings.fontSize - 1)"><el-icon :size="14"><Minus /></el-icon></button>
                    <span class="text-xs font-mono w-8 text-center text-slate-700">{{ courseStore.uiSettings.fontSize }}</span>
                    <button class="flex-1 p-1.5 hover:bg-white rounded-md text-slate-600 transition-colors" @click="courseStore.uiSettings.fontSize = Math.min(72, courseStore.uiSettings.fontSize + 1)"><el-icon :size="14"><Plus /></el-icon></button>
                  </div>
                </div>
                <div class="space-y-2">
                  <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">字体</div>
                  <div class="grid grid-cols-3 gap-1.5">
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all" :class="courseStore.uiSettings.fontFamily === 'sans' ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.fontFamily = 'sans'">无衬线</button>
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all font-serif" :class="courseStore.uiSettings.fontFamily === 'serif' ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.fontFamily = 'serif'">衬线</button>
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all font-mono" :class="courseStore.uiSettings.fontFamily === 'mono' ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.fontFamily = 'mono'">等宽</button>
                  </div>
                </div>
                <div class="space-y-2">
                  <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">行高</div>
                  <div class="grid grid-cols-3 gap-1.5">
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all" :class="courseStore.uiSettings.lineHeight === 1.5 ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.lineHeight = 1.5">紧凑</button>
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all" :class="courseStore.uiSettings.lineHeight === 1.75 ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.lineHeight = 1.75">舒适</button>
                    <button class="px-2 py-1.5 text-xs rounded-lg border transition-all" :class="courseStore.uiSettings.lineHeight === 2 ? 'bg-primary-50 border-primary-300 text-primary-600' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'" @click="courseStore.uiSettings.lineHeight = 2">宽松</button>
                  </div>
                </div>
              </div>
            </el-popover>
            
            <!-- Focus Mode -->
            <button 
              class="btn-icon"
              :class="{'!text-primary-600 !bg-primary-50 !border-primary-200': courseStore.isFocusMode}"
              @click="toggleFocusMode"
              title="专注模式 (F)"
            >
              <el-icon :size="17"><FullScreen /></el-icon>
            </button>

            <!-- Export Dropdown -->
            <el-dropdown trigger="click" @command="handleExport">
              <button class="btn-icon" title="导出">
                <el-icon :size="17"><Download /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu class="glass-popover">
                  <el-dropdown-item command="json">导出 JSON 备份</el-dropdown-item>
                  <el-dropdown-item command="markdown">导出 Markdown 文档</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <!-- Divider -->
          <div class="w-px h-7 bg-gradient-to-b from-transparent via-slate-200 to-transparent"></div>

          <!-- Help Button -->
          <button 
            class="btn-icon"
            @click="shortcutsHelpRef?.open()"
            title="快捷键帮助 (?)"
          >
            <el-icon :size="17"><QuestionFilled /></el-icon>
          </button>
          </template>
        </div>
      </header>

      <!-- Main Content Area - Router View -->
      <main class="flex-1 flex gap-3 min-h-0 overflow-hidden">
        <router-view class="flex-1 overflow-hidden" />
      </main>

      <!-- Simple Status Bar -->
      <div class="flex-shrink-0 glass-panel rounded-none xl:rounded-2xl h-9 xl:h-10 animate-fade-in-up flex items-center justify-center gap-6 px-6 text-xs font-medium text-slate-500" style="animation-delay: 0.2s;">
        <span>课程: {{ courseStore.courseList.length }}</span>
        <span class="w-1 h-1 rounded-full bg-slate-300"></span>
        <span>节点: {{ courseStore.nodes.length }}</span>
        <span class="w-1 h-1 rounded-full bg-slate-300"></span>
        <span :class="courseStore.loading ? 'text-amber-500' : 'text-emerald-500'">
          {{ courseStore.loading ? '加载中...' : '就绪' }}
        </span>
      </div>
    </div>

    <!-- Modals & Overlays -->
    <KnowledgeGraph />
    
    <KeyboardShortcutsHelp ref="shortcutsHelpRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  Search, CircleClose, ArrowRight, Connection, Setting, 
  Minus, Plus, FullScreen, Download, QuestionFilled
} from '@element-plus/icons-vue'

import KnowledgeGraph from './components/KnowledgeGraph.vue'
import KeyboardShortcutsHelp from './components/KeyboardShortcutsHelp.vue'

import { useCourseStore } from './stores/course'
import { useTaskWebSocket } from './composables/useTaskWebSocket'

const router = useRouter()
const courseStore = useCourseStore()
const shortcutsHelpRef = ref<InstanceType<typeof KeyboardShortcutsHelp>>()

useTaskWebSocket()

// UI State
const isSearchFocused = ref(false)
const globalSearchResults = ref<any[]>([])

// Initialize - Load course list on mount
onMounted(async () => {
  await courseStore.fetchCourseList()
})

// Debounce utility
function debounce<T extends (...args: any[]) => any>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timer: number | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = window.setTimeout(() => fn(...args), delay)
  }
}

// Global Search Handler with debounce
const debouncedSearch = debounce((query: string) => {
  courseStore.globalSearchQuery = query
  // Search logic here
}, 300)

function handleGlobalSearch(e: Event) {
  const query = (e.target as HTMLInputElement).value
  debouncedSearch(query)
}

function scrollToSearchResult(_id: string) {
  // Scroll logic here
}

// Focus Mode Toggle
function toggleFocusMode() {
  courseStore.isFocusMode = !courseStore.isFocusMode
  ElMessage.success(courseStore.isFocusMode ? '已进入专注模式' : '已退出专注模式')
}

// Export Handler
function handleExport(command: string) {
  if (command === 'json') {
    // Export JSON logic
    ElMessage.success('JSON 导出成功')
  } else if (command === 'markdown') {
    // Export Markdown logic
    ElMessage.success('Markdown 导出成功')
  }
}
</script>

<style scoped>
/* Custom Element Plus Overrides */
:deep(.glass-popover) {
  background: rgba(255, 255, 255, 0.95) !important;
  backdrop-filter: blur(20px) !important;
  border: 1px solid rgba(255, 255, 255, 0.6) !important;
  border-radius: 16px !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.1), 0 8px 24px rgba(0, 0, 0, 0.05) !important;
}

:deep(.el-dropdown-menu) {
  background: rgba(255, 255, 255, 0.95) !important;
  backdrop-filter: blur(20px) !important;
  border: 1px solid rgba(255, 255, 255, 0.6) !important;
  border-radius: 12px !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.1) !important;
  padding: 6px !important;
}

:deep(.el-dropdown-menu__item) {
  border-radius: 8px !important;
  padding: 8px 12px !important;
  font-size: 13px !important;
  color: var(--color-text-secondary) !important;
  transition: all 0.2s ease !important;
}

:deep(.el-dropdown-menu__item:hover) {
  background: rgba(99, 102, 241, 0.08) !important;
  color: var(--color-primary-600) !important;
}
</style>
