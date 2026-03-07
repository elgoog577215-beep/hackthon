/**
 * 共享类型定义
 * 从 course.ts 提取的所有接口和类型，供各拆分后的 Store 共用。
 */

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
