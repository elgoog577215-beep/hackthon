import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ courses: vi.fn(), path: vi.fn(), config: vi.fn(), me: vi.fn(), list: vi.fn(), sources: vi.fn(), generate: vi.fn(), get: vi.fn(), note: vi.fn(), resume: vi.fn(), logout: vi.fn(), login: vi.fn(), addText: vi.fn(), upload: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, studySession: { get: () => 'local-session', set: vi.fn(), clear: vi.fn() }, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
vi.mock('@/utils/http', () => ({ isQizhiAuthRequired: () => false, redirectToQizhiLogin: vi.fn() }))
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'
import StudyView from '@/views/StudyView.vue'
import { activeLocale, setLocale } from '@/shared/i18n'

const user = { id: 'student-a', username: 'student_a', role: 'student' }
const source = { id: 'mat-123', filename: '两章资料.md', status: 'parsed', warnings: [], error: '', sections: [{ id: 'blk-1', title: '第一章', characters: 300 }, { id: 'blk-3', title: '第二章', characters: 400 }] }
const saved = { id: 'material-a', title: '两章讲义', purpose: 'systematic', status: 'completed', task_id: 'task-a', updated_at: '', plans: [], notes: { 'revision-a': { content: '已保存的理解', updated_at: '' } }, revisions: [{ id: 'revision-a', status: 'completed', sections: [{ id: 's1', title: '第一章', complete: true, fragment: '', source: { filename: '资料.md', asset_id: 'mat-123', source_sha256: '123456789abcdef' }, blocks: [{ block_id: 'b1', content_type: 'definition', type_label: '定义', title: '向量', content: '真实讲义正文', knowledge_names: [], answer_to: '' }] }] }], task: { id: 'task-a', status: 'completed', progress: 100 } }
let wrapper: VueWrapper | undefined

async function page(path = '/study') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/study/:materialId?', name: 'study', component: StudyView }, { path: '/courses', component: { template: '<div />' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount({ components: { RouterView }, template: '<RouterView />' }, { attachTo: document.body, global: { plugins: [createPinia(), router], stubs: { PersonalHandoutAssistant: true, MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' }, HandoutContentBlock: { template: '<div><slot /></div>' }, HandoutConceptMap: true, HandoutTableOfContents: true } } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(async () => {
  vi.clearAllMocks(); sessionStorage.clear(); vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh }))); await setLocale('zh')
  api.config.mockResolvedValue({ local_login_enabled: true }); api.me.mockResolvedValue(user)
  api.courses.mockResolvedValue([]); api.list.mockResolvedValue([]); api.sources.mockResolvedValue([source]); api.get.mockResolvedValue(structuredClone(saved)); api.logout.mockResolvedValue({})
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.replaceChildren(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('personal study handouts', () => {
  it('reconnects the visible authorized course library together with personal sources', async () => {
    api.sources.mockRejectedValueOnce(new Error('另一端暂不可达'))
    api.courses.mockRejectedValueOnce(new Error('另一端暂不可达'))
    const { wrapper } = await page('/study?view=courses')
    expect(api.courses).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.course-empty').exists()).toBe(false)
    api.courses.mockResolvedValue([{ course_id: 'course-a', title: '设计思维', revision_id: 'release-a', section_count: 2, reading_available: true }])
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(api.courses).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('设计思维')
    expect(wrapper.find('.study-error').exists()).toBe(false)
    expect(wrapper.find('.student-courses [role="alert"]').exists()).toBe(false)
  })
  it('keeps the home, authorized courses, and personal materials within the authenticated student space', async () => {
    const { wrapper, router } = await page()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    expect(api.courses).toHaveBeenCalledTimes(1)
    await router.push('/study?view=materials'); await flushPromises()
    expect(wrapper.find('.study-library').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    await wrapper.get('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    expect(wrapper.find('.study-create').exists()).toBe(true)
    await wrapper.get('.study-back').trigger('click'); await flushPromises()
    await wrapper.findAll('.library-filter-tabs button').find(button => button.text() === '教师课程')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.study-create').exists()).toBe(false)
    expect(router.currentRoute.value.query.view).toBe('courses')
  })
  it('uses owned materials and source ranges for two learning purposes without teacher setup', async () => {
    const { wrapper } = await page()
    expect(wrapper.text()).toContain('student_a')
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.source-selection')).toHaveLength(2)
    expect(wrapper.findAll('.study-purpose-options button')).toHaveLength(2)
    expect(wrapper.text()).not.toMatch(/教师预览|课程代码|学分|教案确认|teacherPreview/)
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('prevents duplicate submissions and passes the exact selected range and purpose', async () => {
    const { wrapper, router } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    await wrapper.findAll('.source-selection input')[1]!.setValue(true)
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('方程组备考')
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

  it('moves only the reading scroller when restoring a chapter', async () => {
    const { wrapper } = await page('/study/material-a')
    const scroller = wrapper.get('.study-document-scroll').element as HTMLElement
    const section = wrapper.get('[data-section-id="s1"]').element as HTMLElement
    const outer = wrapper.get('.study-workspace').element as HTMLElement
    scroller.scrollTop = 100
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    vi.spyOn(scroller, 'getBoundingClientRect').mockReturnValue({ top: 120 } as DOMRect)
    vi.spyOn(section, 'getBoundingClientRect').mockReturnValue({ top: 420 } as DOMRect)
    await wrapper.get('.study-chapter-list button').trigger('click')
    expect(scrollTo).toHaveBeenCalledWith({ top: 376, behavior: 'instant' })
    expect(outer.scrollTop).toBe(0)
    expect(sessionStorage.getItem('lingzhi-study-position:student-a:material-a:revision-a')).toBe('s1')
  })

  it('filters the directory without changing the handout and keeps notes when the directory is hidden', async () => {
    const material = structuredClone(saved)
    material.revisions[0]!.sections.push({ ...material.revisions[0]!.sections[0]!, id: 's2', title: '第二章', blocks: [] })
    api.get.mockResolvedValue(material)
    const { wrapper } = await page('/study/material-a')
    await wrapper.get('[data-tool="note"]').trigger('click')
    await wrapper.get('.study-note textarea').setValue('目录调整时保留的草稿')
    await wrapper.get('.study-chapter-search input').setValue('第二章')
    expect(wrapper.findAll('.study-chapter-list button')).toHaveLength(1)
    expect(wrapper.get('.study-chapter-number').text()).toBe('02')
    expect(wrapper.findAll('.study-handout-section')).toHaveLength(2)
    await wrapper.get('.study-directory-heading button').trigger('click')
    expect(wrapper.find('.study-navigation').exists()).toBe(false)
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '目录调整时保留的草稿')
    await wrapper.get('button[aria-label="展开目录"]').trigger('click')
    expect(wrapper.get('.study-chapter-search input').element).toHaveProperty('value', '第二章')
    await wrapper.get('.study-chapter-search input').setValue('没有这个章节')
    expect(wrapper.text()).toContain('没有匹配的章节')
    expect(wrapper.findAll('.study-handout-section')).toHaveLength(2)
    expect(api.note).not.toHaveBeenCalled()
  })

  it('keeps an unsaved note after save failure and saves it to its material revision on retry', async () => {
    const { wrapper } = await page('/study/material-a')
    await wrapper.get('[data-tool="note"]').trigger('click')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '已保存的理解')
    await wrapper.get('.study-note textarea').setValue('新的理解与问题')
    await wrapper.get('.study-tool-heading button').trigger('click')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(false)
    await wrapper.get('[data-tool="note"]').trigger('click')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '新的理解与问题')
    api.note.mockRejectedValueOnce(new Error('保存失败')).mockResolvedValueOnce({})
    await wrapper.get('.study-note button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('保存失败')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '新的理解与问题')
    expect(wrapper.text()).toContain('笔记尚未保存')
    await wrapper.get('.study-note button').trigger('click'); await flushPromises()
    expect(api.note).toHaveBeenLastCalledWith('material-a', 'revision-a', '新的理解与问题')
    expect(wrapper.text()).toContain('笔记已保存')
  })

  it('opens the assistant on demand and binds a real reading selection to the exact owned block', async () => {
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(false)
    await wrapper.get('[data-tool="assistant"]').trigger('click')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(true)
    const assistant = wrapper.getComponent({ name: 'PersonalHandoutAssistant' })
    expect(assistant.props()).toMatchObject({ ownerId: 'student-a', materialId: 'material-a', revisionId: 'revision-a', context: { section_id: 's1', block_id: '', quote: '' } })
    const body = wrapper.get('[data-block-id="b1"]').element
    const range = document.createRange(); range.selectNodeContents(body)
    const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range)
    await wrapper.get('.study-document-scroll').trigger('pointerup')
    expect(assistant.props('context')).toMatchObject({ section_id: 's1', section_title: '第一章', block_id: 'b1', block_title: '向量', quote: '真实讲义正文' })
    await wrapper.get('.study-selection-actions button:last-child').trigger('click')
    expect(assistant.props('context')).toMatchObject({ block_id: '', quote: '' })
    selection.removeAllRanges()
  })

  it('restores private note drafts without copying one student’s draft to another', async () => {
    sessionStorage.setItem('lingzhi-study-note:student-a:material-a:revision-a', '未提交的草稿')
    sessionStorage.setItem('lingzhi-study-note:student-b:material-a:revision-a', '另一人的笔记')
    const { wrapper } = await page('/study/material-a')
    await wrapper.get('[data-tool="note"]').trigger('click')
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
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Choose your sources')
    expect(wrapper.text()).toContain('Systematic learning')
    expect(wrapper.text()).toContain('Exam preparation')
    expect(wrapper.text()).toContain('Generate course handout')
    expect(wrapper.text()).not.toContain('预计阅读时间')
  })

  it('retries the same submission id after a lost response but uses a new id for changed input', async () => {
    const { wrapper } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    await wrapper.find('.source-selection input').setValue(true)
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('原讲义')
    api.generate.mockRejectedValue(new Error('连接中断'))
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    const originalId = api.generate.mock.calls[0]![0].request_id
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate.mock.calls[1]![0].request_id).toBe(originalId)
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('修改后的讲义')
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate.mock.calls[2]![0].request_id).not.toBe(originalId)
  })

  it('discards an old owner’s late source response after logout and a different login', async () => {
    const { wrapper } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    await wrapper.find('.study-paste-toggle').trigger('click')
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
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.source-selection')).toHaveLength(0)
    expect(wrapper.get('input[placeholder="例如：线性代数前两章"]').element).toHaveProperty('value', '')
  })
  it('uploads an owned source and blocks generation until parsing returns', async () => {
    api.sources.mockResolvedValue([])
    const { wrapper } = await page('/study?create=1')
    let complete!: (value: unknown) => void
    api.upload.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const file = new File(['# First lesson\nSource text'], 'my-course.md', { type: 'text/markdown' })
    const input = wrapper.get('.study-upload-input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await wrapper.get('form.study-create').trigger('submit')
    expect(api.generate).not.toHaveBeenCalled()
    complete({ ...source, filename: 'my-course.md' }); await flushPromises()
    expect(api.upload).toHaveBeenCalledExactlyOnceWith(file)
    expect(wrapper.get('input[placeholder="例如：线性代数前两章"]').element).toHaveProperty('value', 'my-course')
    expect(wrapper.findAll('.source-selection input').some(input => (input.element as HTMLInputElement).checked)).toBe(false)
    expect(wrapper.get('.study-generation-issue').text()).toContain('请先勾选')
    for (const input of wrapper.findAll('.source-selection input')) await input.setValue(true)
    api.generate.mockResolvedValueOnce(saved)
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({ purpose: 'systematic', selections: [{ asset_id: 'mat-123', section_id: 'blk-1' }, { asset_id: 'mat-123', section_id: 'blk-3' }] }))
  })

  it('rejects oversized uploads and stale draft ranges before a generation request', async () => {
    sessionStorage.setItem('lingzhi-study-draft:student-a', JSON.stringify({ form: { title: 'Old draft' }, selectedRanges: ['missing:deleted'] }))
    const { wrapper } = await page('/study?create=1')
    const file = new File(['data'], 'too-large.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: 21 * 1024 * 1024 })
    const input = wrapper.get('.study-upload-input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change'); await flushPromises()
    expect(wrapper.text()).toContain('20 MB')
    expect(api.upload).not.toHaveBeenCalled()
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('restores the create URL and chosen mode after returning from a saved course', async () => {
    const { wrapper, router } = await page('/study?create=1')
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('自建课程草稿')
    await router.push('/study/material-a'); await flushPromises()
    await router.push('/study?create=1'); await flushPromises()
    expect(wrapper.find('form.study-create').exists()).toBe(true)
    expect(wrapper.get('input[placeholder="例如：线性代数前两章"]').element).toHaveProperty('value', '自建课程草稿')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('explains unavailable draft ranges and removes only invalid or duplicate selections', async () => {
    sessionStorage.setItem('lingzhi-study-draft:student-a', JSON.stringify({ form: { title: '保留的课程', purpose: 'exam_prep', requirements: '保留目标' }, selectedRanges: ['mat-123:blk-1', 'missing:deleted', 'mat-123:blk-1'] }))
    const { wrapper } = await page('/study?create=1')
    expect(wrapper.get('.study-generation-issue').text()).toContain('已不可用')
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeDefined()
    await wrapper.get('.study-range-recovery button').trigger('click')
    expect(wrapper.find('.study-range-recovery').exists()).toBe(false)
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeUndefined()
    expect(wrapper.findAll('.source-selection input').map(input => (input.element as HTMLInputElement).checked)).toEqual([true, false])
    expect(wrapper.get('input[placeholder="例如：线性代数前两章"]').element).toHaveProperty('value', '保留的课程')
    expect(wrapper.get('.study-create textarea').element).toHaveProperty('value', '保留目标')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('shows the missing title or invalid reading time instead of a silent disabled action', async () => {
    const { wrapper } = await page('/study?create=1')
    expect(wrapper.get('.study-generation-issue').text()).toContain('勾选')
    await wrapper.find('.source-selection input').setValue(true)
    expect(wrapper.get('.study-generation-issue').text()).toContain('课程名称')
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('系统学习课程')
    for (const value of ['0', '601', '10.5', '']) {
      await wrapper.get('input[type="number"]').setValue(value)
      expect(wrapper.get('.study-generation-issue').text()).toContain('10–600')
      expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeDefined()
    }
    await wrapper.get('input[type="number"]').setValue('45')
    expect(wrapper.find('.study-generation-issue').exists()).toBe(false)
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeUndefined()
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('keeps saved reading accessible when source discovery fails', async () => {
    api.sources.mockRejectedValueOnce(new Error('资料库暂不可用'))
    const { wrapper } = await page('/study/material-a')
    expect(api.get).toHaveBeenCalledWith('material-a')
    expect(wrapper.text()).toContain('真实讲义正文')
    expect(wrapper.text()).toContain('资料库暂不可用')
    expect(wrapper.findComponent({ name: 'PersonalHandoutAssistant' }).exists()).toBe(true)
    expect(api.resume).not.toHaveBeenCalled()
  })

  it('renders saved reading without waiting for a slow source request', async () => {
    let complete!: (value: unknown) => void
    api.sources.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.text()).toContain('真实讲义正文')
    complete([source]); await flushPromises()
    expect(wrapper.text()).toContain('真实讲义正文')
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('keeps sources available and supports reconnecting when only the course list fails', async () => {
    api.list.mockRejectedValueOnce(new Error('课程列表暂不可用'))
    const { wrapper } = await page('/study?create=1')
    expect(wrapper.find('form.study-create').exists()).toBe(true)
    expect(wrapper.findAll('.source-selection')).toHaveLength(2)
    expect(wrapper.text()).toContain('课程列表暂不可用')
    await wrapper.find('.source-selection input').setValue(true)
    await wrapper.get('input[placeholder="例如：线性代数前两章"]').setValue('未丢失的输入')
    api.list.mockResolvedValue([])
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.find('.study-error').exists()).toBe(false)
    expect(wrapper.find('form.study-create').exists()).toBe(true)
    expect(wrapper.get('input[placeholder="例如：线性代数前两章"]').element).toHaveProperty('value', '未丢失的输入')
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeUndefined()
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('keeps visible reading and the current unsaved note while reconnecting the same material', async () => {
    const { wrapper } = await page('/study/material-a')
    await wrapper.get('[data-tool="note"]').trigger('click')
    await wrapper.get('.study-note textarea').setValue('重连时保留我的笔记')
    api.note.mockRejectedValueOnce(new Error('笔记暂未保存'))
    await wrapper.get('.study-note button').trigger('click'); await flushPromises()
    let complete!: (value: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('真实讲义正文')
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '重连时保留我的笔记')
    complete(structuredClone(saved)); await flushPromises()
    expect(wrapper.get('.study-note textarea').element).toHaveProperty('value', '重连时保留我的笔记')
    expect(wrapper.text()).toContain('笔记尚未保存')
    expect(api.note).toHaveBeenCalledTimes(1)
  })

})
