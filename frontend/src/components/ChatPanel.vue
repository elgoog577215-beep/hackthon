<template>
  <div class="h-full flex flex-col relative overflow-hidden">
    <!-- Header - Improved spacing and layout -->
    <div class="mx-2 sm:mx-3 mt-2 sm:mt-3 mb-2 h-11 sm:h-12 px-2 sm:px-3 z-20 relative flex items-center justify-between gap-1 sm:gap-2 bg-white/70 backdrop-blur-md rounded-xl border border-slate-200/50 shadow-sm">
        <div class="relative flex items-center gap-2 sm:gap-2.5 min-w-0">
            <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-md shadow-primary-500/20 text-white flex-shrink-0">
                <el-icon :size="16" class="sm:!text-[18px]"><ChatDotRound /></el-icon>
            </div>
            <div class="min-w-0 overflow-hidden">
                <div class="font-semibold text-slate-800 text-sm sm:text-base truncate">AI 助手</div>
                <div class="flex items-center gap-1">
                    <div class="w-1 h-1 rounded-full bg-emerald-400 flex-shrink-0"></div>
                    <span class="text-xs sm:text-sm text-slate-400">在线</span>
                </div>
            </div>
        </div>
        <div class="relative flex gap-0.5 sm:gap-1 flex-shrink-0">
            <button class="p-1 sm:p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-primary-600 transition-colors" @click="personaDialogVisible = true" title="设置画像">
                <el-icon :size="14" class="sm:!text-[16px]"><Setting /></el-icon>
            </button>
            <button v-if="courseStore.chatHistory.length > 0" class="p-1 sm:p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-primary-600 transition-colors" @click="handleSummarize" title="一键总结">
                <el-icon :size="14" class="sm:!text-[16px]"><Collection /></el-icon>
            </button>
            <button v-if="courseStore.chatHistory.length > 0" class="p-1 sm:p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors" @click="courseStore.clearChat()" title="清空对话">
                <el-icon :size="14" class="sm:!text-[16px]"><Delete /></el-icon>
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
    <div class="flex-1 m-4 my-2 overflow-hidden relative glass-panel-tech-content rounded-xl flex flex-col shadow-[inset_0_0_20px_rgba(255,255,255,0.5)] border border-white/60">
        <!-- Image Lightbox -->
        <Teleport to="body">
            <transition name="fade">
                <div v-if="lightboxVisible" class="fixed inset-0 z-[100] bg-black/90 backdrop-blur-md flex items-center justify-center cursor-zoom-out" @click="lightboxVisible = false">
                    <img :src="lightboxImage" class="max-w-[95vw] max-h-[95vh] object-contain rounded-lg shadow-2xl transition-transform duration-300 scale-100 hover:scale-[1.02]" alt="Full screen preview" />
                    <button class="absolute top-4 right-4 text-white/50 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors">
                        <el-icon :size="32"><Close /></el-icon>
                    </button>
                </div>
            </transition>
        </Teleport>

        <div class="flex-1 overflow-auto p-5 space-y-6 custom-scrollbar relative scroll-smooth pb-32" ref="chatContainer" @click="handleChatClick">
            <!-- Background Pattern (Cleaned) -->
            <!-- <div class="absolute inset-0 opacity-[0.03] pointer-events-none" style="background-image: radial-gradient(var(--el-color-primary) 1px, transparent 1px); background-size: 24px 24px;"></div> -->

            <!-- Empty States with Smart Suggestions -->
            <div v-if="courseStore.chatHistory.length === 0" class="flex flex-col items-center justify-center mt-6 text-gray-400">
                <div class="w-16 h-16 bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl flex items-center justify-center mb-4 shadow-sm ring-1 ring-white/60">
                    <div class="w-10 h-10 bg-white rounded-lg shadow-sm flex items-center justify-center text-2xl text-primary-500">
                        <el-icon :size="24"><ChatDotRound /></el-icon>
                    </div>
                </div>
                <p class="text-xs text-slate-400 mb-4">有什么可以帮助你的？</p>

                <!-- Smart Suggestions -->
                <div class="w-full px-4 space-y-2">
                    <p class="text-[10px] text-slate-400 uppercase tracking-wider text-center">快速提问</p>
                    <div class="flex flex-wrap gap-2 justify-center">
                        <button v-for="suggestion in smartSuggestions" :key="suggestion"
                                @click="quickAsk(suggestion)"
                                class="px-3 py-1.5 text-xs bg-white/80 hover:bg-white border border-slate-200 hover:border-primary-300 rounded-full text-slate-600 hover:text-primary-600 transition-all shadow-sm hover:shadow">
                            {{ suggestion }}
                        </button>
                    </div>
                </div>

                <!-- Context-based Suggestions -->
                <div v-if="contextSuggestions.length > 0" class="w-full px-4 mt-4 space-y-2">
                    <p class="text-[10px] text-slate-400 uppercase tracking-wider text-center font-medium">基于当前内容</p>
                    <div class="flex flex-col gap-2">
                        <button v-for="suggestion in contextSuggestions" :key="suggestion.text"
                                @click="quickAsk(suggestion.text)"
                                class="px-3 py-2.5 text-xs bg-white/80 hover:bg-primary-50 border border-slate-200/60 hover:border-primary-200 rounded-xl text-slate-600 hover:text-primary-700 transition-all duration-200 text-left flex items-center gap-2 shadow-sm hover:shadow-md">
                            <el-icon :size="12" class="text-primary-400"><Reading /></el-icon>
                            <span class="font-medium">{{ suggestion.text }}</span>
                        </button>
                    </div>
                </div>
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
                class="flex flex-col gap-1.5 animate-fade-in-up" :style="{ animationDelay: `${idx * 30}ms` }">

                <div :class="['p-4 rounded-xl text-base max-w-[95%] transition-all relative shadow-sm group',
                    msg.type === 'user'
                        ? 'bg-primary-600 text-white self-end rounded-tr-sm'
                        : 'bg-white border border-slate-100 !rounded-tl-sm self-start hover:border-slate-200']">

                    <div v-if="msg.type === 'ai' && typeof msg.content === 'object'" class="relative z-10">
                         <!-- Header: AI Icon + Title -->
                        <div class="flex items-center gap-1.5 mb-2 text-xs font-semibold text-primary-600 uppercase tracking-wide border-b border-slate-100/60 pb-1.5 justify-between">
                            <div class="flex items-center gap-1.5">
                                <div class="w-4 h-4 rounded bg-primary-50 flex items-center justify-center text-primary-500">
                                    <el-icon :size="12"><MagicStick /></el-icon>
                                </div>
                                <span>AI</span>
                            </div>
                            <div class="flex items-center gap-1">
                                <!-- Quote Preview (Enhanced Locate) -->
                                <el-popover
                                    v-if="msg.content.quote"
                                    placement="left"
                                    :width="300"
                                    trigger="hover"
                                    popper-class="glass-popover"
                                    :teleported="false"
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
                            <div v-for="(quiz, qIdx) in getQuizList(msg.content)" :key="qIdx" 
                                 class="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-[0_2px_8px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)] transition-all duration-300"
                                 :class="{ 'ring-2 ring-purple-100 border-purple-200': quiz.isReview }">
                                <!-- Review Badge -->
                                <div v-if="quiz.isReview" class="flex items-center gap-1.5 mb-3 text-purple-600">
                                    <el-icon :size="14"><RefreshRight /></el-icon>
                                    <span class="text-[11px] font-bold uppercase tracking-wide">错题回顾</span>
                                </div>
                                
                                <div class="flex items-start gap-3 mb-4">
                                    <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-primary-100 to-primary-50 text-primary-600 flex items-center justify-center font-bold text-sm shrink-0 shadow-sm">
                                        {{ qIdx + 1 }}
                                    </div>
                                    <div class="text-slate-800 font-semibold leading-relaxed pt-1 text-[15px]" v-html="renderMarkdown(quiz.question)"></div>
                                </div>

                                <div class="space-y-2.5 pl-11">
                                    <button 
                                        v-for="(opt, oIdx) in quiz.options" 
                                        :key="oIdx"
                                        class="w-full text-left p-3.5 rounded-xl border transition-all duration-200 relative group"
                                        :class="getOptionClass(idx, qIdx, oIdx, quiz)"
                                        @click="handleOptionClick(idx, qIdx, oIdx)"
                                        :disabled="isQuizSubmitted(idx, qIdx)"
                                    >
                                        <div class="flex items-center gap-3">
                                            <div class="w-6 h-6 rounded-lg border flex items-center justify-center text-[11px] font-bold transition-colors shrink-0"
                                                :class="getOptionBadgeClass(idx, qIdx, oIdx, quiz)">
                                                {{ getOptionLabel(oIdx) }}
                                            </div>
                                            <div class="text-sm font-medium leading-relaxed" v-html="renderMarkdown(opt)"></div>
                                        </div>
                                        
                                        <div v-if="isQuizSubmitted(idx, qIdx)" class="absolute right-3 top-1/2 -translate-y-1/2">
                                            <el-icon v-if="oIdx === quiz.correct_index" class="text-emerald-500 text-xl"><CircleCheckFilled /></el-icon>
                                            <el-icon v-else-if="getQuizState(idx, qIdx).selected === oIdx" class="text-red-500 text-xl"><CircleCloseFilled /></el-icon>
                                        </div>
                                    </button>
                                </div>

                                <div v-if="isQuizSubmitted(idx, qIdx)" class="mt-4 pl-11 animate-in fade-in slide-in-from-top-2 duration-300">
                                    <div class="bg-gradient-to-r from-slate-50 to-white rounded-xl p-4 border border-slate-100 mb-3">
                                        <div class="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase mb-2">
                                            <el-icon :size="12"><InfoFilled /></el-icon>
                                            解析
                                        </div>
                                        <div class="text-sm text-slate-600 leading-[1.8]" v-html="renderMarkdown(quiz.explanation || '')"></div>
                                    </div>
                                    
                                    <div class="flex gap-2 mt-3 flex-wrap">
                                        <button 
                                            v-if="quiz.node_id"
                                            class="flex items-center gap-2 text-xs font-bold text-primary-600 bg-primary-50 hover:bg-primary-100 px-3 py-2 rounded-lg transition-all duration-200 border border-primary-200/50 hover:border-primary-300"
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
        
        <!-- Floating Input Area - Compact Design -->
        <div class="absolute bottom-4 left-4 right-4 z-30">
            <!-- Quick Commands Panel -->
            <div v-if="showQuickCommands" class="mb-2 bg-white/95 backdrop-blur-md rounded-xl border border-slate-200/60 shadow-lg p-3 animate-fade-in-up">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">快捷指令</span>
                    <button @click="showQuickCommands = false" class="text-slate-400 hover:text-slate-600">
                        <el-icon :size="12"><Close /></el-icon>
                    </button>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button v-for="cmd in quickCommands" :key="cmd.key"
                            @click="applyQuickCommand(cmd)"
                            class="flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-slate-50 hover:bg-primary-50 border border-slate-200 hover:border-primary-200 rounded-lg text-slate-600 hover:text-primary-600 transition-all">
                        <el-icon :size="12"><component :is="cmd.icon" /></el-icon>
                        <span>{{ cmd.label }}</span>
                        <span class="text-[9px] text-slate-400 ml-0.5">/{{ cmd.key }}</span>
                    </button>
                </div>
            </div>

            <div class="relative group">
                <div class="relative bg-white/90 backdrop-blur-md rounded-xl border border-slate-200/60 group-focus-within:border-primary-300/60 shadow-sm group-focus-within:shadow-md transition-all duration-200">
                    <!-- Quick Command Trigger -->
                    <button
                        class="absolute left-2.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg bg-slate-100 hover:bg-primary-50 text-slate-400 hover:text-primary-600 transition-all flex items-center justify-center"
                        @click="showQuickCommands = !showQuickCommands"
                        title="快捷指令"
                    >
                        <el-icon :size="14"><CommandMenu /></el-icon>
                    </button>

                    <textarea
                        ref="inputRef"
                        v-model="inputMessage"
                        class="w-full bg-transparent border-none rounded-2xl pl-12 pr-12 py-3.5 text-[15px] focus:ring-0 resize-none h-[56px] max-h-[140px] custom-scrollbar placeholder:text-slate-400/70 text-slate-700 leading-relaxed"
                        placeholder="输入 / 查看快捷指令，或输入问题..."
                        @keydown="handleKeydown"
                        @input="handleInput"
                    ></textarea>

                    <button
                        class="absolute right-2.5 bottom-2.5 w-9 h-9 rounded-xl transition-all duration-200 flex items-center justify-center shadow-sm"
                        :class="courseStore.chatLoading
                            ? 'bg-red-500 text-white hover:bg-red-600 shadow-red-500/30'
                            : (inputMessage.trim() ? 'bg-gradient-to-r from-primary-500 to-primary-600 text-white hover:shadow-primary-500/30 hover:scale-105' : 'bg-slate-100 text-slate-300 cursor-not-allowed')"
                        @click="courseStore.chatLoading ? stopMessage() : sendMessage()"
                        :disabled="!courseStore.chatLoading && !inputMessage.trim()"
                    >
                        <el-icon v-if="courseStore.chatLoading" :size="16"><CircleCloseFilled /></el-icon>
                        <el-icon v-else :size="16"><Position /></el-icon>
                    </button>
                </div>

                <!-- Keyboard hint -->
                <div class="absolute -top-5 right-0 text-[10px] text-slate-400/80 opacity-0 group-focus-within:opacity-100 transition-opacity duration-200 font-medium">
                    Ctrl + Enter 发送
                </div>
            </div>
        </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted, reactive, computed } from 'vue'
import { useCourseStore } from '../stores/course'
import type { AIContent } from '../stores/course'
import { ChatDotRound, Position, MagicStick, Setting, Delete, DocumentAdd, CircleCheckFilled, CircleCloseFilled, Notebook, RefreshRight, Location, Collection, Reading, Close, Check, ArrowRight, InfoFilled, QuestionFilled, Document, DataLine, Sunny, TrendCharts, Menu as CommandMenu } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { renderMarkdown } from '../utils/markdown'
import mermaid from 'mermaid'

const courseStore = useCourseStore()
const inputMessage = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const personaDialogVisible = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const showQuickCommands = ref(false)

// Lazy rendering for Mermaid diagrams
const observedMermaidElements = new WeakSet()
let mermaidObserver: IntersectionObserver | null = null

const initMermaidObserver = () => {
    if (mermaidObserver) return
    
    mermaidObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const target = entry.target as HTMLElement
                if (target.getAttribute('data-processed')) return
                
                // Render mermaid
                mermaid.run({ nodes: [target] }).then(() => {
                    target.style.opacity = '1'
                }).catch(err => {
                    console.error('Mermaid render error:', err)
                    target.innerHTML = `<div class="text-red-500 text-sm p-2">图表渲染失败</div>`
                    target.style.opacity = '1'
                })
                
                mermaidObserver?.unobserve(target)
            }
        })
    }, { rootMargin: '500px 0px' }) // Preload well in advance
}

const scanMermaidDiagrams = () => {
    nextTick(() => {
        const diagrams = document.querySelectorAll('.mermaid')
        diagrams.forEach(el => {
            if (!observedMermaidElements.has(el)) {
                if (!mermaidObserver) initMermaidObserver()
                mermaidObserver?.observe(el)
                observedMermaidElements.add(el)
            }
        })
    })
}

// Watch chat history to render mermaid diagrams
watch(() => courseStore.chatHistory, () => {
    scanMermaidDiagrams()
}, { deep: true })

// Lightbox State
const lightboxVisible = ref(false)
const lightboxImage = ref('')

// Quick Commands Definition
const quickCommands = [
    { key: 'summary', label: '总结内容', icon: Document, template: '请帮我总结一下当前章节的核心内容' },
    { key: 'explain', label: '详细解释', icon: QuestionFilled, template: '请详细解释一下这个概念，包括定义、原理和应用场景' },
    { key: 'example', label: '举例说明', icon: Sunny, template: '请给我举几个具体的例子来帮助理解' },
    { key: 'compare', label: '对比分析', icon: DataLine, template: '请对比分析一下相关概念的异同点' },
    { key: 'quiz', label: '生成测验', icon: TrendCharts, template: '请基于当前内容生成几道测验题' },
    { key: 'keypoints', label: '提取重点', icon: Collection, template: '请提取本章节的重点和考点' }
]

const handleInput = () => {
    adjustTextareaHeight()
    // Show quick commands when typing "/"
    if (inputMessage.value === '/') {
        showQuickCommands.value = true
    } else if (!inputMessage.value.startsWith('/')) {
        showQuickCommands.value = false
    }
}

const applyQuickCommand = (cmd: typeof quickCommands[0]) => {
    inputMessage.value = cmd.template
    showQuickCommands.value = false
    nextTick(() => {
        inputRef.value?.focus()
        adjustTextareaHeight()
    })
}

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
    const state = getQuizState(msgIdx, quizIdx)
    if (state.selected === null) return

    // Record to quiz system
    const nodeName = courseStore.currentNode?.node_name || '未知章节'
    courseStore.recordWrongAnswer({
        question: quiz.question,
        options: quiz.options,
        correctIndex: quiz.correct_index,
        userIndex: state.selected,
        explanation: quiz.explanation,
        nodeId: quiz.node_id || courseStore.currentNode?.node_id || 'global',
        nodeName: nodeName
    })

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

const handleChatClick = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    
    // Handle Copy Button
    const btn = target.closest('.copy-btn') as HTMLElement;
    if (btn) {
        // Check for data-code attribute (utils/markdown.ts style)
        const codeFromAttr = btn.getAttribute('data-code');
        if (codeFromAttr) {
            const decoded = decodeURIComponent(codeFromAttr);
            navigator.clipboard.writeText(decoded).then(() => {
                const originalHTML = btn.innerHTML
                btn.innerHTML = '<span class="text-green-400 font-bold">OK</span>'
                btn.classList.add('bg-green-500/20')
                setTimeout(() => {
                    btn.innerHTML = originalHTML
                    btn.classList.remove('bg-green-500/20')
                }, 2000)
                ElMessage.success('代码已复制')
            }).catch(() => {
                ElMessage.error('复制失败')
            })
            return;
        }

        // Fallback for existing/legacy style (if any)
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
        return
    }

    // Handle Image Click (Lightbox)
    if (target.tagName === 'IMG' && target.closest('.prose')) {
        lightboxImage.value = (target as HTMLImageElement).src
        lightboxVisible.value = true
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

// ========== Smart Suggestions ==========
const smartSuggestions = [
    '帮我总结一下这个章节',
    '这个概念是什么意思？',
    '能举个例子吗？',
    '这个知识点常考吗？',
    '和之前的内容有什么联系？'
]

const contextSuggestions = computed(() => {
    const suggestions = []
    const currentNode = courseStore.currentNode

    if (currentNode) {
        // Based on current node content
        if (currentNode.node_content) {
            const content = currentNode.node_content.toLowerCase()

            // Detect content type and suggest relevant questions
            if (content.includes('定义') || content.includes('概念')) {
                suggestions.push({ text: `"${currentNode.node_name}"的核心定义是什么？`, type: 'definition' })
            }
            if (content.includes('公式') || content.includes('计算')) {
                suggestions.push({ text: `这个公式的适用条件是什么？`, type: 'formula' })
            }
            if (content.includes('步骤') || content.includes('流程')) {
                suggestions.push({ text: `能梳理一下操作步骤吗？`, type: 'process' })
            }
            if (content.includes('例子') || content.includes('案例')) {
                suggestions.push({ text: `还有类似的例子吗？`, type: 'example' })
            }

            // Always add general suggestions
            suggestions.push({ text: `关于"${currentNode.node_name}"的重点有哪些？`, type: 'keypoints' })
        }
    }

    // Limit to 3 suggestions
    return suggestions.slice(0, 3)
})

const quickAsk = (question: string) => {
    inputMessage.value = question
    sendMessage()
}

const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        sendMessage()
    }
}



// Removed duplicate handleSaveAsNote

onMounted(() => {
    scrollToBottom()
    nextTick(() => {
        inputRef.value?.focus()
        scanMermaidDiagrams()
    })
})

onUnmounted(() => {
    if (mermaidObserver) {
        mermaidObserver.disconnect()
        mermaidObserver = null
    }
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
