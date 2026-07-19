import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankReviewCenter from '@/components/QuestionBankReviewCenter.vue'
import { useCourseStore } from '@/stores/course'

describe('QuestionBankReviewCenter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('lists every course and loads the selected course bank without generation tasks', async () => {
    const courses = useCourseStore()
    courses.courseList = [
      { course_id: 'course-data', course_name: '高级数据结构', node_count: 13 },
      { course_id: 'course-calculus', course_name: '微积分', node_count: 68 },
      { course_id: 'course-thermo', course_name: '热力学', node_count: 24 },
    ]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mount(QuestionBankReviewCenter, {
      props: {
        modelValue: true,
        courseId: 'course-calculus',
      },
      global: {
        stubs: {
          Teleport: true,
          QuestionBankReviewPanel: {
            props: ['courseId'],
            template: '<div data-testid="review-panel">{{ courseId }}</div>',
          },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('高级数据结构')
    expect(wrapper.text()).toContain('微积分')
    expect(wrapper.text()).toContain('热力学')
    expect(wrapper.get('[data-testid="review-panel"]').text()).toBe('course-calculus')

    await wrapper.get('[data-testid="question-bank-course-course-thermo"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="review-panel"]').text()).toBe('course-thermo')
  })
})
