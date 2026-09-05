import { describe, expect, it } from 'vitest'
import { emptyLessonShellContent } from '@/utils/course-navigation'
import type { Node } from '@/stores/types'

const content = { node_id:'content-7', node_level:2, node_name:'结构化表达', node_content:'正式讲义' } as Node
const shell = { node_id:'lesson-7', node_level:1, node_name:'第7讲 结构化表达', node_content:'', children:[content] } as Node

describe('empty lesson covers in the reading projection', () => {
  it('resolves an empty compatibility cover to the original content node without changing its identity', () => {
    expect(emptyLessonShellContent(shell)).toBe(content)
    expect(shell.children).toEqual([content])
  })
  it('keeps meaningful parent content, objectives, blocks and historical chapter groups', () => {
    for (const patch of [
      {node_content:'导读'}, {learning_objective:'独立目标'},
      {course_blocks:[{block_id:'formal-block'}]}, {content_blocks:[{id:'legacy-block'}]},
      {node_name:'第二章 表达'}, {children:[content,{...content,node_id:'another'}]},
      {children:[{...content,children:[{...content,node_id:'nested'}]}]},
    ]) expect(emptyLessonShellContent({...shell,...patch} as Node)).toBeNull()
  })
})
