import { describe, expect, it } from 'vitest'
import { courseCoverPreset, formatCourseTitle } from '@/utils/course-presentation'

describe('course presentation', () => {
  it('wraps every non-empty course title in exactly one pair of book-title marks', () => {
    expect(formatCourseTitle('Unity 游戏编程进阶实战')).toBe('《Unity 游戏编程进阶实战》')
    expect(formatCourseTitle('《微积分》')).toBe('《微积分》')
    expect(formatCourseTitle(' 《《线性代数：理论与应用》》 ')).toBe('《线性代数：理论与应用》')
    expect(formatCourseTitle('')).toBe('')
  })

  it.each([
    ['机器学习：原理、算法与实践', 'ai'],
    ['Unity 游戏编程进阶实战', 'programming'],
    ['线性代数：理论与应用', 'mathematics'],
    ['大学物理', 'science'],
    ['中国文学史', 'humanities'],
    ['职业发展', 'general'],
  ])('maps %s to the %s preset cover', (title, preset) => {
    expect(courseCoverPreset(title)).toBe(preset)
  })
})
