import { ref, onMounted, onUnmounted } from 'vue'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'

export interface TaskUpdateMessage {
    type: 'task_update' | 'task_created' | 'task_completed' | 'task_error' | 'task_cancelled' | 'progress_update' | 'node_completed' | 'queue_update'
    payload: {
        taskId?: string
        courseId?: string
        status?: string
        progress?: number
        currentNodeName?: string
        completedNodes?: number
        totalNodes?: number
        estimatedTimeRemaining?: number
        bytesGenerated?: number
        message?: string
        error?: string
        nodes?: any[]
        queue?: any[]
    }
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

const WS_RECONNECT_DELAY = 3000
const WS_MAX_RECONNECT_ATTEMPTS = 5
const WS_HEARTBEAT_INTERVAL = 30000

let wsInstance: WebSocket | null = null
let reconnectAttempts = 0
let heartbeatTimer: number | null = null
let reconnectTimer: number | null = null

export function useTaskWebSocket() {
    const courseStore = useCourseStore()
    const genStore = useGenerationStore()
    const connectionStatus = ref<ConnectionStatus>('disconnected')
    const lastMessageTime = ref<Date | null>(null)

    const getWsUrl = (): string => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = import.meta.env.VITE_API_BASE_URL 
            ? import.meta.env.VITE_API_BASE_URL.replace(/^https?:\/\//, '').replace(/\/$/, '')
            : window.location.host
        return `${protocol}//${host}/ws/tasks`
    }

    const connect = () => {
        if (wsInstance?.readyState === WebSocket.OPEN) {
            return
        }

        connectionStatus.value = 'connecting'
        const wsUrl = getWsUrl()

        try {
            wsInstance = new WebSocket(wsUrl)

            wsInstance.onopen = () => {
                connectionStatus.value = 'connected'
                reconnectAttempts = 0
                startHeartbeat()
                logger.info('[WebSocket] Connected to task server')
                
                wsInstance?.send(JSON.stringify({
                    type: 'subscribe',
                    payload: { courseId: courseStore.currentCourseId || 'all' }
                }))
            }

            wsInstance.onmessage = (event) => {
                lastMessageTime.value = new Date()
                
                try {
                    const message: TaskUpdateMessage = JSON.parse(event.data)
                    handleMessage(message)
                } catch (e) {
                    logger.error('[WebSocket] Failed to parse message:', e)
                }
            }

            wsInstance.onclose = (event) => {
                connectionStatus.value = 'disconnected'
                stopHeartbeat()
                logger.info('[WebSocket] Connection closed:', event.code, event.reason)
                
                if (reconnectAttempts < WS_MAX_RECONNECT_ATTEMPTS) {
                    scheduleReconnect()
                } else {
                    ElMessage.warning('任务服务器连接断开，请刷新页面重试')
                }
            }

            wsInstance.onerror = (error) => {
                connectionStatus.value = 'error'
                logger.error('[WebSocket] Connection error:', error)
            }
        } catch (error) {
            connectionStatus.value = 'error'
            logger.error('[WebSocket] Failed to create connection:', error)
        }
    }

    const disconnect = () => {
        stopHeartbeat()
        clearReconnectTimer()
        
        if (wsInstance) {
            wsInstance.close(1000, 'User disconnect')
            wsInstance = null
        }
        
        connectionStatus.value = 'disconnected'
    }

    const startHeartbeat = () => {
        stopHeartbeat()
        heartbeatTimer = window.setInterval(() => {
            if (wsInstance?.readyState === WebSocket.OPEN) {
                wsInstance.send(JSON.stringify({ type: 'ping' }))
            }
        }, WS_HEARTBEAT_INTERVAL)
    }

    const stopHeartbeat = () => {
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer)
            heartbeatTimer = null
        }
    }

    const scheduleReconnect = () => {
        clearReconnectTimer()
        reconnectAttempts++
        
        const delay = WS_RECONNECT_DELAY * Math.pow(1.5, reconnectAttempts - 1)
        logger.info(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`)
        
        reconnectTimer = window.setTimeout(() => {
            connect()
        }, delay)
    }

    const clearReconnectTimer = () => {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer)
            reconnectTimer = null
        }
    }

    const handleMessage = (message: TaskUpdateMessage) => {
        const { type, payload } = message

        switch (type) {
            case 'task_update':
                handleTaskUpdate(payload)
                break
            case 'task_created':
                handleTaskCreated(payload)
                break
            case 'task_completed':
                handleTaskCompleted(payload)
                break
            case 'task_error':
                handleTaskError(payload)
                break
            case 'task_cancelled':
                handleTaskCancelled(payload)
                break
            case 'progress_update':
                handleProgressUpdate(payload)
                break
            case 'node_completed':
                handleNodeCompleted(payload)
                break
            case 'queue_update':
                handleQueueUpdate(payload)
                break
        }
    }

    const handleTaskUpdate = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        
        const task = genStore.getTask(payload.courseId)
        if (task) {
            if (payload.status) task.status = payload.status as any
            if (payload.progress !== undefined) task.progress = payload.progress
            if (payload.currentNodeName) task.currentStep = payload.currentNodeName
            if (payload.message) task.logs.push(`[${new Date().toLocaleTimeString()}] ${payload.message}`)
        }
    }

    const handleTaskCreated = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        logger.info('[WebSocket] Task created:', payload.courseId)
    }

    const handleTaskCompleted = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        
        const task = genStore.getTask(payload.courseId)
        if (task) {
            task.status = 'completed'
            task.progress = 100
            if (payload.message) task.logs.push(`[${new Date().toLocaleTimeString()}] ✅ ${payload.message}`)
        }
        
        if (payload.nodes) {
            courseStore.nodes = payload.nodes
            courseStore.courseTree = courseStore.buildTree(payload.nodes)
        }
        
        ElMessage.success('课程生成完成！')
    }

    const handleTaskError = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        
        const task = genStore.getTask(payload.courseId)
        if (task) {
            task.status = 'error'
            if (payload.error) task.logs.push(`[${new Date().toLocaleTimeString()}] ❌ 错误: ${payload.error}`)
        }
        
        ElMessage.error(payload.error || '任务执行出错')
    }

    const handleTaskCancelled = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        
        genStore.tasks.delete(payload.courseId)
        genStore.queue = genStore.queue.filter((i: any) => i.courseId !== payload.courseId)
        
        ElMessage.info('任务已取消')
    }

    const handleProgressUpdate = (payload: TaskUpdateMessage['payload']) => {
        if (!payload.courseId) return
        
        const task = genStore.getTask(payload.courseId)
        if (task) {
            if (payload.progress !== undefined) task.progress = payload.progress
            if (payload.currentNodeName) task.currentStep = payload.currentNodeName
            
            genStore.generationProgress = payload.progress || 0
            genStore.currentGeneratingNode = payload.currentNodeName || ''
        }
        
        genStore.taskProgress = {
            ...genStore.taskProgress,
            [payload.courseId]: {
                percentage: payload.progress || 0,
                currentNodeName: payload.currentNodeName || '',
                completedNodes: payload.completedNodes || 0,
                totalNodes: payload.totalNodes || 0,
                estimatedTimeRemaining: payload.estimatedTimeRemaining || 0,
                bytesGenerated: payload.bytesGenerated || 0,
                updatedAt: new Date()
            }
        }
    }

    const handleNodeCompleted = (payload: TaskUpdateMessage['payload']) => {
        if (payload.nodes) {
            courseStore.nodes = payload.nodes
            courseStore.courseTree = courseStore.buildTree(payload.nodes)
        }
    }

    const handleQueueUpdate = (payload: TaskUpdateMessage['payload']) => {
        if (payload.queue) {
            genStore.queue = payload.queue
        }
    }

    const sendCommand = (command: string, payload: any = {}) => {
        if (wsInstance?.readyState !== WebSocket.OPEN) {
            ElMessage.warning('WebSocket 未连接，请稍后重试')
            return false
        }
        
        wsInstance.send(JSON.stringify({
            type: 'command',
            command,
            payload
        }))
        
        return true
    }

    const pauseTask = (courseId: string) => {
        return sendCommand('pause_task', { courseId })
    }

    const resumeTask = (courseId: string) => {
        return sendCommand('resume_task', { courseId })
    }

    const cancelTask = (courseId: string) => {
        return sendCommand('cancel_task', { courseId })
    }

    const retryNode = (courseId: string, nodeId: string) => {
        return sendCommand('retry_node', { courseId, nodeId })
    }

    const setPriority = (courseId: string, priority: 'high' | 'normal' | 'low') => {
        return sendCommand('set_priority', { courseId, priority })
    }

    onMounted(() => {
        connect()
    })

    onUnmounted(() => {
        // Don't disconnect on unmount, keep the connection alive
        // disconnect() should be called explicitly when needed
    })

    return {
        connectionStatus,
        lastMessageTime,
        connect,
        disconnect,
        pauseTask,
        resumeTask,
        cancelTask,
        retryNode,
        setPriority,
        sendCommand
    }
}
