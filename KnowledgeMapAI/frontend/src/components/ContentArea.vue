<template>
  <div class="h-full flex flex-col">
    <!-- Toolbar -->
    <div class="h-16 flex items-center justify-between px-4 lg:px-6 mx-2 lg:mx-6 mt-4 mb-2 sticky top-4 z-30 transition-all duration-300 glass-panel rounded-2xl">
      <div class="bg-white/50 backdrop-blur-sm rounded-full px-4 py-1.5 border border-white/40 shadow-sm flex items-center gap-2">
        <span class="font-bold text-slate-700 truncate max-w-[200px]">
            {{ courseStore.courseList.find(c => c.course_id === courseStore.currentCourseId)?.course_name || '课程预览' }}
        </span>
        <span class="text-slate-300">|</span>
        <span class="text-xs text-slate-500">全书模式</span>
      </div>
      
      <div class="flex gap-3">
        <div class="glass-segment flex items-center bg-white/40 rounded-lg p-1 border border-white/40">
            <el-button size="small" text :icon="Minus" @click="fontSize = Math.max(12, fontSize - 1)" class="!px-2 hover:!bg-white/80 !rounded-md !text-slate-600 !h-7" />
            <span class="text-xs text-slate-500 w-8 text-center font-mono select-none font-bold">{{ fontSize }}px</span>
            <el-button size="small" text :icon="Plus" @click="fontSize = Math.min(24, fontSize + 1)" class="!px-2 hover:!bg-white/80 !rounded-md !text-slate-600 !h-7" />
        </div>
        <button 
            class="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/80 border border-white/50 text-slate-600 hover:text-primary-600 flex items-center gap-2 transition-all shadow-sm hover:shadow-md text-xs font-bold" 
            @click="exportContent"
        >
            <el-icon><Download /></el-icon>
            <span>导出全书</span>
        </button>
      </div>
    </div>

    <!-- Content List (Continuous Scroll) -->
    <div class="flex-1 overflow-auto p-4 lg:p-10 relative scroll-smooth custom-scrollbar" id="content-scroll-container" @mouseup="handleMouseUp">
      
      <!-- Selection Menu -->
      <transition name="scale-fade">
        <div v-if="selectionMenu.visible" 
            class="fixed z-50 flex gap-1 p-1.5 bg-slate-800/90 backdrop-blur-xl rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.12)] border border-white/10 ring-1 ring-white/10"
            :style="{ left: selectionMenu.x + 'px', top: selectionMenu.y + 'px' }"
            @mousedown.stop>
            <div class="absolute inset-0 rounded-xl bg-gradient-to-br from-white/10 to-transparent pointer-events-none"></div>
            <button @click="handleExplain" class="relative z-10 flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20 rounded-lg transition-all group active:scale-95">
                <el-icon class="text-primary-300 group-hover:scale-110 group-hover:text-primary-200 transition-transform"><MagicStick /></el-icon> 
                <span class="text-shadow-sm">AI 深度解析</span>
            </button>
        </div>
      </transition>

      <div v-if="flatNodes.length > 0" class="w-full max-w-[96%] mx-auto space-y-12 pb-32">
        <div v-for="(node, index) in flatNodes" :key="node.node_id" :id="'node-' + node.node_id" 
             class="scroll-mt-24 transition-all duration-500 animate-fade-in-up"
             :style="{ animationDelay: (index * 100) + 'ms' }">
            
            <!-- Level 1: Course Title / Part -->
            <div v-if="node.node_level === 1" class="relative overflow-hidden rounded-[2.5rem] bg-white/60 backdrop-blur-2xl border border-white/60 shadow-xl shadow-purple-500/5 mb-24 group hover:shadow-2xl hover:shadow-purple-500/10 transition-shadow duration-500">
                <!-- Background Decor -->
                <div class="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-white/20 pointer-events-none"></div>
                <div class="absolute -top-[40%] -right-[20%] w-[80%] h-[120%] bg-gradient-to-b from-primary-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                <div class="absolute -bottom-[40%] -left-[20%] w-[80%] h-[120%] bg-gradient-to-t from-pink-100/40 to-transparent rounded-full blur-[100px] pointer-events-none opacity-60 mix-blend-multiply"></div>
                
                <div class="relative z-10 p-16 lg:p-24 flex flex-col items-center text-center">
                    <!-- Badge -->
                    <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/80 border border-slate-200/60 shadow-sm backdrop-blur-md mb-10 group-hover:-translate-y-1 transition-transform duration-500">
                        <span class="relative flex h-2 w-2">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                        </span>
                        <span class="text-[10px] font-bold tracking-widest text-slate-500 uppercase font-sans">Interactive Course</span>
                    </div>

                    <!-- Title -->
                    <h1 class="text-5xl lg:text-7xl font-black text-slate-800 mb-8 tracking-tighter drop-shadow-sm font-display leading-[1.1] max-w-6xl bg-clip-text text-transparent bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
                        {{ node.node_name.replace(/《|》/g, '') }}
                    </h1>

                    <!-- Divider -->
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
                 
                 <!-- Quiz Button -->
                 <div class="absolute right-0 top-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <button 
                      class="glass-icon-btn !w-auto !px-3 !h-8 !rounded-full bg-white/50 hover:bg-white/90 text-xs gap-2"
                      @click="handleStartQuiz(node)" 
                      title="智能测验"
                    >
                      <el-icon><VideoPlay /></el-icon>
                      <span>本章测验</span>
                    </button>
                 </div>
            </div>

            <!-- Level 3+: Content Card -->
            <div v-else class="group relative pl-8 border-l-2 border-slate-100 hover:border-primary-300 transition-colors duration-300">
                <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-slate-50 border-2 border-slate-200 group-hover:border-primary-500 group-hover:bg-primary-50 transition-all duration-300"></div>
                
                <h3 class="text-xl font-bold text-slate-800 mb-4 flex items-center gap-3">
                    {{ node.node_name }}
                    <div class="opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex gap-2">
                        <button class="p-1 text-slate-400 hover:text-primary-500 rounded-md hover:bg-slate-100 transition-colors" @click="handleStartQuiz(node)" title="小节测验">
                            <el-icon><VideoPlay /></el-icon>
                        </button>
                    </div>
                </h3>
                
                <div class="glass-panel p-6 lg:p-8 rounded-2xl relative overflow-hidden group-hover:shadow-lg transition-shadow duration-300">
                    <div class="prose prose-slate max-w-none prose-headings:font-display prose-headings:text-slate-800 prose-p:text-slate-600 prose-a:text-primary-600 hover:prose-a:text-primary-500 prose-strong:text-slate-700 prose-code:text-primary-600 prose-code:bg-primary-50 prose-pre:bg-slate-800 prose-pre:shadow-lg" 
                         :style="{ fontSize: fontSize + 'px' }"
                         v-html="renderMarkdown(node.node_content)">
                    </div>
                    
                    <!-- Copy Buttons for Code Blocks (Injected via JS, handled globally) -->
                </div>
            </div>
        </div>
      </div>

      <!-- Empty Selection Guide -->
      <div v-else-if="!courseStore.currentCourseId" class="flex flex-col items-center justify-center h-full text-slate-400 animate-in fade-in zoom-in duration-500">
          <div class="w-32 h-32 bg-slate-50 rounded-full flex items-center justify-center mb-6 shadow-inner relative overflow-hidden">
              <div class="absolute inset-0 bg-gradient-to-tr from-slate-100 to-transparent opacity-50"></div>
              <el-icon :size="48" class="opacity-30 text-slate-500"><Notebook /></el-icon>
          </div>
          <h3 class="text-xl font-bold text-slate-600 mb-2">开始您的学习之旅</h3>
          <p class="text-sm font-medium opacity-60">请从左侧选择一个课程或章节开始阅读</p>
      </div>
      
      <!-- Loading State -->
      <div v-else class="flex flex-col items-center justify-center h-64 gap-4">
          <div class="w-12 h-12 border-4 border-primary-200 border-t-primary-500 rounded-full animate-spin"></div>
          <p class="text-sm text-slate-500 font-medium animate-pulse">正在加载精彩内容...</p>
      </div>

    </div>

    <!-- Quiz Dialog -->
    <el-dialog
      v-model="quizVisible"
      title="智能测验"
      width="600px"
      class="glass-dialog"
      align-center
      append-to-body
    >
      <div v-if="generatingQuiz" class="flex flex-col items-center justify-center py-12">
        <div class="w-16 h-16 relative mb-4">
             <div class="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
             <div class="absolute inset-0 border-4 border-primary-500 rounded-full border-t-transparent animate-spin"></div>
        </div>
        <p class="text-slate-600 font-medium">AI 正在出题中...</p>
      </div>
      <div v-else class="py-2">
        <div v-for="(q, idx) in quizQuestions" :key="idx" class="mb-8 last:mb-0">
          <p class="font-bold text-slate-800 mb-3 text-lg">{{ idx + 1 }}. {{ q.question }}</p>
          <div class="space-y-2">
            <div 
              v-for="(opt, oIdx) in q.options" 
              :key="oIdx"
              class="p-3 rounded-xl border border-slate-200 cursor-pointer transition-all duration-200 hover:border-primary-300 hover:bg-primary-50/30 flex items-center gap-3"
              :class="{ 
                '!bg-emerald-50 !border-emerald-500': quizSubmitted && opt === q.answer,
                '!bg-red-50 !border-red-500': quizSubmitted && userAnswers[idx] === opt && opt !== q.answer,
                'bg-primary-50 border-primary-500': userAnswers[idx] === opt && !quizSubmitted
              }"
              @click="!quizSubmitted && (userAnswers[idx] = opt)"
            >
              <div class="w-5 h-5 rounded-full border flex items-center justify-center text-xs transition-colors"
                   :class="{
                     'border-emerald-500 bg-emerald-500 text-white': quizSubmitted && opt === q.answer,
                     'border-red-500 bg-red-500 text-white': quizSubmitted && userAnswers[idx] === opt && opt !== q.answer,
                     'border-primary-500 bg-primary-500 text-white': userAnswers[idx] === opt && !quizSubmitted,
                     'border-slate-300 text-slate-400': userAnswers[idx] !== opt && !(quizSubmitted && opt === q.answer)
                   }">
                  <span v-if="quizSubmitted && opt === q.answer"><el-icon><Check /></el-icon></span>
                  <span v-else-if="quizSubmitted && userAnswers[idx] === opt && opt !== q.answer"><el-icon><Close /></el-icon></span>
                  <span v-else>{{ ['A','B','C','D'][oIdx] }}</span>
              </div>
              <span class="text-slate-700 font-medium">{{ opt }}</span>
            </div>
          </div>
          <div v-if="quizSubmitted" class="mt-3 text-sm bg-slate-50 p-3 rounded-lg text-slate-600">
             <span class="font-bold text-slate-800">解析：</span> {{ q.explanation }}
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-3" v-if="!generatingQuiz">
          <el-button @click="quizVisible = false" class="!border-none !bg-slate-100 hover:!bg-slate-200 text-slate-600">关闭</el-button>
          <el-button v-if="!quizSubmitted" type="primary" @click="submitQuiz" class="bg-gradient-to-r from-primary-500 to-primary-600 border-none shadow-lg shadow-primary-500/30 hover:shadow-primary-500/40">
            提交答案
          </el-button>
          <el-button v-else type="primary" @click="quizVisible = false">
            完成
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCourseStore } from '../stores/course'
import { marked } from 'marked'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'
import { Minus, Plus, Download, MagicStick, VideoPlay, Notebook, Check, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const fontSize = ref(16)
const selectionMenu = ref({ visible: false, x: 0, y: 0, text: '' })

// Quiz State
const quizVisible = ref(false)
const generatingQuiz = ref(false)
const quizQuestions = ref<any[]>([])
const userAnswers = ref<string[]>([])
const quizSubmitted = ref(false)

const flatNodes = computed(() => {
    if (!courseStore.treeData || courseStore.treeData.length === 0) return []
    const nodes: any[] = []
    const traverse = (data: any[]) => {
        for (const node of data) {
            nodes.push(node)
            if (node.children && node.children.length > 0) {
                traverse(node.children)
            }
        }
    }
    traverse(courseStore.treeData)
    return nodes
})

const renderMarkdown = (content: string) => {
    if (!content) return ''
    
    // Add Copy Buttons to Code Blocks
    const renderer = new marked.Renderer()
    renderer.code = ({ text, lang, escaped }: any) => {
        const validLang = !!(lang && hljs.getLanguage(lang)) ? lang : 'plaintext'
        const highlighted = hljs.highlight(text, { language: validLang }).value
        return `<div class="relative group my-4 rounded-xl overflow-hidden shadow-sm border border-slate-200/60 bg-[#1e293b]">
                  <div class="flex items-center justify-between px-4 py-2 bg-slate-800/50 border-b border-white/5">
                      <div class="flex gap-1.5">
                          <div class="w-3 h-3 rounded-full bg-red-400/80"></div>
                          <div class="w-3 h-3 rounded-full bg-amber-400/80"></div>
                          <div class="w-3 h-3 rounded-full bg-emerald-400/80"></div>
                      </div>
                      <span class="text-xs text-slate-400 font-mono">${validLang}</span>
                  </div>
                  <button class="copy-btn absolute top-2 right-2 p-1.5 text-slate-400 hover:text-white rounded-lg opacity-0 group-hover:opacity-100 transition-opacity bg-white/10 hover:bg-white/20" data-code="${encodeURIComponent(text)}">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                  </button>
                  <pre class="!m-0 !p-4 !bg-transparent overflow-x-auto text-sm font-mono leading-relaxed"><code class="hljs ${validLang}">${highlighted}</code></pre>
                </div>`
    }
    
    marked.setOptions({ renderer })
    const rawHtml = marked(content)
    return DOMPurify.sanitize(rawHtml)
}

const exportContent = () => {
    // Export logic
    ElMessage.success('导出功能开发中')
}

// Selection Handling
const handleMouseUp = (e: MouseEvent) => {
    const selection = window.getSelection()
    if (selection && selection.toString().trim().length > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        selectionMenu.value = {
            visible: true,
            x: rect.left + (rect.width / 2) - 50, // Center horizontally
            y: rect.top - 40, // Position above
            text: selection.toString()
        }
    } else {
        selectionMenu.value.visible = false
    }
}

const handleExplain = () => {
    if (selectionMenu.value.text) {
        courseStore.addMessage('user', `请解释一下这段内容：\n> ${selectionMenu.value.text}`)
        selectionMenu.value.visible = false
        // Scroll to chat (optional)
    }
}

// Quiz Handling
const handleStartQuiz = async (node: any) => {
    quizVisible.value = true
    generatingQuiz.value = true
    quizSubmitted.value = false
    userAnswers.value = []
    
    try {
        const questions = await courseStore.generateQuiz(node.node_id, node.node_content)
        quizQuestions.value = questions
        userAnswers.value = new Array(questions.length).fill('')
    } catch (error) {
        ElMessage.error('生成题目失败，请重试')
        quizVisible.value = false
    } finally {
        generatingQuiz.value = false
    }
}

const submitQuiz = () => {
    if (userAnswers.value.some(a => !a)) {
        ElMessage.warning('请完成所有题目后再提交')
        return
    }
    quizSubmitted.value = true
    
    // Calculate score
    let correct = 0
    quizQuestions.value.forEach((q, i) => {
        if (q.answer === userAnswers.value[i]) correct++
    })
    
    if (correct === quizQuestions.value.length) {
        ElMessage.success(`太棒了！全对！`)
    } else {
        ElMessage.info(`答对 ${correct}/${quizQuestions.value.length} 题，继续加油！`)
    }
}

onMounted(() => {
    document.addEventListener('mousedown', (e) => {
        if (selectionMenu.value.visible && !(e.target as HTMLElement).closest('#content-scroll-container')) {
            selectionMenu.value.visible = false
        }
    })
})
</script>

<style scoped>
.scale-fade-enter-active,
.scale-fade-leave-active {
  transition: all 0.2s ease;
}

.scale-fade-enter-from,
.scale-fade-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

:deep(.glass-dialog) {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.5);
}

:deep(.el-dialog__header) {
    margin-right: 0;
    padding: 20px 24px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}

:deep(.el-dialog__title) {
    font-weight: 800;
    color: #1e293b;
    font-size: 1.125rem;
}

:deep(.el-dialog__body) {
    padding: 24px;
}
</style>