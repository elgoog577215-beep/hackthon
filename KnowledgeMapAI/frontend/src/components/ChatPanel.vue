<template>
  <div class="h-full flex flex-col relative overflow-hidden">
    <!-- Header -->
    <div class="mx-4 mt-4 mb-2 h-16 px-4 z-20 relative flex items-center justify-between gap-3 glass-panel-tech-floating rounded-2xl">
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
            <button v-if="courseStore.chatHistory.length > 0" class="glass-icon-btn p-2 rounded-lg hover:bg-white/50 text-slate-500 hover:text-primary-600 transition-colors" @click="handleSummarize" title="一键总结">
                <el-icon :size="18"><Collection /></el-icon>
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
    
    <!-- Summary Preview Dialog -->
    <el-dialog
        v-model="summaryDialogVisible"
        width="600px"
        append-to-body
        class="glass-dialog !rounded-[2rem] !p-0 overflow-hidden shadow-2xl"
        align-center
        :show-close="false"
    >
        <template #header>
            <div class="px-8 py-5 border-b border-slate-100/80 flex justify-between items-center bg-white/80 backdrop-blur-xl">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
                        <el-icon :size="20"><Collection /></el-icon>
                    </div>
                    <div>
                        <h4 class="text-lg font-bold text-slate-800 leading-tight font-display">对话总结预览</h4>
                        <p class="text-xs text-slate-500 font-medium mt-0.5">AI 智能提炼核心要点</p>
                    </div>
                </div>
                <button @click="summaryDialogVisible = false" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
                    <el-icon :size="18"><Close /></el-icon>
                </button>
            </div>
        </template>

        <div class="p-8 bg-slate-50/50">
            <div class="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                <!-- Title Input -->
                <div class="px-6 py-4 border-b border-slate-50">
                    <input 
                        v-model="summaryTitle" 
                        class="w-full text-lg font-bold text-slate-800 placeholder-slate-300 bg-transparent outline-none" 
                        placeholder="请输入笔记标题..."
                    />
                </div>
                
                <!-- Markdown Content Preview -->
                <div class="relative">
                    <div class="p-6 max-h-[50vh] overflow-y-auto custom-scrollbar bg-white">
                        <div class="prose prose-slate prose-sm max-w-none 
                            prose-headings:font-bold prose-headings:text-slate-800 
                            prose-p:text-slate-600 prose-p:leading-relaxed
                            prose-li:text-slate-600 prose-strong:text-slate-800 prose-strong:font-bold
                            prose-code:text-primary-600 prose-code:bg-primary-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
                            prose-pre:bg-slate-800 prose-pre:rounded-xl prose-pre:shadow-lg
                            prose-blockquote:border-l-4 prose-blockquote:border-primary-200 prose-blockquote:bg-primary-50/30 prose-blockquote:px-4 prose-blockquote:py-1 prose-blockquote:rounded-r-lg prose-blockquote:not-italic
                            "
                            v-html="renderMarkdown(summaryContent)"
                        ></div>
                    </div>
                    
                    <!-- Edit Overlay (Optional, if we want to allow raw edit) -->
                    <!-- For now, keep it read-only preview with title edit, as markdown edit is complex in this view -->
                </div>
            </div>
        </div>

        <div class="px-8 py-5 border-t border-slate-100 bg-white flex justify-end gap-3 items-center">
            <el-button @click="summaryDialogVisible = false" class="!rounded-xl !px-6 !h-10 !border-slate-200 text-slate-600 hover:!bg-slate-50">取消</el-button>
            <el-button type="primary" @click="saveSummary" class="!rounded-xl !px-8 !h-10 !bg-gradient-to-r !from-emerald-500 !to-teal-600 !border-none shadow-lg shadow-emerald-500/30 hover:shadow-emerald-500/50 hover:-translate-y-0.5 transition-all font-bold">
                <el-icon class="mr-1"><Check /></el-icon> 保存为笔记
            </el-button>
        </div>
    </el-dialog>
    
    <!-- Output Area -->
    <div class="flex-1 m-4 my-2 overflow-hidden relative glass-panel-tech-content rounded-3xl flex flex-col shadow-[inset_0_0_20px_rgba(255,255,255,0.5)] border border-white/60">
        <div class="flex-1 overflow-auto p-5 space-y-6 custom-scrollbar relative scroll-smooth pb-32" ref="chatContainer" @click="handleChatClick">
            <!-- Background Pattern (Cleaned) -->
            <!-- <div class="absolute inset-0 opacity-[0.03] pointer-events-none" style="background-image: radial-gradient(var(--el-color-primary) 1px, transparent 1px); background-size: 24px 24px;"></div> -->

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

            <!-- Finish Topic Button (Visible when chat exists) -->
            <div v-if="courseStore.chatHistory.length > 2" class="sticky top-0 z-10 flex justify-center py-2 pointer-events-none">
                <button 
                    class="pointer-events-auto bg-white/90 backdrop-blur-md border border-primary-200 text-primary-600 px-4 py-1.5 rounded-full shadow-sm text-xs font-bold hover:bg-primary-50 transition-all flex items-center gap-1.5 group"
                    @click="handleSummarize"
                >
                    <el-icon><CircleCheckFilled /></el-icon>
                    <span>我学会了，结束本话题</span>
                    <el-icon class="group-hover:translate-x-0.5 transition-transform"><ArrowRight /></el-icon>
                </button>
            </div>

            <!-- QA History -->
            <div v-for="(msg, idx) in courseStore.chatHistory" :key="idx" 
                class="flex flex-col gap-2 animate-fade-in-up" :style="{ animationDelay: `${idx * 50}ms` }">
                
                <div :class="['p-5 rounded-3xl text-sm max-w-[90%] transition-all relative overflow-hidden shadow-sm backdrop-blur-md group', 
                    msg.type === 'user' 
                        ? 'bg-gradient-to-br from-primary-600 to-primary-700 text-white self-end rounded-tr-sm shadow-[0_8px_20px_-4px_rgba(139,92,246,0.3)] ring-1 ring-white/20 border-t border-white/20' 
                        : 'bg-white/80 border border-white/60 !rounded-tl-sm self-start hover:bg-white/90 transition-all shadow-[0_4px_20px_-4px_rgba(148,163,184,0.1)] hover:shadow-[0_8px_25px_-5px_rgba(148,163,184,0.15)]']">
                    
                    <!-- Noise Texture Overlay for subtle detail -->
                    <!-- <div class="absolute inset-0 opacity-[0.1] pointer-events-none mix-blend-overlay bg-[url('data:image/svg+xml,%3Csvg%20viewBox=%220%200%20200%20200%22%20xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter%20id=%22noise%22%3E%3CfeTurbulence%20type=%22fractalNoise%22%20baseFrequency=%220.8%22%20numOctaves=%223%22%20stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect%20width=%22100%25%22%20height=%22100%25%22%20filter=%22url(%23noise)%22%20opacity=%221%22/%3E%3C/svg%3E')]"></div> -->

                    <!-- Shimmer for AI messages -->
                    <div v-if="msg.type === 'ai'" class="absolute inset-0 bg-gradient-to-r from-transparent via-white/60 to-transparent w-1/2 -skew-x-12 translate-x-[-200%] animate-[shimmer_4s_infinite] pointer-events-none"></div>

                    <!-- Reflection for User messages -->
                    <div v-if="msg.type === 'user'" class="absolute inset-0 bg-gradient-to-b from-white/20 to-transparent opacity-50 pointer-events-none"></div>
                    <div v-if="msg.type === 'user'" class="absolute -bottom-10 -right-10 w-32 h-32 bg-primary-600/30 blur-3xl rounded-full pointer-events-none"></div>

                    <div v-if="msg.type === 'ai' && typeof msg.content === 'object'" class="relative z-10">
                         <!-- Header: AI Icon + Title -->
                        <div class="flex items-center gap-2 mb-3 text-xxs font-bold text-primary-600 uppercase tracking-wider border-b border-gray-100/80 pb-2 justify-between">
                            <div class="flex items-center gap-2">
                                <div class="w-5 h-5 rounded bg-primary-50 flex items-center justify-center text-primary-500">
                                    <el-icon><MagicStick /></el-icon>
                                </div>
                                <span>AI Analysis</span>
                            </div>
                            <div class="flex items-center gap-1">
                                <!-- Quote Preview (Enhanced Locate) -->
                                <el-popover
                                    v-if="msg.content.quote"
                                    placement="top"
                                    :width="300"
                                    trigger="hover"
                                    popper-class="glass-popover"
                                >
                                    <template #reference>
                                        <button 
                                            class="flex items-center gap-1 text-slate-400 hover:text-primary-600 transition-colors px-2 py-1 rounded hover:bg-primary-50"
                                            @click="scrollToSource(msg.content)"
                                        >
                                            <el-icon><Location /></el-icon>
                                            <span class="scale-90">原文</span>
                                        </button>
                                    </template>
                                    <div class="p-2 space-y-2">
                                        <div class="text-xs font-bold text-slate-500 uppercase flex items-center gap-1">
                                            <el-icon><Reading /></el-icon> 引用来源
                                        </div>
                                        <div class="text-xs text-slate-700 leading-relaxed border-l-2 border-primary-300 pl-2 italic">
                                            "{{ msg.content.quote.length > 100 ? msg.content.quote.slice(0, 100) + '...' : msg.content.quote }}"
                                        </div>
                                        <div class="text-[10px] text-slate-400 text-right">点击按钮跳转到此处</div>
                                    </div>
                                </el-popover>
                                
                                <button 
                                    v-else-if="msg.content.node_id || msg.content.anno_id"
                                    class="flex items-center gap-1 text-slate-400 hover:text-primary-600 transition-colors px-2 py-1 rounded hover:bg-primary-50"
                                    @click="scrollToSource(msg.content)"
                                    title="定位到原文"
                                >
                                    <el-icon><Location /></el-icon>
                                    <span class="scale-90">原文</span>
                                </button>

                                <button 
                                    class="flex items-center gap-1 text-slate-400 hover:text-primary-600 transition-colors px-2 py-1 rounded hover:bg-primary-50"
                                    @click="handleSaveAsNote(getMessageText(msg.content), { ...msg, idx })"
                                    title="保存为笔记"
                                >
                                    <el-icon><DocumentAdd /></el-icon>
                                    <span class="scale-90">保存</span>
                                </button>
                            </div>
                        </div>
                        <div v-if="msg.content.answer" class="prose prose-sm prose-slate mb-3 leading-relaxed">
                            <div v-html="renderMarkdown(msg.content.answer)"></div>
                        </div>
                        <div v-if="getQuizList(msg.content).length > 0" class="mt-3 space-y-4 select-none">
                            <div v-for="(quiz, qIdx) in getQuizList(msg.content)" :key="qIdx" class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                                <div class="flex items-start gap-3 mb-3">
                                    <div class="w-8 h-8 rounded-lg bg-primary-100 text-primary-600 flex items-center justify-center font-bold text-sm shrink-0">
                                        Q
                                    </div>
                                    <div class="text-slate-800 font-bold leading-relaxed pt-1">{{ quiz.question }}</div>
                                </div>

                                <div class="space-y-2 pl-11">
                                    <button 
                                        v-for="(opt, oIdx) in quiz.options" 
                                        :key="oIdx"
                                        class="w-full text-left p-3 rounded-xl border transition-all relative group"
                                        :class="getOptionClass(idx, qIdx, oIdx, quiz)"
                                        @click="handleOptionClick(idx, qIdx, oIdx)"
                                        :disabled="isQuizSubmitted(idx, qIdx)"
                                    >
                                        <div class="flex items-center gap-3">
                                            <div class="w-6 h-6 rounded-full border flex items-center justify-center text-xs font-bold transition-colors shrink-0"
                                                :class="getOptionBadgeClass(idx, qIdx, oIdx, quiz)">
                                                {{ getOptionLabel(oIdx) }}
                                            </div>
                                            <span class="text-sm font-medium">{{ opt }}</span>
                                        </div>
                                        
                                        <div v-if="isQuizSubmitted(idx, qIdx)" class="absolute right-3 top-1/2 -translate-y-1/2">
                                            <el-icon v-if="oIdx === quiz.correct_index" class="text-emerald-500 text-lg"><CircleCheckFilled /></el-icon>
                                            <el-icon v-else-if="getQuizState(idx, qIdx).selected === oIdx" class="text-red-500 text-lg"><CircleCloseFilled /></el-icon>
                                        </div>
                                    </button>
                                </div>

                                <div v-if="isQuizSubmitted(idx, qIdx)" class="mt-4 pl-11 animate-in fade-in slide-in-from-top-2">
                                    <div class="bg-slate-50 rounded-xl p-3 border border-slate-100 mb-3">
                                        <div class="text-xs font-bold text-slate-500 uppercase mb-1">解析</div>
                                        <div class="text-sm text-slate-600 leading-relaxed">{{ quiz.explanation }}</div>
                                    </div>
                                    
                                    <div class="flex gap-2 mt-3 flex-wrap">
                                        <button 
                                            v-if="quiz.node_id"
                                            class="flex items-center gap-2 text-xs font-bold text-primary-600 bg-primary-50 hover:bg-primary-100 px-3 py-2 rounded-lg transition-colors border border-primary-200"
                                            @click="courseStore.scrollToNode(quiz.node_id)"
                                        >
                                            <el-icon><Reading /></el-icon>
                                            <span>回顾知识点</span>
                                        </button>

                                        <button 
                                            v-if="getQuizState(idx, qIdx).selected !== quiz.correct_index"
                                            class="flex items-center gap-2 text-xs font-bold text-amber-600 bg-amber-50 hover:bg-amber-100 px-3 py-2 rounded-lg transition-colors border border-amber-200"
                                            @click="saveWrongQuestion(quiz, idx, qIdx)"
                                        >
                                            <el-icon><Notebook /></el-icon>
                                            <span>加入错题本</span>
                                        </button>
                                        
                                        <button 
                                            class="flex items-center gap-2 text-xs font-bold text-slate-500 hover:text-primary-600 bg-white hover:bg-slate-50 px-3 py-2 rounded-lg transition-colors border border-slate-200 shadow-sm"
                                            @click="resetQuiz(idx, qIdx)"
                                        >
                                            <el-icon><RefreshRight /></el-icon>
                                            <span>重试</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div v-else class="relative z-10 leading-relaxed whitespace-pre-wrap font-medium" :class="msg.type === 'user' ? 'text-white' : 'text-slate-700'">
                        <div v-if="msg.type === 'ai'" v-html="renderMarkdown(getMessageText(msg.content))"></div>
                        <span v-else>{{ msg.content }}</span>
                    </div>
                </div>
            </div>
            
            <div v-if="courseStore.chatLoading" class="flex gap-2 p-4 animate-pulse items-center">
                <div class="w-8 h-8 rounded-full bg-slate-200"></div>
                <div class="h-8 bg-slate-100 rounded-xl w-32"></div>
            </div>
        </div>
        
        <!-- Floating Input Area (Dock Style) -->
        <div class="absolute bottom-6 left-6 right-6 z-30">
            <div class="relative group bg-white/80 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.08)] rounded-[2rem] border border-white/60 hover:border-primary-200 hover:shadow-[0_12px_40px_rgba(139,92,246,0.15)] transition-all duration-300 ring-1 ring-white/50">
                <textarea
                    ref="inputRef"
                    v-model="inputMessage"
                    class="w-full bg-transparent border-none rounded-[2rem] px-6 py-4 pr-14 text-sm focus:ring-0 resize-none h-[60px] max-h-[200px] custom-scrollbar placeholder:text-slate-400 text-slate-700 font-medium leading-relaxed"
                    placeholder="输入问题，与 AI 探索知识 (Ctrl + Enter 发送)..."
                    @keydown="handleKeydown"
                    @input="adjustTextareaHeight"
                ></textarea>
                
                <button 
                    class="absolute right-2 bottom-2 w-11 h-11 rounded-full transition-all duration-300 flex items-center justify-center group/btn"
                    :class="courseStore.chatLoading
                        ? 'bg-red-500 text-white shadow-lg shadow-red-500/30 hover:scale-110 active:scale-95'
                        : (inputMessage.trim() ? 'bg-gradient-to-br from-primary-500 to-primary-600 text-white shadow-lg shadow-primary-500/30 hover:scale-110 active:scale-95' : 'bg-slate-100 text-slate-300 cursor-not-allowed')"
                    @click="courseStore.chatLoading ? stopMessage() : sendMessage()"
                    :disabled="!courseStore.chatLoading && !inputMessage.trim()"
                >
                    <el-icon v-if="courseStore.chatLoading" :size="18"><CircleCloseFilled /></el-icon>
                    <el-icon v-else :size="20" class="group-hover/btn:-translate-y-0.5 group-hover/btn:translate-x-0.5 transition-transform"><Position /></el-icon>
                </button>
            </div>
            <div class="text-center mt-3">
                <span class="text-[10px] text-slate-400 font-medium bg-white/40 backdrop-blur px-3 py-1 rounded-full border border-white/30 shadow-sm">AI 内容由大模型生成，请仔细甄别</span>
            </div>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, reactive } from 'vue'
import { useCourseStore } from '../stores/course'
import type { AIContent } from '../stores/course'
import { ChatDotRound, Position, MagicStick, Setting, Delete, DocumentAdd, CircleCheckFilled, CircleCloseFilled, Notebook, RefreshRight, Location, Collection, Reading, Close, Check, ArrowRight } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import DOMPurify from 'dompurify'
import { ElMessage, ElMessageBox } from 'element-plus'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css'

const courseStore = useCourseStore()
const inputMessage = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const personaDialogVisible = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)

const adjustTextareaHeight = () => {
    if (inputRef.value) {
        inputRef.value.style.height = '60px' // Reset to min height to calculate scrollHeight correctly
        const scrollHeight = inputRef.value.scrollHeight
        inputRef.value.style.height = `${Math.min(Math.max(scrollHeight, 60), 200)}px`
    }
}

watch(inputMessage, () => {
    nextTick(() => {
        adjustTextareaHeight()
    })
})

// Summary Dialog State
const summaryDialogVisible = ref(false)
const summaryTitle = ref('')
const summaryContent = ref('')
const summaryStuck = ref('')
const summarySolution = ref('')
const summaryInspiration = ref('')
const summarySuggestQuiz = ref(false)

// Watch for pending chat input from other components (e.g. quote selection)
watch(() => courseStore.pendingChatInput, (newVal) => {
    if (newVal) {
        inputMessage.value = newVal
        // Focus input
        nextTick(() => {
            inputRef.value?.focus()
            // Clear the pending state so it can be triggered again with same text if needed
            courseStore.pendingChatInput = ''
        })
    }
})

const handleSummarize = async () => {
    const summary = await courseStore.summarizeChat()
    if (summary) {
        summaryTitle.value = summary.title || '对话总结'
        summaryContent.value = summary.content || ''
        summaryStuck.value = summary.stuck_point || ''
        summarySolution.value = summary.solution || ''
        summaryInspiration.value = summary.inspiration || ''
        summarySuggestQuiz.value = summary.suggest_quiz || false
        
        summaryDialogVisible.value = true
    }
}

const saveSummary = () => {
    const fullContent = `
# ${summaryTitle.value}

## 🔴 卡点 (Stuck Point)
${summaryStuck.value}

## 🟢 解答 (Solution)
${summarySolution.value}

## ✨ 启发 (Inspiration)
${summaryInspiration.value}

---
**详细复盘**：
${summaryContent.value}
`
    courseStore.createNote({
        id: `summary-${Date.now()}`,
        nodeId: courseStore.currentNode?.node_id || 'global',
        highlightId: '',
        quote: '',
        content: fullContent,
        color: 'blue',
        createdAt: Date.now(),
        sourceType: 'ai',
        style: 'highlight'
    })
    
    summaryDialogVisible.value = false
    ElMessage.success('复盘笔记已保存')
    
    // Suggest Quiz
    if (summarySuggestQuiz.value) {
        ElMessageBox.confirm('本轮对话包含重要知识点，是否进行测验以巩固学习？', '巩固测验', {
            confirmButtonText: '开始测验',
            cancelButtonText: '稍后',
            type: 'success'
        }).then(() => {
             // Generate quiz based on summary content
             // We can trigger a quiz generation using the summary content as context
             courseStore.generateQuizFromSummary(summaryContent.value)
        }).catch(() => {})
    }
}

// Helper to get option label (A, B, C...)
const getOptionLabel = (index: number) => String.fromCharCode(65 + index)

const getMessageText = (content: string | AIContent) => {
    if (typeof content === 'string') return content
    return content.core_answer || content.answer || ''
}

const getQuizList = (content: AIContent) => {
    if (content.quiz_list && content.quiz_list.length > 0) return content.quiz_list
    if (content.quiz) return [content.quiz]
    return []
}

const scrollToSource = (content: AIContent) => {
    if (content.anno_id) {
        courseStore.scrollToNote(content.anno_id)
        return
    }
    if (content.node_id) {
        courseStore.scrollToNode(content.node_id)
    }
}

// Quiz State Management
const quizStates = reactive<Record<string, { selected: number | null }>>({})
const getQuizKey = (msgIdx: number, quizIdx: number) => `${msgIdx}-${quizIdx}`

const getQuizState = (msgIdx: number, quizIdx: number) => {
    const key = getQuizKey(msgIdx, quizIdx)
    if (!quizStates[key]) {
        quizStates[key] = { selected: null }
    }
    return quizStates[key]
}

const isQuizSubmitted = (msgIdx: number, quizIdx: number) => {
    return getQuizState(msgIdx, quizIdx).selected !== null
}

const resetQuiz = (msgIdx: number, quizIdx: number) => {
    const state = getQuizState(msgIdx, quizIdx)
    state.selected = null
}

const handleOptionClick = (msgIdx: number, quizIdx: number, optIdx: number) => {
    const state = getQuizState(msgIdx, quizIdx)
    if (state.selected !== null) return
    
    state.selected = optIdx
}

const getOptionClass = (msgIdx: number, quizIdx: number, optIdx: number, quiz: any) => {
    const state = getQuizState(msgIdx, quizIdx)
    const isSelected = state.selected === optIdx
    const isCorrect = quiz.correct_index === optIdx
    const isSubmitted = state.selected !== null
    
    if (!isSubmitted) {
        return isSelected 
            ? 'border-primary-500 bg-primary-50 text-primary-700 shadow-sm ring-1 ring-primary-200' 
            : 'border-slate-200 hover:border-primary-300 hover:bg-slate-50 text-slate-600'
    }
    
    // Submitted state
    if (isCorrect) {
        return 'border-emerald-500 bg-emerald-50 text-emerald-700 shadow-sm ring-1 ring-emerald-200'
    }
    
    if (isSelected && !isCorrect) {
        return 'border-red-500 bg-red-50 text-red-700 shadow-sm ring-1 ring-red-200'
    }
    
    return 'border-slate-100 text-slate-400 opacity-60'
}

const getOptionBadgeClass = (msgIdx: number, quizIdx: number, optIdx: number, quiz: any) => {
    const state = getQuizState(msgIdx, quizIdx)
    const isSelected = state.selected === optIdx
    const isCorrect = quiz.correct_index === optIdx
    const isSubmitted = state.selected !== null
    
    if (!isSubmitted) {
        return isSelected 
            ? 'border-primary-500 bg-primary-500 text-white' 
            : 'border-slate-300 text-slate-500 group-hover:border-primary-400 group-hover:text-primary-500'
    }
    
    if (isCorrect) {
        return 'border-emerald-500 bg-emerald-500 text-white'
    }
    
    if (isSelected && !isCorrect) {
        return 'border-red-500 bg-red-500 text-white'
    }
    
    return 'border-slate-200 text-slate-300'
}

const saveWrongQuestion = async (quiz: any, msgIdx: number, quizIdx: number) => {
    // 1. Prompt for Reflection
    try {
        const result = await ElMessageBox.prompt('请简要分析错误原因（这将帮助你更好地避坑）：', '错题反思', {
            confirmButtonText: '保存',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：概念混淆、粗心大意、公式记错...',
            inputType: 'textarea',
        })
        const reflection = typeof result === 'string' ? result : (result as { value?: string }).value
        
        if (reflection) {
             const state = getQuizState(msgIdx, quizIdx)
             if (state.selected === null) return
             const wrongOpt = quiz.options[state.selected]
             const correctOpt = quiz.options[quiz.correct_index]
             
             courseStore.addNote({
                 id: `wrong-${Date.now()}`,
                 nodeId: quiz.node_id || courseStore.currentNode?.node_id || 'global',
                 highlightId: '',
                 quote: quiz.question,
                 content: `🔴 **错题记录**\n\n**题目**：${quiz.question}\n\n**我的选择**：${wrongOpt} (❌)\n**正确答案**：${correctOpt} (✅)\n\n**解析**：${quiz.explanation}\n\n**💡 我的反思**：\n${reflection}`,
                 color: 'red',
                 createdAt: Date.now(),
                 sourceType: 'wrong', // Special type for mistakes,
                 style: 'highlight'
             })
             
             ElMessage.success('已加入错题本')
        }
    } catch (e) {
        // Cancelled
    }
}

const handleSaveAsNote = async (content: string, msg?: any) => {
    if (!content) return
    
    // Use injected nodeId from msg, or fallback to current node or first node
    const nodeId = msg?.content?.node_id || msg?.node_id
    const targetNodeId = nodeId || courseStore.currentNode?.node_id || courseStore.nodes?.[0]?.node_id || ''
    
    if (!targetNodeId) {
        ElMessage.warning('无法关联章节，请先生成课程内容')
        return
    }

    try {
        // Construct structured note content if message context is available
        let finalContent = content
        let quote = ''
        
        if (msg) {
            // Find previous user message for question
            let question = '提问'
            if (msg.idx && msg.idx > 0) {
                const prevMsg = courseStore.chatHistory[msg.idx - 1]
                if (prevMsg && prevMsg.type === 'user') {
                    question = typeof prevMsg.content === 'string' ? prevMsg.content : ''
                }
            }
            
            // Get Quote
            if (msg.content?.quote) {
                quote = msg.content.quote
            }
            
            // Format: 1. Original 2. Question 3. Answer
            finalContent = ``
            
            if (quote) {
                finalContent += `> ${quote}\n\n`
            }
            
            if (question) {
                finalContent += `**Q: ${question}**\n\n`
            }
            
            finalContent += `**A:**\n${content}`
        }

        const noteId = crypto.randomUUID()
        await courseStore.createNote({
            id: noteId,
            nodeId: targetNodeId,
            highlightId: '', // General note, not attached to text
            quote: quote, // Store raw quote for potential linking
            content: finalContent,
            color: '#fef3c7', // Amber color for notes
            createdAt: Date.now(),
            sourceType: 'ai'
        }) 
        ElMessage.success('已保存到笔记')
    } catch (e) {
        console.error(e)
        ElMessage.error('保存失败')
    }
}

const customMathPlugin = (md: MarkdownIt) => {
    // Inline math $...$
    md.inline.ruler.before('escape', 'math_inline', (state, silent) => {
        if (state.src[state.pos] !== '$') return false
        if (state.src.slice(state.pos, state.pos + 2) === '$$') return false
        
        const start = state.pos + 1
        let match = start
        let pos = start
        
        // Find closing $
        while ((match = state.src.indexOf('$', pos)) !== -1) {
            // Check for escaped \$
            if (state.src[match - 1] === '\\') {
                pos = match + 1
                continue
            }
            break
        }
        
        if (match === -1) return false
        if (match - start === 0) return false // Empty $$
        
        if (!silent) {
            const token = state.push('math_inline', 'math', 0)
            token.markup = '$'
            token.content = state.src.slice(start, match)
        }
        
        state.pos = match + 1
        return true
    })

    // Block math $$...$$
    md.block.ruler.after('blockquote', 'math_block', (state, startLine, endLine, silent) => {
        const startPos = (state.bMarks[startLine] ?? 0) + (state.tShift[startLine] ?? 0)
        
        if (state.src.slice(startPos, startPos + 2) !== '$$') return false
        
        let pos = startPos + 2
        let content = ''
        let found = false
        let nextLine = startLine
        
        // Check if closing $$ is on the same line
        if (state.src.indexOf('$$', pos) !== -1) {
            const end = state.src.indexOf('$$', pos)
            content = state.src.slice(pos, end)
            nextLine = startLine + 1
            found = true
        } else {
            // Multiline block
            content = state.src.slice(pos)
            nextLine++
            
            while (nextLine < endLine) {
                const lineStart = (state.bMarks[nextLine] ?? 0) + (state.tShift[nextLine] ?? 0)
                const lineEnd = state.eMarks[nextLine] ?? lineStart
                const lineText = state.src.slice(lineStart, lineEnd)
                
                if (lineText.trim().endsWith('$$')) {
                    content += '\n' + lineText.trim().slice(0, -2)
                    found = true
                    nextLine++
                    break
                }
                
                content += '\n' + lineText
                nextLine++
            }
        }
        
        if (!found) return false
        if (silent) return true
        
        const token = state.push('math_block', 'math', 0)
        token.block = true
        token.content = content
        token.map = [startLine, nextLine]
        token.markup = '$$'
        
        state.line = nextLine
        return true
    })

    // Renderers
    md.renderer.rules.math_inline = (tokens, idx) => {
        const token = tokens[idx]
        if (!token) return ''
        try {
            return katex.renderToString(token.content, { 
                throwOnError: false, 
                displayMode: false 
            })
        } catch (e) {
            return token.content
        }
    }

    md.renderer.rules.math_block = (tokens, idx) => {
        const token = tokens[idx]
        if (!token) return ''
        try {
            return '<div class="katex-display">' + katex.renderToString(token.content, { 
                throwOnError: false, 
                displayMode: true 
            }) + '</div>'
        } catch (e) {
            return '<pre>' + token.content + '</pre>'
        }
    }
}

// Markdown Setup
const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true
}).use(customMathPlugin)

md.options.highlight = (str: string, lang: string) => {
    if (lang && hljs.getLanguage(lang)) {
        try {
            return '<pre class="hljs p-4 rounded-lg bg-[#282c34] text-sm overflow-x-auto"><code>' +
                   hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
                   '</code></pre>';
        } catch (__) {}
    }
    return '<pre class="hljs p-4 rounded-lg bg-[#282c34] text-sm overflow-x-auto"><code>' + md.utils.escapeHtml(str) + '</code></pre>';
}

// Custom fence renderer for Copy Button
md.renderer.rules.fence = function (tokens: any[], idx: number, options: any) {
  const token = tokens[idx];
  const info = token.info ? md.utils.escapeHtml(token.info) : '';
  const langName = info.split(/\s+/g)[0];
  
  let highlighted;
  if (options.highlight) {
      highlighted = options.highlight(token.content, langName, '') || md.utils.escapeHtml(token.content);
  } else {
      highlighted = md.utils.escapeHtml(token.content);
  }
  
  return `<div class="relative group code-block-wrapper my-2 rounded-lg overflow-hidden border border-slate-200/50 shadow-sm bg-[#282c34]">
            <div class="absolute top-2 right-2 flex items-center gap-2 z-10">
                <span class="text-xs text-slate-400 font-mono opacity-0 group-hover:opacity-100 transition-opacity select-none">${langName}</span>
                <button class="p-1.5 rounded-md bg-slate-700/50 hover:bg-slate-700 text-white/70 hover:text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all copy-btn" title="复制代码">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2-2v1"></path></svg>
                </button>
            </div>
            ${highlighted}
          </div>`;
};

const handleChatClick = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const btn = target.closest('.copy-btn');
    if (btn) {
        const wrapper = btn.closest('.code-block-wrapper');
        const codeEl = wrapper?.querySelector('pre code') || wrapper?.querySelector('pre');
        if (codeEl) {
            const text = codeEl.textContent || '';
            navigator.clipboard.writeText(text).then(() => {
                ElMessage.success('代码已复制')
            }).catch(() => {
                ElMessage.error('复制失败')
            })
        }
    }
}

const scrollToBottom = async (force = false) => {
    await nextTick()
    if (!chatContainer.value) return
    
    const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
    // Threshold to determine if user is near bottom (e.g. 100px)
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150
    
    if (force || isNearBottom) {
        chatContainer.value.scrollTo({
            top: scrollHeight,
            behavior: 'smooth'
        })
    }
}

watch(() => courseStore.chatHistory, () => {
    scrollToBottom(false)
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
    
    await scrollToBottom(true) // Force scroll on user send
    
    await courseStore.sendMessage(msg)
}

const stopMessage = () => {
    courseStore.cancelChat()
}

const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        sendMessage()
    }
}

const renderMarkdown = (content: string) => {
    if (typeof content !== 'string') return ''
    
    // Pre-process LaTeX formula fixes
    let fixedContent = content
        // Fix \[ ... \] block formulas to $$ ... $$
        .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
        // Fix \( ... \) inline formulas to $ ... $
        .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')
        // Fix LLM generating spaces in function calls like f' (x) -> f'(x)
        .replace(/(\w+)'\s+\((.+?)\)/g, "$1'($2)")
        .replace(/(\w+)\s+'/g, "$1'")
        // Fix trailing dollar signs in block math
        .replace(/(\$\$[\s\S]*?)[^$]\$$/gm, "$1$$")
        // Standardize mixed math blocks
        .replace(/(\$\$[\s\S]*?\$\$)|(\$\s+(.+?)\\s+\$)/g, (match, block, inline, content) => {
            if (block) return block
            if (inline) return `$${content}$`
            return match
        })
    
    try {
        const rawHtml = md.render(fixedContent)
        // Allow katex classes and styles
        return DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['span', 'div'],
            ADD_ATTR: ['class', 'style']
        })
    } catch (e) {
        console.warn('Markdown render error:', e)
        return content
    }
}

// Removed duplicate handleSaveAsNote

onMounted(() => {
    scrollToBottom()
    nextTick(() => {
        inputRef.value?.focus()
    })
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

.glass-panel-tech-floating {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.glass-panel-tech-content {
    background: rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.4);
}
</style>
