import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseCreateView from '@/views/TeacherCourseCreateView.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const runtime = vi.hoisted(() => ({ createTeacherCourseSpace: vi.fn(), fetchCourseList: vi.fn(), push: vi.fn() }))
vi.mock('@/features/teacher-course/useTeacherCourseRuntime', () => ({ useTeacherCourseRuntime: () => ({ course: runtime }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: runtime.push }) }))
let wrapper: ReturnType<typeof mount>
beforeEach(async () => {
  vi.resetAllMocks()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute('open') } })
  runtime.createTeacherCourseSpace.mockResolvedValue({ course_id: 'created-course' })
  runtime.fetchCourseList.mockResolvedValue(undefined)
  await setLocale('zh')
  wrapper = mount(TeacherCourseCreateView, { attachTo: document.body, global: { stubs: { Teleport: true, ZjuCourseScheduleGrid: true } } })
})
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
async function setGoals() {
  await wrapper.get('#course-name').setValue('线性代数')
  await wrapper.get('#course-category').setValue('专业基础课')
  await wrapper.get('#course-goal').setValue('用矩阵求解线性方程组')
  await wrapper.get('#course-subject-type').setValue('math_formal')
  await wrapper.get('.form-actions .primary').trigger('click')
  await wrapper.get('#planned-lecture-count').setValue(2)
  await wrapper.get('#total-hours').setValue(8)
  await wrapper.get('.form-actions .primary').trigger('click')
}
describe('teacher course creation flow', () => {
  it('requires real goals before proceeding and does not create on intermediate steps', async () => {
    await wrapper.get('.form-actions .primary').trigger('click')
    expect(wrapper.find('#course-goal').exists()).toBe(true)
    expect(wrapper.find('#planned-lecture-count').exists()).toBe(false)
    expect(runtime.createTeacherCourseSpace).not.toHaveBeenCalled()
    await setGoals()
    expect(wrapper.text()).toContain('2 讲 · 8 学时')
    expect(runtime.createTeacherCourseSpace).not.toHaveBeenCalled()
  })
  it('carries goals and the selected material path into the same course workspace', async () => {
    await setGoals()
    await wrapper.findAll('.source-options button')[1]!.trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(runtime.createTeacherCourseSpace).toHaveBeenCalledWith(expect.objectContaining({
      planned_lecture_count: 2, total_hours: 8,
      generation_request: expect.objectContaining({ pedagogy_mode: 'math_formal', course_intent: expect.objectContaining({ learning_goal: '用矩阵求解线性方程组' }), teacher_course_brief: expect.objectContaining({ lecture_count: 2, total_class_hours: 8 }) }),
    }))
    expect(runtime.push).toHaveBeenCalledWith(expect.objectContaining({ name: 'course-workspace', params: { courseId: 'created-course', mode: 'setup' }, query: expect.objectContaining({ prepare: 'materials', stage: 'foundation' }) }))
  })
  it('retains input after a failed creation and allows an explicit retry', async () => {
    runtime.createTeacherCourseSpace.mockRejectedValueOnce(new Error('Connection interrupted'))
    await setGoals(); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Connection interrupted')
    expect(wrapper.get('.creation-summary').text()).toContain('用矩阵求解线性方程组')
    expect(runtime.push).not.toHaveBeenCalled()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(runtime.createTeacherCourseSpace).toHaveBeenCalledTimes(2)
    expect(runtime.push).toHaveBeenCalledWith(expect.objectContaining({ query: expect.objectContaining({ prepare: 'blank' }) }))
  })
  it('translates the steps and course hierarchy in English', async () => {
    await setLocale('en')
    expect(wrapper.get('.creation-steps').text()).toContain('Course goals')
    await setGoals()
    expect(wrapper.text()).toContain('Creating it does not start an AI request')
    expect(wrapper.text()).toContain('2 lectures · 8 class hours')
  })
  it('reopens the saved course after navigation failure without creating a duplicate', async () => {
    runtime.push.mockRejectedValueOnce(new Error('Navigation interrupted'))
    await setGoals(); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('课程已保存')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(runtime.createTeacherCourseSpace).toHaveBeenCalledTimes(1)
    expect(runtime.push).toHaveBeenCalledTimes(2)
    expect(runtime.push.mock.calls[1]![0]).toMatchObject({ params: { courseId: 'created-course', mode: 'setup' } })
  })
})
