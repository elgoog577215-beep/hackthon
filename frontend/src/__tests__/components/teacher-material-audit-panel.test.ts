import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: httpMock,
  teacherRequestConfig: (config = {}) => config,
}))

import TeacherMaterialAuditPanel from '@/components/TeacherMaterialAuditPanel.vue'

const plan = {
  schema_version: 'course_material_absorption_v1',
  plan_id: 'plan-1',
  status: 'ready',
  unresolved_items: [],
  scope_options: [{ scope_id: 'lesson-1', label: '第一讲' }],
  summary: { target_count: 1, working_draft_count: 1, unresolved_count: 0, source_count: 1 },
  targets: [{
    target_id: 'lesson-plan:lesson-1',
    target_type: 'lesson_plan',
    target_scope_id: 'lesson-1',
    target_scope_label: '第一讲',
    title: '第一讲教案',
    status: 'ready',
    issues: [],
    review_items: [],
    sources: [{
      asset_id: 'asset-1',
      filename: '第一讲教案.docx',
      relative_path: '已有资料/第一讲教案.docx',
      action: 'absorb',
      role: 'primary',
      version_role: 'current',
      parse_status: 'parsed',
      parse_warnings: [],
    }],
    structured_draft: {
      schema_version: 'structured_material_document_v1',
      title: '第一讲教案',
      sections: [{
        section_id: 'section-1',
        title: '教学目标',
        source_asset_id: 'asset-1',
        source_role: 'primary',
        blocks: [{ block_id: 'block-1', kind: 'paragraph', text: '掌握核心概念' }],
      }],
    },
  }],
}

const packageData = {
  package_id: 'package-1',
  course_id: 'course-1',
  asset_count: 1,
  assets: [{
    asset_id: 'asset-1',
    filename: '第一讲教案.docx',
    relative_path: '已有资料/第一讲教案.docx',
    document_type: 'lesson_plan',
    structure_matches: [{ node_id: 'lesson-1' }],
  }],
  material_absorption: plan,
}

describe('TeacherMaterialAuditPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    httpMock.get.mockReset().mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [packageData] })
      return Promise.resolve({ data: packageData })
    })
    httpMock.post.mockReset().mockResolvedValue({
      data: {
        package: {
          ...packageData,
          material_absorption: {
            ...plan,
            execution: {
              receipts: [{ plan_id: 'plan-1', target_ids: ['lesson-plan:lesson-1'], status: 'working_drafts_created' }],
            },
          },
        },
        receipt: { status: 'working_drafts_created' },
        authoring_receipt: { status: 'working_drafts_created' },
      },
    })
    httpMock.patch.mockReset().mockResolvedValue({ data: { package: packageData } })
  })

  it('在当前教案页展示来源、审计结果和工作稿边界', async () => {
    const wrapper = mount(TeacherMaterialAuditPanel, {
      props: { courseId: 'course-1', targetType: 'lesson_plan', targetScopeId: 'lesson-1' },
      global: { plugins: [createPinia()] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('材料审计')
    expect(wrapper.text()).toContain('第一讲教案.docx')
    expect(wrapper.text()).toContain('结构化结果')
    expect(wrapper.text()).toContain('不覆盖正式内容')
    expect(wrapper.text()).toContain('教学目标')

    await wrapper.get('footer .primary').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/material-absorption/execute',
      { target_ids: ['lesson-plan:lesson-1'] },
      expect.anything(),
    )
    expect(wrapper.emitted('executed')).toHaveLength(1)
    expect(wrapper.text()).toContain('工作稿已生成')
  })

  it('更换主来源时先把旧主来源降为参考', async () => {
    const secondSource = {
      asset_id: 'asset-2',
      filename: '第一讲教案-修订.docx',
      relative_path: '已有资料/第一讲教案-修订.docx',
      action: 'absorb',
      role: 'reference',
      version_role: 'unknown',
      parse_status: 'parsed',
      parse_warnings: [],
    }
    const packageWithTwoSources = {
      ...packageData,
      asset_count: 2,
      assets: [
        ...packageData.assets,
        { ...secondSource, document_type: 'lesson_plan', structure_matches: [{ node_id: 'lesson-1' }] },
      ],
      material_absorption: {
        ...plan,
        targets: [{ ...plan.targets[0]!, sources: [...plan.targets[0]!.sources, secondSource] }],
      },
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [packageWithTwoSources] })
      return Promise.resolve({ data: packageWithTwoSources })
    })
    httpMock.patch.mockResolvedValue({ data: { package: packageWithTwoSources } })

    const wrapper = mount(TeacherMaterialAuditPanel, {
      props: { courseId: 'course-1', targetType: 'lesson_plan', targetScopeId: 'lesson-1' },
      global: { plugins: [createPinia()] },
    })
    await flushPromises()

    const selects = wrapper.findAll('.material-audit__sources select')
    await selects[1]!.setValue('primary')
    await flushPromises()

    expect(httpMock.patch.mock.calls[0]?.[1]).toEqual({ role: 'reference', action: 'absorb' })
    expect(httpMock.patch.mock.calls[1]?.[1]).toEqual({ role: 'primary', action: 'absorb' })
  })
})
