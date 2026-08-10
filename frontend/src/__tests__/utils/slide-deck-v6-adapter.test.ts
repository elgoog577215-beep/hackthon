import { describe, expect, it } from 'vitest'

import adapterContract from '../../data/slide-deck-v6-layout-adapters.json'
import { adaptSlideDeckV6ForWeb } from '../../utils/slide-deck-v6-adapter'


describe('slide deck V6 web adapter', () => {
  it('uses the shared template adapter contract and preserves full V6 layout identity', () => {
    const content = {
      schema_version: 'slide_deck_v6',
      title: 'Event-driven interaction',
      theme: 'qizhi-classroom',
      template_theme_overrides: { accent: '315E7D', title_font: 'Noto Serif SC' },
      pages: [{
        schema_version: 'slide_page_v6',
        page_id: 'page-code',
        page_ordinal: 0,
        title: 'Connect the event to feedback',
        resolved_layout: 'qizhi-classroom-v2@2026.08.10.4/evidence-code',
        source_block_ids: ['condition', 'implementation', 'result'],
        artifact_kinds: ['code'],
        regions: [
          {
            region_id: 'page-code:code',
            slot_id: 'code',
            content_kind: 'code',
            content: 'function onEvent(value) { return validate(value); }',
            source_block_ids: ['implementation'],
          },
          {
            region_id: 'page-code:annotation',
            slot_id: 'annotation',
            content_kind: 'body',
            content: 'The handler runs after the event and preserves rejected input.',
            source_block_ids: ['condition', 'result'],
          },
        ],
        speaker_notes: {
          source_document_revision: 'course-rev-1',
          teaching_unit_id: 'unit-1',
          source_blocks: [{
            block_id: 'implementation',
            block_revision: 'block-rev-1',
            full_text: 'function onEvent(value) { return validate(value); }',
          }],
        },
      }],
    }

    const slides = adaptSlideDeckV6ForWeb(content)
    const slide = slides[0]!
    const page = content.pages[0]!

    expect(adapterContract.schema_version).toBe('slide_deck_v6_layout_adapters_v1')
    expect(slides).toHaveLength(1)
    expect(slide.layout).toBe('code')
    expect(slide.quality.resolved_layout).toBe('code')
    expect(slide.quality.v6_layout_slug).toBe('evidence-code')
    expect(slide.quality.v6_template_layout_id).toBe(page.resolved_layout)
    expect(slide.blocks[0]!.type).toBe('code')
    expect(slide.source_block_ids).toEqual(page.source_block_ids)
    expect(slide.speaker_notes).toContain('course-rev-1')
    expect(slide.quality.template_theme_overrides).toEqual(content.template_theme_overrides)
  })

  it('fails closed when a V6 page references a layout absent from the published adapter contract', () => {
    expect(() => adaptSlideDeckV6ForWeb({
      schema_version: 'slide_deck_v6',
      pages: [{
        page_id: 'page-unknown',
        page_ordinal: 0,
        title: 'Unknown',
        resolved_layout: 'template@1/legacy-two-column',
        source_block_ids: ['block-1'],
        regions: [],
        speaker_notes: { source_document_revision: 'r1', teaching_unit_id: 'u1', source_blocks: [] },
      }],
    })).toThrow('v6_template_layout_adapter_missing')
  })
})
