import { describe, expect, it } from 'vitest'
import { resolveInitialPresentationScope } from '@/services/presentations'

describe('presentation launch scope', () => {
  it('学习页主入口按章节创建，课程库次入口默认整门课程', () => {
    expect(resolveInitialPresentationScope('chapter-2')).toBe('chapter')
    expect(resolveInitialPresentationScope(undefined)).toBe('course')
    expect(resolveInitialPresentationScope('')).toBe('course')
  })
})
