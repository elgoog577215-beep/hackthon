import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  teacherRequestConfig: (config = {}) => config,
}))

import CompanionDocumentStudio from '@/components/CompanionDocumentStudio.vue'

const rubricTemplate = {
  template_id: 'zju-grading-rubric-v1',
  template_version: 1,
  document_type: 'grading_rubric',
  name: '评分细则',
  name_en: 'Grading rubric',
  description: '按考核项目生成正式文件',
  description_en: 'Create a formal grading document',
  institution: '浙江大学',
  form_kind: 'grading_rubric',
  default_inputs: {
    title: '《数据结构》课程成绩评定细则',
    course_name: '数据结构',
    teacher_name: '',
    effective_date: '',
    special_rules: '',
    components: [
      { component_id: 'usual', name: '平时成绩', weight: 40, scope: '个人', details: '课堂表现与作业' },
      { component_id: 'exam', name: '期末考试', weight: 60, scope: '个人', details: '闭卷考试' },
    ],
  },
}

const checklistTemplate = {
  ...rubricTemplate,
  template_id: 'zju-exam-course-material-checklist-v1',
  document_type: 'course_material_checklist',
  name: '考试课程材料自查清单',
  name_en: 'Exam-course material checklist',
  form_kind: 'material_checklist',
  default_inputs: { title: '考试课程材料自查清单', course_name: '数据结构', teacher_name: '', items: [] },
}

describe('CompanionDocumentStudio', () => {
  it('先展示二级模板，再用结构化表单生成正式文件', async () => {
    httpMock.get.mockResolvedValue({ data: { templates: [rubricTemplate, checklistTemplate], documents: [] } })
    httpMock.post.mockResolvedValue({
      data: {
        document_id: 'compdoc-1',
        template_id: rubricTemplate.template_id,
        document_type: 'grading_rubric',
        title: rubricTemplate.default_inputs.title,
        status: 'ready',
        revision_id: 'revision-1',
        revision_number: 1,
        inputs: rubricTemplate.default_inputs,
        rendered_markdown: '# 课程成绩评定细则',
        updated_at: '2026-08-23T00:00:00Z',
      },
    })

    const wrapper = mount(CompanionDocumentStudio, {
      props: { courseId: 'course-1' },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<div class="markdown-stub">{{ content }}</div>' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.template-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('评分细则')
    expect(wrapper.text()).toContain('考试课程材料自查清单')
    expect(wrapper.text()).not.toContain(rubricTemplate.description)

    await wrapper.findAll('.template-card')[0]!.trigger('click')
    expect(wrapper.get('.document-form')).toBeTruthy()
    expect(wrapper.get('.weight-total').text()).toBe('100%')
    expect(wrapper.text()).not.toContain('各项比例合计必须为 100%')
    expect(wrapper.text()).not.toContain('右侧资料会作为引用依据')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/companion-documents/zju-grading-rubric-v1/generate',
      { inputs: rubricTemplate.default_inputs },
      { silentError: true },
    )
    expect(wrapper.get('.markdown-stub').text()).toContain('课程成绩评定细则')
    expect(wrapper.emitted('saved')?.[0]?.[0]).toMatchObject({ document_id: 'compdoc-1' })
  })
})
