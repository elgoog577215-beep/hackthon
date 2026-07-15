import { describe, expect, it } from 'vitest'
import { isResumableLearningAction, latestResumableCourse, resumeKindLabel } from '../../utils/learning-resume'

describe('learning resume presentation', () => {
  it('only promotes explicit resume actions', () => {
    expect(isResumableLearningAction({ action_type: 'resume_practice_attempt' })).toBe(true)
    expect(isResumableLearningAction({ action_type: 'resume_reading' })).toBe(true)
    expect(isResumableLearningAction({ action_type: 'start_objective' })).toBe(false)
    expect(isResumableLearningAction({ action_type: 'start_next_chapter' })).toBe(false)
    expect(isResumableLearningAction({ action_type: 'start_due_review' })).toBe(false)
  })

  it('uses concrete labels for restored work', () => {
    expect(resumeKindLabel('practice')).toBe('继续未完成练习')
    expect(resumeKindLabel('reading')).toBe('继续上次学习')
  })

  it('selects the most recent course with a real resumable node', () => {
    const latest = latestResumableCourse([
      { course_id: 'empty', resume: { activity_at: '2026-07-13T12:00:00Z' } },
      { course_id: 'older', resume: { node_id: 'node-1', activity_at: '2026-07-12T12:00:00Z' } },
      { course_id: 'latest', resume: { node_id: 'node-2', activity_at: '2026-07-13T10:00:00Z' } },
    ])

    expect(latest?.course_id).toBe('latest')
    expect(latestResumableCourse([{ course_id: 'empty' }])).toBeNull()
  })
})
