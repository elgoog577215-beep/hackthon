import type { LearningObjectiveProgress } from '../stores/learningProgress'

export type LearningScopeNode = {
  node_id: string
  node_name: string
  node_level?: number
  node_content?: string
}

export type PracticeScope = 'node' | 'final' | 'all'

export function resolveLearningScopeNode(
  selectedNode: LearningScopeNode | null | undefined,
  currentObjective: LearningObjectiveProgress | null | undefined,
  courseNodes: LearningScopeNode[],
): LearningScopeNode | null {
  const selectedIsObjective = selectedNode && selectedNode.node_level !== 1
  if (selectedIsObjective && courseNodes.some(node => node.node_id === selectedNode.node_id)) return selectedNode
  if (!currentObjective?.node_id) return null
  return courseNodes.find(node => node.node_id === currentObjective.node_id) || {
    node_id: currentObjective.node_id,
    node_name: currentObjective.node_name || currentObjective.statement,
  }
}

export function practiceScopeKind(scope: PracticeScope): 'objective' | 'final' | 'course' {
  if (scope === 'final') return 'final'
  if (scope === 'all') return 'course'
  return 'objective'
}

export function isStartableLearningObjective(
  node: LearningScopeNode | null | undefined,
): boolean {
  return node?.node_level === 2 && Boolean(node.node_content?.trim())
}
