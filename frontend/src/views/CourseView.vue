<template>
  <div ref="containerRef" class="course-view-container">
    
    <!-- Mobile/Tablet Overlay -->
    <Transition name="fade">
      <div v-if="showOverlay" 
           class="fixed inset-0 bg-slate-900/30 backdrop-blur-sm z-[40]"
           @click="closeAllSidebars">
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
             class="flex-shrink-0 z-20 flex items-start" style="padding-top: 12px;">
            <button 
                @click="expandLeft" 
                class="collapse-indicator"
                title="展开目录 (Ctrl+1)"
            >
                <el-icon :size="14"><DArrowRight /></el-icon>
            </button>
        </div>
      </Transition>
      
      <!-- Left Resizer -->
      <div 
        v-if="showLeftResizer"
        class="w-2 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative transition-all duration-200 hover:w-3 hover:-ml-0.5"
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
        v-model:notes-collapsed="notesCollapsed"
        :side-ai-panel-visible="sideAIPanelVisible"
        :class="[
          'flex-1 overflow-hidden relative z-0',
          !leftVisible && !isMobile ? 'ml-2' : ''
        ]"
        @quote-ask="openSideAIPanel"
      />

      <!-- Floating AI Assistant Button -->
      <Transition name="fade">
        <button
          v-if="!sideAIPanelVisible && courseStore.currentCourseId"
          class="fixed bottom-20 z-50 w-12 h-12 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg hover:shadow-xl hover:scale-105 flex items-center justify-center transition-all duration-200 cursor-pointer"
          :class="notesCollapsed ? 'right-6' : 'right-[340px]'"
          title="AI 助手"
          @click="openSideAIPanelDirect"
        >
          <Bot :size="22" />
        </button>
      </Transition>

      <!-- Side AI Panel -->
      <Transition name="slide-in-right">
        <SideAIPanel
          v-if="sideAIPanelVisible"
          :visible="sideAIPanelVisible"
          :quote-text="sideAIQuoteText"
          :quote-node-id="sideAIQuoteNodeId"
          @close="closeSideAIPanel"
        />
      </Transition>


    </div>

    <!-- Smart Bar (Bottom) -->
    <SmartBar 
      v-if="!courseStore.isFocusMode"
      :notes-count="notesCount"
      :wrong-count="wrongAnswersCount"
      :notes="noteStore.notes"
      :current-location="readingLocation"
      @start-quiz="handleStartQuiz"
      @show-stats="handleShowStats"
      @show-graph="handleShowGraph"
      @show-wrong-answers="handleShowWrongAnswers"
      @view-all-notes="handleViewAllNotes"
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

    <!-- Notes Modal -->
    <Teleport to="body">
      <Transition name="fade-scale">
        <div v-if="showNotesPanel" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="showNotesPanel = false"></div>
          <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
            <button @click="showNotesPanel = false" class="absolute top-4 right-4 z-10 w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all">
              <el-icon :size="20"><Close /></el-icon>
            </button>
            <NotesPanel ref="notesPanelRef" class="flex-1 min-h-0" @locate="handleLocateFromPanel" @view-detail="handleViewDetailFromPanel" @close="showNotesPanel = false" @start-similar-quiz="handleStartSimilarQuiz" />
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
import SideAIPanel from '../components/SideAIPanel.vue'
import LearningStats from '../components/LearningStats.vue'
import SmartBar from '../components/SmartBar.vue'
import NotesPanel from '../components/NotesPanel.vue'
import KeyboardShortcutsHelp from '../components/KeyboardShortcutsHelp.vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useLearningStore } from '../stores/learning'
import { useReviewStore } from '../stores/review'
import { useGenerationStore } from '../stores/generation'
import { usePendingChangesStore } from '../stores/pendingChanges'
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { DArrowRight, TrendCharts, Close } from '@element-plus/icons-vue'
import { Bot } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const learningStore = useLearningStore()
const pendingChangesStore = usePendingChangesStore()
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
    logger.warn('Failed to load sidebar state:', e)
  }
  return {
    leftVisible: true,
    rightVisible: true,
    leftWidth: 250,
    rightWidth: 320
  }
}

const savedState = loadSidebarState()
const leftVisible = ref(savedState.leftVisible)
const rightVisible = ref(savedState.rightVisible)
const leftSidebarWidth = ref(savedState.leftWidth)
const rightSidebarWidth = ref(savedState.rightWidth)
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

// Learning stats modal
const showLearningStats = ref(false)
const showNotesPanel = ref(false)

// Notes collapsed state (lifted from ContentArea for panel coordination)
const notesCollapsed = ref(false)

// Side AI Panel state
const sideAIPanelVisible = ref(false)
const sideAIQuoteText = ref('')
const sideAIQuoteNodeId = ref('')
const layoutBeforePanel = ref<{ leftVisible: boolean; notesCollapsed: boolean } | null>(null)

const openSideAIPanel = (payload: { text: string; nodeId: string }) => {
  // Save current layout
  layoutBeforePanel.value = {
    leftVisible: leftVisible.value,
    notesCollapsed: notesCollapsed.value
  }
  // Collapse sidebars to make room
  leftVisible.value = false
  notesCollapsed.value = true
  // Open panel with quote
  sideAIQuoteText.value = payload.text
  sideAIQuoteNodeId.value = payload.nodeId
  sideAIPanelVisible.value = true
}

const openSideAIPanelDirect = () => {
  // Save current layout (same as openSideAIPanel)
  layoutBeforePanel.value = {
    leftVisible: leftVisible.value,
    notesCollapsed: notesCollapsed.value
  }
  // Collapse sidebars to make room
  leftVisible.value = false
  notesCollapsed.value = true
  // Open panel without quote
  sideAIQuoteText.value = ''
  sideAIQuoteNodeId.value = ''
  sideAIPanelVisible.value = true
}

const closeSideAIPanel = () => {
  sideAIPanelVisible.value = false
  // Restore layout
  if (layoutBeforePanel.value) {
    leftVisible.value = layoutBeforePanel.value.leftVisible
    notesCollapsed.value = layoutBeforePanel.value.notesCollapsed
    layoutBeforePanel.value = null
  }
}

// Show resizers
const showLeftResizer = computed(() => {
  return !isMobile.value && leftVisible.value && !courseStore.isFocusMode
})

// Transition name based on screen size
const sidebarTransition = computed(() => {
  return 'slide-in-left'
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

const expandLeft = () => {
  leftVisible.value = true
  mobileLeftOpen.value = true
}

const collapseLeft = () => {
  leftVisible.value = false
  mobileLeftOpen.value = false
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
    leftSidebarWidth.value = screenWidth.value < SCREEN_XL ? 240 : 250
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
        // AI assistant is now a global floating component
        e.preventDefault()
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

  // Escape to close mobile sidebars or Side AI Panel
  if (e.key === 'Escape') {
    if (sideAIPanelVisible.value) {
      closeSideAIPanel()
      return
    }
    if (showOverlay.value) {
      closeAllSidebars()
    }
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
  // Auto-close SideAIPanel on course switch to prevent stale context
  if (sideAIPanelVisible.value && oldCourseId && newCourseId !== oldCourseId) {
    closeSideAIPanel()
  }
  if (newCourseId) {
    courseStore.loadCourse(newCourseId as string)
    pendingChangesStore.fetchPendingChanges(newCourseId as string)
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
const notesCount = computed(() => noteStore.notes?.filter(n => n.sourceType !== 'format' && n.sourceType !== 'wrong').length || 0)
const wrongAnswersCount = computed(() => {
  const currentNodeIds = new Set(courseStore.nodes.map(n => n.node_id))
  const structured = (reviewStore.wrongAnswers || []).filter(w => currentNodeIds.has(w.nodeId))
  const structuredQuestions = new Set(structured.map(w => w.question))
  const legacyCount = (noteStore.notes || [])
    .filter(n => n.sourceType === 'wrong' && currentNodeIds.has(n.nodeId || '') && !structuredQuestions.has(n.quote || ''))
    .length
  return structured.length + legacyCount
})

// Reading location indicator
const parentNodeName = computed(() => {
  const node = courseStore.currentNode
  if (!node?.parent_node_id) return ''
  const parent = courseStore.nodes.find(n => n.node_id === node.parent_node_id)
  return parent?.node_name || ''
})

const readingLocation = computed(() => {
  const node = courseStore.currentNode
  if (!node) return ''
  return parentNodeName.value ? `${parentNodeName.value} · ${node.node_name}` : node.node_name
})

const contentAreaRef = ref<InstanceType<typeof ContentArea> | null>(null)
const notesPanelRef = ref<InstanceType<typeof NotesPanel> | null>(null)

// SmartBar event handlers
const handleStartQuiz = () => {
  if (!courseStore.currentNode) {
    ElMessage.warning('请先选择一个章节')
    return
  }
  contentAreaRef.value?.startQuiz(courseStore.currentNode)
}

const handleShowStats = () => {
  flushStudyTime() // record accumulated time before showing stats
  showLearningStats.value = true
}

const handleShowGraph = () => {
  courseStore.showKnowledgeGraph = true
}

const handleViewAllNotes = () => {
  showNotesPanel.value = true
}

const handleShowWrongAnswers = () => {
  showNotesPanel.value = true
  nextTick(() => {
    notesPanelRef.value?.setTab('wrong')
  })
}

const handleLocateNote = (note: any) => {
  if (note.nodeId) {
    const node = courseStore.nodes.find(n => n.node_id === note.nodeId)
    if (node) courseStore.selectNode(node)
    setTimeout(() => {
      courseStore.scrollToNote(note.id)
    }, 100)
  }
}

const handleLocateFromPanel = (note: any) => {
  showNotesPanel.value = false
  handleLocateNote(note)
}

const handleViewDetailFromPanel = (note: any) => {
  showNotesPanel.value = false
  contentAreaRef.value?.showNoteDetail(note, () => {
    showNotesPanel.value = true
  })
}

const handleStartSimilarQuiz = (quizzes: any[], nodeId: string) => {
  showNotesPanel.value = false
  contentAreaRef.value?.loadSimilarQuiz(quizzes, nodeId)
}

// ========== Study Time Tracking ==========
let studyStartTime: number | null = null
let studyNodeId: string | null = null
let studyTickHandle: number | null = null

const flushStudyTime = () => {
  if (studyStartTime && studyNodeId) {
    const elapsed = Math.floor((Date.now() - studyStartTime) / 1000) // seconds
    if (elapsed > 0) {
      courseStore.recordStudyTime(elapsed, studyNodeId)
      studyStartTime = Date.now()
    }
  }
}

const startStudyTimer = (nodeId: string) => {
  flushStudyTime() // flush previous node's time
  studyStartTime = Date.now()
  studyNodeId = nodeId

  // Periodic flush every 15 seconds to keep stats fresh
  if (studyTickHandle !== null) clearInterval(studyTickHandle)
  studyTickHandle = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      flushStudyTime()
    }
  }, 15000)
}

const stopStudyTimer = () => {
  flushStudyTime()
  studyStartTime = null
  studyNodeId = null
  if (studyTickHandle !== null) {
    clearInterval(studyTickHandle)
    studyTickHandle = null
  }
}

// Track node switches — mark as completed when content exists
watch(() => courseStore.currentNode, (node) => {
  if (node && node.node_content && node.node_content.length > 50) {
    courseStore.markNodeAsCompleted(node.node_id)
    courseStore.markNodeAsRead(node.node_id)
  }
  if (node) {
    startStudyTimer(node.node_id)
  } else {
    stopStudyTimer()
  }
}, { immediate: true })

// Pause/resume on visibility change
const handleVisibilityChange = () => {
  if (document.visibilityState === 'visible' && courseStore.currentNode) {
    studyStartTime = Date.now() // reset start on resume
  } else {
    flushStudyTime()
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopStudyTimer()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
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

.collapse-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 48px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-left: none;
  border-radius: 0 8px 8px 0;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
}

.collapse-indicator:hover {
  color: #6366f1;
  background: #eef2ff;
  border-color: #c7d2fe;
  width: 28px;
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
.slide-in-left-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-in-left-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}

.slide-in-left-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}
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
