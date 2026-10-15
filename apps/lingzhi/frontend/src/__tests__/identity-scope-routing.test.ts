import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setStudyIdentity, STUDY_SESSION_KEY } from '@/utils/study-identity'
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
vi.mock('@/views/StudyView.vue', () => ({ default: { render: () => null } }))
const me = vi.hoisted(() => vi.fn())
vi.mock('@/api/study', () => ({ studyApi: { me } }))

describe('explicit route identity scope', () => {
  beforeEach(async () => {
    sessionStorage.clear()
    me.mockReset()
    setActiveRequestIdentityScope('learner')
    await router.replace('/workspace-concept')
  })
  afterEach(() => { sessionStorage.clear() })

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
    expect(router.currentRoute.value.name).toBe('study')
    expect(router.currentRoute.value.query.returnTo).toBe('/course/course-1/learn/node-1')

    await router.push('/course/course-1/learn/node-1?teacherPreview=1')
    expect(getActiveRequestIdentityScope()).toBe('teacher')

  })

  it('verifies the student session before opening formal learning and rejects an expired session', async () => {
    sessionStorage.setItem(STUDY_SESSION_KEY, 'student-session')
    me.mockResolvedValueOnce({ id: 'local-student:a', username: 'student_a', role: 'student' })
    await router.push('/course/course-1/learn/node-1')
    expect(router.currentRoute.value.name).toBe('learning')
    expect(me).toHaveBeenCalledTimes(1)
    me.mockRejectedValueOnce(new Error('expired'))
    await router.push('/course/course-2/learn/node-2')
    expect(router.currentRoute.value.name).toBe('study')
    setStudyIdentity(null)
  })
})
