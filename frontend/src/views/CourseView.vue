<template>
  <div ref="containerRef" class="flex-1 flex overflow-hidden relative min-h-0 w-full h-full">
    
    <!-- Mobile Overlay - Improved z-index and click handling -->
    <Transition name="fade">
      <div v-if="isMobile && (mobileShowLeft || mobileShowRight)" 
           class="fixed inset-0 bg-slate-900/30 backdrop-blur-sm z-[60]"
           @click="closeMobileSidebars">
      </div>
    </Transition>

    <!-- Mobile Toggles - Better positioning and styling -->
    <div v-if="isMobile && !courseStore.isFocusMode" class="fixed top-20 left-4 z-50">
        <button 
          @click="toggleLeftSidebar" 
          class="w-10 h-10 bg-white/95 backdrop-blur-md rounded-xl shadow-lg border border-slate-200 text-slate-600 flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95"
          :class="{ 'bg-primary-50 border-primary-200 text-primary-600': mobileShowLeft }"
        >
            <el-icon :size="18"><Menu /></el-icon>
        </button>
    </div>
    <div v-if="isMobile && !courseStore.isFocusMode" class="fixed top-20 right-4 z-50">
        <button 
          @click="toggleRightSidebar" 
          class="w-10 h-10 bg-white/95 backdrop-blur-md rounded-xl shadow-lg border border-slate-200 text-slate-600 flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95"
          :class="{ 'bg-primary-50 border-primary-200 text-primary-600': mobileShowRight }"
        >
            <el-icon :size="18"><ChatDotRound /></el-icon>
        </button>
    </div>

    <CourseTree
      v-show="(!isMobile || mobileShowLeft) && !isLeftCollapsed && !courseStore.isFocusMode"
      :style="{ width: isMobile ? '85%' : leftSidebarWidth + 'px' }"
      :class="[
        'flex-shrink-0 overflow-hidden transition-all duration-300 ease-out',
        isMobile ? 'absolute left-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-10 animate-fade-in-up stagger-1',
        isResizingLeft ? '!transition-none' : ''
      ]"
      @update:preferredWidth="handlePreferredWidth"
      @node-selected="mobileShowLeft = false"
      @toggle-sidebar="isLeftCollapsed = true"
    />
    
    <!-- Collapsed Sidebar Trigger -->
    <div v-if="isLeftCollapsed && !isMobile && !courseStore.isFocusMode" class="absolute left-4 top-4 z-50">
        <button 
            @click="isLeftCollapsed = false" 
            class="p-2 glass-panel-tech rounded-xl text-slate-500 hover:text-primary-600 shadow-lg hover:scale-105 transition-all"
            title="展开侧边栏"
        >
            <el-icon :size="20"><Expand /></el-icon>
        </button>
    </div>
    
    <!-- Left Resizer (Desktop Only) - Optimized Position -->
    <div 
      v-if="!isMobile && !isLeftCollapsed && !courseStore.isFocusMode"
      class="w-1 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative transition-colors hover:w-2 hover:-ml-0.5 transition-all duration-200"
      @mousedown="startResizeLeft"
      @dblclick="resetLeftSidebar"
    >
        <!-- Vertical Line (Always subtle, darker on hover/active) -->
        <div 
            class="absolute inset-y-0 w-px transition-colors duration-300"
            :class="isResizingLeft ? 'bg-primary-300' : 'bg-transparent group-hover:bg-slate-200'"
        ></div>
        
        <!-- Handle Pill - More Compact -->
        <div 
            class="w-0.5 h-10 rounded-full backdrop-blur-sm transition-all duration-300 shadow-sm"
            :class="isResizingLeft 
                ? 'bg-primary-500 h-14 w-1 shadow-[0_0_8px_rgba(99,102,241,0.4)]' 
                : 'bg-slate-300/60 group-hover:bg-primary-400 group-hover:h-12 group-hover:w-1'"
        ></div>
    </div>

    <ContentArea class="flex-1 overflow-hidden relative z-0 animate-fade-in-up stagger-2" />

    <!-- Right Resizer (Desktop Only) - Optimized Position -->
    <div 
      v-if="!isMobile && !courseStore.isFocusMode"
      class="w-1 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative hover:w-2 hover:-mr-0.5 transition-all duration-200"
      @mousedown="startResizeRight"
      @dblclick="resetRightSidebar"
    >
        <!-- Hover Line -->
        <div class="absolute inset-y-4 w-px bg-white/0 group-hover:bg-primary-300/50 transition-colors duration-300"></div>
        <!-- Handle - More Compact -->
        <div class="w-0.5 h-10 rounded-full bg-slate-300/40 backdrop-blur-sm group-hover:bg-primary-400 group-hover:h-12 group-hover:w-1 group-hover:shadow-[0_0_8px_rgba(139,92,246,0.4)] transition-all duration-300"></div>
    </div>

    <!-- Right Sidebar: Chat or Stats -->
    <div
      v-show="(!isMobile || mobileShowRight) && !courseStore.isFocusMode"
      :style="{ width: isMobile ? '85%' : rightSidebarWidth + 'px' }"
      :class="[
        'flex-shrink-0 overflow-hidden h-full',
        isMobile ? 'absolute right-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-20 animate-fade-in-up stagger-3'
      ]"
    >
      <!-- Tab Switcher - Moved to right side -->
      <div class="absolute top-2 right-4 z-30 flex bg-white/90 backdrop-blur-md rounded-full p-1 shadow-sm border border-slate-100">
        <button
          v-for="tab in ['chat', 'stats']"
          :key="tab"
          @click="activeRightTab = tab"
          class="px-3 py-1 text-xs font-medium rounded-full transition-all"
          :class="activeRightTab === tab ? 'bg-primary-500 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'"
        >
          {{ tab === 'chat' ? 'AI助手' : '学习统计' }}
        </button>
      </div>

      <ChatPanel v-show="activeRightTab === 'chat'" class="h-full pt-10" />
      <LearningStats v-show="activeRightTab === 'stats'" class="h-full pt-10" />
    </div>
  </div>
</template>

<script setup lang="ts">
import CourseTree from '../components/CourseTree.vue'
import ContentArea from '../components/ContentArea.vue'
import ChatPanel from '../components/ChatPanel.vue'
import LearningStats from '../components/LearningStats.vue'
import { useCourseStore } from '../stores/course'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu, ChatDotRound, Expand } from '@element-plus/icons-vue'

const courseStore = useCourseStore()
const route = useRoute()
const containerRef = ref<HTMLElement | null>(null)

// Restore state (tasks, logs, etc.) but DO NOT redirect automatically
courseStore.restoreGenerationState()

// Restore learning stats
courseStore.restoreLearningStats()

// Restore quiz data
courseStore.restoreQuizData()

// Right sidebar tab
const activeRightTab = ref('chat')

// Mobile Logic
const isMobile = ref(false)
const mobileShowLeft = ref(false)
const mobileShowRight = ref(false)
const isLeftCollapsed = ref(false)

const checkMobile = () => {
    isMobile.value = window.innerWidth < 768
    if (!isMobile.value) {
        mobileShowLeft.value = false
        mobileShowRight.value = false
    }
}

const closeMobileSidebars = () => {
    mobileShowLeft.value = false
    mobileShowRight.value = false
}

// Toggle functions with mutual exclusivity
const toggleLeftSidebar = () => {
    mobileShowLeft.value = !mobileShowLeft.value
    if (mobileShowLeft.value) {
        mobileShowRight.value = false
    }
}

const toggleRightSidebar = () => {
    mobileShowRight.value = !mobileShowRight.value
    if (mobileShowRight.value) {
        mobileShowLeft.value = false
    }
}

// Sidebar Resizing Logic - Compact Width
// Handles mouse events to resize sidebars with min/max constraints
const leftSidebarWidth = ref(300) // Fixed width
const rightSidebarWidth = ref(window.innerWidth < 1440 ? 280 : 340) // Optimized for laptops
const isResizingLeft = ref(false)
const isResizingRight = ref(false)
const isAutoWidth = ref(false)

const handleBeforeUnload = () => {
    courseStore.persistGenerationState()
}

const startResizeLeft = () => { 
  isResizingLeft.value = true 
  isAutoWidth.value = false
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
const startResizeRight = () => { 
  isResizingRight.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const resetLeftSidebar = () => { 
  leftSidebarWidth.value = 300
}
const resetRightSidebar = () => { rightSidebarWidth.value = 400 }

const handlePreferredWidth = (width: number) => {
  if (isAutoWidth.value && !isMobile.value && !isResizingLeft.value) {
    // Smooth width transition with constraints
    // Min: 200px (compact), Max: 400px (comfortable reading)
    const targetWidth = Math.max(200, Math.min(width, 400))

    // Use smooth interpolation for gradual changes
    const currentWidth = leftSidebarWidth.value
    const diff = targetWidth - currentWidth

    // Only update if change is significant (> 10px) to avoid jitter
    if (Math.abs(diff) > 10) {
      // Smooth transition: move 30% towards target
      const newWidth = Math.round(currentWidth + diff * 0.3)
      leftSidebarWidth.value = newWidth
    }
  }
}

const handleMouseMove = (e: MouseEvent) => {
  if (isMobile.value || !containerRef.value) return

  const containerRect = containerRef.value.getBoundingClientRect()

  if (isResizingLeft.value) {
    const newWidth = e.clientX - containerRect.left
    if (newWidth >= 180 && newWidth <= 400) { // Compact range for better UX
      leftSidebarWidth.value = newWidth
    }
  }
  
  if (isResizingRight.value) {
    const newWidth = containerRect.right - e.clientX
    if (newWidth >= 280 && newWidth <= 500) { // Optimized range
      rightSidebarWidth.value = newWidth
    }
  }
}

const handleMouseUp = () => {
  isResizingLeft.value = false
  isResizingRight.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// Watch for route changes to update selected course
watch(
  () => route.params.courseId,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      if (courseStore.currentCourseId !== newId) {
        courseStore.currentCourseId = newId
        await courseStore.loadCourse(newId)
      }
    } else {
      courseStore.currentCourseId = ''
      courseStore.courseTree = []
    }
  },
  { immediate: true }
)

const handleKeydown = (e: KeyboardEvent) => {
    // Ignore if input/textarea is focused or if modifier keys are pressed
    if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName) || (e.target as HTMLElement).isContentEditable) return
    if (e.ctrlKey || e.metaKey || e.altKey) return

    if (e.key.toLowerCase() === 'f') {
        courseStore.isFocusMode = !courseStore.isFocusMode
        e.preventDefault()
    } else if (e.key === '[') {
        if (isMobile.value) {
            mobileShowLeft.value = !mobileShowLeft.value
        } else {
            isLeftCollapsed.value = !isLeftCollapsed.value
        }
    }
}

// Study time tracking
let studyStartTime: number | null = null
let currentNodeId: string | null = null
let studyInterval: number | null = null

const startStudyTracking = () => {
  studyStartTime = Date.now()
  currentNodeId = courseStore.currentNode?.node_id || null

  // Record study time every minute
  studyInterval = window.setInterval(() => {
    if (studyStartTime && document.visibilityState === 'visible') {
      const elapsedMinutes = Math.floor((Date.now() - studyStartTime) / 60000)
      if (elapsedMinutes > 0) {
        courseStore.recordStudyTime(elapsedMinutes, currentNodeId || undefined)
        studyStartTime = Date.now() // Reset start time
      }
    }
  }, 60000) // Every minute
}

const stopStudyTracking = () => {
  if (studyInterval) {
    clearInterval(studyInterval)
    studyInterval = null
  }

  // Record remaining time
  if (studyStartTime) {
    const elapsedMinutes = Math.round((Date.now() - studyStartTime) / 60000)
    if (elapsedMinutes > 0) {
      courseStore.recordStudyTime(elapsedMinutes, currentNodeId || undefined)
    }
    studyStartTime = null
  }
}

// Handle visibility change
const handleVisibilityChange = () => {
  if (document.visibilityState === 'hidden') {
    // Pause tracking when tab is hidden
    if (studyStartTime) {
      const elapsedMinutes = Math.round((Date.now() - studyStartTime) / 60000)
      if (elapsedMinutes > 0) {
        courseStore.recordStudyTime(elapsedMinutes, currentNodeId || undefined)
      }
      studyStartTime = null
    }
  } else {
    // Resume tracking when tab becomes visible
    studyStartTime = Date.now()
    currentNodeId = courseStore.currentNode?.node_id || null
  }
}

onMounted(() => {
  courseStore.fetchCourseList()
  checkMobile()
  window.addEventListener('resize', checkMobile)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('visibilitychange', handleVisibilityChange)

  // Start study tracking
  startStudyTracking()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('visibilitychange', handleVisibilityChange)

  // Stop study tracking
  stopStudyTracking()
})
</script>

<style scoped>
/* Smooth transitions for all interactive elements */
button, .interactive {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Enhanced hover effects */
button:hover:not(:disabled) {
  transform: translateY(-1px);
}

button:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}

/* Focus ring animation */
button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.3);
}

/* Tab switcher animation */
.tab-indicator {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Sidebar slide animations */
.sidebar-enter-active,
.sidebar-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar-enter-from,
.sidebar-leave-to {
  transform: translateX(-100%);
}

/* Mobile overlay fade */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Resizer handle glow effect */
.resizer-handle {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.resizer-handle:hover {
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.4);
}

/* Content area smooth scroll */
:deep(.content-scroll) {
  scroll-behavior: smooth;
}

/* Ripple effect for buttons */
.ripple {
  position: relative;
  overflow: hidden;
}

.ripple::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0;
  height: 0;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition: width 0.6s, height 0.6s;
}

.ripple:active::after {
  width: 200%;
  height: 200%;
}
</style>
