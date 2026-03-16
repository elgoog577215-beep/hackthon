<template>
  <!-- Overlay backdrop (mobile only) -->
  <div v-if="isOverlayMode" class="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" @click="handleClose"></div>
  <div :class="panelClasses" class="h-full flex flex-col bg-white/95 backdrop-blur-xl border-l border-slate-200/60">
    <!-- Panel Header -->
    <div class="flex items-center justify-between px-4 h-12 border-b border-slate-200/50 flex-shrink-0 bg-white/70 backdrop-blur-md">
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-md shadow-primary-500/20 text-white flex-shrink-0">
          <el-icon :size="16"><ChatDotRound /></el-icon>
        </div>
        <span class="font-semibold text-slate-800 text-sm">AI 助手</span>
      </div>
      <button
        class="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
        @click="handleClose"
        title="关闭面板"
      >
        <el-icon :size="18"><Close /></el-icon>
      </button>
    </div>

    <!-- Chat Area (scrollable) -->
    <div ref="chatContainer" class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
      <!-- Empty State -->
      <div v-if="courseStore.chatHistory.length === 0" class="flex flex-col items-center justify-center h-full text-slate-400">
        <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center mb-3 shadow-sm">
          <el-icon :size="24" class="text-primary-400"><ChatDotRound /></el-icon>
        </div>
        <p class="text-xs text-slate-400">选中文本后提问，或直接输入问题</p>
      </div>

      <!-- Messages -->
      <div v-for="(msg, idx) in courseStore.chatHistory" :key="idx" class="flex flex-col gap-1">
        <!-- User Message -->
        <div v-if="msg.type === 'user'" class="self-end max-w-[85%]">
          <div class="px-3 py-2 rounded-xl rounded-tr-sm bg-gradient-to-br from-primary-500 to-primary-600 text-white text-sm leading-relaxed whitespace-pre-wrap shadow-sm">
            {{ msg.content }}
          </div>
        </div>

        <!-- AI Message (object content) -->
        <div v-else-if="msg.type === 'ai' && typeof msg.content === 'object'" class="self-start max-w-[95%]">
          <div class="p-3 rounded-xl rounded-tl-sm bg-white border border-slate-100 shadow-sm">
            <div class="flex items-center gap-1.5 mb-1.5 text-xs font-semibold text-primary-600">
              <el-icon :size="12"><MagicStick /></el-icon>
              <span>AI</span>
            </div>
            <div v-if="msg.content.answer" class="prose prose-sm prose-slate leading-relaxed">
              <MarkdownRenderer :content="msg.content.answer" />
            </div>
            <div v-else-if="msg.content.core_answer" class="prose prose-sm prose-slate leading-relaxed">
              <MarkdownRenderer :content="msg.content.core_answer" />
            </div>
          </div>
        </div>

        <!-- AI Message (string content) -->
        <div v-else-if="msg.type === 'ai'" class="self-start max-w-[95%]">
          <div class="p-3 rounded-xl rounded-tl-sm bg-white border border-slate-100 shadow-sm prose prose-sm prose-slate leading-relaxed">
            <MarkdownRenderer :content="getMessageText(msg.content)" />
          </div>
        </div>
      </div>

      <!-- Loading Indicator — Thinking Robot -->
      <div v-if="courseStore.chatLoading" class="self-start max-w-[85%]">
        <div class="p-3 rounded-xl rounded-tl-sm bg-white border border-slate-100 shadow-sm">
          <div class="flex items-center gap-3">
            <!-- Animated robot face -->
            <div class="thinking-robot flex-shrink-0">
              <div class="robot-face">
                <div class="robot-eye left"></div>
                <div class="robot-eye right"></div>
                <div class="robot-mouth"></div>
              </div>
            </div>
            <div class="flex flex-col gap-1">
              <span class="text-xs font-medium text-slate-500">{{ thinkingText }}</span>
              <div class="flex gap-1">
                <span class="thinking-dot"></span>
                <span class="thinking-dot" style="animation-delay: 0.2s"></span>
                <span class="thinking-dot" style="animation-delay: 0.4s"></span>
              </div>
            </div>
            <button
              class="ml-auto flex-shrink-0 px-2 py-1 text-xs bg-white border border-slate-200 hover:border-red-300 hover:bg-red-50 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
              @click="courseStore.cancelChat()"
              title="停止生成"
            >
              停止
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Section: QuoteCard + Suggestions + Input -->
    <div class="flex-shrink-0 border-t border-slate-200/50 bg-white/80 backdrop-blur-md">
      <!-- Quote Card -->
      <div
        v-if="showQuoteCard && props.quoteText"
        class="mx-3 mt-3 px-3 py-2 flex items-center gap-2 bg-primary-50/50 border-l-3 border-primary-400 rounded-r-lg"
      >
        <span class="flex-1 text-xs text-slate-600 truncate" :title="props.quoteText">
          {{ props.quoteText }}
        </span>
        <button
          class="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded text-slate-400 hover:text-slate-600 hover:bg-white/60 transition-colors"
          @click="dismissQuote"
          title="取消引用"
        >
          <el-icon :size="14"><RefreshLeft /></el-icon>
        </button>
      </div>

      <!-- Suggestion Buttons -->
      <div
        v-if="showSuggestions && showQuoteCard && props.quoteText"
        class="mx-3 mt-2 flex flex-wrap gap-2"
      >
        <button
          v-for="suggestion in suggestions"
          :key="suggestion.label"
          class="px-3 py-1.5 text-xs bg-white hover:bg-primary-50 border border-slate-200 hover:border-primary-300 rounded-full text-slate-600 hover:text-primary-600 transition-all shadow-sm"
          @click="handleSuggestionClick(suggestion)"
        >
          {{ suggestion.label }}
        </button>
      </div>

      <!-- Input Area -->
      <div class="p-3">
        <div class="relative flex items-end gap-2">
          <textarea
            ref="inputRef"
            v-model="inputMessage"
            class="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-400/30 focus:border-primary-400 placeholder:text-slate-400 text-slate-700 leading-relaxed custom-scrollbar"
            :rows="1"
            placeholder="输入问题..."
            @keydown="handleKeydown"
          ></textarea>
          <button
            class="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 shadow-sm"
            :class="canSend
              ? 'bg-primary-500 hover:bg-primary-600 text-white shadow-primary-500/30'
              : 'bg-slate-100 text-slate-300 cursor-not-allowed'"
            :disabled="!canSend"
            @click="handleSend"
            title="发送"
          >
            <el-icon :size="16"><Promotion /></el-icon>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useCourseStore } from '../stores/course'
import type { AIContent } from '../stores/types'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { ChatDotRound, Close, MagicStick, RefreshLeft, Promotion } from '@element-plus/icons-vue'

// Props & Emits
const props = defineProps<{
  visible: boolean
  quoteText: string
  quoteNodeId: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update:visible', value: boolean): void
}>()

// Store
const courseStore = useCourseStore()

// Internal state
const showQuoteCard = ref(true)
const showSuggestions = ref(true)
const inputMessage = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

// Responsive layout
const windowWidth = ref(window.innerWidth)
const isOverlayMode = computed(() => windowWidth.value < 1024)

const panelClasses = computed(() => {
  if (isOverlayMode.value) {
    return 'fixed inset-y-0 right-0 w-full max-w-md z-50 shadow-2xl'
  }
  return 'w-1/3 min-w-[320px] max-w-[480px]'
})

const onResize = () => { windowWidth.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

// Suggestions config
const suggestions = [
  { label: '解释一下 →', action: '解释一下' },
  { label: '详细展开 →', action: '详细展开' },
  { label: '深入研究 →', action: '深入研究' },
]

// Computed
const canSend = computed(() => {
  return inputMessage.value.trim().length > 0 && !courseStore.chatLoading
})

// Thinking text rotation
const thinkingPhrases = ['正在思考', '翻阅笔记中', '组织语言中', '灵感涌现中', '认真分析中']
const thinkingIndex = ref(0)
const thinkingText = computed(() => thinkingPhrases[thinkingIndex.value % thinkingPhrases.length])
let thinkingTimer: ReturnType<typeof setInterval> | null = null

watch(() => courseStore.chatLoading, (loading) => {
  if (loading) {
    thinkingIndex.value = 0
    thinkingTimer = setInterval(() => { thinkingIndex.value++ }, 2000)
  } else if (thinkingTimer) {
    clearInterval(thinkingTimer)
    thinkingTimer = null
  }
})
onUnmounted(() => { if (thinkingTimer) clearInterval(thinkingTimer) })

// Helpers
const getMessageText = (content: string | AIContent): string => {
  if (typeof content === 'string') return content
  return content.core_answer || content.answer || ''
}

// Handlers (placeholder — real logic in task 1.2)
const handleClose = () => {
  emit('close')
  emit('update:visible', false)
}

const dismissQuote = () => {
  showQuoteCard.value = false
  showSuggestions.value = false
}

const handleSuggestionClick = (suggestion: { label: string; action: string }) => {
  if (!props.quoteText) return
  const prompt = `关于以下内容：\n"${props.quoteText}"\n\n请${suggestion.action}`
  showSuggestions.value = false
  courseStore.sendMessage(prompt)
}

const handleSend = () => {
  const msg = inputMessage.value.trim()
  if (!msg || courseStore.chatLoading) return
  inputMessage.value = ''
  courseStore.sendMessage(msg)
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// Auto-scroll to latest message
const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

watch(
  () => courseStore.chatHistory.length,
  () => scrollToBottom()
)

watch(
  () => courseStore.chatLoading,
  () => scrollToBottom()
)

// Task 1.4: Re-quote behavior — reset quote card and suggestions when new quote arrives
watch(
  () => props.quoteText,
  (newVal) => {
    if (newVal) {
      showQuoteCard.value = true
      showSuggestions.value = true
    }
  }
)
</script>

<style scoped>
.border-l-3 {
  border-left-width: 3px;
}

/* Thinking robot animation */
.thinking-robot {
  width: 36px;
  height: 36px;
  position: relative;
}

.robot-face {
  width: 36px;
  height: 32px;
  background: linear-gradient(135deg, #818cf8, #6366f1);
  border-radius: 8px 8px 10px 10px;
  position: relative;
  animation: robot-bob 1.5s ease-in-out infinite;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.robot-face::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 8px;
  height: 8px;
  background: #a5b4fc;
  border-radius: 50%;
  animation: antenna-glow 1s ease-in-out infinite alternate;
}

.robot-eye {
  position: absolute;
  top: 10px;
  width: 8px;
  height: 8px;
  background: white;
  border-radius: 50%;
  animation: robot-blink 3s ease-in-out infinite;
}

.robot-eye.left { left: 7px; }
.robot-eye.right { right: 7px; }

.robot-eye::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 4px;
  height: 4px;
  background: #1e1b4b;
  border-radius: 50%;
  animation: eye-look 4s ease-in-out infinite;
}

.robot-mouth {
  position: absolute;
  bottom: 6px;
  left: 50%;
  transform: translateX(-50%);
  width: 12px;
  height: 3px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 2px;
  animation: robot-talk 0.8s ease-in-out infinite;
}

.thinking-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #a5b4fc;
  border-radius: 50%;
  animation: dot-bounce 1.2s ease-in-out infinite;
}

@keyframes robot-bob {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  25% { transform: translateY(-2px) rotate(-2deg); }
  75% { transform: translateY(-2px) rotate(2deg); }
}

@keyframes robot-blink {
  0%, 42%, 44%, 100% { transform: scaleY(1); }
  43% { transform: scaleY(0.1); }
}

@keyframes eye-look {
  0%, 40% { transform: translateX(0); }
  45%, 55% { transform: translateX(2px); }
  60%, 100% { transform: translateX(0); }
}

@keyframes robot-talk {
  0%, 100% { width: 12px; height: 3px; border-radius: 2px; }
  50% { width: 10px; height: 6px; border-radius: 50%; }
}

@keyframes antenna-glow {
  from { background: #a5b4fc; box-shadow: 0 0 4px rgba(165, 180, 252, 0.5); }
  to { background: #c7d2fe; box-shadow: 0 0 8px rgba(199, 210, 254, 0.8); }
}

@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-6px); opacity: 1; }
}
</style>
