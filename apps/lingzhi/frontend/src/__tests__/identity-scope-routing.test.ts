import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from '@/router'
import {
  getActiveRequestIdentityScope,
  setActiveRequestIdentityScope,
} from '@/utils/http'

// Identity routing uses the real route metadata and guard, without compiling
// unrelated workbench and PPT views during navigation.
vi.mock('@/views/WorkspacePortalConceptView.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/TeacherTeachingCalendarView.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/CourseWorkspaceView.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/PptWorkspaceView.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/LearningView.vue', () => ({ default: { render: () => null } }))

describe('explicit route identity scope', () => {
  beforeEach(async () => {
    setActiveRequestIdentityScope('learner')
    await router.replace('/workspace-concept')
  })

  it('uses teacher identity for home, workbench and PPT routes', async () => {
    await router.push('/courses')
    expect(getActiveRequestIdentityScope()).toBe('teacher')

    await router.push('/course/course-1/workspace/setup')
    expect(getActiveRequestIdentityScope()).toBe('teacher')

    await router.push('/course/course-1/ppt')
    expect(getActiveRequestIdentityScope()).toBe('teacher')
  })

  it('keeps ordinary learning separate and explicitly elevates teacher preview', async () => {
    await router.push('/course/course-1/learn/node-1')
    expect(getActiveRequestIdentityScope()).toBe('learner')

    await router.push('/course/course-1/learn/node-1?teacherPreview=1')
    expect(getActiveRequestIdentityScope()).toBe('teacher')

  })
})
