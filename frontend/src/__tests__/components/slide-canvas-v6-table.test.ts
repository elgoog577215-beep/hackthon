import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideCanvas from '../../components/SlideCanvas.vue'


type TableVariant = 'table-with-interpretation' | 'table-continuation' | 'table-wide-with-summary' | 'table-row-detail'

function tableSlide(variant: TableVariant) {
  return {
    layout: 'concept',
    title: 'Compare the field evidence',
    visuals: [{
      visual_id: 'table-visual',
      kind: 'table',
      purpose: 'evidence',
      alt_text: 'Field evidence table',
      parameters: { headers: ['Check', 'Evidence'], rows: [['Input', 'Recorded']] },
    }],
    blocks: [
      {
        block_id: 'table',
        type: 'statement',
        content: '| Check | Evidence |\n| --- | --- |\n| Input | Recorded |',
        metadata: { table_source: true },
      },
      {
        block_id: 'interpretation',
        type: 'statement',
        title: 'Interpretation',
        content: 'Compare the recorded condition with the required evidence.',
      },
    ],
    quality: {
      resolved_layout: 'data-highlight',
      audience_label_policy: 'source_only',
      v6_layout_variant: variant,
      v6_artifact_support_mode: (
        variant === 'table-with-interpretation'
          ? 'split'
          : variant === 'table-wide-with-summary'
            ? 'band'
            : 'full'
      ) as 'split' | 'full' | 'band',
    },
  }
}

function mountSlide(variant: TableVariant) {
  return mount(SlideCanvas, {
    props: {
      slide: tableSlide(variant),
      pageNumber: variant === 'table-continuation' ? 2 : 1,
      pageCount: 2,
      deckTitle: 'Field evidence review',
    },
    global: {
      stubs: {
        MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
        SlideVisualRenderer: { template: '<div class="visual-stub" />' },
      },
    },
  })
}

describe('SlideCanvas V6 table family', () => {
  it('shows interpretation beside the table once and gives continuation pages the full canvas', () => {
    const split = mountSlide('table-with-interpretation')
    const splitStory = split.get('.deck-canvas__story')

    expect(splitStory.attributes('data-layout-variant')).toBe('table-with-interpretation')
    expect(split.find('.deck-canvas__heading small').exists()).toBe(false)
    expect(split.findAll('.deck-canvas__source section')).toHaveLength(1)
    expect(split.get('.deck-canvas__source').text()).toContain('Compare the recorded condition')
    expect(split.get('.deck-canvas__source').text()).not.toContain('| Check | Evidence |')

    const continuation = mountSlide('table-continuation')
    const continuationStory = continuation.get('.deck-canvas__story')

    expect(continuationStory.attributes('data-layout-variant')).toBe('table-continuation')
    expect(continuationStory.attributes('data-source-empty')).toBe('true')
    expect(continuation.find('.deck-canvas__source').exists()).toBe(false)
  })

  it('keeps the source-grounded summary visible below a wide table', () => {
    const wide = mountSlide('table-wide-with-summary')
    const story = wide.get('.deck-canvas__story')

    expect(story.attributes('data-layout-variant')).toBe('table-wide-with-summary')
    expect(story.attributes('data-source-empty')).toBe('false')
    expect(wide.get('.deck-canvas__source').text()).toContain('Compare the recorded condition')
  })

  it('promotes one oversized continuation row into labeled detail fields', () => {
    const detail = mountSlide('table-row-detail')
    const fields = detail.findAll('.deck-table-row-detail article')

    expect(fields).toHaveLength(2)
    expect(fields[0]!.text()).toContain('Check')
    expect(fields[0]!.text()).toContain('Input')
    expect(fields[1]!.text()).toContain('Evidence')
    expect(fields[1]!.text()).toContain('Recorded')
    expect(detail.find('.visual-stub').exists()).toBe(false)
  })
})
