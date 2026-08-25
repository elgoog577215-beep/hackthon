import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseReferenceTray from '@/components/CourseReferenceTray.vue'
import http from '@/utils/http'

const assets = [{
  package_id: 'package-1', asset_id: 'asset-1', material_asset_id: 'mat-1',
  filename: '课堂案例.pdf', relative_path: '资料库/课堂案例.pdf', size_bytes: 2048,
  role: 'reference', usages: [{ target_id: 'ppt-v6:L1-1', target_type: 'ppt', role: 'primary' }],
}]

describe('PPT smart reference tray', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockImplementation((url: string) => {
      if (url === '/api/materials') return Promise.resolve({ data: { assets } } as any)
      if (url.includes('/web-research')) return Promise.resolve({ data: { accepted_references: [] } } as any)
      return Promise.resolve({ data: {} } as any)
    })
    vi.spyOn(http, 'put').mockResolvedValue({ data: { relationships: [] } } as any)
  })

  it('在右侧集中显示 AI 将使用的资料，而不是平铺上传分组', async () => {
    const wrapper = mount(CourseReferenceTray, {
      props: {
        courseId: 'course-1', modelValue: [], stage: 'ppt', lessonId: 'L1-1',
        scopeTargetId: 'ppt-v6:L1-1', scopeTargetType: 'ppt', scopeTargetLabel: '第一讲 PPT',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray__header').text()).toContain('PPT 智能资料')
    expect(wrapper.get('.system-context').text()).toContain('AI 自动读取')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('课堂案例.pdf')
    expect(wrapper.get('.ppt-smart-source-list').text()).toContain('主参考')
    expect(wrapper.find('.drop-zone').exists()).toBe(false)
    expect(wrapper.find('.source-group--references').exists()).toBe(false)
    expect(wrapper.get('.ppt-smart-actions').text()).toContain('添加资料')
    expect(wrapper.get('.ppt-smart-actions').text()).toContain('联网查找')
  })
})
