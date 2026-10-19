import { describe, expect, it } from 'vitest'
import { readWorkspaceLocation, workspaceLocationQuery } from '@/shared/course-workspace-navigation'
describe('course workspace locations', () => {
  it('round trips the same lecture through files and refresh without losing the return target', () => {
    const source = { stage: 'script', lesson: 'lecture-2', returnTo: '/courses?view=courses' }
    const query = workspaceLocationQuery(source, { ...readWorkspaceLocation(source), view: 'files' })
    expect(query).toMatchObject({ view: 'files', stage: 'script', lesson: 'lecture-2', returnTo: source.returnTo })
    expect(readWorkspaceLocation(query)).toMatchObject({ stage: 'script', lessonId: 'lecture-2' })
  })
  it('keeps knowledge and companion pages separate from the numbered production chain', () => {
    expect(readWorkspaceLocation({ stage: 'knowledge', lesson: 'lecture-2' })).toMatchObject({ knowledge: true, stage: 'script', lessonId: 'lecture-2' })
    const location = readWorkspaceLocation({ stage: 'companion', template: 'rubric' })
    expect(workspaceLocationQuery({}, location)).toMatchObject({ stage: 'companion', template: 'rubric' })
  })
  it('retains a focused failure on the same stage but drops it when leaving that stage', () => {
    const query = { stage: 'script', lesson: 'lecture-2', task: 'job-2', issue: 'issue-2', expandIssue: '1' }
    expect(workspaceLocationQuery(query, readWorkspaceLocation(query))).toMatchObject({ task: 'job-2', issue: 'issue-2' })
    const changed = workspaceLocationQuery(query, { ...readWorkspaceLocation(query), stage: 'lesson' })
    expect(changed).not.toHaveProperty('task')
    expect(changed).not.toHaveProperty('issue')
  })
  it('normalizes unknown and array-valued navigation without changing course identity', () => {
    expect(readWorkspaceLocation({ stage: ['script'], lesson: ['wrong'], view: 'unknown' })).toEqual({ view: 'categories', stage: 'foundation', lessonId: '', knowledge: false, companionTemplateId: '' })
  })
  it('keeps the lesson and production stage while entering and leaving analysis', () => {
    const source = { stage: 'script', lesson: 'lecture-2', returnTo: '/courses' }
    const analysis = workspaceLocationQuery(source, { ...readWorkspaceLocation(source), view: 'insights' })
    expect(readWorkspaceLocation(analysis)).toMatchObject({ view: 'insights', stage: 'script', lessonId: 'lecture-2' })
    const restored = workspaceLocationQuery(analysis, { ...readWorkspaceLocation(analysis), view: 'categories' })
    expect(restored).toMatchObject(source)
    expect(restored).not.toHaveProperty('view')
  })

})
