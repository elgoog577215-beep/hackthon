export interface LearningTrajectoryArea {
  nodeId: string
  name: string
  wrongCount?: number
  accuracy?: number
  quizScore?: number
  reason?: string
}

export interface LearningTrajectoryStats {
  source: 'LearningOSSnapshot' | 'local'
  available: boolean
  totalNodes: number
  completedCount: number
  completionRate: number
  quizzesTaken: number
  averageQuizScore: number
  weakAreas: LearningTrajectoryArea[]
  strengthAreas: LearningTrajectoryArea[]
  review: Record<string, any>
}

export function buildLearningTrajectoryStats(input: {
  learningState?: any
  courseNodes?: any[]
  completedNodeIds?: string[]
  wrongAnswers?: any[]
  quizHistory?: any[]
}): LearningTrajectoryStats {
  const payload = input.learningState || {}
  const trajectory = payload.snapshot?.trajectory || {}
  const courseNodes = Array.isArray(input.courseNodes) ? input.courseNodes : []
  const courseNodeIds = new Set(courseNodes.map(node => String(node.node_id || node.nodeId || '')).filter(Boolean))
  const completedNodeIds = (input.completedNodeIds || []).filter(id => !courseNodeIds.size || courseNodeIds.has(String(id)))
  const wrongAnswers = normalList(input.wrongAnswers, []).filter(item => !courseNodeIds.size || courseNodeIds.has(String(item.nodeId || item.node_id || '')))
  const quizHistory = normalList(input.quizHistory, []).filter(item => !courseNodeIds.size || courseNodeIds.has(String(item.nodeId || item.node_id || '')))

  const localTotalNodes = courseNodes.length
  const localCompletedCount = completedNodeIds.length
  const localCompletionRate = localTotalNodes > 0 ? Math.round((localCompletedCount / localTotalNodes) * 100) : 0
  const localTotalQuestions = quizHistory.reduce((sum, item) => sum + Number(item.totalQuestions || item.total_questions || 0), 0)
  const localTotalCorrect = quizHistory.reduce((sum, item) => sum + Number(item.correctCount || item.correct_count || 0), 0)
  const localAccuracy = localTotalQuestions > 0 ? Math.round((localTotalCorrect / localTotalQuestions) * 100) : 0
  const localWeakAreas = buildLocalWeakAreas(wrongAnswers)
  const localStrengthAreas = buildLocalStrengthAreas(quizHistory)
  const hasSnapshotTrajectory = trajectory.available === true

  const totalNodes = hasSnapshotTrajectory
    ? normalizedNumber(trajectory.total_nodes, localTotalNodes)
    : localTotalNodes
  const completedCount = hasSnapshotTrajectory
    ? normalizedNumber(trajectory.completed_nodes, localCompletedCount)
    : localCompletedCount
  const completionRate = hasSnapshotTrajectory
    ? Math.round(clamp(normalizedNumber(trajectory.completion_percentage, localCompletionRate), 0, 100))
    : localCompletionRate
  const quizzesTaken = hasSnapshotTrajectory
    ? normalizedNumber(trajectory.quizzes_taken, quizHistory.length)
    : quizHistory.length
  const averageQuizScore = hasSnapshotTrajectory
    ? Math.round(clamp(normalizedNumber(trajectory.average_quiz_score, localAccuracy), 0, 100))
    : localAccuracy

  return {
    source: hasSnapshotTrajectory ? 'LearningOSSnapshot' : 'local',
    available: hasSnapshotTrajectory || localTotalNodes > 0 || quizHistory.length > 0 || wrongAnswers.length > 0,
    totalNodes,
    completedCount,
    completionRate,
    quizzesTaken,
    averageQuizScore,
    weakAreas: hasSnapshotTrajectory
      ? normalizeTrajectoryAreas(trajectory.weak_nodes, localWeakAreas, 'weak')
      : localWeakAreas,
    strengthAreas: hasSnapshotTrajectory
      ? normalizeTrajectoryAreas(trajectory.strong_nodes, localStrengthAreas, 'strong')
      : localStrengthAreas,
    review: hasSnapshotTrajectory && trajectory.review ? trajectory.review : {},
  }
}

function normalizedNumber(value: unknown, fallback: number): number {
  if (value === null || value === undefined || value === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function optionalNumber(value: unknown): number | undefined {
  if (value === null || value === undefined || value === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function buildLocalWeakAreas(wrongAnswers: any[]): LearningTrajectoryArea[] {
  const counts = new Map<string, { name: string; count: number }>()
  wrongAnswers.forEach(item => {
    const nodeId = String(item.nodeId || item.node_id || '')
    if (!nodeId) return
    const current = counts.get(nodeId)
    if (current) {
      current.count += 1
    } else {
      counts.set(nodeId, {
        name: String(item.nodeName || item.node_name || '未知章节'),
        count: 1,
      })
    }
  })

  return Array.from(counts.entries())
    .map(([nodeId, data]) => ({
      nodeId,
      name: data.name,
      wrongCount: data.count,
      reason: '本地错题记录较多',
    }))
    .sort((a, b) => (b.wrongCount || 0) - (a.wrongCount || 0))
    .slice(0, 5)
}

function buildLocalStrengthAreas(quizHistory: any[]): LearningTrajectoryArea[] {
  const scores = new Map<string, { name: string; correct: number; total: number }>()
  quizHistory.forEach(item => {
    const nodeId = String(item.nodeId || item.node_id || '')
    if (!nodeId) return
    const current = scores.get(nodeId)
    if (current) {
      current.correct += Number(item.correctCount || item.correct_count || 0)
      current.total += Number(item.totalQuestions || item.total_questions || 0)
    } else {
      scores.set(nodeId, {
        name: String(item.nodeName || item.node_name || '未知章节'),
        correct: Number(item.correctCount || item.correct_count || 0),
        total: Number(item.totalQuestions || item.total_questions || 0),
      })
    }
  })

  return Array.from(scores.entries())
    .map(([nodeId, data]) => ({
      nodeId,
      name: data.name,
      accuracy: data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0,
      reason: '本地测验记录表现较好',
    }))
    .filter(item => (item.accuracy || 0) >= 80)
    .sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0))
    .slice(0, 5)
}

function normalizeTrajectoryAreas(primary: any, fallback: LearningTrajectoryArea[], prefix: string): LearningTrajectoryArea[] {
  const areas = normalList(primary, []).map((item, index) => ({
    nodeId: String(item.node_id || item.nodeId || `${prefix}-${index}`),
    name: String(item.node_name || item.nodeName || item.name || '未知章节'),
    wrongCount: optionalNumber(item.wrong_count || item.wrongCount),
    accuracy: optionalNumber(item.accuracy),
    quizScore: optionalNumber(item.quiz_score || item.quizScore),
    reason: String(item.reason || ''),
  }))
  return areas.length > 0 ? areas.slice(0, 5) : fallback
}

function normalList(primary: any, fallback: any[] | undefined): any[] {
  if (Array.isArray(primary) && primary.length > 0) return primary
  return Array.isArray(fallback) ? fallback : []
}
