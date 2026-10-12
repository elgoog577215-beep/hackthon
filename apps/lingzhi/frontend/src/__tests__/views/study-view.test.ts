import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ config: vi.fn(), me: vi.fn(), list: vi.fn(), sources: vi.fn(), generate: vi.fn(), get: vi.fn(), note: vi.fn(), resume: vi.fn(), logout: vi.fn(), login: vi.fn(), addText: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, studySession: { get: () => 'local-session', set: vi.fn(), clear: vi.fn() }, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
vi.mock('@/utils/http', () => ({ isQizhiAuthRequired: () => false, redirectToQizhiLogin: vi.fn() }))
import StudyView from '@/views/StudyView.vue'
import { activeLocale } from '@/shared/i18n'

const user = { id: 'student-a', username: 'student_a', role: 'student' }
const source = { id: 'mat-123', filename: '两章资料.md', status: 'parsed', warnings: [], error: '', sections: [{ id: 'blk-1', title: '第一章', characters: 300 }, { id: 'blk-3', title: '第二章', characters: 400 }] }
const saved = { id: 'material-a', title: '两章讲义', purpose: 'systematic', status: 'completed', task_id: 'task-a', updated_at: '', plans: [], notes: { 'revision-a': { content: '已保存的理解', updated_at: '' } }, revisions: [{ id: 'revision-a', status: 'completed', sections: [{ id: 's1', title: '第一章', complete: true, fragment: '', source: { filename: '资料.md', asset_id: 'mat-123', source_sha256: '123456789abcdef' }, blocks: [{ block_id: 'b1', content_type: 'definition', type_label: '定义', title: '向量', content: '真实讲义正文', knowledge_names: [], answer_to: '' }] }] }], task: { id: 'task-a', status: 'completed', progress: 100 } }
let wrapper: VueWrapper | undefined

async function page(path = '/study') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/study/:materialId?', name: 'study', component: StudyView }, { path: '/courses', component: { template: '<div />' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount({ components: { RouterView }, template: '<RouterView />' }, { global: { plugins: [createPinia(), router], stubs: { MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' }, HandoutContentBlock: { template: '<div><slot /></div>' }, HandoutConceptMap: true, HandoutTableOfContents: true } } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear(); activeLocale.value = 'zh'
  api.config.mockResolvedValue({ local_login_enabled: true }); api.me.mockResolvedValue(user)
  api.list.mockResolvedValue([]); api.sources.mockResolvedValue([source]); api.get.mockResolvedValue(structuredClone(saved)); api.logout.mockResolvedValue({})
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })

describe('personal study handouts', () => {
  it('uses owned materials and source ranges for two learning purposes without teacher setup', async () => {
    const { wrapper } = await page()
    expect(wrapper.text()).toContain('student_a')
    expect(wrapper.text()).toContain('第一份讲义')
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.source-selection')).toHaveLength(2)
    expect(wrapper.findAll('.study-purpose-options button')).toHaveLength(2)
    expect(wrapper.text()).not.toMatch(/教师预览|课程代码|学分|教案确认|teacherPreview/)
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('prevents duplicate submissions and passes the exact selected range and purpose', async () => {
    const { wrapper, router } = await page()
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    await wrapper.findAll('.source-selection input')[1]!.setValue(true)
    await wrapper.get('input[placeholder="例如：线性代数前两章复习"]').setValue('方程组备考')
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    let resolve: (value: unknown) => void = () => {}
    api.generate.mockImplementation(() => new Promise(done => { resolve = done }))
    await wrapper.get('form.study-create').trigger('submit')
    await wrapper.get('form.study-create').trigger('submit')
    expect(api.generate).toHaveBeenCalledTimes(1)
    expect(api.generate.mock.calls[0]![0]).toMatchObject({ title: '方程组备考', purpose: 'exam_prep', selections: [{ asset_id: 'mat-123', section_id: 'blk-3' }] })
    const requestId = api.generate.mock.calls[0]![0].request_id
    expect(requestId).toHaveLength(36)
    resolve(saved); await flushPromises()
    expect(router.currentRoute.value.params.materialId).toBe('material-a')
    expect(wrapper.text()).toContain('真实讲义正文')
  })

  it('keeps an unsaved note after save failure and saves it to its material revision on retry', async () => {
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '已保存的理解')
    await wrapper.get('.study-note textarea').setValue('新的理解与问题')
    api.note.mockRejectedValueOnce(new Error('保存失败')).mockResolvedValueOnce({})
    await wrapper.get('.study-note button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('保存失败')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '新的理解与问题')
    expect(wrapper.text()).toContain('笔记尚未保存')
    await wrapper.get('.study-note button').trigger('click'); await flushPromises()
    expect(api.note).toHaveBeenLastCalledWith('material-a', 'revision-a', '新的理解与问题')
    expect(wrapper.text()).toContain('笔记已保存')
  })

  it('restores private note drafts without copying one student’s draft to another', async () => {
    sessionStorage.setItem('lingzhi-study-note:student-a:material-a:revision-a', '未提交的草稿')
    sessionStorage.setItem('lingzhi-study-note:student-b:material-a:revision-a', '另一人的笔记')
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '未提交的草稿')
    expect(wrapper.text()).not.toContain('另一人的笔记')
    expect(api.note).not.toHaveBeenCalled()
  })

  it('loads an interrupted job without automatically resuming it', async () => {
    api.get.mockResolvedValue({ ...structuredClone(saved), status: 'failed', task: { id: 'task-a', status: 'paused', progress: 50 } })
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.text()).toContain('继续缺失内容')
    expect(api.resume).not.toHaveBeenCalled()
    await wrapper.get('.study-progress button').trigger('click'); await flushPromises()
    expect(api.resume).toHaveBeenCalledExactlyOnceWith('material-a')
  })

  it('renders the corresponding English creation flow', async () => {
    activeLocale.value = 'en'
    const { wrapper } = await page()
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Choose your sources')
    expect(wrapper.text()).toContain('Deep understanding')
    expect(wrapper.text()).toContain('Exam preparation')
    expect(wrapper.text()).toContain('Generate handout')
    expect(wrapper.text()).not.toContain('预计阅读时间')
  })

  it('retries the same submission id after a lost response but uses a new id for changed input', async () => {
    const { wrapper } = await page()
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    await wrapper.find('.source-selection input').setValue(true)
    await wrapper.get('input[placeholder="例如：线性代数前两章复习"]').setValue('原讲义')
    api.generate.mockRejectedValue(new Error('连接中断'))
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    const originalId = api.generate.mock.calls[0]![0].request_id
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate.mock.calls[1]![0].request_id).toBe(originalId)
    await wrapper.get('input[placeholder="例如：线性代数前两章复习"]').setValue('修改后的讲义')
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate.mock.calls[2]![0].request_id).not.toBe(originalId)
  })

  it('discards an old owner’s late source response after logout and a different login', async () => {
    const { wrapper } = await page()
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    await wrapper.find('.study-source-actions button').trigger('click')
    await wrapper.find('.study-paste input').setValue('A 的私有资料')
    await wrapper.find('.study-paste textarea').setValue('A 的私有正文')
    let resolve: (value: unknown) => void = () => {}
    api.addText.mockImplementation(() => new Promise(done => { resolve = done }))
    await wrapper.find('.study-paste button').trigger('click')
    await wrapper.find('.study-header-actions button:last-child').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('A 的私有正文')
    api.login.mockResolvedValue({ token: 'b-session', user: { id: 'student-b', username: 'student_b', role: 'student' } })
    api.sources.mockResolvedValue([])
    await wrapper.get('form.study-login-card').trigger('submit'); await flushPromises()
    resolve({ ...source, filename: 'A 的私有资料.md' }); await flushPromises()
    expect(wrapper.text()).toContain('student_b')
    expect(wrapper.text()).not.toContain('A 的私有资料')
    await wrapper.find('.study-navigation>button:nth-of-type(2)').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.source-selection')).toHaveLength(0)
    expect(wrapper.get('input[placeholder="例如：线性代数前两章复习"]').element).toHaveProperty('value', '')
  })
})
