import { describe, expect, it } from 'vitest'

import { masteryAvailabilityCopy, practiceAvailabilityCopy } from '@/utils/course-availability'

const translate = (_key: string, fallback = '') => fallback

describe('course availability presentation', () => {
  it.each([
    ['declared_reading_only', '按设计只提供阅读'],
    ['legacy_reading_compatible', '旧版兼容课程'],
    ['required_practice_missing', '练习资产需要修复'],
    ['no_questions_in_scope', '当前范围没有正式练习'],
  ])('为 %s 展示明确的练习空状态', (reasonCode, expected) => {
    expect(practiceAvailabilityCopy(reasonCode, translate).title).toContain(expected)
  })

  it('明确说明纯阅读自检不等于系统掌握验证', () => {
    const copy = masteryAvailabilityCopy({ mode: 'reading_only', capabilities: {} }, translate)

    expect(copy?.title).toContain('阅读与自检')
    expect(copy?.body).toContain('不等于系统已经验证掌握')
  })

  it('标准课程掌握资产缺失时展示修复状态', () => {
    const copy = masteryAvailabilityCopy({
      mode: 'standard',
      capabilities: { mastery_evidence: { status: 'blocked' } },
    }, translate)

    expect(copy?.tone).toBe('warning')
    expect(copy?.title).toContain('需要修复')
  })
})
