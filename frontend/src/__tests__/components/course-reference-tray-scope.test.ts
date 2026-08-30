import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseReferenceTray from '@/components/CourseReferenceTray.vue'
import http from '@/utils/http'

const assets = [
  {
    package_id: 'package-1', asset_id: 'asset-1', material_asset_id: 'mat-1',
    filename: '第一讲案例.docx', relative_path: '生成资料/第一讲案例.docx', size_bytes: 1200,
    role: 'reference', usages: [{ target_id: 'lesson-plan:L1-1', target_type: 'lesson_plan', role: 'primary' }],
  },
  {
    package_id: 'package-1', asset_id: 'asset-2', material_asset_id: 'mat-2',
    filename: '第二讲练习.pdf', relative_path: '生成资料/第二讲练习.pdf', size_bytes: 2400,
    role: 'reference', usages: [{ target_id: 'lesson-plan:L1-2', target_type: 'lesson_plan', role: 'reference' }],
  },
  {
    package_id: 'package-1', asset_id: 'asset-3', material_asset_id: 'mat-3',
    filename: '第二讲主教材.docx', relative_path: '生成资料/第二讲主教材.docx', size_bytes: 1800,
    role: 'reference', usages: [{ target_id: 'lesson-plan:L1-2', target_type: 'lesson_plan', role: 'primary' }],
  },
  {
    package_id: 'package-1', asset_id: 'asset-4', material_asset_id: 'mat-4',
    filename: '2025年期末真题.pdf', relative_path: '生成资料/2025年期末真题.pdf', size_bytes: 3600,
    role: 'reference', usages: [{ target_id: 'managed:question-bank', target_type: 'question_bank', role: 'reference' }],
  },
]

describe('CourseReferenceTray lesson scope', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockImplementation((url: string) => {
      if (url === '/api/materials') return Promise.resolve({ data: { assets } } as any)
      if (url.includes('/web-research')) return Promise.resolve({ data: { accepted_references: [] } } as any)
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [{ package_id: 'package-1' }] } as any)
      return Promise.resolve({ data: {} } as any)
    })
    vi.spyOn(http, 'put').mockResolvedValue({ data: { relationships: [] } } as any)
  })

  it('切换讲次时只恢复该讲已经绑定的资料', async () => {
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [], stage: 'lesson', lessonId: 'L1-1',
        scopeTargetId: 'lesson-plan:L1-1', scopeTargetType: 'lesson_plan',
        scopeTargetLabel: '第一讲',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray__header').text()).toBe('课程资料')
    expect(wrapper.find('.system-context').exists()).toBe(false)
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第一讲案例.docx')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('原始材料')
    expect(wrapper.get('.ppt-smart-source-list').text()).not.toContain('第二讲练习.pdf')

    await wrapper.setProps({
      lessonId: 'L1-2', scopeTargetId: 'lesson-plan:L1-2',
      scopeTargetLabel: '第二讲',
      previousScopeTargetId: 'lesson-plan:L1-1',
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray__header').text()).toBe('课程资料')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第二讲练习.pdf')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第二讲主教材.docx')

    await wrapper.get('.reuse-previous').trigger('click')
    await flushPromises()
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第二讲主教材.docx')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第一讲案例.docx')
    expect(wrapper.find('.reuse-previous').exists()).toBe(false)
    expect(http.put).toHaveBeenLastCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({
        target_id: 'lesson-plan:L1-2',
        sources: expect.arrayContaining([
          expect.objectContaining({ source_asset_id: 'asset-1', role: 'reference' }),
          expect.objectContaining({ source_asset_id: 'asset-2', role: 'reference' }),
          expect.objectContaining({ source_asset_id: 'asset-3', role: 'primary' }),
        ]),
      }),
      expect.any(Object),
    )

    while (wrapper.find('.ppt-smart-source-item button').exists()) {
      await wrapper.get('.ppt-smart-source-item button').trigger('click')
      await flushPromises()
    }
    expect(http.put).toHaveBeenLastCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({ target_id: 'lesson-plan:L1-2', target_type: 'lesson_plan', sources: [] }),
      expect.any(Object),
    )
  })

  it('首次打开讲稿时自动匹配同讲原教案，并把后续清空保存为人工决定', async () => {
    const importedAssets = [
      {
        package_id: 'package-1', asset_id: 'asset-plan-1', material_asset_id: 'mat-plan-1',
        filename: '第1讲教案.docx', relative_path: '辅助资料/第1讲教案.docx', size_bytes: 1800,
        document_type: 'lesson_plan', role: 'reference', usages: [],
      },
      {
        package_id: 'package-1', asset_id: 'asset-plan-2', material_asset_id: 'mat-plan-2',
        filename: '第2讲教案.docx', relative_path: '辅助资料/第2讲教案.docx', size_bytes: 1800,
        document_type: 'lesson_plan', role: 'reference', usages: [],
      },
    ]
    vi.mocked(http.get).mockImplementation((url: string) => {
      if (url === '/api/materials') return Promise.resolve({ data: { assets: importedAssets, configured_source_target_ids: [] } } as any)
      if (url.includes('/web-research')) return Promise.resolve({ data: { accepted_references: [] } } as any)
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [{ package_id: 'package-1' }] } as any)
      return Promise.resolve({ data: {} } as any)
    })
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [], stage: 'script', lessonId: 'L1-1',
        scopeTargetId: 'script:L1-1', scopeTargetType: 'script', scopeTargetLabel: '第一讲',
        scopeTargetPosition: 1,
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('第1讲教案.docx')
    expect(wrapper.get('.ppt-smart-source-list').text()).not.toContain('第2讲教案.docx')
    expect(http.put).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({
        target_id: 'script:L1-1',
        target_type: 'script',
        binding_mode: 'auto',
        sources: [{ source_asset_id: 'asset-plan-1', role: 'primary' }],
      }),
      expect.any(Object),
    )

    await wrapper.get('.ppt-smart-source-item button').trigger('click')
    await flushPromises()
    expect(http.put).toHaveBeenLastCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({ binding_mode: 'manual', sources: [] }),
      expect.any(Object),
    )
  })

  it('资料导入完成后立即刷新并自动匹配当前工作台', async () => {
    let currentAssets: any[] = []
    vi.mocked(http.get).mockImplementation((url: string) => {
      if (url === '/api/materials') return Promise.resolve({ data: { assets: currentAssets, configured_source_target_ids: [] } } as any)
      if (url.includes('/web-research')) return Promise.resolve({ data: { accepted_references: [] } } as any)
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [{ package_id: 'package-1' }] } as any)
      return Promise.resolve({ data: {} } as any)
    })
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [], stage: 'foundation', refreshToken: 0,
        scopeTargetId: 'managed:outline', scopeTargetType: 'outline', scopeTargetLabel: '课程大纲',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()
    expect(wrapper.get('.ppt-smart-empty').text()).toContain('尚未选择课程资料')

    currentAssets = [{
      package_id: 'package-1', asset_id: 'asset-outline', material_asset_id: 'mat-outline',
      filename: '课程大纲.md', relative_path: '辅助资料/其他资料/课程大纲.md', size_bytes: 1200,
      document_type: 'outline', role: 'reference', usages: [],
    }]
    await wrapper.setProps({ refreshToken: 1 })
    await flushPromises()

    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('课程大纲.md')
    expect(http.put).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({
        target_id: 'managed:outline',
        binding_mode: 'auto',
        sources: [{ source_asset_id: 'asset-outline', role: 'primary' }],
      }),
      expect.any(Object),
    )
  })

  it('题库常驻侧栏只保留真题资料并以专用角色保存', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({
      data: {
        asset_id: 'mat-5', filename: '2024年期中真题.pdf', size_bytes: 4200,
        course_space: { package_id: 'package-1', course_asset_id: 'asset-5', relative_path: '生成资料/2024年期中真题.pdf' },
      },
    } as any)
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [], stage: 'question-bank', variant: 'question-bank',
        scopeTargetId: 'managed:question-bank', scopeTargetType: 'question_bank', scopeTargetLabel: '课程题库',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray__header').text()).toContain('真题资料')
    expect(wrapper.get('.reference-tray__header').text()).toContain('1 份')
    expect(wrapper.get('.source-group--question-bank').text()).toContain('2025年期末真题.pdf')
    expect(wrapper.find('.system-context').exists()).toBe(false)
    expect(wrapper.find('.source-group--references').exists()).toBe(false)
    expect(wrapper.find('.source-group--web').exists()).toBe(false)
    expect(http.get).not.toHaveBeenCalledWith(expect.stringContaining('/web-research'), expect.anything())

    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['exam'], '2024年期中真题.pdf', { type: 'application/pdf' })],
    })
    await input.trigger('change')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/materials', expect.any(FormData), expect.any(Object))
    expect(http.put).toHaveBeenLastCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({
        target_id: 'managed:question-bank',
        target_type: 'question_bank',
        sources: expect.arrayContaining([
          expect.objectContaining({ source_asset_id: 'asset-4', role: 'question_source' }),
          expect.objectContaining({ source_asset_id: 'asset-5', role: 'question_source' }),
        ]),
      }),
      expect.any(Object),
    )
  })
})
