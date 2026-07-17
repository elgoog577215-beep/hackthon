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
    return { open: () => emit('startPractice', node) }
  },
  template: '<div id="content-scroll-container"><button id="practice-block-n1" class="open-practice" @click="open">open</button></div>',
})

const TaskOverlayStub = defineComponent({
  props: ['courseId', 'nodeId', 'nodeLabel', 'originRect'],
  emits: ['close', 'graded', 'askTeacher', 'records', 'stats'],
  template: '<div class="task-overlay-stub" :data-origin-top="originRect?.top"><span>{{ nodeLabel }}</span><button class="task-records" @click="$emit(\'records\')">records</button><button class="task-stats" @click="$emit(\'stats\')">stats</button><button class="close-task" @click="$emit(\'close\')">close</button></div>',
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
    vi.spyOn(workspace, 'migrateLegacyPracticeData').mockResolvedValue(undefined)

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
          LearningStats: true,
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

  it('正文页只保留三个底部域，进入学习覆盖层后才显示二级入口', async () => {
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
          SideAIPanel: { template: '<aside class="ai-panel-stub">AI 老师</aside>' },
          TeachingRepresentationsOverlay: true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.learning-dock__domain').map(button => button.text())).toEqual(['学习', '资源', '智能助教'])
    expect(wrapper.find('.learning-main > .learning-context-tabs').exists()).toBe(false)

    await wrapper.get('[data-domain="learning"]').trigger('click')
    expect(wrapper.find('.task-overlay-stub').exists()).toBe(true)

    await wrapper.get('.task-records').trigger('click')
    expect(wrapper.find('.records-overlay').exists()).toBe(true)
    expect(wrapper.findAll('.records-overlay .learning-context-tabs [role="tab"]').map(tab => tab.text())).toEqual(['当前练习', '学习记录', '学习概况'])

    await wrapper.get('[data-domain="resources"]').trigger('click')
    const courseStore = useCourseStore()
    expect(courseStore.showKnowledgeLibrary).toBe(true)

    courseStore.showKnowledgeLibrary = false
    courseStore.showTeachingResources = true
    await flushPromises()
    expect(wrapper.getComponent({ name: 'TeachingRepresentationsOverlay' }).props('visible')).toBe(true)

    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(wrapper.find('.ai-panel-stub').exists()).toBe(true)
    wrapper.unmount()
  })

})
