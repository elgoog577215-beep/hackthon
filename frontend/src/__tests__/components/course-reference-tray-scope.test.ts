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
        scopeTargetLabel: '第一讲', scopeTitle: '第 1 讲引用资料',
      },
      global: { stubs: { WebResearchDialog: true } },
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray>header').text()).toContain('第 1 讲引用资料')
    expect(wrapper.get('.drop-zone').text()).toContain('第一讲案例.docx')
    expect(wrapper.get('.reference-list').text()).not.toContain('第二讲练习.pdf')

    await wrapper.setProps({
      lessonId: 'L1-2', scopeTargetId: 'lesson-plan:L1-2',
      scopeTargetLabel: '第二讲', scopeTitle: '第 2 讲引用资料',
    })
    await flushPromises()

    expect(wrapper.get('.reference-tray>header').text()).toContain('第 2 讲引用资料')
    expect(wrapper.get('.reference-list').text()).toContain('第二讲练习.pdf')
    expect(wrapper.get('.drop-zone').text()).not.toContain('第一讲案例.docx')

    await wrapper.get('.reference-item button').trigger('click')
    await flushPromises()
    expect(http.put).toHaveBeenLastCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({ target_id: 'lesson-plan:L1-2', target_type: 'lesson_plan', sources: [] }),
      expect.any(Object),
    )
  })
})
