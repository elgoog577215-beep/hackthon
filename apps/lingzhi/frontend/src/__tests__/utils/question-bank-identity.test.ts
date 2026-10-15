import { afterEach, describe, expect, it, vi } from 'vitest'
import http, { getTeacherIdentity, setActiveRequestIdentityScope } from '@/utils/http'
import { runQuestionBankRebuild, resumeQuestionBankRebuild } from '@/utils/question-bank-rebuild'

vi.mock('@/utils/usage-tracker', () => ({ trackApiAction: vi.fn() }))

const originalAdapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = originalAdapter; setActiveRequestIdentityScope('learner') })

describe('teacher question job request identity with the real HTTP interceptor', () => {
  it('keeps create and poll bound to the teacher when ambient scope is learner', async () => {
    setActiveRequestIdentityScope('learner')
    const actors: string[] = []
    http.defaults.adapter = async config => {
      actors.push(String(config.headers.get('X-User-Id')))
      setActiveRequestIdentityScope('learner')
      return { config, status: 200, statusText: 'OK', headers: {}, data: {
        job_id: 'identity-job', status: config.method === 'post' ? 'queued' : 'completed',
        progress: 100, status_url: '/api/courses/c/question-bank/rebuilds/identity-job',
      } }
    }
    await runQuestionBankRebuild('c', { request_id: 'identity-test', scope: 'nodes', node_ids: ['L2-1-1'], mode: 'incremental' }, { pollIntervalMs: 0 })
    expect(actors).toEqual([getTeacherIdentity(), getTeacherIdentity()])
  })

  it('keeps recovery and resumed polling bound to the teacher', async () => {
    setActiveRequestIdentityScope('learner')
    const actors: string[] = []
    http.defaults.adapter = async config => {
      actors.push(String(config.headers.get('X-User-Id')))
      return { config, status: 200, statusText: 'OK', headers: {}, data: {
        job_id: 'identity-job', status: actors.length === 1 ? 'running' : 'completed',
        progress: 100, status_url: '/api/courses/c/question-bank/rebuilds/identity-job',
      } }
    }
    await resumeQuestionBankRebuild('c', { pollIntervalMs: 0 })
    expect(actors).toEqual([getTeacherIdentity(), getTeacherIdentity()])
  })

  it('does not hide an ownership denial as an idle job', async () => {
    const denied = { response: { status: 404, data: { detail: { code: 'teacher_course_unavailable' } } } }
    http.defaults.adapter = async () => { throw denied }
    await expect(resumeQuestionBankRebuild('c')).rejects.toBe(denied)
  })
})
