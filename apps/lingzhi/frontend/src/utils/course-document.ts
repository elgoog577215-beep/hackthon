import type {
  ContentBlock,
  CourseDocument,
  CourseDocumentBlock,
  CourseDocumentSection,
  Node,
} from '../stores/types'

const legacyType = (role: string): ContentBlock['type'] => {
  if (role === 'orientation') return 'intro'
  if (role === 'checkpoint') return 'exercise'
  if (['prerequisite', 'objective', 'concept', 'reasoning', 'example', 'counterexample', 'application', 'activity', 'feedback', 'misconception', 'remediation', 'summary', 'transfer'].includes(role)) {
    return role as ContentBlock['type']
  }
  return 'custom'
}

const blockContent = (block: CourseDocumentBlock) => String(
  block.payload.markdown || block.payload.text || '',
)

const blockTitle = (block: CourseDocumentBlock) => String(block.payload.title || '')

const legacyBlock = (block: CourseDocumentBlock): ContentBlock => ({
  block_id: block.block_id,
  parent_block_id: block.parent_group_id,
  type: legacyType(block.role),
  title: blockTitle(block),
  content: blockContent(block),
  summary: String(block.payload.summary || ''),
  order: block.position,
  status: block.status === 'draft' ? 'draft' : 'final',
  metadata: {
    kind: block.kind,
    role: block.role,
    asset_refs: block.asset_refs,
    objective_refs: block.objective_refs,
  },
  block_revision_id: block.internal_revision,
})

const sectionMarkdown = (blocks: CourseDocumentBlock[]) => blocks
  .filter(block => block.status !== 'retired')
  .sort((left, right) => left.position - right.position)
  .map(block => {
    const title = blockTitle(block)
    const content = blockContent(block)
    return title ? `## ${title}\n\n${content}`.trim() : content
  })
  .filter(Boolean)
  .join('\n\n')

const sectionNode = (section: CourseDocumentSection, blocks: CourseDocumentBlock[]): Node => {
  const activeBlocks = blocks
    .filter(block => block.section_id === section.section_id && block.status !== 'retired')
    .sort((left, right) => left.position - right.position)
  const attributes = section.attributes || {}
  const content = sectionMarkdown(activeBlocks)
  return {
    ...(attributes as Partial<Node>),
    node_id: section.section_id,
    parent_node_id: section.parent_section_id || 'root',
    node_name: section.title,
    node_level: section.level,
    node_content: content,
    content_blocks: activeBlocks.map(legacyBlock),
    course_blocks: activeBlocks,
    learning_objective: section.learning_objective,
    objective_id: section.objective_id,
    objective_revision_id: section.objective_revision_id,
    node_type: (attributes.node_type as Node['node_type']) || 'original',
    generation_status: (attributes.generation_status as Node['generation_status']) || 'completed',
    generated_chars: Number(attributes.generated_chars ?? content.length),
  }
}

export const courseDocumentToNodes = (document: CourseDocument): Node[] => document.sections
  .slice()
  .sort((left, right) => left.position - right.position)
  .map(section => sectionNode(section, document.blocks))
