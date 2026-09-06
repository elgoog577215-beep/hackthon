import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SlideCanvas from '../../components/SlideCanvas.vue'
import themePack from '../../data/slide-themes.json'

const themes = [
  'qizhi-classroom',
  'academic-editorial',
  'grid-notebook',
  'modern-geometric',
  'dark-tech',
] as const

const semanticRoles = [
  'cover',
  'agenda',
  'chapter',
  'objective',
  'definition',
  'concept',
  'boundary',
  'process',
  'worked-example',
  'reasoning',
  'practice',
  'feedback',
  'code',
  'table',
  'visual-evidence',
  'misconception',
  'recap',
  'synthesis',
] as const

describe('five-theme Web rendering matrix', () => {
  it('renders all 90 theme-by-semantic-role pages through the complete template mechanism', () => {
    let renderedPages = 0

    for (const theme of themes) {
      for (const [index, semanticRole] of semanticRoles.entries()) {
        const wrapper = mount(SlideCanvas, {
          props: {
            slide: {
              layout: 'concept',
              eyebrow: semanticRole,
              title: `${theme} · ${semanticRole}`,
              key_message: '教学文本保持可编辑，并由模板负责背景、卡片和强调样式。',
              blocks: [{
                block_id: `${theme}-${semanticRole}`,
                type: semanticRole === 'practice' ? 'exercise' : 'text',
                title: '语义内容',
                content: '这是一条用于验证背景安全区、文本卡片和主题变量的标准样例。',
                metadata: { semantic_role: semanticRole },
              }],
              quality: { resolved_layout: 'editorial-body' },
            },
            pageNumber: index + 1,
            pageCount: semanticRoles.length,
            deckTitle: '五主题标准样例',
            theme,
          },
          global: {
            stubs: {
              MarkdownRenderer: { template: '<div class="markdown-stub"><slot /></div>' },
              SlideVisualRenderer: { template: '<div class="visual-stub" />' },
            },
          },
        })

        expect(wrapper.get('.deck-canvas').attributes('data-template-rich')).toBe('true')
        expect(wrapper.get('.deck-canvas').attributes('data-theme')).toBe(theme)
        expect(wrapper.find('.slide-visual__fallback').exists()).toBe(false)
        expect(wrapper.text()).toContain(semanticRole)
        wrapper.unmount()
        renderedPages += 1
      }
    }

    expect(renderedPages).toBe(90)
  })

  it('uses the selected pack label and authenticated logo instead of a hard-coded Qizhi brand', () => {
    const compiledTheme = {
      ...themePack.themes['academic-editorial'],
      label: '示例学院',
    }
    const wrapper = mount(SlideCanvas, {
      props: {
        slide: {
          layout: 'cover',
          title: '课程封面',
          blocks: [],
          quality: { resolved_layout: 'cover-editorial' },
        },
        pageNumber: 1,
        pageCount: 18,
        deckTitle: '示例课程',
        theme: 'academic-editorial',
        templatePack: {
          compiled_theme: compiledTheme,
          asset_urls: { logo: 'blob:personal-template-logo' },
        },
      },
    })

    expect(wrapper.get('.deck-cover__brand img').attributes('src')).toBe('blob:personal-template-logo')
    expect(wrapper.get('.deck-cover__brand').attributes('aria-label')).toBe('示例学院')
  })
})
