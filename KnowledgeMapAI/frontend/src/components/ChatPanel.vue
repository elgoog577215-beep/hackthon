<template>
  <div class="h-full flex flex-col relative overflow-hidden">
    <!-- Header -->
    <div class="m-2 lg:m-4 mb-2 p-3 lg:p-4 z-20 relative flex items-center justify-between gap-3 glass-panel rounded-2xl">
        <div class="absolute inset-0 bg-gradient-to-r from-primary-50/30 to-primary-50/30 pointer-events-none rounded-2xl"></div>
        <div class="relative flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center shadow-lg shadow-primary-500/30 text-white animate-pulse-slow">
                <el-icon class="text-xl"><ChatDotRound /></el-icon>
            </div>
            <div>
                <div class="font-bold text-gray-800 font-display text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-gray-800 to-gray-600">AI 智能助手</div>
                <div class="flex items-center gap-1.5">
                    <div class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.6)]"></div>
                    <span class="text-[10px] font-medium text-gray-500 uppercase tracking-wider">在线</span>
                </div>
            </div>
        </div>
        <div class="relative z-10 flex gap-2">
            <button class="glass-icon-btn p-2 rounded-lg hover:bg-white/50 text-slate-500 hover:text-primary-600 transition-colors" @click="personaDialogVisible = true" title="设置画像">
                <el-icon :size="18"><Setting /></el-icon>
            </button>
            <button v-if="courseStore.chatHistory.length > 0" class="glass-icon-btn p-2 rounded-lg hover:bg-red-50 text-slate-500 hover:text-red-500 transition-colors" @click="courseStore.clearChat()" title="清空对话">
                <el-icon :size="18"><Delete /></el-icon>
            </button>
        </div>
    </div>
    
    <!-- Persona Settings Dialog -->
    <el-dialog
        v-model="personaDialogVisible"
        title="设置 AI 教学助手画像"
        width="400px"
        append-to-body
        class="glass-dialog"
        align-center
    >
        <div class="flex flex-col gap-4">
            <div class="text-sm text-gray-500 bg-blue-50/50 p-3 rounded-xl border border-blue-100">
                告诉 AI 你是谁，它将为你定制回答风格。
            </div>
            <div class="glass-input-wrapper">
                <el-input
                    v-model="courseStore.userPersona"
                    type="textarea"
                    :rows="4"
                    placeholder="例如：我是大一新生，喜欢通俗易懂的解释... 或：我是资深工程师，请直接讲底层原理..."
                    resize="none"
                    class="glass-textarea"
                />
            </div>
        </div>
        <template #footer>
            <div class="dialog-footer">
                <button class="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-xl font-medium shadow-lg shadow-primary-500/30 transition-all active:scale-95" @click="personaDialogVisible = false">保存设定</button>
            </div>
        </template>
    </el-dialog>
    
    <!-- Output Area -->
    <div class="flex-1 m-4 my-2 overflow-hidden relative glass-panel rounded-2xl flex flex-col">
        <div class="flex-1 overflow-auto p-5 space-y-6 custom-scrollbar relative scroll-smooth" ref="chatContainer">
            <!-- Background Pattern -->
            <div class="absolute inset-0 opacity-[0.03] pointer-events-none" style="background-image: radial-gradient(var(--el-color-primary) 1px, transparent 1px); background-size: 24px 24px;"></div>

            <!-- Empty States -->
            <div v-if="courseStore.chatHistory.length === 0" class="flex flex-col items-center justify-center mt-10 text-gray-400 opacity-80 animate-in fade-in zoom-in duration-500">
                <div class="w-24 h-24 bg-gradient-to-br from-gray-50 to-gray-100 rounded-[2rem] flex items-center justify-center mb-6 shadow-[0_8px_30px_rgba(0,0,0,0.04)] ring-1 ring-white/60 relative overflow-hidden group">
                    <div class="absolute inset-0 bg-gradient-to-tr from-primary-500/5 via-primary-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
                    <div class="w-14 h-14 bg-white rounded-2xl shadow-sm flex items-center justify-center text-3xl animate-float relative z-10 text-primary-500">
                        <el-icon><ChatDotRound /></el-icon>
                    </div>
                    <!-- Decor dots -->
                    <div class="absolute top-6 right-6 w-2 h-2 rounded-full bg-primary-400/30 animate-ping"></div>
                </div>
                <span class="text-sm font-bold text-gray-500 bg-white/60 backdrop-blur-md px-5 py-2 rounded-full border border-white/50 shadow-sm flex items-center gap-2">
                    <el-icon class="text-primary-500"><MagicStick /></el-icon>
                    有什么不懂的？随时问我
                </span>
            </div>

            <!-- QA History -->
            <div v-for="(msg, idx) in courseStore.chatHistory" :key="idx" 
                class="flex flex-col gap-2 animate-fade-in-up" :style="{ animationDelay: `${idx * 50}ms` }">
                
                <div :class="['p-5 rounded-3xl text-sm max-w-[90%] transition-all relative overflow-hidden shadow-sm backdrop-blur-md group', 
                    msg.type === 'user' 
                        ? 'bg-gradient-to-br from-primary-600 to-primary-700 text-white self-end rounded-tr-sm shadow-[0_8px_20px_-4px_rgba(139,92,246,0.3)] ring-1 ring-white/20 border-t border-white/20' 
                        : 'bg-white/80 border border-white/60 !rounded-tl-sm self-start hover:bg-white/90 transition-all shadow-[0_4px_20px_-4px_rgba(148,163,184,0.1)] hover:shadow-[0_8px_25px_-5px_rgba(148,163,184,0.15)]']">
                    
                    <!-- Noise Texture Overlay for subtle detail -->
                    <div class="absolute inset-0 opacity-[0.1] pointer-events-none mix-blend-overlay bg-[url('data:image/svg+xml,%3Csvg%20viewBox=%220%200%20200%20200%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter%20id=%22noise%22%3E%3CfeTurbulence%20type=%22fractalNoise%22%20baseFrequency=%220.8%22%20numOctaves=%223%22%20stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect%20width=%22100%25%22%20height=%22100%25%22%20filter=%22url(%23noise)%22%20opacity=%221%22/%3E%3C/svg%3E')]"></div>

                    <!-- Shimmer for AI messages -->
                    <div v-if="msg.type === 'ai'" class="absolute inset-0 bg-gradient-to-r from-transparent via-white/60 to-transparent w-1/2 -skew-x-12 translate-x-[-200%] animate-[shimmer_4s_infinite] pointer-events-none"></div>

                    <!-- Reflection for User messages -->
                    <div v-if="msg.type === 'user'" class="absolute inset-0 bg-gradient-to-b from-white/20 to-transparent opacity-50 pointer-events-none"></div>
                    <div v-if="msg.type === 'user'" class="absolute -bottom-10 -right-10 w-32 h-32 bg-primary-600/30 blur-3xl rounded-full pointer-events-none"></div>

                    <div v-if="msg.type === 'ai' && typeof msg.content === 'object'" class="relative z-10">
                         <!-- Header: AI Icon + Title -->
                        <div class="flex items-center gap-2 mb-3 text-xxs font-bold text-primary-600 uppercase tracking-wider border-b border-gray-100/80 pb-2">
                            <div class="w-5 h-5 rounded bg-primary-50 flex items-center justify-center text-primary-500">
                                <el-icon><MagicStick /></el-icon>
                            </div>
                            <span>AI Analysis</span>
                        </div>
                        <div v-if="msg.content.answer" class="prose prose-sm prose-slate mb-3 leading-relaxed">
                            <div v-html="renderMarkdown(msg.content.answer)"></div>
                        </div>
                        <div v-if="msg.content.quiz" class="mt-3 bg-primary-50/50 p-4 rounded-xl border border-primary-100/50">
                            <div class="text-xs font-bold text-primary-700 mb-2 flex items-center gap-2">
                                <el-icon><QuestionFilled /></el-icon> 思考题
                            </div>
                            <div class="text-slate-700 font-medium">{{ msg.content.quiz.question }}</div>
                            <div class="mt-2 space-y-1">
                                <div v-for="(opt, oIdx) in msg.content.quiz.options" :key="oIdx" class="text-xs text-slate-500 bg-white/60 px-2 py-1.5 rounded border border-white/50">
                                    {{ (['A','B','C','D'][oIdx] as string) }}. {{ opt }}
                                </div>
                            </div>
                        </div>
                    </div>
                    <div v-else class="relative z-10 leading-relaxed whitespace-pre-wrap font-medium" :class="msg.type === 'user' ? 'text-white' : 'text-slate-700'">
                        <div v-if="msg.type === 'ai'" v-html="renderMarkdown(msg.content)"></div>
                        <span v-else>{{ msg.content }}</span>
                    </div>
                </div>
            </div>
            
            <div v-if="courseStore.chatLoading" class="flex gap-2 p-4 animate-pulse items-center">
                <div class="w-8 h-8 rounded-full bg-slate-200"></div>
                <div class="h-8 bg-slate-100 rounded-xl w-32"></div>
            </div>
        </div>
        
        <!-- Floating Input Area -->
        <div class="p-4 pt-2 bg-gradient-to-t from-white/80 to-transparent backdrop-blur-sm relative z-20">
            <div class="relative group shadow-lg shadow-primary-500/5 rounded-2xl bg-white border border-slate-200 focus-within:border-primary-400 focus-within:ring-4 focus-within:ring-primary-500/10 transition-all duration-300">
                <textarea
                    v-model="inputMessage"
                    class="w-full bg-transparent border-none rounded-2xl px-4 py-3 pr-12 text-sm focus:ring-0 resize-none h-[52px] max-h-[120px] custom-scrollbar placeholder:text-slate-400 text-slate-700"
                    placeholder="输入问题，Ctrl + Enter 发送..."
                    @keydown="handleKeydown"
                ></textarea>
                
                <button 
                    class="absolute right-2 bottom-2 p-2 rounded-xl transition-all duration-300 flex items-center justify-center"
                    :class="inputMessage.trim() ? 'bg-primary-600 text-white shadow-md shadow-primary-500/30 hover:scale-105 active:scale-95' : 'bg-slate-100 text-slate-400 cursor-not-allowed'"
                    @click="sendMessage"
                    :disabled="!inputMessage.trim() || courseStore.chatLoading"
                >
                    <el-icon v-if="courseStore.chatLoading" class="is-loading"><Loading /></el-icon>
                    <el-icon v-else :size="18"><Position /></el-icon>
                </button>
            </div>
            <div class="text-center mt-2">
                <span class="text-[10px] text-slate-400 font-medium bg-white/50 px-2 py-0.5 rounded-full border border-slate-100">AI 内容由大模型生成，请仔细甄别</span>
            </div>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useCourseStore } from '../stores/course'
import { ChatDotRound, Position, Loading, MagicStick, Setting, Delete, QuestionFilled } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const courseStore = useCourseStore()
const inputMessage = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const personaDialogVisible = ref(false)

const scrollToBottom = async () => {
    await nextTick()
    if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
}

watch(() => courseStore.chatHistory, () => {
    scrollToBottom()
}, { deep: true })

const sendMessage = async () => {
    if (!inputMessage.value.trim() || courseStore.chatLoading) return
    
    const msg = inputMessage.value
    inputMessage.value = ''
    
    // Optimistic UI: Add user message immediately
    courseStore.chatHistory.push({
        type: 'user',
        content: msg
    })
    
    await scrollToBottom()
    
    await courseStore.sendMessage(msg)
}

const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        sendMessage()
    }
}

const renderMarkdown = (content: string) => {
    if (typeof content !== 'string') return ''
    const rawHtml = marked(content) as string
    return DOMPurify.sanitize(rawHtml)
}

onMounted(() => {
    scrollToBottom()
})
</script>

<style scoped>
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

:deep(.glass-dialog) {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.5);
}

:deep(.glass-textarea .el-textarea__inner) {
    background-color: rgba(255, 255, 255, 0.5);
    box-shadow: none;
    border: 1px solid rgba(203, 213, 225, 0.6);
    border-radius: 12px;
    padding: 12px;
    transition: all 0.3s;
}

:deep(.glass-textarea .el-textarea__inner:focus) {
    background-color: white;
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}
</style>