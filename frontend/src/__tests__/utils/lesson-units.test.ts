import { describe, expect, it } from 'vitest'
import type { Node } from '../../stores/types'
import {
  lessonUnitHasContent,
  lessonUnitMembers,
  projectLessonUnits,
  resolveLessonUnit,
} from '../../utils/lesson-units'

function node(id: string, parent: string, level: number, name: string, content = ''): Node {
  return {
    node_id: id,
    parent_node_id: parent,
    node_name: name,
    node_level: level,
    node_content: content,
    node_type: 'original',
    generation_status: content ? 'completed' : 'pending',
    generated_chars: content.length,
  }
}

describe('lesson unit projection', () => {
  const nodes = [
    node('lesson-1', 'root', 1, '第一讲'),
    node('knowledge-1', 'lesson-1', 2, '知识点一', '内容一'),
    node('knowledge-2', 'lesson-1', 2, '知识点二'),
    node('lesson-2', 'root', 1, '第二讲'),
    node('knowledge-3', 'lesson-2', 2, '知识点三', '内容三'),
  ]

  it('projects chapters as lectures instead of leaf content nodes', () => {
    expect(projectLessonUnits(nodes).map(item => item.node_id)).toEqual(['lesson-1', 'lesson-2'])
  })

  it('keeps all knowledge nodes inside their lecture', () => {
    expect(lessonUnitMembers(nodes, 'lesson-1').map(item => item.node_id)).toEqual(['knowledge-1', 'knowledge-2'])
    expect(resolveLessonUnit(nodes, 'knowledge-2')?.node_id).toBe('lesson-1')
  })

  it('derives lecture readiness from descendant content', () => {
    expect(lessonUnitHasContent(nodes, nodes[0]!)).toBe(true)
    expect(lessonUnitHasContent(nodes, node('lesson-3', 'root', 1, '第三讲'))).toBe(false)
  })
})
