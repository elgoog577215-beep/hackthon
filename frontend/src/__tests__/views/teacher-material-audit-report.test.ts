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
    useRoute: () => ({ params: { courseId: 'course-1' } }),
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
    document_type: 'outline', version_role: 'current', parse_status: 'parsed',
    structure_matches: [{ node_id: 'course', title: '整课' }],
    absorption_decision: { action: 'absorb', role: 'primary' },
  }],
  material_absorption: plan,
}

function mountReport() {
  return mount(TeacherMaterialAuditReportView, {
    props: { courseId: 'course-1' },
    global: {
      plugins: [createPinia()],
      stubs: {
        Teleport: true,
        RouterLink: { props: ['to'], template: '<a><slot /></a>' },
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
      return Promise.resolve({ data: packageData })
    })
    httpMock.patch.mockReset().mockResolvedValue({ data: { package: packageData } })
    httpMock.post.mockReset().mockResolvedValue({
      data: {
        package: {
          ...packageData,
          material_absorption: {
            ...plan,
            status: 'executed',
            execution: { receipts: [{ plan_id: 'plan-1', target_ids: ['managed:outline'], status: 'working_drafts_created' }] },
          },
        },
      },
    })
  })

  it('在独立页面集中展示完整审计并执行全部工作稿', async () => {
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.text()).toContain('课程材料审计报告')
    expect(wrapper.text()).toContain('文件审计结论')
    expect(wrapper.text()).toContain('课程大纲.docx')
    expect(wrapper.text()).toContain('结构化结果')
    expect(wrapper.text()).toContain('课程目标')

    await wrapper.get('.execute-all').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/material-absorption/execute',
      { target_ids: [] },
      expect.anything(),
    )
    expect(wrapper.text()).toContain('全部工作稿已生成')
  })

  it('在独立报告中解决讲次归属问题', async () => {
    const unresolvedPackage = {
      ...packageData,
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
      return Promise.resolve({ data: unresolvedPackage })
    })
    httpMock.patch.mockResolvedValue({ data: { package: packageData } })

    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.text()).toContain('需要老师确认')
    await wrapper.get('.report-decisions select').setValue('lesson-1')
    await flushPromises()

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/assets/asset-1/absorption',
      { target_scope_id: 'lesson-1', action: 'absorb' },
      expect.anything(),
    )
  })

  it('在独立报告中纠正文件类型并重新审计', async () => {
    httpMock.patch.mockResolvedValue({ data: { ...packageData.assets[0], document_type: 'lesson_plan' } })
    httpMock.post.mockImplementation((url: string) => {
      if (url.endsWith('/material-absorption/refresh')) return Promise.resolve({ data: { package: packageData } })
      return Promise.resolve({ data: { package: packageData } })
    })
    const wrapper = mountReport()
    await flushPromises()

    await wrapper.findAll('.report-table__row select')[0]!.setValue('lesson_plan')
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
