import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { activeLocale, setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'
import StudentCourseLibrary from '@/components/StudentCourseLibrary.vue'

const api = vi.hoisted(() => ({ courses: vi.fn(), courseSource: vi.fn(), path: vi.fn(), updateCourse: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api }))
const course = { course_id: 'course-a', title: '线性代数', revision_id: 'revision-a', section_count: 2, reading_available: true }
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(async () => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  await setLocale('zh')
  api.courses.mockResolvedValue([course]); api.path.mockResolvedValue({ course_id: 'course-a', chapter: { chapter_id: 'lecture-a', chapter_name: '第一讲' }, attempt_count: 2, steps: [], next_action: { action_type: 'resume_practice_attempt', node_id: 'lecture-a' } })
})
afterEach(() => { wrapper?.unmount(); activeLocale.value = 'zh'; vi.unstubAllGlobals() })
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/study?view=courses')
  wrapper = mount(StudentCourseLibrary, { props: { userId: 'local-student:a' }, global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}
describe('authorized student course library', () => {
  it('adopts a teacher update only after the student chooses it, then refreshes paths', async () => {
    api.courses.mockResolvedValue([{ ...course, exchange_origin: { node_id: 'publisher' }, update_available: true, question_count: 3 }])
    api.updateCourse.mockResolvedValue({ release_id: 'revision-b' })
    const view = await page()
    expect(api.updateCourse).not.toHaveBeenCalled()
    api.courses.mockResolvedValue([{ ...course, revision_id: 'revision-b', exchange_origin: { node_id: 'publisher' }, update_available: false }])
    await view.findAll('button').find(b => b.text() === '使用新版本')!.trigger('click')
    await flushPromises()
    expect(api.updateCourse).toHaveBeenCalledExactlyOnceWith('course-a', 'revision-a')
    expect(view.text()).not.toContain('教师发布了新版本')
    expect(api.path).toHaveBeenCalledTimes(2)
  })
  it('opens formal learning without preview and carries a practice continuation intent', async () => {
    const view = await page()
    expect(view.text()).toContain('线性代数')
    expect(view.text()).toContain('继续未完成练习')
    const links = view.findAll('a').map(a => a.attributes('href'))
    expect(links.every(link => !link?.includes('teacherPreview'))).toBe(true)
    expect(links.some(link => link?.includes('learningAction=resume_practice_attempt'))).toBe(true)
  })
  it('derives sources from the displayed immutable course revision and emits only the returned owned source', async () => {
    const source = { id: 'source-a', filename: '线性代数.md', sections: [] }
    api.courseSource.mockResolvedValue(source)
    const view = await page()
    await view.findAll('button').find(b => b.text() === '生成个人复习讲义')!.trigger('click')
    await flushPromises()
    expect(api.courseSource).toHaveBeenCalledExactlyOnceWith('course-a', 'revision-a')
    expect(view.emitted('source')).toEqual([[source]])
  })
  it('keeps a stale-revision error visible without emitting a source or starting generation', async () => {
    api.courseSource.mockRejectedValue(new Error('教师讲义已更新'))
    const view = await page()
    await view.findAll('button').find(b => b.text() === '生成个人复习讲义')!.trigger('click')
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toBe('教师讲义已更新')
    expect(view.emitted('source')).toBeUndefined()
  })
  it('renders the English library and shared continuation labels', async () => {
    await setLocale('en')
    const view = await page()
    expect(view.text()).toContain('Authorized courses')
    expect(view.text()).toContain('Create a personal revision handout')
    expect(view.text()).toContain('Continue unfinished practice')
  })
})
