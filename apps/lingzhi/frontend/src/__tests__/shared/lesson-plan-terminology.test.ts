import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// 需求 6：教案页面用老师的课程口径称呼产物。
// 这里守的是词典本身——组件里的 t() fallback 只在词典加载失败时出现，
// 真实运行时读到的是这两份 JSON。
function locale(lang: 'zh' | 'en'): Record<string, any> {
  return JSON.parse(
    readFileSync(resolve(process.cwd(), `public/locales/${lang}/translation.json`), 'utf8'),
  )
}

const zh = locale('zh')
const en = locale('en')
const zhPlan = zh.courseGeneration.lessonPlan
const enPlan = en.courseGeneration.lessonPlan

describe('教案术语对齐老师课程口径', () => {
  it('两份词典都能被 JSON.parse 且教案命名空间键集一致', () => {
    expect(Object.keys(zhPlan).sort()).toEqual(Object.keys(enPlan).sort())
  })

  it('中文用教学大纲、教学设计、教学目标、学情分析', () => {
    expect(zhPlan.overallTab).toBe('教学大纲')
    expect(zhPlan.sectionsTab).toBe('教学设计')
    expect(zhPlan.overallObjectivesEyebrow).toBe('教学目标')
    expect(zhPlan.entryEyebrow).toBe('学情分析')
  })

  it('英文同步维护，不留旧说法', () => {
    expect(enPlan.overallTab).toBe('Syllabus')
    expect(enPlan.sectionsTab).toBe('Lesson design')
    expect(enPlan.overallObjectivesEyebrow).toBe('Learning objectives')
    expect(enPlan.entryEyebrow).toBe('Learner analysis')
  })

  it('教案命名空间不再出现被替换的旧术语', () => {
    const retired = ['总体教案', '分小节教案', '总体目标', '学习起点']
    const zhText = JSON.stringify(zhPlan)
    for (const term of retired) {
      expect(zhText).not.toContain(term)
    }
  })

  it('英文词典没有中文残留、没有原始 key 兜底', () => {
    const enText = JSON.stringify(enPlan)
    expect(enText).not.toMatch(/[一-鿿]/)
    expect(enText).not.toContain('courseGeneration.lessonPlan')
    // 全角问号是转码事故的典型信号，中英文词典都不应出现。
    expect(JSON.stringify(zhPlan)).not.toContain('�')
    expect(enText).not.toContain('�')
  })

  it('小节自身的章节编号是内容，不受术语改名影响', () => {
    // 「第一章第一节 矩阵复合」这类标题来自课程节点名，不走词典。
    expect(zhPlan.currentSection).toBe('当前小节')
    expect(enPlan.currentSection).toBe('Current section')
  })
})
