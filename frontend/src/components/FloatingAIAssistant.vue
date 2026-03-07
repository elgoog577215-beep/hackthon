<template>
  <!-- Floating Button -->
  <Transition name="fab-bounce">
    <button
      v-show="!isOpen"
      class="fixed z-[200] right-4 bottom-20 w-12 h-12 rounded-full shadow-lg flex items-center justify-center text-white cursor-pointer select-none transition-all duration-300 hover:scale-110 hover:shadow-xl active:scale-95 group"
      style="background: var(--gradient-primary, linear-gradient(135deg, #6366f1, #8b5cf6));"
      @click="open"
      title="AI 助手"
      aria-label="打开 AI 助手"
    >
      <el-icon :size="22"><ChatDotRound /></el-icon>
      <span v-if="hasNewMessage" class="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full border-2 border-white"></span>
    </button>
  </Transition>

  <!-- Fullscreen Overlay -->
  <Teleport to="body">
    <Transition name="ai-overlay">
      <div v-show="isOpen" class="fixed inset-0 z-[300] flex bg-white/95 backdrop-blur-xl">
        
        <!-- Left: Conversation Sidebar -->
        <div class="w-64 flex-shrink-0 border-r border-slate-200/60 bg-slate-50/80 flex flex-col h-full">
          <!-- Sidebar Header -->
          <div class="flex items-center justify-between px-4 h-14 border-b border-slate-200/60 flex-shrink-0">
            <div class="flex items-center gap-2">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-md" style="background: var(--gradient-primary);">
                <el-icon :size="16"><ChatDotRound /></el-icon>
              </div>
              <span class="font-semibold text-slate-700 text-sm">对话列表</span>
            </div>
            <button
              class="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-primary-600 hover:bg-white transition-all"
              @click="handleNewConversation"
              title="新建对话"
            >
              <el-icon :size="18"><Plus /></el-icon>
            </button>
          </div>

          <!-- Conversation List -->
          <div class="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            <div
              v-for="conv in courseStore.conversations"
              :key="conv.id"
              class="group relative flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200"
              :class="conv.id === courseStore.currentConversationId
                ? 'bg-white shadow-sm border border-primary-200/60 text-primary-700'
                : 'hover:bg-white/60 text-slate-600 hover:text-slate-800'"
              @click="switchTo(conv.id)"
              @dblclick="startRename(conv)"
            >
              <el-icon :size="14" class="flex-shrink-0 opacity-60"><ChatLineSquare /></el-icon>
              
              <!-- Rename Input -->
              <input
                v-if="renamingId === conv.id"
                ref="renameInputRef"
                v-model="renameValue"
                class="flex-1 min-w-0 text-sm bg-transparent border-none outline-none px-0"
                @blur="finishRename(conv.id)"
                @keydown.enter="finishRename(conv.id)"
                @keydown.escape="cancelRename"
                @click.stop
              />
              <span v-else class="flex-1 min-w-0 text-sm truncate">{{ conv.name }}</span>

              <!-- Message count -->
              <span v-if="conv.messages.length > 0 && renamingId !== conv.id" class="text-[10px] text-slate-400 flex-shrink-0">{{ conv.messages.length }}</span>

              <!-- Actions (visible on hover) -->
              <div v-if="renamingId !== conv.id" class="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 bg-white/90 rounded-lg px-0.5 shadow-sm border border-slate-100">
                <button class="w-6 h-6 flex items-center justify-center text-slate-400 hover:text-primary-600 rounded transition-colors" @click.stop="startRename(conv)" title="重命名">
                  <el-icon :size="12"><Edit /></el-icon>
                </button>
                <button
                  v-if="courseStore.conversations.length > 1"
                  class="w-6 h-6 flex items-center justify-center text-slate-400 hover:text-red-500 rounded transition-colors"
                  @click.stop="deleteConv(conv.id)"
                  title="删除"
                >
                  <el-icon :size="12"><Delete /></el-icon>
                </button>
              </div>
            </div>

            <div v-if="courseStore.conversations.length === 0" class="text-center text-xs text-slate-400 py-8">
              暂无对话
            </div>
          </div>
        </div>

        <!-- Right: Chat Area -->
        <div class="flex-1 flex flex-col min-w-0 h-full">
          <!-- Top Bar -->
          <div class="flex items-center justify-between px-4 sm:px-6 h-14 border-b border-slate-200/60 bg-white/80 backdrop-blur-md flex-shrink-0">
            <div class="flex items-center gap-3 min-w-0">
              <div class="font-semibold text-slate-800 text-sm sm:text-base truncate">
                {{ currentConvName }}
              </div>
              <div class="flex items-center gap-1 flex-shrink-0">
                <div class="w-1.5 h-1.5 rounded-full bg-emerald-400"></div>
                <span class="text-xs text-slate-400">在线</span>
              </div>
            </div>
            <button
              class="w-10 h-10 rounded-xl flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all flex-shrink-0"
              @click="close"
              title="关闭 (Esc)"
              aria-label="关闭 AI 助手"
            >
              <el-icon :size="22"><Close /></el-icon>
            </button>
          </div>

          <!-- Chat Panel Container -->
          <div class="flex-1 min-h-0">
            <ChatPanel class="h-full" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ChatDotRound, Close, Plus, Edit, Delete, ChatLineSquare } from '@element-plus/icons-vue'
import ChatPanel from './ChatPanel.vue'
import { useCourseStore } from '../stores/course'

const courseStore = useCourseStore()
const isOpen = ref(false)
const hasNewMessage = ref(false)

// Rename state
const renamingId = ref('')
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement[]>([])

const currentConvName = computed(() => {
  const conv = courseStore.conversations.find(c => c.id === courseStore.currentConversationId)
  return conv?.name || 'AI 助手'
})

const open = () => {
  isOpen.value = true
  hasNewMessage.value = false
  courseStore.initConversations()
}

const close = () => {
  courseStore.syncCurrentConversation()
  courseStore.saveConversations()
  isOpen.value = false
}

const handleNewConversation = () => {
  courseStore.createConversation()
}

const switchTo = (id: string) => {
  if (renamingId.value) return
  courseStore.switchConversation(id)
}

const startRename = (conv: { id: string; name: string }) => {
  renamingId.value = conv.id
  renameValue.value = conv.name
  nextTick(() => {
    const inputs = renameInputRef.value
    if (inputs && inputs.length > 0) {
      inputs[0]!.focus()
      inputs[0]!.select()
    }
  })
}

const finishRename = (id: string) => {
  if (renameValue.value.trim()) {
    courseStore.renameConversation(id, renameValue.value)
  }
  renamingId.value = ''
}

const cancelRename = () => {
  renamingId.value = ''
}

const deleteConv = (id: string) => {
  courseStore.deleteConversation(id)
}

// Watch store flag to auto-open when triggered from other components
watch(() => courseStore.showFloatingAI, (val) => {
  if (val) {
    open()
    courseStore.showFloatingAI = false
  }
})

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isOpen.value) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.fab-bounce-enter-active {
  animation: fab-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.fab-bounce-leave-active {
  animation: fab-out 0.2s ease-in;
}
@keyframes fab-in {
  0% { transform: scale(0) rotate(-45deg); opacity: 0; }
  100% { transform: scale(1) rotate(0); opacity: 1; }
}
@keyframes fab-out {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(0); opacity: 0; }
}

.ai-overlay-enter-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.ai-overlay-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.ai-overlay-enter-from {
  opacity: 0;
  transform: translateY(100%) scale(0.95);
}
.ai-overlay-leave-to {
  opacity: 0;
  transform: translateY(30%) scale(0.98);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 4px;
}
</style>
