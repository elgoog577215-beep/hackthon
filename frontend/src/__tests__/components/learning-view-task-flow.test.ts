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
  emits: ['close', 'graded', 'askTeacher'],
  template: '<div class="task-overlay-stub" :data-origin-top="originRect?.top"><span>{{ nodeLabel }}</span><button class="close-task" @click="$emit(\'close\')">close</button></div>',
})

describe('LearningView 正文任务覆盖层', () => {
  beforeEach(async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: LearningView },
        { path: '/course/:courseId/deck', name: 'presentation-entry', component: { template: '<div />' } },
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

  it('从学习页进入课件时保留课程与章节上下文', async () => {
    const course = useCourseStore()
    const chapter: Node = {
      node_id: 'chapter-1', parent_node_id: '', node_name: '第 2 章', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }
    course.nodes = [chapter, node]
    course.courseTree = [chapter]

    const wrapper = mount(LearningView, {
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
    await wrapper.get('.courseware-entry').trigger('click')
    await flushPromises()

    const route = (globalThis as any).__learningTestRouter.currentRoute.value
    expect(route.name).toBe('presentation-entry')
    expect(route.query).toMatchObject({
      nodeId: 'n1',
      courseTitle: '线性代数',
      chapterTitle: '第 2 章',
    })
    wrapper.unmount()
  })

})
