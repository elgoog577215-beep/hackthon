import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { activeLocale } from '@/shared/i18n'
import { createPinia, setActivePinia } from 'pinia'
import CoursePublicationPanel from '@/components/CoursePublicationPanel.vue'
import StudentCourseFeedback from '@/components/StudentCourseFeedback.vue'

const api = vi.hoisted(() => ({ courseFeedback: vi.fn(), sendCourseFeedback: vi.fn(), retryCourseFeedback: vi.fn() }))
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api }))
vi.mock('@/utils/http', () => ({ default: http, teacherRequestConfig: (config = {}) => ({ ...config, identityScope: 'teacher' }) }))
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks(); activeLocale.value = 'zh'
  api.courseFeedback.mockResolvedValue({ items: [], replies_available: true })
  http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/preview') ? { availability: { reading: true } } : url.endsWith('/feedback') ? { items: [] } : { enabled: true, current_revision: 'doc-a', status: 'unpublished', ppt_options: [{ project_id: 'ppt-a', title: '课程幻灯片' }] } }))
  http.post.mockResolvedValue({ data: {} })
})
afterEach(() => { wrapper?.unmount(); activeLocale.value = 'zh' })
describe('two-service course publication and feedback', () => {
  it('labels an explicitly shared goal summary separately from a formal attempt',async()=>{
    api.courseFeedback.mockResolvedValue({items:[{feedback_id:'summary',kind:'learning_summary',payload:{goal:{text:'考试复习'}},status:'superseded',created_at:''}],replies_available:true})
    wrapper=mount(StudentCourseFeedback,{props:{courseId:'c',revisionId:'r'}});await flushPromises()
    expect(wrapper.text()).toContain('目标摘要');expect(wrapper.text()).toContain('考试复习');expect(wrapper.text()).not.toContain('正式作答回执')
  })
  it('blocks publication until the public preview confirms readable handout content', async () => {
    http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/preview') ? { availability: { reading: false } } : url.endsWith('/feedback') ? { items: [] } : { enabled: true, current_revision: 'doc-a', status: 'unpublished' } }))
    wrapper = mount(CoursePublicationPanel, { props: { courseId: 'source-a' }, global: { stubs: { Teleport: true } } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    const publish = wrapper.findAll('button').find(b => b.text() === '发布当前课程版本')!
    expect(publish.attributes('disabled')).toBeDefined()
    await publish.trigger('click')
    expect(http.post).not.toHaveBeenCalled()
  })
  it('publishes the current revision and only explicitly selected PPTs with teacher identity', async () => {
    wrapper = mount(CoursePublicationPanel, { props: { courseId: 'source-a' }, global: { stubs: { Teleport: true } } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(http.post).not.toHaveBeenCalled()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('button').find(b => b.text() === '发布当前课程版本')!.trigger('click'); await flushPromises()
    expect(http.get).toHaveBeenCalledWith('/api/teacher/courses/source-a/exchange', { identityScope: 'teacher', timeout: 60000 })
    expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/source-a/exchange/publish', { expected_revision: 'doc-a', ppt_project_ids: ['ppt-a'] }, { identityScope: 'teacher', timeout: 240000 })
    expect(wrapper.text()).toContain('课程版本已发布')
  })
  it('replies to a specific received question with its optimistic revision', async () => {
    http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/feedback') ? { items: [{ feedback_id: 'feedback-a', actor_id: 'local-student:a', kind: 'course_question', payload: { text: '哪里不懂？' }, revision: 4, reply: '' }] } : { enabled: true, current_revision: 'doc-a', status: 'published' } }))
    wrapper = mount(CoursePublicationPanel, { props: { courseId: 'source-a' }, global: { stubs: { Teleport: true } } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.findAll('.delivery-tabs button')[2]!.trigger('click')
    await wrapper.get('textarea').setValue('请看第三段。'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/source-a/exchange/feedback/feedback-a/reply', { expected_revision: 4, text: '请看第三段。' }, { identityScope: 'teacher' })
  })
  it('keeps a lost-response feedback submission id stable on manual retry', async () => {
    api.sendCourseFeedback.mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce({ feedback_id: 'feedback-a', status: 'pending' })
    wrapper = mount(StudentCourseFeedback, { props: { courseId: 'course-a', revisionId: 'release-a' } })
    await flushPromises(); await wrapper.get('textarea').setValue('为什么这样计算？')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('为什么这样计算？')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const first = api.sendCourseFeedback.mock.calls[0]!
    expect(api.sendCourseFeedback.mock.calls[1]).toEqual(first)
    expect(first[1]).toMatchObject({ expected_release_id: 'release-a', text: '为什么这样计算？' })
    expect(wrapper.text()).toContain('问题已保存')
  })
  it('shows saved pending questions offline and gives a manual delivery action', async () => {
    api.courseFeedback.mockResolvedValue({ replies_available: false, items: [{ feedback_id: 'feedback-a', kind: 'course_question', payload: { text: 'My saved question' }, status: 'pending' }] })
    api.retryCourseFeedback.mockResolvedValue({ status: 'pending' })
    activeLocale.value = 'en'
    wrapper = mount(StudentCourseFeedback, { props: { courseId: 'course-a', revisionId: 'release-a' } })
    await flushPromises()
    expect(wrapper.text()).toContain('showing saved delivery records')
    expect(wrapper.text()).toContain('Personal handouts, notes and AI conversations stay in your study space')
    await wrapper.findAll('button').find(b => b.text() === 'Send again')!.trigger('click'); await flushPromises()
    expect(api.retryCourseFeedback).toHaveBeenCalledWith('course-a', 'feedback-a')
  })
  it('discards a late reply when switching to another course', async () => {
    let resolve!: (value: unknown) => void
    api.courseFeedback.mockReturnValueOnce(new Promise(done => { resolve = done }))
    wrapper = mount(StudentCourseFeedback, { props: { courseId: 'course-a', revisionId: 'release-a' } })
    await wrapper.setProps({ courseId: 'course-b', revisionId: 'release-b' }); await flushPromises()
    resolve({ items: [{ feedback_id: 'private-a', kind: 'course_question', payload: { text: 'Old course reply' } }], replies_available: true }); await flushPromises()
    expect(wrapper.text()).not.toContain('Old course reply')
  })
})
