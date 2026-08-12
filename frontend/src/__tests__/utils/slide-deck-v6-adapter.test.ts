import { describe, expect, it } from 'vitest'

import adapterContract from '../../data/slide-deck-v6-layout-adapters.json'
import { adaptSlideDeckV6ForWeb } from '../../utils/slide-deck-v6-adapter'


describe('slide deck V6 web adapter', () => {
  it('adapts the source-bound course cover without leaking its layout slug', () => {
    const page = {
      page_id: 'course-cover',
      page_ordinal: 0,
      title: 'Unity 游戏编程进阶实战',
      resolved_layout: 'qizhi-classroom-v2@2026.08.12.1/cover-minimal',
      source_block_ids: [],
      source_section_ids: ['chapter-1'],
      regions: [{
        region_id: 'course-cover:subtitle',
        slot_id: 'subtitle',
        content_kind: 'body',
        content: '开发环境初始化与项目结构规范',
        source_section_ids: ['chapter-1'],
      }],
      speaker_notes: {
        source_document_revision: 'course-rev-cover',
        teaching_unit_id: 'course-cover',
        source_blocks: [],
        source_section_ids: ['chapter-1'],
      },
    }

    const slide = adaptSlideDeckV6ForWeb({
      schema_version: 'slide_deck_v6',
      pages: [page],
    })[0]!

    expect(slide.eyebrow).toBe('COURSE DECK')
    expect(slide.subtitle).toBe('开发环境初始化与项目结构规范')
  })

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
        resolved_layout: 'qizhi-classroom-v2@2026.08.10.5/evidence-code',
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

  it('preserves ordered step regions as process blocks for numbered web rendering', () => {
    const slides = adaptSlideDeckV6ForWeb({
      schema_version: 'slide_deck_v6',
      pages: [{
        page_id: 'page-steps',
        page_ordinal: 0,
        title: 'Transfer the specimen',
        resolved_layout: 'qizhi-classroom-v2@2026.08.10.5/practice-prompt',
        source_block_ids: ['transfer-steps'],
        regions: [{
          region_id: 'page-steps:task',
          slot_id: 'task',
          content_kind: 'steps',
          content: [
            'Verify the specimen: Match the identifier to the record.',
            'Close the container: Confirm the seal is intact.',
            'Record the handoff: Capture the receiver name.',
          ].join('\n'),
          source_block_ids: ['transfer-steps'],
        }],
        speaker_notes: {
          source_document_revision: 'course-rev-steps',
          teaching_unit_id: 'unit-steps',
          source_blocks: [],
        },
      }],
    })

    expect(slides[0]!.blocks[0]!.type).toBe('process')
    expect(slides[0]!.quality.resolved_layout).toBe('practice-sequence')
    expect(slides[0]!.blocks[0]!.items).toEqual([
      'Verify the specimen: Match the identifier to the record.',
      'Close the container: Confirm the seal is intact.',
      'Record the handoff: Capture the receiver name.',
    ])
  })

  it('adapts a mixed practice-code page to the shared practice-artifact renderer', () => {
    const slides = adaptSlideDeckV6ForWeb({
      schema_version: 'slide_deck_v6',
      pages: [{
        page_id: 'page-practice-code',
        page_ordinal: 0,
        title: 'Verify the reading before accepting it',
        resolved_layout: 'qizhi-classroom-v2@2026.08.12.1/practice-code',
        source_block_ids: ['verification-task'],
        regions: [
          {
            region_id: 'page-practice-code:code',
            slot_id: 'code',
            content_kind: 'code',
            content: 'def accept(reading, threshold):\n    return reading <= threshold',
            source_block_ids: ['verification-task'],
          },
          {
            region_id: 'page-practice-code:task',
            slot_id: 'task',
            content_kind: 'steps',
            content: 'Capture the reading.\nCompare with the threshold.\nRecord the evidence.',
            source_block_ids: ['verification-task'],
          },
        ],
        speaker_notes: {
          source_document_revision: 'course-rev-mixed',
          teaching_unit_id: 'unit-mixed',
          source_blocks: [],
        },
      }],
    })

    expect(slides[0]!.quality.resolved_layout).toBe('practice-artifact')
    expect(slides[0]!.quality.v6_layout_slug).toBe('practice-code')
    expect(slides[0]!.blocks.map((block: any) => block.type)).toEqual(['code', 'process'])
    expect(slides[0]!.quality.task_prompt_mode).toBe('artifact-guided')
  })

  it('materializes published table-family variants and structured table data without duplicating source text', () => {
    const basePage = {
      schema_version: 'slide_page_v6',
      page_id: 'page-table',
      page_ordinal: 0,
      title: 'Compare the field evidence',
      resolved_layout: 'qizhi-classroom-v2@2026.08.10.5/evidence-table',
      source_block_ids: ['interpretation', 'evidence'],
      continuation_index: 1,
      continuation_count: 2,
      regions: [
        {
          region_id: 'page-table:table',
          slot_id: 'table',
          content_kind: 'table',
          content: '| Check | Evidence |\n| --- | --- |\n| Input \\| timestamp | Recorded |',
          source_block_ids: ['evidence'],
        },
        {
          region_id: 'page-table:interpretation',
          slot_id: 'interpretation',
          content_kind: 'body',
          content: 'Compare the recorded condition with the required evidence.',
          source_block_ids: ['interpretation'],
        },
      ],
      visual_decision: { decision: 'table' },
      speaker_notes: {
        source_document_revision: 'r1',
        teaching_unit_id: 'u1',
        source_blocks: [{ block_id: 'evidence', block_revision: 'b1', full_text: 'full table' }],
      },
    }
    const content = {
      schema_version: 'slide_deck_v6',
      pages: [
        basePage,
        {
          ...basePage,
          page_id: 'page-table--continuation-2',
          page_ordinal: 1,
          continuation_of_page_id: 'page-table',
          continuation_index: 2,
          regions: basePage.regions.map(region => ({
            ...region,
            region_id: region.region_id.replace('page-table', 'page-table--continuation-2'),
          })),
        },
      ],
    }

    const slides = adaptSlideDeckV6ForWeb(content)

    expect(slides[0]!.quality.v6_layout_variant).toBe('table-with-interpretation')
    expect(slides[1]!.quality.v6_layout_variant).toBe('table-row-detail')
    expect(slides[0]!.visuals[0].parameters).toEqual({
      headers: ['Check', 'Evidence'],
      rows: [['Input | timestamp', 'Recorded']],
    })
    expect(slides[0]!.blocks[0].metadata.table_source).toBe(true)
  })

  it('uses the row-detail layout when one source row is too dense for table columns', () => {
    const content = {
      schema_version: 'slide_deck_v6',
      pages: [{
        schema_version: 'slide_page_v6',
        page_id: 'page-dense-row',
        page_ordinal: 0,
        title: 'Inspect every field before publishing',
        resolved_layout: 'qizhi-classroom-v2@2026.08.11.1/evidence-table',
        source_block_ids: ['evidence'],
        continuation_index: 1,
        continuation_count: 1,
        regions: [{
          region_id: 'page-dense-row:table',
          slot_id: 'table',
          content_kind: 'table',
          content: [
            '| Stage | Standard | Evidence | Basis | Repair |',
            '| --- | --- | --- | --- | --- |',
            '| Observe | Preserve the complete signed field record before analysis begins | Retain the place, time, observer, instrument, and sampling window | Compare the record against the declared acceptance condition | Keep evidence separate from interpretation and restore every missing source field before publishing |',
          ].join('\n'),
          source_block_ids: ['evidence'],
        }],
        visual_decision: { decision: 'table' },
        speaker_notes: {
          source_document_revision: 'r1',
          teaching_unit_id: 'u1',
          source_blocks: [{ block_id: 'evidence', block_revision: 'b1', full_text: 'full table' }],
        },
      }],
    }

    const slides = adaptSlideDeckV6ForWeb(content)

    expect(slides[0]!.quality.v6_layout_variant).toBe('table-row-detail')
    expect(slides[0]!.quality.v6_artifact_support_mode).toBe('full')
  })

  it('uses the wide-table summary band for four-or-more-column evidence', () => {
    const page = {
      schema_version: 'slide_page_v6',
      page_id: 'page-wide-table',
      page_ordinal: 0,
      title: 'Compare the field evidence',
      resolved_layout: 'qizhi-classroom-v2@2026.08.10.5/evidence-table',
      source_block_ids: ['evidence', 'interpretation'],
      continuation_index: 1,
      continuation_count: 1,
      regions: [
        {
          region_id: 'page-wide-table:table',
          slot_id: 'table',
          content_kind: 'table',
          content: [
            '| Stage | Standard | Evidence | Repair |',
            '| --- | --- | --- | --- |',
            '| Observe | Record context | Preserve evidence | Repair gaps |',
          ].join('\n'),
          source_block_ids: ['evidence'],
        },
        {
          region_id: 'page-wide-table:interpretation',
          slot_id: 'interpretation',
          content_kind: 'body',
          content: 'Compare every observation with its declared evidence.',
          source_block_ids: ['interpretation'],
        },
      ],
      visual_decision: { decision: 'table' },
      speaker_notes: {
        source_document_revision: 'r1',
        teaching_unit_id: 'u1',
        source_blocks: [],
      },
    }

    const slides = adaptSlideDeckV6ForWeb({ schema_version: 'slide_deck_v6', pages: [page] })

    expect(slides[0]!.quality.v6_layout_variant).toBe('table-wide-with-summary')
    expect(slides[0]!.quality.v6_artifact_support_mode).toBe('band')
  })

  it('uses the full-width table family for dense three-column evidence', () => {
    const content = {
      schema_version: 'slide_deck_v6',
      pages: [{
        schema_version: 'slide_page_v6',
        page_id: 'page-dense-three-column-table',
        page_ordinal: 0,
        title: 'Preserve the full diagnostic evidence',
        resolved_layout: 'qizhi-classroom-v2@2026.08.10.5/evidence-table',
        source_block_ids: ['evidence', 'interpretation'],
        continuation_index: 1,
        continuation_count: 1,
        regions: [
          {
            region_id: 'page-dense-three-column-table:table',
            slot_id: 'table',
            content_kind: 'table',
            content: [
              '| Symptom | Cause | Repair |',
              '| --- | --- | --- |',
              '| The recorded state cannot be reconciled with the acceptance condition | Preserve the complete source evidence before review | Re-open the review and repair every missing field |',
            ].join('\n'),
            source_block_ids: ['evidence'],
          },
          {
            region_id: 'page-dense-three-column-table:interpretation',
            slot_id: 'interpretation',
            content_kind: 'body',
            content: 'Compare every condition before publishing the result.',
            source_block_ids: ['interpretation'],
          },
        ],
        visual_decision: { decision: 'table' },
        speaker_notes: {
          source_document_revision: 'r1',
          teaching_unit_id: 'u1',
          source_blocks: [],
        },
      }],
    }

    const slides = adaptSlideDeckV6ForWeb(content)

    expect(slides[0]!.quality.v6_layout_variant).toBe('table-wide-with-summary')
    expect(slides[0]!.quality.v6_artifact_support_mode).toBe('band')
  })
})
