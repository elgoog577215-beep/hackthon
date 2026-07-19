import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import CourseNavigatorNode from '@/components/CourseNavigatorNode.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import type { CourseDocumentBlock, Node } from '@/stores/types'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const block = (
  blockId: string,
  position: number,
  role: CourseDocumentBlock['role'],
  title: string,
): CourseDocumentBlock => ({
  block_id: blockId,
  section_id: 'section-1',
  parent_group_id: null,
  position,
  kind: 'rich_text',
  role,
  payload: { title, markdown: `${title}正文` },
  asset_refs: [],
  objective_refs: [],
  concept_refs: [],
  evidence_refs: [],
  visibility_rule: {},
  internal_revision: `${blockId}-rev`,
  status: 'final',
})

const section: Node = {
  node_id: 'section-1',
  node_name: '1.1 向量与线性组合',
  node_level: 2,
  parent_node_id: 'chapter-1',
  node_content: '正文',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 2,
  children: [],
  course_blocks: [
    block('block-concept', 1, 'concept', '正式定义'),
    block('block-example', 2, 'example', '例题推演'),
    block('block-reasoning', 3, 'reasoning', '证明与推导'),
  ],
}

describe('CourseNavigatorNode 课程块目录', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
    setActivePinia(createPinia())
    useCourseStore().currentCourseProjection = 'published'
  })

  afterEach(async () => {
    await setLocale('zh')
    vi.unstubAllGlobals()
  })

  it('只为当前小节展开有序课程块并标记当前位置', () => {
    const wrapper = mount(CourseNavigatorNode, {
      props: {
        node: section,
        activeId: section.node_id,
        activeBlockId: 'block-example',
        depth: 1,
      },
    })

    expect(wrapper.get('.node-button').attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('.course-block-link')).toHaveLength(3)
    expect(wrapper.text()).toContain('概念')
    expect(wrapper.text()).toContain('正式定义')
    expect(wrapper.text()).toContain('例子')
    expect(wrapper.text()).toContain('例题推演')
    expect(wrapper.get('.course-block-link.active').attributes('aria-current')).toBe('location')
  })

  it('允许当前小节收起课程块目录', async () => {
    const wrapper = mount(CourseNavigatorNode, {
      props: { node: section, activeId: section.node_id, depth: 1 },
    })

    await wrapper.get('.node-button').trigger('click')

    expect(wrapper.get('.node-button').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.course-block-outline').exists()).toBe(false)
  })

  it('非当前小节默认收起，搜索时只展示匹配课程块', () => {
    const wrapper = mount(CourseNavigatorNode, {
      props: { node: section, activeId: 'section-2', query: '推导', depth: 1 },
    })

    const links = wrapper.findAll('.course-block-link')
    expect(links).toHaveLength(1)
    expect(links[0]!.text()).toContain('证明与推导')
    expect(links[0]!.text()).not.toContain('例题推演')
  })

  it('展开非当前小节时先切换小节，避免普通状态同时铺开多组课程块', async () => {
    const wrapper = mount(CourseNavigatorNode, {
      props: { node: section, activeId: 'section-2', depth: 1 },
    })

    await wrapper.get('.node-button > svg').trigger('click')

    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(section)
    expect(wrapper.find('.course-block-outline').exists()).toBe(false)
  })

  it('点击课程块时携带小节和稳定块 ID', async () => {
    const wrapper = mount(CourseNavigatorNode, {
      props: { node: section, activeId: section.node_id, depth: 1 },
    })

    const links = wrapper.findAll('.course-block-link')
    await links[1]!.trigger('click')

    expect(wrapper.emitted('selectBlock')?.[0]?.[0]).toEqual({
      node: section,
      blockId: 'block-example',
    })
  })

  it('英文模式使用完整英文标签且不泄露中文或翻译 key', async () => {
    await setLocale('en')
    const wrapper = mount(CourseNavigatorNode, {
      props: { node: section, activeId: section.node_id, depth: 1 },
    })

    expect(wrapper.get('.course-block-outline').attributes('aria-label')).toBe('Lesson blocks')
    expect(wrapper.text()).toContain('Concept')
    expect(wrapper.text()).toContain('Example')
    expect(wrapper.text()).toContain('Reasoning')
    expect(wrapper.text()).not.toContain('概念')
    expect(wrapper.text()).not.toContain('courseBlocks.')
    expect(wrapper.text()).not.toContain('learningNavigator.')
  })
})
