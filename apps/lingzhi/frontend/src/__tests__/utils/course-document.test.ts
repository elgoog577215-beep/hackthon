import { describe, expect, it } from 'vitest'
import { courseDocumentToNodes } from '../../utils/course-document'
import type { CourseDocument } from '../../stores/types'

const document: CourseDocument = {
  schema_version: 'course_document_v1',
  course_id: 'course-1',
  title: '线性代数',
  document_revision: 'cdr-1',
  sections: [
    {
      section_id: 'chapter-1', parent_section_id: null, title: '第一章', position: 0, level: 1,
      learning_objective: '', objective_id: '', objective_revision_id: '', attributes: {},
    },
    {
      section_id: 'objective-1', parent_section_id: 'chapter-1', title: '向量', position: 1, level: 2,
      learning_objective: '理解向量', objective_id: 'lo-1', objective_revision_id: 'lor-1',
      attributes: { difficulty_contract: { level: 'beginner' } },
    },
  ],
  blocks: [
    {
      block_id: 'block-2', section_id: 'objective-1', position: 1, kind: 'rich_text', role: 'example',
      payload: { title: '例子', markdown: '第二块' }, asset_refs: [], objective_refs: ['lo-1'],
      concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-2', status: 'final',
    },
    {
      block_id: 'block-1', section_id: 'objective-1', position: 0, kind: 'rich_text', role: 'concept',
      payload: { title: '定义', markdown: '第一块' }, asset_refs: [], objective_refs: ['lo-1'],
      concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-1', status: 'final',
    },
  ],
}

describe('courseDocumentToNodes', () => {
  it('只为现有界面投影节点，课程块仍保持正式顺序和修订', () => {
    const nodes = courseDocumentToNodes(document)
    const objective = nodes[1]

    expect(nodes.map(node => node.node_id)).toEqual(['chapter-1', 'objective-1'])
    expect(objective?.course_blocks?.map(block => block.block_id)).toEqual(['block-1', 'block-2'])
    expect(objective?.content_blocks?.map(block => block.block_revision_id)).toEqual(['cbr-1', 'cbr-2'])
    expect(objective?.node_content).toContain('## 定义')
    expect(objective?.difficulty_contract).toEqual({ level: 'beginner' })
  })
})
