import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseOutlineReview from '@/components/CourseOutlineReview.vue'
import { setLocale } from '@/shared/i18n'
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

  it('先保存手动修改，再生成差异并通过现有草稿接口应用整套方案', async () => {
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

    await wrapper.get('.outline-review__nodes textarea').setValue('准确选择生命周期入口')
    await wrapper.get('.outline-review__adjustment textarea').setValue('新增一节组件组合，并把生命周期放在最前面')
    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledTimes(1)
    expect(preview).toHaveBeenCalledWith('course-1', expect.objectContaining({
      base_blueprint_revision_id: 'bp-1',
      expected_draft_revision_id: 'draft-2',
      instruction: '新增一节组件组合，并把生命周期放在最前面',
    }))
    expect(save.mock.invocationCallOrder[0]).toBeLessThan(preview.mock.invocationCallOrder[0])
    expect(wrapper.text()).toContain('新增“组件组合”小节')
    expect(wrapper.text()).toContain('第2节')
    expect(wrapper.text()).toContain('第1节')
    expect(document.activeElement).toBe(wrapper.get('.outline-review__proposal').element)

    await wrapper.get('[data-testid="apply-outline-adjustment"]').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith('course-1', expect.objectContaining({
      expected_draft_revision_id: 'draft-2',
      nodes: expect.arrayContaining([
        expect.objectContaining({ node_name: '组件组合' }),
      ]),
    }))
    expect(wrapper.text()).toContain('方案已应用并保存')
    expect(wrapper.text()).toContain('组件组合')
  })

  it('取消预览不写入；预览后手动编辑会立即使方案失效', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: currentDraft() } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockResolvedValue({} as any)
    vi.spyOn(workspace, 'previewBlueprintAdjustment').mockResolvedValue(proposal() as any)
    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-1', courseName: 'Unity 游戏编程' },
    })
    await flushPromises()

    await wrapper.get('.outline-review__adjustment textarea').setValue('新增一节组件组合')
    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="cancel-outline-adjustment"]').trigger('click')
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.find('.outline-review__proposal').exists()).toBe(false)

    await wrapper.get('[data-testid="generate-outline-adjustment"]').trigger('click')
    await flushPromises()
    await wrapper.get('.outline-review__nodes input').setValue('手动修改后的基础章')
    await flushPromises()

    expect(wrapper.find('[data-testid="apply-outline-adjustment"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('目录已被手动修改，请重新生成方案')
  })
})
