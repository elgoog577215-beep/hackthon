import { describe, expect, it } from 'vitest'
import { structuralLessonAliases } from '@/utils/course-navigation'
import type { Node } from '@/stores/types'

const section: Node = {
  node_id: 'section-7', parent_node_id: 'lesson-7', node_level: 2,
  node_name: '结构化表达', node_content: '完整讲义', node_type: 'original',
  generation_status: 'completed', generated_chars: 4,
}
const lesson: Node = {
  ...section, node_id: 'lesson-7', parent_node_id: 'root', node_level: 1,
  node_name: '第7讲 结构化表达', node_content: '', children: [section],
}

describe('连续讲义的历史层级兼容', () => {
  it('空讲次封面指向原正文 ID，保留树和正式正文对象', () => {
    const aliases = structuralLessonAliases([lesson])
    expect([...aliases]).toEqual([['lesson-7', 'section-7']])
    expect(lesson.children?.[0]).toBe(section)
    expect(section.node_content).toBe('完整讲义')
  })

  it.each([
    { node_name: '第一章 表达' },
    { node_content: '不能丢掉的导读' },
    { learning_objective: '独立的学习目标' },
    { course_blocks: [{ block_id: 'visual', section_id: 'lesson-7', status: 'final', payload: {} }] as Node['course_blocks'] },
    { generation_status: 'generating' },
    { generation_status: 'error' },
    { children: [section, { ...section, node_id: 'section-8' }] },
    { content_blocks: [{ block_id: 'intro', type: 'intro', title: '导读', content: '正式导读', order: 0 }] },
  ] as Partial<Node>[] )('保留有独立内容、状态或章节职责的父级 %j', patch => {
    expect(structuralLessonAliases([{ ...lesson, ...patch }]).size).toBe(0)
  })
})
