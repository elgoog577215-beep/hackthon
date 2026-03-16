<<<<<<< HEAD
import { ref, computed } from 'vue'
import type { Ref } from 'vue'
import type { WSMessage, WSCommand } from '../stores/types'
import http from '../utils/http'
=======
import { ref, onMounted, onUnmounted } from 'vue'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'
>>>>>>> classmate/main

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface UseTaskWebSocketOptions {
  /** Callback invoked for every WSMessage received from the server */
  onMessage?: (message: WSMessage) => void
  /** Callback invoked when connection state changes */
  onStateChange?: (state: ConnectionState) => void
}

export interface UseTaskWebSocketReturn {
  connect: () => void
  disconnect: () => void
  subscribe: (courseId: string) => void
  unsubscribe: (courseId: string) => void
  sendCommand: (command: WSCommand) => boolean
  isConnected: Ref<boolean>
  connectionState: Ref<ConnectionState>
}

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

const WS_RECONNECT_BASE_DELAY = 3000   // 3 seconds
const WS_MAX_RECONNECT_ATTEMPTS = 5
const WS_RECONNECT_FACTOR = 1.5
const WS_HEARTBEAT_INTERVAL = 30000    // 30 seconds
const HTTP_POLL_INTERVAL = 2000        // 2 seconds

let wsInstance: WebSocket | null = null
let reconnectAttempts = 0
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pollingTimer: ReturnType<typeof setInterval> | null = null

// Shared reactive state so every consumer sees the same values
const connectionState = ref<ConnectionState>('disconnected')
const isConnected = computed(() => connectionState.value === 'connected')

// Track subscribed courseIds for re-subscribe on reconnect
const subscribedCourseIds = new Set<string>()

// Store the latest options (callback) – updated each time useTaskWebSocket is called
let currentOptions: UseTaskWebSocketOptions = {}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

<<<<<<< HEAD
function getWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_API_BASE_URL
    ? (import.meta.env.VITE_API_BASE_URL as string).replace(/^https?:\/\//, '').replace(/\/$/, '')
    : window.location.host
  return `${protocol}//${host}/ws`
}

function setConnectionState(state: ConnectionState) {
  connectionState.value = state
  currentOptions.onStateChange?.(state)
}

// ---------------------------------------------------------------------------
// Heartbeat
// ---------------------------------------------------------------------------

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (wsInstance?.readyState === WebSocket.OPEN) {
      wsInstance.send(JSON.stringify({ type: 'ping' }))
    }
  }, WS_HEARTBEAT_INTERVAL)
}

function stopHeartbeat() {
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// ---------------------------------------------------------------------------
// HTTP Polling fallback
// ---------------------------------------------------------------------------

function startPolling() {
  if (pollingTimer !== null) return // already polling
  console.log('[WebSocket] Falling back to HTTP polling')
  pollingTimer = setInterval(async () => {
    try {
      const response = await http.get('/api/tasks', { params: { limit: 100 } })
      // Wrap polling data as a synthetic WSMessage so the caller can handle it uniformly
      if (response.data && currentOptions.onMessage) {
        const tasks = Array.isArray(response.data) ? response.data : [response.data]
        for (const task of tasks) {
          const msg: WSMessage = {
            type: 'progress_update',
            task_id: task.task_id ?? task.id ?? '',
            course_id: task.course_id ?? '',
            payload: task,
          }
          currentOptions.onMessage(msg)
        }
      }
    } catch {
      // Polling errors are non-fatal; just log
      console.warn('[WebSocket] HTTP polling request failed')
    }
  }, HTTP_POLL_INTERVAL)
}

function stopPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer)
    pollingTimer = null
    console.log('[WebSocket] Stopped HTTP polling')
  }
}

// ---------------------------------------------------------------------------
// Reconnect logic (exponential backoff: base 3s, factor 1.5, max 5 attempts)
// ---------------------------------------------------------------------------

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect() {
  clearReconnectTimer()
  reconnectAttempts++

  if (reconnectAttempts > WS_MAX_RECONNECT_ATTEMPTS) {
    console.warn('[WebSocket] Max reconnect attempts reached, staying in polling mode')
    return
  }

  const delay = WS_RECONNECT_BASE_DELAY * Math.pow(WS_RECONNECT_FACTOR, reconnectAttempts - 1)
  console.log(`[WebSocket] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts}/${WS_MAX_RECONNECT_ATTEMPTS})`)

  reconnectTimer = setTimeout(() => {
    connect()
  }, delay)
}

// ---------------------------------------------------------------------------
// Core connect / disconnect
// ---------------------------------------------------------------------------

function connect() {
  if (wsInstance?.readyState === WebSocket.OPEN || wsInstance?.readyState === WebSocket.CONNECTING) {
    return
  }

  setConnectionState('connecting')
  const wsUrl = getWsUrl()

  try {
    wsInstance = new WebSocket(wsUrl)

    wsInstance.onopen = () => {
      setConnectionState('connected')
      reconnectAttempts = 0
      startHeartbeat()
      stopPolling() // reconnected → stop HTTP fallback
      console.log('[WebSocket] Connected')

      // Re-subscribe to all previously subscribed courseIds
      for (const courseId of subscribedCourseIds) {
        sendRaw({ type: 'subscribe', course_id: courseId })
      }
    }

    wsInstance.onmessage = (event: MessageEvent) => {
      try {
        const message: WSMessage = JSON.parse(event.data as string)
        currentOptions.onMessage?.(message)
      } catch {
        // pong or non-JSON frames – ignore
      }
    }

    wsInstance.onclose = (_event: CloseEvent) => {
      setConnectionState('disconnected')
      stopHeartbeat()
      startPolling() // fallback to HTTP polling
      scheduleReconnect()
    }

    wsInstance.onerror = () => {
      setConnectionState('error')
    }
  } catch {
    setConnectionState('error')
    startPolling()
    scheduleReconnect()
  }
}

function disconnect() {
  stopHeartbeat()
  clearReconnectTimer()
  stopPolling()

  if (wsInstance) {
    wsInstance.onclose = null // prevent auto-reconnect on intentional close
    wsInstance.close(1000, 'Client disconnect')
    wsInstance = null
  }

  reconnectAttempts = 0
  subscribedCourseIds.clear()
  setConnectionState('disconnected')
}

// ---------------------------------------------------------------------------
// Subscribe / Unsubscribe
// ---------------------------------------------------------------------------

function subscribe(courseId: string) {
  subscribedCourseIds.add(courseId)
  sendRaw({ type: 'subscribe', course_id: courseId })
}

function unsubscribe(courseId: string) {
  subscribedCourseIds.delete(courseId)
  sendRaw({ type: 'unsubscribe', course_id: courseId })
}

// ---------------------------------------------------------------------------
// Send helpers
// ---------------------------------------------------------------------------

function sendRaw(data: Record<string, unknown>): boolean {
  if (wsInstance?.readyState !== WebSocket.OPEN) {
    return false
  }
  wsInstance.send(JSON.stringify(data))
  return true
}

function sendCommand(command: WSCommand): boolean {
  return sendRaw(command as unknown as Record<string, unknown>)
}

// ---------------------------------------------------------------------------
// Public composable
// ---------------------------------------------------------------------------

export function useTaskWebSocket(options: UseTaskWebSocketOptions = {}): UseTaskWebSocketReturn {
  // Update the module-level callback reference so the singleton WS uses the latest caller's handlers
  currentOptions = options

  return {
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    sendCommand,
    isConnected,
    connectionState,
  }
=======
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
>>>>>>> classmate/main
}
