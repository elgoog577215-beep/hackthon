/* eslint-disable @typescript-eslint/no-unused-vars */
import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'
import { ElMessage } from 'element-plus'
import { useCourseStore } from './course'
import { useTaskWebSocket, type ConnectionState } from '../composables/useTaskWebSocket'
import {
  TEACHING_STYLES,
  type CourseGenerationOptions,
  type TeachingStyle
} from '@/shared/prompt-config'
import type { Node, Task, WSMessage, FailureReport } from './types'
import { t } from '@/shared/i18n'

// vue-tsc + Pinia Options API: re-export to suppress TS6133
export { ElMessage, TEACHING_STYLES }
export type { TeachingStyle }

const GENERATION_STATE_KEY = 'course-generation-state-v1'
const SERVER_BACKED_TASK_STATUSES = new Set<Task['status']>([
  'pending',
  'running',
  'paused',
  'waiting_for_review',
  'conflict',
  'error',
  'completed_with_warnings',
])
const isPublishedTask = (task: Task, backendTask?: Record<string, any>) => (
  task.status === 'completed'
  || (task.status === 'completed_with_warnings' && backendTask?.publication_allowed !== false)
)
const PHASE_LABELS: Record<string, string> = {
  queued: 'courseGeneration.phases.queued',
  requirement_analysis: 'courseGeneration.phases.requirement_analysis',
  material_processing: 'courseGeneration.phases.material_processing',
  pedagogy_resolution: 'courseGeneration.phases.pedagogy_resolution',
  blueprint_generation: 'courseGeneration.phases.blueprint_generation',
  blueprint_validation: 'courseGeneration.phases.blueprint_validation',
  blueprint_ready: 'courseGeneration.phases.blueprint_ready',
  content_generation: 'courseGeneration.phases.content_generation',
  learning_assets: 'courseGeneration.phases.learning_assets',
  content_validation: 'courseGeneration.phases.content_validation',
  finalizing: 'courseGeneration.phases.finalizing',
  completed: 'courseGeneration.phases.completed',
}

const phaseLabel = (phase: string): string => t(PHASE_LABELS[phase] || '', phase)

const mergeStreamDelta = (existing: string, delta: string): string => {
  if (!delta || existing.endsWith(delta)) return existing
  const maxOverlap = Math.min(existing.length, delta.length)
  for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
    if (existing.endsWith(delta.slice(0, overlap))) {
      return existing + delta.slice(overlap)
    }
  }
  return existing + delta
}

type TaskProgressState = {
  percentage: number
  currentNodeName: string
  completedNodes: number
  totalNodes: number
  estimatedTimeRemaining: number
  bytesGenerated: number
  updatedAt: Date
  lastCompletedAt?: Date
  etaSampleCount: number
  secondsPerNode: number
}

const projectTaskProgress = (
  previous: TaskProgressState | undefined,
  input: Omit<TaskProgressState, 'updatedAt' | 'lastCompletedAt' | 'etaSampleCount' | 'secondsPerNode' | 'estimatedTimeRemaining'>,
  now = new Date(),
): TaskProgressState => {
  const completedRegressed = Boolean(previous && input.completedNodes < previous.completedNodes)
  let lastCompletedAt = completedRegressed ? undefined : previous?.lastCompletedAt
  let etaSampleCount = completedRegressed ? 0 : (previous?.etaSampleCount ?? 0)
  let secondsPerNode = completedRegressed ? 0 : (previous?.secondsPerNode ?? 0)

  if (!previous || input.completedNodes > previous.completedNodes) {
    const completedDelta = input.completedNodes - (previous?.completedNodes ?? 0)
    if (previous?.lastCompletedAt && previous.completedNodes > 0 && completedDelta > 0) {
      const elapsedSeconds = (now.getTime() - previous.lastCompletedAt.getTime()) / 1000
      if (elapsedSeconds > 0) {
        const observedSecondsPerNode = elapsedSeconds / completedDelta
        secondsPerNode = secondsPerNode > 0
          ? (secondsPerNode * 0.7) + (observedSecondsPerNode * 0.3)
          : observedSecondsPerNode
        etaSampleCount += 1
      }
    }
    if (input.completedNodes > 0) lastCompletedAt = now
  }

  const complete = input.totalNodes > 0 && input.completedNodes >= input.totalNodes
  const estimatedTimeRemaining = !complete && etaSampleCount >= 2 && secondsPerNode > 0
    ? Math.max(1, Math.round((input.totalNodes - input.completedNodes) * secondsPerNode))
    : 0

  return {
    ...input,
    estimatedTimeRemaining,
    updatedAt: now,
    lastCompletedAt,
    etaSampleCount,
    secondsPerNode,
  }
}

export const useGenerationStore = defineStore('generation', {
  state: () => ({
    tasks: new Map<string, Task>(),
    globalTasks: [] as any[],
    globalPollingTimer: null as number | null,
    activeTaskId: null as string | null,
    taskProgress: {} as Record<string, TaskProgressState>,
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
    wsInitialized: false,
    observedCourseId: '' as string,
    previewHydrationPending: new Set<string>(),
    lastGenerationPreviewRefreshAt: 0,
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
      if (this.wsInitialized) {
        useTaskWebSocket().connect()
        return
      }
      this.wsInitialized = true
      const ws = useTaskWebSocket({
        onMessage: (message: WSMessage) => {
          this.handleWSMessage(message)
        },
        onStateChange: (state: ConnectionState) => {
          this.wsConnectionState = state
          const wasConnected = this.wsConnected
          this.wsConnected = state === 'connected'

          if (this.wsConnected) {
            // WebSocket only covers subscribed courses; keep the global list synchronized.
            this.startGlobalMonitor()
            // Re-subscribe to current course if available
            const cs = this._courseStore()
            if (this.observedCourseId) {
              ws.subscribe(this.observedCourseId)
            }
            // Deterministic refresh on reconnect (Req 12.3)
            if (!wasConnected && this.observedCourseId) {
              cs.refreshCourseData(this.observedCourseId)
            }
          } else if (state === 'disconnected' || state === 'error') {
            // WebSocket disconnected → fall back to HTTP polling (Req 1.4)
            this.startGlobalMonitor()
          }
        },
      })
      ws.connect()
    },

    observeCourse(courseId: string) {
      const ws = useTaskWebSocket()
      if (this.observedCourseId && this.observedCourseId !== courseId) {
        ws.unsubscribe(this.observedCourseId)
      }
      this.observedCourseId = courseId
      this.initWebSocket()
      ws.subscribe(courseId)
      this.startGlobalMonitor()
    },

    unobserveCourse(courseId: string) {
      if (!courseId || this.observedCourseId !== courseId) return
      useTaskWebSocket().unsubscribe(courseId)
      this.observedCourseId = ''
    },

    handleWSMessage(message: WSMessage) {
      switch (message.type) {
        case 'progress_update':
          this.handleWSProgressUpdate(message)
          break
        case 'node_completed':
          this.handleWSNodeCompleted(message)
          break
        case 'node_finalized':
          this.handleWSNodeFinalized(message)
          break
        case 'stream_chunk':
          this.handleWSStreamChunk(message)
          break
        case 'task_completed':
          this.handleWSProgressUpdate(message)
          void this.reconcilePublishedCourses([message.course_id]).catch((error) => {
            console.error('Failed to reconcile published course', error)
          })
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
        else if (status === 'error' || status === 'failed') localTask.status = 'error'
        else if (status === 'pending') localTask.status = 'pending'
        else if (status === 'waiting_for_review') localTask.status = 'waiting_for_review'
        else if (status === 'completed_with_warnings') localTask.status = 'completed_with_warnings'
        else if (status === 'conflict') localTask.status = 'conflict'

        localTask.progress = (payload.progress as number) ?? localTask.progress
        if (task_id) localTask.id = task_id
        const phase = String(payload.current_phase || payload.phase || '')
        if (phase) {
          localTask.currentPhase = phaseLabel(phase)
          localTask.phaseProgress = (payload.phase_progress as number) ?? localTask.progress
          localTask.phaseDetail = (payload.phase_detail as Record<string, unknown>) || {}
        }
        const backendMessage = payload.message as string | undefined
        const currentNodeName = payload.current_node_name as string | undefined
        if (currentNodeName) {
          localTask.currentStep = `正在生成: ${currentNodeName}`
        } else if (backendMessage) {
          localTask.currentStep = backendMessage
        } else if (status === 'pending') {
          localTask.currentStep = '等待中...'
        }
        if (payload.current_nodes) {
          localTask.currentNodes = payload.current_nodes as Task['currentNodes']
        }
        if (typeof payload.publication_allowed === 'boolean') {
          localTask.publicationAllowed = payload.publication_allowed
        }
        if (payload.quality_status) localTask.qualityStatus = String(payload.quality_status)
      }
      this.taskProgress[course_id] = projectTaskProgress(this.taskProgress[course_id], {
        percentage: (payload.progress as number) ?? 0,
        currentNodeName: (payload.current_node_name as string) ?? '',
        completedNodes: (payload.completed_nodes as number) ?? 0,
        totalNodes: (payload.total_nodes as number) ?? 0,
        bytesGenerated: (payload.bytes_generated as number) ?? this.taskProgress[course_id]?.bytesGenerated ?? 0,
      })
      if (localTask) {
        this.syncCurrentCourseGenerationState(
          course_id,
          localTask.status,
          localTask.progress,
          localTask.currentStep,
        )
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

    handleWSNodeFinalized(message: WSMessage) {
      const { course_id, payload } = message
      const cs = this._courseStore()
      if (course_id !== cs.currentCourseId || !payload.node_id) return

      const nodeId = payload.node_id as string
      const node = cs.nodes.find((n: Node) => n.node_id === nodeId)
      if (node && payload.node_content !== undefined) {
        node.node_content = payload.node_content as string
        node.generation_status = 'completed'
        node.generated_chars = (payload.generated_chars as number) ?? node.generated_chars
      }
      delete this.streamingContent[nodeId]
    },

    handleWSStreamChunk(message: WSMessage) {
      const { course_id, payload } = message
      const nodeId = payload.node_id as string
      const chunk = payload.chunk as string
      if (!nodeId || !chunk) return

      this.streamingContent[nodeId] = (this.streamingContent[nodeId] || '') + chunk

      const cs = this._courseStore()
      if (course_id === cs.currentCourseId) {
        const node = cs.nodes.find((item: Node) => item.node_id === nodeId)
        if (!node) {
          if (!this.previewHydrationPending.has(nodeId)) {
            this.previewHydrationPending.add(nodeId)
            void cs.refreshGenerationPreview(course_id).then(() => {
              const hydratedNode = cs.nodes.find((item: Node) => item.node_id === nodeId)
              if (!hydratedNode) return
              hydratedNode.node_content = mergeStreamDelta(
                hydratedNode.node_content || '',
                this.streamingContent[nodeId] || '',
              )
              hydratedNode.generation_status = 'generating'
              this.currentGeneratingNode = `正在生成: ${hydratedNode.node_name}`
            }).finally(() => this.previewHydrationPending.delete(nodeId))
          }
          return
        }
        if (this.currentGeneratingNodeId !== nodeId) {
          this.currentGeneratingNodeId = nodeId
          this.currentGeneratingNode = `正在生成: ${node.node_name}`
          node.generation_status = 'generating'
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
      const sent = ws.sendCommand({
        type: 'custom_instruction',
        course_id: courseId,
        node_id: nodeId,
        payload: { instruction },
      })
      if (!sent) {
        try {
          await http.post(`/api/courses/${courseId}/nodes/${nodeId}/instruction`, { instruction })
        } catch (e) {
          console.error('Failed to set custom instruction', e)
          ElMessage.error('设置自定义指令失败')
          throw e
        }
      }
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

    syncCurrentCourseGenerationState(
      courseId: string,
      status: Task['status'],
      progress: number,
      currentStep = '',
    ) {
      const cs = this._courseStore()
      if (cs.currentCourseId !== courseId) return
      const active = status === 'pending' || status === 'running'
      this.isGenerating = active
      this.generationStatus = active
        ? 'generating'
        : status === 'paused'
          ? 'paused'
          : status === 'error'
            ? 'error'
            : 'idle'
      this.generationProgress = progress
      this.currentGeneratingNode = active && currentStep ? currentStep : null
    },

    async reconcilePublishedCourses(courseIds: Iterable<string>) {
      const publishedCourseIds = new Set(courseIds)
      if (!publishedCourseIds.size) return
      const cs = this._courseStore()
      const refreshes: Promise<unknown>[] = [cs.fetchCourseList()]
      if (cs.currentCourseId && publishedCourseIds.has(cs.currentCourseId)) {
        refreshes.push(cs.refreshCourseData(cs.currentCourseId))
      }
      await Promise.all(refreshes)
    },

    createTask(taskId: string, courseId: string, courseName: string, options: CourseGenerationOptions = {}): Task {
      const task: Task = {
        id: taskId, courseId, courseName, status: 'pending', progress: 0, currentStep: '等待调度',
        currentPhase: phaseLabel('queued'), phaseProgress: 0,
        phaseDetail: {},
        logs: [], shouldStop: false,
        difficulty: options.difficulty,
        style: options.style,
        requirements: options.requirements,
      }
      this.tasks.set(courseId, task)
      return task
    },

    getTask(courseId: string) { return this.tasks.get(courseId) },

    async ensureJobId(courseId: string) {
      let task = this.tasks.get(courseId)
      if (task?.id) return task.id
      const res = await http.get(`/api/courses/${courseId}/task`)
      if (!res.data?.id) return null
      if (!task) {
        const cs = this._courseStore()
        const course = cs.courseList.find((c: any) => c.course_id === courseId)
        task = this.createTask(res.data.id, courseId, course?.course_name || '后台生成任务')
      }
      task.id = res.data.id
      task.status = res.data.status || task.status
      task.progress = res.data.progress ?? task.progress
      task.recovery = res.data.recovery || task.recovery
      return task.id
    },

    async pauseTask(courseId: string) {
      const task = this.tasks.get(courseId)
      try {
        const taskId = await this.ensureJobId(courseId)
        if (taskId) await http.post(`/api/tasks/${taskId}/pause`)
      } catch (e) {
        console.error('Failed to pause task', e)
        ElMessage.error('暂停任务失败')
        throw e
      }
      const current = this.tasks.get(courseId) || task
      if (!current) return
      current.status = 'paused'
      current.shouldStop = true
      this.addLogToTask(courseId, '⏸️ 任务已暂停')
      this.persistGenerationState()
    },

    async resumeTask(courseId: string) {
      try {
        const taskId = await this.ensureJobId(courseId)
        if (taskId) {
          const response = await http.post(`/api/tasks/${taskId}/resume`)
          const current = this.tasks.get(courseId)
          if (current) {
            const backendTask = response.data?.task || {}
            current.status = backendTask.status === 'running' ? 'running' : 'pending'
            current.progress = backendTask.progress ?? current.progress
            current.currentStep = backendTask.message || current.currentStep
            current.recovery = backendTask.recovery || current.recovery
            current.shouldStop = false
            this.addLogToTask(courseId, t('courseTasks.recovery.resumedLog', '已从保存点继续'))
            this.persistGenerationState()
          }
          if (this.wsConnected) useTaskWebSocket().subscribe(courseId)
          else this.startGlobalMonitor()
          return
        }
      } catch (e) {
        console.error('Failed to resume task', e)
        ElMessage.error('继续任务失败')
        throw e
      }
    },

    async repairQuality(courseId: string) {
      const taskId = await this.ensureJobId(courseId)
      if (!taskId) return
      try {
        const response = await http.post(`/api/tasks/${taskId}/repair-quality`)
        const current = this.tasks.get(courseId)
        const task = response.data?.task || {}
        if (current) {
          current.status = 'running'
          current.currentPhase = task.phase || 'asset_repair'
          current.currentStep = task.message || '正在补齐缺失学习资产'
          current.shouldStop = false
          this.persistGenerationState()
        }
        this.startGlobalMonitor()
      } catch (error) {
        console.error('Failed to repair quality', error)
        ElMessage.error('自动补齐未能启动')
        throw error
      }
    },

    async startTask(courseId: string) {
      const task = this.tasks.get(courseId)
      if (task?.status === 'paused') await this.resumeTask(courseId)
      else if (task?.status === 'pending' || task?.status === 'running') return
    },

    async cancelTask(courseId: string) {
      const task = this.tasks.get(courseId)
      if (task) {
        try {
          const taskId = await this.ensureJobId(courseId)
          if (taskId) await http.delete(`/api/tasks/${taskId}`)
        } catch (e: any) {
          if (e?.response?.status !== 404) {
            console.error('Failed to cancel task', e)
            ElMessage.error('取消任务失败')
            throw e
          }
        }
        this.dropLocalTaskState(courseId)
        this.persistGenerationState()
        await this._courseStore().fetchCourseList()
      }
    },

    dropLocalTaskState(courseId: string) {
      const cs = this._courseStore()
      this.tasks.delete(courseId)
      delete this.taskProgress[courseId]
      if (cs.currentCourseId !== courseId) return
      this.isGenerating = false
      this.generationStatus = 'idle'
      this.generationProgress = 0
      this.currentGeneratingNode = null
      this.currentGeneratingNodeId = null
    },

    async reconcileMissingLocalTasks(listedTasks: any[]) {
      const listedTaskIds = new Set(
        listedTasks.map(task => String(task?.id || '')).filter(Boolean),
      )
      const missingTasks = Array.from(this.tasks.values()).filter(task => (
        Boolean(task.id)
        && SERVER_BACKED_TASK_STATUSES.has(task.status)
        && !listedTaskIds.has(task.id)
      ))
      if (!missingTasks.length) return [] as any[]

      const recoveredTasks: any[] = []
      const staleCourseIds: string[] = []
      await Promise.all(missingTasks.map(async task => {
        try {
          const response = await http.get(`/api/tasks/${encodeURIComponent(task.id)}`, { silentError: true })
          if (response.data?.id) recoveredTasks.push(response.data)
        } catch (error: any) {
          if (error?.response?.status === 404) staleCourseIds.push(task.courseId)
        }
      }))

      if (staleCourseIds.length) {
        staleCourseIds.forEach(courseId => this.dropLocalTaskState(courseId))
        this.persistGenerationState()
        await this._courseStore().fetchCourseList()
        ElMessage.warning(t(
          'courseTasks.staleStateCleared',
          '已清理失效的本地生成状态；后端没有对应任务，请重新创建课程。',
        ))
      }
      return recoveredTasks
    },

    async clearFailedTasks() {
      try {
        const res = await http.delete('/api/tasks/failed')
        await this.fetchGlobalTasks()
        ElMessage.success(`已清理 ${res.data?.removed ?? 0} 个失败任务`)
      } catch (e) {
        console.error('Failed to clear failed tasks', e)
        ElMessage.error('清理失败任务失败')
        throw e
      }
    },

    persistGenerationState() {
      try {
        const tasks = Array.from(this.tasks.values()).map(task => ({
          id: task.id, courseId: task.courseId, courseName: task.courseName, status: task.status,
          progress: task.progress, currentStep: task.currentStep,
          currentPhase: task.currentPhase, phaseProgress: task.phaseProgress, phaseDetail: task.phaseDetail,
          difficulty: task.difficulty, style: task.style, requirements: task.requirements,
          recovery: task.recovery,
          publicationAllowed: task.publicationAllowed,
          qualityStatus: task.qualityStatus,
          shouldStop: false,
        }))
        const cs = this._courseStore()
        const data = { version: 3, currentCourseId: cs.currentCourseId, tasks }
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
          data.tasks.forEach((rawTask: any) => {
            const courseId = rawTask.courseId || rawTask.id
            const taskId = rawTask.backendTaskId || rawTask.id
            tasks.set(courseId, {
              ...rawTask,
              id: taskId,
              courseId,
              logs: [],
              shouldStop: false,
            })
          })
        }
        this.tasks = tasks
        const cs = this._courseStore()
        cs.currentCourseId = ''
        this.stateRestored = true
        return null
      } catch (e) { console.error(e); return null }
    },

    async fetchGlobalTasks() {
      try {
        const res = await http.get('/api/tasks?limit=100', { silentError: true })
        const listedTasks = Array.isArray(res.data) ? res.data : []
        const recoveredTasks = await this.reconcileMissingLocalTasks(listedTasks)
        this.globalTasks = [...listedTasks, ...recoveredTasks]
        const publishedCourseIds = new Set<string>()
        const discoveredCourseIds = new Set<string>()
        this.globalTasks.forEach((backendTask: any) => {
          const courseId = backendTask.course_id
          let localTask = this.tasks.get(courseId)
          if (!localTask && ['pending', 'running', 'paused', 'error', 'failed', 'waiting_for_review', 'completed_with_warnings', 'conflict'].includes(backendTask.status)) {
            localTask = this.createTask(backendTask.id, courseId, backendTask.course_name || '后台生成任务')
            discoveredCourseIds.add(courseId)
          }
          if (localTask) {
            const prevStatus = localTask.status
            if (backendTask.status === 'running') localTask.status = 'running'
            else if (backendTask.status === 'paused') localTask.status = 'paused'
            else if (backendTask.status === 'completed') localTask.status = 'completed'
            else if (backendTask.status === 'error' || backendTask.status === 'failed') localTask.status = 'error'
            else if (backendTask.status === 'pending') localTask.status = 'pending'
            else if (backendTask.status === 'waiting_for_review') localTask.status = 'waiting_for_review'
            else if (backendTask.status === 'completed_with_warnings') localTask.status = 'completed_with_warnings'
            else if (backendTask.status === 'conflict') localTask.status = 'conflict'
            localTask.progress = backendTask.progress
            localTask.id = backendTask.id
            localTask.recovery = backendTask.recovery || undefined
            if (typeof backendTask.publication_allowed === 'boolean') {
              localTask.publicationAllowed = backendTask.publication_allowed
            }
            if (backendTask.quality_status) localTask.qualityStatus = String(backendTask.quality_status)
            const phase = backendTask.current_phase || backendTask.phase
            if (phase) {
              localTask.currentPhase = phaseLabel(phase)
              localTask.phaseProgress = backendTask.phase_progress ?? backendTask.progress
              localTask.phaseDetail = backendTask.phase_detail || {}
            }
            if (backendTask.message) localTask.currentStep = backendTask.message
            if (backendTask.current_node_name) {
              localTask.currentStep = `正在生成: ${backendTask.current_node_name}`
            }
            this.syncCurrentCourseGenerationState(
              courseId,
              localTask.status,
              localTask.progress,
              localTask.currentStep,
            )

            // Sync taskProgress for UI (progress bar, node count, ETA)
            const completedNodes = backendTask.completed_nodes ?? 0
            const totalNodes = backendTask.total_nodes ?? 0
            const prev = this.taskProgress[courseId]
            this.taskProgress[courseId] = projectTaskProgress(prev, {
              percentage: backendTask.progress ?? 0,
              currentNodeName: backendTask.current_node_name ?? '',
              completedNodes,
              totalNodes,
              bytesGenerated: prev?.bytesGenerated ?? 0,
            })

            // Deterministic refresh: only when task transitions to completed (Req 12.1, 12.3)
            if (
              prevStatus !== 'completed'
              && prevStatus !== 'completed_with_warnings'
              && isPublishedTask(localTask, backendTask)
            ) {
              publishedCourseIds.add(courseId)
            }
          }
        })
        if (publishedCourseIds.size) {
          await this.reconcilePublishedCourses(publishedCourseIds)
        } else if (discoveredCourseIds.size) {
          await this._courseStore().fetchCourseList()
        }
        const cs = this._courseStore()
        const now = Date.now()
        const currentTask = cs.currentCourseId ? this.tasks.get(cs.currentCourseId) : undefined
        if (
          cs.currentCourseProjection === 'generation_preview'
          && currentTask
          && SERVER_BACKED_TASK_STATUSES.has(currentTask.status)
          && now - this.lastGenerationPreviewRefreshAt >= 5000
        ) {
          this.lastGenerationPreviewRefreshAt = now
          await cs.refreshGenerationPreview(cs.currentCourseId)
        }
      } catch (e) { console.error('Failed to fetch global tasks', e) }
    },

    startGlobalMonitor() {
      if (this.globalPollingTimer) return
      this.fetchGlobalTasks()
      this.globalPollingTimer = window.setInterval(() => { this.fetchGlobalTasks() }, 2000)
    },

    stopGlobalMonitor() {
      if (this.globalPollingTimer) { clearInterval(this.globalPollingTimer); this.globalPollingTimer = null }
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

    async stopGeneration() {
      const cs = this._courseStore()
      if (cs.currentCourseId) { await this.pauseTask(cs.currentCourseId) }
      this.isGenerating = false
      this.generationStatus = 'paused'
      this.typingBuffer.clear()
      if (this.typingInterval) { clearInterval(this.typingInterval); this.typingInterval = null }
      ElMessage.info('生成已暂停')
      this.persistGenerationState()
    },

    async startSmartGeneration(subject: string, options: CourseGenerationOptions = {}) {
      // Block generation in outline edit mode (Req 6.2)
      if (this.isOutlineEditMode) {
        ElMessage.warning('请先确认大纲后再启动生成任务')
        return null
      }
      const cs = this._courseStore()
      cs.loading = true
      this.isGenerating = true
      this.generationStatus = 'generating'
      this.generationProgress = 0
      this.generationLogs = []
      this.addLog(`已提交课程生成: ${subject}`)
      try {
        const res = await http.post(`/api/course-generation/generate`, { subject, ...options })
        if (res.data?.job_id && res.data?.course_id) {
          const jobId = res.data.job_id
          const courseId = res.data.course_id
          const courseName = res.data.course_name || subject
          const task = this.createTask(jobId, courseId, courseName, options)
          task.status = res.data.status || 'pending'
          task.currentPhase = phaseLabel(res.data.phase || 'queued')
          cs.currentCourseId = courseId
          cs.currentPedagogyProfile = null
          cs.currentGenerationQualityReport = null
          cs.nodes = []
          cs.courseTree = []
          await cs.fetchCourseList()
          this.taskProgress[courseId] = {
            percentage: 0,
            currentNodeName: '',
            completedNodes: 0,
            totalNodes: 0,
            estimatedTimeRemaining: 0,
            bytesGenerated: 0,
            updatedAt: new Date(),
            etaSampleCount: 0,
            secondsPerNode: 0,
          }
          this.persistGenerationState()
          if (this.wsConnected) useTaskWebSocket().subscribe(courseId)
          else this.startGlobalMonitor()
          return { jobId, courseId, courseName }
        }
        return null
      } catch (error) {
        this.addLog(`❌ 生成失败: ${error}`)
        ElMessage.error('生成失败')
        this.isGenerating = false
        this.generationStatus = 'error'
        this.persistGenerationState()
        return null
      } finally { cs.loading = false }
    },

    async generateCourse(subject: string, options: CourseGenerationOptions = {}) {
      return this.startSmartGeneration(subject, options)
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
        const style = (task?.style as TeachingStyle) || TEACHING_STYLES.ACADEMIC
        const requirement = t(
          'courseGeneration.regeneration.defaultRequirement',
          '重新生成当前节点，保持原课程的难度契约和教学结构'
        )
        const response = await fetch(withApiBase(`/api/courses/${cs.currentCourseId}/nodes/${nodeId}/redefine_stream`), {
          method: 'POST',
          headers: learnerIdentityHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            node_id: node.node_id, node_name: node.node_name,
            original_content: node.node_content || '',
            user_requirement: requirement, course_context: courseContext,
            previous_context: previousContext, style: style
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
