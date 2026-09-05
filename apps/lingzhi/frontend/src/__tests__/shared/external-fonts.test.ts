import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('external font loading', () => {
  it('does not block the application shell on third-party font stylesheets', () => {
    const indexHtml = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')
    const globalCss = readFileSync(resolve(process.cwd(), 'src/style.css'), 'utf8')
    const applicationShell = `${indexHtml}\n${globalCss}`

    expect(applicationShell).not.toContain('fonts.googleapis.com')
    expect(applicationShell).not.toContain('fonts.gstatic.com')
    expect(applicationShell).not.toMatch(/@import\s+url\(['"]https?:\/\//)
  })
})
