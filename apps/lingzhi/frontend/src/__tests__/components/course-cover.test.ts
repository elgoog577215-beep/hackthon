import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const coverSource = readFileSync(resolve(process.cwd(), 'src/components/CourseCover.vue'), 'utf8')

describe('course cover', () => {
  it('uses category texture variants of the same three-dimensional book model', () => {
    expect(coverSource).toMatch(/width:\s*var\(--course-cover-width,\s*78px\)/)
    expect(coverSource).toMatch(/aspect-ratio:\s*2\s*\/\s*3/)
    const presets = ['ai', 'programming', 'mathematics', 'medicine', 'engineering', 'science', 'humanities', 'general']
    for (const preset of presets) {
      const filename = `course-book-${preset}.png`
      expect(coverSource).toContain(filename)
      expect(existsSync(resolve(process.cwd(), 'src/assets/course-covers', filename))).toBe(true)
    }
    expect(coverSource.match(/class="course-cover__book"/g)).toHaveLength(1)
    expect(coverSource).toMatch(/:src="bookTexture"/)
    expect(coverSource).toMatch(/const bookTextures:\s*Record<CourseCoverPreset,\s*string>/)
    expect(coverSource).toMatch(/BookOpenText/)
    expect(coverSource).toContain("variant === 'glyph'")
    expect(coverSource).toMatch(/\.course-cover--glyph\s*\{/)
    expect(coverSource).not.toMatch(/course-cover__(?:artwork|pattern|symbol|detail)/)
  })
})
