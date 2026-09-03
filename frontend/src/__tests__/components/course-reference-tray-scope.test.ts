import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseReferenceTray, { type CourseReferenceItem } from '@/components/CourseReferenceTray.vue'
import http from '@/utils/http'

const assets: CourseReferenceItem[] = [
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

    expect(wrapper.find('.reference-tray__header').exists()).toBe(false)
    expect(wrapper.find('.system-context').exists()).toBe(true)
    expect(wrapper.get('.drop-zone').text()).toContain('第一讲案例.docx')
    expect(wrapper.get('.source-group--references').text()).not.toContain('第二讲练习.pdf')

    await wrapper.setProps({
      lessonId: 'L1-2', scopeTargetId: 'lesson-plan:L1-2',
      scopeTargetLabel: '第二讲',
      previousScopeTargetId: 'lesson-plan:L1-1',
    })
    await flushPromises()

    expect(wrapper.find('.reference-tray__header').exists()).toBe(false)
    expect(wrapper.get('.source-group--references').text()).toContain('第二讲练习.pdf')
    expect(wrapper.get('.drop-zone').text()).toContain('第二讲主教材.docx')

    await wrapper.get('.reuse-previous').trigger('click')
    await flushPromises()
    expect(wrapper.get('.drop-zone').text()).toContain('第二讲主教材.docx')
    expect(wrapper.get('.source-group--references').text()).toContain('第一讲案例.docx')
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

    if (wrapper.find('.drop-zone.has-file > button').exists()) {
      await wrapper.get('.drop-zone.has-file > button').trigger('click')
      await flushPromises()
    }
    while (wrapper.find('.reference-item > button').exists()) {
      await wrapper.get('.reference-item > button').trigger('click')
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

    expect(wrapper.get('.drop-zone').text()).toContain('第1讲教案.docx')
    expect(wrapper.get('.source-group--references').text()).not.toContain('第2讲教案.docx')
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

    await wrapper.get('.drop-zone.has-file > button').trigger('click')
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
    expect(wrapper.find('.reference-tray__header').exists()).toBe(false)
    expect(wrapper.find('.source-status--collecting').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('先准备本阶段资料')
    expect(wrapper.get('.empty-drop').text()).toContain('上传资料文件')
    expect(wrapper.get('.reference-add').text()).toContain('上传参考文件')

    currentAssets = [{
      package_id: 'package-1', asset_id: 'asset-outline', material_asset_id: 'mat-outline',
      filename: '课程大纲.md', relative_path: '辅助资料/其他资料/课程大纲.md', size_bytes: 1200,
      document_type: 'outline', role: 'reference', usages: [],
    }]
    await wrapper.setProps({ refreshToken: 1 })
    await flushPromises()

    expect(wrapper.get('.drop-zone').text()).toContain('课程大纲.md')
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

  it('生成开始后把上传命令切换为资料使用状态，并支持暂停、继续和取消', async () => {
    const selected = [
      { ...assets[2]!, role: 'primary' as const },
      { ...assets[1]!, role: 'reference' as const },
    ]
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: selected, stage: 'lesson',
        workflowState: 'generating', workflowProgress: 42,
        workflowCanPause: true, workflowCanCancel: true,
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.find('.system-context').exists()).toBe(true)
    expect(wrapper.get('.workflow-state--generating').text()).toContain('第二讲主教材.docx')
    expect(wrapper.get('.workflow-state--generating').text()).toContain('第二讲练习.pdf')
    expect(wrapper.get('.workflow-state--generating').text()).toContain('使用中')
    expect(wrapper.get('.workflow-progress i').attributes('style')).toContain('scaleX(0.42)')
    expect(wrapper.find('.empty-drop').exists()).toBe(false)
    expect(wrapper.find('.reference-add').exists()).toBe(false)

    const generatingButtons = wrapper.findAll('.workflow-state footer button')
    await generatingButtons[0]!.trigger('click')
    await generatingButtons[1]!.trigger('click')
    expect(wrapper.emitted('pause-workflow')).toHaveLength(1)
    expect(wrapper.emitted('cancel-workflow')).toHaveLength(1)

    await wrapper.setProps({ workflowState: 'paused', workflowCanPause: false, workflowCanResume: true })
    await flushPromises()
    expect(wrapper.get('.workflow-state--paused').text()).toContain('已保留')
    expect(wrapper.find('.reference-add').exists()).toBe(false)
    await wrapper.get('.workflow-resume').trigger('click')
    expect(wrapper.emitted('resume-workflow')).toHaveLength(1)

    await wrapper.setProps({ workflowState: 'ready', workflowCanResume: false, workflowCanCancel: false })
    await flushPromises()
    expect(wrapper.get('.source-group--primary').text()).toContain('资料文件')
    expect(wrapper.get('.source-group--references').text()).toContain('参考文件')
  })

  it('生成失败后保留课程信息与资料，并提供同一任务重试入口', async () => {
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [{ ...assets[2]!, role: 'primary' }], stage: 'lesson',
        workflowState: 'failed', workflowDetail: '模型返回结构不完整', workflowCanRetry: true,
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.find('.system-context').exists()).toBe(true)
    expect(wrapper.get('.source-status--failed').text()).toContain('模型返回结构不完整')
    expect(wrapper.get('.source-group--primary').text()).toContain('第二讲主教材.docx')
    await wrapper.get('.source-status__retry').trigger('click')
    expect(wrapper.emitted('retry-workflow')).toHaveLength(1)
  })

  it('内容确认后收起上传入口，只在老师主动调整时展开', async () => {
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [{ ...assets[2]!, role: 'primary' }], stage: 'lesson',
        workflowState: 'confirmed',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.find('.system-context').exists()).toBe(true)
    expect(wrapper.get('.source-status--confirmed').text()).toContain('当前内容已确认')
    expect(wrapper.get('.confirmed-source-summary').text()).toContain('本讲教案使用的资料')
    expect(wrapper.get('.confirmed-source-summary').text()).toContain('第二讲主教材.docx')
    expect(wrapper.find('.empty-drop').exists()).toBe(false)
    expect(wrapper.find('.reference-add').exists()).toBe(false)
    expect(wrapper.find('.web-research-open').exists()).toBe(false)

    await wrapper.get('.confirmed-source-adjust').trigger('click')
    expect(wrapper.get('.source-status--confirmed').text()).toContain('正在调整资料')
    expect(wrapper.find('.confirmed-source-summary').exists()).toBe(false)
    expect(wrapper.find('.empty-drop').exists()).toBe(false)
    expect(wrapper.get('.source-group--primary').text()).toContain('第二讲主教材.docx')
    expect(wrapper.get('.reference-add').text()).toContain('上传参考文件')

    await wrapper.get('.source-status__collapse').trigger('click')
    expect(wrapper.find('.confirmed-source-summary').exists()).toBe(true)
    expect(wrapper.find('.reference-add').exists()).toBe(false)
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
