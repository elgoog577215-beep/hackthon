import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const librarySource = readFileSync(
  resolve(process.cwd(), 'src/views/CourseLibraryView.vue'),
  'utf8',
)
const coverSource = readFileSync(
  resolve(process.cwd(), 'src/components/CourseCover.vue'),
  'utf8',
)

describe('course library density contract', () => {
  it('preserves the original course library shell measurements', () => {
    expect(librarySource).toMatch(/--course-content-width:\s*1280px/)
    expect(librarySource).toMatch(/padding:\s*30px\s+clamp\(18px,4vw,54px\)\s+48px/)
    expect(librarySource).not.toMatch(/class="resume-card"/)
    expect(librarySource).toMatch(/\.library-toolbar\s*\{[^}]*margin:\s*24px\s+auto\s+14px[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(240px,360px\)\s+minmax\(0,1fr\)/s)
    expect(librarySource).toMatch(/\.library-toolbar label\s*\{[^}]*width:\s*100%[^}]*height:\s*44px/s)
    expect(librarySource).toMatch(/\.library-toolbar__count\s*\{[^}]*justify-self:\s*end/s)
    expect(librarySource).not.toMatch(/class="library-resume"/)
  })

  it('uses two readable teacher-workbench cards and gives a single course enough width', () => {
    expect(librarySource).toMatch(/--course-grid-width:\s*1280px/)
    expect(librarySource).toMatch(/--course-card-height:\s*150px/)
    expect(librarySource).toMatch(/--course-grid-gap:\s*18px/)
    expect(librarySource).toMatch(/\.course-grid\s*\{[^}]*max-width:\s*1040px[^}]*margin:\s*0[^}]*margin-inline-start:\s*max\(0px,calc\(\(100%\s*-\s*var\(--course-content-width\)\)\s*\/\s*2\)\)[^}]*justify-content:\s*start/s)
    expect(librarySource).toMatch(/\.course-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/s)
    expect(librarySource).toMatch(/\.course-grid:has\(\.course-item:only-child\)\s*\{[^}]*max-width:\s*720px[^}]*grid-template-columns:\s*minmax\(0,720px\)/s)
    expect(librarySource).toMatch(/@media\s*\(max-width:1360px\)\s*\{[^}]*\.course-grid\s*\{[^}]*max-width:\s*1040px[^}]*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/s)
    expect(librarySource).toMatch(/@media\s*\(max-width:860px\)\s*\{[^}]*\.course-grid\s*\{[^}]*max-width:\s*511px[^}]*grid-template-columns:\s*minmax\(0,1fr\)/s)
    expect(librarySource).not.toMatch(/\.course-grid\s*\{[^}]*margin:\s*0\s+auto/s)
    expect(librarySource).toMatch(/\.course-item\s*\{[^}]*grid-template-columns:\s*minmax\(0,1fr\)\s+96px/s)
    expect(librarySource).toMatch(/\.course-main\s*\{[^}]*gap:\s*16px[^}]*padding:\s*16px\s+8px\s+16px\s+18px/s)
    expect(librarySource).toMatch(/\.course-copy\s*\{[^}]*min-width:\s*0[^}]*display:\s*flex/s)
    expect(librarySource).not.toMatch(/\.course-copy\s*\{[^}]*max-width:/s)
    expect(librarySource).toMatch(/\.course-copy h2\s*\{[^}]*font-size:\s*16px/s)
    expect(librarySource).toMatch(/\.course-status\s*\{[^}]*font-size:\s*12px/s)
  })

  it('uses category texture variants of the same three-dimensional book model', () => {
    expect(librarySource).toMatch(/--course-cover-width:\s*78px/)
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
    expect(coverSource).not.toMatch(/lucide-vue-next/)
    expect(coverSource).not.toMatch(/course-cover__(?:artwork|pattern|symbol|detail)/)
  })

  it('keeps the primary action on one line and uses a compact overflow menu', () => {
    expect(librarySource).toMatch(/\.course-primary-action\s*\{[^}]*white-space:\s*nowrap/s)
    expect(librarySource).toMatch(/\.course-menu\s*\{[^}]*width:\s*160px[^}]*padding:\s*4px[^}]*border-radius:\s*10px/s)
    expect(librarySource).toMatch(/\.course-menu__item\s*\{[^}]*min-height:\s*36px[^}]*gap:\s*8px[^}]*padding:\s*0\s+9px/s)
    expect(librarySource.match(/<(?:ShieldCheck|Trash2)\s+:size="15"/g)).toHaveLength(2)
  })
})
