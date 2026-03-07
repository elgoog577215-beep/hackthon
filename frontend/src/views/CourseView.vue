<template>
  <div ref="containerRef" class="course-view-container">
    
    <!-- Mobile/Tablet Overlay -->
    <Transition name="fade">
      <div v-if="showOverlay" 
           class="fixed inset-0 bg-slate-900/30 backdrop-blur-sm z-[40]"
           @click="closeAllSidebars">
      </div>
    </Transition>

    <!-- Floating Toggle Buttons (Mobile/Tablet) -->
    <Transition name="slide-in-left">
      <div v-if="showLeftToggle" class="fixed left-4 z-[60]" :style="{ top: toggleButtonTop }">
          <button 
            @click="toggleLeftSidebar" 
            class="toggle-button"
            :class="{ 'toggle-button-active': leftVisible }"
            :title="leftVisible ? '收起目录' : '展开目录'"
            :aria-expanded="leftVisible"
            aria-label="切换目录侧栏"
          >
              <el-icon :size="18"><Menu /></el-icon>
              <span v-if="!leftVisible" class="ml-1.5 text-xs font-medium hidden sm:inline">目录</span>
          </button>
      </div>
    </Transition>
    
    <Transition name="slide-in-right">
      <div v-if="showRightToggle" class="fixed right-4 z-[60]" :style="{ top: toggleButtonTop }">
          <button 
            @click="toggleRightSidebar" 
            class="toggle-button"
            :class="{ 'toggle-button-active': rightVisible }"
            :title="rightVisible ? '收起助手' : '展开助手'"
            :aria-expanded="rightVisible"
            aria-label="切换AI助手侧栏"
          >
              <span v-if="!rightVisible" class="mr-1.5 text-xs font-medium hidden sm:inline">AI</span>
              <el-icon :size="18"><ChatDotRound /></el-icon>
          </button>
      </div>
    </Transition>

    <!-- Floating Stats Button -->
    <Transition name="slide-in-right">
      <div v-if="!courseStore.isFocusMode" class="fixed right-4 z-[60]" :style="{ top: statsButtonTop }">
          <button 
            @click="showLearningStats = true" 
            class="toggle-button toggle-button-stats"
            :class="{ 'toggle-button-active': showLearningStats }"
            title="学习统计"
            aria-label="查看学习统计"
          >
              <el-icon :size="18"><TrendCharts /></el-icon>
              <span v-if="completionRate > 0" class="absolute -top-1 -right-1 w-5 h-5 bg-emerald-500 text-white text-[10px] rounded-full flex items-center justify-center font-bold">
                {{ completionRate }}%
              </span>
          </button>
      </div>
    </Transition>

    <!-- Exit Focus Mode Button -->
    <Transition name="fade-scale">
      <div v-if="courseStore.isFocusMode" class="fixed top-4 right-4 z-[100]">
          <button 
            @click="courseStore.toggleFocusMode()" 
            class="px-4 py-2 bg-white/90 backdrop-blur-md text-slate-700 rounded-xl shadow-lg border border-slate-200/60 flex items-center gap-2 hover:bg-white hover:shadow-xl transition-all"
            title="退出专注模式 (Ctrl+Shift+F)"
          >
              <el-icon :size="16"><Close /></el-icon>
              <span class="text-sm font-medium">退出专注模式</span>
          </button>
      </div>
    </Transition>

    <!-- Main Content Area -->
    <div class="main-content-wrapper" :class="{ 'with-smart-bar': !courseStore.isFocusMode }">
      <!-- Course Tree Sidebar (Left) -->
      <Transition :name="sidebarTransition">
        <CourseTree
          v-show="leftVisible && !courseStore.isFocusMode"
          :style="{ width: isMobile ? '85%' : leftSidebarWidth + 'px' }"
          :class="[
            'flex-shrink-0 overflow-hidden glass-panel rounded-none xl:rounded-2xl',
            isMobile ? 'fixed left-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-10',
            isResizingLeft ? '!transition-none' : 'transition-all duration-300 ease-out'
          ]"
          @update:preferredWidth="handlePreferredWidth"
          @node-selected="handleNodeSelected"
          @toggle-sidebar="collapseLeft"
        />
      </Transition>
      
      <!-- Left Sidebar Collapse Indicator -->
      <Transition name="fade">
        <div v-if="!leftVisible && !isMobile && !courseStore.isFocusMode" 
             class="absolute left-3 top-1/2 -translate-y-1/2 z-20">
            <button 
                @click="expandLeft" 
                class="collapse-indicator"
                title="展开目录 (Ctrl+1)"
            >
                <el-icon :size="16"><ArrowRight /></el-icon>
                <span class="text-xs font-medium text-slate-400 ml-1">目录</span>
            </button>
        </div>
      </Transition>
      
      <!-- Left Resizer -->
      <div 
        v-if="showLeftResizer"
        class="w-1 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative transition-all duration-200 hover:w-2 hover:-ml-0.5"
        @mousedown="startResizeLeft"
        @touchstart="startResizeLeft"
        @dblclick="resetLeftSidebar"
      >
          <div 
              class="absolute inset-y-0 w-px transition-colors duration-300"
              :class="isResizingLeft ? 'bg-primary-300' : 'bg-transparent group-hover:bg-slate-200'"
          ></div>
          <div 
              class="w-0.5 h-10 rounded-full backdrop-blur-sm transition-all duration-300 shadow-sm"
              :class="isResizingLeft 
                  ? 'bg-primary-500 h-14 w-1 shadow-[0_0_8px_rgba(99,102,241,0.4)]' 
                  : 'bg-slate-300/60 group-hover:bg-primary-400 group-hover:h-12 group-hover:w-1'"
          ></div>
      </div>

      <!-- Content Area -->
      <ContentArea 
        ref="contentAreaRef"
        :class="[
          'flex-1 overflow-hidden relative z-0',
          !leftVisible && !isMobile ? 'ml-2' : ''
        ]"
      />

      <!-- Right Resizer -->
      <div 
        v-if="showRightResizer"
        class="w-1 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative transition-all duration-200 hover:w-2 hover:-mr-0.5"
        @mousedown="startResizeRight"
        @touchstart="startResizeRight"
        @dblclick="resetRightSidebar"
      >
          <div class="absolute inset-y-4 w-px bg-white/0 group-hover:bg-primary-300/50 transition-colors duration-300"></div>
          <div class="w-0.5 h-10 rounded-full bg-slate-300/40 backdrop-blur-sm group-hover:bg-primary-400 group-hover:h-12 group-hover:w-1 group-hover:shadow-[0_0_8px_rgba(139,92,246,0.4)] transition-all duration-300"></div>
      </div>

      <!-- Right Sidebar (AI Assistant) -->
      <Transition :name="sidebarTransition">
        <div
          v-show="rightVisible && !courseStore.isFocusMode"
          :style="{ width: isMobile ? '85%' : rightSidebarWidth + 'px' }"
          :class="[
            'flex-shrink-0 overflow-hidden h-full relative glass-panel rounded-none xl:rounded-2xl',
            isMobile ? 'fixed right-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-20',
            isResizingRight ? '!transition-none' : 'transition-all duration-300 ease-out'
          ]"
        >
          <!-- Collapse Button -->
          <button 
            v-if="!isMobile"
            @click="collapseRight"
            class="absolute top-3 left-2 z-40 w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-all duration-200 hover:scale-105"
            title="收起 (Ctrl+3)"
          >
            <el-icon :size="16"><ArrowLeft /></el-icon>
          </button>

          <ChatPanel class="h-full" />
        </div>
      </Transition>

      <!-- Right Sidebar Collapse Indicator -->
      <Transition name="fade">
        <div v-if="!rightVisible && !isMobile && !courseStore.isFocusMode" 
             class="absolute right-3 top-1/2 -translate-y-1/2 z-20">
            <button 
                @click="expandRight" 
                class="collapse-indicator"
                title="展开助手 (Ctrl+3)"
            >
                <span class="text-xs font-medium text-slate-400 mr-1">AI</span>
                <el-icon :size="16"><ArrowLeft /></el-icon>
            </button>
        </div>
      </Transition>
    </div>

    <!-- Smart Bar (Bottom) -->
    <SmartBar 
      v-if="!courseStore.isFocusMode"
      :notes-count="notesCount"
      :wrong-answers-count="wrongAnswersCount"
      :notes="noteStore.notes"
      :wrong-answers="reviewStore.wrongAnswers"
      @start-quiz="handleStartQuiz"
      @summarize="handleSummarize"
      @show-stats="handleShowStats"
      @show-graph="handleShowGraph"
      @view-all-notes="handleViewAllNotes"
      @view-all-wrong-answers="handleViewAllWrongAnswers"
      @retry-wrong="handleRetryWrong"
      @retry-all-wrong="handleRetryAllWrong"
      @locate-note="handleLocateNote"
    />

    <!-- Learning Stats Modal -->
    <Teleport to="body">
      <Transition name="fade-scale">
        <div v-if="showLearningStats" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="showLearningStats = false"></div>
          <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden">
            <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white">
                  <el-icon :size="20"><TrendCharts /></el-icon>
                </div>
                <div>
                  <h3 class="text-lg font-bold text-slate-800">学习统计</h3>
                  <p class="text-xs text-slate-500">实时追踪你的学习进度</p>
                </div>
              </div>
              <button @click="showLearningStats = false" class="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="overflow-y-auto max-h-[70vh]">
              <LearningStats />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Keyboard Shortcuts Help -->
    <KeyboardShortcutsHelp ref="shortcutsHelpRef" />
  </div>
</template>

<script setup lang="ts">
import CourseTree from '../components/CourseTree.vue'
import ContentArea from '../components/ContentArea.vue'
import ChatPanel from '../components/ChatPanel.vue'
import LearningStats from '../components/LearningStats.vue'
import SmartBar from '../components/SmartBar.vue'
import KeyboardShortcutsHelp from '../components/KeyboardShortcutsHelp.vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useLearningStore } from '../stores/learning'
import { useReviewStore } from '../stores/review'
import { useGenerationStore } from '../stores/generation'
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu, ChatDotRound, ArrowLeft, ArrowRight, TrendCharts, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const learningStore = useLearningStore()
const reviewStore = useReviewStore()
const genStore = useGenerationStore()
const route = useRoute()
const containerRef = ref<HTMLElement | null>(null)
const shortcutsHelpRef = ref<InstanceType<typeof KeyboardShortcutsHelp> | null>(null)

// Breakpoints
const SCREEN_MD = 768
const SCREEN_LG = 1024
const SCREEN_XL = 1280

// Screen size state
const screenWidth = ref(window.innerWidth)
const isMobile = computed(() => screenWidth.value < SCREEN_MD)
const isTablet = computed(() => screenWidth.value >= SCREEN_MD && screenWidth.value < SCREEN_LG)
const isSmallDesktop = computed(() => screenWidth.value >= SCREEN_LG && screenWidth.value < SCREEN_XL)

// Sidebar visibility state
const STORAGE_KEY = 'knowledgeMap_sidebarState'

interface SidebarState {
  leftVisible: boolean
  rightVisible: boolean
  leftWidth: number
  rightWidth: number
}

const loadSidebarState = (): SidebarState => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      return JSON.parse(saved)
    }
  } catch (e) {
    console.warn('Failed to load sidebar state:', e)
  }
  return {
    leftVisible: true,
    rightVisible: true,
    leftWidth: 300,
    rightWidth: 320
  }
}

const savedState = loadSidebarState()
const leftVisible = ref(savedState.leftVisible)
const rightVisible = ref(savedState.rightVisible)
const leftSidebarWidth = ref(savedState.leftWidth)
const rightSidebarWidth = ref(savedState.rightWidth)
const activeRightTab = ref<'chat' | 'notes' | 'quiz'>('chat')

const debounce = <T extends (...args: any[]) => any>(fn: T, delay: number): ((...args: Parameters<T>) => void) => {
  let timer: number | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = window.setTimeout(() => fn(...args), delay)
  }
}

const saveSidebarStateImmediate = () => {
  const state: SidebarState = {
    leftVisible: leftVisible.value,
    rightVisible: rightVisible.value,
    leftWidth: leftSidebarWidth.value,
    rightWidth: rightSidebarWidth.value
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

const saveSidebarState = debounce(saveSidebarStateImmediate, 500)

watch([leftVisible, rightVisible, leftSidebarWidth, rightSidebarWidth], saveSidebarState)

// Mobile-specific visibility (for overlay mode)
const mobileLeftOpen = ref(false)
const mobileRightOpen = ref(false)

// Computed visibility
const showOverlay = computed(() => {
  return isMobile.value && (mobileLeftOpen.value || mobileRightOpen.value)
})

const toggleButtonTop = computed(() => {
  return isMobile.value ? '5rem' : '1rem'
})

const statsButtonTop = computed(() => {
  return isMobile.value ? '8rem' : '4rem'
})

// Learning stats modal
const showLearningStats = ref(false)

// Completion rate for stats button badge
const completionRate = computed(() => {
  const totalNodes = courseStore.courseTree.length
  const completedCount = learningStore.learningStats.completedNodes.length
  if (totalNodes === 0) return 0
  return Math.round((completedCount / totalNodes) * 100)
})

// Show toggle buttons when sidebar is hidden or in mobile/tablet mode
const showLeftToggle = computed(() => {
  if (courseStore.isFocusMode) return false
  if (isMobile.value) return true
  if (isTablet.value) return true
  return !leftVisible.value
})

const showRightToggle = computed(() => {
  if (courseStore.isFocusMode) return false
  if (isMobile.value) return true
  if (isTablet.value) return true
  return !rightVisible.value
})

// Show resizers
const showLeftResizer = computed(() => {
  return !isMobile.value && leftVisible.value && !courseStore.isFocusMode
})

const showRightResizer = computed(() => {
  return !isMobile.value && rightVisible.value && !courseStore.isFocusMode
})

// Transition name based on screen size
const sidebarTransition = computed(() => {
  return isMobile.value ? 'slide-in-left' : 'fade'
})

// Sidebar control functions
const toggleLeftSidebar = () => {
  if (isMobile.value) {
    mobileLeftOpen.value = !mobileLeftOpen.value
    if (mobileLeftOpen.value) mobileRightOpen.value = false
  } else {
    leftVisible.value = !leftVisible.value
  }
}

const toggleRightSidebar = () => {
  if (isMobile.value) {
    mobileRightOpen.value = !mobileRightOpen.value
    if (mobileRightOpen.value) mobileLeftOpen.value = false
  } else {
    rightVisible.value = !rightVisible.value
  }
}

const expandLeft = () => {
  leftVisible.value = true
  mobileLeftOpen.value = true
}

const collapseLeft = () => {
  leftVisible.value = false
  mobileLeftOpen.value = false
}

const expandRight = () => {
  rightVisible.value = true
  mobileRightOpen.value = true
}

const collapseRight = () => {
  rightVisible.value = false
  mobileRightOpen.value = false
}

const closeAllSidebars = () => {
  mobileLeftOpen.value = false
  mobileRightOpen.value = false
}

const handleNodeSelected = () => {
  if (isMobile.value || isTablet.value) {
    mobileLeftOpen.value = false
  }
}

// Resize handlers with touch support
const isResizingLeft = ref(false)
const isResizingRight = ref(false)

const startResizeLeft = (e: MouseEvent | TouchEvent) => {
    isResizingLeft.value = true
    const startX = 'touches' in e ? (e.touches[0]?.clientX ?? 0) : e.clientX
    const startWidth = leftSidebarWidth.value

    const onMove = (e: MouseEvent | TouchEvent) => {
        const currentX = 'touches' in e ? (e.touches[0]?.clientX ?? 0) : e.clientX
        const delta = currentX - startX
        leftSidebarWidth.value = Math.max(240, Math.min(480, startWidth + delta))
    }

    const onEnd = () => {
        isResizingLeft.value = false
        document.removeEventListener('mousemove', onMove as any)
        document.removeEventListener('mouseup', onEnd)
        document.removeEventListener('touchmove', onMove as any)
        document.removeEventListener('touchend', onEnd)
    }

    document.addEventListener('mousemove', onMove as any)
    document.addEventListener('mouseup', onEnd)
    document.addEventListener('touchmove', onMove as any, { passive: true })
    document.addEventListener('touchend', onEnd)
}

const resetLeftSidebar = () => {
    leftSidebarWidth.value = screenWidth.value < SCREEN_XL ? 280 : 300
}

const startResizeRight = (e: MouseEvent | TouchEvent) => {
    isResizingRight.value = true
    const startX = 'touches' in e ? (e.touches[0]?.clientX ?? 0) : e.clientX
    const startWidth = rightSidebarWidth.value

    const onMove = (e: MouseEvent | TouchEvent) => {
        const currentX = 'touches' in e ? (e.touches[0]?.clientX ?? 0) : e.clientX
        const delta = startX - currentX
        rightSidebarWidth.value = Math.max(280, Math.min(480, startWidth + delta))
    }

    const onEnd = () => {
        isResizingRight.value = false
        document.removeEventListener('mousemove', onMove as any)
        document.removeEventListener('mouseup', onEnd)
        document.removeEventListener('touchmove', onMove as any)
        document.removeEventListener('touchend', onEnd)
    }

    document.addEventListener('mousemove', onMove as any)
    document.addEventListener('mouseup', onEnd)
    document.addEventListener('touchmove', onMove as any, { passive: true })
    document.addEventListener('touchend', onEnd)
}

const resetRightSidebar = () => {
    rightSidebarWidth.value = 320
}

const handlePreferredWidth = (width: number) => {
    if (!isMobile.value) {
        leftSidebarWidth.value = width
    }
}

// Keyboard shortcuts
const handleKeydown = (e: KeyboardEvent) => {
  // Ignore shortcuts when typing in input fields
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.contentEditable === 'true')) {
    return
  }

  if (e.ctrlKey || e.metaKey) {
    switch (e.key.toLowerCase()) {
      case '1':
        e.preventDefault()
        toggleLeftSidebar()
        break
      case '2':
        e.preventDefault()
        // Toggle both sidebars
        if (leftVisible.value && rightVisible.value) {
          rightVisible.value = false
        } else if (leftVisible.value) {
          rightVisible.value = true
        } else {
          leftVisible.value = true
        }
        break
      case '3':
        e.preventDefault()
        toggleRightSidebar()
        break
      case 'k':
        // Ctrl+K: Focus search in course tree
        e.preventDefault()
        // Emit event to focus search or open search dialog
        const searchInput = document.querySelector('.course-tree-search input') as HTMLInputElement
        if (searchInput) {
          searchInput.focus()
        }
        break
      case 'f':
        if (e.shiftKey) {
          // Ctrl+Shift+F: Toggle focus mode
          e.preventDefault()
          courseStore.toggleFocusMode()
        }
        break
      case 'b':
        // Ctrl+B: Toggle sidebar (same as Ctrl+1)
        e.preventDefault()
        toggleLeftSidebar()
        break
      case 'g':
        // Ctrl+G: Toggle knowledge graph
        e.preventDefault()
        courseStore.showKnowledgeGraph = !courseStore.showKnowledgeGraph
        break
      case 'e':
        if (e.shiftKey) {
          // Ctrl+Shift+E: Export (triggered in ContentArea)
          // This is handled in ContentArea component
        }
        break
    }
  }

  // ? key: Show keyboard shortcuts help
  if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault()
    shortcutsHelpRef.value?.open()
  }

  // Escape to close mobile sidebars
  if (e.key === 'Escape' && showOverlay.value) {
    closeAllSidebars()
  }
}

// Screen size check
const checkScreenSize = () => {
    const prevWidth = screenWidth.value
    screenWidth.value = window.innerWidth
    
    // Handle transitions between breakpoints
    const wasDesktop = prevWidth >= SCREEN_MD
    const isNowMobile = screenWidth.value < SCREEN_MD
    
    if (wasDesktop && isNowMobile) {
      // Transitioning to mobile - close sidebars
      mobileLeftOpen.value = false
      mobileRightOpen.value = false
    } else if (!wasDesktop && !isNowMobile) {
      // Transitioning from mobile - close mobile overlays
      mobileLeftOpen.value = false
      mobileRightOpen.value = false
    }
    
    // Auto-collapse right sidebar on tablet/small desktop
    if (isTablet.value || isSmallDesktop.value) {
      // On smaller screens, prefer left sidebar
      if (leftVisible.value && rightVisible.value) {
        // Both visible might be too crowded, but respect user choice
      }
    }
}

// Initialize
onMounted(() => {
  genStore.restoreGenerationState()
  learningStore.restoreLearningStats()
  reviewStore.restoreQuizData()
  
  checkScreenSize()
  window.addEventListener('resize', checkScreenSize)
  window.addEventListener('keydown', handleKeydown)
  
  // Initial state for tablet
  if (isTablet.value) {
    rightVisible.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', checkScreenSize)
  window.removeEventListener('keydown', handleKeydown)
})

// Watch route changes to load course
watch(() => route.params.courseId, (newCourseId, oldCourseId) => {
  if (newCourseId) {
    courseStore.loadCourse(newCourseId as string)
  } else if (oldCourseId && !newCourseId) {
    // Navigating back to home - clear current course
    courseStore.currentCourseId = ''
    courseStore.courseTree = []
    courseStore.nodes = []
    courseStore.currentNode = null
    noteStore.notes = []
  }
}, { immediate: true })

// SmartBar computed properties
const notesCount = computed(() => noteStore.notes?.length || 0)
const wrongAnswersCount = computed(() => reviewStore.wrongAnswers?.length || 0)

const contentAreaRef = ref<InstanceType<typeof ContentArea> | null>(null)

// SmartBar event handlers
const handleStartQuiz = () => {
  if (!courseStore.currentNode) {
    ElMessage.warning('请先选择一个章节')
    return
  }
  contentAreaRef.value?.startQuiz(courseStore.currentNode)
}

const handleSummarize = () => {
  courseStore.quickSummarize()
}

const handleShowStats = () => {
  showLearningStats.value = true
}

const handleShowGraph = () => {
  courseStore.showKnowledgeGraph = true
}

const handleViewAllNotes = () => {
  courseStore.isMobileNotesVisible = true
}

const handleViewAllWrongAnswers = () => {
  courseStore.isMobileNotesVisible = true
}

const handleRetryWrong = (_item: any) => {
  if (!courseStore.currentNode) {
    ElMessage.warning('请先选择一个章节')
    return
  }
  contentAreaRef.value?.startQuiz(courseStore.currentNode)
}

const handleRetryAllWrong = () => {
  activeRightTab.value = 'chat'
  if (!rightVisible.value) {
    rightVisible.value = true
  }
}

const handleLocateNote = (note: any) => {
  if (note.nodeId) {
    courseStore.selectNode(note.nodeId)
    // Scroll to the note's highlight in content area
    setTimeout(() => {
      noteStore.scrollToNote(note.id)
    }, 100)
  }
}
</script>

<style scoped>
.course-view-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
  min-height: 0;
  width: 100%;
  height: 100%;
}

.main-content-wrapper {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
  min-height: 0;
  width: 100%;
  height: 100%;
  gap: 3px;
}

.main-content-wrapper.with-smart-bar {
  padding-bottom: 0;
}

.toggle-button {
  width: 40px;
  height: 40px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border: 1px solid #e2e8f0;
  color: #475569;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.toggle-button:hover {
  transform: scale(1.05);
}

.toggle-button:active {
  transform: scale(0.95);
}

@media (min-width: 640px) {
  .toggle-button {
    width: auto;
    height: auto;
    padding: 8px 12px;
  }
}

.toggle-button-active {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.3);
  color: #6366f1;
}

.collapse-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border: 1px solid #e2e8f0;
  color: #64748b;
  transition: all 0.2s ease;
}

.collapse-indicator:hover {
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.3);
  transform: scale(1.05);
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide in from left */
.slide-in-left-enter-active,
.slide-in-left-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-in-left-enter-from,
.slide-in-left-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

/* Slide in from right */
.slide-in-right-enter-active,
.slide-in-right-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-in-right-enter-from,
.slide-in-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
