import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import LearningView from '@/views/LearningView.vue'
import { useAITeacherStore } from '@/stores/aiTeacher'
import { useChangeProposalsStore } from '@/stores/changeProposals'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useGenerationStore } from '@/stores/generation'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useNoteStore } from '@/stores/notes'
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
  beforeEach(async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    const pinia = createPinia()
    setActivePinia(pinia)
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
          LearningStats: LearningStatsStub,
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
          LearningStats: LearningStatsStub,
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

    expect(wrapper.findAll('.learning-context-bar [data-workspace-item]')).toHaveLength(0)
    expect(wrapper.findAll('.learning-dock__domain').map(button => button.text())).toEqual(['笔记本', '题库本1', '学习概况', '知识库', '智能助教'])

    await wrapper.get('.open-practice').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)

    await wrapper.get('.close-task').trigger('click')
    await wrapper.get('[data-domain="notebook"]').trigger('click')
    expect(wrapper.find('.notebook-side-panel').exists()).toBe(true)
    expect(wrapper.find('.notebook-overlay').exists()).toBe(false)
    expect(wrapper.get('.notes-panel-stub').attributes('data-mode')).toBe('sidebar')

    await wrapper.get('.close-notes').trigger('click')
    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
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

  it('教师预览复用完整学生学习现场，并把笔记放在右侧栏', async () => {
    const router = (globalThis as any).__learningTestRouter
    await router.replace('/course/c1/learn/n1?teacherPreview=1')
    const course = useCourseStore()
    const notes = useNoteStore()
    const progress = useLearningProgressStore()
    const ai = useAITeacherStore()
    const workspace = useCourseWorkspaceStore()

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, router],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: LearningStatsStub,
          MistakeNotebookPanel: true,
          NotesPanel: NotesPanelStub,
          SideAIPanel: { template: '<aside class="ai-panel-stub">AI 老师</aside>' },
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.teacher-preview-bar').text()).toContain('学生视角预览')
    expect(wrapper.get('#content-scroll-container').attributes('data-read-only')).toBe('false')
    expect(wrapper.find('[data-testid="open-content-practice"]').exists()).toBe(false)
    expect(wrapper.find('[title="打开 AI 老师"]').exists()).toBe(true)
    expect(wrapper.findAll('.learning-dock__domain').map(button => button.text())).toEqual(['笔记本', '题库本1', '学习概况', '知识库', '智能助教'])
    expect(course.loadCourse).toHaveBeenCalledWith('c1')
    expect(notes.loadCourseRecords).toHaveBeenCalledWith('c1')
    expect(progress.load).toHaveBeenCalledWith('c1', 'n1')
    expect(ai.load).toHaveBeenCalledWith('c1', 'n1')
    expect(workspace.loadMistakeBook).toHaveBeenCalledWith('c1')

    await wrapper.get('[data-domain="notebook"]').trigger('click')
    expect(wrapper.find('.notebook-side-panel').exists()).toBe(true)
    expect(wrapper.get('.notes-panel-stub').attributes('data-mode')).toBe('sidebar')
    await wrapper.get('.close-notes').trigger('click')

    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it('教师预览在移动端把笔记本放入全屏弹层', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    const router = (globalThis as any).__learningTestRouter
    await router.replace('/course/c1/learn/n1?teacherPreview=1')

    const wrapper = mount(LearningView, {
      attachTo: document.body,
      global: {
        plugins: [(globalThis as any).__learningTestPinia, router],
        stubs: {
          ContentArea: ContentAreaStub,
          LearningTaskOverlay: TaskOverlayStub,
          CourseNavigator: true,
          LearningStats: LearningStatsStub,
          MistakeNotebookPanel: true,
          NotesPanel: NotesPanelStub,
          SideAIPanel: true,
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-domain="notebook"]').trigger('click')
    expect(wrapper.find('.notebook-side-panel').exists()).toBe(false)
    expect(wrapper.find('.notebook-overlay').exists()).toBe(true)
    expect(wrapper.get('.notes-panel-stub').attributes('data-mode')).toBeUndefined()
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
          LearningDock: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: GrowthSideAIPanelStub,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.classes()).toContain('has-ai-course-growth')
    expect(wrapper.get('.ai-course-version').text()).toContain('新版本已应用')
    await wrapper.get('[title="打开 AI 老师"]').trigger('click')
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

    await wrapper.get('[data-domain="question-book"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)
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

  it('当前三级节点没有直连题目时使用最近父级的练习范围', async () => {
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
    expect(wrapper.get('.task-overlay-stub').attributes('data-node-id')).toBe(parentNode.node_id)
    expect(wrapper.get('.task-overlay-stub').text()).toContain(parentNode.node_name)
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
    expect(wrapper.get('.context-copy').text()).toContain('向量空间')
    expect(wrapper.get('.context-copy').text()).not.toContain('课程生产')
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
    expect(wrapper.find('.context-leading button').exists()).toBe(false)
    expect(wrapper.find('[data-workspace-item]').exists()).toBe(false)
    expect(wrapper.find('.formation-recovery').exists()).toBe(false)
    expect(wrapper.find('.generation-gate').exists()).toBe(false)
    expect(wrapper.find('#content-scroll-container').exists()).toBe(true)
    wrapper.unmount()
  })

})
