import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CourseBlockStream from '@/components/CourseBlockStream.vue'
import type { Node as CourseNode, Note } from '@/stores/types'

const baseNode: CourseNode = {
  node_id: 'node-1',
  parent_node_id: 'root',
  node_name: '向量空间',
  node_level: 2,
  node_content: '旧版完整 Markdown',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}

const global = {
  stubs: {
    MarkdownRenderer: {
      props: ['content'],
      template: '<div class="markdown-renderer">{{ content }}</div>',
    },
    FeedbackReviewBlock: {
      name: 'FeedbackReviewBlock',
      props: ['content', 'structure', 'searchWords'],
      template: '<div class="feedback-review-stub">{{ content }}</div>',
    },
    MarkdownDocumentEditor: {
      props: ['content'],
      template: '<div class="legacy-markdown">{{ content }}</div>',
    },
    InlineCourseBlockAI: {
      name: 'InlineCourseBlockAI',
      props: ['node', 'block', 'active'],
      emits: ['activate'],
      template: '<div><button class="inline-block-ai-stub" :data-block-id="block.block_id" @click="$emit(\'activate\', block.block_id)">AI</button></div>',
    },
  },
}

describe('CourseBlockStream', () => {
  it('优先渲染正式课程文档块，而不是旧内容块副本', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'legacy', block_revision_id: 'old', type: 'concept', title: '旧块', content: '不应显示', order: 0 },
      ],
      course_blocks: [
        {
          block_id: 'canonical', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'reasoning',
          payload: { title: '推导', markdown: '正式课程文档内容' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-new', status: 'final',
        },
      ],
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })

    expect(wrapper.get('.course-content-block').attributes('data-content-block-id')).toBe('canonical')
    expect(wrapper.get('.markdown-renderer').text()).toBe('正式课程文档内容')
    expect(wrapper.text()).not.toContain('不应显示')
  })

  it('显示正式教学角色，并隐藏没有正文的最终空块', () => {
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [
        {
          block_id: 'empty', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'orientation',
          payload: { title: '向量空间', markdown: '' }, asset_refs: [], objective_refs: [], concept_refs: [],
          evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-empty', status: 'final',
        },
        {
          block_id: 'objective', section_id: 'node-1', position: 1, kind: 'rich_text', role: 'objective',
          payload: { title: '本节任务', markdown: '建立可验证的学习目标。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-objective', status: 'final',
        },
        {
          block_id: 'activity', section_id: 'node-1', position: 2, kind: 'rich_text', role: 'activity',
          payload: { title: '学习者行动', markdown: '请独立完成任务。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-activity', status: 'final',
        },
      ],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })

    expect(wrapper.findAll('.course-content-block')).toHaveLength(2)
    expect(wrapper.text()).toContain('任务')
    expect(wrapper.text()).toContain('行动')
    expect(wrapper.text()).not.toContain('向量空间')
  })

  it('把正式反馈块交给核对视图，并透传后端编译结构', () => {
    const feedbackStructure = {
      schema_version: 'course_feedback_v1',
      mode: 'static_reference',
      sections: [{ section_id: 'task-1', title: '任务 1', markdown: '参考结论', collapsed_by_default: true }],
    }
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [
        {
          block_id: 'feedback', section_id: 'node-1', position: 0, kind: 'review_checkpoint', role: 'feedback',
          payload: { title: '检查与反馈', markdown: '参考正文', feedback_structure: feedbackStructure },
          asset_refs: [], objective_refs: [], concept_refs: [], evidence_refs: [], visibility_rule: {},
          internal_revision: 'cbr-feedback', status: 'final',
        },
      ],
    }

    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, searchWords: ['结论'] },
      global,
    })
    const review = wrapper.findComponent({ name: 'FeedbackReviewBlock' })

    expect(wrapper.get('.course-content-block').attributes('data-content-block-kind')).toBe('review_checkpoint')
    expect(review.props('content')).toBe('参考正文')
    expect(review.props('structure')).toEqual(feedbackStructure)
    expect(review.props('searchWords')).toEqual(['结论'])
    expect(wrapper.find('.markdown-renderer').exists()).toBe(false)
  })

  it('为课程块提供原位 AI 协作入口并带出稳定块引用', async () => {
    const block = {
      block_id: 'canonical', section_id: 'node-1', position: 0, kind: 'rich_text' as const, role: 'concept' as const,
      payload: { title: '向量定义', markdown: '向量具有大小和方向。' }, asset_refs: [], objective_refs: ['lo-1'],
      concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-current', status: 'final' as const,
    }
    const node: CourseNode = { ...baseNode, course_blocks: [block] }
    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, canImproveBlocks: true },
      global,
    })

    const entry = wrapper.get('.inline-block-ai-stub')
    expect(entry.attributes('data-block-id')).toBe('canonical')
    await entry.trigger('click')

    expect(wrapper.findComponent({ name: 'InlineCourseBlockAI' }).props('active')).toBe(true)

    expect(wrapper.findAll('.block-ai-menu button')).toHaveLength(0)
    await wrapper.get('.block-formal-improvement').trigger('click')
    expect(wrapper.emitted('improveBlock')).toEqual([[
      expect.objectContaining({ nodeId: 'node-1', block: expect.objectContaining({ block_id: 'canonical' }) }),
    ]])
  })

  it('旧结构化课程块也保留原位 AI 协作能力，但不冒充正式课程改写', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [{ block_id: 'legacy', block_revision_id: 'old', type: 'concept', title: '旧块', content: '旧内容', order: 0 }],
    }
    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, canImproveBlocks: true },
      global,
    })

    expect(wrapper.find('.inline-block-ai-stub').exists()).toBe(true)
    expect(wrapper.find('.block-formal-improvement').exists()).toBe(false)
  })

  it('按正式顺序渲染结构化课程块和稳定锚点', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'b2', block_revision_id: 'r2', type: 'example', title: '例子', content: '第二块', order: 2 },
        { block_id: 'b1', block_revision_id: 'r1', type: 'concept', title: '定义', content: '第一块', order: 1 },
      ],
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })
    const blocks = wrapper.findAll('.course-content-block')

    expect(blocks).toHaveLength(2)
    expect(blocks[0]?.attributes('data-content-block-id')).toBe('b1')
    expect(blocks[0]?.attributes('data-content-block-revision-id')).toBe('r1')
    expect(blocks.map(block => block.find('.markdown-renderer').text())).toEqual(['第一块', '第二块'])
  })

  it('旧课程没有结构化块时无损回退到完整 Markdown', () => {
    const wrapper = mount(CourseBlockStream, { props: { node: baseNode, content: baseNode.node_content }, global })

    expect(wrapper.find('.legacy-markdown').text()).toBe('旧版完整 Markdown')
    expect(wrapper.find('.course-content-block').exists()).toBe(false)
  })

  it('把同一真源的学习记录投影到所属内容块之后', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'b1', block_revision_id: 'r1', type: 'concept', title: '定义', content: '向量空间的定义', order: 1 },
        { block_id: 'b2', block_revision_id: 'r2', type: 'example', title: '例子', content: '一个具体例子', order: 2 },
      ],
    }
    const record: Note = {
      id: 'note-1', nodeId: 'node-1', highlightId: 'hl-1', quote: '向量空间', content: '这里要区分集合和运算。',
      color: 'amber', createdAt: Date.now(), sourceType: 'user', recordType: 'note', status: 'active',
      anchor: { block_id: 'b1', block_revision_id: 'r1' }, migrationStatus: 'current', syncState: 'saved',
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content, records: [record] }, global })
    const children = wrapper.get('.course-block-stream').element.children

    expect(children[0]?.getAttribute('data-content-block-id')).toBe('b1')
    expect(children[1]?.classList.contains('inline-learning-record')).toBe(true)
    expect(children[1]?.textContent).toContain('这里要区分集合和运算。')
    expect(children[2]?.getAttribute('data-content-block-id')).toBe('b2')
  })
})
