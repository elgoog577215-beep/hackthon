import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ courses: vi.fn(), path: vi.fn(), config: vi.fn(), guest: vi.fn(), me: vi.fn(), list: vi.fn(), sources: vi.fn(), generate: vi.fn(), get: vi.fn(), note: vi.fn(), resume: vi.fn(), logout: vi.fn(), login: vi.fn(), addText: vi.fn(), upload: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, STUDY_UPLOAD_ACCEPT: '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md,.markdown,.txt,.csv,.json,.py,.js,.ts,.html,.css,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff', studySession: { get: () => 'local-session', set: vi.fn(), clear: vi.fn() }, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
vi.mock('@/utils/http', () => ({ isQizhiAuthRequired: () => false, redirectToQizhiLogin: vi.fn() }))
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'
import StudyView from '@/views/StudyView.vue'
import { activeLocale, setLocale } from '@/shared/i18n'

const user = { id: 'student-a', username: 'student_a', role: 'student' }
const source = { id: 'mat-123', filename: '两章资料.md', status: 'parsed', warnings: [], error: '', sections: [{ id: 'blk-1', title: '第一章', characters: 300 }, { id: 'blk-3', title: '第二章', characters: 400 }] }
const saved = { id: 'material-a', title: '两章讲义', purpose: 'systematic', status: 'completed', task_id: 'task-a', updated_at: '', plans: [], notes: { 'revision-a': { content: '已保存的理解', updated_at: '' } }, revisions: [{ id: 'revision-a', status: 'completed', sections: [{ id: 's1', title: '第一章', complete: true, fragment: '', source: { filename: '资料.md', asset_id: 'mat-123', source_sha256: '123456789abcdef' }, blocks: [{ block_id: 'b1', content_type: 'definition', type_label: '定义', title: '向量', content: '真实讲义正文', knowledge_names: [], answer_to: '' }] }] }], task: { id: 'task-a', status: 'completed', progress: 100 } }
let wrapper: VueWrapper | undefined
const originalRangeBoundingClientRect = Range.prototype.getBoundingClientRect

async function page(path = '/study') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/study/:materialId?', name: 'study', component: StudyView }, { path: '/courses', component: { template: '<div />' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount({ components: { RouterView }, template: '<RouterView />' }, { attachTo: document.body, global: { plugins: [createPinia(), router], stubs: { PersonalHandoutAssistant: true, MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' }, HandoutContentBlock: { template: '<div><slot /></div>' }, HandoutConceptMap: { name: 'HandoutConceptMap', props: ['sections'], template: '<aside class="concept-map-stub"><slot name="actions" /></aside>' }, HandoutTableOfContents: true } } })
  await flushPromises()
  return { wrapper, router }
}
beforeEach(async () => {
  vi.stubGlobal('innerWidth', 1440)
  HTMLElement.prototype.scrollTo = vi.fn(function (this: HTMLElement, options?: ScrollToOptions | number) { if (typeof options === 'object') this.scrollTop = options.top || 0 })
  localStorage.clear()
  vi.clearAllMocks(); sessionStorage.clear(); vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh }))); await setLocale('zh')
  api.config.mockResolvedValue({ local_login_enabled: true }); api.me.mockResolvedValue(user)
  api.courses.mockResolvedValue([]); api.list.mockResolvedValue([]); api.sources.mockResolvedValue([source]); api.get.mockResolvedValue(structuredClone(saved)); api.logout.mockResolvedValue({})
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.replaceChildren(); vi.useRealTimers(); vi.unstubAllGlobals(); if (originalRangeBoundingClientRect) Object.defineProperty(Range.prototype, 'getBoundingClientRect', { configurable: true, value: originalRangeBoundingClientRect }); else delete (Range.prototype as any).getBoundingClientRect })

describe('personal study handouts', () => {
  it('explains input budget failure without retrying or replacing completed text', async () => {
    api.get.mockResolvedValue({ ...structuredClone(saved), status: 'failed', task: { ...saved.task, status: 'failed', error_code: 'generation_budget_exceeded' } })
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-progress').text()).toContain('请求输入超出限制')
    expect(wrapper.get('.study-progress').text()).toContain('重新检查输入并继续')
    expect(wrapper.get('.study-progress').text()).not.toContain('可以主动继续')
    expect(wrapper.get('.study-handout').text()).toContain('真实讲义正文')
    expect(api.resume).not.toHaveBeenCalled()
    expect(api.generate).not.toHaveBeenCalled()
    await setLocale('en'); await flushPromises()
    expect(wrapper.get('.study-progress').text()).toContain('exceeded the input limit')
    expect(wrapper.get('.study-progress').text()).toContain('Check input and continue')
  })

  it.each(['practice', 'mistakes', 'sources', 'concepts'])('ignores removed %s tools and keeps exercises in the handout', async (tab) => {
    sessionStorage.setItem('lingzhi-study-tools:student-a:material-a', JSON.stringify({ tab, open: true }))
    const material = structuredClone(saved)
    material.revisions[0]!.sections[0]!.blocks.push({ block_id: 'q1', content_type: 'exercise', type_label: '练习', title: '自测', content: '请在纸上计算结果', knowledge_names: [], answer_to: '' })
    api.get.mockResolvedValue(material)
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-handout').text()).toContain('请在纸上计算结果')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(true)
    expect(wrapper.findComponent({ name: 'PersonalHandoutPractice' }).exists()).toBe(false)
    for (const locale of ['zh', 'en'] as const) {
      await setLocale(locale); await flushPromises()
      expect(wrapper.findAll('[data-tool]').map(item => item.attributes('data-tool'))).toEqual(['assistant', 'reference', 'paths', 'note'])
    }
  })


  it('does not interpret an unavailable auth configuration as disabled login, and reconnects', async () => {
    api.config.mockRejectedValueOnce(new Error('HTTP 500'))
    const { wrapper } = await page()
    expect(wrapper.text()).toContain('请点击重新连接')
    expect(wrapper.text()).not.toContain('HTTP 500')
    expect(wrapper.text()).not.toContain('本地学生登录未启用')
    expect(wrapper.find('.study-login-card').exists()).toBe(false)
    expect(api.me).not.toHaveBeenCalled()
    await setLocale('en'); await flushPromises()
    expect(wrapper.text()).toContain('Unable to open your study space')
    expect(wrapper.text()).not.toContain('Local student login is disabled')
    api.config.mockResolvedValueOnce({ local_login_enabled: false, development_identity: true })
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    expect(wrapper.find('.study-error').exists()).toBe(false)
  })

  it('enters a guest workspace automatically without a login form or sign-out control', async () => {
    api.config.mockResolvedValue({ local_login_enabled: false, guest_login_enabled: true })
    api.guest.mockResolvedValue({ token: 'guest-session', user: { ...user, guest: true } })
    const { wrapper } = await page()
    expect(api.guest).toHaveBeenCalledTimes(1)
    expect(api.me).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    expect(wrapper.find('.study-login-card').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('退出登录')
    expect(wrapper.get('.study-user').attributes('title')).toContain('清除站点数据')
    await setLocale('en'); await flushPromises()
    expect(wrapper.get('.study-user').text()).toBe('My study space')
    expect(wrapper.text()).not.toContain('Sign out')
  })

  it('shows a retry instead of a password form when automatic entry fails', async () => {
    api.config.mockResolvedValue({ local_login_enabled: false, guest_login_enabled: true })
    api.guest.mockRejectedValueOnce(new Error('暂时无法连接'))
    const { wrapper } = await page()
    expect(wrapper.find('.study-login-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('请点击重新连接')
    api.guest.mockResolvedValueOnce({ token: 'guest-session', user: { ...user, guest: true } })
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    expect(wrapper.find('.study-error').exists()).toBe(false)
  })

  it('keeps development identity connection failures out of the login page', async () => {
    api.config.mockResolvedValue({ local_login_enabled: false, development_identity: true })
    api.me.mockRejectedValueOnce(new Error('HTTP 500'))
    const { wrapper } = await page()
    expect(wrapper.text()).toContain('请点击重新连接')
    expect(wrapper.text()).not.toContain('本地学生登录未启用')
    expect(wrapper.find('.login-story').exists()).toBe(false)
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
  })

  it('renders the student home without secure-context crypto.randomUUID' , async () => {
    vi.stubGlobal('crypto', undefined)
    const { wrapper } = await page()
    expect(wrapper.findComponent({ name: 'StudentLearningHome' }).exists()).toBe(true)
    expect(api.courses).toHaveBeenCalledTimes(1)
  })

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
    await wrapper.get('.study-create-back').trigger('click'); await flushPromises()
    await wrapper.get('.library-filter-tabs > button').trigger('click')
    await wrapper.get('[role=option][data-option-value=teacher]').trigger('click')
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
    expect(wrapper.get('.study-purpose-mobile-hint').text()).toContain('知识脉络')
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.study-purpose-mobile-hint').text()).toContain('考试范围')
  })

  it('uses one generation flow and allows a self-study handout without uploaded sources', async () => {
    api.sources.mockResolvedValueOnce([])
    const { wrapper, router } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-generation-mode]').exists()).toBe(false)
    expect(wrapper.text()).toContain('学习资料（选填）')
    expect(wrapper.findAll('.source-selection')).toHaveLength(0)
    expect(wrapper.text()).toContain('未添加资料，将按课程主题、目标与场景生成讲义。')
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('C语言：面向图像项目')
    await wrapper.get('.study-create textarea').setValue('我想做一个华为成像项目，希望理论结合场景，并安排实战练习。')
    api.generate.mockResolvedValueOnce(saved)
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({
      title: 'C语言：面向图像项目', selections: [],
      requirements: '我想做一个华为成像项目，希望理论结合场景，并安排实战练习。',
    }))
    expect(router.currentRoute.value.params.materialId).toBe('material-a')
  })

  it('shows a clear return action and keeps the course switch out of the create flow', async () => {
    const { wrapper, router } = await page('/study?create=1')
    expect(wrapper.find('.study-home-navigation').exists()).toBe(false)
    expect(wrapper.get('.study-create-back').text()).toContain('返回我的课程')
    await wrapper.get('.study-create-back').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query.create).toBeUndefined()
    expect(wrapper.find('.study-create').exists()).toBe(false)
  })

  it('prevents duplicate submissions and passes the exact selected range and purpose', async () => {
    const { wrapper, router } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    await wrapper.findAll('.source-selection input')[1]!.setValue(true)
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('方程组备考')
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

  it('allows selecting and using more than six material ranges', async () => {
    const manyRanges = { ...source, sections: Array.from({ length: 8 }, (_, index) => ({ id: `blk-${index + 1}`, title: `第${index + 1}章`, characters: 300 })) }
    api.sources.mockResolvedValueOnce([manyRanges])
    const { wrapper } = await page('/study?create=1')
    const checkboxes = wrapper.findAll('.source-selection input')
    expect(checkboxes).toHaveLength(8)
    for (const checkbox of checkboxes) {
      expect((checkbox.element as HTMLInputElement).disabled).toBe(false)
      await checkbox.setValue(true)
    }
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('多章节课程')
    api.generate.mockResolvedValueOnce(saved)
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({ selections: expect.arrayContaining(Array.from({ length: 8 }, (_, index) => ({ asset_id: source.id, section_id: `blk-${index + 1}` }))) }))
  })

  it('moves only the reading scroller when restoring a chapter', async () => {
    const { wrapper } = await page('/study/material-a')
    const scroller = wrapper.get('.study-document-scroll').element as HTMLElement
    const section = wrapper.get('[data-section-id="s1"]').element as HTMLElement
    const outer = wrapper.get('.study-workspace').element as HTMLElement
    const answer = document.createElement('details')
    answer.className = 'handout-block--answer'
    section.append(answer)
    scroller.scrollTop = 100
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    vi.spyOn(scroller, 'getBoundingClientRect').mockReturnValue({ top: 120 } as DOMRect)
    vi.spyOn(section, 'getBoundingClientRect').mockReturnValue({ top: 420 } as DOMRect)
    await wrapper.get('.study-chapter-list button').trigger('click')
    expect(scrollTo).toHaveBeenCalledWith({ top: 376, behavior: 'instant' })
    expect(outer.scrollTop).toBe(0)
    expect(answer.open).toBe(false)
    expect(JSON.parse(sessionStorage.getItem('lingzhi-study-position:student-a:material-a:revision-a')!)).toMatchObject({ sectionId: 's1' })
  })

  it('expands and collapses directory details without moving the reading position', async () => {
    const { wrapper } = await page('/study/material-a')
    const scroller = wrapper.get('.study-document-scroll').element as HTMLElement
    scroller.scrollTop = 200
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    const toggle = wrapper.get('.study-chapter-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click')
    expect(wrapper.find('.study-block-list').exists()).toBe(false)
    expect(scrollTo).not.toHaveBeenCalled()
    expect(scroller.scrollTop).toBe(200)
    await toggle.trigger('click')
    expect(wrapper.get('.study-block-list').text()).toContain('向量')
    await wrapper.get('.study-chapter-search input').setValue('第一章')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('keeps directory titles clean while allowing search by localized teaching type', async () => {
    const material = structuredClone(saved)
    material.revisions[0]!.sections[0]!.blocks[0]!.title = '练习中的概念'
    api.get.mockResolvedValue(material)
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.find('.study-block-tag').exists()).toBe(false)
    expect(wrapper.get('.study-block-list').text()).toBe('练习中的概念')
    await wrapper.get('.study-chapter-search input').setValue('定义')
    expect(wrapper.find('.study-block-list').exists()).toBe(true)
    await wrapper.get('.study-chapter-search input').setValue('')
    await setLocale('en'); await flushPromises()
    expect(wrapper.find('.study-block-tag').exists()).toBe(false)
    expect(wrapper.get('.study-block-list').text()).toBe('练习中的概念')
  })



  it('opens the assistant on demand and binds a real reading selection to the exact owned block', async () => {
    const { wrapper } = await page('/study/material-a')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(true)
    await wrapper.get('[data-tool="assistant"]').trigger('click')
    expect(wrapper.get('.study-reading-tools').isVisible()).toBe(true)
    const assistant = wrapper.getComponent({ name: 'PersonalHandoutAssistant' })
    expect(assistant.props()).toMatchObject({ ownerId: 'student-a', materialId: 'material-a', revisionId: 'revision-a', context: { section_id: 's1', block_id: '', quote: '' } })
    const body = wrapper.get('[data-block-id="b1"]').element
    Object.defineProperty(Range.prototype, 'getBoundingClientRect', { configurable: true, value: () => new DOMRect(240, 280, 160, 20) })
    const range = document.createRange(); range.selectNodeContents(body)
    const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range)
    await wrapper.get('.study-document-scroll').trigger('pointerup')
    expect(assistant.props('context')).toMatchObject({ section_id: 's1', section_title: '第一章', block_id: 'b1', block_title: '向量', quote: '真实讲义正文' })
    const toolbar = document.body.querySelector<HTMLElement>('.study-selection-actions')
    expect(toolbar).not.toBeNull()
    expect(toolbar?.getAttribute('role')).toBe('toolbar')
    expect(toolbar?.style.top).toBe('272px')
    expect(toolbar?.querySelectorAll('button')).toHaveLength(5)
    expect(toolbar?.textContent).toContain('写批注')
    expect(toolbar?.textContent).toContain('记疑问')
    document.body.querySelector<HTMLButtonElement>('[data-selection-action="clear"]')?.click()
    await flushPromises()
    expect(assistant.props('context')).toMatchObject({ block_id: '', quote: '' })
    const secondRange = document.createRange(); secondRange.selectNodeContents(body)
    selection.removeAllRanges(); selection.addRange(secondRange)
    await wrapper.get('.study-document-scroll').trigger('pointerup')
    document.body.querySelector<HTMLButtonElement>('[data-selection-action="ask"]')?.click()
    await flushPromises()
    expect(document.body.querySelector('.study-selection-actions')).toBeNull()
    expect(assistant.props('context')).toMatchObject({ block_id: 'b1', quote: '真实讲义正文' })
    document.body.querySelector<HTMLButtonElement>('[data-tool="note"]')?.click()
    await flushPromises()
    expect(wrapper.get('#study-panel-note').attributes('role')).toBe('region')
    selection.removeAllRanges()
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
    expect(wrapper.text()).toContain('Study materials (optional)')
    expect(wrapper.text()).toContain('Materials optional')
    expect(wrapper.text()).toContain('Systematic learning')
    expect(wrapper.text()).toContain('Exam preparation')
    expect(wrapper.text()).toContain('Generate course handout')
    expect(wrapper.text()).not.toContain('预计阅读时间')
  })

  it('retries the same submission id after a lost response but uses a new id for changed input', async () => {
    const { wrapper } = await page()
    await wrapper.find('[data-testid="student-create-handout"]').trigger('click'); await flushPromises()
    await wrapper.find('.source-selection input').setValue(true)
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('原讲义')
    api.generate.mockRejectedValue(new Error('连接中断'))
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    const originalId = api.generate.mock.calls[0]![0].request_id
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate.mock.calls[1]![0].request_id).toBe(originalId)
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('修改后的讲义')
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
    expect(wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').element).toHaveProperty('value', '')
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
    expect(wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').element).toHaveProperty('value', 'my-course')
    expect(wrapper.findAll('.source-selection input').some(input => (input.element as HTMLInputElement).checked)).toBe(false)
    expect(wrapper.find('.study-generation-issue').exists()).toBe(false)
    for (const input of wrapper.findAll('.source-selection input')) await input.setValue(true)
    api.generate.mockResolvedValueOnce(saved)
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({ purpose: 'systematic', selections: [{ asset_id: 'mat-123', section_id: 'blk-1' }, { asset_id: 'mat-123', section_id: 'blk-3' }] }))
  })

  it('accepts uploads above the former size cap and keeps materials optional', async () => {
    sessionStorage.setItem('lingzhi-study-draft:student-a', JSON.stringify({ form: { title: 'Old draft', generation_mode: 'materials' }, selectedRanges: [] }))
    const { wrapper } = await page('/study?create=1')
    const file = new File(['data'], 'too-large.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: 51 * 1024 * 1024 })
    api.upload.mockResolvedValueOnce({ ...source, filename: file.name })
    const input = wrapper.get('.study-upload-input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change'); await flushPromises()
    expect(api.upload).toHaveBeenCalledExactlyOnceWith(file)
    expect(wrapper.text()).not.toContain('50 MB')
    expect(wrapper.find('[data-generation-mode]').exists()).toBe(false)
    await wrapper.get('form.study-create').trigger('submit'); await flushPromises()
    expect(api.generate).toHaveBeenCalledWith(expect.objectContaining({ title: 'Old draft', selections: [] }))
  })

  it('restores the create URL and selected source ranges after returning from a saved course', async () => {
    const { wrapper, router } = await page('/study?create=1')
    await wrapper.findAll('.source-selection input')[0]!.setValue(true)
    await wrapper.findAll('.study-purpose-options button')[1]!.trigger('click')
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('自建课程草稿')
    await router.push('/study/material-a'); await flushPromises()
    await router.push('/study?create=1'); await flushPromises()
    expect(wrapper.find('form.study-create').exists()).toBe(true)
    expect(wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').element).toHaveProperty('value', '自建课程草稿')
    expect(wrapper.find('[data-generation-mode]').exists()).toBe(false)
    expect((wrapper.findAll('.source-selection input')[0]!.element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('explains unavailable draft ranges and removes only invalid or duplicate selections', async () => {
    sessionStorage.setItem('lingzhi-study-draft:student-a', JSON.stringify({ form: { title: '保留的课程', purpose: 'exam_prep', generation_mode: 'materials', requirements: '保留目标' }, selectedRanges: ['mat-123:blk-1', 'missing:deleted', 'mat-123:blk-1'] }))
    const { wrapper } = await page('/study?create=1')
    expect(wrapper.get('.study-generation-issue').text()).toContain('已不可用')
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeDefined()
    await wrapper.get('.study-range-recovery button').trigger('click')
    expect(wrapper.find('.study-range-recovery').exists()).toBe(false)
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeUndefined()
    expect(wrapper.findAll('.source-selection input').map(input => (input.element as HTMLInputElement).checked)).toEqual([true, false])
    expect(wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').element).toHaveProperty('value', '保留的课程')
    expect(wrapper.get('.study-create textarea').element).toHaveProperty('value', '保留目标')
    expect(wrapper.findAll('.study-purpose-options button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('shows the missing title or invalid reading time instead of a silent disabled action', async () => {
    const { wrapper } = await page('/study?create=1')
    expect(wrapper.get('.study-generation-issue').text()).toContain('课程主题')
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('系统学习课程')
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
    await wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').setValue('未丢失的输入')
    api.list.mockResolvedValue([])
    await wrapper.get('.study-error button').trigger('click'); await flushPromises()
    expect(wrapper.find('.study-error').exists()).toBe(false)
    expect(wrapper.find('form.study-create').exists()).toBe(true)
    expect(wrapper.get('input[placeholder="例如：C语言：面向图像项目"]').element).toHaveProperty('value', '未丢失的输入')
    expect(wrapper.get('.study-generate-bar button').attributes('disabled')).toBeUndefined()
    expect(api.generate).not.toHaveBeenCalled()
  })


})


it.each(['direct', 'materials'])('offers the same concept recovery for %s handouts', async generation_mode => {
  api.get.mockResolvedValue({ ...structuredClone(saved), generation_mode, concepts_complete: false })
  const { wrapper } = await page('/study/material-a')
  await wrapper.get('[data-tool="paths"]').trigger('click')
  expect(wrapper.text()).toContain('部分阅读辅助尚未整理或已过期')
  expect(wrapper.text()).not.toContain('当前没有资料来源关系图')
  const resume = wrapper.findAll('button').find(button => button.text() === '补齐缺失内容与阅读辅助')!
  await resume.trigger('click'); await flushPromises()
  expect(api.resume).toHaveBeenCalledWith('material-a')
  expect(wrapper.text()).toContain('真实讲义正文')
  await setLocale('en'); await flushPromises()
  expect(wrapper.text()).toContain('Some reading aids are missing or outdated')
  expect(wrapper.text()).toContain('Complete missing content and reading aids')
})

it('keeps a partial concept map visible during generation without offering a duplicate run', async () => {
  const partial = { ...structuredClone(saved), concepts_complete: false,
    plans: [{ node_id: 's1', knowledge_structure: [{ knowledge_points: [{ name: '向量' }] }] }],
    task: { ...saved.task, status: 'running' } }
  api.get.mockResolvedValue(partial)
  const { wrapper } = await page('/study/material-a')
  expect(wrapper.text()).not.toContain('正在整理思维链')
  await wrapper.get('[data-tool="paths"]').trigger('click')
  expect(wrapper.find('.concept-map-stub').exists()).toBe(true)
  expect(wrapper.findAll('button').some(button => button.text() === '补齐缺失内容与阅读辅助')).toBe(false)
})


it('continues the upload batch after a rejected file and identifies the failed file', async () => {
  const { wrapper } = await page('/study?create=1')
  const failed = new File(['bad'], '损坏.pdf', { type: 'application/pdf' })
  const valid = new File(['# 正文'], '可用.md', { type: 'text/markdown' })
  api.upload.mockRejectedValueOnce(new Error('无法解析文件')).mockResolvedValueOnce({ ...source, id: 'mat-new', filename: valid.name })
  const input = wrapper.get('.study-upload-input')
  Object.defineProperty(input.element, 'files', { value: [failed, valid], configurable: true })
  await input.trigger('change'); await flushPromises()
  expect(api.upload).toHaveBeenNthCalledWith(2, valid)
  expect(wrapper.text()).toContain('可用.md')
  expect(wrapper.get('.study-error').text()).toContain('损坏.pdf')
  expect(wrapper.get('.study-error').text()).toContain('无法解析文件')
})




it('stops a batch immediately when the student session expires', async () => {
  const { StudyApiError } = await import('@/api/study')
  const { wrapper } = await page('/study?create=1')
  api.upload.mockRejectedValueOnce(new StudyApiError(401, '登录已失效'))
  const input = wrapper.get('.study-upload-input')
  Object.defineProperty(input.element, 'files', { value: [new File(['a'], 'a.md'), new File(['b'], 'b.md')], configurable: true })
  await input.trigger('change'); await flushPromises()
  expect(api.upload).toHaveBeenCalledTimes(1)
  expect(wrapper.find('form.study-create').exists()).toBe(false)
})






it('restores reading preferences for the current student', async () => {
  localStorage.setItem('lingzhi-study-reading:student-a', JSON.stringify({ size: 21, font: 'sans' }))
  const { wrapper } = await page('/study/material-a')
  expect(wrapper.get('.study-handout').attributes('style')).toContain('21px')
  expect(wrapper.get('.study-handout').attributes('style')).toContain('var(--handout-sans)')
  await wrapper.get('input[type="range"]').setValue(20)
  expect(JSON.parse(localStorage.getItem('lingzhi-study-reading:student-a')!)).toEqual({ size: 20, font: 'sans' })
})


it('keeps reference filters and reading position across tools, but clears them for another material', async () => {
  const { wrapper, router } = await page('/study/material-a')
  await wrapper.get('[data-tool="reference"]').trigger('click')
  await wrapper.get('.aid-search-toggle').trigger('click')
  await wrapper.get('.handout-reference .aid-toolbar input').setValue('向量')
  const results = wrapper.get('.reference-results').element
  results.scrollTop = 180
  await wrapper.get('.reference-results').trigger('scroll')
  await wrapper.get('[data-tool="note"]').trigger('click')
  expect(wrapper.find('.handout-reference').exists()).toBe(false)
  await wrapper.get('[data-tool="reference"]').trigger('click'); await flushPromises()
  expect(wrapper.get('.handout-reference .aid-toolbar input').element).toHaveProperty('value', '向量')
  expect(wrapper.find('.aid-scope-toggle').exists()).toBe(false)
  expect(wrapper.get('.reference-results').element.scrollTop).toBe(180)
  await wrapper.get('.study-tool-heading button').trigger('click')
  await wrapper.get('[data-tool="reference"]').trigger('click')
  expect(wrapper.get('.handout-reference .aid-toolbar input').element).toHaveProperty('value', '向量')
  api.get.mockResolvedValue({ ...structuredClone(saved), id: 'material-b' })
  await router.push('/study/material-b'); await flushPromises()
  await wrapper.get('[data-tool="reference"]').trigger('click')
  expect(wrapper.find('.aid-toolbar input').exists()).toBe(false)
  expect(wrapper.find('.aid-scope-toggle').exists()).toBe(false)
})

it('renders formulas in reading titles and directory labels instead of exposing delimiters', async () => {
  const material = structuredClone(saved)
  material.title = '理解 $h=0$'
  material.revisions[0]!.sections[0]!.title = '条件 $h\\ne0$'
  material.revisions[0]!.sections[0]!.blocks[0]!.title = '关于 $h=0$ 的常见错误'
  api.get.mockResolvedValue(material)
  const { wrapper } = await page('/study/material-a')
  expect(wrapper.get('h1').find('.katex').exists()).toBe(true)
  expect(wrapper.get('.study-chapter-title').find('.katex').exists()).toBe(true)
  const block = wrapper.get('.study-block-list button')
  expect(block.find('.katex').exists()).toBe(true)
  expect(block.text()).not.toContain('$')
})




it('keeps notes in the four-tool tab bar without a duplicate bottom shortcut', async () => {
  const { wrapper } = await page('/study/material-a')
  expect(wrapper.findAll('.study-tool-tabs [role="tab"]').map(b=>b.attributes('data-tool'))).toEqual(['assistant','reference','paths','note'])
  expect(wrapper.find('#study-reasoning-panel').exists()).toBe(false)
  expect(wrapper.get('.study-bottom-bar').text()).toContain('第一章')
  expect(wrapper.find('.study-bottom-bar [data-bottom-tool="note"]').exists()).toBe(false)
  expect(wrapper.find('.study-note-add').exists()).toBe(false)
  await wrapper.get('[data-tool="note"]').trigger('click'); await flushPromises()
  expect(wrapper.findComponent({name:'ReadingNotesPanel'}).exists()).toBe(true)
  expect(wrapper.get('#study-panel-note').attributes('role')).toBe('region')
  expect(wrapper.find('.notes-legacy').exists()).toBe(false)
  expect(wrapper.find('.study-note textarea').exists()).toBe(false)
  await wrapper.get('[data-tool="reference"]').trigger('click'); await flushPromises()
  expect(wrapper.find('.aid-scope-toggle').exists()).toBe(false)
  expect(wrapper.get('[data-tool="reference"]').attributes('aria-selected')).toBe('true')
})
