import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherScriptDocument from '@/components/TeacherScriptDocument.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { setLocale } from '@/shared/i18n'
import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import type { TeacherLessonProjection } from '@/stores/teacherLessonAuthoring'
import zhMessages from '../../../public/locales/zh/translation.json'

const lesson: TeacherLessonProjection = {
  lesson_unit_id: 'lesson-1', number: 1, title: '第1讲 爬虫概述', duration_minutes: 45,
  sections: [{ section_node_id: 'section-1', title: '1.1 爬虫基础' }],
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
    const rewrite = vi.spyOn(store, 'rewriteScriptSection').mockResolvedValue({ replacement_text: 'AI 候选讲稿' } as any)
    const save = vi.spyOn(store, 'saveScriptDraft').mockResolvedValue(lesson as any)
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('AI 优化'))!.trigger('click')
    await wrapper.get('.script-ai textarea').setValue('增加一个真实课堂案例')
    await wrapper.get('.script-ai').trigger('submit')
    await flushPromises()

    expect(rewrite).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-1', 'section-1', '增加一个真实课堂案例')
    expect(wrapper.get('.script-content').attributes('data-state')).toBe('candidate')
    expect(wrapper.findComponent(MarkdownRenderer).props('content')).toBe('AI 候选讲稿')
    expect(save).not.toHaveBeenCalled()

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('采用'))!.trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-1', [
      { section_node_id: 'section-1', title: '1.1 爬虫基础', content: 'AI 候选讲稿' },
    ])
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('底部同一位置先确认，确认后切换为进入 PPT', async () => {
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })
    const button = wrapper.get('.script-footer button')
    expect(button.text()).toContain('确认讲稿')
    await button.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)

    await wrapper.setProps({ confirmed: true })
    expect(wrapper.find('.script-state').exists()).toBe(false)
    expect(wrapper.find('.script-saved').exists()).toBe(false)
    expect(wrapper.get('.script-footer button').text()).toContain('进入 PPT')
    await wrapper.get('.script-footer button').trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
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
})
