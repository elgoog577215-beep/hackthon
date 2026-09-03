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

describe('统一讲义页面', () => {
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
    expect(wrapper.text()).not.toContain('课程讲义')
    expect(wrapper.text()).not.toContain('1 个小节')

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('编辑讲义'))!.trigger('click')
    await wrapper.get('.script-body textarea').setValue('老师修改后的讲稿')
    await wrapper.findAll('.script-actions button').find(button => button.text().includes('完成编辑'))!.trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-1', [
      { section_node_id: 'section-1', title: '1.1 爬虫基础', content: '老师修改后的讲稿' },
    ])
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.find('.script-document').exists()).toBe(true)
  })

  it('取消讲义编辑会丢弃临时输入并恢复已保存正文', async () => {
    const store = useTeacherLessonAuthoringStore()
    const save = vi.spyOn(store, 'saveScriptDraft')
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('编辑讲义'))!.trigger('click')
    await wrapper.get('.script-body textarea').setValue('这是只存在于本次编辑的临时内容')
    await wrapper.findAll('.script-actions button').find(button => button.text().includes('取消'))!.trigger('click')
    await flushPromises()

    expect(save).not.toHaveBeenCalled()
    expect(wrapper.find('.script-body textarea').exists()).toBe(false)
    expect(wrapper.get('.script-content').text()).toContain('原始讲稿内容')
    expect(wrapper.text()).not.toContain('这是只存在于本次编辑的临时内容')
  })

  it('讲稿跨教学块编辑时可以撤销和重做', async () => {
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })
    ;(wrapper.vm as any).beginEditing()
    await flushPromises()

    await wrapper.get('.script-body textarea').setValue('修改后的讲稿')
    await flushPromises()
    expect((wrapper.vm as any).canUndo).toBe(true)

    ;(wrapper.vm as any).undoEdit()
    await flushPromises()
    expect((wrapper.get('.script-body textarea').element as HTMLTextAreaElement).value).toBe('原始讲稿内容')

    ;(wrapper.vm as any).redoEdit()
    await flushPromises()
    expect((wrapper.get('.script-body textarea').element as HTMLTextAreaElement).value).toBe('修改后的讲稿')
  })

  it('按当前教案的教学块展示和逐块编辑讲稿', async () => {
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

    await wrapper.findAll('.script-actions button').find(button => button.text().includes('编辑讲义'))!.trigger('click')
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

    expect(wrapper.findAll('.script-body')).toHaveLength(2)
    expect(wrapper.findAll('.script-content').map(node => node.text())).toEqual([
      '原始讲稿内容',
      '第二节讲稿内容',
    ])
    expect(wrapper.get('.script-body.active .script-content').text()).toContain('第二节讲稿内容')
    expect(wrapper.emitted('ai-scope-change')?.at(-1)).toEqual([{ id: 'section-2', title: '1.2 HTTP 请求与响应' }])
    expect((wrapper.vm as any).selectAiScope('missing-section')).toBe(false)
  })

  it('讲义生成后直接可用，不再出现确认操作', () => {
    const wrapper = mount(TeacherScriptDocument, { props: { courseId: 'course-1', lesson } })
    expect(wrapper.find('.script-footer').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('确认本讲讲义')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.find('.script-state').exists()).toBe(false)
    expect(wrapper.find('.script-saved').exists()).toBe(false)
  })

  it('允许课程工作台接管标题与操作栏，正文只保留小节和内容', () => {
    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson, externalToolbar: true },
      slots: { toolbar: '<div class="external-script-toolbar">讲稿操作</div>' },
    })

    expect(wrapper.find('.script-header').exists()).toBe(false)
    expect(wrapper.find('.script-footer').exists()).toBe(false)
    expect(wrapper.get('.external-script-toolbar').text()).toBe('讲稿操作')
    expect(wrapper.find('.script-body').exists()).toBe(true)
  })

  it('无讲稿时先映射教案教学块，核对后直接触发生成', async () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }
    emptyLesson.plan.revisions = [{
      revision_id: 'plan-1', lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1',
      generation_source: 'model', status: 'draft', warnings: [], actor: 'teacher', created_at: '',
      plan: {
        sections: [{
          node_id: 'section-1',
          teaching_modules: [{
            module_id: 'core_explanation', label: '核心教学', planned_minutes: 20,
            teacher_activity: '用界面实例讲清用户、任务和界面之间的关系',
          }],
        }],
      },
    }]
    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson: emptyLesson, canGenerate: true },
    })

    expect(wrapper.get('.script-source-steps').text()).toContain('检查教案映射')
    expect(wrapper.get('.script-source-steps').text()).toContain('生成讲义')
    expect(wrapper.get('.script-source-blocks').text()).toContain('核心教学')
    expect(wrapper.get('.script-source-blocks').text()).toContain('用界面实例讲清')
    expect(wrapper.find('.script-source-review textarea').exists()).toBe(false)
    await wrapper.get('.script-source-review').trigger('submit')

    expect(wrapper.emitted('generate')).toEqual([['']])
    expect(wrapper.find('.script-footer').exists()).toBe(false)
  })

  it('教案不可用时突出阻塞状态，不再显示正常生成说明', () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }

    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson: emptyLesson, canGenerate: false },
    })

    const blocked = wrapper.get('.script-source-review__blocked')
    expect(blocked.attributes('role')).toBe('status')
    expect(blocked.text()).toContain('暂无可用教案')
    expect(blocked.text()).toContain('请先完成本讲教案，再生成讲义。')
    expect(blocked.find('svg').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('本讲讲义将按以下教案生成')
    expect(wrapper.text()).not.toContain('教案中还没有可映射的教学块')
    expect(wrapper.get('.script-source-review button').attributes('disabled')).toBeDefined()
  })

  it('资料状态阻塞时展示真实原因，不误报为缺少教案', () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }

    const wrapper = mount(TeacherScriptDocument, {
      props: {
        courseId: 'course-1', lesson: emptyLesson, canGenerate: false,
        generationBlockedReason: '正在更新课程资料…',
      },
    })

    const blocked = wrapper.get('.script-source-review__blocked')
    expect(blocked.text()).toContain('暂时无法生成讲义')
    expect(blocked.text()).toContain('正在更新课程资料…')
    expect(blocked.text()).not.toContain('暂无可用教案')
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
    expect(wrapper.get('.script-source-review button').text()).toContain('继续生成剩余内容')

    await wrapper.get('.script-source-review').trigger('submit')
    expect(wrapper.emitted('generate')).toEqual([['']])

    await wrapper.setProps({
      generating: true,
      generationJob: { ...generationJob, status: 'running', message: '正在生成：核心教学' },
    })
    expect(wrapper.find('.script-source-review').exists()).toBe(false)
    expect(wrapper.get('.script-generation-progress').text()).toContain('正在生成：核心教学')
    const generationActions = wrapper.findAll('.script-generation-progress button')
    expect(generationActions.map(button => button.text())).toEqual(['暂停', '取消'])
    await generationActions[0]!.trigger('click')
    expect(wrapper.emitted('pause-generation')).toHaveLength(1)
    await generationActions[1]!.trigger('click')
    expect(wrapper.emitted('cancel-generation')).toHaveLength(1)

    await wrapper.setProps({
      generating: false,
      generationJob: { ...generationJob, status: 'cancelled', message: '已停止生成，已完成内容仍然保留' },
    })
    expect(wrapper.get('.script-source-review button').text()).toContain('继续生成剩余内容')
  })

  it('按当前教学块实时渲染流式增量文本', async () => {
    const emptyLesson = structuredClone(lesson)
    emptyLesson.script = { ...emptyLesson.script, current_revision_id: '', ready: false, sections: [] }
    emptyLesson.arrangement.blocks = [{
      block_id: 'block-1', module_id: 'core_explanation', section_node_id: 'section-1',
      section_title: '1.1 爬虫基础', name: '核心教学', role: 'concept', purpose: '讲清概念',
      content_summary: '解释爬虫工作流程', planned_minutes: 20,
      teacher_activity: '', student_activity: '', expected_output: '', required: true,
    }]
    const generationJob = {
      id: 'script-job-stream', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'running', progress: 20,
      phase: 'lesson_script_generation', message: '正在生成：核心教学', warnings: [],
      total_blocks: 1, completed_blocks: 0, current_block_id: 'block-1', current_block_title: '核心教学',
      block_states: { 'block-1': 'running' }, streamed_block_content: { 'block-1': '爬虫会先发起请求' },
      streamed_sequence_by_shard: { 'block-1:shard-1': 1 }, result_sections: [],
    } as TeacherLessonJob
    const wrapper = mount(TeacherScriptDocument, {
      props: { courseId: 'course-1', lesson: emptyLesson, canGenerate: true, generating: true, generationJob },
    })

    expect(wrapper.get('.script-module').text()).toContain('核心教学')
    expect(wrapper.get('.script-module').text()).toContain('爬虫会先发起请求')
    expect(wrapper.find('.script-streamed-block .stream-caret').exists()).toBe(true)

    await wrapper.setProps({
      generationJob: {
        ...generationJob,
        progress: 32,
        streamed_block_content: { 'block-1': '爬虫会先发起请求，再解析响应。' },
        streamed_sequence_by_shard: { 'block-1:shard-1': 2 },
      },
    })

    expect(wrapper.get('.script-module').text()).toContain('再解析响应')
  })

  it('历史恢复稿不作为生成成功结果，只允许重试', () => {
    const recoveryLesson = structuredClone(lesson)
    recoveryLesson.script.ready = false
    recoveryLesson.script.publication_eligible = false
    recoveryLesson.script.generation_source = 'model_block_pipeline_with_recovery_preview'
    recoveryLesson.script.quality_contract_version = 'teacher_script_quality_v8'
    recoveryLesson.script.quality_report = {
      passed: false,
      publication_eligible: false,
      blocking_issues: [{
        code: 'teacher_script:recovery_draft_not_publishable',
        message: '当前稿包含本地恢复内容，只能继续编辑或重新生成。',
      }],
      review_issues: [],
      metrics: {},
    }
    const failedJob = {
      id: 'failed-ai-job', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'failed', progress: 5,
      phase: 'lesson_script_failed', message: 'AI 生成失败', warnings: [],
      total_blocks: 2, completed_blocks: 0, block_states: {}, result_sections: [],
      error: { code: 'provider_failed', message: '提供方失败', retryable: true },
    } as TeacherLessonJob

    const wrapper = mount(TeacherScriptDocument, {
      props: {
        courseId: 'course-1', lesson: recoveryLesson,
        generationJob: failedJob, generationError: '提供方失败',
      },
    })

    expect(wrapper.text()).not.toContain('恢复草稿')
    expect(wrapper.text()).not.toContain('当前稿包含本地恢复内容')
    expect(wrapper.text()).toContain('讲义生成失败')
    expect(wrapper.get('.script-source-review button').text()).toContain('生成本讲讲义')
    expect(wrapper.find('.script-footer').exists()).toBe(false)
  })

  it('AI 失败后展示通过检查的教师编辑稿，不把失败任务冒充正文来源', () => {
    const editedLesson = structuredClone(lesson)
    editedLesson.script.publication_eligible = true
    editedLesson.script.generation_source = 'teacher_edit'
    editedLesson.script.quality_report = {
      passed: true, publication_eligible: true,
      blocking_issues: [], review_issues: [], metrics: {},
    }
    const failedJob = {
      id: 'failed-ai-job', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'failed', progress: 5,
      phase: 'lesson_script_failed', message: 'AI 生成失败', warnings: [],
      total_blocks: 2, completed_blocks: 0, block_states: {}, result_sections: [],
      error: { code: 'provider_failed', message: '提供方失败', retryable: true },
    } as TeacherLessonJob

    const wrapper = mount(TeacherScriptDocument, {
      props: {
        courseId: 'course-1', lesson: editedLesson,
        generationJob: failedJob, generationError: '提供方失败',
      },
    })

    expect(wrapper.text()).toContain('教师编辑稿 · 当前讲义可用')
    expect(wrapper.text()).toContain('不是该次失败任务的输出')
    expect(wrapper.text()).not.toContain('讲稿生成失败')
    expect(wrapper.find('.script-footer').exists()).toBe(false)
  })
})
