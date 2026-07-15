import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { type CourseGenerationOptions } from '@/shared/prompt-config'
import { useNoteStore } from './notes'
import { useGenerationStore } from './generation'
import logger from '../utils/logger'
import { courseDocumentToNodes } from '../utils/course-document'
import { t } from '@/shared/i18n'

// =============================================================================
// Course Store - 核心课程状态管理
// =============================================================================
//
// 架构说明：
// 本模块管理课程核心状态和与课程深度耦合的功能（聊天、导航、导出）。
// 已拆分到独立 Store 的功能域：
//   - generation.ts  → 生成队列、任务管理
//   - notes.ts       → 笔记 CRUD、标签、导出
//   - learning.ts    → 学习统计、学习路径、知识掌握度
//   - review.ts      → 错题记录、测验历史
//   - chat.ts        → 聊天基础状态（备用）
// =============================================================================

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
export type { ContentBlock, Node, Annotation, Note, Course, SelectionRewritePayload, SelectionRewriteResult } from './types'
import type {
    BlockRegenerationApplyResult,
    BlockRegenerationCandidate,
    CourseBlockEditTarget,
    CourseDocumentEnvelope,
    Node,
    Annotation,
    Note,
    Course,
    Task,
    SelectionRewritePayload,
    SelectionRewriteResult,
} from './types'

export const useCourseStore = defineStore('course', {
  state: () => ({
    // --- 核心课程状态 ---
    courseList: [] as Course[],
    currentCourseId: '' as string,
    currentCourseVersionId: '' as string,
    currentDocumentRevision: '' as string,
    currentCourseSourceFormat: '' as '' | 'canonical' | 'legacy_projection',
    courseTree: [] as Node[],
    nodes: [] as Node[],
    currentNode: null as Node | null,
    currentPedagogyProfile: null as null | {
        primary_mode: string
        secondary_mode?: string | null
        secondary_intensity?: string | null
        confidence?: string
        rationale?: string
    },
    currentGenerationQualityReport: null as Record<string, unknown> | null,
    loading: false,

    // --- Annotations（fetchCourseAnnotations 桥接 Notes 系统） ---
    annotations: [] as Annotation[],

    activeAnnotation: null as Annotation | null,

    // --- UI State ---
    isFocusMode: false,
    showKnowledgeLibrary: false,
    globalSearchQuery: '',
    scrollToNodeId: null as string | null,
    focusNoteId: null as string | null,

    uiSettings: (() => {
        try {
            const saved = JSON.parse(localStorage.getItem('ui_settings') || 'null')
            if (saved && typeof saved.fontSize === 'number' && saved.fontSize >= 8 && saved.fontSize <= 72) {
                return { fontSize: saved.fontSize, fontFamily: saved.fontFamily || 'sans', lineHeight: saved.lineHeight || 1.75 }
            }
        } catch {}
        return { fontSize: 17, fontFamily: 'sans' as 'sans' | 'serif' | 'mono', lineHeight: 1.75 }
    })(),
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
        localStorage.setItem('ui_settings', JSON.stringify(this.uiSettings))
    },
    toggleFocusMode() { this.isFocusMode = !this.isFocusMode },
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
        await this._genStore().generateCourse(courseName)
        return this.currentCourseId
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
        } catch (error) {
            logger.error(error)
            // Keep the last successful list so offline task actions do not disappear.
        }
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
                    if (!localTask) {
                        localTask = genStore.createTask(backendTask.id, courseId, 'Loading...')
                    }
                    localTask.id = backendTask.id
                    localTask.status = backendTask.status
                    localTask.progress = backendTask.progress
                    const phase = backendTask.current_phase || backendTask.phase
                    if (phase) localTask.currentPhase = phase
                    localTask.phaseProgress = backendTask.phase_progress ?? backendTask.progress
                    localTask.phaseDetail = backendTask.phase_detail || {}
                    if (backendTask.status === 'running' || backendTask.status === 'pending') {
                        genStore.startGlobalMonitor()
                    }
                }
            } catch (_ignore) { /* no task is fine */ }

            const res = await http.get<CourseDocumentEnvelope>(`/api/courses/${courseId}/document`)
            if (res.data?.document) {
                const currentNodeId = this.currentNode?.node_id
                this.nodes = courseDocumentToNodes(res.data.document)
                this.courseTree = this.buildTree(this.nodes)
                this.currentCourseVersionId = res.data.current_course_version_id || ''
                this.currentDocumentRevision = res.data.document.document_revision || ''
                this.currentCourseSourceFormat = res.data.source_format || ''
                if (currentNodeId) this.currentNode = this.nodes.find(node => node.node_id === currentNodeId) || null
                this.currentPedagogyProfile = res.data.subject_pedagogy_profile || null
                this.currentGenerationQualityReport = res.data.generation_quality_report || null
                const localTask = genStore.tasks.get(courseId)
                if (localTask && localTask.courseName === 'Loading...') {
                    localTask.courseName = res.data.course_name
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
                
            } else {
                throw new Error('课程数据为空')
            }
        } catch (error) {
            logger.error(error)
            ElMessage.error('加载课程失败')
            this.currentCourseId = ''
            this.currentNode = null
            this.currentCourseVersionId = ''
            this.currentDocumentRevision = ''
            this.currentCourseSourceFormat = ''
            this.currentPedagogyProfile = null
            this.currentGenerationQualityReport = null
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
            ElMessage.success(t('courseLibrary.deleted', '课程已删除'))
            genStore.dropLocalTaskState(courseId)
            await this.fetchCourseList()
            if (this.currentCourseId === courseId) {
                this.nodes = []; this.courseTree = []; this.currentCourseId = ''; this.currentNode = null
                this.currentCourseVersionId = ''; this.currentDocumentRevision = ''; this.currentCourseSourceFormat = ''
                this.currentPedagogyProfile = null
                this.currentGenerationQualityReport = null
            }
            genStore.persistGenerationState()
        } catch (error) {
            throw error
        }
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
            const res = await http.get<CourseDocumentEnvelope>(`/api/courses/${courseId}/document`)
            if (res.data?.document) {
                const currentNodeId = this.currentNode?.node_id
                this.nodes = courseDocumentToNodes(res.data.document)
                this.courseTree = this.buildTree(this.nodes)
                if (currentNodeId) this.currentNode = this.nodes.find(node => node.node_id === currentNodeId) || null
                this.currentPedagogyProfile = res.data.subject_pedagogy_profile || null
                this.currentGenerationQualityReport = res.data.generation_quality_report || null
                this.currentCourseVersionId = res.data.current_course_version_id || ''
                this.currentDocumentRevision = res.data.document.document_revision || ''
                this.currentCourseSourceFormat = res.data.source_format || ''
            }
        } catch (e) { logger.error('Failed to refresh course data', e) }
    },

    // ========== Node Operations ==========
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
            const originalContent = node.node_content
            node.node_content = ''; node.node_type = 'custom'
            const response = await fetch(withApiBase(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`), {
                method: 'POST', headers: learnerIdentityHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ node_id: node.node_id, node_name: node.node_name, original_content: originalContent, user_requirement: requirement, course_context: courseContext, previous_context: previousContext })
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

    async rewriteSelection(node: Node, payload: SelectionRewritePayload): Promise<SelectionRewriteResult> {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const res = await http.post(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}/selection-rewrite`, payload)
        return res.data as SelectionRewriteResult
    },

    async createBlockRegenerationCandidate(
        target: CourseBlockEditTarget,
        instruction: string,
        actionType: 'rewrite' | 'simplify' | 'example' | 'expand' = 'rewrite',
    ): Promise<BlockRegenerationCandidate> {
        if (!this.currentCourseId || !this.currentDocumentRevision) throw new Error('Missing canonical course revision')
        const response = await http.post(
            `/api/courses/${this.currentCourseId}/blocks/${target.block.block_id}/regeneration-candidates`,
            {
                request_id: crypto.randomUUID(),
                expected_document_revision: this.currentDocumentRevision,
                expected_block_revision: target.block.internal_revision,
                instruction,
                action_type: actionType,
            },
        )
        return response.data as BlockRegenerationCandidate
    },

    async getLatestBlockRegenerationCandidate(
        target: CourseBlockEditTarget,
    ): Promise<BlockRegenerationCandidate | null> {
        if (!this.currentCourseId || !this.currentDocumentRevision) return null
        try {
            const response = await http.get(
                `/api/courses/${this.currentCourseId}/blocks/${target.block.block_id}/regeneration-candidates/latest`,
                {
                    params: {
                        expected_document_revision: this.currentDocumentRevision,
                        expected_block_revision: target.block.internal_revision,
                    },
                },
            )
            return response.data as BlockRegenerationCandidate
        } catch (error: any) {
            if (error?.response?.status === 404) return null
            throw error
        }
    },

    async getBlockRegenerationCandidate(
        candidate: BlockRegenerationCandidate,
    ): Promise<BlockRegenerationCandidate> {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const response = await http.get(
            `/api/courses/${this.currentCourseId}/blocks/${candidate.block_id}/regeneration-candidates/${candidate.candidate_id}`,
        )
        return response.data as BlockRegenerationCandidate
    },

    async retryBlockRegenerationCandidate(
        candidate: BlockRegenerationCandidate,
    ): Promise<BlockRegenerationCandidate> {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const response = await http.post(
            `/api/courses/${this.currentCourseId}/blocks/${candidate.block_id}/regeneration-candidates/${candidate.candidate_id}/retry`,
        )
        return response.data as BlockRegenerationCandidate
    },

    async applyBlockRegenerationCandidate(candidate: BlockRegenerationCandidate): Promise<BlockRegenerationApplyResult> {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const response = await http.post(
            `/api/courses/${this.currentCourseId}/blocks/${candidate.block_id}/regeneration-candidates/${candidate.candidate_id}/apply`,
        )
        const result = response.data as BlockRegenerationApplyResult
        const envelope = result.document
        this.nodes = courseDocumentToNodes(envelope.document)
        this.courseTree = this.buildTree(this.nodes)
        this.currentCourseVersionId = envelope.current_course_version_id || ''
        this.currentDocumentRevision = envelope.document.document_revision || ''
        this.currentCourseSourceFormat = envelope.source_format
        const currentNodeId = this.currentNode?.node_id
        this.currentNode = currentNodeId ? this.nodes.find(node => node.node_id === currentNodeId) || null : null
        return result
    },

    async rejectBlockRegenerationCandidate(candidate: BlockRegenerationCandidate): Promise<BlockRegenerationCandidate> {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const response = await http.post(
            `/api/courses/${this.currentCourseId}/blocks/${candidate.block_id}/regeneration-candidates/${candidate.candidate_id}/reject`,
        )
        return response.data as BlockRegenerationCandidate
    },

    async saveNodeContent(node: Node, content: string) {
        if (!this.currentCourseId) throw new Error('Missing current course')
        const res = await http.put(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}`, {
            node_content: content,
        })
        const saved = res.data?.node || {}
        node.node_content = typeof saved.node_content === 'string' ? saved.node_content : content
        node.content_blocks = []
        node.node_type = 'custom'
        return node
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
            const response = await fetch(withApiBase(`/api/courses/${this.currentCourseId}/nodes/${node.node_id}/redefine_stream`), {
                method: 'POST', headers: learnerIdentityHeaders({ 'Content-Type': 'application/json' }),
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
            const extension = res.data.content || res.data.node_content || ''
            node.node_content += `\n\n${extension}`
            ElMessage.success('内容扩展成功')
        } catch (error) { ElMessage.error('扩展失败') }
        finally { this.loading = false }
    },

    // ========== Learning records (legacy method names retained for callers) ==========
    async fetchCourseAnnotations(courseId: string) {
        const noteStore = this._noteStore()
        try {
            await noteStore.loadCourseRecords(courseId)
            this.annotations = []
        } catch (error) { logger.error("Failed to load learning records", error) }
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
        const saved = await this._noteStore().createNote({
            id: newAnno.anno_id,
            nodeId: newAnno.node_id,
            highlightId: `hl-${newAnno.anno_id}`,
            quote: newAnno.quote || '',
            content: newAnno.answer || '',
            summary: newAnno.anno_summary,
            color: 'amber',
            createdAt: Date.now(),
            sourceType: newAnno.source_type === 'ai' ? 'ai' : 'user',
            recordType: 'note',
        })
        if (saved) this.activeAnnotation = newAnno
    },

    async deleteAnnotation(annoId: string) {
        await this._noteStore().deleteNote(annoId)
        this.annotations = this.annotations.filter(a => a.anno_id !== annoId)
        if (this.activeAnnotation?.anno_id === annoId) { this.activeAnnotation = null }
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
    generateCourse(subject: string, options: CourseGenerationOptions = {}) {
        return this._genStore().generateCourse(subject, options)
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
