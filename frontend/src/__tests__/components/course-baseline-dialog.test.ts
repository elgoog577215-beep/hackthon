import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseBaselineDialog from '@/components/CourseBaselineDialog.vue'
import { setLocale } from '@/shared/i18n'
import http from '@/utils/http'
import zhMessages from '../../../public/locales/zh/translation.json'

const information = {
  course_name: '人工智能通识课', academic_year: '2026-2027', term: '秋冬',
  course_profile: {
    english_name: 'Introduction to Artificial Intelligence',
    course_code: 'AI101', course_goal: '理解人工智能的基本原理', default_location: '西1-205',
    target_grade: '本科生', course_category: '通识必修课', target_major: '', credits: 2,
    weekly_hours: 2, prerequisite_courses: '无', weekday: '周三', periods: '第 3—4 节',
    total_hours: 32, assessment_method: '过程考核', course_intro: '理解 AI 的基本原理。',
    teaching_goals: '理解人工智能的基本原理',
  },
  generation_request: {
    subject: '人工智能通识课', target_audience: '本科生', course_type: 'systematic', difficulty: 'intermediate',
    composition_style: 'balanced', pedagogy_mode: 'general', production_mode: 'manual',
    course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: '理解人工智能的基本原理' },
    teacher_course_brief: {
      schema_version: 'teacher_course_brief_v1', academic_term: '2026-2027 秋冬', target_audience: '本科生',
      total_class_hours: 32, lesson_duration_minutes: 45, teaching_context: 'classroom', section_count: 16,
    },
  },
}

function envelope(current = information) {
  return {
    course_id: 'course-1', revision: 1, document_revision: 'doc-1', information: structuredClone(current),
    versions: [
      { revision: 1, current: true, source: 'current', committed_at: '2026-08-24T08:00:00Z', changed_fields: [], information: structuredClone(current) },
      { revision: 0, current: false, source: 'manual', committed_at: '2026-08-24T07:00:00Z', changed_fields: ['course_scale'], information: structuredClone({ ...information, generation_request: { ...information.generation_request, teacher_course_brief: { ...information.generation_request.teacher_course_brief, total_class_hours: 16 } } }) },
    ],
  }
}

describe('CourseBaselineDialog', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
    vi.spyOn(http, 'get').mockResolvedValue({ data: envelope() } as any)
  })

  it('默认查看基础信息，编辑后先确认差异再保存', async () => {
    const updated = envelope({ ...information, course_profile: { ...information.course_profile, weekly_hours: 4 } })
    updated.revision = 2
    vi.spyOn(http, 'put').mockResolvedValue({ data: updated } as any)
    const wrapper = mount(CourseBaselineDialog, {
      props: { modelValue: true, courseId: 'course-1' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    expect(wrapper.get('.course-identity').text()).toContain('人工智能通识课')
    expect(wrapper.get('.information-view').text()).toContain('Introduction to Artificial Intelligence')
    expect(wrapper.get('.information-view').text()).toContain('周学时2')
    expect(wrapper.get('.information-view').text()).toContain('先修课程无')
    expect(wrapper.get('.information-view').text()).toContain('课程基本信息')
    expect(wrapper.get('.information-view').text()).not.toContain('教学实施条件')
    expect(wrapper.get('.information-view').text()).not.toContain('教学设计')
    expect(wrapper.get('.information-view').text()).not.toContain('预计章节数')
    expect(wrapper.get('.information-view').text()).not.toContain('预计课次')
    expect(wrapper.get('.information-view').text()).toContain('上课星期周三')
    expect(wrapper.get('.information-view').text()).toContain('上课节次第 3—4 节')
    expect(wrapper.get('.information-view').text()).not.toContain('待填写')
    expect(wrapper.text()).not.toContain('集中查看建课信息')
    expect(wrapper.text()).not.toContain('编号、类别、教学对象和学期信息')
    expect(wrapper.text()).not.toContain('课时与班级情况')
    expect(wrapper.text()).not.toContain('课程名称关联正式课程文档')
    expect(wrapper.text()).not.toContain('大纲版本')
    expect(wrapper.text()).not.toContain('已确认教案')

    await wrapper.get('.primary-button').trigger('click')
    expect(wrapper.get('.information-form').text()).toContain('课程英文名称')
    expect(wrapper.get('.information-form').text()).toContain('周学时')
    expect(wrapper.get('.information-form').text()).toContain('先修课程')
    expect(wrapper.get('.information-form').text()).not.toContain('辅助学科类型')
    expect(wrapper.get('.information-form').text()).not.toContain('预计章节数')
    expect(wrapper.get('.information-form').text()).not.toContain('预计课次')
    expect(wrapper.get('.information-form').text()).toContain('上课时间')
    expect(wrapper.get('.information-form').text()).toContain('计划讲数')
    expect(wrapper.text()).not.toContain('编号、类别、教学对象和学期信息')
    expect(wrapper.text()).not.toContain('课时与班级情况')
    expect(wrapper.text()).not.toContain('教学类型、学科类型与难度')
    expect(wrapper.text()).not.toContain('课程简介、考核方式与额外教学要求')
    expect(wrapper.get('.information-form').text()).not.toContain('授课场景')
    const weeklyHoursField = wrapper.findAll('label').find(label => label.text().includes('周学时'))
    expect(weeklyHoursField).toBeTruthy()
    await weeklyHoursField!.get('input').setValue(4)
    await wrapper.get('.primary-button').trigger('click')

    expect(wrapper.get('.review-panel').text()).toContain('周学时')
    expect(wrapper.get('.review-panel').text()).toContain('2')
    expect(wrapper.get('.review-panel').text()).toContain('4')
    expect(wrapper.text()).not.toContain('不会自动重新生成已有内容')

    await wrapper.get('.primary-button').trigger('click')
    await flushPromises()
    expect(http.put).toHaveBeenCalledWith(
      '/api/courses/course-1/course-information',
      expect.objectContaining({
        expected_revision: 1,
        source: 'manual',
        information: expect.objectContaining({
          course_profile: expect.objectContaining({ weekly_hours: 4 }),
        }),
      }),
      expect.any(Object),
    )
    const savedInformation = vi.mocked(http.put).mock.calls[0]?.[1] as any
    expect(savedInformation.information.generation_request).toMatchObject({
      learning_purpose: 'systematic',
      course_teaching_type: 'comprehensive',
    })
    expect(savedInformation.information.generation_request).not.toHaveProperty('course_type')
    expect(savedInformation.information.generation_request).not.toHaveProperty('course_purpose')
    expect(savedInformation.information.generation_request).not.toHaveProperty('composition_style')
    expect(wrapper.get('.save-status').text()).toContain('课程信息已保存')
  })

  it('可从修改记录恢复上一版，并以新修订保存', async () => {
    vi.spyOn(http, 'put').mockResolvedValue({ data: { ...envelope(), revision: 2 } } as any)
    const wrapper = mount(CourseBaselineDialog, {
      props: { modelValue: true, courseId: 'course-1' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    await wrapper.get('.secondary-button').trigger('click')
    expect(wrapper.get('.history-panel').text()).toContain('修订 0')
    expect(wrapper.text()).not.toContain('恢复旧设置会创建一个新修订')
    await wrapper.get('.history-panel li:last-child button').trigger('click')
    expect(wrapper.get('.review-panel').text()).toContain('恢复历史设置')
    await wrapper.get('.primary-button').trigger('click')
    await flushPromises()

    expect(http.put).toHaveBeenCalledWith(
      '/api/courses/course-1/course-information',
      expect.objectContaining({ source: 'restore', restore_revision: 0 }),
      expect.any(Object),
    )
  })

  it('有预取内容时立即可看，后台刷新超时也不遮住内容', async () => {
    vi.mocked(http.get).mockRejectedValueOnce({ code: 'ECONNABORTED' })
    const initialEnvelope = envelope()
    const wrapper = mount(CourseBaselineDialog, {
      props: { modelValue: true, courseId: 'course-1', initialEnvelope: initialEnvelope as any },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('.information-view').text()).toContain('人工智能通识课')
    expect(wrapper.find('.dialog-state').exists()).toBe(false)
    expect(wrapper.get('.refresh-status').text()).toContain('正在确认最新课程信息')

    await flushPromises()

    expect(wrapper.get('.information-view').text()).toContain('人工智能通识课')
    expect(wrapper.get('.load-warning').text()).toContain('当前仍显示上次读取的内容')
    expect(http.get).toHaveBeenCalledWith(
      '/api/courses/course-1/course-information',
      expect.objectContaining({ timeout: 10000, signal: expect.any(AbortSignal) }),
    )
  })
})
