import { AxiosHeaders } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import http from '@/utils/http'
import { setStudyIdentity, STUDY_SESSION_KEY } from '@/utils/study-identity'
import type { InternalAxiosRequestConfig } from 'axios'
import {
  applyLearnerIdentity,
  activeIdentityHeaders,
  getActiveRequestIdentity,
  getActiveRequestIdentityScope,
  getIdentityForScope,
  getLearnerIdentity,
  getTeacherIdentity,
  identityScopeHeaders,
  learnerIdentityHeaders,
  LEARNER_ID_STORAGE_KEY,
  LOCAL_TEACHER_USER_ID,
  setActiveRequestIdentityScope,
  teacherIdentityHeaders,
} from '@/utils/http'

const requestConfig = () => ({ headers: new AxiosHeaders() }) as InternalAxiosRequestConfig

describe('learner identity request header', () => {
  afterEach(() => { sessionStorage.removeItem(STUDY_SESSION_KEY); setStudyIdentity(null) })
  it('uses the authenticated student for learning while keeping local student credentials out of teacher requests', async () => {
    const productionTeacher = getTeacherIdentity('', false)
    sessionStorage.setItem(STUDY_SESSION_KEY, 'student-session')
    setStudyIdentity({ id: 'local-student:a', username: 'student_a', role: 'student' })
    expect(learnerIdentityHeaders().get('Authorization')).toBe('Bearer student-session')
    expect(learnerIdentityHeaders().get('X-User-Id')).toBe('local-student:a')
    expect(teacherIdentityHeaders().has('Authorization')).toBe(false)
    expect(getTeacherIdentity('', false)).toBe(productionTeacher)
    expect(getTeacherIdentity('', false)).not.toBe('local-student:a')
    const captured: InternalAxiosRequestConfig[] = []
    const adapter = async (config: InternalAxiosRequestConfig) => {
      captured.push(config)
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    }
    await http.get('/api/courses/course/document', { identityScope: 'learner', adapter })
    await http.get('/api/teacher/courses', { identityScope: 'teacher', adapter })
    expect(captured[0]!.headers.get('Authorization')).toBe('Bearer student-session')
    expect(captured[1]!.headers.has('Authorization')).toBe(false)
    expect(captured[1]!.headers.get('X-User-Id')).toBe(LOCAL_TEACHER_USER_ID)
  })
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

  it('业务域显式选择教师身份，不再从 URL 猜测', () => {
    expect(getIdentityForScope('teacher')).toBe(LOCAL_TEACHER_USER_ID)
    expect(identityScopeHeaders('teacher', {
      'Content-Type': 'application/json',
    }).get('X-User-Id')).toBe(LOCAL_TEACHER_USER_ID)
  })

  it('路由可以切换当前请求身份域，普通学习仍使用独立学习者身份', () => {
    setActiveRequestIdentityScope('learner')
    expect(getActiveRequestIdentityScope()).toBe('learner')
    expect(getActiveRequestIdentity()).toMatch(/^learner_/)
    expect(activeIdentityHeaders().get('X-User-Id')).toMatch(/^learner_/)

    setActiveRequestIdentityScope('teacher')
    expect(getActiveRequestIdentityScope()).toBe('teacher')
    expect(getActiveRequestIdentity()).toBe(LOCAL_TEACHER_USER_ID)
    expect(activeIdentityHeaders().get('X-User-Id')).toBe(LOCAL_TEACHER_USER_ID)
  })

  it('统一登录退出清除两种浏览器令牌，但保留按本人归属的草稿', async () => {
    vi.stubEnv('VITE_QIZHI_AUTH_REQUIRED', 'true')
    vi.resetModules()
    try {
      const auth = await import('@/utils/http')
      localStorage.setItem('auth_token', 'test-local-token')
      sessionStorage.setItem('auth_token', 'test-session-token')
      sessionStorage.setItem('lingzhi-study-draft:student-a', 'private draft')
      expect(auth.getQizhiAccessToken()).toBe('test-local-token')
      auth.clearQizhiAccessToken()
      expect(auth.getQizhiAccessToken()).toBe('')
      expect(sessionStorage.getItem('auth_token')).toBeNull()
      expect(sessionStorage.getItem('lingzhi-study-draft:student-a')).toBe('private draft')
    } finally { vi.unstubAllEnvs(); vi.resetModules() }
  })
})
