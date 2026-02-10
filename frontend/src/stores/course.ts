import { defineStore } from 'pinia'
import http from '../utils/http'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const GENERATION_STATE_KEY = 'course-generation-state-v1'
const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_').trim()
const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

export interface Node {
  node_id: string
  parent_node_id: string
  node_name: string
  node_level: number
  node_content: string
  node_type: 'original' | 'custom' | 'extend'
  children?: Node[]
  is_read?: boolean
  quiz_score?: number
}

export interface Annotation {
  anno_id: string
  node_id: string
  question: string
  answer: string
  anno_summary: string
  source_type: string
  quote?: string
}

export interface Note {
    id: string
    nodeId: string
    highlightId: string
    quote: string
    content: string
    summary?: string // The concise summary (概括)
    color: string
    createdAt: number
    top?: number // Dynamic position for rendering
    sourceType?: 'user' | 'ai' | 'format' | 'wrong'
    style?: 'bold' | 'underline' | 'wave' | 'dashed' | 'highlight' | 'solid' | 'wavy'
    title?: string // Optional note title
    expanded?: boolean
}

export interface Course {
    course_id: string
    course_name: string
    node_count: number
}

export interface QueueItem {
    uuid: string
    courseId: string
    type: 'structure' | 'content' | 'subchapter'
    targetNodeId: string
    title: string
    status: 'pending' | 'running' | 'completed' | 'error'
    errorMsg?: string
}

export interface Task {
    id: string // courseId
    courseName: string
    status: 'idle' | 'running' | 'paused' | 'completed' | 'error'
    progress: number
    currentStep: string // "Generating Chapter X"
    logs: string[]
    nodes: Node[] // Local copy of nodes for background processing
    shouldStop: boolean // Flag to signal stop
}

export interface AIContent {
    core_answer: string
    detail_answer?: unknown[]
    quote?: string
    anno_summary?: string
    anno_id?: string
    node_id?: string
    question?: string
    answer?: string
    quiz?: {
        question: string
        options: string[]
        answer: string
        correct_index?: number
        explanation?: string
        node_id?: string
        isReview?: boolean
    }
    quiz_list?: {
        question: string
        options: string[]
        answer?: string
        correct_index?: number
        explanation?: string
        node_id?: string
        isReview?: boolean
    }[]
}

export interface ChatMessage {
    type: 'user' | 'ai'
    content: string | AIContent
}

export const useCourseStore = defineStore('course', {
  state: () => ({
    courseList: [] as Course[],
    currentCourseId: '' as string,
    courseTree: [] as Node[],
    nodes: [] as Node[], 
    currentNode: null as Node | null,
    annotations: [] as Annotation[],
    loading: false,
    chatHistory: [] as ChatMessage[],
    
    // --- Task Management System ---
    tasks: new Map<string, Task>(), // courseId -> Task
    activeTaskId: null as string | null,
    
    // --- Queue System (Playlist Style) ---
    queue: [] as QueueItem[],
    isQueueProcessing: false,

    // Legacy/UI Compatibility State (mapped from active task)
    isGenerating: false,
    generationStatus: 'idle' as 'idle' | 'generating' | 'paused' | 'error',
    generationLogs: [] as string[],
    currentGeneratingNode: null as string | null,
    currentGeneratingNodeId: null as string | null,
    generationProgress: 0,
    
    // Typewriter effect buffer
    typingBuffer: new Map<string, string>(),
    typingInterval: null as number | null,
    
    // Context-aware Q&A
    activeAnnotation: null as Annotation | null,
    scrollToNodeId: null as string | null,
    focusNoteId: null as string | null,
    pendingChatInput: '' as string, // For quoting text to chat
    userPersona: localStorage.getItem('user_persona') || '',
    chatLoading: false,
    chatAbortController: null as AbortController | null,
    
    // UI State
    isFocusMode: false,
    showKnowledgeGraph: false,
    isMobileNotesVisible: false,
    globalSearchQuery: '',
    uiSettings: {
        fontSize: 17, // Default font size
        fontFamily: 'sans' as 'sans' | 'serif' | 'mono',
        lineHeight: 1.75
    },
    
    // Notes System
    notes: [] as Note[],

    // Learning Statistics
    learningStats: {
        totalStudyTime: 0, // minutes
        dailyStudyTime: {} as Record<string, number>, // date -> minutes
        nodeReadTime: {} as Record<string, number>, // nodeId -> minutes
        lastReadPosition: {} as Record<string, { nodeId: string; scrollTop: number }>, // courseId -> position
        completedNodes: [] as string[], // nodeIds that are fully read
        streakDays: 0,
        lastStudyDate: null as string | null,
        studyDays: 0, // Total days studied
    },

    // Quiz System
    wrongAnswers: [] as Array<{
        question: string
        options: string[]
        correctIndex: number
        userIndex: number
        explanation: string
        nodeId: string
        nodeName: string
        timestamp: number
        reviewCount: number
    }>,
    quizHistory: [] as Array<{
        nodeId: string
        nodeName: string
        totalQuestions: number
        correctCount: number
        timestamp: number
    }>,

    // State Restoration Flag
    stateRestored: false,
  }),
  getters: {
    treeData: (state) => state.courseTree,
    getNotesByNodeId: (state) => (nodeId: string) => state.notes.filter(n => n.nodeId === nodeId),
    currentCourse: (state) => state.courseList.find(c => c.course_id === state.currentCourseId),
  },
  actions: {
    setUiSettings(settings: Partial<typeof this.uiSettings>) {
        this.uiSettings = { ...this.uiSettings, ...settings }
    },
    addNote(note: Note) {
        this.notes.push(note)
    },
    updateUserPersona(persona: string) {
        this.userPersona = persona
        localStorage.setItem('user_persona', persona)
    },

    // ========== Learning Statistics ==========
    recordStudyTime(minutes: number, nodeId?: string) {
        const today = dayjs().format('YYYY-MM-DD')

        // Update total time
        this.learningStats.totalStudyTime += minutes

        // Update daily time
        if (!this.learningStats.dailyStudyTime[today]) {
            this.learningStats.dailyStudyTime[today] = 0
        }
        this.learningStats.dailyStudyTime[today] += minutes

        // Update node-specific time
        if (nodeId) {
            if (!this.learningStats.nodeReadTime[nodeId]) {
                this.learningStats.nodeReadTime[nodeId] = 0
            }
            this.learningStats.nodeReadTime[nodeId] += minutes
        }

        // Update streak
        const todayStr = dayjs().format('YYYY-MM-DD')
        const lastDate = this.learningStats.lastStudyDate

        if (lastDate) {
            const diff = dayjs(todayStr).diff(dayjs(lastDate), 'day')
            if (diff === 1) {
                // Consecutive day
                this.learningStats.streakDays += 1
            } else if (diff > 1) {
                // Streak broken
                this.learningStats.streakDays = 1
            }
        } else {
            this.learningStats.streakDays = 1
        }

        this.learningStats.lastStudyDate = todayStr

        // Persist to localStorage
        this.persistLearningStats()
    },

    saveReadingPosition(courseId: string, nodeId: string, scrollTop: number) {
        this.learningStats.lastReadPosition[courseId] = { nodeId, scrollTop }
        this.persistLearningStats()
    },

    getReadingPosition(courseId: string): { nodeId: string; scrollTop: number } | null {
        return this.learningStats.lastReadPosition[courseId] || null
    },

    markNodeAsCompleted(nodeId: string) {
        if (!this.learningStats.completedNodes.includes(nodeId)) {
            this.learningStats.completedNodes.push(nodeId)
            this.persistLearningStats()
        }
    },

    isNodeCompleted(nodeId: string): boolean {
        return this.learningStats.completedNodes.includes(nodeId)
    },

    getNodeReadTime(nodeId: string): number {
        return this.learningStats.nodeReadTime[nodeId] || 0
    },

    getTodayStudyTime(): number {
        const today = dayjs().format('YYYY-MM-DD')
        return this.learningStats.dailyStudyTime[today] || 0
    },

    getWeeklyStudyTime(): number {
        let total = 0
        for (let i = 0; i < 7; i++) {
            const date = dayjs().subtract(i, 'day').format('YYYY-MM-DD')
            total += this.learningStats.dailyStudyTime[date] || 0
        }
        return total
    },

    persistLearningStats() {
        try {
            localStorage.setItem('learning_stats', JSON.stringify(this.learningStats))
        } catch (e) {
            console.error('Failed to persist learning stats:', e)
        }
    },

    restoreLearningStats() {
        try {
            const raw = localStorage.getItem('learning_stats')
            if (raw) {
                const stats = JSON.parse(raw)
                this.learningStats = { ...this.learningStats, ...stats }
            }
        } catch (e) {
            console.error('Failed to restore learning stats:', e)
        }
    },

    // ========== Note Export Functions ==========
    exportNotesToMarkdown(): string {
        const notes = this.notes
        if (notes.length === 0) {
            return '# 学习笔记\n\n暂无笔记内容。'
        }

        let markdown = '# 学习笔记导出\n\n'
        markdown += `导出时间：${dayjs().format('YYYY-MM-DD HH:mm:ss')}\n\n`
        markdown += `---\n\n`

        // Group notes by source type
        const groupedNotes = {
            user: notes.filter(n => n.sourceType === 'user' || !n.sourceType),
            ai: notes.filter(n => n.sourceType === 'ai'),
            wrong: notes.filter(n => n.sourceType === 'wrong'),
            format: notes.filter(n => n.sourceType === 'format')
        }

        // Export wrong questions first (important)
        if (groupedNotes.wrong.length > 0) {
            markdown += '## 📝 错题记录\n\n'
            groupedNotes.wrong.forEach((note, idx) => {
                markdown += `### 错题 ${idx + 1}\n\n`
                markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
                if (note.quote) {
                    markdown += `**题目**：\n> ${note.quote}\n\n`
                }
                markdown += `${note.content}\n\n`
                markdown += `---\n\n`
            })
        }

        // Export AI Q&A notes
        if (groupedNotes.ai.length > 0) {
            markdown += '## 💬 AI 问答记录\n\n'
            groupedNotes.ai.forEach((note, idx) => {
                markdown += `### 问答 ${idx + 1}\n\n`
                markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
                if (note.quote) {
                    markdown += `**引用**：\n> ${note.quote}\n\n`
                }
                markdown += `${note.content}\n\n`
                markdown += `---\n\n`
            })
        }

        // Export user notes
        if (groupedNotes.user.length > 0) {
            markdown += '## ✏️ 个人笔记\n\n'
            groupedNotes.user.forEach((note, idx) => {
                markdown += `### 笔记 ${idx + 1}\n\n`
                markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
                if (note.quote) {
                    markdown += `**引用**：\n> ${note.quote}\n\n`
                }
                markdown += `${note.content}\n\n`
                markdown += `---\n\n`
            })
        }

        return markdown
    },

    exportNotesToJSON(): string {
        const exportData = {
            exportTime: dayjs().format('YYYY-MM-DD HH:mm:ss'),
            totalNotes: this.notes.length,
            notes: this.notes.map(note => ({
                ...note,
                createdAtFormatted: dayjs(note.createdAt).format('YYYY-MM-DD HH:mm:ss')
            }))
        }
        return JSON.stringify(exportData, null, 2)
    },

    downloadNotes(format: 'markdown' | 'json' = 'markdown') {
        const content = format === 'markdown' ? this.exportNotesToMarkdown() : this.exportNotesToJSON()
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
        const filename = `学习笔记_${dayjs().format('YYYYMMDD')}.${format === 'markdown' ? 'md' : 'json'}`
        downloadBlob(blob, filename)
    },

    persistGenerationState() {
        try {
            const tasks = Array.from(this.tasks.values()).map(task => ({
                id: task.id,
                courseName: task.courseName,
                status: task.status,
                progress: task.progress,
                currentStep: task.currentStep,
                logs: task.logs,
                nodes: task.nodes,
                shouldStop: false
            }))
            const queue = this.queue.map(item => ({ ...item }))
            const data = {
                version: 1,
                currentCourseId: this.currentCourseId,
                tasks,
                queue
            }
            localStorage.setItem(GENERATION_STATE_KEY, JSON.stringify(data))
        } catch (e) {
            console.error(e)
        }
    },

    restoreGenerationState() {
        if (this.stateRestored) {
            return this.currentCourseId
        }
        const raw = localStorage.getItem(GENERATION_STATE_KEY)
        if (!raw) return null
        try {
            const data = JSON.parse(raw)
            const tasks = new Map<string, Task>()
            if (Array.isArray(data.tasks)) {
                data.tasks.forEach((task: Task) => {
                    tasks.set(task.id, {
                        ...task,
                        shouldStop: false
                    })
                })
            }
            const normalizedQueue = Array.isArray(data.queue)
                ? data.queue.filter((item: QueueItem) => item.status === 'completed' || item.status === 'error')
                : []

            this.tasks = tasks
            this.queue = normalizedQueue
            this.isQueueProcessing = false

            // DO NOT restore currentCourseId. 
            // We want the user to start fresh on the home page.
            this.currentCourseId = ''

            // Reset all running/paused tasks to idle and do NOT resume
            this.tasks.forEach(task => {
                if (task.status === 'running' || task.status === 'paused') {
                    task.status = 'idle'
                    task.currentStep = ''
                    this.addLogToTask(task.id, '⏹️ 未完成的任务已停止')
                }
            })
            
            this.stateRestored = true
            return null
        } catch (e) {
            console.error(e)
            return null
        }
    },

    finalizeIdleTasks() {
        let updated = false
        this.tasks.forEach(task => {
            const hasWork = this.queue.some(i => i.courseId === task.id && (i.status === 'pending' || i.status === 'running'))
            if (task.status === 'running' && !hasWork) {
                task.status = 'completed'
                task.progress = 100
                task.currentStep = ''
                this.addLogToTask(task.id, '✅ 生成完成')
                updated = true
            }
        })
        if (updated) {
            this.isGenerating = false
            if (this.currentCourseId) {
                const currentTask = this.tasks.get(this.currentCourseId)
                if (!currentTask || currentTask.status !== 'running') {
                    this.generationStatus = 'idle'
                }
            }
            this.persistGenerationState()
        }
    },

    async markNodeAsRead(nodeId: string) {
        const node = this.nodes.find(n => n.node_id === nodeId)
        if (node && !node.is_read) {
            node.is_read = true
            try {
                await http.put(`/courses/${this.currentCourseId}/nodes/${nodeId}`, { is_read: true })
            } catch (e) {
                console.error('Failed to sync read status', e)
            }
        }
    },

    async updateNodeScore(nodeId: string, score: number) {
        const node = this.nodes.find(n => n.node_id === nodeId)
        if (node) {
            // Keep best score
            if (!node.quiz_score || score > node.quiz_score) {
                node.quiz_score = score
                try {
                    await http.put(`/courses/${this.currentCourseId}/nodes/${nodeId}`, { quiz_score: score })
                } catch (e) {
                    console.error('Failed to sync quiz score', e)
                }
            }
        }
    },

    async createNote(note: Note) {
        this.addNote(note)
        // Persist to backend
        try {
            await this.saveAnnotation({
                anno_id: note.id,
                node_id: note.nodeId,
                question: note.sourceType === 'ai' ? 'AI Assistant Note' : 'User Note',
                answer: note.content,
                anno_summary: note.summary || (note.content.length > 50 ? note.content.slice(0, 50) + '...' : note.content),
                quote: note.quote,
                source_type: note.sourceType || 'user'
            })
        } catch (e) {
            console.error('Failed to persist note', e)
        }
    },
    async updateNote(id: string, content: string) {
        const note = this.notes.find(n => n.id === id)
        if (note) {
            note.content = content
            try {
                await http.put(`/annotations/${id}`, { content })
            } catch (e) {
                console.error('Failed to update note persistence', e)
                ElMessage.warning('笔记保存失败，请重试')
            }
        }
    },
    async deleteNote(id: string) {
        const index = this.notes.findIndex(n => n.id === id)
        if (index !== -1) {
            this.notes.splice(index, 1)
            // Persist to backend
            try {
                await http.delete(`/annotations/${id}`)
                // Also remove from legacy annotations if present
                this.annotations = this.annotations.filter(a => a.anno_id !== id)
            } catch (e) {
                console.error('Failed to delete note persistence', e)
            }
        }
    },
    createTask(courseId: string, courseName: string, nodes: Node[]): Task {
        const task: Task = {
            id: courseId,
            courseName: courseName,
            status: 'idle',
            progress: 0,
            currentStep: '',
            logs: [],
            nodes: JSON.parse(JSON.stringify(nodes)), // Deep copy for task isolation
            shouldStop: false
        }
        this.tasks.set(courseId, task)
        this.persistGenerationState()
        return task
    },

    async createCourse(courseName: string) {
        try {
            const res = await http.post('/generate_course', { keyword: courseName })
            if (res.data) {
                const courseId = res.data.course_id
                // Initialize empty task/state if needed
                await this.fetchCourseList()
                return courseId
            }
        } catch (error) {
            console.error(error)
            throw error
        }
    },

    async sendMessage(message: string) {
        this.chatLoading = true
        try {
            await this.askQuestion(message)
        } finally {
            this.chatLoading = false
        }
    },

    cancelChat() {
        if (this.chatAbortController) {
            this.chatAbortController.abort()
        }
    },

    addMessage(type: 'user' | 'ai', content: string | AIContent) {
        this.chatHistory.push({ type, content })
    },

    scrollToNode(nodeId: string) {
        this.scrollToNodeId = null
        setTimeout(() => {
            this.scrollToNodeId = nodeId
        }, 10)
    },

    scrollToNote(noteId: string) {
        // Just trigger the action, let the component handle the DOM
        this.focusNoteId = null
        setTimeout(() => {
            this.focusNoteId = noteId
        }, 10)
    },

    setPendingChatInput(text: string) {
        this.pendingChatInput = text
    },

    // --- Task Actions ---
    getTask(courseId: string) {
        return this.tasks.get(courseId)
    },

    pauseTask(courseId: string) {
        const task = this.tasks.get(courseId)
        if (task) {
            task.status = 'paused'
            task.shouldStop = true
            this.addLogToTask(courseId, '⏸️ 任务已暂停')
            this.persistGenerationState()
        }
    },

    startTask(courseId: string) {
        const task = this.tasks.get(courseId)
        if (task) {
            task.status = 'running'
            task.shouldStop = false
            this.addLogToTask(courseId, '▶️ 任务继续')
            
            // Check if queue needs repopulation (e.g. after restart)
            const hasPending = this.queue.some(i => i.courseId === courseId && (i.status === 'pending' || i.status === 'running'))
            if (!hasPending) {
                 this.addLogToTask(courseId, '🔄 正在检查未完成章节...')
                 this.generateFullDetails(courseId)
            }

            this.persistGenerationState()
            // Trigger queue processing if it was stopped
            this.processQueue()
        }
    },
    
    clearChat() {
        this.chatHistory = []
        this.activeAnnotation = null
    },

    async generateQuiz(nodeId: string, nodeContent: string, style: string = 'standard', difficulty: string = 'medium', options: { silent?: boolean, questionCount?: number } = {}) {
        this.chatLoading = true
        const silent = options.silent === true
        const questionCount = options.questionCount || 3
        if (!silent) {
            this.chatHistory.push({
                type: 'user',
                content: `请为"${this.nodes.find(n => n.node_id === nodeId)?.node_name || '当前章节'}"生成一份${difficulty === 'hard' ? '困难' : (difficulty === 'easy' ? '简单' : '中等')}难度的${style === 'creative' ? '创意' : (style === 'practical' ? '实战' : '标准')}测试题（共${questionCount}题）。`
            })
        }
        
        try {
            const res = await http.post(`/courses/${this.currentCourseId}/nodes/${nodeId}/quiz`, {
                node_content: nodeContent,
                node_name: this.nodes.find(n => n.node_id === nodeId)?.node_name || '',
                difficulty: difficulty,
                style: style,
                user_persona: this.userPersona,
                question_count: questionCount
            })
            
            // The backend returns a list of questions. We'll add them as AI messages.
            // For now, let's just handle the first one or all of them.
            // Typically "Generate Quiz" implies a set.
            // But the UI in ChatPanel seems to handle one quiz object per message nicely.
            // Let's add them as separate messages or a single message with multiple quizzes?
            // The current ChatPanel handles `msg.content.quiz` as a SINGLE object.
            // Let's change backend to return one quiz? No, backend returns List.
            // We will iterate and add them.
            
            if (Array.isArray(res.data)) {
                if (res.data.length === 0) {
                    if (!silent) {
                        this.chatHistory.push({
                            type: 'ai',
                            content: '抱歉，无法根据当前内容生成测试题。'
                        })
                    }
                } else if (!silent) {
                    const title = `### 📝 ${style === 'creative' ? '创意挑战' : (style === 'practical' ? '实战演练' : '知识测验')}\n这里有几道题目来检测你的学习成果：`
                    this.chatHistory.push({
                        type: 'ai',
                        content: {
                            core_answer: title,
                            answer: title,
                            quiz_list: res.data.map((quizItem: any) => ({
                                ...quizItem,
                                node_id: nodeId
                            }))
                        }
                    })
                }
            }
            
            return Array.isArray(res.data) ? res.data : []
        } catch (error) {
            ElMessage.error('生成测验失败')
            if (!silent) {
                this.chatHistory.push({
                    type: 'ai',
                    content: '生成测验时遇到错误，请稍后再试。'
                })
            }
            return []
        } finally {
            this.chatLoading = false
        }
    },

    // ========== Enhanced Quiz System ==========
    recordWrongAnswer(quizData: {
        question: string
        options: string[]
        correctIndex: number
        userIndex: number
        explanation: string
        nodeId: string
        nodeName: string
    }) {
        const existingIndex = this.wrongAnswers.findIndex(
            w => w.question === quizData.question && w.nodeId === quizData.nodeId
        )

        if (existingIndex >= 0) {
            // Update existing wrong answer
            const existing = this.wrongAnswers[existingIndex]
            if (existing) {
                existing.reviewCount += 1
                existing.timestamp = Date.now()
            }
        } else {
            // Add new wrong answer
            this.wrongAnswers.push({
                ...quizData,
                timestamp: Date.now(),
                reviewCount: 1
            })
        }

        // Persist to localStorage
        this.persistQuizData()
    },

    recordQuizResult(nodeId: string, nodeName: string, total: number, correct: number) {
        this.quizHistory.push({
            nodeId,
            nodeName,
            totalQuestions: total,
            correctCount: correct,
            timestamp: Date.now()
        })
        this.persistQuizData()
    },

    persistQuizData() {
        try {
            localStorage.setItem('quiz_wrong_answers', JSON.stringify(this.wrongAnswers))
            localStorage.setItem('quiz_history', JSON.stringify(this.quizHistory))
        } catch (e) {
            console.error('Failed to persist quiz data:', e)
        }
    },

    restoreQuizData() {
        try {
            const wrongRaw = localStorage.getItem('quiz_wrong_answers')
            const historyRaw = localStorage.getItem('quiz_history')

            if (wrongRaw) {
                this.wrongAnswers = JSON.parse(wrongRaw)
            }
            if (historyRaw) {
                this.quizHistory = JSON.parse(historyRaw)
            }
        } catch (e) {
            console.error('Failed to restore quiz data:', e)
        }
    },

    // Get wrong answers that need review (sorted by review count and time)
    getWrongAnswersForReview(limit: number = 10) {
        return this.wrongAnswers
            .sort((a, b) => {
                // Prioritize: fewer reviews first, then older ones
                if (a.reviewCount !== b.reviewCount) {
                    return a.reviewCount - b.reviewCount
                }
                return a.timestamp - b.timestamp
            })
            .slice(0, limit)
    },

    // Mark wrong answer as reviewed (remove or increment)
    markWrongAnswerReviewed(question: string, nodeId: string, remove: boolean = false) {
        const index = this.wrongAnswers.findIndex(
            w => w.question === question && w.nodeId === nodeId
        )

        if (index >= 0) {
            const wrongAnswer = this.wrongAnswers[index]
            if (remove) {
                this.wrongAnswers.splice(index, 1)
            } else if (wrongAnswer) {
                wrongAnswer.reviewCount += 1
                wrongAnswer.timestamp = Date.now()
            }
            this.persistQuizData()
        }
    },

    // Generate smart quiz based on wrong answers
    async generateSmartQuizFromMistakes() {
        const wrongAnswersToReview = this.getWrongAnswersForReview(5)

        if (wrongAnswersToReview.length === 0) {
            ElMessage.info('暂无需要复习的错题')
            return []
        }

        // Create a review quiz message
        const title = '### 🔄 错题回顾\n根据你之前的错题，我们精选了一些题目帮助你巩固：'

        this.chatHistory.push({
            type: 'ai',
            content: {
                core_answer: title,
                answer: title,
                quiz_list: wrongAnswersToReview.map(w => ({
                    question: w.question,
                    options: w.options,
                    correct_index: w.correctIndex,
                    explanation: w.explanation,
                    node_id: w.nodeId,
                    isReview: true // Mark as review question
                }))
            }
        })

        return wrongAnswersToReview
    },

    // Get quiz statistics
    getQuizStats() {
        const totalQuizzes = this.quizHistory.length
        const totalQuestions = this.quizHistory.reduce((sum, h) => sum + h.totalQuestions, 0)
        const totalCorrect = this.quizHistory.reduce((sum, h) => sum + h.correctCount, 0)
        const accuracy = totalQuestions > 0 ? Math.round((totalCorrect / totalQuestions) * 100) : 0

        return {
            totalQuizzes,
            totalQuestions,
            totalCorrect,
            accuracy,
            wrongAnswerCount: this.wrongAnswers.length
        }
    },

    // --- Task Logic ---

    // --- Typewriter Effect Logic ---
    startTypingEffect() {
        if (this.typingInterval) return
        
        this.typingInterval = setInterval(() => {
            let hasWork = false
            
            this.typingBuffer.forEach((buffer, nodeId) => {
                if (buffer.length > 0) {
                    hasWork = true
                    // Take a small chunk (1-3 chars) to keep it fast but smooth
                    const speed = buffer.length > 50 ? 5 : (buffer.length > 20 ? 2 : 1)
                    const chunk = buffer.slice(0, speed)
                    
                    this.typingBuffer.set(nodeId, buffer.slice(speed))
                    
                    // Update node content
                    // Find node in nodes list (Current View Only)
                    // Typewriter only affects the VIEWED nodes
                    const node = this.nodes.find(n => n.node_id === nodeId)
                    if (node) {
                        node.node_content = (node.node_content || '') + chunk
                    }
                } else {
                    this.typingBuffer.delete(nodeId)
                }
            })
            
            // Auto-stop if no generating and no buffer
            if (!this.isGenerating && !hasWork) {
                if (this.typingInterval !== null) {
                    clearInterval(this.typingInterval)
                    this.typingInterval = null
                }
            }
        }, 30) // 30ms per update
    },

    addToBuffer(nodeId: string, content: string) {
        const current = this.typingBuffer.get(nodeId) || ''
        this.typingBuffer.set(nodeId, current + content)
        this.startTypingEffect()
    },

    stopGeneration() {
        // Stop current task
        if (this.currentCourseId) {
            this.pauseTask(this.currentCourseId)
        }
        this.isGenerating = false
        this.generationStatus = 'paused'
        this.typingBuffer.clear()
        if (this.typingInterval) {
            clearInterval(this.typingInterval)
            this.typingInterval = null
        }
        ElMessage.info('生成已暂停')
        this.persistGenerationState()
    },

    async startSmartGeneration(keyword: string, options: { difficulty?: string, style?: string, requirements?: string } = {}) {
        this.loading = true
        this.isGenerating = true
        this.generationStatus = 'generating'
        this.generationProgress = 0
        this.generationLogs = []
        this.addLog(`🚀 启动智能课程生成引擎: ${keyword}`)

        try {
            // Step 1: Generate Skeleton
            this.addLog(`🏗️ 正在构建课程大纲架构...`)
        const res = await http.post(`/generate_course`, { keyword, ...options })
            if (res.data && res.data.nodes) {
                const courseId = res.data.course_id
                const courseName = res.data.course_name
                
                // Initialize Task
                const task = this.createTask(courseId, courseName, res.data.nodes)
                task.status = 'running'
                
                this.currentCourseId = courseId
                this.nodes = res.data.nodes
                this.courseTree = this.buildTree(this.nodes)
                await this.fetchCourseList()
                this.addLog(`✅ 大纲架构构建完成，包含 ${this.nodes.length} 个节点`)
                this.persistGenerationState()
                
                // Link task nodes to UI nodes (by reference or copy?)
                // Actually, let's keep them separate but sync them.
                // Or better: UI uses this.nodes. Task uses task.nodes.
                // If viewing, we sync task.nodes updates to this.nodes?
                // Actually, simpler: generateFullDetails uses task.nodes.
                // If courseId == currentCourseId, we verify if we need to copy back.
                
                // Step 2: Auto-expand Details
                await this.generateFullDetails(courseId)
            }
        } catch (error) {
            this.addLog(`❌ 生成失败: ${error}`)
            ElMessage.error('生成失败')
            this.isGenerating = false
            this.generationStatus = 'error'
            this.persistGenerationState()
        } finally {
            this.loading = false
        }
    },

    async fetchCourseList() {
        this.loading = true
        try {
            const res = await http.get(`/courses`)
            this.courseList = res.data
        } catch (error) {
            console.error(error)
            this.courseList = []
        } finally {
            this.loading = false
        }
    },

    async loadCourse(courseId: string) {
        this.loading = true
        this.currentCourseId = courseId
        
        // Clear previous notes to ensure isolation
        this.notes = []
        
        // Load Annotations for the whole course
        this.fetchCourseAnnotations(courseId)
        
        // Check if there is an active task for this course
        const task = this.tasks.get(courseId)
        
        try {
            const res = await http.get(`/courses/${courseId}`)
            if (res.data && res.data.nodes) {
                this.nodes = res.data.nodes
                this.courseTree = this.buildTree(this.nodes)
                
                // If task exists, update its local nodes to match server state (which might be newer if we reloaded)
                // BUT, if task is running, its local nodes are the truth.
                // If task is running, we should trust the task?
                // Actually, if task is running, we shouldn't have reloaded the page.
                // If we switched courses and came back, the task might have updated backend.
                // If task is paused/idle, we can update task nodes.
                if (task && task.status !== 'running') {
                    task.nodes = JSON.parse(JSON.stringify(this.nodes))
                }
                
                // Sync UI state with task state
                if (task && task.status === 'running') {
                    this.isGenerating = true
                    this.generationProgress = task.progress
                    this.currentGeneratingNode = task.currentStep
                    this.generationLogs = task.logs
                } else {
                    this.isGenerating = false
                    this.generationProgress = task ? task.progress : 100
                    this.generationLogs = task ? task.logs : []
                }
            } else {
                throw new Error('课程数据为空')
            }
        } catch (error) {
            console.error(error)
            ElMessage.error('加载课程失败')
            this.currentCourseId = ''
            this.currentNode = null
            this.nodes = []
            this.courseTree = []
            this.isGenerating = false
            this.generationStatus = 'idle'
            this.generationProgress = 0
        } finally {
            this.loading = false
        }
    },

    async deleteCourse(courseId: string) {
        try {
            await http.delete(`/courses/${courseId}`)
            ElMessage.success('课程已删除')
            this.tasks.delete(courseId) // Remove task
            await this.fetchCourseList()
            if (this.currentCourseId === courseId) {
                this.nodes = []
                this.courseTree = []
                this.currentCourseId = ''
                this.currentNode = null
            }
            this.queue = this.queue.filter(item => item.courseId !== courseId)
            this.persistGenerationState()
        } catch (error) {
            ElMessage.error('删除失败')
        }
    },

    async fetchCourseTree() {
       await this.fetchCourseList()
       if (this.courseList.length > 0 && this.courseList[0]) {
           await this.loadCourse(this.courseList[0].course_id)
       }
    },
    
    buildTree(nodes: Node[]) {
      const nodeMap = new Map<string, Node>()
      const tree: Node[] = []
      
      // Use shallow copy to preserve object references for reactivity
      // We modify the SAME objects so that changes to this.nodes reflect in this.courseTree
      // This is intentional for Vue reactivity.
      
      const deepNodes = nodes // Direct reference

      deepNodes.forEach((node: Node) => {
        node.children = []
        nodeMap.set(node.node_id, node)
      })

      deepNodes.forEach((node: Node) => {
        if (node.parent_node_id === 'root') {
          tree.push(node)
        } else {
          const parent = nodeMap.get(node.parent_node_id)
          if (parent) {
            parent.children?.push(node)
          }
        }
      })
      
      return tree
    },

    addLog(msg: string) {
        // Add log to current task if exists
        if (this.currentCourseId) {
            const task = this.tasks.get(this.currentCourseId)
            if (task) {
                task.logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
            }
        }
        // Also update UI legacy state
        this.generationLogs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
    },
    
    addLogToTask(courseId: string, msg: string) {
        const task = this.tasks.get(courseId)
        if (task) {
            task.logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
        }
        if (this.currentCourseId === courseId) {
             this.generationLogs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
        }
    },

    async generateCourse(keyword: string, options: { difficulty?: string, style?: string, requirements?: string } = {}) {
      await this.startSmartGeneration(keyword, options)
    },

    getLinearNodes(nodes?: Node[]): Node[] {
      const targetNodes = nodes || this.courseTree
      let result: Node[] = []
      for (const node of targetNodes) {
        result.push(node)
        if (node.children && node.children.length > 0) {
          result.push(...this.getLinearNodes(node.children))
        }
      }
      return result
    },

    exportCourseJson() {
        const course = this.courseList.find(c => c.course_id === this.currentCourseId)
        const nodeIds = new Set(this.getLinearNodes(this.courseTree).map(n => n.node_id))
        const notes = this.notes.filter(n => nodeIds.has(n.nodeId) && n.sourceType !== 'format')
        if (!course && this.nodes.length === 0 && notes.length === 0) {
            ElMessage.warning('当前没有可导出的内容')
            return
        }
        const data = JSON.stringify({
            exportedAt: dayjs().format('YYYY-MM-DD HH:mm:ss'),
            course: course || null,
            nodes: this.nodes,
            courseTree: this.courseTree,
            notes
        }, null, 2)
        const filename = `${sanitizeFileName(course?.course_name || 'course')}_export_${dayjs().format('YYYYMMDD_HHmmss')}.json`
        downloadBlob(new Blob([data], { type: 'application/json' }), filename)
        ElMessage.success('导出成功')
    },

    exportCourseMarkdown() {
        const course = this.courseList.find(c => c.course_id === this.currentCourseId)
        const linearNodes = this.getLinearNodes(this.courseTree)
        const nodeIds = new Set(linearNodes.map(n => n.node_id))
        const notes = this.notes.filter(n => nodeIds.has(n.nodeId))
        if (!course && this.nodes.length === 0 && notes.length === 0) {
            ElMessage.warning('当前没有可导出的内容')
            return
        }
        const courseName = course?.course_name || 'My Course'
        let md = `# ${courseName}\n\n`
        md += `> 导出时间：${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
        md += `> 节点数：${this.nodes.length}\n\n`
        md += `> 笔记数：${notes.filter(n => n.sourceType !== 'format').length}\n\n---\n\n`
        const groupedNotes = new Map<string, Note[]>()
        const nodeOrder = new Map(linearNodes.map((n, i) => [n.node_id, i]))
        notes.sort((a, b) => {
            const orderA = nodeOrder.get(a.nodeId) ?? -1
            const orderB = nodeOrder.get(b.nodeId) ?? -1
            if (orderA !== orderB) return orderA - orderB
            return a.createdAt - b.createdAt
        })
        notes.forEach(note => {
            const nodeId = note.nodeId
            if (!groupedNotes.has(nodeId)) groupedNotes.set(nodeId, [])
            groupedNotes.get(nodeId)?.push(note)
        })
        linearNodes.forEach(node => {
            const level = Math.min(4, Math.max(1, Number(node.node_level || 1)))
            md += `${'#'.repeat(level)} ${node.node_name}\n\n`
            if (node.node_content) {
                md += `${node.node_content}\n\n`
            }
            const nodeNotes = groupedNotes.get(node.node_id)?.filter(n => n.sourceType !== 'format') || []
            if (nodeNotes.length > 0) {
                md += `**笔记**\n\n`
                nodeNotes.forEach(note => {
                    if (note.quote) {
                        md += `> ${note.quote}\n\n`
                    }
                    md += `${note.content}\n\n`
                    const typeLabel = note.sourceType === 'ai' ? 'AI 助手' : '笔记'
                    md += `> — *${typeLabel} · ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}*\n\n`
                })
                md += `---\n\n`
            }
        })
        const filename = `${sanitizeFileName(courseName)}_export_${dayjs().format('YYYYMMDD_HHmmss')}.md`
        downloadBlob(new Blob([md], { type: 'text/markdown' }), filename)
        ElMessage.success('导出成功')
    },

    exportNotesMarkdown(notes: Note[], options: { filterLabel: string, query?: string }) {
        if (!notes || notes.length === 0) {
            ElMessage.warning('当前没有可导出的笔记')
            return
        }
        const courseName = this.courseList.find(c => c.course_id === this.currentCourseId)?.course_name || 'My Notes'
        let md = `# ${courseName}\n\n`
        md += `> 导出时间：${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
        md += `> 类型：${options.filterLabel}\n\n`
        if (options.query) {
            md += `> 搜索：${options.query}\n\n`
        }
        md += `> 条目数：${notes.length}\n\n---\n\n`
        const linearNodes = this.getLinearNodes(this.courseTree)
        const nodeOrder = new Map(linearNodes.map((n, i) => [n.node_id, i]))
        const nodeNameMap = new Map(linearNodes.map(n => [n.node_id, n.node_name]))
        notes.sort((a, b) => {
            const orderA = nodeOrder.get(a.nodeId) ?? -1
            const orderB = nodeOrder.get(b.nodeId) ?? -1
            if (orderA !== orderB) return orderA - orderB
            return a.createdAt - b.createdAt
        })
        const groupedNotes = new Map<string, Note[]>()
        notes.forEach(note => {
            const nodeId = note.nodeId
            if (!groupedNotes.has(nodeId)) groupedNotes.set(nodeId, [])
            groupedNotes.get(nodeId)?.push(note)
        })
        groupedNotes.forEach((noteItems, nodeId) => {
            md += `## ${nodeNameMap.get(nodeId) || '未知章节'}\n\n`
            noteItems.forEach(note => {
                if (note.quote) {
                    md += `> ${note.quote}\n\n`
                }
                md += `${note.content}\n\n`
                const typeLabel = note.sourceType === 'ai' ? 'AI 助手' : '笔记'
                md += `> — *${typeLabel} · ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}*\n\n---\n\n`
            })
        })
        const filename = `${sanitizeFileName(courseName)}_${options.filterLabel}_${dayjs().format('YYYYMMDD_HHmmss')}.md`
        downloadBlob(new Blob([md], { type: 'text/markdown' }), filename)
        ElMessage.success('Markdown 导出成功')
    },

    // --- Queue System Actions ---
    
    addToQueue(item: Omit<QueueItem, 'uuid' | 'status'>) {
        const exists = this.queue.some(existing =>
            existing.courseId === item.courseId &&
            existing.type === item.type &&
            existing.targetNodeId === item.targetNodeId &&
            (existing.status === 'pending' || existing.status === 'running')
        )
        if (exists) {
            return
        }
        const newItem: QueueItem = {
            ...item,
            uuid: crypto.randomUUID(),
            status: 'pending'
        }
        this.queue.push(newItem)
        this.persistGenerationState()
        
        // Trigger processing
        this.processQueue()
    },

    async processQueue() {
        if (this.isQueueProcessing) return
        
        const nextItem = this.queue.find(i => i.status === 'pending')
        if (!nextItem) {
            this.isQueueProcessing = false
            this.finalizeIdleTasks()
            this.persistGenerationState()
            return
        }

        this.isQueueProcessing = true
        nextItem.status = 'running'
        this.persistGenerationState()
        
        const task = this.tasks.get(nextItem.courseId)
        
        try {
            if (task) {
                task.status = 'running'
                task.currentStep = nextItem.title
                
                if (this.currentCourseId === nextItem.courseId) {
                    this.currentGeneratingNodeId = nextItem.targetNodeId
                    this.isGenerating = true
                    this.generationStatus = 'generating'
                }
            }

            if (nextItem.type === 'structure') {
                await this.processStructureItem(nextItem)
            } else if (nextItem.type === 'content') {
                await this.processContentItem(nextItem)
            } else if (nextItem.type === 'subchapter') {
                await this.processSubchapterItem(nextItem)
            }

            nextItem.status = 'completed'
            if (task) {
                task.logs.push(`✅ 完成: ${nextItem.title}`)
                // Update progress based on queue stats?
                // For now, simple progress
                const total = this.queue.length
                const completed = this.queue.filter(i => i.status === 'completed').length
                task.progress = Math.floor((completed / total) * 100)
            }
            this.persistGenerationState()

        } catch (e: any) {
            const errorMessage = e instanceof Error ? e.message : String(e)
            nextItem.status = 'error'
            nextItem.errorMsg = errorMessage
            if (task) task.logs.push(`❌ 失败: ${nextItem.title} - ${errorMessage}`)
            this.persistGenerationState()
        } finally {
            if (task && task.shouldStop) {
                this.isQueueProcessing = false
                task.status = 'paused'
            } else {
                this.isQueueProcessing = false
                setTimeout(() => this.processQueue(), 50)
            }
            this.persistGenerationState()
        }
    },

    async processStructureItem(item: QueueItem) {
        const task = this.tasks.get(item.courseId)
        if (!task) throw new Error('Task not found')
        
        const node = task.nodes.find(n => n.node_id === item.targetNodeId)
        if (!node) throw new Error('Node not found')
        
        this.addLogToTask(item.courseId, `📂 正在构建: ${node.node_name}...`)
        
        const res = await http.post(`/courses/${item.courseId}/nodes/${node.node_id}/subnodes`, {
            node_id: node.node_id,
            node_name: node.node_name,
            node_level: node.node_level
        })
        
        const newNodes = res.data
        if (Array.isArray(newNodes)) {
            task.nodes.push(...newNodes)
            
            // Auto-queue content generation for new nodes
            for (const newNode of newNodes) {
                this.addToQueue({
                    courseId: item.courseId,
                    type: 'content',
                    targetNodeId: newNode.node_id,
                    title: `撰写正文: ${newNode.node_name}`
                })
            }

            if (this.currentCourseId === item.courseId) {
                this.nodes = [...task.nodes]
                this.courseTree = this.buildTree(this.nodes)
            }
        }
    },

    async processContentItem(item: QueueItem) {
        const task = this.tasks.get(item.courseId)
        if (!task) throw new Error('Task not found')
        
        const node = task.nodes.find(n => n.node_id === item.targetNodeId)
        if (!node) throw new Error('Node not found')
        
        this.addLogToTask(item.courseId, `📝 正在撰写: ${node.node_name}...`)
        
        const courseContext = task.nodes
            .filter(n => n.node_level <= 2)
            .map(n => `${'  '.repeat(n.node_level-1)}- ${n.node_name}`)
            .join('\n')
            
        // Find previous node content for context
        // Simple approach: find index
        const index = task.nodes.findIndex(n => n.node_id === node.node_id)
        let previousContext = "相关上下文..."
        if (index > 0) {
            const prev = task.nodes[index - 1]
            if (prev && prev.node_content) {
                previousContext = `上节 (${prev.node_name}) 回顾: ` + prev.node_content.slice(-300)
            }
        }

        node.node_content = ''
        node.node_type = 'custom'
        
        const response = await fetch(`${API_BASE}/courses/${item.courseId}/nodes/${node.node_id}/redefine_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                node_id: node.node_id,
                node_name: node.node_name,
                original_content: '',
                user_requirement: '详细正文',
                course_context: courseContext,
                previous_context: previousContext
            })
        })

        const reader = response.body?.getReader()
        if (reader) {
            const decoder = new TextDecoder()
            while (true) {
                if (task.shouldStop) {
                    reader.cancel()
                    break
                }
                const { done, value } = await reader.read()
                if (done) break
                const chunk = decoder.decode(value, { stream: true })
                
                if (this.currentCourseId === item.courseId) {
                    this.addToBuffer(node.node_id, chunk)
                } else {
                    node.node_content = (node.node_content || '') + chunk
                }
            }
        }
    },

    async processSubchapterItem(item: QueueItem) {
        const task = this.tasks.get(item.courseId)
        if (!task) throw new Error('Task not found')
        
        const node = task.nodes.find(n => n.node_id === item.targetNodeId)
        if (!node) throw new Error('Node not found')
        
        // Check for headers in content
        const content = node.node_content || ''
        const headers: string[] = []
        const regex = /^(#{1,6})\s+(.*)$/gm
        let match
        while ((match = regex.exec(content)) !== null) {
            if (match[2]) {
                headers.push(match[2].trim())
            }
        }

        if (headers.length > 0) {
            this.addLogToTask(item.courseId, `🔍 提取到 ${headers.length} 个标题，正在生成...`)
            for (const title of headers) {
                try {
                    // Try to create node manually
                    // Assumption: POST /nodes creates a node
                    const res = await http.post(`/courses/${item.courseId}/nodes`, {
                        parent_node_id: node.node_id,
                        node_name: title,
                        node_level: node.node_level + 1,
                        node_content: ''
                    })
                    task.nodes.push(res.data)
                    // Queue content generation for it?
                    this.addToQueue({
                        courseId: item.courseId,
                        type: 'content',
                        targetNodeId: res.data.node_id,
                        title: `撰写正文: ${res.data.node_name}`
                    })
                } catch (e) {
                    console.error('Manual create failed, trying fallback', e)
                }
            }
        } else {
            this.addLogToTask(item.courseId, `🤖 智能生成子章节...`)
            const res = await http.post(`/courses/${item.courseId}/nodes/${node.node_id}/subnodes`, {
                node_id: node.node_id,
                node_name: node.node_name,
                node_level: node.node_level
            })
            const newNodes = res.data
            task.nodes.push(...newNodes)
            for (const newNode of newNodes) {
                this.addToQueue({
                    courseId: item.courseId,
                    type: 'content',
                    targetNodeId: newNode.node_id,
                    title: `撰写正文: ${newNode.node_name}`
                })
            }
        }
        
        if (this.currentCourseId === item.courseId) {
            this.nodes = [...task.nodes]
            this.courseTree = this.buildTree(this.nodes)
        }
    },

    async generateSubChapters(node: Node) {
        if (!this.currentCourseId) return
        this.addToQueue({
            courseId: this.currentCourseId,
            type: 'subchapter',
            targetNodeId: node.node_id,
            title: `生成子章节: ${node.node_name}`
        })
    },

    async generateFullDetails(courseId?: string) {
      const targetCourseId = courseId || this.currentCourseId
      if (!targetCourseId) return
      
      const task = this.tasks.get(targetCourseId)
      if (!task) return
      
      task.status = 'running'
      task.shouldStop = false
      if (targetCourseId === this.currentCourseId) {
          this.generationStatus = 'generating'
      }

      // Populate Queue
      const l2Nodes = task.nodes.filter(n => n.node_level === 2)
      for (const n of l2Nodes) {
          const hasChildren = task.nodes.some(child => child.parent_node_id === n.node_id)
          if (!hasChildren) {
              this.addToQueue({
                  courseId: targetCourseId,
                  type: 'structure',
                  targetNodeId: n.node_id,
                  title: `构建章节: ${n.node_name}`
              })
          }
      }
      
      const l3Nodes = task.nodes.filter(n => n.node_level === 3 && (!n.node_content || n.node_content.length < 50))
      for (const n of l3Nodes) {
          this.addToQueue({
              courseId: targetCourseId,
              type: 'content',
              targetNodeId: n.node_id,
              title: `撰写正文: ${n.node_name}`
          })
      }
    },

    // --- Single Node Generation (Chapter Level Control) ---
    async generateNodeContent(nodeId: string) {
        if (!this.currentCourseId) return
        
        const node = this.nodes.find(n => n.node_id === nodeId)
        if (!node) return

        this.isGenerating = true
        this.currentGeneratingNode = `正在生成: ${node.node_name}`
        this.currentGeneratingNodeId = nodeId
        this.addLog(`🚀 开始生成章节: ${node.node_name}`)
        
        // Clear existing content
        node.node_content = ''
        node.node_type = 'custom'

        try {
            // Context
            const courseContext = this.nodes
                .filter(n => n.node_level <= 2)
                .map(n => `${'  '.repeat(n.node_level-1)}- ${n.node_name}`)
                .join('\n')
            
            // Find previous node for context (simple linear search in current tree)
            const linear = this.getLinearNodes(this.courseTree)
            const idx = linear.findIndex(n => n.node_id === nodeId)
            let previousContext = "相关背景..."
            if (idx > 0) {
                const prev = linear[idx - 1]
                if (prev && prev.node_content) {
                    previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500)
                }
            }

            const response = await fetch(`${API_BASE}/courses/${this.currentCourseId}/nodes/${nodeId}/redefine_stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                   node_id: node.node_id,
                   node_name: node.node_name,
                   original_content: node.node_content || '',
                   user_requirement: '教科书级详细正文',
                   course_context: courseContext,
                   previous_context: previousContext
                })
            })

            const reader = response.body?.getReader()
            
            if (reader) {
                const decoder = new TextDecoder()
                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    const chunk = decoder.decode(value, { stream: true })
                    
                    this.addToBuffer(node.node_id, chunk)
                }
            }
            
            this.addLog(`✅ 章节生成完成: ${node.node_name}`)
            ElMessage.success('章节生成完成')

        } catch (e) {
            this.addLog(`❌ 生成失败: ${e}`)
            ElMessage.error('生成失败')
        } finally {
            this.isGenerating = false
            this.currentGeneratingNode = null
            this.currentGeneratingNodeId = null
        }
    },

    selectNode(node: Node) {
        this.currentNode = node
        // fetchAnnotations is deprecated and handled by loadCourse (fetchCourseAnnotations)
    },

    setCurrentNodeSilent(node: Node) {
        this.currentNode = node
    },

    setCurrentNode(nodeId: string) {
        const node = this.courseTree.find(n => n.node_id === nodeId)
        if (node) {
            this.currentNode = node
        }
    },
    
    // markNodeAsVisited removed as per request

    async fetchAnnotations(nodeId: string) {
      // Deprecated: We now load all annotations for the course at once
      // But we can keep it for specific refresh if needed
      try {
        const res = await axios.get(`${API_BASE}/nodes/${nodeId}/annotations`)
        // Merge into main list (deduplicate)
        const newAnnos = res.data as Annotation[]
        const existingIds = new Set(this.annotations.map(a => a.anno_id))
        newAnnos.forEach(a => {
            if (!existingIds.has(a.anno_id)) {
                this.annotations.push(a)
            }
        })
      } catch (error) {
        console.error(error)
      }
    },

    async fetchCourseAnnotations(courseId: string) {
        try {
            const res = await axios.get(`${API_BASE}/courses/${courseId}/annotations`)
            this.annotations = res.data
            
            // Unify: Convert legacy annotations to Notes
            const annotations = res.data as Annotation[]
            annotations.forEach(anno => {
                // Avoid duplicates based on ID
                if (!this.notes.find(n => n.id === anno.anno_id)) {
                    this.notes.push({
                        id: anno.anno_id,
                        nodeId: anno.node_id,
                        highlightId: `hl-${anno.anno_id}`, // Synthetic highlight ID
                        quote: anno.quote || '',
                        content: anno.answer || anno.question || '',
                        summary: anno.anno_summary || '',
                        color: 'amber',
                        createdAt: Date.now(),
                        sourceType: (anno.source_type as any) || 'user',
                    })
                }
            })
        } catch (error) {
            console.error("Failed to load annotations", error)
        }
    },

    async saveAnnotation(anno: Partial<Annotation>) {
        // Prevent duplicates locally first
        if (anno.anno_id && this.annotations.find(a => a.anno_id === anno.anno_id)) {
             ElMessage.warning('该笔记已存在')
             return
        }

        const newAnno: Annotation = {
            anno_id: anno.anno_id || `anno_${crypto.randomUUID()}`,
            node_id: anno.node_id!,
            question: anno.question || 'User Note',
            answer: anno.answer || '',
            anno_summary: anno.anno_summary || 'Note',
            source_type: anno.source_type || 'user_saved',
            quote: anno.quote
        }
            
        try {
            // Save to backend
                await http.post(`/annotations`, newAnno)
                
                this.annotations.push(newAnno)
                
                // Suppress toast for pure formatting actions (highlight, bold, etc)
                if (anno.source_type !== 'format') {
                    ElMessage.success('笔记已保存')
                }
                
                // Also update active annotation to highlight immediately
                this.activeAnnotation = newAnno
            } catch (e) {
                ElMessage.error('保存失败')
                console.error(e)
            }
    },

    async deleteAnnotation(annoId: string) {
        try {
            await http.delete(`/annotations/${annoId}`)
            this.annotations = this.annotations.filter(a => a.anno_id !== annoId)
            ElMessage.success('笔记已删除')
            if (this.activeAnnotation?.anno_id === annoId) {
                this.activeAnnotation = null
            }
        } catch (e) {
            ElMessage.error('删除失败')
        }
    },

    async askQuestion(question: string, selection: string = "", targetNodeId?: string) {
      let controller: AbortController | null = null
      let aiMessage: ChatMessage | null = null
      // Fallback to the first node (Course Root) if no node is explicitly selected
      let targetNode = this.currentNode
      
      // If a specific target node is requested (e.g. from selection), use it
      if (targetNodeId) {
          const found = this.nodes.find(n => n.node_id === targetNodeId)
          if (found) targetNode = found
      }
      
      if (!targetNode && this.nodes.length > 0) {
          targetNode = this.nodes[0] || null
      }

      if (!targetNode) {
          ElMessage.warning('请先选择一个课程或章节')
          return
      }
      
      this.loading = true
      this.chatLoading = true
      try {
        if (this.chatAbortController) {
            this.chatAbortController.abort()
        }
        controller = new AbortController()
        this.chatAbortController = controller
        // Construct full course context for Q&A
        const linearNodes = this.getLinearNodes(this.courseTree)
        
        // --- Context Optimization Start ---
        // 1. Structure (Lightweight Outline)
        const structureContext = linearNodes
            .map(n => `${'  '.repeat(n.node_level - 1)}- ${n.node_name} (ID: ${n.node_id})`)
            .join('\n')

        // 2. Target Node Content (The one user is likely reading)
        let focusContext = ""
        if (targetNode) {
            focusContext = `\n\n### 当前选中/阅读章节 (重点关注)\n章节名：${targetNode.node_name}\nID：${targetNode.node_id}\n内容：\n${targetNode.node_content || '(暂无内容)'}`
        }

        // 3. Keyword Match Context (Simple Client-side RAG)
        // Find other nodes whose names appear in the question (e.g. user asks about "Chapter 2")
        const relevantNodes = linearNodes.filter(n => 
            n.node_id !== targetNode?.node_id && // Exclude already added
            n.node_content && // Must have content
            question.includes(n.node_name) // Name matches question
        )

        let retrievalContext = ""
        if (relevantNodes.length > 0) {
            retrievalContext = "\n\n### 相关章节内容（根据问题自动提取）\n" + relevantNodes.map(n => 
                `章节：${n.node_name} (ID: ${n.node_id})\n内容：\n${n.node_content?.slice(0, 3000)}...` // Limit per node to avoid overflow
            ).join('\n\n')
        }

        // Combine
        const fullContext = `### 课程完整大纲结构\n${structureContext}${focusContext}${retrievalContext}`
        // --- Context Optimization End ---

        // Construct history
        const history = this.chatHistory.map(msg => ({
            role: msg.type === 'user' ? 'user' : 'assistant',
            content: typeof msg.content === 'string' ? msg.content : (msg.content.core_answer || '')
        }))

        // Create a placeholder message for AI
        
        // Prepare user notes context (Learning Footprint)
        const userNotes = this.notes
            .map(n => `- [${n.sourceType === 'ai' ? 'AI' : 'User'}] ${n.content} (Related to Node: ${n.nodeId})`)
            .join('\n')
            .slice(0, 5000) // Limit to 5000 chars to avoid token overflow

        const aiMessageContent: AIContent = {
            core_answer: '',
            detail_answer: [],
            quote: '',
            anno_summary: 'AI 思考中...',
            anno_id: `anno_${crypto.randomUUID()}`,
            node_id: '',
            question: question,
            answer: ''
        }
        
        const aiMessageRaw: ChatMessage = {
          type: 'ai',
          content: aiMessageContent
        }
        
        this.chatHistory.push(aiMessageRaw)
        // Get the reactive proxy from the array so updates trigger UI changes
        aiMessage = this.chatHistory[this.chatHistory.length - 1] as ChatMessage
        if (typeof aiMessage.content === 'string') return // Should not happen

        // Fetch Stream
        const response = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                node_id: targetNode.node_id,
                node_name: targetNode.node_name,
                node_content: fullContext,
                question,
                history,
                selection,
                user_notes: userNotes,
                user_persona: this.userPersona
            }),
            signal: controller.signal
        })
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error("No reader")

        const decoder = new TextDecoder()
        let fullText = ""
        let isCollectingMetadata = false
        
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            
            const chunk = decoder.decode(value, { stream: true })
            fullText += chunk
            
            // Check for Metadata split
            if (!isCollectingMetadata) {
                const splitIdx = fullText.indexOf('---METADATA---')
                if (splitIdx !== -1) {
                    // Split content
                    const answerPart = fullText.substring(0, splitIdx)
                    aiMessage.content.core_answer = answerPart
                    aiMessage.content.answer = answerPart // Backward compat
                    
                    // The rest is metadata
                    isCollectingMetadata = true
                    // We don't stream metadata to UI text, we parse it at the end usually
                    // But if we want to be safe, we can try to parse if it looks complete?
                    // Usually metadata comes in one go at the end.
                } else {
                    // Still just answer
                    aiMessage.content.core_answer = fullText
                    aiMessage.content.answer = fullText
                }
            }
        }
        
        // Final Parse
        const splitIdx = fullText.indexOf('---METADATA---')
        if (splitIdx !== -1) {
            const answerPart = fullText.substring(0, splitIdx)
            const metadataPart = fullText.substring(splitIdx + 14).trim()
            
            aiMessage.content.core_answer = answerPart.trim()
            aiMessage.content.answer = answerPart.trim()
            
            try {
                const metadata = JSON.parse(metadataPart)
                if (metadata) {
                    aiMessage.content.node_id = metadata.node_id
                    aiMessage.content.quote = metadata.quote
                    aiMessage.content.anno_summary = metadata.anno_summary || 'AI 笔记'
                    
                    // Auto-save annotation if quote exists? No, let user decide.
                    // Actually, if we want to unify, we can save it as a Note automatically?
                    // The user requested "AI 助手生成的笔记自动保存到 Notes 列表"
                    const quoteText = (metadata.quote || '').trim()
                    const answerText = (aiMessage.content.core_answer || aiMessage.content.answer || '').trim()
                    const summaryText = (metadata.anno_summary || '').trim()
                    const noteContentRaw = summaryText && summaryText !== 'AI 笔记' ? summaryText : answerText
                    const noteContent = noteContentRaw.replace(/\s+/g, ' ').trim()
                    if (quoteText && quoteText.length >= 3 && noteContent.length >= 8) {
                        const noteId = `note-${Date.now()}`
                        const resolvedNodeId = metadata.node_id || aiMessage.content.node_id || this.currentNode?.node_id || ''
                        const shortSummary = summaryText && summaryText !== 'AI 笔记'
                            ? summaryText
                            : (answerText.length > 50 ? `${answerText.slice(0, 50)}...` : answerText)
                        
                        this.activeAnnotation = {
                            anno_id: noteId,
                            node_id: resolvedNodeId,
                            question: 'AI 笔记',
                            answer: answerText,
                            anno_summary: shortSummary || 'AI 笔记',
                            source_type: 'ai_chat',
                            quote: quoteText
                        }
                        
                        // Auto-convert to Note
                        const highlightId = `highlight-${Date.now()}`
                        this.createNote({
                            id: noteId,
                            nodeId: resolvedNodeId,
                            highlightId: highlightId,
                            quote: quoteText,
                            content: answerText,
                            summary: shortSummary,
                            color: 'purple',
                            createdAt: Date.now(),
                            sourceType: 'ai'
                        })

                        // Update message with noteId for UI actions
                        aiMessage.content.anno_id = noteId

                        // Teacher Behavior: Auto-scroll to the location (Turn the page & Highlight)
                        if (metadata.node_id) {
                            // Expand the node if needed (ensure visibility)
                            this.scrollToNode(metadata.node_id)
                            
                            // Scroll to the specific highlight (Note)
                            // We use a small timeout to allow the DOM to update with the new highlight
                            setTimeout(() => {
                                this.focusNoteId = null
                                setTimeout(() => {
                                    this.focusNoteId = noteId
                                }, 50)
                            }, 100)
                        }
                    }
                }
            } catch (e) {
                console.warn("Failed to parse metadata", e)
            }
        } else {
             aiMessage.content.core_answer = fullText
             aiMessage.content.answer = fullText
        }
        
      } catch (error: any) {
        if (controller?.signal.aborted || error?.name === 'AbortError') {
            if (aiMessage && typeof aiMessage.content !== 'string') {
                aiMessage.content.core_answer = '已停止生成'
                aiMessage.content.answer = '已停止生成'
                aiMessage.content.anno_summary = '已停止生成'
            }
            return
        }
        console.error(error)
        ElMessage.error('提问失败')
        if (aiMessage && typeof aiMessage.content !== 'string') {
            aiMessage.content.core_answer = '生成失败，请稍后重试。'
            aiMessage.content.answer = '生成失败，请稍后重试。'
            aiMessage.content.anno_summary = '生成失败'
        }
        // Remove the failed placeholder or mark error?
        // this.chatHistory.pop() 
      } finally {
        this.loading = false
        this.chatLoading = false
        if (this.chatAbortController === controller) {
            this.chatAbortController = null
        }
      }
    },

    async generateSubNodes(node: Node) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/courses/${this.currentCourseId}/nodes/${node.node_id}/subnodes`, {
                node_id: node.node_id,
                node_name: node.node_name,
                node_level: node.node_level
            })
            const newNodes = res.data
            this.nodes.push(...newNodes)
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('子章节生成成功')
        } catch (error) {
            ElMessage.error('生成失败')
        } finally {
            this.loading = false
        }
    },

    async summarizeChat() {
        if (this.chatHistory.length === 0) {
            ElMessage.warning('没有可总结的对话')
            return null
        }
        
        this.chatLoading = true
        try {
            // Construct lightweight context
            const history = this.chatHistory.map(msg => ({
                role: msg.type === 'user' ? 'user' : 'assistant',
                content: typeof msg.content === 'string' ? msg.content : (msg.content.core_answer || '')
            }))
            
            const context = this.currentNode ? `当前章节：${this.currentNode.node_name}` : '全书概览'
            
            const res = await axios.post(`${API_BASE}/summarize_chat`, {
                history,
                course_context: context,
                user_persona: this.userPersona
            })
            
            return res.data
        } catch (e) {
            console.error(e)
            ElMessage.error('总结生成失败')
            return null
        } finally {
            this.chatLoading = false
        }
    },

    async generateQuizFromSummary(summaryContent: string) {
        if (!this.currentNode) return
        
        const prompt = `基于以下复盘内容生成测验：\n${summaryContent.slice(0, 2000)}`
        
        // Use existing addMessage to simulate user request, but clearer
        this.addMessage('user', '请根据刚才的复盘内容，帮我出几道题巩固一下。')
        
        await this.askQuestion(prompt)
    },

    async redefineContent(node: Node, requirement: string) {
        if (!this.currentCourseId) return
        this.loading = true
        
        // Prepare context
        const courseContext = this.nodes
            .filter(n => n.node_level <= 2)
            .map(n => `${'  '.repeat(n.node_level-1)}- ${n.node_name}`)
            .join('\n')
            
        let previousContext = ""
        const linearNodes = this.getLinearNodes(this.courseTree)
        const idx = linearNodes.findIndex(n => n.node_id === node.node_id)
        if (idx > 0) {
            const prev = linearNodes[idx - 1]
            if (prev && prev.node_content) {
                previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500)
            }
        }

        try {
            node.node_content = '' 
            node.node_type = 'custom'
            
            const response = await fetch(`${API_BASE}/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    node_id: node.node_id,
                    node_name: node.node_name,
                    original_content: node.node_content,
                    user_requirement: requirement,
                    course_context: courseContext,
                    previous_context: previousContext
                })
            })

            const reader = response.body?.getReader()
            
            if (reader) {
                const decoder = new TextDecoder()
                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    const chunk = decoder.decode(value, { stream: true })
                    this.addToBuffer(node.node_id, chunk)
                }
            }
            ElMessage.success('内容重写成功')
        } catch (error) {
            ElMessage.error('重写失败')
        } finally {
            this.loading = false
        }
    },

    async generateBody(node: Node) {
        if (!this.currentCourseId) return
        this.loading = true
        
        // Use existing content as Intro context
        const intro = node.node_content || ''
        
        // Prepare context
        const courseContext = this.nodes
            .filter(n => n.node_level <= 2)
            .map(n => `${'  '.repeat(n.node_level-1)}- ${n.node_name}`)
            .join('\n')
            
        let previousContext = ""
        const linearNodes = this.getLinearNodes(this.courseTree)
        const idx = linearNodes.findIndex(n => n.node_id === node.node_id)
        if (idx > 0) {
            const prev = linearNodes[idx - 1]
            if (prev && prev.node_content) {
                previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500)
            }
        }
        
        // Add Intro to context
        previousContext += `\n本节简介: ${intro}`

        try {
            // Append delimiter if not present
            if (!node.node_content?.includes('<!-- BODY_START -->')) {
                 node.node_content = (node.node_content || '') + '\n\n<!-- BODY_START -->\n\n'
            }
            
            const response = await fetch(`${API_BASE}/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    node_id: node.node_id,
                    node_name: node.node_name,
                    original_content: '', // We want new content
                    user_requirement: '基于简介撰写教科书级详细正文，不要重复简介内容',
                    course_context: courseContext,
                    previous_context: previousContext
                })
            })

            const reader = response.body?.getReader()
            
            if (reader) {
                const decoder = new TextDecoder()
                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    const chunk = decoder.decode(value, { stream: true })
                    
                    this.addToBuffer(node.node_id, chunk)
                }
            }
            
            ElMessage.success('正文生成完成')
        } catch (error) {
            ElMessage.error('生成失败')
            console.error(error)
        } finally {
            this.loading = false
        }
    },

    async extendContent(node: Node, requirement: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/courses/${this.currentCourseId}/nodes/${node.node_id}/extend`, {
                node_id: node.node_id,
                node_name: node.node_name,
                current_content: node.node_content,
                user_requirement: requirement
            })
            node.node_content += `\n\n${res.data.node_content}`
            ElMessage.success('内容扩展成功')
        } catch (error) {
            ElMessage.error('扩展失败')
        } finally {
            this.loading = false
        }
    },

    async locateNode(keyword: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await axios.post(`${API_BASE}/courses/${this.currentCourseId}/locate`, { keyword })
            if (res.data.target_node_id) {
                const target = this.nodes.find(n => n.node_id === res.data.target_node_id)
                if (target) {
                    this.currentNode = target
                    ElMessage.success(`已定位到: ${target.node_name}`)
                }
            } else {
                ElMessage.warning('未找到相关节点')
            }
        } catch (error) {
            ElMessage.error('定位失败')
        } finally {
            this.loading = false
        }
    },

    async addCustomNode(parentId: string, name: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/courses/${this.currentCourseId}/nodes`, {
                parent_node_id: parentId,
                node_name: name
            })
            this.nodes.push(res.data)
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('添加成功')
        } catch (error) {
            ElMessage.error('添加失败')
        } finally {
            this.loading = false
        }
    },

    async deleteNode(nodeId: string) {
        if (!this.currentCourseId) return
        try {
            await http.delete(`/courses/${this.currentCourseId}/nodes/${nodeId}`)
            const toDelete = new Set<string>([nodeId])
            let changed = true
            while(changed) {
                changed = false
                this.nodes.forEach(n => {
                    if (toDelete.has(n.parent_node_id) && !toDelete.has(n.node_id)) {
                        toDelete.add(n.node_id)
                        changed = true
                    }
                })
            }
            this.nodes = this.nodes.filter(n => !toDelete.has(n.node_id))
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('删除成功')
        } catch (error) {
            ElMessage.error('删除失败')
        }
    },

    async renameNode(nodeId: string, newName: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            await http.put(`/courses/${this.currentCourseId}/nodes/${nodeId}`, {
                node_name: newName
            })
            const node = this.nodes.find(n => n.node_id === nodeId)
            if (node) {
                node.node_name = newName
            }
            ElMessage.success('重命名成功')
        } catch (error) {
            ElMessage.error('重命名失败')
        } finally {
            this.loading = false
        }
    },

    // Removed duplicate saveAnnotation
  }
})
