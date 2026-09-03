import { describe, expect, it } from 'vitest'
import {
  teacherLessonPlanIsReady,
  teacherLessonPptAssetIsReady,
  teacherLessonPptIsReady,
  teacherLessonScriptIsReady,
} from '../shared/teacher-asset-readiness'
import type { TeacherLessonProjection } from '../stores/teacherLessonAuthoring'

function lessonWith(overrides: Record<string, unknown> = {}): TeacherLessonProjection {
  return {
    lesson_unit_id: 'lesson-1',
    number: 1,
    title: '第一讲',
    duration_minutes: 45,
    sections: [],
    arrangement: {} as TeacherLessonProjection['arrangement'],
    plan: {
      lesson_unit_id: 'lesson-1',
      working_revision_id: 'plan-1',
      confirmed_revision_id: '',
      source_state: 'current',
      ready: false,
      revisions: [],
      ppt_assets: [],
    },
    script: {
      current_revision_id: 'script-1',
      confirmed_revision_id: '',
      source_lesson_plan_revision_id: 'plan-1',
      source_state: 'current',
      ready: false,
      confirmed: false,
      confirmed_at: '',
      sections: [],
    },
    ...overrides,
  }
}

describe('teacher asset readiness contract', () => {
  it('never treats identifiers as completion without backend readiness', () => {
    const lesson = lessonWith()
    lesson.plan.ppt_assets = [{
      asset_id: 'ppt-1',
      lesson_unit_id: 'lesson-1',
      role: 'primary',
      working_revision_id: 'ppt-revision-1',
      source_lesson_plan_revision_id: 'plan-1',
      source_state: 'current',
      revisions: [],
      ai_candidates: [],
    }]

    expect(teacherLessonPlanIsReady(lesson)).toBe(false)
    expect(teacherLessonScriptIsReady(lesson)).toBe(false)
    expect(teacherLessonPptAssetIsReady(lesson.plan.ppt_assets[0])).toBe(false)
    expect(teacherLessonPptIsReady(lesson)).toBe(false)
  })

  it('uses only explicit ready states across all three asset types', () => {
    const lesson = lessonWith()
    lesson.plan.ready = true
    lesson.script.ready = true
    lesson.plan.ppt_assets = [{
      asset_id: 'ppt-1',
      lesson_unit_id: 'lesson-1',
      role: 'primary',
      working_revision_id: 'ppt-revision-1',
      source_lesson_plan_revision_id: 'plan-1',
      source_state: 'current',
      ready: true,
      revisions: [],
      ai_candidates: [],
    }]

    expect(teacherLessonPlanIsReady(lesson)).toBe(true)
    expect(teacherLessonScriptIsReady(lesson)).toBe(true)
    expect(teacherLessonPptIsReady(lesson)).toBe(true)
  })
})
