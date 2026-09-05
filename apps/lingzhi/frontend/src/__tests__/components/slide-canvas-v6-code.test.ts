import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideCanvas from '../../components/SlideCanvas.vue'


describe('SlideCanvas V6 source-only code layout', () => {
  it('uses the whole content width when no source-backed annotation exists', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        slide: {
          layout: 'code',
          title: 'Normalize the reading',
          blocks: [{
            block_id: 'normalization-code',
            type: 'code',
            title: '',
            content: 'def normalize(reading):\n    return max(0, min(100, reading))',
          }],
          quality: {
            resolved_layout: 'code',
            v6_layout_slug: 'evidence-code',
          },
        },
        pageNumber: 1,
        pageCount: 1,
        deckTitle: 'Source-bound automation',
      },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
          SlideVisualRenderer: { template: '<div />' },
        },
      },
    })

    const blocks = wrapper.get('.deck-canvas__blocks')
    const source = readFileSync(resolve(process.cwd(), 'src/components/SlideCanvas.vue'), 'utf8')

    expect(blocks.attributes('data-layout')).toBe('code')
    expect(blocks.attributes('data-count')).toBe('1')
    expect(source).toMatch(
      /\.deck-canvas__blocks\[data-layout="code"\]\[data-count="1"\]\s*\{[^}]*grid-template-columns:1fr/s,
    )
  })
})
