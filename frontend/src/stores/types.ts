/**
 * 共享类型定义
 * 从 course.ts 提取的所有接口和类型，供各拆分后的 Store 共用。
 */

export type NodeGenerationStatus = 'pending' | 'generating' | 'completed' | 'error' | 'skipped'

export interface NodeGenerationConfig {
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  style: string
  target_word_range: [number, number]
  include_code_examples: boolean
  include_exercises: boolean
  custom_instruction?: string
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
  // 节点生成状态与配置
  generation_status: NodeGenerationStatus
  generation_config?: NodeGenerationConfig
  generated_chars: number
  error_summary?: string
}

export interface TaskProgress {
  task_id: string
  course_id: string
  status: string
  progress: number
  current_node_name: string
  completed_nodes: number
  total_nodes: number
  estimated_time_remaining: number
}

export interface FailureReport {
  task_id: string
  course_id: string
  failed_nodes: Array<{
    node_id: string
    node_name: string
    error: string
    retry_count: number
  }>
  total_failed: number
}

export interface WSMessage {
  type: 'progress_update' | 'node_completed' | 'stream_chunk' | 'task_completed' | 'task_error' | 'failure_report'
  task_id: string
  course_id: string
  payload: Record<string, unknown>
}

export interface WSCommand {
  type: 'subscribe' | 'unsubscribe' | 'skip_node' | 'retry_node' | 'stop_node' | 'custom_instruction' | 'retry_all_failed'
  course_id: string
  node_id?: string
  payload?: Record<string, unknown>
}

export interface Annotation {
  anno_id: string
  node_id: string
  course_id?: string
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
    summary?: string
    color: string
    createdAt: number
    top?: number
    sourceType?: 'user' | 'ai' | 'format' | 'wrong'
    style?: 'bold' | 'underline' | 'wave' | 'dashed' | 'highlight' | 'solid' | 'wavy'
    title?: string
    expanded?: boolean
    tags?: string[]
    category?: string
    priority?: 'low' | 'medium' | 'high'
}

export interface Course {
    course_id: string
    course_name: string
    node_count: number
}

export interface QueueItem {
    uuid: string
    courseId: string
    type: 'structure' | 'content' | 'subchapter' | 'knowledge_graph'
    targetNodeId: string
    title: string
    status: 'pending' | 'running' | 'completed' | 'error'
    errorMsg?: string
    retryCount?: number
}

export interface Task {
    id: string
    courseName: string
    status: 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'pending'
    progress: number
    currentStep: string
    currentPhase?: string
    phaseProgress?: string
    currentNodes?: Array<{
        node_id?: string
        node_name?: string
        name: string
        action: string
        type: string
    }>
    completedNodes?: number
    totalNodes?: number
    logs: string[]
    nodes: Node[]
    shouldStop: boolean
    difficulty?: string
    style?: string
    requirements?: string
    backendTaskId?: string
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

export interface ChatConversation {
    id: string
    name: string
    messages: ChatMessage[]
    createdAt: number
}
