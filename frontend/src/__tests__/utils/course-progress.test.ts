import { describe, it, expect } from 'vitest'
import { taskProgressStep } from '@/utils/course-progress'

describe('生成进度显示的位置', () => {
  it('有位置时报到第几章第几节，而不是只报小节名', () => {
    expect(taskProgressStep({
      current_node_location: { label: '第2章第3节 · 不确定性原理' } as any,
      current_node_name: '不确定性原理',
    })).toBe('第2章第3节 · 不确定性原理')
  })

  it('没有位置时退回小节名，不让进度栏变空', () => {
    // 正文阶段之前与旧任务上都没有位置
    expect(taskProgressStep({ current_node_name: '波函数' })).toBe('波函数')
  })

  it('连小节名都没有时退回阶段文案', () => {
    expect(taskProgressStep({ message: '正在生成课程目录' })).toBe('正在生成课程目录')
  })

  it('位置为空串时不遮住小节名', () => {
    expect(taskProgressStep({
      current_node_location: { label: '   ' } as any,
      current_node_name: '波函数',
    })).toBe('波函数')
  })

  it('全空时用调用方给的兜底值', () => {
    expect(taskProgressStep(null, '上一次的进度')).toBe('上一次的进度')
    expect(taskProgressStep({}, '上一次的进度')).toBe('上一次的进度')
  })
})
