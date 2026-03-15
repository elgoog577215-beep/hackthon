/**
 * 知识图谱类型定义
 */

export type KGNodeType = 'root' | 'concept' | 'theorem' | 'method' | 'application' | 'custom'

export interface KGNode {
  id: string
  label: string
  type: KGNodeType
  description: string
  chapter_id?: string
  x: number
  y: number
  color?: string
  created_by: 'ai' | 'user'
  created_at: number
  updated_at: number
}

export interface KGEdge {
  id: string
  source: string
  target: string
  relation: string
  weight: number
  label?: string
  created_by: 'ai' | 'user'
}

export interface KnowledgeGraphData {
  nodes: KGNode[]
  edges: KGEdge[]
  updated_at: number
}

/** 节点类型元数据 */
export interface KGNodeTypeMeta {
  value: KGNodeType
  label: string
  color: string
}

/** 关系类型元数据 */
export interface KGRelationMeta {
  value: string
  label: string
  color: string
}

export const NODE_TYPES: KGNodeTypeMeta[] = [
  { value: 'root', label: '课程核心', color: '#6366f1' },
  { value: 'concept', label: '核心概念', color: '#0ea5e9' },
  { value: 'theorem', label: '关键定理', color: '#f43f5e' },
  { value: 'method', label: '核心方法', color: '#10b981' },
  { value: 'application', label: '应用场景', color: '#f59e0b' },
  { value: 'custom', label: '自定义', color: '#8b5cf6' },
]

export const RELATION_TYPES: KGRelationMeta[] = [
  { value: 'prerequisite', label: '前置', color: '#f43f5e' },
  { value: 'derives', label: '推导', color: '#6366f1' },
  { value: 'applies_to', label: '应用', color: '#0ea5e9' },
  { value: 'contrasts_with', label: '对比', color: '#10b981' },
  { value: 'extends', label: '扩展', color: '#8b5cf6' },
  { value: 'implements', label: '实现', color: '#6366f1' },
  { value: 'leads_to', label: '引出', color: '#f59e0b' },
  { value: 'contains', label: '包含', color: '#94a3b8' },
  { value: 'related', label: '关联', color: '#94a3b8' },
]

export function getNodeColor(node: KGNode): string {
  if (node.color) return node.color
  return NODE_TYPES.find(t => t.value === node.type)?.color ?? '#8b5cf6'
}

export function getNodeTypeLabel(type: string): string {
  return NODE_TYPES.find(t => t.value === type)?.label ?? type
}

export function getRelationColor(relation: string): string {
  return RELATION_TYPES.find(r => r.value === relation)?.color ?? '#94a3b8'
}

export function getRelationLabel(relation: string): string {
  return RELATION_TYPES.find(r => r.value === relation)?.label ?? relation
}
