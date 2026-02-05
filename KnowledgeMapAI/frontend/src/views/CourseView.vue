<template>
  <div ref="containerRef" class="flex-1 flex overflow-hidden relative min-h-0 w-full h-full">
    
    <!-- Mobile Overlay -->
    <div v-if="isMobile && (mobileShowLeft || mobileShowRight)" 
         class="absolute inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
         @click="closeMobileSidebars">
    </div>

    <!-- Mobile Toggles -->
    <div v-if="isMobile" class="absolute top-4 left-4 z-30">
        <button @click="mobileShowLeft = !mobileShowLeft" class="p-2 bg-white/80 backdrop-blur-md rounded-lg shadow-sm border border-slate-200 text-slate-600">
            <el-icon><Menu /></el-icon>
        </button>
    </div>
    <div v-if="isMobile" class="absolute top-4 right-4 z-30">
        <button @click="mobileShowRight = !mobileShowRight" class="p-2 bg-white/80 backdrop-blur-md rounded-lg shadow-sm border border-slate-200 text-slate-600">
            <el-icon><ChatDotRound /></el-icon>
        </button>
    </div>

    <CourseTree 
      v-show="(!isMobile || mobileShowLeft) && !isLeftCollapsed && !courseStore.isFocusMode"
      :style="{ width: isMobile ? '85%' : leftSidebarWidth + 'px' }" 
      :class="[
        'flex-shrink-0 !transition-none overflow-hidden',
        isMobile ? 'absolute left-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-10 animate-fade-in-up stagger-1'
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
    
    <!-- Left Resizer (Desktop Only) -->
    <div 
      v-if="!isMobile && !isLeftCollapsed && !courseStore.isFocusMode"
      class="w-4 -ml-2 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative transition-colors"
      @mousedown="startResizeLeft"
      @dblclick="resetLeftSidebar"
    >
        <!-- Vertical Line (Always subtle, darker on hover/active) -->
        <div 
            class="absolute inset-y-0 w-px transition-colors duration-300"
            :class="isResizingLeft ? 'bg-primary-200' : 'bg-transparent group-hover:bg-slate-200'"
        ></div>
        
        <!-- Handle Pill -->
        <div 
            class="w-1.5 h-12 rounded-full backdrop-blur-sm transition-all duration-300 shadow-sm"
            :class="isResizingLeft 
                ? 'bg-primary-500 h-16 w-2 shadow-[0_0_10px_rgba(99,102,241,0.5)]' 
                : 'bg-slate-300/80 group-hover:bg-primary-400 group-hover:h-16 group-hover:w-2'"
        ></div>
    </div>

    <ContentArea class="flex-1 overflow-hidden relative z-0 animate-fade-in-up stagger-2" />

    <!-- Right Resizer (Desktop Only) -->
    <div 
      v-if="!isMobile && !courseStore.isFocusMode"
      class="w-4 -mr-2 z-30 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none relative"
      @mousedown="startResizeRight"
      @dblclick="resetRightSidebar"
    >
        <!-- Hover Line -->
        <div class="absolute inset-y-4 w-px bg-white/0 group-hover:bg-primary-300/50 transition-colors duration-300"></div>
        <!-- Handle -->
        <div class="w-1 h-8 rounded-full bg-slate-300/30 backdrop-blur-sm group-hover:bg-primary-400 group-hover:h-16 group-hover:w-1 group-hover:shadow-[0_0_10px_rgba(139,92,246,0.6)] transition-all duration-300"></div>
    </div>

    <ChatPanel 
      v-show="(!isMobile || mobileShowRight) && !courseStore.isFocusMode"
      :style="{ width: isMobile ? '85%' : rightSidebarWidth + 'px' }" 
      :class="[
        'flex-shrink-0 overflow-hidden',
        isMobile ? 'absolute right-0 top-0 bottom-0 z-50 bg-white shadow-2xl' : 'z-20 animate-fade-in-up stagger-3'
      ]"
    />
  </div>
</template>

<script setup lang="ts">
import CourseTree from '../components/CourseTree.vue'
import ContentArea from '../components/ContentArea.vue'
import ChatPanel from '../components/ChatPanel.vue'
import { useCourseStore } from '../stores/course'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu, ChatDotRound, Expand } from '@element-plus/icons-vue'

const courseStore = useCourseStore()
const route = useRoute()
const containerRef = ref<HTMLElement | null>(null)

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

// Sidebar Resizing Logic
const leftSidebarWidth = ref(280) // Reduced from 320 for better balance
const rightSidebarWidth = ref(360) // Reduced from 400 to prevent crowding
const isResizingLeft = ref(false)
const isResizingRight = ref(false)
const isAutoWidth = ref(true)

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
  isAutoWidth.value = true
}
const resetRightSidebar = () => { rightSidebarWidth.value = 400 }

const handlePreferredWidth = (width: number) => {
  if (isAutoWidth.value && !isMobile.value) {
    const newWidth = Math.max(280, Math.min(width, 500))
    leftSidebarWidth.value = newWidth
  }
}

const handleMouseMove = (e: MouseEvent) => {
  if (isMobile.value || !containerRef.value) return

  const containerRect = containerRef.value.getBoundingClientRect()

  if (isResizingLeft.value) {
    const newWidth = e.clientX - containerRect.left
    if (newWidth >= 200 && newWidth <= 500) { // Adjusted range
      leftSidebarWidth.value = newWidth
    }
  }
  
  if (isResizingRight.value) {
    const newWidth = containerRect.right - e.clientX
    if (newWidth >= 280 && newWidth <= 600) { // Adjusted min width
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

onMounted(() => {
  courseStore.fetchCourseList()
  checkMobile()
  window.addEventListener('resize', checkMobile)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
  window.removeEventListener('keydown', handleKeydown)
})
</script>
