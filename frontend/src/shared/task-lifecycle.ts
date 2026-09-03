import type { Task } from '@/stores/types'

export const TASK_STATUSES = [
  'idle',
  'pending',
  'running',
  'paused',
  'waiting_for_input',
  'waiting_for_review',
  'conflict',
  'error',
  'completed_with_warnings',
  'completed',
] as const satisfies readonly Task['status'][]

const TASK_STATUS_SET = new Set<string>(TASK_STATUSES)
const TASK_STATUS_ORDER: Record<Task['status'], number> = {
  idle: 0,
  pending: 10,
  running: 20,
  paused: 30,
  waiting_for_input: 30,
  waiting_for_review: 30,
  conflict: 40,
  error: 40,
  completed_with_warnings: 50,
  completed: 60,
}

export function normalizeTaskStatus(
  status: unknown,
  fallback: Task['status'] = 'pending',
): Task['status'] {
  const value = String(status || '')
  if (value === 'failed' || value === 'cancelled') return 'error'
  return TASK_STATUS_SET.has(value) ? value as Task['status'] : fallback
}

type TaskSnapshot = {
  status?: unknown
  updatedAt?: unknown
  updated_at?: unknown
  created_at?: unknown
}

const taskSnapshotTimestamp = (task: TaskSnapshot) => (
  Date.parse(String(task.updatedAt || task.updated_at || task.created_at || '')) || 0
)

export function shouldApplyTaskSnapshot(
  current: TaskSnapshot,
  incoming: TaskSnapshot,
): boolean {
  const currentTimestamp = taskSnapshotTimestamp(current)
  const incomingTimestamp = taskSnapshotTimestamp(incoming)
  if (currentTimestamp && incomingTimestamp && incomingTimestamp !== currentTimestamp) {
    return incomingTimestamp > currentTimestamp
  }
  const currentStatus = normalizeTaskStatus(current.status, 'idle')
  const incomingStatus = normalizeTaskStatus(incoming.status, currentStatus)
  return TASK_STATUS_ORDER[incomingStatus] >= TASK_STATUS_ORDER[currentStatus]
}
