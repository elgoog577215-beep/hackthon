import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import themePack from '../../data/slide-themes.json'

const source = readFileSync(resolve(process.cwd(), 'src/components/SlideCanvas.vue'), 'utf8')

function cssVariables(selector: string) {
  const start = source.indexOf(`${selector} {`)
  const end = source.indexOf('\n}', start)
  return source.slice(start, end)
}

describe('SlideCanvas renderer theme contract', () => {
  it('keeps the Qingfeng Classroom tokens aligned with the backend renderer', () => {
    const css = cssVariables('.deck-canvas')

    expect(css).toContain('--deck-bg:#F7FAFC;')
    expect(css).toContain('--deck-main:#2B6CB0;')
    expect(css).toContain('--deck-title:#1A365D;')
    expect(css).toContain('--deck-accent:#ED8936;')
    expect(css).toContain('--deck-body:#4A5568;')
    expect(css).toContain('--deck-title-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;')
    expect(css).toContain('--deck-body-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;')
  })

  it('keeps the Academic Blue-gray tokens aligned with the backend renderer', () => {
    const css = cssVariables('.deck-canvas[data-theme="academic-bluegray"]')

    expect(css).toContain('--deck-bg:#FCFCFD;')
    expect(css).toContain('--deck-title:#2C3E50;')
    expect(css).toContain('--deck-body:#5D6D7E;')
    expect(css).toContain('--deck-blue:#2E86C1;')
    expect(css).toContain('--deck-chart:#E8EBEE;')
    expect(css).toContain('--deck-title-font:"Noto Serif SC","SimSun","宋体",serif;')
    expect(css).toContain('--deck-body-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;')
  })

  it('ships the authored Qizhi Classroom visual template through the shared theme pack', () => {
    const qizhi = themePack.themes['qizhi-classroom']

    expect(qizhi.template.template_id).toBe('qizhi-classroom-v2')
    expect(qizhi.visual_assets.cover.web_path).toContain('cover-learning-journey.jpg')
    expect(qizhi.visual_assets.chapter.web_path).toContain('chapter-opening.jpg')
    expect(qizhi.visual_assets.recap.web_path).toContain('recap-convergence.jpg')
    expect(qizhi.visual_assets.interior_content.web_path).toContain('interior-content.jpg')
    expect(qizhi.visual_assets.interior_reasoning.web_path).toContain('interior-reasoning.jpg')
    expect(qizhi.visual_assets.interior_practice.web_path).toContain('interior-practice.jpg')
    expect(qizhi.visual_assets.interior_evidence.web_path).toContain('interior-evidence.jpg')
    expect(qizhi.background_profiles.practice.asset).toBe('interior_practice')
    expect(qizhi.text_box_styles.feedback.accent).toBe('16856B')
    expect(qizhi.text_box_styles.feedback.depth).toBe('B4DCCD')
    expect(qizhi.semantic_layout_weights['chapter-question']).toBeGreaterThan(1)
    expect(source).toContain('--deck-cover-image')
    expect(source).toContain('--deck-chapter-image')
    expect(source).toContain('--deck-recap-image')
    expect(source).toContain('--deck-content-image')
    expect(source).toContain('--deck-reasoning-image')
    expect(source).toContain('--deck-practice-image')
    expect(source).toContain('--deck-evidence-image')
    expect(source).toContain('--deck-box-misconception')
    expect(source).toContain('--deck-box-message-depth')
    expect(source).toContain('inset 0 .12cqw 0')
  })

  it('renders the Qizhi hero claim card with one accent rail', () => {
    const heroCardCss = cssVariables(
      '.deck-canvas[data-theme="qizhi-classroom"] .deck-hero-claim',
    )
    const innerRailCss = cssVariables(
      '.deck-canvas[data-theme="qizhi-classroom"] .deck-hero-claim > i',
    )

    expect(heroCardCss).toContain('grid-template-columns:minmax(0,1fr);')
    expect(innerRailCss).toContain('display:none;')
  })
})
