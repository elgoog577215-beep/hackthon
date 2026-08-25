import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherScriptDocument from '@/components/TeacherScriptDocument.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { setLocale } from '@/shared/i18n'
import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import type { TeacherLessonJob, TeacherLessonProjection } from '@/stores/teacherLessonAuthoring'
import zhMessages from '../../../public/locales/zh/translation.json'

const lesson: TeacherLessonProjection = {
  lesson_unit_id: 'lesson-1', number: 1, title: '第1讲 爬虫概述', duration_minutes: 45,
  sections: [{ section_node_id: 'section-1', title: '1.1 爬虫基础' }],
  arrangement: {
    schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1',
    lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1',
    lesson_type: 'theory', lesson_type_label: '理论讲授', blocks: [],
    status: 'confirmed', confirmed: true, source_state: 'current',
  },
  script: {
    current_revision_id: 'script-1', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1',
    source_state: 'current', ready: true, confirmed: false, confirmed_at: '',
    sections: [{ section_node_id: 'section-1', title: '1.1 爬虫基础', content: '原始讲稿内容' }],
  },
  plan: {
    lesson_unit_id: 'lesson-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1',
    source_state: 'current', revisions: [], ppt_assets: [],
  },
}

describe('统一讲稿页面', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('在展示页面原位编辑并保存同一份课程正文', async () => {
    const store = useTeacherLessonAuthoringStore()
    const save = vi.spyOn(store, 'saveScriptDraft').mockResolvedValue(lesson as any)
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })

    expect(wrapper.get('.script-title h3').text()).toBe('第1讲 爬虫概述')
    expect(wrapper.find('.script-state').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('课程讲稿')
    expect(wrapper.text()).not.toContain('1 个小节')

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('编辑讲稿'))!.trigger('click')
    await wrapper.get('.script-body textarea').setValue('老师修改后的讲稿')
    await wrapper.findAll('.script-actions button').find(button => button.text().includes('完成编辑'))!.trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-1', [
      { section_node_id: 'section-1', title: '1.1 爬虫基础', content: '老师修改后的讲稿' },
    ])
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.find('.script-document').exists()).toBe(true)
  })

  it('按已确认教案的教学块展示和逐块编辑讲稿', async () => {
    const structuredLesson = structuredClone(lesson)
    structuredLesson.script.sections[0] = {
      section_node_id: 'section-1',
      title: '1.1 爬虫基础',
      content: '## 本节任务\n\n先说明目标。\n\n## 核心教学\n\n讲清核心概念。',
      schema_version: 'teacher_script_v2',
      blocks: [
        { block_id: 'block-1', module_id: 'lesson_goal', role: 'objective', title: '本节任务', content: '先说明目标。', planned_minutes: 3 },
        { block_id: 'block-2', module_id: 'core_explanation', role: 'concept', title: '核心教学', content: '讲清核心概念。', planned_minutes: 20 },
      ],
    }
    const store = useTeacherLessonAuthoringStore()
    const save = vi.spyOn(store, 'saveScriptDraft').mockResolvedValue(structuredLesson as any)
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson: structuredLesson } })

    expect(wrapper.findAll('.script-module')).toHaveLength(2)
    expect(wrapper.text()).toContain('本节任务')
    expect(wrapper.text()).toContain('核心教学')

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('编辑讲稿'))!.trigger('click')
    const editors = wrapper.findAll('.script-block-editor textarea')
    expect(editors).toHaveLength(2)
    await editors[1]!.setValue('老师逐块修改后的核心讲解。')
    await wrapper.findAll('.script-actions button').find(button => button.text().includes('完成编辑'))!.trigger('click')
    await flushPromises()

    const savedSections = save.mock.calls[0]![3]
    expect(savedSections[0]!.blocks?.[0]!.content).toBe('先说明目标。')
    expect(savedSections[0]!.blocks?.[1]!.content).toBe('老师逐块修改后的核心讲解。')
  })

  it('把用户要求生成成页面内候选，采用后才写入正式正文', async () => {
    const store = useTeacherLessonAuthoringStore()
    const rewrite = vi.spyOn(store, 'rewriteScriptSection').mockResolvedValue({
      candidate_id: 'script-candidate-1',
      section_node_id: 'section-1',
      replacement_text: 'AI 候选讲稿',
    } as any)
    const resolve = vi.spyOn(store, 'resolveScriptAiCandidate').mockResolvedValue(lesson as any)
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('AI 优化'))!.trigger('click')
    expect(wrapper.emitted('open-ai')).toHaveLength(1)
    await (wrapper.vm as any).requestAiCandidate('增加一个真实课堂案例')
    await flushPromises()

    expect(rewrite).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-1', 'section-1', '增加一个真实课堂案例', [])
    expect(wrapper.get('.script-content').attributes('data-state')).toBe('candidate')
    expect(wrapper.findComponent(MarkdownRenderer).props('content')).toBe('AI 候选讲稿')
    expect(resolve).not.toHaveBeenCalled()

    await (wrapper.vm as any).resolveAiCandidate(true)
    await flushPromises()
    expect(resolve).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-candidate-1', true)
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('允许 AI 助手按真实讲稿小节定位正文并回传稳定作用域', async () => {
    const scopedLesson = structuredClone(lesson)
    scopedLesson.sections.push({ section_node_id: 'section-2', title: '1.2 HTTP 请求与响应' })
    scopedLesson.script.sections.push({
      section_node_id: 'section-2', title: '1.2 HTTP 请求与响应', content: '第二节讲稿内容',
    })
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson: scopedLesson } })

    expect((wrapper.vm as any).selectAiScope('section-2')).toBe(true)
    await flushPromises()

    expect(wrapper.get('.script-content').text()).toContain('第二节讲稿内容')
    expect(wrapper.emitted('ai-scope-change')?.at(-1)).toEqual([{ id: 'section-2', title: '1.2 HTTP 请求与响应' }])
    expect((wrapper.vm as any).selectAiScope('missing-section')).toBe(false)
  })

  it('底部只负责确认讲稿，确认后由左侧流程切换阶段', async () => {
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })
    const button = wrapper.get('.script-footer button')
    expect(button.text()).toContain('确认本讲讲稿')
    await button.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)

    await wrapper.setProps({ confirmed: true })
    expect(wrapper.find('.script-state').exists()).toBe(false)
    expect(wrapper.find('.script-saved').exists()).toBe(false)
    expect(wrapper.find('.script-footer').exists()).toBe(false)
  })

  it('无讲稿时先收集需求并只触发一条生成链路', async () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }
    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson: emptyLesson, canGenerate: true },
    })

    await wrapper.get('.script-generate textarea').setValue('增加课堂案例')
    await wrapper.get('.script-generate').trigger('submit')

    expect(wrapper.emitted('generate')).toEqual([['增加课堂案例']])
    expect(wrapper.find('.script-footer').exists()).toBe(false)
  })

  it('生成中展示已完成教学块，失败后只提供继续剩余内容', async () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }
    const generationJob: TeacherLessonJob = {
      id: 'script-job-1', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'failed', progress: 50,
      phase: 'lesson_script_interrupted', message: '核心教学生成中断，已保留完成内容。',
      warnings: [], total_blocks: 2, completed_blocks: 1,
      current_block_id: 'block-2', current_block_title: '核心教学',
      block_states: { 'block-1': 'completed', 'block-2': 'failed' },
      result_sections: [{
        section_node_id: 'section-1', title: '1.1 爬虫基础',
        content: '## 本节任务\n\n先说明目标。', schema_version: 'teacher_script_v2' as const,
        blocks: [{
          block_id: 'block-1', module_id: 'lesson_goal', role: 'objective',
          title: '本节任务', content: '先说明目标。', planned_minutes: 3,
        }],
      }],
    }
    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson: emptyLesson, canGenerate: true, generationJob },
    })

    expect(wrapper.get('.script-generation-progress').text()).toContain('1/2')
    expect(wrapper.findComponent(MarkdownRenderer).props('content')).toBe('先说明目标。')
    expect(wrapper.get('.script-generate button').text()).toContain('继续生成剩余内容')

    await wrapper.get('.script-generate').trigger('submit')
    expect(wrapper.emitted('generate')).toEqual([['']])

    await wrapper.setProps({
      generating: true,
      generationJob: { ...generationJob, status: 'running', message: '正在生成：核心教学' },
    })
    expect(wrapper.find('.script-generate').exists()).toBe(false)
    expect(wrapper.get('.script-generation-progress').text()).toContain('正在生成：核心教学')
    await wrapper.get('.script-generation-progress button').trigger('click')
    expect(wrapper.emitted('cancel-generation')).toHaveLength(1)

    await wrapper.setProps({
      generating: false,
      generationJob: { ...generationJob, status: 'cancelled', message: '已停止生成，已完成内容仍然保留' },
    })
    expect(wrapper.get('.script-generate button').text()).toContain('继续生成剩余内容')
  })
})
