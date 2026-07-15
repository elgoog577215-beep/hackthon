import { ref, computed } from 'vue'
import type { Ref } from 'vue'
import type { WSMessage, WSCommand } from '../stores/types'
import { API_BASE, withApiBase } from '../utils/http'

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

let wsInstance: WebSocket | null = null
let reconnectAttempts = 0
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

// Shared reactive state so every consumer sees the same values
const connectionState = ref<ConnectionState>('disconnected')
const isConnected = computed(() => connectionState.value === 'connected')

// Track subscribed courseIds for re-subscribe on reconnect
const subscribedCourseIds = new Set<string>()

// Store the active callbacks for the singleton WebSocket.
const currentOptions: UseTaskWebSocketOptions = {}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function getWsUrl(): string {
  if (/^https?:\/\//.test(API_BASE)) {
    const url = new URL(withApiBase('/ws'))
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.toString()
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${withApiBase('/ws')}`
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
      scheduleReconnect()
    }

    wsInstance.onerror = () => {
      setConnectionState('error')
    }
  } catch {
    setConnectionState('error')
    scheduleReconnect()
  }
}

function disconnect() {
  stopHeartbeat()
  clearReconnectTimer()
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
  if (options.onMessage) currentOptions.onMessage = options.onMessage
  if (options.onStateChange) currentOptions.onStateChange = options.onStateChange

  return {
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    sendCommand,
    isConnected,
    connectionState,
  }
}
