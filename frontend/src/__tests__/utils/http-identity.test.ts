import { AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import {
  applyLearnerIdentity,
  getLearnerIdentity,
  getSurfaceIdentity,
  getTeacherIdentity,
  isTeacherSurfaceLocation,
  learnerIdentityHeaders,
  LEARNER_ID_STORAGE_KEY,
  LOCAL_TEACHER_USER_ID,
  surfaceIdentityHeaders,
  teacherIdentityHeaders,
} from '@/utils/http'

const requestConfig = () => ({ headers: new AxiosHeaders() }) as InternalAxiosRequestConfig

describe('learner identity request header', () => {
  it('显式配置时为全部 API 请求附加隔离用户', () => {
    const config = applyLearnerIdentity(requestConfig(), ' acceptance-ui-user ')

    expect(config.headers.get('X-User-Id')).toBe('acceptance-ui-user')
  })

  it('显式传入空值时允许受控请求不附加身份', () => {
    const config = applyLearnerIdentity(requestConfig(), '')

    expect(config.headers.has('X-User-Id')).toBe(false)
  })

  it('不覆盖业务域显式指定的教师身份', () => {
    const config = requestConfig()
    config.headers.set('X-User-Id', 'teacher-domain-user')

    applyLearnerIdentity(config, 'learner-should-not-win')

    expect(config.headers.get('X-User-Id')).toBe('teacher-domain-user')
  })

  it('原生 fetch 与 Axios 使用同一身份头', () => {
    const headers = learnerIdentityHeaders({ 'Content-Type': 'application/json' }, 'acceptance-fetch-user')

    expect(headers.get('X-User-Id')).toBe('acceptance-fetch-user')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('默认生成并持久化非共享学习者身份', () => {
    const first = getLearnerIdentity()
    const second = getLearnerIdentity()

    expect(first).toMatch(/^learner_/)
    expect(second).toBe(first)
    expect(localStorage.getItem(LEARNER_ID_STORAGE_KEY)).toBe(first)
    expect(first).not.toBe('default_user')
  })

  it('本地教师工作台跨浏览器使用同一个稳定身份', () => {
    expect(getTeacherIdentity('', true)).toBe(LOCAL_TEACHER_USER_ID)
    expect(getTeacherIdentity(' configured-teacher ', true)).toBe('configured-teacher')
    expect(teacherIdentityHeaders({}, 'teacher-header-user').get('X-User-Id')).toBe('teacher-header-user')
  })

  it('教师首页、课程文件空间和学生视角预览使用教师身份', () => {
    expect(isTeacherSurfaceLocation('/courses', '')).toBe(true)
    expect(isTeacherSurfaceLocation('/course/course-1/workspace/setup', '?lesson=lesson-1')).toBe(true)
    expect(isTeacherSurfaceLocation('/course/course-1/learn/lesson-1', '?teacherPreview=1')).toBe(true)
    expect(getSurfaceIdentity('/course/course-1/workspace/setup', '')).toBe(LOCAL_TEACHER_USER_ID)
    expect(surfaceIdentityHeaders(
      { 'Content-Type': 'application/json' },
      '/course/course-1/workspace/setup',
      '',
    ).get('X-User-Id')).toBe(LOCAL_TEACHER_USER_ID)
  })

  it('普通学生学习界面继续使用独立学习者身份', () => {
    expect(isTeacherSurfaceLocation('/course/course-1/learn/lesson-1', '')).toBe(false)
    expect(getSurfaceIdentity('/course/course-1/learn/lesson-1', '')).toMatch(/^learner_/)
    expect(surfaceIdentityHeaders(
      {},
      '/course/course-1/learn/lesson-1',
      '',
    ).get('X-User-Id')).toMatch(/^learner_/)
  })
})
