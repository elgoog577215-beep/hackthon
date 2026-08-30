import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: httpMock,
  teacherRequestConfig: (config = {}) => config,
}))
vi.mock('vue-router', async () => {
  const actual = await vi.importActual<any>('vue-router')
  return {
    ...actual,
    useRoute: () => ({ params: { courseId: 'course-1' }, query: {} }),
    useRouter: () => routerMock,
  }
})

import TeacherMaterialAuditReportView from '@/views/TeacherMaterialAuditReportView.vue'

const plan = {
  schema_version: 'course_material_absorption_v1',
  plan_id: 'plan-1',
  status: 'ready',
  unresolved_items: [],
  scope_options: [{ scope_id: 'lesson-1', label: '第一讲' }],
  summary: { target_count: 1, working_draft_count: 1, unresolved_count: 0, source_count: 1 },
  targets: [{
    target_id: 'managed:outline',
    target_type: 'outline',
    target_scope_id: 'course',
    target_scope_label: '整课',
    title: '课程大纲',
    status: 'ready',
    issues: [],
    review_items: [],
    sources: [{
      asset_id: 'asset-1', filename: '课程大纲.docx', relative_path: '已有资料/课程大纲.docx',
      action: 'absorb', role: 'primary', version_role: 'current', parse_status: 'parsed', parse_warnings: [],
    }],
    structured_draft: {
      schema_version: 'structured_material_document_v1', title: '课程大纲',
      sections: [{
        section_id: 'section-1', title: '课程目标', source_asset_id: 'asset-1', source_role: 'primary',
        blocks: [{ block_id: 'block-1', kind: 'paragraph', text: '掌握课程核心内容' }],
      }],
    },
  }],
}

const packageData = {
  package_id: 'package-1', course_id: 'course-1', course_name: '数据结构', asset_count: 1,
  assets: [{
    asset_id: 'asset-1', filename: '课程大纲.docx', relative_path: '已有资料/课程大纲.docx',
    document_type: 'outline', version_role: 'current', parse_status: 'parsed', parse_warnings: [],
    structure_matches: [{ node_id: 'course', title: '整课' }],
    absorption_decision: { action: 'absorb', role: 'primary', target_scope_id: 'lesson-1' },
  }],
  material_absorption: plan,
}

const evolutionProgress = {
  course_evolution_plans: [{
    change_set_id: 'change-1', request_text: '所有案例都补充适用边界', status: 'pending', generation_status: 'ready',
    evidence_ids: [], operations: [], allowed_scopes: ['current'], impact_summary: {}, expected_effect: '案例更完整', effect_evaluation: {},
    teacher_change_planning: {
      plan_id: 'change-1', updated_at: '2026-08-30T10:00:00Z', created_at: '2026-08-30T09:00:00Z',
      intent: { interpreted_goal: '补充所有案例的适用边界' },
    },
  }, {
    change_set_id: 'change-2', request_text: '所有案例都补充适用边界', status: 'pending', generation_status: 'ready',
    evidence_ids: [], operations: [], allowed_scopes: ['current'], impact_summary: {}, expected_effect: '案例更完整', effect_evaluation: {},
    teacher_change_planning: {
      plan_id: 'change-2', updated_at: '2026-08-30T09:00:00Z', created_at: '2026-08-30T08:00:00Z',
      intent: { interpreted_goal: '补充所有案例的适用边界' },
    },
  }, {
    change_set_id: 'change-3', request_text: '所有案例都补充适用边界', status: 'applied', generation_status: 'ready',
    evidence_ids: [], operations: [], allowed_scopes: ['current'], impact_summary: {}, expected_effect: '案例更完整', effect_evaluation: {},
    teacher_change_planning: {
      plan_id: 'change-3', updated_at: '2026-08-29T09:00:00Z', created_at: '2026-08-29T08:00:00Z',
      intent: { interpreted_goal: '补充所有案例的适用边界' },
    },
  }],
  summary: {},
}

const courseContext = {
  schema_version: 'teacher_course_change_context_v1', index_schema_version: 'teacher_course_change_index_v1',
  course_id: 'course-1', course_title: '数据结构', source_mode: 'authoring_workspace', ready: true,
  readiness_message: '', base_revision_vector: {}, assets: [], outline: [], units: [], updated_at: '',
  summary: { available_assets: 0, missing_assets: 0, indexed_units: 0, outline_nodes: 0 },
}

function mountReport() {
  return mount(TeacherMaterialAuditReportView, {
    props: { courseId: 'course-1' },
    global: {
      plugins: [createPinia()],
      stubs: {
        Teleport: true,
        CourseEvolutionWorkspace: { template: '<div class="course-evolution-stub">全课影响扫描</div>' },
      },
    },
  })
}

describe('TeacherMaterialAuditReportView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerMock.push.mockReset()
    httpMock.get.mockReset().mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [packageData] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: packageData })
      if (url.endsWith('/evolution/progress')) return Promise.resolve({ data: evolutionProgress })
      if (url.endsWith('/evolution/course-context')) return Promise.resolve({ data: courseContext })
      return Promise.resolve({ data: {} })
    })
    httpMock.patch.mockReset().mockResolvedValue({ data: { package: packageData } })
    httpMock.post.mockReset().mockResolvedValue({
      data: {
        package: {
          ...packageData,
          material_absorption: {
            ...plan,
            status: 'executed',
            execution: { receipts: [{ bundle_id: 'bundle-1', plan_id: 'plan-1', target_ids: ['managed:outline'], status: 'working_drafts_created', executed_at: '2026-08-30T10:30:00Z' }] },
          },
        },
      },
    })
  })

  it('把材料变化与全课调整收入同一更新中心', async () => {
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.text()).toContain('审计与更新中心')
    expect(wrapper.text()).toContain('变化来源')
    expect(wrapper.text()).toContain('课程材料')
    expect(wrapper.text()).toContain('待处理调整')
    expect(wrapper.text()).toContain('课程大纲.docx')
    expect(wrapper.text()).toContain('所有案例都补充适用边界')
    expect(wrapper.text()).toContain('2 次同类调整')
    expect(wrapper.text()).toContain('生成关系')
    expect(wrapper.text()).toContain('课程目标')
    expect(wrapper.find('.source-filters').exists()).toBe(false)
    expect(wrapper.find('.create-change-row').exists()).toBe(false)
    expect(wrapper.findAll('.course-change-group .source-list > button')).toHaveLength(1)

    const addSourceTrigger = wrapper.get('.source-add-trigger')
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    await addSourceTrigger.trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    await addSourceTrigger.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)

    await wrapper.get('.course-change-group .source-list > button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.course-evolution-stub').exists()).toBe(true)
  })

  it('按老师确认的范围执行结构化更新', async () => {
    const wrapper = mountReport()
    await flushPromises()

    await wrapper.get('.center-actionbar .primary').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/material-absorption/execute',
      { target_ids: ['managed:outline'] },
      expect.anything(),
    )
  })

  it('在同一中心内确认材料课程位置', async () => {
    const unresolvedPackage = {
      ...packageData,
      assets: [{ ...packageData.assets[0], absorption_decision: { action: 'absorb', role: 'primary' } }],
      material_absorption: {
        ...plan,
        status: 'needs_decision',
        unresolved_items: [{
          code: 'target_scope_unresolved', asset_id: 'asset-1', filename: '课程大纲.docx',
          message: '课程大纲.docx 尚未确定对应讲次。',
        }],
      },
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [unresolvedPackage] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: unresolvedPackage })
      if (url.endsWith('/evolution/progress')) return Promise.resolve({ data: evolutionProgress })
      if (url.endsWith('/evolution/course-context')) return Promise.resolve({ data: courseContext })
      return Promise.resolve({ data: {} })
    })

    const wrapper = mountReport()
    await flushPromises()

    await wrapper.findAll('.material-decisions select')[1]!.setValue('lesson-1')
    await flushPromises()

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/assets/asset-1/absorption',
      { target_scope_id: 'lesson-1', action: 'absorb' },
      expect.anything(),
    )
  })

  it('纠正文件类型后重新计算生成关系', async () => {
    httpMock.patch.mockResolvedValue({ data: { ...packageData.assets[0], document_type: 'lesson_plan' } })
    httpMock.post.mockImplementation((url: string) => {
      if (url.endsWith('/material-absorption/refresh')) return Promise.resolve({ data: { package: packageData } })
      return Promise.resolve({ data: { package: packageData } })
    })
    const wrapper = mountReport()
    await flushPromises()

    await wrapper.findAll('.material-decisions select')[0]!.setValue('lesson_plan')
    await flushPromises()

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/assets/asset-1',
      { document_type: 'lesson_plan' },
      expect.anything(),
    )
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/material-absorption/refresh',
      {},
      expect.anything(),
    )
  })
})
