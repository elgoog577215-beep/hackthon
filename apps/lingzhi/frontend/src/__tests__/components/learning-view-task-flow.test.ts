import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import LearningView from '@/views/LearnerCourseView.vue'
import { useAITeacherStore } from '@/stores/aiTeacher'
import { useChangeProposalsStore } from '@/stores/changeProposals'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useGenerationStore } from '@/stores/generation'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useNoteStore } from '@/stores/notes'
import { useCompanionPreferencesStore } from '@/stores/companionPreferences'
import { getLearnerIdentity } from '@/utils/http'
import type { Node } from '@/stores/types'

const node: Node = {
  node_id: 'n1', parent_node_id: 'chapter-1', node_name: '向量空间', node_level: 2,
  node_content: '正文', node_type: 'original', generation_status: 'completed', generated_chars: 2,
}

const ContentAreaStub = defineComponent({
  props: { readOnly: Boolean },
  emits: ['startPractice'],
  setup(_, { emit }) {
    return {
      open: () => emit('startPractice', node),
      openTargeted: () => emit('startPractice', node, 'qr-targeted'),
    }
  },
  template: '<div id="content-scroll-container" :data-read-only="readOnly"><button id="practice-block-n1" class="open-practice" @click="open">open</button><button class="open-targeted-practice" @click="openTargeted">targeted</button></div>',
})

const NotesPanelStub = defineComponent({
  name: 'NotesPanel',
  props: { mode: String },
  emits: ['close', 'locate', 'viewDetail'],
  template: '<aside class="notes-panel-stub" :data-mode="mode"><button class="close-notes" @click="$emit(\'close\')">close notes</button></aside>',
})

const growthScrollSpy = vi.fn()
const GrowthContentAreaStub = defineComponent({
  setup(_, { expose }) {
    expose({ scrollToCourseBlock: growthScrollSpy })
  },
  template: '<div id="content-scroll-container"></div>',
})

const GrowthSideAIPanelStub = defineComponent({
  emits: ['close', 'courseApplied'],
  setup(_, { emit }) {
    return {
      applyGrowth: () => emit('courseApplied', {
        planId: 'plan-growth',
        affectedSectionIds: ['n1'],
        appliedBlockIds: ['growth-animation'],
        operationIds: ['operation-animation'],
        targetSectionId: 'n1',
        targetBlockId: 'growth-animation',
        targetOperationId: 'operation-animation',
      }),
    }
  },
  template: '<aside class="growth-ai-panel"><button class="apply-growth" @click="applyGrowth">应用课程生长</button></aside>',
})

const TaskOverlayStub = defineComponent({
  props: ['courseId', 'nodeId', 'nodeLabel', 'originRect'],
  emits: ['close', 'graded', 'askTeacher', 'records', 'stats', 'outline', 'lesson-plan', 'course', 'ppt'],
  template: '<div class="task-overlay-stub" :data-node-id="nodeId" :data-origin-top="originRect?.top"><span>{{ nodeLabel }}</span><button class="task-records" @click="$emit(\'records\')">records</button><button class="task-stats" @click="$emit(\'stats\')">stats</button><button class="close-task" @click="$emit(\'close\')">close</button></div>',
})

const LearningStatsStub = defineComponent({
  props: {
    closable: Boolean,
  },
  emits: ['close'],
  template: '<div class="learning-stats-stub" :data-closable="closable"><button class="close-stats" @click="$emit(\'close\')">close stats</button></div>',
})

describe('LearningView 正文任务覆盖层', () => {
  it('opens passage help beside the text and expands the same panel without reopening its request', async () => {
    const content = defineComponent({
      emits: ['studyDialogue'],
      template: `<div id="content-scroll-container"><button class="ask-inline" @click="$emit('studyDialogue', {kind:'explain',nodeId:'n1',quote:'原文',anchor:{block_id:'b1'}})">ask</button><div data-study-companion-anchor data-study-node-id="n1" data-study-block-id="b1"></div></div>`,
    })
    const panel = defineComponent({ props: ['studyRequest'], setup() { return { draft: ref('') } },
      template: '<aside class="same-study-panel"><textarea v-model="draft" /><span>{{studyRequest?.quote}}</span></aside>' })
    const wrapper = mount(LearningView, { attachTo: document.body, global: {
      plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
      stubs: { ContentArea: content, SideAIPanel: panel, CourseNavigator: true, LearningCompanion: true,
        LearningTaskOverlay: true, LearningStats: true, NotesPanel: true, CourseKnowledgeStudy: true },
    } })
    try {
      await flushPromises(); await wrapper.get('.ask-inline').trigger('click'); await flushPromises()
      const anchor = wrapper.get('[data-study-companion-anchor]')
      const original = anchor.get('.same-study-panel').element
      await anchor.get('textarea').setValue('还没发出的追问')
      const request = wrapper.findComponent(panel).props('studyRequest')
      const loadCount = vi.mocked(useAITeacherStore().load).mock.calls.length
      await anchor.get('[data-testid="companion-expand"]').trigger('click'); await flushPromises()
      expect(wrapper.findComponent(panel).element).toBe(original)
      expect(wrapper.findComponent(panel).props('studyRequest')).toBe(request)
      expect(wrapper.findComponent(panel).get('textarea').element).toHaveProperty('value', '还没发出的追问')
      document.querySelector<HTMLButtonElement>('[data-testid="companion-return-inline"]')!.click(); await flushPromises()
      expect(anchor.get('.same-study-panel').element).toBe(original)
      expect(useAITeacherStore().load).toHaveBeenCalledTimes(loadCount)
    } finally { wrapper.unmount() }
  })
  it('opens the original mistake notebook and retries the exact question in the existing practice workspace', async () => {
    const router = (globalThis as any).__learningTestRouter
    const pinia = (globalThis as any).__learningTestPinia
    const workspace = useCourseWorkspaceStore()
    const prepare = vi.spyOn(workspace, 'preparePracticeTask')
    const mistakes = defineComponent({
      name: 'MistakeNotebookPanel', props: ['courseId'], emits: ['close', 'retry'],
      template: '<div class="original-mistakes" :data-course="courseId"><button @click="$emit(\'retry\', { nodeId: \'n1\', taskRevisionId: \'qr1\' })">Retry original question</button></div>',
    })
    const wrapper = mount(LearningView, { global: { plugins: [pinia, router], stubs: {
      ContentArea: ContentAreaStub, CourseNavigator: true, LearningTaskOverlay: TaskOverlayStub,
      LearningStats: LearningStatsStub, MistakeNotebookPanel: mistakes, NotesPanel: NotesPanelStub,
      SideAIPanel: true, CourseKnowledgeStudy: true, LearningCompanion: true, Teleport: true,
    } } })
    try {
      await flushPromises()
      await wrapper.get('[data-domain="mistakes"]').trigger('click'); await flushPromises()
      expect(wrapper.get('.original-mistakes').attributes('data-course')).toBe('c1')
      await wrapper.get('.original-mistakes button').trigger('click'); await flushPromises()
      expect(prepare).toHaveBeenCalledWith('c1', 'n1', 'qr1')
      expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
      expect(wrapper.find('.original-mistakes').exists()).toBe(false)
      await wrapper.get('[data-domain="notebook"]').trigger('click')
      expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
      expect(wrapper.find('.notebook-side-panel').isVisible()).toBe(true)
    } finally { wrapper.unmount() }
  })

  it.each(['overview', 'practice'])('restores %s from the URL and returns to the handout without losing the student return link', async tool => {
    const router = (globalThis as any).__learningTestRouter
    if (tool === 'practice') useCourseStore().currentNode = null
    await router.replace({ path: '/course/c1/learn', query: { tool, returnTo: '/study?view=courses' } })
    const wrapper = mount(LearningView, { global: { plugins: [(globalThis as any).__learningTestPinia, router], stubs: {
      ContentArea: ContentAreaStub, CourseNavigator: true, LearningTaskOverlay: TaskOverlayStub,
      LearningStats: LearningStatsStub, NotesPanel: NotesPanelStub, SideAIPanel: true,
      CourseKnowledgeStudy: true, LearningCompanion: true, Teleport: true,
    } } })
    try {
      await flushPromises()
      const panel = tool === 'overview' ? '.stats-overlay' : '.task-overlay-stub'
      expect(wrapper.find(panel).exists()).toBe(true)
      expect(useChangeProposalsStore().fetchChangeProposals).not.toHaveBeenCalled()
      await wrapper.get('[data-domain="reading"]').trigger('click'); await flushPromises()
      expect(wrapper.find(panel).exists()).toBe(false)
      expect(router.currentRoute.value.query.tool).toBe('reading')
      expect(router.currentRoute.value.query.returnTo).toBe('/study?view=courses')
    } finally { wrapper.unmount() }
  })
  beforeEach(async () => {
    localStorage.removeItem('lingzhi-companion-layout')
    sessionStorage.removeItem('lingzhi-learning-ai-open')
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    const pinia = createPinia()
    setActivePinia(pinia)
    const companionPreferences=useCompanionPreferencesStore()
    companionPreferences.ready=true;companionPreferences.owner=getLearnerIdentity();companionPreferences.mode='gentle'
    vi.spyOn(companionPreferences,'load').mockResolvedValue(undefined)
    vi.spyOn(companionPreferences,'loadSuppressions').mockResolvedValue(undefined)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: LearningView },
        { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
        { path: '/course/:courseId/ppt', name: 'ppt-workspace', component: { template: '<div />' } },
      ],
    })
    await router.push('/course/c1/learn/n1')
    await router.isReady()
    ;(globalThis as any).__learningTestRouter = router
    ;(globalThis as any).__learningTestPinia = pinia
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })

    const course = useCourseStore()
    course.currentCourseId = 'c1'
    course.nodes = [node]
    course.courseTree = [node]
    course.currentNode = node
    course.courseList = [{ course_id: 'c1', course_name: '线性代数', node_count: 1 }]
    vi.spyOn(course, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(course, 'loadCourse').mockResolvedValue(undefined)
    vi.spyOn(course, 'scrollToNode').mockImplementation(() => undefined)

    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'c1', plan: {}, quality_report: {},
      course_availability: { schema_version: 'course_learning_availability_v1', mode: 'standard', reason_code: 'ready', capabilities: {} },
      assets: { questions: [{ asset_id: 'q1', revision_id: 'qr1', node_id: 'n1' }] },
    }
    vi.spyOn(workspace, 'loadAssets').mockResolvedValue(workspace.assets)
    vi.spyOn(workspace, 'checkPracticeAvailability').mockResolvedValue(false)
    vi.spyOn(workspace, 'migrateLegacyPracticeData').mockResolvedValue(undefined)
    vi.spyOn(workspace, 'loadMistakeBook').mockResolvedValue({ attempts: [] } as any)

    const notes = useNoteStore()
    vi.spyOn(notes, 'loadCourseRecords').mockResolvedValue([])
    const progress = useLearningProgressStore()
    vi.spyOn(progress, 'load').mockResolvedValue(null)
    vi.spyOn(progress, 'loadRuntime').mockResolvedValue(null)
    vi.spyOn(progress, 'startNode').mockResolvedValue(null)
    const ai = useAITeacherStore()
    vi.spyOn(ai, 'load').mockResolvedValue(undefined)
    const generation = useGenerationStore()
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    vi.spyOn(generation, 'observeCourse').mockImplementation(() => undefined)
    vi.spyOn(useChangeProposalsStore(), 'fetchChangeProposals').mockResolvedValue(undefined)
  })

  it('returns from the knowledge tree to the saved reading position, but respects an explicit outline selection', async()=>{
    const router=(globalThis as any).__learningTestRouter
    await router.replace({path:'/course/c1/learn/n1',query:{returnTo:'/study?view=courses'}})
    const second={...node,node_id:'n2',node_name:'第二讲'}
    useCourseStore().nodes=[node,second]
    const wrapper=mount(LearningView,{attachTo:document.body,global:{plugins:[(globalThis as any).__learningTestPinia,(globalThis as any).__learningTestRouter],stubs:{
      ContentArea:ContentAreaStub, LearningTaskOverlay:TaskOverlayStub, LearningStats:LearningStatsStub,
      CourseKnowledgeStudy:defineComponent({emits:['close'],template:'<button class="back-reading" @click="$emit(\'close\')">返回讲义</button>'}),
      CourseNavigator:defineComponent({emits:['select'],setup:()=>({second}),template:'<button class="select-second" @click="$emit(\'select\',second)">第二讲</button>'}),
      NotesPanel:NotesPanelStub,SideAIPanel:{template:'<aside class="ai-panel-stub" />'},Teleport:true,
    }}})
    await flushPromises()
    const content=wrapper.get('#content-scroll-container').element as HTMLElement
    content.scrollTop=315
    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    expect(wrapper.get('[data-domain="knowledge-library"]').attributes('aria-current')).toBe('page')
    content.scrollTop=0
    await wrapper.get('.back-reading').trigger('click');await flushPromises()
    expect(content.scrollTop).toBe(315)
    expect(useCourseStore().currentNode?.node_id).toBe('n1')
    expect(wrapper.get('.learning-side-panel').isVisible()).toBe(false)
    expect(wrapper.find('.reading-side-tabs').exists()).toBe(false)
    content.scrollTop=510
    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    content.scrollTop=0
    await wrapper.get('.select-second').trigger('click');await flushPromises()
    expect(useCourseStore().showKnowledgeLibrary).toBe(false)
    expect(useCourseStore().currentNode?.node_id).toBe('n2')
    expect(content.scrollTop).toBe(0)
    expect(router.currentRoute.value.query.returnTo).toBe('/study?view=courses')
    expect(router.currentRoute.value.params.nodeId).toBe('n2')
    await wrapper.get('[data-domain="question-book"]').trigger('click');await flushPromises()
    await wrapper.get('.select-second').trigger('click');await flushPromises()
    expect(router.currentRoute.value.query.tool).toBe('practice')
    expect(router.currentRoute.value.params.nodeId).toBe('n2')
    expect(router.currentRoute.value.query.returnTo).toBe('/study?view=courses')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it.each([false, true])('shows the first-use greeting only in a loaded learner course (teacher preview: %s)', async preview => {
    const router = (globalThis as any).__learningTestRouter
    if (preview) await router.replace('/course/c1/learn/n1?teacherPreview=1')
    useCourseStore().currentCourseProjection = 'published'
    const wrapper = mount(LearningView, { global: {
      plugins: [(globalThis as any).__learningTestPinia, router],
      stubs: { ContentArea: ContentAreaStub, CourseNavigator: true, LearningTaskOverlay: TaskOverlayStub,
        LearningStats: LearningStatsStub, CourseKnowledgeStudy: true, NotesPanel: NotesPanelStub,
        SideAIPanel: true, Teleport: true },
    } })
    await flushPromises()
    expect(wrapper.findComponent({ name:'LearningCompanion' }).props('welcome')).toBe(!preview)
    if(!preview){wrapper.findComponent(ContentAreaStub).vm.$emit('quoteAsk',{text:'问题',nodeId:'n1'});await flushPromises();expect(wrapper.findComponent({name:'LearningCompanion'}).props('welcome')).toBe(false)}
    if (preview) expect(useCourseStore().fetchCourseList).not.toHaveBeenCalled()
    else expect(useCourseStore().fetchCourseList).toHaveBeenCalledWith({ surface: 'student', background: true })
    wrapper.unmount()
  })

  it('助手、笔记与正文切换保留输入；练习和概况不遮住助手与底栏', async () => {
    const StatefulAssistant = defineComponent({
      name: 'SideAIPanel',
      props: ['visible'],
      setup() { return { draft: ref('') } },
      template: '<aside class="ai-panel-stub"><textarea v-model="draft" /></aside>',
    })
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub, CourseNavigator: true,
          LearningTaskOverlay: TaskOverlayStub, LearningStats: LearningStatsStub, CourseKnowledgeStudy: true,
          NotesPanel: NotesPanelStub, SideAIPanel: StatefulAssistant,
          Teleport: false,
        },
      },
    })
    await flushPromises()
    expect(wrapper.find('.reading-side-tabs').exists()).toBe(false)
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(false)
    const pet = new DOMWrapper(document.querySelector('.learning-companion') as HTMLElement)
    expect(pet.isVisible()).toBe(true)
    await pet.get('[data-testid="companion-dock"]').trigger('click')
    expect(pet.find('[data-testid="companion-open"]').exists()).toBe(false)
    await pet.get('[data-testid="companion-restore"]').trigger('click')
    await pet.get('[data-testid="companion-open"]').trigger('click')
    expect(pet.isVisible()).toBe(true)
    expect(pet.get('[data-testid="companion-open"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(true)
    await wrapper.get('.ai-panel-stub textarea').setValue('保留这段草稿')
    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(false)
    expect(pet.isVisible()).toBe(true)
    expect(document.activeElement).toBe(pet.get('[data-testid="companion-open"]').element)
    expect(wrapper.get('.learning-side-panel').isVisible()).toBe(false)
    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect((wrapper.get('.ai-panel-stub textarea').element as HTMLTextAreaElement).value).toBe('保留这段草稿')
    await wrapper.get('[data-domain="notebook"]').trigger('click')
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(false)
    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(wrapper.get('.notebook-side-panel').isVisible()).toBe(false)
    expect((wrapper.get('.ai-panel-stub textarea').element as HTMLTextAreaElement).value).toBe('保留这段草稿')
    const originalComposer = wrapper.get('.ai-panel-stub textarea').element
    const assistant = wrapper.findComponent(StatefulAssistant)
    assistant.vm.$emit('toggleMode')
    await flushPromises()
    const floatingPanel = new DOMWrapper(document.querySelector('.companion-modal-window') as HTMLElement)
    expect(floatingPanel.isVisible()).toBe(true)
    expect((floatingPanel.get('textarea').element as HTMLTextAreaElement).value).toBe('保留这段草稿')
    expect(wrapper.attributes('inert')).toBeUndefined()
    // Closing must leave the same input in the hidden floating host, without a docked frame.
    assistant.vm.$emit('close')
    await flushPromises()
    expect(floatingPanel.isVisible()).toBe(false)
    expect(floatingPanel.get('textarea').element).toBe(originalComposer)
    expect(wrapper.find('.ai-panel-stub').exists()).toBe(false)
    expect(localStorage.getItem('lingzhi-companion-layout')).toBe('floating')
    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(floatingPanel.isVisible()).toBe(true)
    expect((floatingPanel.get('textarea').element as HTMLTextAreaElement).value).toBe('保留这段草稿')
    assistant.vm.$emit('toggleMode')
    await flushPromises()
    expect(wrapper.get('.ai-panel-stub textarea').element).toBe(originalComposer)
    expect((wrapper.get('.ai-panel-stub textarea').element as HTMLTextAreaElement).value).toBe('保留这段草稿')
    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.learning-stage .task-overlay-stub').exists()).toBe(true)
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(true)
    expect(wrapper.get('[data-domain="assistant"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-domain="question-book"]').attributes('aria-current')).toBe('page')
    expect(wrapper.find('.learning-stage .learning-dock').exists()).toBe(false)
    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(false)
    await wrapper.get('[data-domain="overview"]').trigger('click')
    expect(wrapper.find('.learning-stage .stats-overlay').exists()).toBe(true)
    expect(wrapper.get('.ai-panel-stub').isVisible()).toBe(true)
    await wrapper.get('[data-domain="overview"]').trigger('click')
    expect(wrapper.find('.stats-overlay').exists()).toBe(false)
    useCourseStore().isFocusMode = true
    await flushPromises()
    expect(pet.isVisible()).toBe(false)
    wrapper.unmount()
  })

  it.each(['floating', 'docked'])('restores the %s layout on remount and preserves it across course changes', async layout => {
    localStorage.setItem('lingzhi-companion-layout', layout)
    const Assistant = defineComponent({
      props: ['floating'],
      template: '<aside class="layout-assistant" :data-floating="floating" />',
    })
    const createView = () => mount(LearningView, { attachTo: document.body, global: {
      plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
      stubs: { ContentArea: ContentAreaStub, CourseNavigator: true, LearningTaskOverlay: TaskOverlayStub,
        LearningStats: LearningStatsStub, CourseKnowledgeStudy: true, NotesPanel: NotesPanelStub,
        SideAIPanel: Assistant, Teleport: false },
    } })
    for (let attempt = 0; attempt < 2; attempt++) {
      const wrapper = createView()
      await flushPromises()
      await wrapper.get('[data-domain="assistant"]').trigger('click')
      const panel = new DOMWrapper(document.querySelector('.layout-assistant') as HTMLElement)
      expect(panel.isVisible()).toBe(true)
      expect(panel.attributes('data-floating')).toBe(String(layout === 'floating'))
      useCourseStore().currentCourseId = `c${attempt + 2}`
      await flushPromises()
      expect(wrapper.findComponent(Assistant).props('floating')).toBe(layout === 'floating')
      wrapper.unmount()
    }
  })

  it('从正文打开任务并在关闭后恢复原滚动位置', async () => {
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningDock: true,
          LearningStats: LearningStatsStub, CourseKnowledgeStudy: true,
          MistakeNotebookPanel: { template: '<div class="mistake-notebook-stub">错题本</div>' },
          NotesPanel: NotesPanelStub,
          SideAIPanel: true,
          Transition: false,
        },
      },
    })
    await flushPromises()
    const content = wrapper.get('#content-scroll-container').element as HTMLElement
    const trigger = wrapper.get('.open-practice').element as HTMLElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      top: 120, left: 240, right: 840, bottom: 232, width: 600, height: 112,
      x: 240, y: 120, toJSON: () => ({}),
    })
    content.scrollTop = 315

    trigger.focus()
    await wrapper.get('.open-practice').trigger('click')
    expect(wrapper.get('.task-overlay-stub').text()).toContain('向量空间')
    expect(wrapper.get('.task-overlay-stub').attributes('data-origin-top')).toBe('120')

    content.scrollTop = 0
    await wrapper.get('.close-task').trigger('click')
    await flushPromises()
    expect(content.scrollTop).toBe(315)
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
  })

  it('正文页移除重复产物导航，并从正文和底栏进入学习工具', async () => {
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: LearningStatsStub, CourseKnowledgeStudy: true,
          MistakeNotebookPanel: { template: '<div class="mistake-notebook-stub">错题本</div>' },
          NotesPanel: NotesPanelStub,
          SideAIPanel: { template: '<aside class="ai-panel-stub">AI 老师</aside>' },
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('.learning-context-bar').exists()).toBe(false)
    expect(wrapper.findAll('.learning-dock__domain').map(button => button.attributes('data-domain'))).toEqual(['reading', 'question-book', 'mistakes', 'overview', 'knowledge-library', 'notebook', 'assistant'])

    await wrapper.get('.open-practice').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    expect(useCourseWorkspaceStore().practiceScope).toBe('node')

    await wrapper.get('.close-task').trigger('click')
    await wrapper.get('[data-domain="notebook"]').trigger('click')
    expect(wrapper.find('.notebook-side-panel').exists()).toBe(true)
    expect(wrapper.find('.notebook-overlay').exists()).toBe(false)
    expect(wrapper.get('.notes-panel-stub').attributes('data-mode')).toBe('sidebar')

    await wrapper.get('.close-notes').trigger('click')
    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    expect(useCourseWorkspaceStore().practiceScope).toBe('all')
    await wrapper.get('.close-task').trigger('click')

    await wrapper.get('[data-domain="overview"]').trigger('click')
    expect(wrapper.find('.stats-overlay').exists()).toBe(true)
    expect(wrapper.get('.learning-stats-stub').attributes('data-closable')).toBe('true')
    await wrapper.get('.close-stats').trigger('click')
    expect(wrapper.find('.stats-overlay').exists()).toBe(false)
    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    const courseStore = useCourseStore()
    expect(courseStore.showKnowledgeLibrary).toBe(true)

    courseStore.showKnowledgeLibrary = false
    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(wrapper.find('.ai-panel-stub').exists()).toBe(true)
    wrapper.unmount()
  })


  it('课程生长块携带的独立复验题不会在跨组件转发时丢失', async () => {
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningDock: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.open-targeted-practice').trigger('click')

    expect(useCourseWorkspaceStore().requestedTaskRef?.task_revision_id).toBe('qr-targeted')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it('确认课程生长后先点亮目录，再自动定位正文并稳定保留新版本状态', async () => {
    const evolutionStore = useCourseEvolutionStore()
    let finishGrowthScroll: (() => void) | undefined
    evolutionStore.applyPayload('c1', {
      course_evolution_plans: [{
        change_set_id: 'plan-growth',
        hypothesis_id: 'hypothesis-growth',
        evidence_ids: [],
        operations: [],
        allowed_scopes: ['current'],
        impact_summary: { affected_section_ids: ['n1'] },
        expected_effect: '',
        status: 'applied',
        effect_evaluation: {},
      }],
    })
    growthScrollSpy.mockReset()
    growthScrollSpy.mockImplementation(() => new Promise<void>(resolve => {
      finishGrowthScroll = resolve
    }))
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: GrowthContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningDock: { template: '<button data-testid="open-ai" @click="$emit(\'ai\')">AI</button>' },
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: GrowthSideAIPanelStub,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.classes()).toContain('has-ai-course-growth')
    expect(wrapper.find('.ai-course-version').exists()).toBe(false)
    await wrapper.get('[data-testid="open-ai"]').trigger('click')
    await flushPromises()

    vi.useFakeTimers()
    try {
      await wrapper.get('.apply-growth').trigger('click')
      expect(evolutionStore.applicationVisual?.phase).toBe('navigator')

      await vi.advanceTimersByTimeAsync(980)
      await flushPromises()
      expect(growthScrollSpy).toHaveBeenCalledWith('n1', 'growth-animation')
      expect(evolutionStore.applicationVisual?.phase).toBe('navigator')

      finishGrowthScroll?.()
      await flushPromises()
      await vi.advanceTimersByTimeAsync(32)
      expect(evolutionStore.applicationVisual?.phase).toBe('content')

      await vi.advanceTimersByTimeAsync(2200)
      expect(evolutionStore.applicationVisual?.phase).toBe('settled')
    } finally {
      vi.useRealTimers()
      wrapper.unmount()
    }
  })

  it('旧课程没有可用题目时仍可从正文配套练习进入重建界面', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'c1',
      plan: {},
      quality_report: {},
      course_availability: {
        schema_version: 'course_learning_availability_v1',
        mode: 'compatibility',
        reason_code: 'legacy_reading_compatible',
        capabilities: {
          practice: {
            status: 'degraded',
            reason_code: 'legacy_reading_compatible',
          },
        },
      },
      assets: { questions: [] },
    }

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          TeachingRepresentationsOverlay: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.open-practice').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    expect(wrapper.get('.task-overlay-stub').text()).toContain(node.node_name)
    wrapper.unmount()
  })

  it('学习资源尚未同步时根据正式练习接口解锁当前章节', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'c1',
      plan: {},
      quality_report: {},
      course_availability: {
        schema_version: 'course_learning_availability_v1',
        mode: 'standard',
        reason_code: 'ready',
        capabilities: {},
      },
      assets: { questions: [] },
    }
    vi.mocked(workspace.checkPracticeAvailability).mockResolvedValue(true)

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          TeachingRepresentationsOverlay: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    const practiceAction = wrapper.get('[data-domain="question-book"]')
    expect(workspace.checkPracticeAvailability).toHaveBeenCalledWith('c1', 'n1')
    expect(practiceAction.attributes('disabled')).toBeUndefined()
    await practiceAction.trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it('工具栏进入全课程题库，不因当前三级节点没有直连题目而显示空范围', async () => {
    const parentNode: Node = {
      ...node,
      node_id: 'section-1',
      parent_node_id: 'chapter-1',
      node_name: '1.6 线性无关性',
      node_level: 2,
    }
    const childNode: Node = {
      ...node,
      node_id: 'section-1-6',
      parent_node_id: parentNode.node_id,
      node_name: '1.6.6 线性无关性与矩阵可逆性的关联',
      node_level: 3,
    }
    const course = useCourseStore()
    course.nodes = [parentNode, childNode]
    course.courseTree = [parentNode, childNode]
    course.currentNode = childNode
    await (globalThis as any).__learningTestRouter.replace('/course/c1/learn/section-1-6')

    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'c1',
      plan: {},
      quality_report: {},
      course_availability: {
        schema_version: 'course_learning_availability_v1',
        mode: 'standard',
        reason_code: 'ready',
        capabilities: {},
      },
      assets: {
        questions: [{ asset_id: 'q-parent', revision_id: 'qr-parent', node_id: parentNode.node_id }],
      },
    }

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          TeachingRepresentationsOverlay: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(useCourseWorkspaceStore().practiceScope).toBe('all')
    expect(wrapper.get('.task-overlay-stub').attributes('data-node-id')).toBeUndefined()
    expect(wrapper.get('.task-overlay-stub').text()).not.toContain(parentNode.node_name)
    wrapper.unmount()
  })

  it('生成预览仍只展示课程正文，不挂载教师备课资产', async () => {
    const course = useCourseStore()
    course.currentCourseProjection = 'generation_preview'
    course.currentTeachingPlan = {
      schema_version: 'course_teaching_plan_projection_v1',
      status: 'pending',
      revision_id: '',
      strategy: 'single_whole_course_call',
      section_count: 1,
      knowledge_point_count: 0,
      teaching_module_count: 0,
      sections: [],
    }
    const generation = useGenerationStore()
    const task = generation.createTask('job-live', 'c1', '线性代数')
    task.status = 'running'
    task.currentPhase = 'course_teaching_plan'
    task.totalNodes = 1

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningDock: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-workspace-item]').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'GenerationLessonPlan' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'CourseOutlineReview' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'CourseGenerationLifecycle' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'CourseProductionStage' }).exists()).toBe(false)
    expect(wrapper.find('#content-scroll-container').exists()).toBe(true)
    expect(wrapper.find('.learning-context-bar').exists()).toBe(false)
    wrapper.unmount()
  })

  it('生成中断也不会把教师恢复工作台暴露到学生页', async () => {
    const course = useCourseStore()
    course.currentCourseProjection = 'generation_preview'
    course.nodes = []
    course.courseTree = []
    course.currentNode = null
    const generation = useGenerationStore()
    const task = generation.createTask('job-interrupted', 'c1', '量子力学')
    task.status = 'error'
    task.progress = 32
    task.currentPhase = 'pedagogy_resolution'
    task.error = 'AI provider unavailable: authentication_failed'
    task.guidedWorkflow = {
      schema_version: 'guided_course_generation_v2',
      current_step: 'outline',
      review_step: null,
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'in_progress' },
        { number: 3, key: 'content', status: 'locked' },
        { number: 4, key: 'release', status: 'locked' },
      ],
    }
    task.recovery = {
      state: 'manual_resume',
      can_resume: true,
      reason_code: 'stage_restart_available',
      reason: 'saved',
      checkpoint: {
        phase: 'pedagogy_resolution', completed_nodes: 0, total_nodes: 0,
        draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [], requirements_ready: true,
      },
    }
    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, (globalThis as any).__learningTestRouter],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningDock: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('course-navigator-stub').exists()).toBe(false)
    expect(wrapper.find('.learning-context-bar').exists()).toBe(false)
    expect(wrapper.find('[data-workspace-item]').exists()).toBe(false)
    expect(wrapper.find('.formation-recovery').exists()).toBe(false)
    expect(wrapper.find('.generation-gate').exists()).toBe(false)
    expect(wrapper.find('#content-scroll-container').exists()).toBe(true)
    wrapper.unmount()
  })

})
