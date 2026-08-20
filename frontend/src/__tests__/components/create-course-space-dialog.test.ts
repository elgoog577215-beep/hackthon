import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CreateCourseSpaceDialog from '@/components/CreateCourseSpaceDialog.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'

describe('CreateCourseSpaceDialog', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('只收集课程空间必需信息，不在首页启动整课生成', async () => {
    const wrapper = mount(CreateCourseSpaceDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.text()).toContain('先建立一个空的课程空间')
    expect(wrapper.text()).not.toContain('课程类型')
    expect(wrapper.text()).not.toContain('生成模式')
    await wrapper.get('.course-name-field input').setValue('人工智能通识课')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('create')?.[0]?.[0]).toEqual(expect.objectContaining({
      course_name: '人工智能通识课',
      academic_year: expect.stringMatching(/^\d{4}-\d{4}$/),
      term: expect.stringMatching(/^(春季|秋季)$/),
    }))
  })
})
