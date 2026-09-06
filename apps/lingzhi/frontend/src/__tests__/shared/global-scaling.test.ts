import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('全局页面缩放约束', () => {
  it('不再用 body zoom 和反向视口尺寸压缩桌面界面', () => {
    const stylesheet = readFileSync(resolve(process.cwd(), 'src/style.css'), 'utf8')

    expect(stylesheet).not.toMatch(/body\s*\{[^}]*zoom\s*:\s*(?:0?\.\d+)/s)
    expect(stylesheet).not.toContain('117.6vw')
    expect(stylesheet).not.toContain('117.6vh')
  })
})
