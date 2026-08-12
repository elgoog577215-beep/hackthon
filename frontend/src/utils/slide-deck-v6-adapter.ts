import adapterContract from '../data/slide-deck-v6-layout-adapters.json'


interface V6Region {
  region_id: string
  slot_id: string
  content_kind: string
  content: string
  source_block_ids?: string[]
  source_section_ids?: string[]
  source_asset_refs?: string[]
}

interface V6NoteBlock {
  block_id: string
  block_revision: string
  full_text: string
  source_kind?: string
  source_payload?: Record<string, any>
  asset_refs?: string[]
}

interface V6Page {
  page_id: string
  page_ordinal: number
  title: string
  title_max_lines?: number
  resolved_layout: string
  source_block_ids: string[]
  source_section_ids?: string[]
  continuation_of_page_id?: string
  continuation_index?: number
  continuation_count?: number
  regions: V6Region[]
  visual_decision?: {
    decision?: string
    source_asset_ids?: string[]
    visual_payload?: Record<string, any>
  }
  speaker_notes: {
    source_document_revision: string
    teaching_unit_id: string
    source_blocks: V6NoteBlock[]
    source_section_ids?: string[]
  }
}

interface V6DeckLike {
  schema_version?: string
  pages?: V6Page[]
  template_theme_overrides?: Record<string, string>
}

interface AdapterDefinition {
  renderer_layout: string
  basic_layout: string
  variant_policy?: {
    artifact_content_kind: string
    split_variant: string
    full_variant: string
    continuation_variant: string
    detail_variant?: string
    wide_min_columns?: string
    wide_variant?: string
    wide_support_mode?: string
  }
}

const layouts = adapterContract.layouts as Record<string, AdapterDefinition>

function layoutSlug(layoutId: string): string {
  const slug = String(layoutId || '').split('/').at(-1) || ''
  if (!layouts[slug]) throw new Error(`v6_template_layout_adapter_missing:${layoutId}`)
  return slug
}

function notesText(page: V6Page): string {
  return [
    `source_document_revision: ${page.speaker_notes.source_document_revision}`,
    `teaching_unit_id: ${page.speaker_notes.teaching_unit_id}`,
    `source_section_ids: ${JSON.stringify(page.speaker_notes.source_section_ids || [])}`,
    ...page.speaker_notes.source_blocks.map(block => (
      [
        `[${block.block_id} @ ${block.block_revision}]`,
        `source_kind: ${block.source_kind || 'rich_text'}`,
        `asset_refs: ${JSON.stringify(block.asset_refs || [])}`,
        block.full_text,
        `source_payload: ${JSON.stringify(block.source_payload || {})}`,
      ].join('\n')
    )),
  ].join('\n\n')
}

function parseMarkdownTable(value: string): { headers: string[]; rows: string[][] } {
  const rows = String(value || '')
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.startsWith('|') && line.endsWith('|'))
    .filter(line => !(line.includes('-') && /^[|:\-\s]+$/.test(line)))
    .map(line => line.slice(1, -1)
      .split(/(?<!\\)\|/)
      .map(cell => cell.replace(/\\\|/g, '|').trim()))
  return { headers: rows[0] || [], rows: rows.slice(1) }
}

function tableRowRequiresDetail(value: string): boolean {
  const table = parseMarkdownTable(value)
  if (table.rows.length !== 1) return false
  const cells = table.rows[0] || []
  const columnCount = Math.max(1, table.headers.length, cells.length)
  const safeColumnChars = Math.max(8, Math.round(108 / columnCount))
  return Math.max(0, ...cells.map(cell => cell.length)) > safeColumnChars
}

function layoutVariant(page: V6Page, adapter: AdapterDefinition) {
  const policy = adapter.variant_policy
  if (!policy?.artifact_content_kind) return { variant: '', supportMode: '' }
  const hasArtifact = page.regions.some(
    region => region.content_kind === policy.artifact_content_kind,
  )
  const hasSupport = page.regions.some(
    region => region.content_kind !== policy.artifact_content_kind,
  )
  const artifactRegion = page.regions.find(
    region => region.content_kind === policy.artifact_content_kind,
  )
  if (
    policy.artifact_content_kind === 'table'
    && artifactRegion
    && policy.detail_variant
    && (
      Number(page.continuation_index || 1) > 1
      || (!hasSupport && tableRowRequiresDetail(artifactRegion.content))
    )
  ) {
    return { variant: policy.detail_variant, supportMode: 'full' }
  }
  if (Number(page.continuation_index || 1) > 1) {
    return { variant: policy.continuation_variant, supportMode: 'full' }
  }
  const wideMinimum = Number(policy.wide_min_columns || 0)
  if (
    hasArtifact
    && hasSupport
    && policy.artifact_content_kind === 'table'
    && artifactRegion
    && wideMinimum > 0
    && parseMarkdownTable(artifactRegion.content).headers.length >= wideMinimum
  ) {
    return {
      variant: policy.wide_variant || policy.split_variant,
      supportMode: policy.wide_support_mode || 'band',
    }
  }
  return hasArtifact && hasSupport
    ? { variant: policy.split_variant, supportMode: 'split' }
    : { variant: policy.full_variant, supportMode: 'full' }
}

function regionBlock(region: V6Region): Record<string, unknown> {
  const items = ['items', 'steps'].includes(region.content_kind)
    ? region.content.split('\n').map(item => item.trim()).filter(Boolean)
    : []
  return {
    block_id: region.region_id,
    type: region.content_kind === 'code'
      ? 'code'
      : region.content_kind === 'steps'
        ? 'process'
      : region.content_kind === 'items'
        ? 'bullets'
        : 'statement',
    title: region.slot_id.replace(/_/g, ' '),
    content: items.length ? '' : region.content,
    items,
    metadata: {
      v6_slot_id: region.slot_id,
      v6_region_id: region.region_id,
      source_block_ids: region.source_block_ids || [],
      source_section_ids: region.source_section_ids || [],
      source_asset_refs: region.source_asset_refs || [],
      formula: region.content_kind === 'formula',
      table_source: region.content_kind === 'table',
    },
  }
}

function pageVisuals(page: V6Page): Array<Record<string, unknown>> {
  const formula = page.regions.find(region => region.content_kind === 'formula')
  if (formula) return [{
    kind: 'formula',
    caption: formula.slot_id,
    parameters: { formula: formula.content },
  }]
  const table = page.regions.find(region => region.content_kind === 'table')
  if (table) {
    const parameters = parseMarkdownTable(table.content)
    return [{ kind: 'table', caption: table.slot_id, parameters }]
  }
  if (String(page.visual_decision?.decision || '') === 'diagram') {
    const payload = page.visual_decision?.visual_payload || {}
    const nodes = Array.isArray(payload.nodes) ? payload.nodes : []
    const edges = Array.isArray(payload.edges) ? payload.edges : []
    if (nodes.length < 2 || !edges.length) {
      throw new Error(`v6_visual_diagram_payload_missing:${page.page_id}`)
    }
    return [{
      kind: 'rule_diagram',
      caption: page.title,
      nodes: nodes.map((node: Record<string, any>, index: number) => ({
        node_id: String(node.node_id || ''),
        label: String(node.label || ''),
        emphasis: String(node.emphasis || (index === 0 ? 'primary' : 'supporting')),
        source_fragment_ids: Array.isArray(node.source_block_ids) ? node.source_block_ids : [],
      })),
      edges,
      source_fragment_ids: [...page.source_block_ids],
      alt_text: page.title,
      parameters: {
        direction: String(payload.direction || 'vertical'),
        template: 'process',
        relation_evidence: [...page.source_block_ids],
      },
    }]
  }
  if (['image', 'experiment'].includes(String(page.visual_decision?.decision || ''))) {
    const assetId = page.visual_decision?.source_asset_ids?.[0]
      || page.regions.flatMap(region => region.source_asset_refs || [])[0]
    if (!assetId) throw new Error(`v6_visual_source_asset_missing:${page.page_id}`)
    return [{
      kind: 'source_image',
      caption: page.title,
      alt_text: page.title,
      asset_id: assetId,
      source_fragment_ids: [...page.source_block_ids],
      parameters: { asset_ref: assetId },
    }]
  }
  return []
}

function adaptPage(
  page: V6Page,
  templateThemeOverrides: Record<string, string>,
): Record<string, any> {
  const slug = layoutSlug(page.resolved_layout)
  const adapter = layouts[slug]
  if (!adapter) throw new Error(`v6_template_layout_adapter_missing:${page.resolved_layout}`)
  const variant = layoutVariant(page, adapter)
  return {
    unit_id: page.page_id,
    position: page.page_ordinal,
    layout: adapter.basic_layout,
    slide_purpose: slug,
    eyebrow: slug.replace(/-/g, ' ').toUpperCase(),
    title: page.title,
    subtitle: '',
    key_message: '',
    teaching_job: '',
    takeaway: '',
    transition_from: '',
    composition: slug === 'evidence-diagram' ? 'diagram-full' : '',
    visuals: pageVisuals(page),
    blocks: page.regions.map(regionBlock),
    speaker_notes: notesText(page),
    source_block_ids: [...page.source_block_ids],
    quality: {
      passed: true,
      render_contract: 'template_layout_contract_v1',
      v6_template_layout_id: page.resolved_layout,
      v6_layout_slug: slug,
      v6_layout_variant: variant.variant,
      v6_artifact_support_mode: variant.supportMode,
      v6_continuation_index: Number(page.continuation_index || 1),
      v6_continuation_count: Number(page.continuation_count || 1),
      v6_title_max_lines: Math.max(1, Number(page.title_max_lines || 1)),
      resolved_layout: adapter.renderer_layout,
      task_prompt_mode: slug === 'practice-prompt' ? 'action' : '',
      prompt_label: slug === 'practice-prompt' ? '执行步骤' : '',
      template_theme_overrides: { ...templateThemeOverrides },
    },
  }
}

export function adaptSlideDeckV6ForWeb(content: V6DeckLike): Array<Record<string, any>> {
  if (content.schema_version !== 'slide_deck_v6' || !Array.isArray(content.pages)) return []
  const templateThemeOverrides = content.template_theme_overrides || {}
  return content.pages.map(page => adaptPage(page, templateThemeOverrides))
}
