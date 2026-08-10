import adapterContract from '../data/slide-deck-v6-layout-adapters.json'


interface V6Region {
  region_id: string
  slot_id: string
  content_kind: string
  content: string
  source_block_ids?: string[]
  source_asset_refs?: string[]
}

interface V6NoteBlock {
  block_id: string
  block_revision: string
  full_text: string
}

interface V6Page {
  page_id: string
  page_ordinal: number
  title: string
  resolved_layout: string
  source_block_ids: string[]
  regions: V6Region[]
  visual_decision?: {
    decision?: string
    source_asset_ids?: string[]
  }
  speaker_notes: {
    source_document_revision: string
    teaching_unit_id: string
    source_blocks: V6NoteBlock[]
  }
}

interface V6DeckLike {
  schema_version?: string
  pages?: V6Page[]
}

interface AdapterDefinition {
  renderer_layout: string
  basic_layout: string
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
    ...page.speaker_notes.source_blocks.map(block => (
      `[${block.block_id} @ ${block.block_revision}]\n${block.full_text}`
    )),
  ].join('\n\n')
}

function regionBlock(region: V6Region): Record<string, unknown> {
  const items = region.content_kind === 'items'
    ? region.content.split('\n').map(item => item.trim()).filter(Boolean)
    : []
  return {
    block_id: region.region_id,
    type: region.content_kind === 'code'
      ? 'code'
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
  if (table) return [{ kind: 'table', caption: table.slot_id, parameters: {} }]
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

function adaptPage(page: V6Page): Record<string, any> {
  const slug = layoutSlug(page.resolved_layout)
  const adapter = layouts[slug]
  if (!adapter) throw new Error(`v6_template_layout_adapter_missing:${page.resolved_layout}`)
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
      resolved_layout: adapter.renderer_layout,
    },
  }
}

export function adaptSlideDeckV6ForWeb(content: V6DeckLike): Array<Record<string, any>> {
  if (content.schema_version !== 'slide_deck_v6' || !Array.isArray(content.pages)) return []
  return content.pages.map(adaptPage)
}
