import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseBaselineDialog from '@/components/CourseBaselineDialog.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'


const baseline = {
  subject: '人工智能通识课',
  course_type: 'systematic' as const,
  course_intent: {
    schema_version: 'course_intent_v1' as const,
    type: 'systematic' as const,
    learning_goal: '理解人工智能的基本原理',
  },
  difficulty: 'intermediate' as const,
  composition_style: 'balanced' as const,
  pedagogy_mode: 'general' as const,
  production_mode: 'manual' as const,
  target_audience: '大学生',
  teacher_course_brief: {
    schema_version: 'teacher_course_brief_v1' as const,
    target_audience: '大学生',
    total_class_hours: 16,
    lesson_duration_minutes: 45,
    teaching_context: 'classroom' as const,
    section_count: 8,
  },
}


describe('CourseBaselineDialog', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('hydrates the existing course baseline and emits teacher-confirmed edits', async () => {
    const wrapper = mount(CourseBaselineDialog, {
      props: {
        modelValue: true,
        initialOptions: baseline,
        contextKey: '0:manual',
      },
      global: { stubs: { Teleport: true } },
    })

    expect((wrapper.get('#baseline-learning-goal').element as HTMLTextAreaElement).value)
      .toBe('理解人工智能的基本原理')
    expect((wrapper.get('#baseline-total-hours').element as HTMLInputElement).value).toBe('16')
    expect(wrapper.get('.course-type-options button.active').text()).toContain('系统学习')

    await wrapper.get('#baseline-learning-goal').setValue('能解释 AI 的能力边界并完成案例判断')
    await wrapper.get('#baseline-total-hours').setValue(24)
    await wrapper.get('.primary-button').trigger('click')

    const payload = wrapper.emitted('save')?.[0]?.[0] as any
    expect(payload.subject).toBe('人工智能通识课')
    expect(payload.options.course_intent.learning_goal).toBe('能解释 AI 的能力边界并完成案例判断')
    expect(payload.options.teacher_course_brief.total_class_hours).toBe(24)
    expect(payload.options.production_mode).toBe('manual')
  })

  it('labels an AI result as a draft and keeps saving explicit', () => {
    const wrapper = mount(CourseBaselineDialog, {
      props: {
        modelValue: true,
        initialOptions: baseline,
        contextKey: '0:ai-draft',
        aiDraft: true,
      },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('.ai-draft-notice').text()).toContain('保存后才会更新课程定调')
    expect(wrapper.get('.primary-button').text()).toContain('保存课程定调')
  })
})
