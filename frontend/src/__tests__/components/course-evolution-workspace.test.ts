import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'

describe('CourseEvolutionWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
  })

  it('把课程调整放进独立工作区并保留严格范围上下文', async () => {
    const wrapper = mount(CourseEvolutionWorkspace, {
      attachTo: document.body,
      props: {
        modelValue: true,
        courseId: 'course-1',
        courseTitle: '大学物理',
        sectionId: 'section-1',
        sectionTitle: '第一章 质点力学基础',
      },
      global: {
        plugins: [createPinia()],
        stubs: {
          Teleport: true,
          Transition: false,
          CourseEvolutionPanel: {
            props: ['courseId', 'sectionId', 'focusPlanId', 'surface', 'showHeading'],
            template: '<div class="evolution-workspace-stub" :data-course-id="courseId" :data-section-id="sectionId" :data-surface="surface" :data-heading="showHeading" />',
          },
        },
      },
    })

    expect(wrapper.get('.course-adjustment-title').text()).toContain('课程调整工作台')
    expect(wrapper.get('.course-adjustment-context').text()).toContain('大学物理 · 第一章 质点力学基础')
    expect(wrapper.findAll('.course-adjustment-guide li')).toHaveLength(3)
    expect(wrapper.get('.evolution-workspace-stub').attributes()).toMatchObject({
      'data-course-id': 'course-1',
      'data-section-id': 'section-1',
      'data-surface': 'workspace',
      'data-heading': 'false',
    })

    await wrapper.get('.course-adjustment-close').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    wrapper.unmount()
  })
})
