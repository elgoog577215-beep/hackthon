import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningContinuityBar from '@/components/LearningContinuityBar.vue'
import type { LearningContinuationProjection } from '@/stores/learningProgress'

const projection = (actionType = 'complete_reading'): LearningContinuationProjection => ({
  schema_version: 'learning_continuation_v1', course_id: 'c1', course_version_id: 'cv1', user_id: 'u1', projection_revision_id: 'p1',
  chapter: { chapter_id: 'chapter-1', chapter_name: '第一章', chapter_index: 0, chapter_count: 2, objective_count: 1 },
  current_objective: null,
  progress: { learning: 'in_progress', mastery: 'not_checked', task_continuity: 'none' },
  entry_mode: actionType === 'view_chapter_result' ? 'chapter_closeout' : 'continue_learning',
  progression_contract: {}, risks: [],
  chapter_result: {
    state: actionType === 'view_chapter_result' ? 'covered_unverified' : 'in_progress', chapter_id: 'chapter-1',
    objectives: [{ objective_revision_id: 'lor1', node_name: '目标一', reading_status: 'learned', mastery_status: 'evidence_insufficient', evidence_strength: 'limited' }],
    residuals: {},
  },
  primary_action: {
    action_id: 'a1', action_type: actionType, scope: 'learning_objective', target_id: 'lor1', target_revision_id: 'lor1',
    node_id: 'n1', reason_code: 'reading_in_progress', evidence_refs: [], blocking: false, requires_confirmation: false, availability: 'available',
  },
  secondary_notices: [], version_conflicts: [],
})

describe('LearningContinuityBar', () => {
  it('只发出一个统一主要动作', async () => {
    const wrapper = mount(LearningContinuityBar, { props: { continuation: projection() } })

    expect(wrapper.findAll('.continuity__action')).toHaveLength(1)
    expect(wrapper.text()).toContain('标记本节已学完')
    await wrapper.find('.continuity__action').trigger('click')
    expect(wrapper.emitted('action')?.[0]?.[0]).toMatchObject({ action_type: 'complete_reading', node_id: 'n1' })
  })

  it('章节结果在同一状态带展开，不新建页面', async () => {
    const wrapper = mount(LearningContinuityBar, { props: { continuation: projection('view_chapter_result') } })

    await wrapper.find('.continuity__action').trigger('click')
    expect(wrapper.find('.continuity__result').exists()).toBe(true)
    expect(wrapper.text()).toContain('目标一')
    expect(wrapper.emitted('action')).toBeUndefined()
  })
})
