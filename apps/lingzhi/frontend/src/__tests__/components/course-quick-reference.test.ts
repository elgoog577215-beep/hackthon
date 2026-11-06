import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseQuickReferencePanel from '@/components/CourseQuickReferencePanel.vue'
import type { CourseQuickReferenceItem } from '@/utils/course-quick-reference'
import { setLocale } from '@/shared/i18n'
import zh from '@/../public/locales/zh/translation.json'

const item: CourseQuickReferenceItem = {
  id: 'lesson-1:block-1:theorem-1',
  kind: 'theorem',
  title: '秩-零度定理',
  summary: '线性变换的维数关系。',
  expression: '\\dim V=\\dim\\ker T+\\dim\\operatorname{im}T',
  nodeId: 'lesson-1',
  nodeName: '第一讲 向量空间',
  blockId: 'block-1',
}

describe('course quick reference panel', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
    await setLocale('zh')
  })

  it('shows the indexed item and emits a one-way locate action', async () => {
    const wrapper = mount(CourseQuickReferencePanel, { props: { items: [item] } })
    expect(wrapper.text()).toContain('秩-零度定理')
    expect(wrapper.text()).toContain('第一讲 向量空间')
    await wrapper.get('.course-quick-reference__item').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('locate')?.[0]?.[0]).toEqual(item)
    wrapper.unmount()
  })
})
