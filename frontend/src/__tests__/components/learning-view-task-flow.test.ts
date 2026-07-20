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
import { useGenerationStore } from '@/stores/generation'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useNoteStore } from '@/stores/notes'
import type { Node } from '@/stores/types'

const node: Node = {
  node_id: 'n1', parent_node_id: 'chapter-1', node_name: '向量空间', node_level: 2,
  node_content: '正文', node_type: 'original', generation_status: 'completed', generated_chars: 2,
}

const ContentAreaStub = defineComponent({
  emits: ['startPractice'],
  setup(_, { emit }) {
    return {
      open: () => emit('startPractice', node),
      openTargeted: () => emit('startPractice', node, 'qr-targeted'),
    }
  },
  template: '<div id="content-scroll-container"><button id="practice-block-n1" class="open-practice" @click="open">open</button><button class="open-targeted-practice" @click="openTargeted">targeted</button></div>',
})

const TaskOverlayStub = defineComponent({
  props: ['courseId', 'nodeId', 'nodeLabel', 'originRect'],
  emits: ['close', 'graded', 'askTeacher', 'records', 'stats', 'outline', 'lesson-plan', 'course'],
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
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: LearningView }],
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
          NotesPanel: true,
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

  it('正文页用顶栏切换教案、课程和练习，并从底栏直达知识库', async () => {
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
          NotesPanel: true,
          SideAIPanel: { template: '<aside class="ai-panel-stub">AI 老师</aside>' },
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.learning-context-bar [data-workspace-item]').map(button => button.text())).toEqual(['教案', '课程', '练习'])
    expect(wrapper.get('.learning-context-bar [data-workspace-item="course"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.findAll('.learning-dock__domain').map(button => button.text())).toEqual(['笔记本', '错题本', '学习概况', '知识库', '智能助教'])

    await wrapper.get('.learning-context-bar [data-workspace-item="practice"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)

    await wrapper.get('.task-records').trigger('click')
    expect(wrapper.find('.notebook-overlay').exists()).toBe(true)
    expect(wrapper.get('.notebook-overlay').classes()).toContain('learning-tool-modal')
    expect(wrapper.find('.notebook-overlay .learning-tool-modal__backdrop').exists()).toBe(true)
    expect(wrapper.find('.notebook-overlay .learning-tool-modal__card.is-notebook').exists()).toBe(true)

    await wrapper.get('[data-domain="mistake-book"]').trigger('click')
    expect(wrapper.find('.mistake-book-overlay').exists()).toBe(true)
    expect(wrapper.find('.mistake-book-overlay .learning-tool-modal__card.is-mistake-book').exists()).toBe(true)
    expect(wrapper.find('.mistake-notebook-stub').exists()).toBe(true)

    await wrapper.get('[data-domain="overview"]').trigger('click')
    expect(wrapper.find('.stats-overlay').exists()).toBe(true)
    expect(wrapper.get('.learning-stats-stub').attributes('data-closable')).toBe('true')
    await wrapper.get('.close-stats').trigger('click')
    expect(wrapper.find('.stats-overlay').exists()).toBe(false)

    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    const courseStore = useCourseStore()
    expect(courseStore.showKnowledgeLibrary).toBe(true)

    courseStore.showKnowledgeLibrary = false
    await wrapper.get('.learning-context-bar [data-workspace-item="lesson-plan"]').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'GenerationLessonPlan' }).exists()).toBe(true)
    expect(wrapper.getComponent({ name: 'TeachingRepresentationsOverlay' }).props('visible')).toBe(false)

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

  it('旧课程没有可用题目时仍可从顶层当前练习进入重建界面', async () => {
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

    await wrapper.get('.learning-context-bar [data-workspace-item="practice"]').trigger('click')
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
          LearningDock: true,
          LearningStats: true,
          NotesPanel: true,
          SideAIPanel: true,
          TeachingRepresentationsOverlay: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    const practiceTab = wrapper.get(
      '.learning-context-bar [data-workspace-item="practice"]',
    )
    expect(workspace.checkPracticeAvailability).toHaveBeenCalledWith('c1', 'n1')
    expect(practiceTab.attributes('disabled')).toBeUndefined()
    await practiceTab.trigger('click')
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

    await wrapper.get('.learning-context-bar [data-workspace-item="practice"]').trigger('click')
    expect(wrapper.get('.task-overlay-stub').attributes('data-node-id')).toBe(parentNode.node_id)
    expect(wrapper.get('.task-overlay-stub').text()).toContain(parentNode.node_name)
    wrapper.unmount()
  })

  it('生成现场按真实阶段在教案与正文之间跟随，手动切换后保持当前视图', async () => {
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
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.learning-context-bar [data-workspace-item]').map(button => button.text())).toEqual(['教案', '课程', '练习'])
    expect(wrapper.get('[data-workspace-item="lesson-plan"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-workspace-item="practice"]').attributes('disabled')).toBeDefined()
    expect(wrapper.findComponent({ name: 'GenerationLessonPlan' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'CourseGenerationLifecycle' }).exists()).toBe(true)

    generation.tasks.get('c1')!.currentPhase = 'content_generation'
    await flushPromises()
    expect(wrapper.get('[data-workspace-item="course"]').attributes('aria-selected')).toBe('true')

    await wrapper.get('[data-workspace-item="lesson-plan"]').trigger('click')
    generation.tasks.get('c1')!.currentPhase = 'course_teaching_plan'
    await flushPromises()
    generation.tasks.get('c1')!.currentPhase = 'content_generation'
    await flushPromises()
    expect(wrapper.get('[data-workspace-item="lesson-plan"]').attributes('aria-selected')).toBe('true')

    await wrapper.get('.context-actions button').trigger('click')
    expect(wrapper.get('[data-workspace-item="course"]').attributes('aria-selected')).toBe('true')
    wrapper.unmount()
  })

  it('生成中断时在当前课程现场解释恢复边界并直接继续原任务', async () => {
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
    const resume = vi.spyOn(generation, 'resumeTask').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(course, 'refreshCourseData').mockResolvedValue(undefined)

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
          TeachingRepresentationsOverlay: true,
          Teleport: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('课程生产暂时中断')
    expect(wrapper.find('course-navigator-stub').exists()).toBe(false)
    expect(wrapper.get('.context-leading button').attributes('title')).toBe('返回课程库')
    expect(wrapper.get('[data-workspace-item="lesson-plan"]').attributes('disabled')).toBeDefined()
    await wrapper.get('.production-actions button').trigger('click')
    await flushPromises()
    expect(resume).toHaveBeenCalledWith('c1', 'job-interrupted')
    wrapper.unmount()
  })

})
