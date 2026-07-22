import { describe, expect, it } from 'vitest'
import type { Task } from '@/stores/types'
import {
  canResumeCourseProduction,
  courseProductionStageIndex,
  courseProductionStageStatus,
  hasVisibleCourseDraft,
} from '@/utils/course-production'

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'job-1',
    courseId: 'course-1',
    courseName: '量子力学',
    status: 'running',
    progress: 32,
    currentStep: '正在生成课程目录',
    currentPhase: 'pedagogy_resolution',
    logs: [],
    shouldStop: false,
    guidedWorkflow: {
      schema_version: 'guided_course_generation_v2',
      current_step: 'outline',
      review_step: null,
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'in_progress' },
        { number: 3, key: 'content', status: 'locked' },
        { number: 4, key: 'release', status: 'locked' },
      ],
    },
    ...overrides,
  }
}

describe('course production stage projection', () => {
  it('把需求确认后的教学画像和目录准备归入第 2 阶段', () => {
    const current = task()
    expect(courseProductionStageIndex(current)).toBe(1)
    expect(courseProductionStageStatus(current, 0)).toBe('completed')
    expect(courseProductionStageStatus(current, 1)).toBe('active')
  })

  it('失败、暂停与待确认不会继续投影为旋转中的进行态', () => {
    expect(courseProductionStageStatus(task({ status: 'error' }), 1)).toBe('error')
    expect(courseProductionStageStatus(task({ status: 'paused' }), 1)).toBe('paused')
    expect(courseProductionStageStatus(task({ status: 'waiting_for_review' }), 1)).toBe('review')
  })

  it('质量阻断只卡住发布阶段，不把已完成内容伪装成发布成功', () => {
    const blocked = task({
      status: 'completed_with_warnings',
      currentPhase: 'quality_failed',
      publicationAllowed: false,
    })
    expect(courseProductionStageStatus(blocked, 3)).toBe('completed')
    expect(courseProductionStageStatus(blocked, 4)).toBe('blocked')
  })

  it('区分教案、正文与发布阶段', () => {
    expect(courseProductionStageIndex(task({ currentPhase: 'course_teaching_plan_batch' }))).toBe(2)
    expect(courseProductionStageIndex(task({ currentPhase: 'content_generation' }))).toBe(3)
    expect(courseProductionStageIndex(task({ currentPhase: 'release_validation' }))).toBe(4)
  })

  it('只在后端允许时显示恢复，并识别真实正文草稿', () => {
    const resumable = task({
      status: 'error',
      recovery: {
        state: 'manual_resume',
        can_resume: true,
        reason_code: 'stage_restart_available',
        reason: 'saved',
        checkpoint: {
          phase: 'content_generation', completed_nodes: 1, total_nodes: 3,
          draft_node_ids: ['n1'], failed_node_ids: [], interrupted_node_ids: [],
        },
      },
    })
    expect(canResumeCourseProduction(resumable)).toBe(true)
    expect(hasVisibleCourseDraft(resumable, ['', '已保存正文'])).toBe(true)
    expect(hasVisibleCourseDraft(task(), ['', ''])).toBe(false)
  })
})
