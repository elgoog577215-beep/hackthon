import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import http from '@/utils/http'

describe('course blueprint read coordination', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('shares pending reads but fetches the generated draft on the next read', async () => {
    let resolveRequest!: (value: { data: Record<string, unknown> }) => void
    const request = new Promise<{ data: Record<string, unknown> }>(resolve => { resolveRequest = resolve })
    const get = vi.spyOn(http, 'get').mockReturnValue(request as never)
    const store = useCourseWorkspaceStore()

    const first = store.loadBlueprint('course-1')
    const second = store.loadBlueprint('course-1')

    expect(get).toHaveBeenCalledOnce()
    resolveRequest({ data: { course_id: 'course-1', source_revision: 'outline-1' } })
    await expect(Promise.all([first, second])).resolves.toEqual([
      { course_id: 'course-1', source_revision: 'outline-1' },
      { course_id: 'course-1', source_revision: 'outline-1' },
    ])
    const generated = {
      course_id: 'course-1',
      source_revision: 'outline-2',
      draft: { nodes: [{ content_summary: '本讲介绍静电场与高斯定理。' }] },
    }
    get.mockResolvedValueOnce({ data: generated })
    await expect(store.loadBlueprint('course-1')).resolves.toEqual(generated)
    expect(store.blueprint).toEqual(generated)
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('does not let a previous course response replace the current blueprint', async () => {
    let resolveFirst!: (value: { data: Record<string, unknown> }) => void
    let resolveSecond!: (value: { data: Record<string, unknown> }) => void
    const firstRequest = new Promise<{ data: Record<string, unknown> }>(resolve => { resolveFirst = resolve })
    const secondRequest = new Promise<{ data: Record<string, unknown> }>(resolve => { resolveSecond = resolve })
    vi.spyOn(http, 'get')
      .mockReturnValueOnce(firstRequest as never)
      .mockReturnValueOnce(secondRequest as never)
    const store = useCourseWorkspaceStore()

    const first = store.loadBlueprint('course-1')
    const second = store.loadBlueprint('course-2')
    resolveSecond({ data: { course_id: 'course-2', source_revision: 'outline-2' } })
    await second
    resolveFirst({ data: { course_id: 'course-1', source_revision: 'outline-1' } })
    await first

    expect(store.blueprint).toMatchObject({ course_id: 'course-2', source_revision: 'outline-2' })
  })

  it('reports a refresh failure instead of returning a stale successful snapshot', async () => {
    const snapshot = { course_id: 'course-1', source_revision: 'outline-1' }
    const get = vi.spyOn(http, 'get')
      .mockResolvedValueOnce({ data: snapshot })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: { ...snapshot, source_revision: 'outline-2' } })
    const store = useCourseWorkspaceStore()
    await store.loadBlueprint('course-1')
    await expect(store.loadBlueprint('course-1')).rejects.toThrow('offline')
    expect(store.blueprint).toEqual(snapshot)
    expect(store.loading).toBe(false)
    await expect(store.loadBlueprint('course-1')).resolves.toMatchObject({ source_revision: 'outline-2' })
    expect(get).toHaveBeenCalledTimes(3)
  })

  it('does not let an older same-course read overwrite a forced refresh', async () => {
    let resolveFirst!: (value: { data: Record<string, unknown> }) => void
    const pending = new Promise<{ data: Record<string, unknown> }>(resolve => { resolveFirst = resolve })
    vi.spyOn(http, 'get')
      .mockReturnValueOnce(pending as never)
      .mockResolvedValueOnce({ data: { source_revision: 'outline-2' } })
    const store = useCourseWorkspaceStore()
    const first = store.loadBlueprint('course-1')
    await store.loadBlueprint('course-1', { force: true })
    resolveFirst({ data: { source_revision: 'outline-1' } })
    await first
    expect(store.blueprint).toMatchObject({ source_revision: 'outline-2' })
  })

})
