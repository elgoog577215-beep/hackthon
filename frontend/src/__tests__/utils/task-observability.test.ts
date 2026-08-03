import { describe, expect, it } from 'vitest'
import type { Task } from '@/stores/types'
import {
  OBSERVABLE_TASK_STAGE_KEYS,
  observableTaskStages,
  taskDisplayProgress,
  taskHeartbeatState,
  taskUserError,
} from '@/utils/task-observability'

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'job-1',
    courseId: 'course-1',
    courseName: '线性代数',
    status: 'running',
    progress: 20,
    currentStep: '',
    currentPhase: 'material_processing',
    logs: [],
    shouldStop: false,
    ...overrides,
  }
}

describe('D-05 task observability projection', () => {
  it('稳定公开资料接收、解析、检索、生成、检查和导出六个阶段', () => {
    expect(OBSERVABLE_TASK_STAGE_KEYS).toEqual([
      'receive', 'parse', 'retrieve', 'generate', 'validate', 'export',
    ])

    const stages = observableTaskStages(task())
    expect(stages.map(stage => stage.status)).toEqual([
      'completed', 'active', 'pending', 'pending', 'pending', 'pending',
    ])
  })

  it('把题库联网补充映射为检索，把发布映射为导出', () => {
    expect(observableTaskStages(task({ currentPhase: 'question_bank' }))[2]?.status).toBe('active')
    expect(observableTaskStages(task({ currentPhase: 'release_confirmed' }))[5]?.status).toBe('active')
  })

  it('教案批次的局部校验仍属于内容生成，且历史校验不会覆盖当前活动阶段', () => {
    const stages = observableTaskStages(task({
      currentPhase: 'course_teaching_plan_batch',
      phaseHistory: [
        { phase: 'course_teaching_plan_batch_validation', status: 'completed' },
      ],
    }))
    expect(stages.map(stage => stage.status)).toEqual([
      'completed', 'completed', 'completed', 'active', 'pending', 'pending',
    ])

    const validation = observableTaskStages(task({
      currentPhase: 'course_teaching_plan_batch_validation',
    }))
    expect(validation[3]?.status).toBe('active')
    expect(validation[4]?.status).toBe('pending')
  })

  it('失败任务不会伪装成百分之百完成，并把当前阶段标成错误', () => {
    const failed = task({ status: 'error', progress: 100, currentPhase: 'content_validation' })
    expect(taskDisplayProgress(failed)).toBe(99)
    expect(observableTaskStages(failed)[4]?.status).toBe('error')
  })

  it('根据心跳而非动画判断运行任务可能停滞', () => {
    const now = Date.parse('2026-08-03T10:05:00+08:00')
    expect(taskHeartbeatState(task({ heartbeatAt: '2026-08-03T10:04:30+08:00' }), now).state).toBe('fresh')
    expect(taskHeartbeatState(task({ heartbeatAt: '2026-08-03T10:00:00+08:00' }), now).state).toBe('stalled')
    expect(taskHeartbeatState(task({ status: 'completed', heartbeatAt: '2026-08-03T09:00:00+08:00' }), now).state).toBe('terminal')
  })

  it('将内部错误码转换为可理解原因并保留技术详情', () => {
    const detail = taskUserError(task({
      status: 'error',
      errorCode: 'slide_deck_variant_quality_gate_failed',
      error: 'slide_deck_variant_quality_gate_failed',
    }))
    expect(detail.message).toContain('质量检查未通过')
    expect(detail.technicalDetail).toBe('slide_deck_variant_quality_gate_failed')
  })
})
