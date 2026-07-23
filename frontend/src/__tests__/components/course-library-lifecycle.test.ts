import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import CourseLibraryView from '@/views/CourseLibraryView.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: CourseLibraryView },
    { path: '/course/:courseId/learn', name: 'learning', component: { template: '<div />' } },
  ],
})

const GenerationDialogStub = defineComponent({
  props: { modelValue: Boolean, busy: Boolean },
  emits: ['generate', 'update:modelValue'],
  template: '<button v-if="modelValue" class="generate-now" @click="$emit(\'generate\', { subject: \'微积分\', options: {} })">generate</button>',
})

describe('CourseLibraryView generation lifecycle', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await router.push('/courses')
    await router.isReady()
  })

  it('已发布的质量建议不占用待处理任务角标', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-1', course_name: '世界模型', node_count: 20 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    const task = generation.createTask('job-1', 'course-1', '世界模型')
    task.status = 'completed_with_warnings'
    task.progress = 100
    task.publicationAllowed = true
    task.recovery = {
      state: 'completed', can_resume: false, reason_code: 'already_published', reason: 'done',
      checkpoint: { phase: 'completed', completed_nodes: 20, total_nodes: 20, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
    }

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('可以学习，有优化建议')
    expect(wrapper.text()).toContain('20 个学习节点')
    expect(wrapper.find('.action-count').exists()).toBe(false)
    expect(wrapper.find('.generation-progress').exists()).toBe(false)
  })

  it('为每门课程提供独立于生成任务的题库质量管理入口', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-review', course_name: '热力学', node_count: 12 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    const reviewButton = wrapper.get('[data-testid="open-question-bank-review-course-review"]')
    expect(reviewButton.text()).toContain('题库管理')
    await reviewButton.trigger('click')
    await flushPromises()

    const reviewCenter = wrapper.getComponent({ name: 'QuestionBankReviewCenter' })
    expect(reviewCenter.props('modelValue')).toBe(true)
    expect(reviewCenter.props('courseId')).toBe('course-review')
    const taskCenter = wrapper.getComponent({ name: 'CourseTaskCenter' })
    expect(taskCenter.props('modelValue')).toBe(false)
  })

  it('新建课程后直接进入同一门课程的生成现场', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(courses, 'generateCourse').mockResolvedValue({
      jobId: 'job-live',
      courseId: 'course-live',
      courseName: '微积分',
    })
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: GenerationDialogStub,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.library-actions .primary-button').trigger('click')
    await wrapper.get('.generate-now').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-live')
    expect(wrapper.findComponent({ name: 'CourseTaskCenter' }).props('modelValue')).toBe(false)
  })

  it('opens a published course directly in the learning workspace', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-ready', course_name: '矩阵与线性变换', node_count: 12 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    await router.push('/courses')
    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.course-main').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-ready')
    wrapper.unmount()
  })
})
