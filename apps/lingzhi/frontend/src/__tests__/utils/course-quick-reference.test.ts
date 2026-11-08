import { describe, expect, it } from 'vitest'
import type { Node } from '@/stores/types'
import { collectCourseQuickReferences } from '@/utils/course-quick-reference'

describe('course quick reference index', () => {
  it('collects tagged items across lessons and keeps the source block anchor', () => {
    const nodes = [
      {
        node_id: 'lesson-1',
        node_name: '第一讲 向量空间',
        content_blocks: [],
        course_blocks: [
          {
            block_id: 'definition-1',
            kind: 'teaching',
            status: 'final',
            payload: {
              title: '向量空间',
              markdown: '向量空间是满足若干公理的集合。',
              knowledge_markers: [{ marker_id: 'marker-1', kind: 'definition', heading: '向量空间的定义' }],
            },
          },
          {
            block_id: 'formula-1',
            kind: 'formula',
            status: 'final',
            payload: { title: '秩-零度定理', formula: '\\dim V=\\dim\\ker T+\\dim\\operatorname{im}T' },
          },
          {
            block_id: 'draft-1',
            kind: 'teaching',
            status: 'draft',
            payload: { title: '未完成的定理', knowledge_markers: [{ kind: 'theorem', heading: '未完成的定理' }] },
          },
        ],
      },
      {
        node_id: 'lesson-2',
        node_name: '第二讲 线性变换',
        content_blocks: [{
          block_id: 'law-1',
          title: '线性变换基本定律',
          content: 'T(u+v)=T(u)+T(v)',
          status: 'final',
          metadata: { knowledge_markers: [{ marker_id: 'law-marker', kind: 'law', heading: '可加性' }] },
        }],
      },
    ] as unknown as Node[]

    const items = collectCourseQuickReferences(nodes)

    expect(items.map(item => item.kind)).toEqual(['definition', 'formula', 'law'])
    expect(items.map(item => item.nodeId)).toEqual(['lesson-1', 'lesson-1', 'lesson-2'])
    expect(items[1]).toMatchObject({
      kind: 'formula',
      title: '秩-零度定理',
      expression: '\\dim V=\\dim\\ker T+\\dim\\operatorname{im}T',
      blockId: 'formula-1',
    })
    expect(items.some(item => item.title === '未完成的定理')).toBe(false)
  })
})
