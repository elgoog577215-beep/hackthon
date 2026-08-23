import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import http from '@/utils/http'

const growth = {
  schema_version: 'course_outline_growth_v1',
  state: 'growing',
  active_chapter_number: 2,
  completed_batches: 1,
  total_batches: 3,
  completed_sections: 2,
  total_sections: 6,
  chapters: [
    {
      chapter_number: 1,
      title: '程序环境与基础语法',
      learning_focus: '建立可运行的程序心智模型',
      section_count: 2,
      completed_section_count: 2,
      status: 'completed',
      sections: [
        { node_id: 'L2-1-1', section_number: '1.1', title: 'Hello World 与编译过程', learning_objective: '能解释源码如何变成可执行程序' },
        { node_id: 'L2-1-2', section_number: '1.2', title: '变量与基本数据类型', learning_objective: '能选择合适数据类型' },
      ],
    },
    {
      chapter_number: 2,
      title: '流程控制结构',
      learning_focus: '用条件和循环表达算法',
      section_count: 2,
      completed_section_count: 0,
      status: 'growing',
      sections: [],
    },
  ],
}

const mountWorkbench = (props: Record<string, unknown> = {}) => mount(TeacherCourseWorkbench, {
  props: {
    courseId: 'course-1',
    courseTitle: 'C 语言程序设计',
    generationOptions: {} as any,
    ...props,
  },
  global: {
    stubs: {
      CourseReferenceTray: true,
      CompanionDocumentStudio: true,
      QuestionBankReviewPanel: true,
      MarkdownRenderer: true,
      CourseOutlineReview: {
        template: '<section data-testid="inline-outline-editor"><button type="button" @click="$emit(\'confirmed\')">确认</button></section>',
        emits: ['confirmed'],
      },
    },
  },
})

describe('teacher course workbench outline streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
    vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'resumed' } })
  })

  it('用后端大纲检查点持续吐出已形成的章节文字', () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.currentStep = '正在展开各章小节'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }

    const wrapper = mountWorkbench()

    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('Hello World 与编译过程')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('流程控制结构')
    expect(wrapper.find('.stream-waiting').exists()).toBe(false)
    expect(wrapper.get('.generation-surface>header').text()).toContain('正在展开各章小节')
  })

  it('大纲进入待审阅后退出生成面板并显示真实章节', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1章 程序环境与基础语法', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
      {
        node_id: 'L2-1-1', parent_node_id: 'L1-1', node_name: '1.1 Hello World 与编译过程', node_level: 2,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.progress = 35
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: { ...growth, state: 'completed' } }

    const wrapper = mountWorkbench()

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-review-ready"]').text()).toContain('课程大纲已生成')
    expect(wrapper.get('[data-testid="outline-review-ready"]').text()).toContain('Hello World 与编译过程')
    await wrapper.get('[data-testid="outline-review-ready"] header button').trigger('click')
    expect(wrapper.emitted('update:outlineEditing')).toEqual([[true]])
  })

  it('把大纲编辑器放在工作台中央而不是右侧抽屉', async () => {
    const wrapper = mountWorkbench({ outlineEditing: true })

    expect(wrapper.find('.workbench-center [data-testid="inline-outline-editor"]').exists()).toBe(true)
    expect(wrapper.find('.stage-rail').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    await wrapper.get('[data-testid="inline-outline-editor"] button').trigger('click')
    expect(wrapper.emitted('outlineConfirmed')).toHaveLength(1)
    expect(wrapper.emitted('update:outlineEditing')).toContainEqual([false])
  })

  it('先展示真实大章节，再由老师确认每章小节数并继续同一任务', async () => {
    const generation = useGenerationStore()
    const task = generation.createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.currentPhase = 'outline_shape_ready'
    task.phaseDetail = {
      artifact_type: 'course_outline_skeleton',
      skeleton_revision_id: 'skeleton-1',
      outline_growth: { ...growth, state: 'shape_review', completed_sections: 0 },
    }
    generation.generationStatus = 'error'

    const wrapper = mountWorkbench()
    const sectionInputs = wrapper.findAll('.shape-chapter-list input')

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).toContain('程序环境与基础语法')
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).toContain('流程控制结构')
    expect(sectionInputs).toHaveLength(2)
    await sectionInputs[0]!.setValue(3)
    await sectionInputs[1]!.setValue(5)
    await wrapper.get('.outline-shape-review>footer button').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith(
      '/api/courses/course-1/generation/outline-shape/confirm',
      { chapter_section_counts: [3, 5] },
      expect.any(Object),
    )
  })

  it('生成大章节前不盲填逐章小节数，学时也不自动换算小节', async () => {
    const wrapper = mountWorkbench()

    expect(wrapper.find('.chapter-shape-editor').exists()).toBe(false)
    expect(wrapper.get('.course-shape-summary').text()).toContain('先生成大章节')
    await wrapper.get('.form-field input[type="number"]').setValue(12)
    await wrapper.get('form.stage-form').trigger('submit')
    await flushPromises()

    const emitted = wrapper.emitted('generateOutline')?.[0]?.[0] as any
    expect(emitted.options.teacher_course_brief).toEqual(expect.objectContaining({
      total_class_hours: 12,
    }))
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('chapter_count')
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('section_count')
  })
})
