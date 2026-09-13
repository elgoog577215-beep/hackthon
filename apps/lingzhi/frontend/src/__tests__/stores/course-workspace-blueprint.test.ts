import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import http from '@/utils/http'

describe('course blueprint read coordination', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('shares one in-flight read and reuses the successful course snapshot', async () => {
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
    await expect(store.loadBlueprint('course-1')).resolves.toMatchObject({ source_revision: 'outline-1' })
    expect(get).toHaveBeenCalledOnce()
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
})
