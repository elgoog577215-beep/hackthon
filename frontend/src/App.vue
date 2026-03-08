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
        
        <!-- Central Knowledge Graph Button -->
        <div class="flex-1 flex justify-center" v-if="courseStore.currentCourseId">
          <button 
            class="flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-all duration-300 relative overflow-hidden group animate-fade-in-up"
            :class="courseStore.showKnowledgeGraph 
              ? 'text-white shadow-lg shadow-primary-500/25' 
              : 'text-slate-600 hover:text-primary-600 hover:shadow-md'"
            :style="courseStore.showKnowledgeGraph 
              ? 'background: var(--gradient-primary);' 
              : 'background: rgba(255,255,255,0.8); border: 1px solid rgba(226,232,240,0.8); backdrop-filter: blur(8px);'"
            :aria-pressed="courseStore.showKnowledgeGraph"
            aria-label="知识图谱"
            @click="courseStore.showKnowledgeGraph = true"
          >
            <el-icon :size="16" class="transition-transform duration-300 group-hover:scale-110"><Connection /></el-icon>
            <span>知识图谱</span>
          </button>
        </div>
        
        <!-- Spacer when no course selected -->
        <div class="flex-1" v-else></div>

        <!-- Toolbar Controls -->
        <div class="flex items-center gap-3">
          <template v-if="courseStore.currentCourseId">
          <!-- Divider -->
          <div class="w-px h-7 bg-gradient-to-b from-transparent via-slate-200 to-transparent"></div>
          
          <!-- Global Search (Ctrl+F style) -->
          <div class="relative w-44">
            <div class="absolute right-0 top-1/2 -translate-y-1/2 flex items-center h-9 rounded-full overflow-hidden gap-1.5 px-3 transition-all duration-300 border z-10"
                 :class="isSearchFocused 
                   ? 'bg-white shadow-lg shadow-primary-500/10 border-primary-300 w-72' 
                   : searchQuery 
                     ? 'bg-white/90 border-primary-200/60 shadow-sm w-64' 
                     : 'bg-slate-100/80 border-transparent hover:bg-white/80 hover:border-slate-200 w-44'">
              <el-icon :size="14" class="flex-shrink-0 transition-colors duration-200" :class="isSearchFocused ? 'text-primary-500' : 'text-slate-400'"><Search /></el-icon>
              <input
                ref="globalSearchInputRef"
                v-model="searchQuery"
                type="text"
                placeholder="搜索全书... ⌘F"
                aria-label="搜索全书内容"
                class="bg-transparent border-none outline-none text-sm text-slate-700 placeholder:text-slate-400/70 h-full flex-1 min-w-0"
                @focus="isSearchFocused = true"
                @blur="isSearchFocused = false"
                @input="onSearchInput"
                @keydown.enter.exact.prevent="goNextMatch"
                @keydown.enter.shift.prevent="goPrevMatch"
                @keydown.escape.prevent="clearSearch"
              />
              <template v-if="searchQuery">
                <span class="text-[11px] font-medium whitespace-nowrap flex-shrink-0 px-1.5 py-0.5 rounded-md transition-colors"
                      :class="searchMatchTotal > 0 ? 'text-primary-600 bg-primary-50' : 'text-slate-400 bg-slate-100'">
                  {{ searchMatchTotal > 0 ? `${searchMatchIndex + 1}/${searchMatchTotal}` : '无结果' }}
                </span>
                <div class="flex items-center gap-0.5 ml-0.5">
                  <button class="w-6 h-6 flex items-center justify-center rounded-md text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-all" title="上一个 (Shift+Enter)" @click="goPrevMatch">
                    <el-icon :size="13"><ArrowUp /></el-icon>
                  </button>
                  <button class="w-6 h-6 flex items-center justify-center rounded-md text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-all" title="下一个 (Enter)" @click="goNextMatch">
                    <el-icon :size="13"><ArrowDown /></el-icon>
                  </button>
                  <button class="w-6 h-6 flex items-center justify-center rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all" title="清除 (Esc)" @click="clearSearch">
                    <el-icon :size="12"><CircleClose /></el-icon>
                  </button>
                </div>
              </template>
            </div>
          </div>

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
              :title="courseStore.isFocusMode ? '退出专注模式 (F)' : '专注模式 (F)'"
            >
              <el-icon v-if="!courseStore.isFocusMode" :size="17"><FullScreen /></el-icon>
              <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="4 14 10 14 10 20" />
                <polyline points="20 10 14 10 14 4" />
                <line x1="14" y1="10" x2="21" y2="3" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
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
      <div v-if="!courseStore.isFocusMode" class="flex-shrink-0 glass-panel rounded-none xl:rounded-2xl h-9 xl:h-10 animate-fade-in-up flex items-center justify-center gap-6 px-6 text-xs font-medium text-slate-500" style="animation-delay: 0.2s;">
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
    
    <!-- Global Floating AI Assistant -->
    <FloatingAIAssistant />
    
    <KeyboardShortcutsHelp ref="shortcutsHelpRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  Search, CircleClose, ArrowUp, ArrowDown, Connection, Setting, 
  Minus, Plus, FullScreen, Download, QuestionFilled
} from '@element-plus/icons-vue'

import KnowledgeGraph from './components/KnowledgeGraph.vue'
import KeyboardShortcutsHelp from './components/KeyboardShortcutsHelp.vue'
import FloatingAIAssistant from './components/FloatingAIAssistant.vue'

import { useCourseStore } from './stores/course'
import { useTaskWebSocket } from './composables/useTaskWebSocket'

const router = useRouter()
const courseStore = useCourseStore()
const shortcutsHelpRef = ref<InstanceType<typeof KeyboardShortcutsHelp>>()

useTaskWebSocket()

// UI State
const isSearchFocused = ref(false)
const searchQuery = ref('')
const searchMatchIndex = ref(0)
const searchMatchTotal = ref(0)
const globalSearchInputRef = ref<HTMLInputElement | null>(null)
let searchDebounceTimer: number | null = null

// Initialize - Load course list on mount
onMounted(async () => {
  await courseStore.fetchCourseList()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
})

// Ctrl+F to focus search
function handleGlobalKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f' && courseStore.currentCourseId) {
    e.preventDefault()
    globalSearchInputRef.value?.focus()
    globalSearchInputRef.value?.select()
  }
}

function onSearchInput() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = window.setTimeout(() => {
    courseStore.globalSearchQuery = searchQuery.value
    // MarkdownRenderer re-renders with throttle, wait for DOM update
    setTimeout(() => countAndJumpMatches(0), 400)
  }, 250)
}

function countAndJumpMatches(targetIndex: number) {
  const container = document.getElementById('content-scroll-container')
  if (!container) { searchMatchTotal.value = 0; return }
  // Wait for DOM to update highlights
  nextTick(() => {
    const marks = container.querySelectorAll('span.bg-yellow-200')
    searchMatchTotal.value = marks.length
    // Remove previous active highlight
    container.querySelectorAll('span.search-active').forEach(el => {
      el.classList.remove('search-active')
    })
    if (marks.length === 0) { searchMatchIndex.value = 0; return }
    // Clamp index
    const idx = ((targetIndex % marks.length) + marks.length) % marks.length
    searchMatchIndex.value = idx
    const active = marks[idx] as HTMLElement
    active.classList.add('search-active')
    active.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

function goNextMatch() {
  if (searchMatchTotal.value === 0) return
  countAndJumpMatches(searchMatchIndex.value + 1)
}

function goPrevMatch() {
  if (searchMatchTotal.value === 0) return
  countAndJumpMatches(searchMatchIndex.value - 1)
}

function clearSearch() {
  searchQuery.value = ''
  courseStore.globalSearchQuery = ''
  searchMatchTotal.value = 0
  searchMatchIndex.value = 0
  const container = document.getElementById('content-scroll-container')
  container?.querySelectorAll('span.search-active').forEach(el => {
    el.classList.remove('search-active')
  })
}

// Focus Mode Toggle
function toggleFocusMode() {
  courseStore.isFocusMode = !courseStore.isFocusMode
  ElMessage.success(courseStore.isFocusMode ? '已进入专注模式' : '已退出专注模式')
}

// Export Handler
function handleExport(command: string) {
  if (command === 'json') {
    courseStore.exportCourseJson()
  } else if (command === 'markdown') {
    courseStore.exportCourseMarkdown()
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
