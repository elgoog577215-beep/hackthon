import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import {
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  type DifficultyLevel,
  type TeachingStyle
} from '@/shared/prompt-config'
import { useNoteStore } from './notes'
import { useGenerationStore } from './generation'
import { useLearningStore } from './learning'
import { useReviewStore } from './review'
import logger from '../utils/logger'

// =============================================================================
// Course Store - 核心课程状态管理
// =============================================================================
//
// 架构说明：
// 本模块管理课程核心状态和与课程深度耦合的功能（聊天、测验、导出）。
// 已拆分到独立 Store 的功能域：
//   - generation.ts  → 生成队列、任务管理
//   - notes.ts       → 笔记 CRUD、标签、导出
//   - learning.ts    → 学习统计、学习路径、知识掌握度
//   - review.ts      → 错题记录、测验历史
//   - chat.ts        → 聊天基础状态（备用）
// =============================================================================

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_').trim()
const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
}

// --- 类型重新导出（向后兼容） ---
export type { Node, Annotation, Note, Course, QueueItem, AIContent, ChatMessage, ChatConversation } from './types'
import type { Node, Annotation, Note, Course, QueueItem, Task, AIContent, ChatMessage, ChatConversation } from './types'

export const useCourseStore = defineStore('course', {
  state: () => ({
    // --- 核心课程状态 ---
    courseList: [] as Course[],
    currentCourseId: '' as string,
    courseTree: [] as Node[],
    nodes: [] as Node[],
    currentNode: null as Node | null,
    loading: false,

    // --- Annotations（fetchCourseAnnotations 桥接 Notes 系统） ---
    annotations: [] as Annotation[],

    // --- 聊天状态（组件深度依赖 courseStore.chatHistory） ---
    chatHistory: [] as ChatMessage[],
    chatLoading: false,
    chatAbortController: null as AbortController | null,
    activeAnnotation: null as Annotation | null,

    // --- UI State ---
    isFocusMode: false,
    showKnowledgeGraph: false,
    isMobileNotesVisible: false,
    globalSearchQuery: '',
    scrollToNodeId: null as string | null,
    focusNoteId: null as string | null,
    userPersona: localStorage.getItem('user_persona') || '',

    // --- 多对话管理 ---
    conversations: JSON.parse(localStorage.getItem('chat_conversations') || '[]') as ChatConversation[],
    currentConversationId: localStorage.getItem('chat_current_conversation') || '' as string,
    uiSettings: {
        fontSize: 17,
        fontFamily: 'sans' as 'sans' | 'serif' | 'mono',
        lineHeight: 1.75
    },
  }),
  getters: {
    treeData: (state) => state.courseTree,
    getNotesByNodeId() {
      
      const noteStore = useNoteStore()
      return (nodeId: string) => noteStore.notes.filter((n: Note) => n.nodeId === nodeId)
    },
    currentCourse: (state) => state.courseList.find(c => c.course_id === state.currentCourseId),
  },
  actions: {
    // ========== UI Actions ==========
    setUiSettings(settings: Partial<{ fontSize: number; fontFamily: 'sans' | 'serif' | 'mono'; lineHeight: number }>) {
        this.uiSettings = { ...this.uiSettings, ...settings }
    },
    toggleFocusMode() { this.isFocusMode = !this.isFocusMode },
    updateUserPersona(persona: string) {
        this.userPersona = persona
        localStorage.setItem('user_persona', persona)
    },
    scrollToNode(nodeId: string) {
        this.scrollToNodeId = null
        setTimeout(() => { this.scrollToNodeId = nodeId }, 10)
    },
    scrollToNote(noteId: string) {
        this.focusNoteId = null
        setTimeout(() => { this.focusNoteId = noteId }, 10)
    },
    selectNode(node: Node) { this.currentNode = node },
    setCurrentNodeSilent(node: Node) { this.currentNode = node },
    setCurrentNode(nodeId: string) {
        const node = this.courseTree.find(n => n.node_id === nodeId)
        if (node) { this.currentNode = node }
    },
    addMessage(type: 'user' | 'ai', content: string | AIContent) {
        this.chatHistory.push({ type, content })
    },
    cancelChat() {
        if (this.chatAbortController) { this.chatAbortController.abort() }
    },
    clearChat() {
        this.chatHistory = []
        this.activeAnnotation = null
    },

    // ========== Conversation Management ==========
    initConversations() {
        if (this.conversations.length === 0) {
            this.createConversation()
        }
        if (!this.currentConversationId && this.conversations.length > 0) {
            this.currentConversationId = this.conversations[0]!.id
        }
        this.syncCurrentConversation()
    },
    createConversation() {
        this.syncCurrentConversation()
        const conv: ChatConversation = {
            id: `conv-${Date.now()}`,
            name: `对话 ${this.conversations.length + 1}`,
            messages: [],
            createdAt: Date.now(),
        }
        this.conversations.unshift(conv)
        this.currentConversationId = conv.id
        this.chatHistory = []
        this.activeAnnotation = null
        this.saveConversations()
    },
    switchConversation(id: string) {
        this.syncCurrentConversation()
        this.currentConversationId = id
        const conv = this.conversations.find(c => c.id === id)
        this.chatHistory = conv ? [...conv.messages] : []
        this.activeAnnotation = null
        this.saveConversations()
    },
    syncCurrentConversation() {
        const conv = this.conversations.find(c => c.id === this.currentConversationId)
        if (conv) {
            conv.messages = [...this.chatHistory]
        }
    },
    renameConversation(id: string, name: string) {
        const conv = this.conversations.find(c => c.id === id)
        if (conv) { conv.name = name }
        this.saveConversations()
    },
    deleteConversation(id: string) {
        this.conversations = this.conversations.filter(c => c.id !== id)
        if (this.currentConversationId === id) {
            const first = this.conversations[0]
            if (first) {
                this.currentConversationId = first.id
                this.chatHistory = [...first.messages]
            } else {
                this.createConversation()
            }
        }
        this.saveConversations()
    },
    saveConversations() {
        try {
            localStorage.setItem('chat_conversations', JSON.stringify(this.conversations))
            localStorage.setItem('chat_current_conversation', this.currentConversationId)
        } catch (e) {
            logger.error('Failed to save conversations:', e)
        }
    },

    // ========== Delegation helpers ==========
    _genStore() {
        
        return useGenerationStore()
    },
    _noteStore() {
        
        return useNoteStore()
    },

    // ========== Backward-compat delegations to generation store ==========
    restoreGenerationState() { return this._genStore().restoreGenerationState() },

    // ========== Backward-compat delegations to note store ==========
    addNote(note: Note) { this._noteStore().addNote(note) },
    get notes(): Note[] { return this._noteStore().notes },

    // ========== Course CRUD ==========
    async createCourse(courseName: string) {
        try {
            const res = await http.post('/api/generate_course', { keyword: courseName })
            if (res.data) {
                await this.fetchCourseList()
                return res.data.course_id
            }
        } catch (error) { logger.error(error); throw error }
    },

    async importMarkdown(file: File): Promise<{ course_id: string; course_name: string }> {
        const formData = new FormData()
        formData.append('file', file)
        try {
            const res = await http.post('/api/import_markdown', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            })
            const { course_id, course_name } = res.data
            await this.fetchCourseList()
            await this.loadCourse(course_id)
            return { course_id, course_name }
        } catch (error) { logger.error(error); throw error }
    },

    async fetchCourseList() {
        this.loading = true
        try {
            const res = await http.get('/api/courses')
            this.courseList = res.data
        } catch (error) { logger.error(error); this.courseList = [] }
        finally { this.loading = false }
    },

    async loadCourse(courseId: string) {
        this.loading = true
        this.currentCourseId = courseId
        const noteStore = this._noteStore()
        noteStore.notes = []
        this.fetchCourseAnnotations(courseId)
        const genStore = this._genStore()

        try {
            try {
                const taskRes = await http.get(`/api/courses/${courseId}/task`)
                if (taskRes.data && taskRes.data.status !== 'none' && taskRes.data.status !== 'error') {
                    const backendTask = taskRes.data
                    let localTask = genStore.tasks.get(courseId)
                    if (!localTask) { localTask = genStore.createTask(courseId, 'Loading...', []) }
                    localTask.backendTaskId = backendTask.id
                    localTask.status = backendTask.status
                    localTask.progress = backendTask.progress
                    if (backendTask.status === 'running' || backendTask.status === 'pending') {
                        genStore.startGlobalMonitor()
                    }
                }
            } catch (_ignore) { /* no task is fine */ }

            const res = await http.get(`/api/courses/${courseId}`)
            if (res.data && res.data.nodes) {
                this.nodes = res.data.nodes
                this.courseTree = this.buildTree(this.nodes)
                const localTask = genStore.tasks.get(courseId)
                if (localTask && localTask.courseName === 'Loading...') {
                    localTask.courseName = res.data.course_name
                }
                if (localTask && localTask.status !== 'running') {
                    localTask.nodes = JSON.parse(JSON.stringify(this.nodes))
                }
                if (localTask && localTask.status === 'running') {
                    genStore.isGenerating = true
                    genStore.generationProgress = localTask.progress
                    genStore.currentGeneratingNode = localTask.currentStep
                    genStore.generationLogs = localTask.logs
                } else {
                    genStore.isGenerating = false
                    genStore.generationProgress = localTask ? localTask.progress : 100
                    genStore.generationLogs = localTask ? localTask.logs : []
                }
                
                const learningStore = useLearningStore()
                const pos = learningStore.getReadingPosition(courseId)
                if (pos) { this.scrollToNodeId = pos.nodeId }
            } else {
                throw new Error('课程数据为空')
            }
        } catch (error) {
            logger.error(error)
            ElMessage.error('加载课程失败')
            this.currentCourseId = ''
            this.currentNode = null
            this.nodes = []
            this.courseTree = []
            genStore.isGenerating = false
            genStore.generationStatus = 'idle'
            genStore.generationProgress = 0
        } finally { this.loading = false }
    },

    async deleteCourse(courseId: string) {
        const genStore = this._genStore()
        try {
            await http.delete(`/api/courses/${courseId}`)
            ElMessage.success('课程已删除')
            genStore.tasks.delete(courseId)
            await this.fetchCourseList()
            if (this.currentCourseId === courseId) {
                this.nodes = []; this.courseTree = []; this.currentCourseId = ''; this.currentNode = null
            }
            genStore.queue = genStore.queue.filter((item: QueueItem) => item.courseId !== courseId)
            genStore.persistGenerationState()
        } catch (error) { ElMessage.error('删除失败') }
    },

    async fetchCourseTree() {
        await this.fetchCourseList()
        if (this.courseList.length > 0 && this.courseList[0]) {
            await this.loadCourse(this.courseList[0].course_id)
        }
    },

    async refreshCourseData(courseId: string) {
        if (this.currentCourseId !== courseId) return
        try {
            const res = await http.get(`/api/courses/${courseId}`)
            if (res.data && res.data.nodes) {
                this.nodes = res.data.nodes
                this.courseTree = this.buildTree(this.nodes)
            }
        } catch (e) { logger.error('Failed to refresh course data', e) }
    },

    // ========== Node Operations ==========
    async markNodeAsRead(nodeId: string) {
        const node = this.nodes.find(n => n.node_id === nodeId)
        if (node && !node.is_read) {
            node.is_read = true
            try { await http.put(`/api/courses/${this.currentCourseId}/nodes/${nodeId}`, { is_read: true }) }
            catch (e) { logger.error('Failed to sync read status', e) }
        }
    },

    async updateNodeScore(nodeId: string, score: number) {
        const node = this.nodes.find(n => n.node_id === nodeId)
        if (node && (!node.quiz_score || score > node.quiz_score)) {
            node.quiz_score = score
            try { await http.put(`/api/courses/${this.currentCourseId}/nodes/${nodeId}`, { quiz_score: score }) }
            catch (e) { logger.error('Failed to sync quiz score', e) }
        }
    },

    async generateSubNodes(node: Node) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}/subnodes`, {
                node_id: node.node_id, node_name: node.node_name, node_level: node.node_level
            })
            this.nodes.push(...res.data)
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('子章节生成成功')
        } catch (error) { ElMessage.error('生成失败') }
        finally { this.loading = false }
    },

    async addCustomNode(parentId: string, name: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/nodes`, { parent_node_id: parentId, node_name: name })
            this.nodes.push(res.data)
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('添加成功')
        } catch (error) { ElMessage.error('添加失败') }
        finally { this.loading = false }
    },

    async deleteNode(nodeId: string) {
        if (!this.currentCourseId) return
        try {
            await http.delete(`/api/courses/${this.currentCourseId}/nodes/${nodeId}`)
            const toDelete = new Set<string>([nodeId])
            let changed = true
            while (changed) {
                changed = false
                this.nodes.forEach(n => {
                    if (toDelete.has(n.parent_node_id) && !toDelete.has(n.node_id)) { toDelete.add(n.node_id); changed = true }
                })
            }
            this.nodes = this.nodes.filter(n => !toDelete.has(n.node_id))
            this.courseTree = this.buildTree(this.nodes)
            ElMessage.success('删除成功')
        } catch (error) { ElMessage.error('删除失败') }
    },

    async renameNode(nodeId: string, newName: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            await http.put(`/api/courses/${this.currentCourseId}/nodes/${nodeId}`, { node_name: newName })
            const node = this.nodes.find(n => n.node_id === nodeId)
            if (node) { node.node_name = newName }
            ElMessage.success('重命名成功')
        } catch (error) { ElMessage.error('重命名失败') }
        finally { this.loading = false }
    },

    async locateNode(keyword: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/locate`, { keyword })
            if (res.data.target_node_id) {
                const target = this.nodes.find(n => n.node_id === res.data.target_node_id)
                if (target) { this.currentNode = target; ElMessage.success(`已定位到: ${target.node_name}`) }
            } else { ElMessage.warning('未找到相关节点') }
        } catch (error) { ElMessage.error('定位失败') }
        finally { this.loading = false }
    },

    // ========== Content Generation (single node, uses streaming) ==========
    async redefineContent(node: Node, requirement: string) {
        if (!this.currentCourseId) return
        this.loading = true
        const genStore = this._genStore()
        const courseContext = this.nodes.filter(n => n.node_level <= 2)
            .map(n => `${'  '.repeat(n.node_level - 1)}- ${n.node_name}`).join('\n')
        let previousContext = ""
        const linearNodes = this.getLinearNodes(this.courseTree)
        const idx = linearNodes.findIndex(n => n.node_id === node.node_id)
        if (idx > 0) {
            const prev = linearNodes[idx - 1]
            if (prev?.node_content) { previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500) }
        }
        try {
            node.node_content = ''; node.node_type = 'custom'
            const response = await fetch(`${API_BASE}/api/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ node_id: node.node_id, node_name: node.node_name, original_content: node.node_content, user_requirement: requirement, course_context: courseContext, previous_context: previousContext })
            })
            const reader = response.body?.getReader()
            if (reader) {
                const decoder = new TextDecoder()
                while (true) { const { done, value } = await reader.read(); if (done) break; genStore.addToBuffer(node.node_id, decoder.decode(value, { stream: true })) }
            }
            ElMessage.success('内容重写成功')
        } catch (error) { ElMessage.error('重写失败') }
        finally { this.loading = false }
    },

    async generateBody(node: Node) {
        if (!this.currentCourseId) return
        this.loading = true
        const genStore = this._genStore()
        const intro = node.node_content || ''
        const courseContext = this.nodes.filter(n => n.node_level <= 2)
            .map(n => `${'  '.repeat(n.node_level - 1)}- ${n.node_name}`).join('\n')
        let previousContext = ""
        const linearNodes = this.getLinearNodes(this.courseTree)
        const idx = linearNodes.findIndex(n => n.node_id === node.node_id)
        if (idx > 0) {
            const prev = linearNodes[idx - 1]
            if (prev?.node_content) { previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500) }
        }
        previousContext += `\n本节简介: ${intro}`
        try {
            if (!node.node_content?.includes('<!-- BODY_START -->')) {
                node.node_content = (node.node_content || '') + '\n\n<!-- BODY_START -->\n\n'
            }
            const response = await fetch(`${API_BASE}/api/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ node_id: node.node_id, node_name: node.node_name, original_content: '', user_requirement: '基于简介撰写教科书级详细正文，不要重复简介内容', course_context: courseContext, previous_context: previousContext })
            })
            const reader = response.body?.getReader()
            if (reader) {
                const decoder = new TextDecoder()
                while (true) { const { done, value } = await reader.read(); if (done) break; genStore.addToBuffer(node.node_id, decoder.decode(value, { stream: true })) }
            }
            ElMessage.success('正文生成完成')
        } catch (error) { ElMessage.error('生成失败'); logger.error(error) }
        finally { this.loading = false }
    },

    async extendContent(node: Node, requirement: string) {
        if (!this.currentCourseId) return
        this.loading = true
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}/extend`, {
                node_id: node.node_id, node_name: node.node_name, current_content: node.node_content, user_requirement: requirement
            })
            node.node_content += `\n\n${res.data.node_content}`
            ElMessage.success('内容扩展成功')
        } catch (error) { ElMessage.error('扩展失败') }
        finally { this.loading = false }
    },

    // ========== Annotations (legacy bridge to Notes) ==========
    async fetchCourseAnnotations(courseId: string) {
        const noteStore = this._noteStore()
        try {
            const res = await http.get(`/api/courses/${courseId}/annotations`)
            this.annotations = res.data
            const annotations = res.data as Annotation[]
            annotations.forEach(anno => {
                if (!noteStore.notes.find((n: Note) => n.id === anno.anno_id)) {
                    noteStore.notes.push({
                        id: anno.anno_id, nodeId: anno.node_id,
                        highlightId: `hl-${anno.anno_id}`, quote: anno.quote || '',
                        content: anno.answer || anno.question || '',
                        summary: anno.anno_summary || '', color: 'amber',
                        createdAt: Date.now(), sourceType: (anno.source_type as any) || 'user',
                    })
                }
            })
        } catch (error) { logger.error("Failed to load annotations", error) }
    },

    async saveAnnotation(anno: Partial<Annotation>) {
        if (anno.anno_id && this.annotations.find(a => a.anno_id === anno.anno_id)) {
            ElMessage.warning('该笔记已存在'); return
        }
        const newAnno: Annotation = {
            anno_id: anno.anno_id || `anno_${crypto.randomUUID()}`,
            node_id: anno.node_id!, course_id: this.currentCourseId,
            question: anno.question || 'User Note', answer: anno.answer || '',
            anno_summary: anno.anno_summary || 'Note',
            source_type: anno.source_type || 'user_saved', quote: anno.quote
        }
        try {
            if (newAnno.source_type !== 'format') { await http.post(`/api/annotations`, newAnno) }
            this.annotations.push(newAnno)
            if (newAnno.source_type !== 'format') { ElMessage.success('笔记已保存') }
            this.activeAnnotation = newAnno
        } catch (e) { ElMessage.error('保存失败'); logger.error(e) }
    },

    async deleteAnnotation(annoId: string) {
        try {
            await http.delete(`/api/annotations/${annoId}`)
            this.annotations = this.annotations.filter(a => a.anno_id !== annoId)
            ElMessage.success('笔记已删除')
            if (this.activeAnnotation?.anno_id === annoId) { this.activeAnnotation = null }
        } catch (e) { ElMessage.error('删除失败') }
    },

    // ========== Tree Utilities ==========
    buildTree(nodes: Node[]) {
        const nodeMap = new Map<string, Node>()
        const tree: Node[] = []
        nodes.forEach((node: Node) => { node.children = []; nodeMap.set(node.node_id, node) })
        nodes.forEach((node: Node) => {
            if (node.parent_node_id === 'root') { tree.push(node) }
            else { const parent = nodeMap.get(node.parent_node_id); if (parent) { parent.children?.push(node) } }
        })
        return tree
    },

    getLinearNodes(nodes?: Node[]): Node[] {
        const targetNodes = nodes || this.courseTree
        let result: Node[] = []
        for (const node of targetNodes) {
            result.push(node)
            if (node.children && node.children.length > 0) { result.push(...this.getLinearNodes(node.children)) }
        }
        return result
    },

    // ========== Chat & Quiz (deeply coupled to course state) ==========
    async sendMessage(message: string) {
        this.chatLoading = true
        try { await this.askQuestion(message) }
        finally { this.chatLoading = false }
    },

    async generateQuiz(nodeId: string, nodeContent: string, style: TeachingStyle = TEACHING_STYLES.ACADEMIC, difficulty: DifficultyLevel = DIFFICULTY_LEVELS.INTERMEDIATE, options: { silent?: boolean, questionCount?: number } = {}) {
        if (!this.currentCourseId) {
            ElMessage.warning('请先选择一个课程')
            return []
        }
        this.chatLoading = true
        const silent = options.silent === true
        const questionCount = options.questionCount || 3
        if (!silent) {
            this.chatHistory.push({
                type: 'user',
                content: `请为"${this.nodes.find(n => n.node_id === nodeId)?.node_name || '当前章节'}"生成一份${difficulty === DIFFICULTY_LEVELS.ADVANCED ? '精通' : (difficulty === DIFFICULTY_LEVELS.BEGINNER ? '入门' : '进阶')}难度的${style === TEACHING_STYLES.HUMOROUS ? '幽默风趣' : style === TEACHING_STYLES.SOCRATIC ? '苏格拉底' : style === TEACHING_STYLES.INDUSTRIAL ? '工业实践' : '学术严谨'}测试题（共${questionCount}题）。`
            })
        }
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/nodes/${nodeId}/quiz`, {
                node_content: nodeContent,
                node_name: this.nodes.find(n => n.node_id === nodeId)?.node_name || '',
                difficulty, style, user_persona: this.userPersona, question_count: questionCount
            })
            const processedQuizzes = Array.isArray(res.data) ? res.data.map((quizItem: any) => ({
                ...quizItem,
                answer: quizItem.answer || (typeof quizItem.correct_index === 'number' && quizItem.options ? quizItem.options[quizItem.correct_index] : ''),
                node_id: nodeId
            })) : []
            if (Array.isArray(res.data)) {
                if (res.data.length === 0) {
                    if (!silent) { this.chatHistory.push({ type: 'ai', content: '抱歉，无法根据当前内容生成测试题。' }) }
                } else if (!silent) {
                    const title = `### 📝 ${style === TEACHING_STYLES.HUMOROUS ? '趣味挑战' : (style === TEACHING_STYLES.INDUSTRIAL ? '实战演练' : (style === TEACHING_STYLES.SOCRATIC ? '思辨问答' : '知识测验'))}\n这里有几道题目来检测你的学习成果：`
                    this.chatHistory.push({ type: 'ai', content: { core_answer: title, answer: title, quiz_list: processedQuizzes } })
                }
            }
            return processedQuizzes
        } catch (error) {
            ElMessage.error('生成测验失败')
            if (!silent) { this.chatHistory.push({ type: 'ai', content: '生成测验时遇到错误，请稍后再试。' }) }
            return []
        } finally { this.chatLoading = false }
    },

    async quickSummarize() {
        if (!this.currentNode) { ElMessage.warning('请先选择一个章节'); return }
        this.chatLoading = true
        this.chatHistory.push({ type: 'user', content: `请帮我总结一下「${this.currentNode.node_name}」的核心内容` })
        try {
            const res = await http.post(`/api/courses/${this.currentCourseId}/nodes/${this.currentNode.node_id}/summarize`, {
                node_content: this.currentNode.node_content, node_name: this.currentNode.node_name, user_persona: this.userPersona
            })
            this.chatHistory.push({ type: 'ai', content: { answer: res.data.summary || res.data.content || '总结生成完成', core_answer: res.data.summary || res.data.content || '总结生成完成' } })
        } catch (e) {
            logger.error(e)
            this.chatHistory.push({ type: 'ai', content: '总结生成失败，请稍后再试' })
        } finally { this.chatLoading = false }
    },

    async summarizeChat() {
        if (this.chatHistory.length === 0) { ElMessage.warning('没有可总结的对话'); return null }
        this.chatLoading = true
        try {
            const history = this.chatHistory.map(msg => ({
                role: msg.type === 'user' ? 'user' : 'assistant',
                content: typeof msg.content === 'string' ? msg.content : (msg.content.core_answer || '')
            }))
            const context = this.currentNode ? `当前章节：${this.currentNode.node_name}` : '全书概览'
            const res = await http.post(`/api/summarize_chat`, { history, course_context: context, user_persona: this.userPersona })
            return res.data
        } catch (e) { logger.error(e); ElMessage.error('总结生成失败'); return null }
        finally { this.chatLoading = false }
    },

    async generateQuizFromSummary(summaryContent: string) {
        if (!this.currentNode) return
        this.addMessage('user', '请根据刚才的复盘内容，帮我出几道题巩固一下。')
        await this.askQuestion(`基于以下复盘内容生成测验：\n${summaryContent.slice(0, 2000)}`)
    },

    async askQuestion(question: string, selection: string = "", targetNodeId?: string) {
      let controller: AbortController | null = null
      let aiMessage: ChatMessage | null = null
      const noteStore = this._noteStore()
      let targetNode = this.currentNode
      if (targetNodeId) {
          const found = this.nodes.find(n => n.node_id === targetNodeId)
          if (found) targetNode = found
      }
      if (!targetNode && this.nodes.length > 0) { targetNode = this.nodes[0] || null }
      if (!targetNode) { ElMessage.warning('请先选择一个课程或章节'); return }

      this.loading = true
      this.chatLoading = true
      try {
        if (this.chatAbortController) { this.chatAbortController.abort() }
        controller = new AbortController()
        this.chatAbortController = controller
        const linearNodes = this.getLinearNodes(this.courseTree)
        const structureContext = linearNodes.map(n => `${'  '.repeat(n.node_level - 1)}- ${n.node_name} (ID: ${n.node_id})`).join('\n')
        let focusContext = ""
        if (targetNode) {
            focusContext = `\n\n### 当前选中/阅读章节 (重点关注)\n章节名：${targetNode.node_name}\nID：${targetNode.node_id}\n内容：\n${targetNode.node_content || '(暂无内容)'}`
        }
        const relevantNodes = linearNodes.filter(n => n.node_id !== targetNode?.node_id && n.node_content && question.includes(n.node_name))
        let retrievalContext = ""
        if (relevantNodes.length > 0) {
            retrievalContext = "\n\n### 相关章节内容（根据问题自动提取）\n" + relevantNodes.map(n => `章节：${n.node_name} (ID: ${n.node_id})\n内容：\n${n.node_content?.slice(0, 3000)}...`).join('\n\n')
        }
        const fullContext = `### 课程完整大纲结构\n${structureContext}${focusContext}${retrievalContext}`
        const history = this.chatHistory.map(msg => ({
            role: msg.type === 'user' ? 'user' : 'assistant',
            content: typeof msg.content === 'string' ? msg.content : (msg.content.core_answer || '')
        }))
        const sessionMetrics = this.calculateSessionMetrics()
        const userNotes = noteStore.notes.map((n: Note) => `- [${n.sourceType === 'ai' ? 'AI' : 'User'}] ${n.content} (Related to Node: ${n.nodeId})`).join('\n').slice(0, 5000)

        const aiMessageContent: AIContent = {
            core_answer: '', detail_answer: [], quote: '', anno_summary: 'AI 思考中...',
            anno_id: `anno_${crypto.randomUUID()}`, node_id: '', question: question, answer: ''
        }
        this.chatHistory.push({ type: 'ai', content: aiMessageContent })
        aiMessage = this.chatHistory[this.chatHistory.length - 1] as ChatMessage
        if (typeof aiMessage.content === 'string') return

        const response = await fetch(`${API_BASE}/api/ask`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                node_id: targetNode.node_id, node_name: targetNode.node_name,
                node_content: fullContext, question, history, selection,
                user_notes: userNotes, user_persona: this.userPersona,
                session_metrics: sessionMetrics, enable_long_term_memory: true
            }),
            signal: controller.signal
        })
        if (!response.ok) { throw new Error(`HTTP ${response.status}`) }
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
            if (!isCollectingMetadata) {
                const splitIdx = fullText.indexOf('---METADATA---')
                if (splitIdx !== -1) {
                    aiMessage.content.core_answer = fullText.substring(0, splitIdx)
                    aiMessage.content.answer = fullText.substring(0, splitIdx)
                    isCollectingMetadata = true
                } else {
                    aiMessage.content.core_answer = fullText
                    aiMessage.content.answer = fullText
                }
            }
        }

        // Final parse
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
                    const quoteText = (metadata.quote || '').trim()
                    const answerText = (aiMessage.content.core_answer || '').trim()
                    const summaryText = (metadata.anno_summary || '').trim()
                    const noteContentRaw = summaryText && summaryText !== 'AI 笔记' ? summaryText : answerText
                    const noteContent = noteContentRaw.replace(/\s+/g, ' ').trim()
                    if (quoteText && quoteText.length >= 3 && noteContent.length >= 8) {
                        const noteId = `note-${Date.now()}`
                        const resolvedNodeId = metadata.node_id || this.currentNode?.node_id || ''
                        const shortSummary = summaryText && summaryText !== 'AI 笔记' ? summaryText : (answerText.length > 50 ? `${answerText.slice(0, 50)}...` : answerText)
                        this.activeAnnotation = {
                            anno_id: noteId, node_id: resolvedNodeId, question: 'AI 笔记',
                            answer: answerText, anno_summary: shortSummary || 'AI 笔记',
                            source_type: 'ai_chat', quote: quoteText
                        }
                        noteStore.createNote({
                            id: noteId, nodeId: resolvedNodeId, highlightId: `highlight-${Date.now()}`,
                            quote: quoteText, content: answerText, summary: shortSummary,
                            color: 'purple', createdAt: Date.now(), sourceType: 'ai'
                        })
                        aiMessage.content.anno_id = noteId
                        if (metadata.node_id) {
                            this.scrollToNode(metadata.node_id)
                            setTimeout(() => { this.focusNoteId = null; setTimeout(() => { this.focusNoteId = noteId }, 50) }, 100)
                        }
                    }
                }
            } catch (e) { logger.warn("Failed to parse metadata", e) }
        } else {
            aiMessage.content.core_answer = fullText
            aiMessage.content.answer = fullText
        }
      } catch (error: any) {
        if (controller?.signal.aborted || error?.name === 'AbortError') {
            if (aiMessage && typeof aiMessage.content !== 'string') {
                aiMessage.content.core_answer = '已停止生成'; aiMessage.content.answer = '已停止生成'; aiMessage.content.anno_summary = '已停止生成'
            }
            return
        }
        logger.error(error); ElMessage.error('提问失败')
        if (aiMessage && typeof aiMessage.content !== 'string') {
            aiMessage.content.core_answer = '生成失败，请稍后重试。'; aiMessage.content.answer = '生成失败，请稍后重试。'; aiMessage.content.anno_summary = '生成失败'
        }
      } finally {
        this.loading = false; this.chatLoading = false
        if (this.chatAbortController === controller) { this.chatAbortController = null }
      }
    },

    // ========== Session Metrics (internal, used by askQuestion) ==========
    calculateSessionMetrics() {
        const metrics = {
            total_messages: this.chatHistory.length,
            user_messages: this.chatHistory.filter(m => m.type === 'user').length,
            ai_messages: this.chatHistory.filter(m => m.type === 'ai').length,
            session_duration_minutes: 0,
            topics_discussed: [] as string[],
            question_types: { conceptual: 0, procedural: 0, troubleshooting: 0, exploratory: 0 }
        }
        if (this.chatHistory.length >= 2) {
            metrics.session_duration_minutes = Math.max(1, Math.floor(this.chatHistory.length / 2))
        }
        const userQuestions = this.chatHistory.filter(m => m.type === 'user').map(m => typeof m.content === 'string' ? m.content : '')
        metrics.topics_discussed = this.extractSessionTopics(userQuestions)
        userQuestions.forEach(q => {
            if (q.includes('为什么') || q.includes('是什么') || q.includes('概念')) { metrics.question_types.conceptual++ }
            else if (q.includes('怎么') || q.includes('如何') || q.includes('步骤')) { metrics.question_types.procedural++ }
            else if (q.includes('错误') || q.includes('问题') || q.includes('失败')) { metrics.question_types.troubleshooting++ }
            else { metrics.question_types.exploratory++ }
        })
        return metrics
    },

    extractSessionTopics(questions: string[]): string[] {
        const topics = new Set<string>()
        const topicKeywords = ['概念', '原理', '定义', '方法', '步骤', '流程', '函数', '类', '对象', '变量', '算法', '数据结构', '前端', '后端', '数据库', 'API', '框架', '库', '错误', '异常', '调试', '优化', '性能', '安全']
        questions.forEach(q => { topicKeywords.forEach(kw => { if (q.includes(kw)) topics.add(kw) }) })
        return Array.from(topics).slice(0, 10)
    },

    // ========== Session Memory (internal) ==========
    saveSessionMemory(sessionId: string, memory: any) {
        try {
            const key = `session_memory_${sessionId}`
            const existing = localStorage.getItem(key)
            let memories = existing ? JSON.parse(existing) : []
            memory.timestamp = Date.now()
            memories.push(memory)
            if (memories.length > 50) { memories = memories.slice(-50) }
            localStorage.setItem(key, JSON.stringify(memories))
        } catch (e) { logger.warn('Failed to save session memory:', e) }
    },

    getSessionMemories(sessionId: string, limit: number = 10): any[] {
        try {
            const key = `session_memory_${sessionId}`
            const data = localStorage.getItem(key)
            if (!data) return []
            return JSON.parse(data).slice(-limit)
        } catch (e) { logger.warn('Failed to get session memories:', e); return [] }
    },

    clearSessionMemories(sessionId: string) {
        try { localStorage.removeItem(`session_memory_${sessionId}`) }
        catch (e) { logger.warn('Failed to clear session memories:', e) }
    },

    // ========== Backward-compat: Learning Store delegations ==========
    get learningStats() {
        
        return useLearningStore().learningStats
    },
    get learningPath() {
        
        return useLearningStore().learningPath
    },
    get knowledgeMastery() {
        
        return useLearningStore().knowledgeMastery
    },
    get learningPathLoading() {
        
        return useLearningStore().learningPathLoading
    },
    recordStudyTime(seconds: number, nodeId?: string) {
        
        return useLearningStore().recordStudyTime(seconds, nodeId)
    },
    saveReadingPosition(courseId: string, nodeId: string, scrollTop: number) {
        
        return useLearningStore().saveReadingPosition(courseId, nodeId, scrollTop)
    },
    getReadingPosition(courseId: string) {
        
        return useLearningStore().getReadingPosition(courseId)
    },
    markNodeAsCompleted(nodeId: string) {
        
        return useLearningStore().markNodeAsCompleted(nodeId)
    },
    isNodeCompleted(nodeId: string) {
        
        return useLearningStore().isNodeCompleted(nodeId)
    },
    getNodeReadTime(nodeId: string) {
        
        return useLearningStore().getNodeReadTime(nodeId)
    },
    getTodayStudyTime() {
        
        return useLearningStore().getTodayStudyTime()
    },
    getWeeklyStudyTime() {
        
        return useLearningStore().getWeeklyStudyTime()
    },
    persistLearningStats() {
        
        return useLearningStore().persistLearningStats()
    },
    restoreLearningStats() {
        
        return useLearningStore().restoreLearningStats()
    },
    generateLearningPath(goal: string, availableTime: number, focusAreas?: string[], weakAreas?: string[]) {
        
        return useLearningStore().generateLearningPath(this.currentCourseId, goal, availableTime, focusAreas, weakAreas)
    },
    fetchKnowledgeMastery() {
        
        return useLearningStore().fetchKnowledgeMastery(this.currentCourseId)
    },
    fetchLearningStats() {
        
        return useLearningStore().fetchLearningStats(this.currentCourseId)
    },
    clearLearningPath() {
        
        return useLearningStore().clearLearningPath()
    },
    clearKnowledgeMastery() {
        
        return useLearningStore().clearKnowledgeMastery()
    },

    // ========== Backward-compat: Review Store delegations ==========
    get wrongAnswers() {
        
        return useReviewStore().wrongAnswers
    },
    get quizHistory() {
        
        return useReviewStore().quizHistory
    },
    recordWrongAnswer(quizData: { question: string; options: string[]; correctIndex: number; userIndex: number; explanation: string; nodeId: string; nodeName: string; reflection?: string }) {
        
        return useReviewStore().recordWrongAnswer(quizData)
    },
    recordQuizResult(nodeId: string, nodeName: string, total: number, correct: number) {
        
        return useReviewStore().recordQuizResult(nodeId, nodeName, total, correct)
    },
    persistQuizData() {
        
        return useReviewStore().persistQuizData()
    },
    restoreQuizData() {
        
        return useReviewStore().restoreQuizData()
    },
    getWrongAnswersForReview(limit?: number) {
        
        return useReviewStore().getWrongAnswersForReview(limit)
    },
    markWrongAnswerReviewed(question: string, nodeId: string, remove?: boolean) {
        
        return useReviewStore().markWrongAnswerReviewed(question, nodeId, remove)
    },
    getQuizStats() {
        
        return useReviewStore().getQuizStats()
    },
    generateSmartQuizFromMistakes() {
        
        return useReviewStore().generateSmartQuizFromMistakes()
    },

    // ========== Backward-compat: Note Store delegations ==========
    createNote(note: Note) { this._noteStore().createNote(note) },
    updateNote(id: string, content: string) { return this._noteStore().updateNote(id, content) },
    deleteNote(id: string) { return this._noteStore().deleteNote(id) },
    updateNoteTags(id: string, tags: string[]) { return this._noteStore().updateNoteTags(id, tags) },
    updateNoteCategory(id: string, category: string) { return this._noteStore().updateNoteCategory(id, category) },
    updateNotePriority(id: string, priority: 'low' | 'medium' | 'high') { return this._noteStore().updateNotePriority(id, priority) },
    getAllTags() { return this._noteStore().getAllTags() },
    getAllCategories() { return this._noteStore().getAllCategories() },
    getNotesByTag(tag: string) { return this._noteStore().getNotesByTag(tag) },
    getNotesByCategory(category: string) { return this._noteStore().getNotesByCategory(category) },
    getNotesByPriority(priority: 'low' | 'medium' | 'high') { return this._noteStore().getNotesByPriority(priority) },
    exportNotesToMarkdown() { return this._noteStore().exportNotesToMarkdown() },
    exportNotesToJSON() { return this._noteStore().exportNotesToJSON() },
    downloadNotes(format: 'markdown' | 'json' = 'markdown') { return this._noteStore().downloadNotes(format) },

    // ========== Backward-compat: Generation Store delegations ==========
    get tasks(): Map<string, Task> { return this._genStore().tasks },
    set tasks(val: any) { this._genStore().tasks = val },
    get taskProgress() { return this._genStore().taskProgress },
    set taskProgress(val: any) { this._genStore().taskProgress = val },
    get queue() { return this._genStore().queue },
    set queue(val: any) { this._genStore().queue = val },
    get isGenerating() { return this._genStore().isGenerating },
    set isGenerating(val: boolean) { this._genStore().isGenerating = val },
    get generationStatus() { return this._genStore().generationStatus },
    set generationStatus(val: any) { this._genStore().generationStatus = val },
    get generationLogs() { return this._genStore().generationLogs },
    set generationLogs(val: any) { this._genStore().generationLogs = val },
    get currentGeneratingNode() { return this._genStore().currentGeneratingNode },
    set currentGeneratingNode(val: any) { this._genStore().currentGeneratingNode = val },
    get generationProgress() { return this._genStore().generationProgress },
    set generationProgress(val: number) { this._genStore().generationProgress = val },
    getTask(courseId: string) { return this._genStore().getTask(courseId) },
    pauseTask(courseId: string) { return this._genStore().pauseTask(courseId) },
    startTask(courseId: string) { return this._genStore().startTask(courseId) },
    cancelTask(courseId: string) { return this._genStore().cancelTask(courseId) },
    generateCourse(keyword: string, options: { difficulty?: string; style?: string; requirements?: string } = {}) {
        return this._genStore().generateCourse(keyword, options)
    },

    // ========== Course Export ==========
    exportCourseJson() {
        const course = this.courseList.find(c => c.course_id === this.currentCourseId)
        const nodeIds = new Set(this.getLinearNodes(this.courseTree).map(n => n.node_id))
        const noteStore = this._noteStore()
        const notes = noteStore.notes.filter((n: Note) => nodeIds.has(n.nodeId) && n.sourceType !== 'format')
        if (!course && this.nodes.length === 0 && notes.length === 0) {
            ElMessage.warning('当前没有可导出的内容'); return
        }
        const data = JSON.stringify({
            exportedAt: dayjs().format('YYYY-MM-DD HH:mm:ss'),
            course: course || null, nodes: this.nodes, courseTree: this.courseTree, notes
        }, null, 2)
        const filename = `${sanitizeFileName(course?.course_name || 'course')}_export_${dayjs().format('YYYYMMDD_HHmmss')}.json`
        downloadBlob(new Blob([data], { type: 'application/json' }), filename)
        ElMessage.success('导出成功')
    },

    exportCourseMarkdown() {
        const course = this.courseList.find(c => c.course_id === this.currentCourseId)
        const linearNodes = this.getLinearNodes(this.courseTree)
        const nodeIds = new Set(linearNodes.map(n => n.node_id))
        const noteStore = this._noteStore()
        const notes: Note[] = noteStore.notes.filter((n: Note) => nodeIds.has(n.nodeId))
        if (!course && this.nodes.length === 0 && notes.length === 0) {
            ElMessage.warning('当前没有可导出的内容'); return
        }
        const courseName = course?.course_name || 'My Course'
        let md = `# ${courseName}\n\n`
        md += `> 导出时间：${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
        md += `> 节点数：${this.nodes.length}\n\n`
        md += `> 笔记数：${notes.filter((n: Note) => n.sourceType !== 'format').length}\n\n---\n\n`
        const groupedNotes = new Map<string, Note[]>()
        const nodeOrder = new Map(linearNodes.map((n: Node, i: number) => [n.node_id, i]))
        notes.sort((a: Note, b: Note) => {
            const orderA = nodeOrder.get(a.nodeId) ?? -1
            const orderB = nodeOrder.get(b.nodeId) ?? -1
            if (orderA !== orderB) return orderA - orderB
            return a.createdAt - b.createdAt
        })
        notes.forEach((note: Note) => {
            if (!groupedNotes.has(note.nodeId)) groupedNotes.set(note.nodeId, [])
            groupedNotes.get(note.nodeId)?.push(note)
        })
        linearNodes.forEach(node => {
            const level = Math.min(4, Math.max(1, Number(node.node_level || 1)))
            md += `${'#'.repeat(level)} ${node.node_name}\n\n`
            if (node.node_content) { md += `${node.node_content}\n\n` }
            const nodeNotes = groupedNotes.get(node.node_id)?.filter(n => n.sourceType !== 'format') || []
            if (nodeNotes.length > 0) {
                md += `**笔记**\n\n`
                nodeNotes.forEach(note => {
                    if (note.quote) { md += `> ${note.quote}\n\n` }
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
  }
})
