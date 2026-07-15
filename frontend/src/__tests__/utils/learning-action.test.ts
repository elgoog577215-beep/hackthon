import { describe, expect, it } from 'vitest'
import type { NextLearningAction } from '@/stores/learningProgress'
import enLocaleRaw from '../../../public/locales/en/translation.json?raw'
import {
  isWorkspaceTaskAction,
  learningActionPresentation,
} from '@/utils/learning-action'

const action = (overrides: Partial<NextLearningAction> = {}): NextLearningAction => ({
  action_id: 'a1',
  action_type: 'start_mastery_check',
  scope: 'learning_objective',
  target_id: 'lor1',
  target_revision_id: 'lor1',
  node_id: 'n1',
  reason_code: 'mastery_evidence_insufficient',
  evidence_refs: [],
  blocking: false,
  requires_confirmation: false,
  availability: 'available',
  task_ref: {
    kind: 'practice', object_id: '', task_revision_id: 'qr1', status: 'active',
    context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' }, return_node_id: 'n1',
  },
  ...overrides,
})

describe('learning action contract', () => {
  it('所有消费者共享动作和原因翻译键', () => {
    const translate = (key: string, fallback = '') => ({
      'courseWorkspace.continuity.actions.start_mastery_check': 'Take mastery check',
      'courseWorkspace.continuity.reasons.mastery_evidence_insufficient': 'Evidence is insufficient.',
    }[key] || fallback)

    expect(learningActionPresentation(action(), translate)).toEqual({
      label: 'Take mastery check',
      reason: 'Evidence is insufficient.',
    })
  })

  it('任务路由只读取 task_ref.kind，不从 scope 猜测', () => {
    expect(isWorkspaceTaskAction(action())).toBe(true)
    expect(isWorkspaceTaskAction(action({
      action_type: 'start_objective',
      scope: 'practice_attempt',
      task_ref: { ...action().task_ref!, kind: 'reading' },
    }))).toBe(false)
  })

  it('实际英文词条覆盖当前主动作和原因码', () => {
    const messages = JSON.parse(enLocaleRaw)
    const translate = (key: string, fallback = '') => {
      let current: any = messages
      for (const segment of key.split('.')) current = current?.[segment]
      return typeof current === 'string' ? current : fallback
    }

    expect(learningActionPresentation(action(), translate)).toEqual({
      label: 'Take mastery check',
      reason: 'Current evidence is insufficient to verify mastery.',
    })
  })
})
