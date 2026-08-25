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

  it('内联大纲始终使用同一内容结构，只在编辑态解锁操作', async () => {
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
    expect(wrapper.get('.outline-view-switch button.active').text()).toContain('正式大纲')
    const outlineElement = wrapper.get('[data-testid="outline-chapter-list"]').element
    const toolbarElement = wrapper.get('.outline-review__list-toolbar').element
    expect(wrapper.get('.outline-review').attributes('data-mode')).toBe('view')
    expect(wrapper.get('.outline-review__chapter-heading input').attributes('readonly')).toBeDefined()
    expect(wrapper.findAll('.outline-review__objective-text')).toHaveLength(2)
    expect(wrapper.find('.outline-review__chapter-heading textarea').exists()).toBe(false)
    expect(wrapper.find('.outline-review__section textarea').exists()).toBe(false)
    expect(wrapper.get('.outline-review__chapter-heading .outline-review__objective-text').text()).toBe('建立基础')
    expect(wrapper.get('.outline-review__section .outline-review__objective-text').text()).toBe('理解生命周期')
    expect(wrapper.get('.outline-review__list-toolbar').text()).toContain('AI 调整')
    expect(wrapper.find('[data-testid="add-outline-chapter"]').exists()).toBe(false)
    expect(wrapper.find('.outline-review__starting-point').exists()).toBe(false)
    expect(wrapper.find('.outline-coverage').exists()).toBe(false)
    expect(wrapper.find('.outline-retrieval').exists()).toBe(false)
    expect(wrapper.text()).toContain('确认课程大纲')
    await wrapper.get('.outline-review__list-toolbar button').trigger('click')
    expect(wrapper.emitted('open-ai')).toHaveLength(1)

    await wrapper.setProps({ editable: true })

    expect(wrapper.find('[data-testid="formal-outline-document"]').exists()).toBe(false)
    expect(wrapper.get('.outline-view-switch button.active').text()).toContain('课程结构')
    expect(wrapper.get('[data-testid="outline-chapter-list"]').element).toBe(outlineElement)
    expect(wrapper.get('.outline-review__list-toolbar').element).toBe(toolbarElement)
    expect(wrapper.get('.outline-review').attributes('data-mode')).toBe('edit')
    expect(wrapper.get('.outline-review__chapter-heading input').attributes('readonly')).toBeUndefined()
    expect(wrapper.find('.outline-review__objective-text').exists()).toBe(false)
    expect(wrapper.find('.outline-review__chapter-heading textarea').exists()).toBe(true)
    expect(wrapper.find('.outline-review__section textarea').exists()).toBe(true)
    expect(wrapper.get('.outline-review__list-toolbar').text()).toContain('AI 调整')
    expect(wrapper.find('[data-testid="add-outline-chapter"]').exists()).toBe(true)
    expect(wrapper.find('.outline-review__adjustment').exists()).toBe(false)
    expect(wrapper.find('.outline-review__adjustment').exists()).toBe(false)
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
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('完成一项可检查的生命周期任务')
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

  it('新增章和小节后滚动并聚焦标题，避免长大纲看起来没有响应', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const scrollIntoView = vi.fn()
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })
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

    try {
      await flushPromises()
      await wrapper.get('[data-testid="add-outline-chapter"]').trigger('click')
      await flushPromises()

      const chapterInputs = wrapper.findAll('.outline-review__chapter-heading input')
      const addedInput = chapterInputs.at(-1)!
      expect((addedInput.element as HTMLInputElement).value).toBe('新章节 2')
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
      expect(document.activeElement).toBe(addedInput.element)
      expect((addedInput.element as HTMLInputElement).selectionStart).toBe(0)
      expect((addedInput.element as HTMLInputElement).selectionEnd).toBe('新章节 2'.length)

      scrollIntoView.mockClear()
      const addedChapter = wrapper.findAll('.outline-review__chapter').at(-1)!
      await addedChapter.get('button[title="新增小节"]').trigger('click')
      await flushPromises()

      const addedSectionInput = addedChapter.get('.outline-review__section input')
      expect((addedSectionInput.element as HTMLInputElement).value).toBe('新小节 1')
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
      expect(document.activeElement).toBe(addedSectionInput.element)
      expect((addedSectionInput.element as HTMLInputElement).selectionStart).toBe(0)
      expect((addedSectionInput.element as HTMLInputElement).selectionEnd).toBe('新小节 1'.length)
    } finally {
      wrapper.unmount()
      if (originalScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
          configurable: true,
          value: originalScrollIntoView,
        })
      } else {
        delete (HTMLElement.prototype as { scrollIntoView?: typeof HTMLElement.prototype.scrollIntoView }).scrollIntoView
      }
    }
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

    await wrapper.get('.outline-review__chapter-heading input').setValue('新的基础章')
    const finished = await (wrapper.vm as any).finishEditing()

    expect(finished).toBe(true)
    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      nodes: expect.arrayContaining([expect.objectContaining({ node_name: '新的基础章' })]),
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

    await wrapper.get('.outline-review__section textarea').setValue('准确选择生命周期入口')
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
    expect(wrapper.findAll('.outline-review__chapters input').map(input => (input.element as HTMLInputElement).value))
      .toContain('组件组合')
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
    await wrapper.get('.outline-review__chapter-heading input').setValue('手动修改后的基础章')
    await flushPromises()

    expect(wrapper.find('[data-testid="apply-outline-adjustment"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('目录已被手动修改，请重新生成方案')
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
