import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

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
})
