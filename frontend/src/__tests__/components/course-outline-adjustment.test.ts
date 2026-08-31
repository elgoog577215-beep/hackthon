import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseOutlineReview from '@/components/CourseOutlineReview.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import zhMessages from '../../../public/locales/zh/translation.json'

function currentDraft() {
  return {
    base_blueprint_revision_id: 'bp-1',
    draft_revision_id: 'draft-1',
    course_name: 'Unity 游戏编程',
    course_type: 'systematic',
    course_purpose: 'systematic',
    course_blueprint: {},
    learning_asset_plan: {},
    blueprint_locks: {},
    nodes: [
      {
        node_id: 'L1-1',
        parent_node_id: 'root',
        node_level: 1,
        node_name: '基础',
        learning_objective: '建立基础',
      },
      {
        node_id: 'L2-1-1',
        parent_node_id: 'L1-1',
        node_level: 2,
        node_name: '生命周期',
        learning_objective: '理解生命周期',
      },
    ],
  }
}

function proposal() {
  const draft = currentDraft()
  draft.draft_revision_id = 'draft-proposed'
  draft.nodes.push({
    node_id: 'L2-1-2',
    parent_node_id: 'L1-1',
    node_level: 2,
    node_name: '组件组合',
    learning_objective: '使用组件组合能力',
  })
  return {
    proposal_id: 'proposal-1',
    source_draft_revision_id: 'draft-2',
    operations: [{ op: 'add_node', temp_ref: 'tmp-1' }],
    summary: '新增“组件组合”小节',
    diff: {
      added: [{ node_name: '组件组合', new_position: '第1章 · 第2节' }],
      removed: [],
      moved: [{ node_name: '生命周期', old_position: '第2节', new_position: '第1节' }],
      updated: [],
      before: { chapter_count: 1, section_count: 1 },
      after: { chapter_count: 1, section_count: 2 },
    },
    draft,
    impact_report: {},
    constraint_report: { chapter_count: 1, section_count: 2 },
    can_apply: true,
    blocking_issues: [],
    warnings: [],
  }
}

describe('一句话调整课程目录', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
  })

  it('内联大纲始终使用同一篇文档，只在编辑态解锁文字工具', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        ...currentDraft(),
        course_type: 'project',
        course_intent: { expected_deliverable: '研究报告' },
        learner_starting_profile: { status: 'tentative', self_reported_strengths: ['会写提示词'] },
      },
      coverage: { available: true, status: 'partial', scale_label: '专题课' },
      retrieval: { notice: '联网核验未完成' },
    } as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: false,
        variant: 'inline',
        requiresConfirmation: true,
        surface: 'teacher',
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="formal-outline-document"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('Unity 游戏编程')
    const editorElement = wrapper.get('[data-testid="outline-rich-editor"]').element
    expect(wrapper.get('.outline-review').attributes('data-mode')).toBe('view')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').attributes('contenteditable')).toBe('false')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').text()).toContain('理解生命周期')
    expect(wrapper.find('.outline-document-toolbar').exists()).toBe(false)
    expect(wrapper.find('[data-testid="add-outline-chapter"]').exists()).toBe(false)
    expect(wrapper.find('.outline-review__starting-point').exists()).toBe(false)
    expect(wrapper.find('.outline-coverage').exists()).toBe(false)
    expect(wrapper.find('.outline-retrieval').exists()).toBe(false)
    expect(wrapper.text()).toContain('确认课程大纲')
    await wrapper.setProps({ editable: true })

    expect(wrapper.find('[data-testid="formal-outline-document"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="outline-rich-editor"]').element).toBe(editorElement)
    expect(wrapper.get('.outline-review').attributes('data-mode')).toBe('edit')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').attributes('contenteditable')).toBe('true')
    expect(wrapper.get('.outline-document-toolbar').text()).toContain('章标题')
    expect(wrapper.get('.outline-document-toolbar').text()).toContain('加粗')
    expect(wrapper.text()).not.toContain('课程结构')
    expect(wrapper.find('[data-testid="add-outline-chapter"]').exists()).toBe(false)
    expect(wrapper.find('.outline-review__adjustment').exists()).toBe(false)
  })

  it('教师正式大纲按老师模板显示，并把已有一章一节结果归一为单层讲次', async () => {
    const workspace = useCourseWorkspaceStore()
    const draft = {
      ...currentDraft(),
      authoring_structure_version: 'lecture_v1',
      course_generation_brief: {
        course_shape_constraints: { teacher_lecture_mode: true },
        formal_course_profile: {
          active_week_start: 1,
          schedule_slots: [
            { weekday: 1, period: 1 },
            { weekday: 1, period: 2 },
            { weekday: 3, period: 5 },
            { weekday: 3, period: 6 },
            { weekday: 3, period: 7 },
          ],
        },
      },
      course_plan: {
        authoring_structure_version: 'lecture_v1',
        course_title: '电动力学',
        course_intro_zh: '从经典电磁场理论建立统一分析框架。',
        course_intro_en: 'A systematic introduction to classical electrodynamics.',
        learning_objectives: ['能解释并运用麦克斯韦方程组'],
        education_objectives: ['形成严谨求证的科学态度'],
        measurable_outcomes: ['能够独立完成典型边值问题'],
        teaching_methods: ['线下课堂'],
        assessment_methods: ['课堂任务与期末考核'],
        reference_books: ['郭硕鸿：《电动力学》'],
        chapters: [{
          chapter_number: 1,
          title: '第1章 静电场与边值问题',
          sections: [{
            node_id: 'L2-1-1',
            section_number: '1.1',
            title: '1.1 静电场基本方程',
            content_summary: '介绍静电场基本方程、边界条件与典型求解方法。',
            planned_hours: 2,
          }],
        }],
      },
      nodes: [
        { ...currentDraft().nodes[0], node_name: '第1章 静电场与边值问题' },
        { ...currentDraft().nodes[1], node_name: '1.1 静电场基本方程', content_summary: '介绍静电场基本方程、边界条件与典型求解方法。' },
      ],
    }
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: draft } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-electrodynamics',
        courseName: '电动力学',
        editable: false,
        variant: 'inline',
        surface: 'teacher',
      },
    })
    await flushPromises()

    const document = wrapper.get('[data-testid="formal-outline-document"]')
    expect(document.text()).toContain('一、课程介绍')
    expect(document.text()).toContain('二、教学目标')
    expect(document.text()).toContain('三、课程要求')
    expect(document.text()).toContain('四、教学内容及教学安排')
    expect(document.text()).toContain('第1讲 静电场与边值问题')
    expect(document.text()).toContain('五、参考资料')
    expect(document.text()).toContain('六、课程教学网站')
    expect(document.text()).not.toContain('第1章')
    expect(document.text()).not.toContain('1.1')
    expect(document.text()).not.toContain('小节')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').text()).toContain('介绍静电场基本方程')
    expect(wrapper.find('button[title="Markdown"]').exists()).toBe(false)
  })

  it('页面内部不再复制节点 AI，整篇 AI 仍通过右侧接口生成和应用', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const candidate: any = proposal()
    candidate.summary = '把生命周期目标改得更具体'
    candidate.operations = [{ op: 'update_node', node_ref: 'L2-1-1' }]
    candidate.diff = {
      ...candidate.diff,
      added: [], moved: [],
      updated: [{
        node_id: 'L2-1-1',
        node_name: '生命周期',
        changes: {
          learning_objective: {
            before: '理解生命周期',
            after: '能按执行顺序解释并验证生命周期回调',
          },
        },
      }],
      before: { chapter_count: 1, section_count: 1 },
      after: { chapter_count: 1, section_count: 1 },
    }
    candidate.draft.nodes = currentDraft().nodes.map(node => node.node_id === 'L2-1-1'
      ? { ...node, learning_objective: '能按执行顺序解释并验证生命周期回调' }
      : node)
    const preview = vi.spyOn(workspace, 'previewBlueprintAdjustment').mockResolvedValue(candidate as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({ draft: payload }) as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        requiresConfirmation: false,
        surface: 'teacher',
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-node-ai-action"]').exists()).toBe(false)
    await (wrapper.vm as any).requestAiCandidate('把目标改成课堂上可以检查的行为')
    await flushPromises()

    expect(preview).toHaveBeenCalledWith('course-1', expect.objectContaining({
      instruction: '把目标改成课堂上可以检查的行为',
    }))
    expect(wrapper.emitted('ai-candidate-change')?.[0]?.[0]).toEqual(expect.objectContaining({
      summary: '把生命周期目标改得更具体',
    }))

    await (wrapper.vm as any).resolveAiCandidate(true)
    await flushPromises()
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      adjustment_operations: [{ op: 'update_node', node_ref: 'L2-1-1' }],
    }))
    expect(wrapper.get('[data-testid="outline-rich-editor"]').text())
      .toContain('能按执行顺序解释并验证生命周期回调')
  })

  it('从整篇质量建议直接生成定点修复候选', async () => {
    const workspace = useCourseWorkspaceStore()
    const draft = {
      ...currentDraft(),
      course_plan: {
        course_title: 'Unity 游戏编程',
        positioning: '面向初学者建立组件化游戏开发能力',
        learning_objectives: ['能设计并实现可运行的游戏原型'],
        prerequisites: ['基本编程语法'],
        chapters: [{
          chapter_number: 1,
          title: '基础',
          learning_focus: '建立运行机制认知',
          sections: [{
            node_id: 'L2-1-1',
            section_number: '1.1',
            title: '生命周期',
            learning_objective: '理解生命周期',
            assessment: '完成一项可检查的生命周期任务',
          }],
        }],
      },
    }
    const instruction = '只重写这些小节的 assessment，写清产出与判断标准。'
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: draft,
      quality: {
        status: 'review_suggested',
        summary: '发现 2 类可改进项，结构可继续使用。',
        issues: [
          {
            code: 'outline_editorial:missing_positioning',
            message: '课程定位待完善',
            node_ids: [],
            repair_instruction: '补写课程定位。',
          },
          {
            code: 'outline_editorial:repeated_assessment_template',
            message: '达成检验过于模板化',
            node_ids: ['L2-1-1'],
            repair_instruction: instruction,
          },
        ],
      },
    } as any)
    const preview = vi.spyOn(workspace, 'previewBlueprintAdjustment').mockResolvedValue(proposal() as any)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: false,
        variant: 'inline',
        requiresConfirmation: true,
        surface: 'teacher',
      },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('达成检验过于模板化')
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('生命周期')
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('理解生命周期')
    expect(wrapper.findAll('.outline-quality li button')).toHaveLength(1)
    await wrapper.get('.outline-quality li button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('open-ai')).toHaveLength(1)
    expect(preview).toHaveBeenCalledWith('course-1', expect.objectContaining({
      instruction: `${instruction}\n仅允许修改节点：L2-1-1。`,
    }))
    expect(wrapper.emitted('ai-candidate-change')?.[0]?.[0]).toEqual(expect.objectContaining({
      proposal_id: 'proposal-1',
    }))
  })

  it('工具栏只保留 Word 式文字与标题工具，不显示结构表单操作', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        surface: 'teacher',
      },
      attachTo: document.body,
    })

    await flushPromises()
    const toolbar = wrapper.get('.outline-document-toolbar')
    expect(toolbar.text()).toContain('章标题')
    expect(toolbar.text()).toContain('小节标题')
    expect(toolbar.text()).toContain('正文')
    expect(toolbar.text()).not.toContain('新增章')
    expect(toolbar.text()).not.toContain('上移')
    expect(toolbar.text()).not.toContain('删除')
    wrapper.unmount()
  })

  it('Markdown 是同一份结构化大纲的双向投影，并保留表格与流程图源码', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({ draft: payload }) as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        requiresConfirmation: false,
        surface: 'teacher',
      },
    })
    await flushPromises()

    const modeButtons = wrapper.findAll('.outline-editor-modes button')
    await modeButtons[1]!.trigger('click')
    await flushPromises()

    const source = wrapper.get<HTMLTextAreaElement>('[data-testid="outline-markdown-editor"] textarea')
    expect(source.element.value).toContain('## 基础')
    expect(source.element.value).toContain('### 生命周期')
    await source.setValue([
      '## 基础进阶',
      '',
      '建立可验证的编程基础。',
      '',
      '### 生命周期进阶',
      '',
      '| 阶段 | 结果 |',
      '| --- | --- |',
      '| 初始化 | 可运行 |',
      '',
      '```mermaid',
      'flowchart LR',
      '  A[开始] --> B[结果]',
      '```',
    ].join('\n'))

    await modeButtons[0]!.trigger('click')
    await flushPromises()
    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    expect(editor.get('h2').text()).toBe('基础进阶')
    expect(editor.get('h3').text()).toBe('生命周期进阶')
    expect(editor.find('table').exists()).toBe(true)

    await (wrapper.vm as any).finishEditing()
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({
        node_name: '生命周期进阶',
        outline_editor_html: expect.objectContaining({
          body_html: expect.stringContaining('<table>'),
          body_markdown: expect.stringContaining('```mermaid'),
        }),
      })]),
    }))
  })

  it('插入菜单可把可编辑表格写入当前文档并随大纲保存', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({ draft: payload }) as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        requiresConfirmation: false,
        surface: 'teacher',
      },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('.outline-insert-trigger').trigger('mousedown')
    const tableAction = wrapper.findAll('.outline-insert-menu button').find(button => button.text().includes('表格'))!
    await tableAction.trigger('mousedown')
    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    expect(editor.find('table').exists()).toBe(true)

    await (wrapper.vm as any).finishEditing()
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({
        outline_editor_html: expect.objectContaining({ body_html: expect.stringContaining('<table>') }),
      })]),
    }))
    wrapper.unmount()
  })

  it('把低频专业格式收进更多菜单，并提供公式与查找替换入口', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        surface: 'teacher',
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('.outline-document-toolbar').text()).toContain('更多格式')
    expect(wrapper.get('.outline-document-toolbar').text()).toContain('查找')
    await wrapper.get('.outline-menu-trigger').trigger('mousedown')
    expect(wrapper.get('.outline-format-menu').text()).toContain('段落对齐')
    expect(wrapper.get('.outline-format-menu').text()).toContain('清除格式')

    await wrapper.get('.outline-insert-trigger').trigger('mousedown')
    expect(wrapper.get('.outline-insert-menu').text()).toContain('公式')
    wrapper.unmount()
  })

  it('保留 Word 富文本粘贴，并让公式、查找替换与 Markdown 使用同一份正文', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({ draft: payload }) as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        requiresConfirmation: false,
        surface: 'teacher',
      },
      attachTo: document.body,
    })
    await flushPromises()

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        getData: (type: string) => type === 'text/html'
          ? '<p class="MsoNormal" style="font-size:16pt"><strong>课堂重点</strong>与<em>案例</em></p><ul><li>练习一</li></ul>'
          : '课堂重点与案例\n练习一',
      },
    })
    editor.element.dispatchEvent(pasteEvent)
    await flushPromises()
    expect(editor.html()).toContain('<strong>课堂重点</strong>')
    expect(editor.html()).toContain('<em>案例</em>')
    expect(editor.find('ul').exists()).toBe(true)
    expect(editor.html()).not.toContain('MsoNormal')

    await wrapper.get('.outline-insert-trigger').trigger('mousedown')
    const formulaAction = wrapper.findAll('.outline-insert-menu button').find(button => button.text().includes('公式'))!
    await formulaAction.trigger('mousedown')
    await wrapper.get('.outline-insert-prompt input').setValue('E = mc^2')
    await wrapper.get('.outline-insert-prompt').trigger('submit')
    expect(editor.find('[data-formula="E = mc^2"]').exists()).toBe(true)

    await wrapper.get('.outline-find-trigger').trigger('mousedown')
    await wrapper.get('.outline-find-panel input[type="search"]').setValue('生命周期')
    await wrapper.get('.outline-find-panel input[type="text"]').setValue('生命周期方法')
    await wrapper.findAll('.outline-find-panel__actions button')[1]!.trigger('click')
    expect(editor.text()).toContain('生命周期方法')
    expect(editor.find('[data-formula="E = mc^2"]').exists()).toBe(true)

    const modeButtons = wrapper.findAll('.outline-editor-modes button')
    await modeButtons[1]!.trigger('click')
    await flushPromises()
    const markdown = wrapper.get<HTMLTextAreaElement>('[data-testid="outline-markdown-editor"] textarea')
    expect(markdown.element.value).toContain('$E = mc^2$')
    expect(markdown.element.value).toContain('**课堂重点**')

    await modeButtons[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="outline-rich-editor"]').find('[data-formula="E = mc^2"]').exists()).toBe(true)
    await (wrapper.vm as any).finishEditing()
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({
        outline_editor_html: expect.objectContaining({ body_html: expect.stringContaining('data-formula="E = mc^2"') }),
      })]),
    }))
    wrapper.unmount()
  })

  it('完成编辑时保存当前修改并留在同一大纲页', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({
      draft: { ...payload, draft_revision_id: 'draft-2' },
    }) as any)
    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-1',
        courseName: 'Unity 游戏编程',
        editable: true,
        variant: 'inline',
        requiresConfirmation: false,
        surface: 'teacher',
      },
    })
    await flushPromises()

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    editor.get('h2').element.innerHTML = '<strong>新的基础章</strong>'
    await editor.trigger('input')
    const finished = await (wrapper.vm as any).finishEditing()

    expect(finished).toBe(true)
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({ node_name: '新的基础章' })]),
    }))
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({
        outline_editor_html: expect.objectContaining({ title_html: '<strong>新的基础章</strong>' }),
      })]),
    }))
  })

  it('先保存手动修改，再生成差异并通过现有草稿接口应用整套方案', async () => {
    const course = useCourseStore()
    course.currentCourseId = 'course-1'
    course.currentCourseProjection = 'generation_preview'
    course.nodes = currentDraft().nodes.map(node => ({
      ...node,
      node_content: '',
      node_type: 'original' as const,
      generation_status: 'pending' as const,
      generated_chars: 0,
      children: [],
    }))
    course.courseTree = course.buildTree(course.nodes)
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({
      draft: { ...payload, draft_revision_id: 'draft-2' },
    }) as any)
    const preview = vi.spyOn(workspace, 'previewBlueprintAdjustment').mockResolvedValue(proposal() as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-1', courseName: 'Unity 游戏编程' },
      attachTo: document.body,
    })
    await flushPromises()

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    const sectionBody = editor.element.querySelector<HTMLElement>('[data-node-body="L2-1-1"] p')!
    sectionBody.textContent = '准确选择生命周期入口'
    await editor.trigger('input')
    await wrapper.get('.outline-review__adjustment textarea').setValue('新增一节组件组合，并把生命周期放在最前面')
    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledTimes(1)
    expect(preview).toHaveBeenCalledWith('course-1', expect.objectContaining({
      base_blueprint_revision_id: 'bp-1',
      expected_draft_revision_id: 'draft-2',
      instruction: '新增一节组件组合，并把生命周期放在最前面',
    }))
    expect(save.mock.invocationCallOrder[0]!).toBeLessThan(preview.mock.invocationCallOrder[0]!)
    expect(wrapper.text()).toContain('新增“组件组合”小节')
    expect(wrapper.text()).toContain('第2节')
    expect(wrapper.text()).toContain('第1节')
    expect(document.activeElement).toBe(wrapper.get('.outline-review__proposal').element)

    await wrapper.get('[data-testid="apply-outline-adjustment"]').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith('course-1', expect.objectContaining({
      expected_draft_revision_id: 'draft-2',
      adjustment_operations: [{ op: 'add_node', temp_ref: 'tmp-1' }],
      nodes: expect.arrayContaining([
        expect.objectContaining({ node_name: '组件组合' }),
      ]),
    }))
    expect(wrapper.text()).toContain('方案已应用并保存')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').text()).toContain('组件组合')
    expect(course.nodes.map(node => node.node_name)).toContain('组件组合')
    expect(course.courseTree[0]?.children?.map(node => node.node_name)).toEqual([
      '生命周期',
      '组件组合',
    ])
  })

  it('取消预览不写入；预览后手动编辑会立即使方案失效', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockResolvedValue({} as any)
    vi.spyOn(workspace, 'previewBlueprintAdjustment').mockResolvedValue(proposal() as any)
    const cancel = vi.spyOn(workspace, 'cancelBlueprintAdjustment').mockResolvedValue({ status: 'cancelled' } as any)
    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-1', courseName: 'Unity 游戏编程' },
    })
    await flushPromises()

    await wrapper.get('.outline-review__adjustment textarea').setValue('新增一节组件组合')
    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="cancel-outline-adjustment"]').trigger('click')
    expect(save).not.toHaveBeenCalled()
    expect(cancel).toHaveBeenCalledWith('course-1', 'proposal-1', expect.stringContaining('outline-adjustment-'))
    expect(wrapper.find('.outline-review__proposal').exists()).toBe(false)

    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()
    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    editor.get('h2').element.textContent = '手动修改后的基础章'
    await editor.trigger('input')
    await flushPromises()

    expect(wrapper.find('[data-testid="apply-outline-adjustment"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('大纲已修改，保存后生效')
  })

  it('刷新恢复未确认草稿时同步更新导航树，而不是继续显示生成预览旧目录', async () => {
    const course = useCourseStore()
    course.currentCourseId = 'course-1'
    course.currentCourseProjection = 'generation_preview'
    course.nodes = currentDraft().nodes.map(node => ({
      ...node,
      node_content: '',
      node_type: 'original' as const,
      generation_status: 'pending' as const,
      generated_chars: 0,
      children: [],
    }))
    course.courseTree = course.buildTree(course.nodes)

    const savedDraft = proposal().draft
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: currentDraft(),
      draft: savedDraft,
      has_unconfirmed_draft: true,
    } as any)

    mount(CourseOutlineReview, {
      props: { courseId: 'course-1', courseName: 'Unity 游戏编程' },
    })
    await flushPromises()

    expect(course.nodes.map(node => node.node_name)).toContain('组件组合')
    expect(course.courseTree[0]?.children?.map(node => node.node_name)).toEqual([
      '生命周期',
      '组件组合',
    ])
  })
})
