import { describe, expect, it } from 'vitest'
import {
  formatPracticeQuestionMarkdown,
  splitPracticeQuestionMarkdown,
} from '@/utils/practice-question-markdown'

describe('formatPracticeQuestionMarkdown', () => {
  it('keeps course Markdown structure, removes internal comments and separates the task', () => {
    const material = [
      '给定课程材料：',
      '<!-- BODY_START -->',
      '',
      '# Python 对象模型',
      '',
      '## 核心概念',
      '',
      '- 对象',
      '- 类型',
      '',
      '```python',
      'class Book:',
    ].join('\n')
    const task = '完成实现并提交测试依据。'

    const result = formatPracticeQuestionMarkdown({
      prompt: `${material}\n${task}`,
      input_materials: [material],
    })

    expect(result).not.toContain('BODY_START')
    expect(result).toContain('# Python 对象模型')
    expect(result).toContain('- 对象\n- 类型')
    expect(result).toContain('class Book:\n```')
    expect(result).toContain('## 作答任务\n\n完成实现并提交测试依据。')
  })

  it('separates the concise task from the collapsed reference material', () => {
    const material = [
      '给定课程材料：',
      '<!-- BODY_START -->',
      '# Python 对象模型',
      '',
      '课程正文。',
    ].join('\n')
    const sections = splitPracticeQuestionMarkdown({
      prompt: `${material}\n完成对象模型辨析。`,
      input_materials: [material],
    })

    expect(sections.task).toBe('完成对象模型辨析。')
    expect(sections.material).toBe('# Python 对象模型\n\n课程正文。')
  })

  it('keeps concise question stimulus visible and fences bare code', () => {
    const material = [
      '考虑以下代码：',
      '',
      'class Meta(type):',
      '    pass',
      '',
      'class Base(metaclass=Meta):',
      '    value = 10',
      '',
      'obj = Base()',
      '',
      '分析三个 type() 调用。',
    ].join('\n')
    const sections = splitPracticeQuestionMarkdown({
      prompt: `${material}\n基于上述代码选择正确选项。`,
      input_materials: [material],
    })

    expect(sections.task).toBe('基于上述代码选择正确选项。')
    expect(sections.material).toBe('')
    expect(sections.stimulus).toContain('```python\nclass Meta(type):')
    expect(sections.stimulus).toContain('obj = Base()\n```')
  })

  it('still closes an unterminated fence when structured materials are unavailable', () => {
    expect(formatPracticeQuestionMarkdown({
      prompt: '```python\nprint("hello")',
    })).toBe('```python\nprint("hello")\n```')
  })
})
