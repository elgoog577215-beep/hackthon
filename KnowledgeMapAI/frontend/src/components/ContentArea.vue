<template>
  <div class="h-full flex flex-col">
    <!-- Toolbar -->
    <div class="h-16 flex items-center justify-between px-4 lg:px-6 mx-2 lg:mx-6 mt-4 mb-2 sticky top-4 z-30 transition-all duration-300 glass-panel-tech rounded-2xl">
      <div class="bg-white/50 backdrop-blur-sm rounded-full px-4 py-1.5 border border-white/40 shadow-sm flex items-center gap-2">
        <span class="font-bold text-slate-700">
            {{ courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || '课程预览' }}
        </span>
        <span class="text-slate-300">|</span>
        <span class="text-xs text-slate-500">全书模式</span>
      </div>
      
      <div class="flex gap-3">
        <div class="glass-segment">
            <el-button size="small" text :icon="Minus" @click="fontSize = Math.max(12, fontSize - 1)" class="!px-2 hover:!bg-white/80 !rounded-lg !text-slate-600" />
            <span class="text-xs text-slate-500 w-8 text-center font-mono select-none font-bold">{{ fontSize }}px</span>
            <el-button size="small" text :icon="Plus" @click="fontSize = Math.min(24, fontSize + 1)" class="!px-2 hover:!bg-white/80 !rounded-lg !text-slate-600" />
        </div>
        <button 
            class="glass-button-elegant group" 
            @click="exportContent"
        >
            <el-icon class="text-lg text-primary-500 group-hover:scale-110 transition-transform"><Download /></el-icon>
            <span class="group-hover:text-primary-600 transition-colors">导出全书</span>
        </button>
      </div>
    </div>

    <!-- Content List (Continuous Scroll) -->
    <div class="flex-1 overflow-auto p-4 lg:p-10 relative scroll-smooth custom-scrollbar" id="content-scroll-container" @mouseup="handleMouseUp">
      
      <!-- Selection Menu -->
      <div v-if="selectionMenu.visible" 
           class="fixed z-50 flex gap-1 p-1.5 bg-slate-800/90 backdrop-blur-xl rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.12)] animate-in fade-in zoom-in-95 duration-200 border border-white/10 ring-1 ring-white/10"
           :style="{ left: selectionMenu.x + 'px', top: selectionMenu.y + 'px' }"
           @mousedown.stop>
          <div class="absolute inset-0 rounded-xl bg-gradient-to-br from-white/10 to-transparent pointer-events-none"></div>
          <button @click="handleExplain" class="relative z-10 flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20 rounded-lg transition-all group active:scale-95">
              <el-icon class="text-primary-300 group-hover:scale-110 group-hover:text-primary-200 transition-transform"><MagicStick /></el-icon> 
              <span class="text-shadow-sm">AI 深度解析</span>
          </button>
      </div>

      <div v-if="flatNodes.length > 0" class="w-full max-w-[96%] mx-auto space-y-12 pb-32">
        <!-- Empty Selection Guide -->
        <div v-if="!courseStore.currentCourseId" class="flex flex-col items-center justify-center h-96 text-slate-400">
            <el-icon :size="48" class="mb-4 opacity-50"><Notebook /></el-icon>
            <p class="text-lg font-medium">请从左侧选择一个课程或章节开始</p>
        </div>

        <div v-for="(node, index) in flatNodes" :key="node.node_id" :id="'node-' + node.node_id" 
             class="scroll-mt-24 transition-all duration-500 animate-fade-in-up"
             :style="{ animationDelay: (index * 100) + 'ms' }">
            
            <!-- Level 1: Course Title / Part -->
            <div v-if="node.node_level === 1" class="relative overflow-hidden rounded-[2.5rem] bg-white/60 backdrop-blur-2xl border border-white/60 shadow-xl shadow-purple-500/5 mb-24 group glass-hover-effect">
                <!-- Sophisticated Background -->
                <div class="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-white/20 pointer-events-none"></div>
                <!-- Softer, more diffuse ambient light -->
                <div class="absolute -top-[40%] -right-[20%] w-[80%] h-[120%] bg-gradient-to-b from-primary-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                <div class="absolute -bottom-[40%] -left-[20%] w-[80%] h-[120%] bg-gradient-to-t from-pink-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                
                <!-- Subtle noise texture for paper-like feel -->
                <div class="absolute inset-0 opacity-[0.4] pointer-events-none mix-blend-overlay" style="background-image: var(--glass-noise);"></div>
                
                <div class="relative z-10 p-16 lg:p-24 flex flex-col items-center text-center">
                    <!-- Badge -->
                    <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/80 border border-slate-200/60 shadow-sm backdrop-blur-md mb-10 group-hover:-translate-y-1 transition-transform duration-500">
                        <span class="relative flex h-2 w-2">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                        </span>
                        <span class="text-[10px] font-bold tracking-widest text-slate-500 uppercase font-sans">Interactive Course</span>
                    </div>

                    <!-- Title with Modern Typography -->
                    <!-- Removing quotes, using cleaner font stack, better line-height -->
                    <h1 class="text-5xl lg:text-7xl font-black text-slate-800 mb-8 tracking-tighter drop-shadow-sm font-display leading-[1.1] max-w-6xl bg-clip-text text-transparent bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
                        {{ node.node_name.replace(/《|》/g, '') }}
                    </h1>

                    <!-- Decorative Divider -->
                    <div class="flex items-center gap-6 mb-10 opacity-40">
                        <div class="w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                        <div class="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                        <div class="w-16 h-px bg-gradient-to-r from-transparent via-slate-400 to-transparent"></div>
                    </div>

                    <!-- Description -->
                    <div class="prose prose-lg prose-slate text-slate-600 max-w-5xl mx-auto font-sans leading-relaxed mix-blend-multiply text-center font-medium" v-html="renderMarkdown(node.node_content)"></div>
                </div>
            </div>

            <!-- Level 2: Chapter -->
            <div v-else-if="node.node_level === 2" class="mt-24 mb-10 relative group">
                 <div class="absolute -left-4 -top-4 w-20 h-20 bg-gradient-to-br from-slate-100 to-transparent rounded-full opacity-50 blur-xl group-hover:opacity-100 transition-opacity"></div>
                 <div class="flex items-baseline gap-4 mb-6 border-b-2 border-slate-100 pb-4">
                    <span class="text-4xl font-black text-slate-200 font-display select-none">CHAPTER</span>
                    <h2 class="text-3xl font-bold text-slate-800 relative z-10">{{ node.node_name }}</h2>
                 </div>
                 <div v-if="node.node_content" 
                      class="text-lg text-slate-600 pl-6 border-l-4 border-primary-300 italic bg-slate-50/50 p-4 rounded-r-xl prose prose-lg prose-slate max-w-none"
                      v-html="renderMarkdown(node.node_content)">
                 </div>
                 
                 <!-- Action to generate subnodes if empty and NOT generating -->
                 <div v-if="(!node.children || node.children.length === 0)" class="mt-8 flex justify-center">
                    <button 
                        v-if="!courseStore.isGenerating"
                        class="glass-button !px-6 !py-2.5 !text-base !font-medium" 
                        @click="courseStore.generateSubChapters(node)"
                    >
                       <el-icon class="mr-2 text-lg"><Operation /></el-icon> 构建本章细分目录
                    </button>
                    <button 
                        v-else
                        class="glass-button !px-6 !py-2.5 !text-base !font-medium opacity-75 cursor-not-allowed" 
                        disabled
                    >
                       <el-icon class="mr-2 text-lg is-loading"><Loading /></el-icon> 正在构建目录...
                    </button>
                 </div>
            </div>

            <!-- Level 3+: Section (Content) -->
            <div v-else class="glass-card-tech rounded-3xl p-8 lg:p-12 group relative overflow-visible">
                        <!-- Side Notes Container -->
                <div class="hidden xl:block absolute top-0 left-full ml-6 w-72 h-full pointer-events-none">
                    <div class="relative w-full h-full pointer-events-auto" :id="'side-notes-' + node.node_id">
                        <div v-for="item in sideNotesMap[node.node_id]" :key="item.anno.anno_id"
                             class="absolute left-0 w-full transition-all duration-500 ease-in-out"
                             :style="{ top: item.top + 'px' }"
                        >
                            <div 
                                :class="['p-4 rounded-xl backdrop-blur-md border shadow-sm transition-all duration-300 cursor-pointer group hover:scale-105',
                                    courseStore.activeAnnotation?.anno_id === item.anno.anno_id 
                                        ? 'bg-primary-50/90 border-primary-300 ring-2 ring-primary-200 shadow-lg' 
                                        : 'bg-white/60 border-white/60 hover:bg-white/90 hover:shadow-md'
                                ]"
                                @click="scrollToHighlight(item.anno.anno_id)"
                            >
                                <div class="flex items-center gap-2 mb-2">
                                    <div class="w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse"></div>
                                    <span class="text-xxs font-bold uppercase tracking-wider text-primary-600">AI Annotation</span>
                                </div>
                                <div class="text-sm text-slate-700 leading-relaxed font-medium">
                                    {{ item.anno.anno_summary || '点击查看详情' }}
                                </div>
                                <div class="mt-2 pt-2 border-t border-slate-200/50 text-[10px] text-slate-400 line-clamp-2 italic">
                                    "{{ item.anno.quote }}"
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="flex justify-between items-start mb-8">
                    <h3 class="text-2xl font-bold text-slate-800 flex items-center gap-3">
                        <div class="w-1.5 h-8 bg-gradient-to-b from-primary-500 to-primary-600 rounded-full shadow-sm"></div>
                        {{ node.node_name }}
                    </h3>
                    
                    <!-- Inline Actions -->
                     <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-x-2 group-hover:translate-x-0">
                        <button 
                            class="glass-icon-btn !w-8 !h-8 !rounded-full bg-white/50 hover:bg-white/90"
                            @click="handleStartQuiz(node)" 
                            title="智能测验"
                        >
                            <el-icon><VideoPlay /></el-icon>
                        </button>
                        <button 
                            class="glass-icon-btn !w-8 !h-8 !rounded-full bg-white/50 hover:bg-white/90"
                            @click="courseStore.redefineContent(node, '优化正文')" 
                            title="重新生成"
                        >
                            <el-icon><MagicStick /></el-icon>
                        </button>
                        <button 
                            class="glass-icon-btn !w-8 !h-8 !rounded-full bg-white/50 hover:bg-white/90"
                            @click="courseStore.generateSubChapters(node)" 
                            title="生成下一级章节"
                        >
                            <el-icon><Operation /></el-icon>
                        </button>
                     </div>
                </div>

                <!-- Intro Section (New) -->
                <div v-if="splitContent(node.node_content).intro" 
                     class="mb-8 text-lg text-slate-700 pl-6 border-l-4 border-primary-400 italic bg-white/40 backdrop-blur-sm p-6 rounded-r-2xl prose prose-lg prose-slate max-w-none shadow-sm"
                     v-html="getRenderedContent(splitContent(node.node_content).intro, node)">
                </div>

                <!-- Content Body -->
                <div v-if="splitContent(node.node_content).body && splitContent(node.node_content).body.length > 20" 
                     class="prose prose-lg prose-slate max-w-none text-gray-700 leading-loose font-serif"
                     :style="{ fontSize: fontSize + 'px' }"
                     v-html="getRenderedContent(splitContent(node.node_content).body, node)">
                </div>
                
                <!-- Empty State / Generation Trigger -->
                <div v-else class="py-16 flex flex-col items-center justify-center border-2 border-dashed border-primary-100 rounded-2xl bg-primary-50/10 group-hover:bg-primary-50/30 transition-colors">
                    <div class="w-16 h-16 bg-white/60 rounded-full flex items-center justify-center mb-4 text-primary-200 group-hover:text-primary-400 group-hover:scale-110 transition-all shadow-sm">
                        <el-icon :size="24"><EditPen /></el-icon>
                    </div>
                    <p class="text-primary-400/80 font-medium mb-6">{{ splitContent(node.node_content).intro ? '暂无正文内容' : '暂无内容' }}</p>
                    
                    <button v-if="splitContent(node.node_content).intro" class="glass-button-primary !px-6 !py-2" @click="courseStore.generateBody(node)">
                        <el-icon class="mr-2"><MagicStick /></el-icon> 撰写正文
                    </button>
                    <button v-else class="glass-button-primary !px-6 !py-2" @click="courseStore.redefineContent(node, '生成教科书级正文')">
                        <el-icon class="mr-2"><MagicStick /></el-icon> 立即撰写
                    </button>
                </div>
            </div>

        </div>
      </div>
      
      <!-- Empty State - Hero Version -->
      <div v-else class="flex flex-col items-center justify-center h-full relative overflow-hidden">
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-50">
            <div class="w-full max-w-2xl aspect-square bg-primary-100/50 rounded-full blur-3xl"></div>
        </div>
        <div class="p-12 rounded-5xl glass-card-tech text-center max-w-lg mx-auto relative z-10 border border-white/60 backdrop-blur-2xl">
            <div class="w-32 h-32 bg-gradient-to-tr from-white to-primary-50 rounded-4xl flex items-center justify-center mb-10 shadow-xl shadow-primary-500/10 mx-auto ring-1 ring-white/80">
                <span class="text-6xl filter drop-shadow-md text-slate-400">✨</span>
            </div>
            <h3 class="text-3xl font-bold text-slate-800 mb-4 font-display tracking-tight">准备就绪</h3>
            <p class="text-slate-500 leading-relaxed text-lg font-medium max-w-xs mx-auto">
                选择或新建课程，开始<span class="text-primary-600 font-bold">全书阅读体验</span>
            </p>
        </div>
      </div>
    </div>

    <!-- Quiz Dialog -->
    <el-dialog
        v-model="quizDialogVisible"
        title="AI 智能测验"
        width="600px"
        append-to-body
        :close-on-click-modal="false"
        class="glass-dialog"
    >
        <div v-if="quizLoading" class="flex flex-col items-center justify-center py-12">
            <div class="relative w-16 h-16 flex items-center justify-center mb-4">
                <div class="absolute inset-0 rounded-full border-t-2 border-primary-500 animate-spin"></div>
                <div class="absolute inset-2 rounded-full border-b-2 border-primary-500 animate-spin-reverse"></div>
                <el-icon class="text-2xl text-primary-500 animate-pulse"><Cpu /></el-icon>
            </div>
            <p class="text-slate-500 font-medium">正在分析内容生成题目...</p>
        </div>

        <div v-else-if="quizQuestions.length > 0" class="py-4">
            <!-- Progress -->
            <div class="flex items-center justify-between mb-6 px-1">
                <span class="text-sm font-bold text-slate-500">QUESTION {{ currentQuestionIndex + 1 }} / {{ quizQuestions.length }}</span>
                <span class="text-sm font-bold text-primary-600">得分: {{ score }}</span>
            </div>
            
            <!-- Question Card -->
            <div class="bg-white/50 border border-white/60 rounded-2xl p-6 shadow-sm mb-6 relative overflow-hidden">
                <div class="absolute top-0 left-0 w-1 h-full bg-primary-500"></div>
                <h3 class="text-lg font-bold text-slate-800 leading-relaxed mb-4">
                    {{ quizQuestions[currentQuestionIndex].question }}
                </h3>
                
                <div class="space-y-3">
                    <button 
                        v-for="(option, idx) in quizQuestions[currentQuestionIndex].options" 
                        :key="idx"
                        class="w-full text-left p-4 rounded-xl border transition-all duration-200 flex items-center justify-between group relative overflow-hidden"
                        :class="[
                            showResult 
                                ? (idx === quizQuestions[currentQuestionIndex].correct_index 
                                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700 ring-1 ring-emerald-200' 
                                    : (idx === selectedOption ? 'bg-red-50 border-red-200 text-red-700' : 'bg-slate-50 border-slate-100 opacity-60'))
                                : 'bg-white hover:bg-primary-50 border-slate-200 hover:border-primary-200 hover:shadow-md cursor-pointer'
                        ]"
                        @click="submitAnswer(idx)"
                        :disabled="showResult"
                    >
                        <span class="font-medium relative z-10">{{ option }}</span>
                        
                        <!-- Status Icons -->
                        <div v-if="showResult" class="relative z-10">
                            <el-icon v-if="idx === quizQuestions[currentQuestionIndex].correct_index" class="text-emerald-500 text-xl"><Check /></el-icon>
                            <el-icon v-if="idx === selectedOption && idx !== quizQuestions[currentQuestionIndex].correct_index" class="text-red-500 text-xl"><Close /></el-icon>
                        </div>
                    </button>
                </div>
            </div>
            
            <!-- Explanation -->
            <transition name="el-fade-in">
                <div v-if="showResult" class="bg-blue-50/50 border border-blue-100 rounded-xl p-4 mb-6 text-sm text-slate-600">
                    <div class="font-bold text-blue-600 mb-1 flex items-center gap-2">
                        <el-icon><MagicStick /></el-icon> 解析
                    </div>
                    {{ quizQuestions[currentQuestionIndex].explanation }}
                </div>
            </transition>

            <div class="flex justify-end">
                <button 
                    class="glass-button-primary !px-8 !py-3 !text-base shadow-lg shadow-primary-500/20" 
                    @click="nextQuestion"
                    :disabled="!showResult"
                    :class="{ 'opacity-50 cursor-not-allowed': !showResult }"
                >
                    {{ currentQuestionIndex < quizQuestions.length - 1 ? '下一题' : '完成测验' }}
                </button>
            </div>
        </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUpdated, onBeforeUnmount } from 'vue'
import { useCourseStore } from '../stores/course'
import { Plus, Minus, Download, EditPen, Operation, MagicStick, Collection, VideoPlay, RefreshRight, Check, Close, Cpu } from '@element-plus/icons-vue'
import { renderMarkdown } from '../utils/markdown'
import mermaid from 'mermaid'
import { ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const fontSize = ref(Number(localStorage.getItem('content-font-size')) || 17)
watch(fontSize, (val) => {
    localStorage.setItem('content-font-size', val.toString())
})

const targetNodeId = ref<string | null>(null)

// --- Quiz Logic ---
const quizDialogVisible = ref(false)
const quizLoading = ref(false)
const quizQuestions = ref<any[]>([])
const currentQuestionIndex = ref(0)
const selectedOption = ref<number | null>(null)
const showResult = ref(false)
const score = ref(0)
const quizNodeId = ref('')

const handleStartQuiz = async (node: any) => {
    quizNodeId.value = node.node_id
    quizLoading.value = true
    quizDialogVisible.value = true
    quizQuestions.value = []
    currentQuestionIndex.value = 0
    score.value = 0
    selectedOption.value = null
    showResult.value = false

    const content = node.node_content
    const questions = await courseStore.generateQuiz(node.node_id, content)
    
    if (questions && questions.length > 0) {
        quizQuestions.value = questions
    } else {
        quizDialogVisible.value = false
        ElMessage.warning('无法生成测验，请确保内容充足')
    }
    quizLoading.value = false
}

const submitAnswer = (index: number) => {
    if (showResult.value) return
    selectedOption.value = index
    showResult.value = true
    
    if (index === quizQuestions.value[currentQuestionIndex.value].correct_index) {
        score.value++
    }
}

const nextQuestion = () => {
    if (currentQuestionIndex.value < quizQuestions.value.length - 1) {
        currentQuestionIndex.value++
        selectedOption.value = null
        showResult.value = false
    } else {
        // End of quiz
        ElMessage.success(`测验完成！得分: ${score.value}/${quizQuestions.value.length}`)
        quizDialogVisible.value = false
    }
}

// Selection Menu State
const selectionMenu = ref({
    visible: false,
    x: 0,
    y: 0,
    text: ''
})

const handleMouseUp = () => {
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) {
        selectionMenu.value.visible = false
        return
    }

    const text = selection.toString().trim()
    if (!text) {
        selectionMenu.value.visible = false
        return
    }

    // Get position
    const range = selection.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    
    // Ensure menu is within viewport
    const x = Math.max(10, Math.min(window.innerWidth - 120, rect.left + (rect.width / 2) - 60))
    
    // Check top boundary (Toolbar is h-16 = 64px)
    let y = rect.top - 50
    if (y < 70) {
        y = rect.bottom + 10
    }

    selectionMenu.value = {
        visible: true,
        x,
        y,
        text,
        nodeId: findNodeIdFromElement(range.commonAncestorContainer)
    }
}

const findNodeIdFromElement = (el: Node | null): string | undefined => {
    let current = el as HTMLElement | null
    while (current && current.classList) {
        if (current.id && current.id.startsWith('node-')) {
            return current.id.replace('node-', '')
        }
        current = current.parentElement
    }
    return undefined
}

const handleExplain = async () => {
    if (!selectionMenu.value.text) return
    
    const text = selectionMenu.value.text
    const nodeId = selectionMenu.value.nodeId
    selectionMenu.value.visible = false
    
    // Clear selection visually
    window.getSelection()?.removeAllRanges()
    
    // Trigger AI
    await courseStore.askQuestion(`请详细解析这段内容`, text, nodeId)
}

const scrollToHighlight = (annoId: string) => {
    const el = document.getElementById(`note-mark-${annoId}`)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Add flash effect
        el.classList.add('!bg-yellow-300', '!decoration-yellow-600')
        setTimeout(() => {
            el.classList.remove('!bg-yellow-300', '!decoration-yellow-600')
        }, 1500)
    }
}

// Initialize mermaid rendering
const runMermaid = async () => {
    await nextTick()
    // Find all mermaid divs that haven't been processed yet
    // mermaid.run automatically handles this if we target the class
    try {
        const nodes = document.querySelectorAll('.mermaid')
        if (nodes.length > 0) {
             await mermaid.run({
                querySelector: '.mermaid'
            })
        }
    } catch (e) {
        console.warn('Mermaid rendering warning:', e)
    }
}

// Handle Custom Event for Note Click (from HTML string)
onMounted(() => {
    runMermaid()
    
    window.addEventListener('note-click', ((e: CustomEvent) => {
        const annoId = e.detail
        const anno = courseStore.annotations.find(a => a.anno_id === annoId)
        if (anno) {
            courseStore.activeAnnotation = anno
        }
    }) as EventListener)
})

onUpdated(runMermaid)

// Compute flat list of nodes for continuous scroll
const flatNodes = computed(() => {
    if (!courseStore.courseTree || courseStore.courseTree.length === 0) return []
    return courseStore.getLinearNodes(courseStore.courseTree)
})

// Watch for new answers to highlight
watch(() => courseStore.activeAnnotation, async (newVal) => {
    if (!newVal || !newVal.quote) return
    
    // Find node containing the quote
    // We search in flatNodes. Note: Quote might be raw markdown or processed text.
    // We assume exact match on raw node_content for now.
    const targetNode = flatNodes.value.find(n => n.node_content && n.node_content.includes(newVal.quote))
    
    if (targetNode) {
        targetNodeId.value = targetNode.node_id
        
        // Wait for DOM update and rendering
        await nextTick()
        
        // Scroll to mark
        const mark = document.getElementById('current-annotation-mark')
        if (mark) {
            mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
            
            // Add a temporary flash effect
            mark.classList.add('ring-4', 'ring-yellow-300/50')
            setTimeout(() => mark.classList.remove('ring-4', 'ring-yellow-300/50'), 2000)
        } else {
            // Fallback: scroll to node
            const el = document.getElementById('node-' + targetNode.node_id)
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
    }
})

// Watch for generation to auto-scroll (Chapter-by-chapter reveal)
watch(() => courseStore.currentGeneratingNodeId, async (newVal) => {
    if (!newVal) return
    
    await nextTick()
    
    const el = document.getElementById('node-' + newVal)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
})

// Watch for manual jump (e.g. from Chat)
watch(() => courseStore.scrollToNodeId, async (newVal) => {
    if (!newVal) return
    
    await nextTick()
    
    const el = document.getElementById('node-' + newVal)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        
        // Highlight effect
        el.classList.add('ring-4', 'ring-primary-300/50', 'bg-primary-50/30')
        setTimeout(() => el.classList.remove('ring-4', 'ring-primary-300/50', 'bg-primary-50/30'), 2000)
    }
})

// Reactive side notes mapping with position info
interface SideNoteItem {
    anno: any
    top: number
}
const sideNotesMap = ref<Record<string, SideNoteItem[]>>({})

const repositionNotes = async () => {
    // Wait for DOM to be ready
    await nextTick()
    
    const map: Record<string, SideNoteItem[]> = {}
    
    // Group annotations by node_id
    const grouped: Record<string, any[]> = {}
    courseStore.annotations.forEach(anno => {
        if (!anno.node_id) return
        if (!grouped[anno.node_id]) grouped[anno.node_id] = []
        grouped[anno.node_id].push(anno)
    })
    
    // Calculate positions for each node group
    for (const nodeId in grouped) {
        const annos = grouped[nodeId]
        
        // First pass: get natural positions
        const naturalPositions = annos.map(anno => {
            const el = document.getElementById(`note-mark-${anno.anno_id}`)
            if (!el) return { anno, top: 0, valid: false }
            
            // Find the Section Card container for relative positioning
            // The side container is absolute relative to .glass-card-tech (which has relative position)
            const container = el.closest('.glass-card-tech')
            if (!container) return { anno, top: 0, valid: false }
            
            const rect = el.getBoundingClientRect()
            const containerRect = container.getBoundingClientRect()
            
            // Calculate top relative to the container
            // We subtract 20px to align the top of the note card roughly with the highlight text
            const top = rect.top - containerRect.top - 20
            
            return { anno, top, valid: true }
        }).filter(item => item.valid) as { anno: any, top: number, valid: boolean }[]
        
        // Sort by top position to process in order
        naturalPositions.sort((a, b) => a.top - b.top)
        
        // Second pass: Anti-collision (Greedy layout)
        let currentY = 0
        const minGap = 160 // Approximate height of a note card + gap
        
        const finalItems = naturalPositions.map(item => {
            let top = item.top
            
            // Ensure we don't place it higher than the previous one + gap
            // But if the text is far apart, we should respect the text position.
            if (top < currentY) {
                top = currentY
            }
            
            // Update currentY for the next item
            currentY = top + minGap
            
            return { anno: item.anno, top }
        })
        
        map[nodeId] = finalItems
    }
    
    sideNotesMap.value = map
}

const debounce = (fn: Function, delay: number) => {
    let timeoutId: any
    return (...args: any[]) => {
        clearTimeout(timeoutId)
        timeoutId = setTimeout(() => fn(...args), delay)
    }
}

const debouncedRepositionNotes = debounce(repositionNotes, 300)

// Watchers
watch(() => courseStore.annotations, debouncedRepositionNotes, { deep: true })

// Also watch generation to reposition as content grows
watch(() => courseStore.currentGeneratingNodeId, () => {
    debouncedRepositionNotes()
})

// Lifecycle
onMounted(() => {
    debouncedRepositionNotes()
    window.addEventListener('resize', debouncedRepositionNotes)
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', debouncedRepositionNotes)
})

onUpdated(() => {
    debouncedRepositionNotes()
})

const getRenderedContent = (content: string, node: any) => {
    // Gather all annotations for this node (saved + active)
    const annos = courseStore.annotations.filter(a => a.node_id === node.node_id && a.quote)
    
    // Add activeAnnotation if it's for this node and not already in saved list
    if (courseStore.activeAnnotation?.quote && 
        courseStore.activeAnnotation.node_id === node.node_id) {
        const isActiveSaved = annos.some(a => a.anno_id === courseStore.activeAnnotation!.anno_id)
        if (!isActiveSaved) {
            annos.push(courseStore.activeAnnotation)
        }
    }

    // Apply highlights
    for (const anno of annos) {
        const quote = anno.quote!
        if (!content.includes(quote)) continue
        
        const isFocused = courseStore.activeAnnotation?.anno_id === anno.anno_id
        const idAttr = `id="note-mark-${anno.anno_id}"`
        const focusClass = isFocused ? 'bg-yellow-200/80 decoration-yellow-500' : 'bg-yellow-100/50 decoration-yellow-300/50'
        
        // WeChat Public Account Style Highlight:
        // Dashed underline + subtle background + small marker
        const summary = anno.anno_summary || 'AI 注解'
        const highlightHtml = `<span ${idAttr} class="relative inline cursor-pointer group/anno transition-all duration-300 border-b-2 border-dashed border-primary-400/60 hover:bg-primary-50 hover:border-solid hover:border-primary-500 ${focusClass} rounded-sm px-0.5 mx-0.5" onclick="document.dispatchEvent(new CustomEvent('note-click', {detail: '${anno.anno_id}'}))">
            ${quote}
            <sup class="inline-flex items-center justify-center w-3.5 h-3.5 text-[8px] font-bold text-white bg-primary-400 rounded-full align-top ml-0.5 -mt-0.5 select-none opacity-80 group-hover/anno:opacity-100 shadow-sm">注</sup>
            
            <!-- Tooltip for small screens (hidden on XL+) -->
            <span class="xl:hidden absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-max max-w-[200px] bg-slate-800 text-white text-xs px-3 py-2 rounded-xl shadow-xl opacity-0 group-hover/anno:opacity-100 transition-all duration-300 translate-y-2 group-hover/anno:translate-y-0 pointer-events-none z-50 flex flex-col gap-1 items-center">
                <span class="font-bold text-yellow-300 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse"></span>
                    AI Note
                </span>
                <span class="font-medium text-center leading-relaxed">${summary}</span>
                <svg class="absolute text-slate-800 h-2 w-4 left-1/2 -translate-x-1/2 top-full" viewBox="0 0 255 255" xml:space="preserve"><polygon class="fill-current" points="0,0 127.5,127.5 255,0"/></svg>
            </span>
        </span>`
        
        content = content.replace(quote, highlightHtml)
    }
    
    return renderMarkdown(content)
}

const splitContent = (content: string) => {
    if (!content) return { intro: '', body: '' }
    const parts = content.split('<!-- BODY_START -->')
    if (parts.length > 1) {
        return { intro: parts[0], body: parts[1] }
    }
    // If no delimiter, treat as intro
    return { intro: content, body: '' }
}

const exportContent = () => {
    if (flatNodes.value.length === 0) {
        ElMessage.warning('当前课程暂无内容可导出')
        return
    }
    
    const courseName = courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || 'Course'
    let content = `# ${courseName}\n\n`
    
    for (const node of flatNodes.value) {
        content += `${'#'.repeat(node.node_level)} ${node.node_name}\n\n`
        if (node.node_content) {
            // Remove internal delimiters for clean export
            const cleanContent = node.node_content.replace('<!-- BODY_START -->', '\n\n')
            content += `${cleanContent}\n\n`
        }
    }

    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${courseName}_Export.md`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('课程内容已导出')
}
</script>

<style scoped>
:deep(.prose h1), :deep(.prose h2), :deep(.prose h3) {
    color: var(--color-slate-800);
    font-weight: 700;
}
:deep(.prose p) {
    margin-bottom: 1.8em; /* Relaxed reading */
    text-align: justify;
}
:deep(.prose strong) {
    color: var(--color-primary-600);
    font-weight: 600;
}
:deep(.katex) {
    font-size: 1.15em;
}
/* Smooth scrolling for anchor links */
html {
    scroll-behavior: smooth;
}
</style>