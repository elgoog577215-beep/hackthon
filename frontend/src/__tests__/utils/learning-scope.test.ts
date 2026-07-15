import { describe, expect, it } from 'vitest'
import {
  isStartableLearningObjective,
  practiceScopeKind,
  resolveLearningScopeNode,
} from '../../utils/learning-scope'
import type { LearningObjectiveProgress } from '../../stores/learningProgress'

const objective = (overrides: Partial<LearningObjectiveProgress> = {}): LearningObjectiveProgress => ({
  objective_id: 'objective-1',
  objective_revision_id: 'objective-revision-1',
  statement: '理解状态机的基本转换',
  node_id: 'node-1',
  node_name: '状态机基础',
  course_version_id: 'cv1',
  reading_status: 'in_progress',
  mastery_status: 'not_checked',
  content_block_ids: [],
  question_revision_ids: [],
  criterion_revision_ids: [],
  criterion_states: [],
  evidence_event_ids: [],
  has_historical_evidence: false,
  ...overrides,
})

describe('resolveLearningScopeNode', () => {
  it('优先使用当前课程内用户显式选择的节点', () => {
    const nodes = [
      { node_id: 'node-1', node_name: '状态机基础' },
      { node_id: 'node-2', node_name: '状态迁移' },
    ]

    expect(resolveLearningScopeNode(nodes[1], objective(), nodes)).toEqual(nodes[1])
  })

  it('旧节点未选择时回退到 LearningRuntime 当前目标', () => {
    const nodes = [{ node_id: 'node-1', node_name: '状态机基础' }]

    expect(resolveLearningScopeNode(null, objective(), nodes)).toEqual(nodes[0])
  })

  it('一级章节选择不覆盖运行时当前目标', () => {
    const chapter = { node_id: 'chapter-1', node_name: '第一章', node_level: 1 }
    const target = { node_id: 'node-1', node_name: '状态机基础', node_level: 2 }

    expect(resolveLearningScopeNode(chapter, objective(), [chapter, target])).toEqual(target)
  })

  it('运行时目标尚未进入课程节点列表时仍保留正式目标身份', () => {
    expect(resolveLearningScopeNode(null, objective(), [])).toEqual({
      node_id: 'node-1',
      node_name: '状态机基础',
    })
  })
})

describe('practiceScopeKind', () => {
  it.each([
    ['node', 'objective'],
    ['all', 'course'],
    ['final', 'final'],
  ] as const)('把 %s 映射为 %s 展示范围', (scope, expected) => {
    expect(practiceScopeKind(scope)).toBe(expected)
  })
})

describe('isStartableLearningObjective', () => {
  it('一级章节只负责导航，不触发学习目标开始事件', () => {
    expect(isStartableLearningObjective({
      node_id: 'chapter-1',
      node_name: '第一章',
      node_level: 1,
      node_content: '章节导语',
    })).toBe(false)
  })

  it('有正文的二级学习目标可以触发开始事件', () => {
    expect(isStartableLearningObjective({
      node_id: 'node-1',
      node_name: '状态机基础',
      node_level: 2,
      node_content: '这是一段可学习的正式正文。',
    })).toBe(true)
  })

  it('没有正文的二级节点不应被记录为已经开始学习', () => {
    expect(isStartableLearningObjective({
      node_id: 'node-1',
      node_name: '状态机基础',
      node_level: 2,
      node_content: '   ',
    })).toBe(false)
  })
})
