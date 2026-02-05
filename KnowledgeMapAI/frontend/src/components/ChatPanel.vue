<template>
  <div class="h-full flex flex-col relative overflow-hidden">
    <!-- Header -->
    <div class="m-2 lg:m-4 mb-2 p-3 lg:p-4 z-20 relative flex items-center justify-between gap-3 glass-panel-tech rounded-2xl">
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
            <button class="glass-icon-btn" @click="personaDialogVisible = true" title="设置画像">
                <el-icon :size="16"><Setting /></el-icon>
            </button>
            <button v-if="courseStore.chatHistory.length > 0" class="glass-icon-btn danger" @click="courseStore.clearChat()" title="清空对话">
                <el-icon :size="16"><Delete /></el-icon>
            </button>
        </div>
    </div>
    
    <!-- Persona Settings Dialog -->
    <el-dialog
        v-model="personaDialogVisible"
        title="设置 AI 教学助手画像"
        width="400px"
        append-to-body
    >
        <div class="flex flex-col gap-4">
            <div class="text-sm text-gray-500">
                告诉 AI 你是谁，它将为你定制回答风格。
            </div>
            <div class="glass-input">
                <el-input
                    v-model="courseStore.userPersona"
                    type="textarea"
                    :rows="4"
                    placeholder="例如：我是大一新生，喜欢通俗易懂的解释... 或：我是资深工程师，请直接讲底层原理..."
                    resize="none"
                />
            </div>
        </div>
        <template #footer>
            <div class="dialog-footer">
                <button class="glass-button-primary !px-6 !py-2" @click="personaDialogVisible = false">保存设定</button>
            </div>
        </template>
    </el-dialog>
    
    <!-- Output Area -->
    <div class="flex-1 m-4 my-2 overflow-hidden relative glass-panel-tech rounded-2xl flex flex-col">
        <div class="flex-1 overflow-auto p-5 space-y-6 custom-scrollbar relative" ref="chatContainer">
            <!-- Background Pattern -->
            <div class="absolute inset-0 opacity-[0.03] pointer-events-none" style="background-image: radial-gradient(var(--color-primary-500) 1px, transparent 1px); background-size: 24px 24px;"></div>

            <!-- Empty States -->
            <div v-if="courseStore.chatHistory.length === 0" class="flex flex-col items-center justify-center mt-10 text-gray-400 opacity-80 animate-in fade-in zoom-in duration-500">
            <div class="w-24 h-24 bg-gradient-to-br from-gray-50 to-gray-100 rounded-5xl flex items-center justify-center mb-6 shadow-[0_8px_30px_rgba(0,0,0,0.04)] ring-1 ring-white/60 relative overflow-hidden group">
                <div class="absolute inset-0 bg-gradient-to-tr from-primary-500/5 via-primary-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
                <div class="w-14 h-14 bg-white rounded-2xl shadow-sm flex items-center justify-center text-3xl animate-float relative z-10 text-primary-500">
                    <el-icon><ChatDotRound /></el-icon>
                </div>
                <!-- Decor dots -->
                <div class="absolute top-6 right-6 w-2 h-2 rounded-full bg-primary-400/30 animate-ping"></div>
            </div>
            <span class="text-sm font-bold text-gray-500 bg-white/60 backdrop-blur-md px-5 py-2 rounded-full border border-white/50 shadow-sm flex items-center gap-2">
                <el-icon class="text-primary-500"><MagicStick /></el-icon>
                选择一个节点开始对话
            </span>
        </div>

        <!-- QA History -->
        <div v-for="(msg, idx) in courseStore.chatHistory" :key="idx" 
            class="flex flex-col gap-2 animate-fade-in-up" :style="{ animationDelay: `${idx * 100}ms` }">
            
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
                            <el-icon><Cpu /></el-icon>
                        </div>
                        <span>AI Assistant</span>
                    </div>

                    <!-- Main Answer Content -->
                    <div class="leading-relaxed text-slate-700 prose prose-sm max-w-none prose-slate" v-html="renderMarkdown(msg.content.core_answer)"></div>
                    
                    <!-- Actions -->
                    <div class="flex flex-wrap gap-2 mt-4 pt-3 border-t border-slate-100/80">
                        <!-- Jump Button -->
                        <button 
                            v-if="msg.content.node_id"
                            class="glass-button !h-7 !px-3 !text-xs !rounded-lg !border-emerald-200/50 !text-emerald-600 hover:!bg-emerald-50/80 hover:!shadow-emerald-500/10 group/btn"
                            @click="courseStore.scrollToNode(msg.content.node_id)"
                        >
                            <el-icon class="mr-1 group-hover/btn:scale-110 transition-transform"><Aim /></el-icon>
                            定位原文
                        </button>

                        <!-- Save Note Button -->
                        <button 
                            v-if="msg.content.quote"
                            class="glass-button !h-7 !px-3 !text-xs !rounded-lg !border-primary-200/50 !text-primary-600 hover:!bg-primary-50/80 hover:!shadow-primary-500/10 group/btn"
                            @click="courseStore.saveAnnotation(msg.content)"
                        >
                            <el-icon class="mr-1 group-hover/btn:scale-110 transition-transform"><EditPen /></el-icon>
                            生成笔记
                        </button>
                    </div>

                    <ul class="space-y-2.5 text-xs opacity-90 mt-3 bg-slate-50/50 p-3 rounded-xl border border-slate-100" v-if="msg.content.detail_answer && msg.content.detail_answer.length > 0">
                            <li v-for="(d, i) in msg.content.detail_answer" :key="i" class="flex gap-2.5 items-start group/item">
                                <span class="text-primary-400 mt-1 text-xxs transition-transform group-hover/item:scale-150">●</span>
                                <span class="leading-relaxed prose prose-xs prose-slate" v-html="renderMarkdown(d)"></span>
                            </li>
                    </ul>
                </div>
                <div v-else class="leading-relaxed relative z-10 prose prose-sm max-w-none" :class="msg.type === 'user' ? 'prose-invert text-white/95' : 'prose-slate'" v-html="renderMarkdown(msg.content)"></div>
            </div>
            <span class="text-[10px] font-bold uppercase tracking-wider text-gray-300 px-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300" :class="msg.type === 'user' ? 'self-end' : 'self-start'">
                <span v-if="msg.type === 'ai'" class="w-1 h-1 rounded-full bg-primary-400"></span>
                {{ msg.type === 'user' ? 'YOU' : 'AI ASSISTANT' }}
            </span>
        </div>
    </div>
    </div>
    
    <!-- Input Area -->
    <div class="m-2 lg:m-4 mt-2 z-20 relative">
        <!-- Floating Thinking Indicator -->
        <div v-if="courseStore.loading" class="absolute -top-10 left-6 z-0 pointer-events-none">
             <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/60 backdrop-blur-md border border-white/40 shadow-sm animate-pulse-slow">
                <el-icon class="is-loading text-primary-500 text-sm"><Loading /></el-icon>
                <span class="text-[10px] font-bold text-transparent bg-clip-text bg-gradient-to-r from-primary-500 to-primary-600 tracking-wide uppercase">
                    AI Thinking...
                </span>
            </div>
        </div>

        <div class="glass-chat-bar p-2 flex items-end gap-3 relative group">
            <div class="relative flex-1 py-1">
                <el-input
                    v-model="input"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    placeholder="输入问题... (Ctrl + Enter 发送)"
                    class="w-full !bg-transparent custom-chat-input !text-base"
                    resize="none"
                    @keydown.enter.exact.prevent="handleSend"
                    @keydown.ctrl.enter.prevent="handleSend"
                />
            </div>
            
            <button 
                class="w-10 h-10 mb-0.5 rounded-xl flex items-center justify-center transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                :class="[
                    input.trim() || courseStore.loading 
                        ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30 hover:bg-primary-600 hover:scale-105 active:scale-95' 
                        : 'bg-slate-100 text-slate-400 hover:bg-slate-200'
                ]"
                :disabled="courseStore.loading || !input.trim()"
                @click="handleSend"
            >
                <el-icon :class="{ 'is-loading': courseStore.loading }" class="text-xl">
                    <Loading v-if="courseStore.loading" />
                    <Position v-else />
                </el-icon>
            </button>
        </div>
        
        <div class="text-xxs text-center mt-2 text-slate-400 font-medium select-none opacity-60">
            AI 生成内容仅供参考
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUpdated, nextTick, watch } from 'vue'
import { useCourseStore } from '../stores/course'
import { ChatDotRound, Delete, Reading, Position, EditPen, Cpu, Aim, MagicStick, Loading, Setting } from '@element-plus/icons-vue'
import { renderMarkdown } from '../utils/markdown'
import mermaid from 'mermaid'

const courseStore = useCourseStore()
const input = ref('')
const personaDialogVisible = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

const scrollToBottom = async () => {
    await nextTick()
    if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
}

watch(() => courseStore.chatHistory, () => {
    scrollToBottom()
}, { deep: true })

const handleSend = async () => {
    const val = input.value.trim()
    if (!val || courseStore.loading) return
    
    input.value = ''
    await courseStore.askQuestion(val)
}

// Initialize mermaid rendering for chat answers
const runMermaid = async () => {
    await nextTick()
    try {
        const nodes = document.querySelectorAll('.mermaid')
        if (nodes.length > 0) {
             await mermaid.run({
                querySelector: '.mermaid'
            })
        }
    } catch (e) {
        // Suppress errors, often due to parsing invalid diagram code from partial streams
        // console.warn('Mermaid rendering warning:', e) 
    }
}

onMounted(runMermaid)
onUpdated(runMermaid)
</script>

<style scoped>
:deep(.el-textarea__inner) {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 12px 16px;
    font-size: 0.95rem;
    line-height: 1.5;
    resize: none;
    color: #334155;
}

:deep(.el-textarea__inner::placeholder) {
    color: #94a3b8;
}

.animate-pulse-slow {
    animation: pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: .8; }
}

/* Basic styling for markdown content in chat */
:deep(p) {
    margin-bottom: 0.5em;
}
:deep(p:last-child) {
    margin-bottom: 0;
}
:deep(ul), :deep(ol) {
    padding-left: 1.5em;
    margin-bottom: 0.5em;
}
:deep(li) {
    list-style-type: disc;
}
</style>