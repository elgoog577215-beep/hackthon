import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: httpMock,
  teacherRequestConfig: (config = {}) => config,
}))

import CoursePreparationDialog from '@/components/CoursePreparationDialog.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'

const pendingPackage = {
  package_id: 'package-1', course_id: 'course-1', course_name: '数据结构',
  academic_year: '2026-2027', term: '秋季', asset_count: 0, assets: [],
  preparation_status: 'pending',
}

describe('CoursePreparationDialog', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
      configurable: true,
      value() { this.setAttribute('open', '') },
    })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', {
      configurable: true,
      value() { this.removeAttribute('open') },
    })
    httpMock.get.mockReset().mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [pendingPackage] })
      return Promise.resolve({ data: pendingPackage })
    })
    httpMock.post.mockReset()
    httpMock.patch.mockReset()
    await setLocale('zh')
  })

  it('在工作台上提供从零开始和基于已有资料两个备课起点', async () => {
    httpMock.patch.mockResolvedValue({ data: { ...pendingPackage, preparation_status: 'skipped' } })
    const wrapper = mount(CoursePreparationDialog, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    expect(wrapper.get('.preparation-choice').text()).toContain('选择备课起点')
    expect(wrapper.get('.preparation-choice').text()).toContain('从零开始')
    expect(wrapper.get('.preparation-choice').text()).toContain('基于已有资料')

    await wrapper.findAll('.start-options button')[0]!.trigger('click')
    await flushPromises()

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/preparation',
      { status: 'skipped' },
      expect.anything(),
    )
    expect(wrapper.emitted('completed')).toHaveLength(1)
  })

  it('批量导入并完成分析后直接进入带嵌入式审计的工作台', async () => {
    const reviewPackage = {
      ...pendingPackage,
      asset_count: 2,
      preparation_status: 'review',
      material_understanding: {
        status: 'ai_completed',
        missing_document_types: ['outline', 'script', 'question_bank'],
        low_confidence_asset_ids: [],
      },
      assets: [
        { asset_id: 'asset-1', filename: '第一讲教案.md', relative_path: '辅助资料/其他资料/第一讲教案.md', document_type: 'lesson_plan', classification_source: 'ai', classification_confidence: 0.93, document_type_reason: '正文包含教学目标和课堂流程', structure_matches: [{ node_id: 'lesson-1', title: '第一讲 线性表', reason: '内容对应第一讲' }], version_role: 'current', version_reason: '当前使用版本', related_asset_ids: ['asset-2'] },
        { asset_id: 'asset-2', filename: '第一讲课件.pptx', relative_path: '辅助资料/其他资料/第一讲课件.pptx', document_type: 'ppt', classification_source: 'hybrid', classification_confidence: 0.99, document_type_reason: 'PowerPoint 格式', structure_matches: [{ node_id: 'lesson-1', title: '第一讲 线性表', reason: '内容对应第一讲' }], version_role: 'current', version_reason: '当前使用版本', related_asset_ids: ['asset-1'] },
      ],
    }
    httpMock.post.mockResolvedValue({
      data: {
        outcomes: [
          { relative_path: reviewPackage.assets[0]!.relative_path, outcome: 'imported' },
          { relative_path: reviewPackage.assets[1]!.relative_path, outcome: 'imported' },
        ],
        package: reviewPackage,
      },
    })
    httpMock.patch.mockImplementation((url: string, body: any) => {
      if (url.includes('/assets/asset-1')) return Promise.resolve({ data: { ...reviewPackage.assets[0], document_type: body.document_type } })
      return Promise.resolve({ data: { ...reviewPackage, preparation_status: body.status } })
    })
    const wrapper = mount(CoursePreparationDialog, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    await wrapper.findAll('.start-options button')[1]!.trigger('click')
    const input = wrapper.get('input[type="file"][multiple]:not([webkitdirectory])')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [
        new File(['教案'], '第一讲教案.md', { type: 'text/markdown' }),
        new File(['课件'], '第一讲课件.pptx', { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }),
      ],
    })
    await input.trigger('change')
    await flushPromises()

    const [url, form] = httpMock.post.mock.calls[0]!
    expect(url).toBe('/api/teacher-course-spaces/package-1/imports')
    expect((form as FormData).getAll('files')).toHaveLength(2)

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/preparation',
      { status: 'completed' },
      expect.anything(),
    )
    expect(wrapper.emitted('completed')).toHaveLength(1)
    expect(wrapper.find('.preparation-review').exists()).toBe(false)
  })
})
