import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('课程教案阅读尺度', () => {
  it('桌面端教案正文不再使用 8 至 10 像素的微缩字号', () => {
    const component = readFileSync(
      resolve(process.cwd(), 'src/components/GenerationLessonPlan.vue'),
      'utf8',
    )

    expect(component).not.toMatch(/font-size:\s*(?:8|9|10)px/)
    expect(component).toContain('width:min(1160px,100%)')
    expect(component).toContain('.generation-lesson-plan__body > header strong { color:#273144; font-size:17px;')
    expect(component).toContain('.generation-lesson-plan__body li p { margin:5px 0 0; color:#697386; font-size:13px;')
  })
})
