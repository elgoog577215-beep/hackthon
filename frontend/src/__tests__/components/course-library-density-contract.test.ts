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
  it('uses a compact desktop shell without weakening the resume path', () => {
    expect(librarySource).toMatch(/--course-content-width:\s*1280px/)
    expect(librarySource).toMatch(/padding:\s*24px\s+clamp\(18px,4vw,54px\)\s+38px/)
    expect(librarySource).not.toMatch(/class="resume-card"/)
    expect(librarySource).toMatch(/\.library-toolbar\s*\{[^}]*margin:\s*16px\s+auto\s+12px[^}]*display:\s*flex[^}]*align-items:\s*center[^}]*gap:\s*10px/s)
    expect(librarySource).toMatch(/\.library-toolbar label\s*\{[^}]*width:\s*100%[^}]*height:\s*40px[^}]*flex:\s*0\s+1\s+330px/s)
    expect(librarySource).toMatch(/\.library-resume\s*\{[^}]*height:\s*40px[^}]*flex:\s*1\s+1\s+520px[^}]*grid-template-columns:\s*26px\s+minmax\(0,1fr\)\s+auto/s)
    expect(librarySource).toMatch(/\.library-resume__action svg\s*\{[^}]*transition:\s*transform\s+\.18s\s+ease/s)
    expect(librarySource).toMatch(/\.library-resume:hover\s+\.library-resume__action svg\s*\{[^}]*transform:\s*translateX\(3px\)/s)
    expect(librarySource).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[^}]*\.library-resume[^}]*transition:\s*none/s)
  })

  it('fills wide screens with three readable cards and steps down responsively', () => {
    expect(librarySource).toMatch(/--course-grid-width:\s*1280px/)
    expect(librarySource).toMatch(/--course-card-height:\s*140px/)
    expect(librarySource).toMatch(/--course-grid-gap:\s*14px/)
    expect(librarySource).toMatch(/\.course-grid\s*\{[^}]*max-width:\s*var\(--course-grid-width\)[^}]*margin:\s*0[^}]*margin-inline-start:\s*max\(0px,calc\(\(100%\s*-\s*var\(--course-content-width\)\)\s*\/\s*2\)\)[^}]*justify-content:\s*start/s)
    expect(librarySource).toMatch(/\.course-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3,minmax\(0,1fr\)\)/s)
    expect(librarySource).toMatch(/@media\s*\(max-width:1360px\)\s*\{[^}]*\.course-grid\s*\{[^}]*max-width:\s*1040px[^}]*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/s)
    expect(librarySource).toMatch(/@media\s*\(max-width:860px\)\s*\{[^}]*\.course-grid\s*\{[^}]*max-width:\s*511px[^}]*grid-template-columns:\s*minmax\(0,1fr\)/s)
    expect(librarySource).not.toMatch(/\.course-grid\s*\{[^}]*margin:\s*0\s+auto/s)
    expect(librarySource).toMatch(/\.course-item\s*\{[^}]*grid-template-columns:\s*minmax\(0,1fr\)\s+96px/s)
    expect(librarySource).toMatch(/\.course-main\s*\{[^}]*gap:\s*14px[^}]*padding:\s*13px\s+8px\s+13px\s+16px/s)
    expect(librarySource).toMatch(/\.course-copy\s*\{[^}]*min-width:\s*0[^}]*display:\s*flex/s)
    expect(librarySource).not.toMatch(/\.course-copy\s*\{[^}]*max-width:/s)
    expect(librarySource).toMatch(/\.course-copy h2\s*\{[^}]*font-size:\s*16px/s)
    expect(librarySource).toMatch(/\.course-status\s*\{[^}]*font-size:\s*12px/s)
  })

  it('uses category texture variants of the same three-dimensional book model', () => {
    expect(librarySource).toMatch(/--course-cover-width:\s*72px/)
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

  it('adapts the Uiverse white navigation control into an accessible split action', () => {
    expect(librarySource).toMatch(/class="create-course-trigger-group"/)
    expect(librarySource).toMatch(/class="create-course-primary__icon"/)
    expect(librarySource).toMatch(/class="create-course-primary__label"/)
    expect(librarySource).toMatch(/\.create-course-trigger-group\s*\{[^}]*height:\s*44px[^}]*border:\s*1px\s+solid[^}]*border-radius:\s*10px[^}]*background:\s*#fff[^}]*box-shadow:/s)
    expect(librarySource).toMatch(/\.create-course-primary\s*\{[^}]*padding:\s*0\s+14px[^}]*font-size:\s*13px[^}]*font-weight:\s*700[^}]*white-space:\s*nowrap/s)
    expect(librarySource).toMatch(/\.create-course-primary__icon\s*\{[^}]*width:\s*22px[^}]*height:\s*22px[^}]*color:\s*#7c3aed[^}]*transition:\s*transform/s)
    expect(librarySource).toMatch(/\.create-course-primary:hover\s*\{[^}]*color:\s*#6d28d9[^}]*background:\s*#f5f5f5/s)
    expect(librarySource).toMatch(/\.create-course-primary:hover\s+\.create-course-primary__icon\s*\{[^}]*transform:\s*rotate\(90deg\)\s+scale\(1\.05\)/s)
    expect(librarySource).toMatch(/\.create-course-menu-toggle\s*\{[^}]*width:\s*40px[^}]*border-left:\s*1px\s+solid\s+rgba\(226,232,240,\.96\)/s)
    expect(librarySource).toMatch(/\.course-primary-action\s*\{[^}]*white-space:\s*nowrap/s)
    expect(librarySource).toMatch(/\.course-menu\s*\{[^}]*width:\s*160px[^}]*padding:\s*4px[^}]*border-radius:\s*10px/s)
    expect(librarySource).toMatch(/\.course-menu__item\s*\{[^}]*min-height:\s*36px[^}]*gap:\s*8px[^}]*padding:\s*0\s+9px/s)
    expect(librarySource.match(/<(?:ShieldCheck|Trash2)\s+:size="15"/g)).toHaveLength(2)
  })
})
