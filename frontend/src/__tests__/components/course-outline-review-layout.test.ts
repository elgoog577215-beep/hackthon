import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentSource = readFileSync(
  resolve(process.cwd(), 'src/components/CourseOutlineReview.vue'),
  'utf8',
)

function cssDeclarations(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = componentSource.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`))
  return match?.[1] ?? ''
}

describe('course outline review layout', () => {
  it('keeps confirmation actions outside the scrollable body when retrieval content is tall', () => {
    const bodyStart = componentSource.indexOf('<div class="outline-review__body">')
    const setupStart = componentSource.indexOf('<div class="outline-review__setup"')
    const editorStart = componentSource.indexOf('data-testid="outline-rich-editor"')
    const footerStart = componentSource.indexOf('<footer class="outline-review__footer"')

    expect(bodyStart).toBeGreaterThan(-1)
    expect(bodyStart).toBeLessThan(setupStart)
    expect(setupStart).toBeLessThan(editorStart)
    expect(editorStart).toBeLessThan(footerStart)

    expect(cssDeclarations('.outline-review__sheet')).toContain(
      'grid-template-rows:minmax(0,1fr) auto',
    )
    expect(cssDeclarations('.outline-review')).toContain('height:100%')
    expect(cssDeclarations('.outline-review')).toContain('box-sizing:border-box')
    expect(cssDeclarations('.outline-review__body')).toContain('min-height:0')
    expect(cssDeclarations('.outline-review__body')).toContain('overflow:auto')
    expect(cssDeclarations('.outline-review__body')).toContain('scrollbar-gutter:stable')
    expect(componentSource).toContain('contenteditable="editable && !adjustmentBusy')
    expect(componentSource).toContain('class="formal-outline__schedule outline-rich-editor"')
    expect(componentSource).not.toContain('outline-review__chapter-nav')
    expect(componentSource).not.toContain('outline-review__index')
    expect(componentSource).not.toContain('outline-review__branch')
    expect(componentSource).not.toContain('class="outline-review__header"')
    expect(componentSource).not.toContain('class="outline-review__course-name"')
  })
})
