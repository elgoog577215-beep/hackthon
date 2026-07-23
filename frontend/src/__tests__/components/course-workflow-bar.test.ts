import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import CourseWorkflowBar from '@/components/CourseWorkflowBar.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { writePptSameSourceHighlight } from '@/utils/ppt-same-source'

const routes = [
  { path: '/course/:courseId/workbench', name: 'course-workbench', component: { template: '<div />' } },
  { path: '/course/:courseId/ppt', name: 'ppt-workspace', component: { template: '<div />' } },
  { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
]

function createTestRouter() {
  return createRouter({ history: createMemoryHistory(), routes })
}

beforeEach(() => {
  sessionStorage.clear()
})

describe('CourseWorkflowBar', () => {
  it('shows real PPT handoff status and supports jumping directly between connected surfaces', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const courseStore = useCourseStore()
    courseStore.courseList = [{ course_id: 'course-1', course_name: '矩阵与线性变换', node_count: 12 }]
    courseStore.currentCourseId = 'course-1'
    writePptSameSourceHighlight(sessionStorage, {
      courseId: 'course-1',
      sectionId: 'section-2',
      blockIds: ['objective-2'],
      primaryBlockId: 'objective-2',
      beforeText: '掌握矩阵乘法的计算规则',
      afterText: '理解矩阵乘法表示线性变换的复合',
      createdAt: Date.now(),
      animationPlayed: false,
    })
    const router = createTestRouter()
    await router.push('/course/course-1/workbench')
    await router.isReady()
    const wrapper = mount(CourseWorkflowBar, { global: { plugins: [pinia, router] } })

    expect(wrapper.text()).toContain('启智课程闭环')
    expect(wrapper.text()).toContain('PPT 改动已交接到课程')
    expect(wrapper.findAll('.workflow-step')).toHaveLength(4)

    await wrapper.findAll('.workflow-step').find(button => button.text().includes('教学设计'))!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ppt-workspace')

    await wrapper.findAll('.workflow-step').find(button => button.text().includes('课程生长'))!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.nodeId).toBe('section-2')
    expect(router.currentRoute.value.query.surface).toBe('growth')
  })

  it('reports applied course growth without presenting it as independently verified success', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const courseStore = useCourseStore()
    courseStore.courseList = [{ course_id: 'course-1', course_name: '矩阵与线性变换', node_count: 12 }]
    courseStore.currentCourseId = 'course-1'
    const evolutionStore = useCourseEvolutionStore()
    evolutionStore.courseId = 'course-1'
    evolutionStore.plans = [{ status: 'applied' } as any]
    const router = createTestRouter()
    await router.push('/course/course-1/learn/section-2?surface=growth')
    await router.isReady()
    const wrapper = mount(CourseWorkflowBar, { global: { plugins: [pinia, router] } })

    expect(wrapper.get('.workflow-status').classes()).toContain('is-growth')
    expect(wrapper.get('.workflow-status').classes()).not.toContain('is-success')
    expect(wrapper.text()).toContain('已应用 1 个生长方案')
    expect(wrapper.find('.workflow-step.active').text()).toContain('课程生长')
  })
})
