/* eslint-disable @typescript-eslint/no-unused-vars */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import { useCourseStore } from './course'
import { useTaskWebSocket, type ConnectionState } from '../composables/useTaskWebSocket'
import {
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  PARAMETER_RULES,
  type DifficultyLevel,
  type TeachingStyle
} from '@/shared/prompt-config'
import type { Node, QueueItem, Task, WSMessage, FailureReport } from './types'

// vue-tsc + Pinia Options API: re-export to suppress TS6133
export { ElMessage, TEACHING_STYLES }
export type { TeachingStyle }

export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const GENERATION_STATE_KEY = 'course-generation-state-v1'
export const MAX_RETRIES = 2
export const QUEUE_PROCESS_DELAY = 50
export const DIFFICULTY_CONFIG: Record<DifficultyLevel, { requirement: string; formulaDensity: string; subSectionRange: [number, number] }> = {
  [DIFFICULTY_LEVELS.BEGINNER]: {
    requirement: '通俗易懂的基础入门教程，重点解释核心概念，多用生活案例类比，避免过于深奥的理论推导。内容要偏基础，适合初学者。',
    formulaDensity: '<10%',
    subSectionRange: [PARAMETER_RULES.subChapterCount.beginner.min, PARAMETER_RULES.subChapterCount.beginner.max]
  },
  [DIFFICULTY_LEVELS.INTERMEDIATE]: {
    requirement: '标准专业教程，理论与实践相结合，包含代码示例或应用场景。不涉及过深的底层原理，但要覆盖核心用法。',
    formulaDensity: '10-30%',
    subSectionRange: [PARAMETER_RULES.subChapterCount.intermediate.min, PARAMETER_RULES.subChapterCount.intermediate.max]
  },
  [DIFFICULTY_LEVELS.ADVANCED]: {
    requirement: '深度专业的技术文档，包含底层原理、源码分析、性能优化和高级最佳实践。适合专家阅读。',
    formulaDensity: '>30%',
    subSectionRange: [PARAMETER_RULES.subChapterCount.advanced.min, PARAMETER_RULES.subChapterCount.advanced.max]
  }
}

export const useGenerationStore = defineStore('generation', {
  state: () => ({
    tasks: new Map<string, Task>(),
    globalTasks: [] as any[],
    globalPollingTimer: null as number | null,
    activeTaskId: null as string | null,
    taskProgress: {} as Record<string, {
      percentage: number
      currentNodeName: string
      completedNodes: number
      totalNodes: number
      estimatedTimeRemaining: number
      bytesGenerated: number
      updatedAt: Date
    }>,
    queue: [] as QueueItem[],
    isQueueProcessing: false,
    isGenerating: false,
    generationStatus: 'idle' as 'idle' | 'generating' | 'paused' | 'error',
    generationLogs: [] as string[],
    currentGeneratingNode: null as string | null,
    currentGeneratingNodeId: null as string | null,
    generationProgress: 0,
    typingBuffer: new Map<string, string>(),
    typingInterval: null as number | null,
    stateRestored: false,
    // --- WebSocket state ---
    wsConnected: false,
    wsConnectionState: 'disconnected' as ConnectionState,
    // --- Outline edit mode ---
    isOutlineEditMode: false,
    // --- Failure report ---
    failureReport: null as FailureReport | null,
    // --- Streaming content accumulation ---
    streamingContent: {} as Record<string, string>,
  }),

  actions: {
    _courseStore() {
      return useCourseStore()
    },

    // ========== WebSocket Integration ==========

    initWebSocket() {
      const ws = useTaskWebSocket({
        onMessage: (message: WSMessage) => {
          this.handleWSMessage(message)
        },
        onStateChange: (state: ConnectionState) => {
          this.wsConnectionState = state
          const wasConnected = this.wsConnected
          this.wsConnected = state === 'connected'

          if (this.wsConnected) {
            // WebSocket connected → stop HTTP polling (Req 1.3)
            this.stopGlobalMonitor()
            // Re-subscribe to current course if available
            const cs = this._courseStore()
            if (cs.currentCourseId) {
              ws.subscribe(cs.currentCourseId)
            }
            // Deterministic refresh on reconnect (Req 12.3)
            if (!wasConnected && cs.currentCourseId) {
              cs.refreshCourseData(cs.currentCourseId)
            }
          } else if (state === 'disconnected' || state === 'error') {
            // WebSocket disconnected → fall back to HTTP polling (Req 1.4)
            this.startGlobalMonitor()
          }
        },
      })
      ws.connect()
    },

    handleWSMessage(message: WSMessage) {
      switch (message.type) {
        case 'progress_update':
          this.handleWSProgressUpdate(message)
          break
        case 'node_completed':
          this.handleWSNodeCompleted(message)
          break
        case 'stream_chunk':
          this.handleWSStreamChunk(message)
          break
        case 'task_completed':
          this.handleWSProgressUpdate(message)
          // Deterministic refresh on task completed (Req 12.3)
          {
            const cs = this._courseStore()
            if (message.course_id === cs.currentCourseId) {
              cs.refreshCourseData(message.course_id)
            }
          }
          break
        case 'task_error':
          this.handleWSTaskError(message)
          break
        case 'failure_report':
          this.handleWSFailureReport(message)
          break
      }
    },

    handleWSProgressUpdate(message: WSMessage) {
      const { course_id, task_id, payload } = message
      const localTask = this.tasks.get(course_id)
      if (localTask) {
        const status = (payload.status as string) || localTask.status
        if (status === 'running') localTask.status = 'running'
        else if (status === 'paused') localTask.status = 'paused'
        else if (status === 'completed') localTask.status = 'completed'
        else if (status === 'error') localTask.status = 'error'
        else if (status === 'pending') localTask.status = 'pending'

        localTask.progress = (payload.progress as number) ?? localTask.progress
        localTask.backendTaskId = task_id || localTask.backendTaskId
        const currentNodeName = payload.current_node_name as string | undefined
        if (currentNodeName) {
          localTask.currentStep = `正在生成: ${currentNodeName}`
        } else if (status === 'pending') {
          localTask.currentStep = '等待中...'
        }
        if (payload.current_nodes) {
          localTask.currentNodes = payload.current_nodes as Task['currentNodes']
        }
      }
      this.taskProgress[course_id] = {
        percentage: (payload.progress as number) ?? 0,
        currentNodeName: (payload.current_node_name as string) ?? '',
        completedNodes: (payload.completed_nodes as number) ?? 0,
        totalNodes: (payload.total_nodes as number) ?? 0,
        estimatedTimeRemaining: (() => {
          const completed = (payload.completed_nodes as number) ?? 0
          const total = (payload.total_nodes as number) ?? 0
          const prev = this.taskProgress[course_id]
          const prevCompleted = prev?.completedNodes ?? 0
          if (completed > prevCompleted && completed < total && prev?.updatedAt) {
            const elapsed = (Date.now() - prev.updatedAt.getTime()) / 1000
            const nodesPerSec = (completed - prevCompleted) / Math.max(elapsed, 0.1)
            return nodesPerSec > 0 ? Math.round((total - completed) / nodesPerSec) : 0
          }
          return completed >= total && total > 0 ? 0 : (prev?.estimatedTimeRemaining ?? 0)
        })(),
        bytesGenerated: (payload.bytes_generated as number) ?? this.taskProgress[course_id]?.bytesGenerated ?? 0,
        updatedAt: new Date(),
      }
    },

    handleWSNodeCompleted(message: WSMessage) {
      const { course_id, payload } = message
      const cs = this._courseStore()
      if (course_id === cs.currentCourseId && payload.node_id) {
        const nodeId = payload.node_id as string
        const node = cs.nodes.find((n: Node) => n.node_id === nodeId)
        if (node) {
          if (payload.node_content !== undefined) {
            node.node_content = payload.node_content as string
          }
          node.generation_status = 'completed'
          if (payload.generated_chars !== undefined) {
            node.generated_chars = payload.generated_chars as number
          }
        }
        if (this.currentGeneratingNodeId === nodeId) {
          this.currentGeneratingNodeId = null
          this.currentGeneratingNode = null
        }
      }
      if (course_id === cs.currentCourseId) {
        cs.refreshCourseData(course_id)
      }
      const nodeId = payload.node_id as string
      if (nodeId) {
        delete this.streamingContent[nodeId]
      }
    },

    handleWSStreamChunk(message: WSMessage) {
      const { course_id, payload } = message
      const nodeId = payload.node_id as string
      const chunk = payload.chunk as string
      if (!nodeId || !chunk) return

      this.streamingContent[nodeId] = (this.streamingContent[nodeId] || '') + chunk

      const cs = this._courseStore()
      if (course_id === cs.currentCourseId) {
        if (this.currentGeneratingNodeId !== nodeId) {
          this.currentGeneratingNodeId = nodeId
          const node = cs.nodes.find((n: Node) => n.node_id === nodeId)
          if (node) {
            this.currentGeneratingNode = `正在生成: ${node.node_name}`
            node.generation_status = 'generating'
          }
        }
        this.addToBuffer(nodeId, chunk)
      }
    },

    handleWSTaskError(message: WSMessage) {
      const { course_id, payload } = message
      const localTask = this.tasks.get(course_id)
      if (localTask) {
        if (payload.node_id) {
          const cs = this._courseStore()
          if (course_id === cs.currentCourseId) {
            const node = cs.nodes.find((n: Node) => n.node_id === (payload.node_id as string))
            if (node) {
              node.generation_status = 'error'
              node.error_summary = (payload.error as string) || 'Unknown error'
            }
            if (this.currentGeneratingNodeId === payload.node_id) {
              this.currentGeneratingNodeId = null
              this.currentGeneratingNode = null
            }
          }
          this.addLogToTask(course_id, `❌ 节点生成失败: ${payload.node_name || payload.node_id} - ${payload.error || 'Unknown error'}`)
        } else {
          localTask.status = 'error'
          this.addLogToTask(course_id, `❌ 任务错误: ${payload.error || 'Unknown error'}`)
        }
      }
    },

    handleWSFailureReport(message: WSMessage) {
      const { payload } = message
      this.failureReport = {
        task_id: message.task_id,
        course_id: message.course_id,
        failed_nodes: (payload.failed_nodes as FailureReport['failed_nodes']) || [],
        total_failed: (payload.total_failed as number) || 0,
      }
    },

    // ========== Node Control Actions (Req 7.1, 7.2, 7.5) ==========

    async skipNode(courseId: string, nodeId: string) {
      const ws = useTaskWebSocket()
      const sent = ws.sendCommand({
        type: 'skip_node',
        course_id: courseId,
        node_id: nodeId,
      })
      if (!sent) {
        // HTTP fallback
        try {
          await http.post(`/api/courses/${courseId}/nodes/${nodeId}/skip`)
        } catch (e) {
          console.error('Failed to skip node', e)
          ElMessage.error('跳过节点失败')
        }
      }
    },

    async retryNode(courseId: string, nodeId: string) {
      const ws = useTaskWebSocket()
      const sent = ws.sendCommand({
        type: 'retry_node',
        course_id: courseId,
        node_id: nodeId,
      })
      if (!sent) {
        // HTTP fallback
        try {
          await http.post(`/api/courses/${courseId}/nodes/${nodeId}/retry`)
        } catch (e) {
          console.error('Failed to retry node', e)
          ElMessage.error('重试节点失败')
        }
      }
    },

    async stopNode(courseId: string, nodeId: string) {
      const ws = useTaskWebSocket()
      ws.sendCommand({
        type: 'stop_node',
        course_id: courseId,
        node_id: nodeId,
      })
    },

    async setCustomInstruction(courseId: string, nodeId: string, instruction: string) {
      const ws = useTaskWebSocket()
      ws.sendCommand({
        type: 'custom_instruction',
        course_id: courseId,
        node_id: nodeId,
        payload: { instruction },
      })
    },

    async retryAllFailed(courseId: string) {
      const ws = useTaskWebSocket()
      const sent = ws.sendCommand({
        type: 'retry_all_failed',
        course_id: courseId,
      })
      if (!sent) {
        // HTTP fallback
        try {
          await http.post(`/api/courses/${courseId}/retry_all_failed`)
        } catch (e) {
          console.error('Failed to retry all failed nodes', e)
          ElMessage.error('批量重试失败')
        }
      }
    },

    // ========== Outline Edit Actions (Req 6.2, 6.3) ==========

    enterOutlineEditMode() {
      this.isOutlineEditMode = true
    },

    async confirmOutline(courseId: string) {
      try {
        await http.post(`/api/courses/${courseId}/confirm_outline`)
        this.isOutlineEditMode = false
      } catch (e) {
        console.error('Failed to confirm outline', e)
        ElMessage.error('确认大纲失败')
      }
    },

    async updateOutline(courseId: string, nodes: Node[]) {
      try {
        await http.put(`/api/courses/${courseId}/outline`, { nodes })
      } catch (e) {
        console.error('Failed to update outline', e)
        ElMessage.error('更新大纲失败')
      }
    },

    // ========== Existing Actions (preserved) ==========

    addLog(msg: string, courseId?: string) {
      const cs = this._courseStore()
      const cid = courseId || cs.currentCourseId
      if (cid) {
        const task = this.tasks.get(cid)
        if (task) { task.logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`) }
      }
      this.generationLogs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
    },

    addLogToTask(courseId: string, msg: string) {
      const cs = this._courseStore()
      const task = this.tasks.get(courseId)
      if (task) { task.logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`) }
      if (cs.currentCourseId === courseId) {
        this.generationLogs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
      }
    },

    createTask(courseId: string, courseName: string, nodes: Node[], options: { difficulty?: string } = {}): Task {
      const task: Task = {
        id: courseId, courseName, status: 'idle', progress: 0, currentStep: '',
        logs: [], nodes: JSON.parse(JSON.stringify(nodes)), shouldStop: false,
        difficulty: options.difficulty,
      }
      this.tasks.set(courseId, task)
      return task
    },

    getTask(courseId: string) { return this.tasks.get(courseId) },

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
        this.startBackendTask(courseId)
      }
    },

    cancelTask(courseId: string) {
      const cs = this._courseStore()
      const task = this.tasks.get(courseId)
      if (task) {
        if (task.backendTaskId) { http.delete(`/api/tasks/${task.backendTaskId}`) }
        this.tasks.delete(courseId)
        this.queue = this.queue.filter(i => i.courseId !== courseId)
        if (cs.currentCourseId === courseId) {
          this.isGenerating = false
          this.generationStatus = 'idle'
          this.generationProgress = 0
          this.currentGeneratingNode = null
          this.currentGeneratingNodeId = null
        }
        delete this.taskProgress[courseId]
        this.persistGenerationState()
      }
    },

    persistGenerationState() {
      try {
        const tasks = Array.from(this.tasks.values()).map(task => ({
          id: task.id, courseName: task.courseName, status: task.status,
          progress: task.progress, currentStep: task.currentStep,
          logs: task.logs, nodes: task.nodes, shouldStop: false
        }))
        const queue = this.queue.map(item => ({ ...item }))
        const cs = this._courseStore()
        const data = { version: 1, currentCourseId: cs.currentCourseId, tasks, queue }
        localStorage.setItem(GENERATION_STATE_KEY, JSON.stringify(data))
      } catch (e) { console.error(e) }
    },

    restoreGenerationState() {
      if (this.stateRestored) { const cs = this._courseStore(); return cs.currentCourseId }
      const raw = localStorage.getItem(GENERATION_STATE_KEY)
      if (!raw) return null
      try {
        const data = JSON.parse(raw)
        const tasks = new Map<string, Task>()
        if (Array.isArray(data.tasks)) {
          data.tasks.forEach((task: Task) => { tasks.set(task.id, { ...task, shouldStop: false }) })
        }
        const normalizedQueue = Array.isArray(data.queue)
          ? data.queue.filter((item: QueueItem) => item.status === 'completed' || item.status === 'error')
          : []
        this.tasks = tasks
        this.queue = normalizedQueue
        this.isQueueProcessing = false
        const cs = this._courseStore()
        cs.currentCourseId = ''
        this.tasks.forEach(task => {
          if ((task.status === 'running' || task.status === 'paused') && !task.backendTaskId) {
            task.status = 'idle'
            task.currentStep = ''
            this.addLogToTask(task.id, '⏹️ 未完成的任务已停止')
          }
        })
        this.stateRestored = true
        return null
      } catch (e) { console.error(e); return null }
    },

    finalizeIdleTasks() {
      let updated = false
      this.tasks.forEach(task => {
        const hasWork = this.queue.some(i => i.courseId === task.id && (i.status === 'pending' || i.status === 'running'))
        if (task.status === 'running' && !hasWork) {
          const hasGraphTask = this.queue.some(i => i.courseId === task.id && i.type === 'knowledge_graph')
          if (!hasGraphTask) {
            this.addToQueue({ courseId: task.id, type: 'knowledge_graph', targetNodeId: 'root', title: '生成知识图谱' })
            return
          }
          task.status = 'completed'
          task.progress = 100
          task.currentStep = ''
          this.addLogToTask(task.id, '✅ 生成完成')
          updated = true
        }
      })
      if (updated) {
        this.isGenerating = false
        const cs = this._courseStore()
        if (cs.currentCourseId) {
          const currentTask = this.tasks.get(cs.currentCourseId)
          if (!currentTask || currentTask.status !== 'running') { this.generationStatus = 'idle' }
        }
        this.persistGenerationState()
      }
    },

    async fetchGlobalTasks() {
      const cs = this._courseStore()
      try {
        const res = await http.get('/api/tasks?limit=100')
        this.globalTasks = res.data
        this.globalTasks.forEach((backendTask: any) => {
          const courseId = backendTask.course_id
          const localTask = this.tasks.get(courseId)
          if (localTask) {
            const prevStatus = localTask.status
            if (backendTask.status === 'running') localTask.status = 'running'
            else if (backendTask.status === 'paused') localTask.status = 'paused'
            else if (backendTask.status === 'completed') localTask.status = 'completed'
            else if (backendTask.status === 'error') localTask.status = 'error'
            else if (backendTask.status === 'pending') localTask.status = 'pending'
            localTask.progress = backendTask.progress
            localTask.backendTaskId = backendTask.id
            if (backendTask.current_node_name) {
              localTask.currentStep = `正在生成: ${backendTask.current_node_name}`
            }

            // Sync taskProgress for UI (progress bar, node count, ETA)
            const completedNodes = backendTask.completed_nodes ?? 0
            const totalNodes = backendTask.total_nodes ?? 0
            const prev = this.taskProgress[courseId]
            const prevCompleted = prev?.completedNodes ?? 0
            let eta = prev?.estimatedTimeRemaining ?? 0
            // Estimate remaining time based on polling interval
            if (completedNodes > prevCompleted && completedNodes < totalNodes) {
              const elapsed = prev?.updatedAt ? (Date.now() - prev.updatedAt.getTime()) : 2000
              const nodesPerMs = (completedNodes - prevCompleted) / Math.max(elapsed, 1)
              const remaining = totalNodes - completedNodes
              eta = nodesPerMs > 0 ? Math.round(remaining / nodesPerMs / 1000) : 0
            } else if (completedNodes >= totalNodes && totalNodes > 0) {
              eta = 0
            }
            this.taskProgress[courseId] = {
              percentage: backendTask.progress ?? 0,
              currentNodeName: backendTask.current_node_name ?? '',
              completedNodes,
              totalNodes,
              estimatedTimeRemaining: eta,
              bytesGenerated: prev?.bytesGenerated ?? 0,
              updatedAt: new Date(),
            }

            // Deterministic refresh: only when task transitions to completed (Req 12.1, 12.3)
            if (courseId === cs.currentCourseId && prevStatus !== 'completed' && localTask.status === 'completed') {
              cs.refreshCourseData(courseId)
            }
          }
        })
      } catch (e) { console.error('Failed to fetch global tasks', e) }
    },

    startGlobalMonitor() {
      if (this.globalPollingTimer) return
      // Don't start polling if WebSocket is connected (Req 1.3)
      if (this.wsConnected) return
      this.fetchGlobalTasks()
      this.globalPollingTimer = window.setInterval(() => { this.fetchGlobalTasks() }, 2000)
    },

    stopGlobalMonitor() {
      if (this.globalPollingTimer) { clearInterval(this.globalPollingTimer); this.globalPollingTimer = null }
    },

    async startBackendTask(courseId: string) {
      // Block generation in outline edit mode (Req 6.2)
      if (this.isOutlineEditMode) {
        ElMessage.warning('请先确认大纲后再启动生成任务')
        return
      }
      try {
        const cs = this._courseStore()
        const res = await http.post(`/api/courses/${courseId}/auto_generate`)
        const { task_id } = res.data
        let task = this.tasks.get(courseId)
        if (!task) {
          const course = cs.courseList.find((c: any) => c.course_id === courseId)
          task = this.createTask(courseId, course?.course_name || 'Unknown Course', [])
        }
        task.backendTaskId = task_id
        task.status = 'running'
        task.shouldStop = false
        this.addLogToTask(courseId, `🚀 后台任务已启动 (ID: ${task_id})`)
        this.persistGenerationState()
        // Subscribe to this course via WebSocket
        if (this.wsConnected) {
          const ws = useTaskWebSocket()
          ws.subscribe(courseId)
        } else {
          this.startGlobalMonitor()
        }
      } catch (error) {
        console.error('Failed to start backend task', error)
        ElMessage.error('启动后台生成失败')
      }
    },

    startTypingEffect() {
      if (this.typingInterval) return
      this.typingInterval = window.setInterval(() => {
        let hasWork = false
        const cs = this._courseStore()
        this.typingBuffer.forEach((buffer, nodeId) => {
          if (buffer.length > 0) {
            hasWork = true
            let speed = 1
            if (buffer.length > 500) speed = 50
            else if (buffer.length > 200) speed = 20
            else if (buffer.length > 50) speed = 5
            else if (buffer.length > 10) speed = 2
            const chunk = buffer.slice(0, speed)
            this.typingBuffer.set(nodeId, buffer.slice(speed))
            const node = cs.nodes.find((n: Node) => n.node_id === nodeId)
            if (node) { node.node_content = (node.node_content || '') + chunk }
          } else { this.typingBuffer.delete(nodeId) }
        })
        if (!this.isGenerating && !hasWork) {
          if (this.typingInterval !== null) { clearInterval(this.typingInterval); this.typingInterval = null }
        }
      }, 10)
    },

    addToBuffer(nodeId: string, content: string) {
      const current = this.typingBuffer.get(nodeId) || ''
      this.typingBuffer.set(nodeId, current + content)
      this.startTypingEffect()
    },

    stopGeneration() {
      const cs = this._courseStore()
      if (cs.currentCourseId) { this.pauseTask(cs.currentCourseId) }
      this.isGenerating = false
      this.generationStatus = 'paused'
      this.typingBuffer.clear()
      if (this.typingInterval) { clearInterval(this.typingInterval); this.typingInterval = null }
      ElMessage.info('生成已暂停')
      this.persistGenerationState()
    },

    async startSmartGeneration(keyword: string, options: { difficulty?: string, style?: string, requirements?: string } = {}) {
      // Block generation in outline edit mode (Req 6.2)
      if (this.isOutlineEditMode) {
        ElMessage.warning('请先确认大纲后再启动生成任务')
        return
      }
      const cs = this._courseStore()
      cs.loading = true
      this.isGenerating = true
      this.generationStatus = 'generating'
      this.generationProgress = 0
      this.generationLogs = []
      this.addLog(`🚀 启动智能课程生成引擎: ${keyword}`)
      try {
        this.addLog(`🏗️ 正在构建课程大纲架构...`)
        const res = await http.post(`/api/generate_course`, { keyword, ...options })
        if (res.data && res.data.nodes) {
          const courseId = res.data.course_id
          const courseName = res.data.course_name
          const task = this.createTask(courseId, courseName, res.data.nodes, options)
          task.status = 'running'
          cs.currentCourseId = courseId
          cs.nodes = res.data.nodes
          cs.courseTree = cs.buildTree(cs.nodes)
          await cs.fetchCourseList()
          this.addLog(`✅ 大纲架构构建完成，包含 ${cs.nodes.length} 个节点`)
          this.taskProgress[courseId] = {
            percentage: 0,
            currentNodeName: '',
            completedNodes: 0,
            totalNodes: cs.nodes.length,
            estimatedTimeRemaining: 0,
            bytesGenerated: 0,
            updatedAt: new Date()
          }
          this.persistGenerationState()
          await this.startBackendTask(courseId)
        }
      } catch (error) {
        this.addLog(`❌ 生成失败: ${error}`)
        ElMessage.error('生成失败')
        this.isGenerating = false
        this.generationStatus = 'error'
        this.persistGenerationState()
      } finally { cs.loading = false }
    },

    async generateCourse(keyword: string, options: { difficulty?: string, style?: string, requirements?: string } = {}) {
      await this.startSmartGeneration(keyword, options)
    },

    addToQueue(item: Omit<QueueItem, 'uuid' | 'status'>) {
      const exists = this.queue.some(existing =>
        existing.courseId === item.courseId &&
        existing.type === item.type &&
        existing.targetNodeId === item.targetNodeId &&
        (existing.status === 'pending' || existing.status === 'running')
      )
      if (exists) return
      const newItem: QueueItem = { ...item, uuid: crypto.randomUUID(), status: 'pending' }
      this.queue.push(newItem)
      this.persistGenerationState()
      this.processQueue()
    },

    retryQueueItem(uuid: string) {
      const item = this.queue.find(i => i.uuid === uuid)
      if (item && item.status === 'error') {
        item.status = 'pending'
        item.retryCount = 0
        item.errorMsg = undefined
        this.addLogToTask(item.courseId, `🔄 手动重试: ${item.title}`)
        this.persistGenerationState()
        this.processQueue()
      }
    },

    async processQueue() {
      if (this.isQueueProcessing) return
      const nextItem = this.queue.find(i => {
        if (i.status !== 'pending') return false
        const task = this.tasks.get(i.courseId)
        return task && task.status === 'running' && !task.shouldStop
      })
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
        this.updateTaskUI(task, nextItem)
        await this.dispatchQueueItem(nextItem)
        this.markQueueItemSuccess(nextItem, task)
      } catch (e: any) {
        await this.handleQueueError(nextItem, task, e)
      } finally { this.finalizeQueueItem(task) }
    },

    updateTaskUI(task: Task | undefined, item: QueueItem) {
      if (!task) return
      const cs = this._courseStore()
      task.status = 'running'
      task.currentStep = item.title
      if (cs.currentCourseId === item.courseId) {
        this.currentGeneratingNodeId = item.targetNodeId
        this.currentGeneratingNode = task.currentStep
        this.isGenerating = true
        this.generationStatus = 'generating'
      }
    },

    async dispatchQueueItem(item: QueueItem) {
      switch (item.type) {
        case 'structure': await this.processStructureItem(item); break
        case 'content': await this.processContentItem(item); break
        case 'subchapter': await this.processSubchapterItem(item); break
        case 'knowledge_graph': await this.processKnowledgeGraphItem(item); break
      }
    },

    markQueueItemSuccess(item: QueueItem, task: Task | undefined) {
      item.status = 'completed'
      if (task) {
        task.logs.push(`✅ 完成: ${item.title}`)
        this.updateTaskProgress(task)
      }
      this.persistGenerationState()
    },

    async handleQueueError(item: QueueItem, task: Task | undefined, error: any) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      item.retryCount = (item.retryCount || 0) + 1
      if (item.retryCount <= MAX_RETRIES) {
        item.status = 'pending'
        if (task) { task.logs.push(`⚠️ 失败 (${item.retryCount}/${MAX_RETRIES}): ${item.title} - ${errorMessage}，准备重试...`) }
      } else {
        item.status = 'error'
        item.errorMsg = errorMessage
        if (task) { task.logs.push(`❌ 失败: ${item.title} - ${errorMessage}`); this.updateTaskProgress(task) }
      }
      this.persistGenerationState()
    },

    updateTaskProgress(task: Task) {
      const total = this.queue.length
      const completed = this.queue.filter(i => i.status === 'completed' || i.status === 'error').length
      task.progress = Math.floor((completed / total) * 100)
    },

    finalizeQueueItem(task: Task | undefined) {
      if (task && task.shouldStop) { this.isQueueProcessing = false; task.status = 'paused' }
      else { this.isQueueProcessing = false; setTimeout(() => this.processQueue(), QUEUE_PROCESS_DELAY) }
      this.persistGenerationState()
    },

    async processStructureItem(item: QueueItem) {
      const cs = this._courseStore()
      const task = this.tasks.get(item.courseId)
      if (!task) throw new Error('Task not found')
      const node = task.nodes.find((n: Node) => n.node_id === item.targetNodeId)
      if (!node) throw new Error('Node not found')
      this.addLogToTask(item.courseId, `📂 正在构建: ${node.node_name}...`)
      const res = await http.post(`/api/courses/${item.courseId}/nodes/${node.node_id}/subnodes`, {
        node_id: node.node_id, node_name: node.node_name, node_level: node.node_level
      })
      const newNodes = res.data
      if (Array.isArray(newNodes)) {
        task.nodes.push(...newNodes)
        for (const newNode of newNodes) {
          const level = Number(newNode.node_level)
          if (level === 2) {
            this.addToQueue({ courseId: item.courseId, type: 'structure', targetNodeId: newNode.node_id, title: `细化小节: ${newNode.node_name}` })
          } else {
            this.addToQueue({ courseId: item.courseId, type: 'content', targetNodeId: newNode.node_id, title: `撰写正文: ${newNode.node_name}` })
          }
        }
        if (cs.currentCourseId === item.courseId) {
          cs.nodes = [...task.nodes]
          cs.courseTree = cs.buildTree(cs.nodes)
        }
      }
    },

    async processContentItem(item: QueueItem) {
      const cs = this._courseStore()
      const task = this.tasks.get(item.courseId)
      if (!task) throw new Error('Task not found')
      const node = task.nodes.find((n: Node) => n.node_id === item.targetNodeId)
      if (!node) throw new Error('Node not found')
      this.addLogToTask(item.courseId, `📝 正在撰写: ${node.node_name}...`)
      const courseContext = task.nodes
        .filter((n: Node) => n.node_level <= 2)
        .map((n: Node) => `${'  '.repeat(n.node_level - 1)}- ${n.node_name}`)
        .join('\n')
      const index = task.nodes.findIndex((n: Node) => n.node_id === node.node_id)
      let previousContext = '相关上下文...'
      if (index > 0) {
        const prev = task.nodes[index - 1]
        if (prev && prev.node_content) {
          previousContext = `上节 (${prev.node_name}) 回顾: ` + prev.node_content.slice(-300)
        }
      }
      node.node_content = ''
      node.node_type = 'custom'
      const response = await fetch(`${API_BASE}/api/courses/${item.courseId}/nodes/${node.node_id}/redefine_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: node.node_id, node_name: node.node_name,
          original_content: '', user_requirement: '详细正文',
          course_context: courseContext, previous_context: previousContext
        })
      })
      const reader = response.body?.getReader()
      if (reader) {
        const decoder = new TextDecoder()
        while (true) {
          if (task.shouldStop) { reader.cancel(); break }
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          node.node_content = (node.node_content || '') + chunk
          if (cs.currentCourseId === item.courseId) { this.addToBuffer(node.node_id, chunk) }
        }
      }
    },

    async processSubchapterItem(item: QueueItem) {
      const cs = this._courseStore()
      const task = this.tasks.get(item.courseId)
      if (!task) throw new Error('Task not found')
      if (task.shouldStop) return
      const node = task.nodes.find((n: Node) => n.node_id === item.targetNodeId)
      if (!node) throw new Error('Node not found')
      const content = node.node_content || ''
      const headers: string[] = []
      const regex = /^(#{1,6})\s+(.*)$/gm
      let match
      while ((match = regex.exec(content)) !== null) {
        if (match[2]) { headers.push(match[2].trim()) }
      }
      if (headers.length > 0) {
        this.addLogToTask(item.courseId, `🔍 提取到 ${headers.length} 个标题，正在生成...`)
        for (const title of headers) {
          try {
            const res = await http.post(`/api/courses/${item.courseId}/nodes`, {
              parent_node_id: node.node_id, node_name: title,
              node_level: node.node_level + 1, node_content: ''
            })
            task.nodes.push(res.data)
            this.addToQueue({ courseId: item.courseId, type: 'content', targetNodeId: res.data.node_id, title: `撰写正文: ${res.data.node_name}` })
          } catch (e) { console.error('Manual create failed, trying fallback', e) }
        }
      } else {
        this.addLogToTask(item.courseId, `🤖 智能生成子章节...`)
        const res = await http.post(`/api/courses/${item.courseId}/nodes/${node.node_id}/subnodes`, {
          node_id: node.node_id, node_name: node.node_name, node_level: node.node_level
        })
        const newNodes = res.data
        task.nodes.push(...newNodes)
        for (const newNode of newNodes) {
          this.addToQueue({ courseId: item.courseId, type: 'content', targetNodeId: newNode.node_id, title: `撰写正文: ${newNode.node_name}` })
        }
      }
      if (cs.currentCourseId === item.courseId) {
        cs.nodes = [...task.nodes]
        cs.courseTree = cs.buildTree(cs.nodes)
      }
    },

    async processKnowledgeGraphItem(item: QueueItem) {
      this.addLogToTask(item.courseId, `🕸️ 正在生成知识图谱...`)
      try {
        await http.post(`/api/courses/${item.courseId}/knowledge_graph`)
        this.addLogToTask(item.courseId, `✅ 知识图谱生成完成`)
      } catch (e) { console.error('Failed to generate knowledge graph', e); throw e }
    },

    async generateSubChapters(node: Node) {
      const cs = this._courseStore()
      if (!cs.currentCourseId) return
      this.addToQueue({ courseId: cs.currentCourseId, type: 'subchapter', targetNodeId: node.node_id, title: `生成子章节: ${node.node_name}` })
    },

    async generateFullDetails(courseId?: string) {
      const cs = this._courseStore()
      const targetCourseId = courseId || cs.currentCourseId
      if (!targetCourseId) return
      const task = this.tasks.get(targetCourseId)
      if (!task) return
      task.status = 'running'
      task.shouldStop = false
      if (targetCourseId === cs.currentCourseId) { this.generationStatus = 'generating' }
      const l1Nodes = task.nodes.filter((n: Node) => n.node_level === 1)
      for (const n of l1Nodes) {
        const hasChildren = task.nodes.some((child: Node) => child.parent_node_id === n.node_id)
        if (!hasChildren) { this.addToQueue({ courseId: targetCourseId, type: 'structure', targetNodeId: n.node_id, title: `构建章节: ${n.node_name}` }) }
      }
      const l2Nodes = task.nodes.filter((n: Node) => n.node_level === 2)
      for (const n of l2Nodes) {
        const hasChildren = task.nodes.some((child: Node) => child.parent_node_id === n.node_id)
        if (!hasChildren) { this.addToQueue({ courseId: targetCourseId, type: 'structure', targetNodeId: n.node_id, title: `细化小节: ${n.node_name}` }) }
      }
      const l3Nodes = task.nodes.filter((n: Node) => n.node_level === 3 && (!n.node_content || n.node_content.length < 50))
      for (const n of l3Nodes) {
        this.addToQueue({ courseId: targetCourseId, type: 'content', targetNodeId: n.node_id, title: `撰写正文: ${n.node_name}` })
      }
    },

    async generateNodeContent(nodeId: string) {
      const cs = this._courseStore()
      if (!cs.currentCourseId) return
      const node = cs.nodes.find((n: Node) => n.node_id === nodeId)
      if (!node) return
      this.isGenerating = true
      this.currentGeneratingNode = `正在生成: ${node.node_name}`
      this.currentGeneratingNodeId = nodeId
      this.addLog(`🚀 开始生成章节: ${node.node_name}`)
      node.node_content = ''
      node.node_type = 'custom'
      try {
        const courseContext = cs.nodes
          .filter((n: Node) => n.node_level <= 2)
          .map((n: Node) => `${'  '.repeat(n.node_level - 1)}- ${n.node_name}`)
          .join('\n')
        const linear = cs.getLinearNodes(cs.courseTree)
        const idx = linear.findIndex((n: Node) => n.node_id === nodeId)
        let previousContext = '相关背景...'
        if (idx > 0) {
          const prev = linear[idx - 1]
          if (prev && prev.node_content) {
            previousContext = `上节回顾 (${prev.node_name}): ` + prev.node_content.slice(-500)
          }
        }
        const task = this.tasks.get(cs.currentCourseId)
        const difficulty = (task?.difficulty as DifficultyLevel) || DIFFICULTY_LEVELS.ADVANCED
        const style = (task?.style as TeachingStyle) || TEACHING_STYLES.ACADEMIC
        const requirement = DIFFICULTY_CONFIG[difficulty]?.requirement || '教科书级详细正文'
        const response = await fetch(`${API_BASE}/api/courses/${cs.currentCourseId}/nodes/${nodeId}/redefine_stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            node_id: node.node_id, node_name: node.node_name,
            original_content: node.node_content || '',
            user_requirement: requirement, course_context: courseContext,
            previous_context: previousContext, difficulty: difficulty, style: style
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
  },
})
