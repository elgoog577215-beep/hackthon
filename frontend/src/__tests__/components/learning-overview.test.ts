import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import LearningStats from '@/components/LearningStats.vue'
import { useCourseStore } from '@/stores/course'
import { useLearnerModelStore } from '@/stores/learnerModel'
import { useLearningProgressStore } from '@/stores/learningProgress'

function mountOverview() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const courseStore = useCourseStore()
  const modelStore = useLearnerModelStore()
  const progressStore = useLearningProgressStore()
  const node = {
    node_id: 'node-1', node_name: '极限定义', node_level: 2,
    parent_node_id: 'chapter-1', node_content: '课程正文',
  } as any
  courseStore.currentCourseId = 'course-1'
  courseStore.nodes = [node]
  courseStore.currentNode = node
  modelStore.model = {
    schema_version: 'learner_model_v1', model_revision_id: 'lmr_acceptance_1',
    user_id: 'u1', course_id: 'course-1', course_version_id: 'cv1',
    source_revision_vector: { events_revision: 'levr_1' }, observed_at: '2026-07-14T00:00:00Z',
    data_sufficiency: {
      level: 'moderate', formal_evidence_count: 2, total_evidence_count: 3,
      covered_objective_count: 1, reason_code: 'sufficient_for_bounded_inference',
    },
    summary: {
      total_objectives: 2, started_objectives: 2, learned_objectives: 1,
      mastered_objectives: 1, needs_attention_objectives: 1,
      formal_evidence_count: 2, active_record_count: 1,
    },
    objectives: [{
      objective_id: 'lo_1', objective_revision_id: 'lor_1', node_id: 'node-1',
      node_name: '极限定义', statement: '能够解释极限的直观含义',
      reading_status: 'learned', mastery_status: 'needs_review', has_historical_evidence: false,
      confidence: 'high', support_need: {
        status: 'needs_support', reason_code: 'repeated_independent_failure',
        confidence: 'high', evidence_refs: ['attempt-1', 'attempt-2'],
      },
      evidence_refs: [], observed_at: '2026-07-14T00:00:00Z', valid_until: '2026-08-13T00:00:00Z',
    }],
    strengths: [],
    needs_attention: [{
      objective_id: 'lo_1', objective_revision_id: 'lor_1', node_id: 'node-1',
      node_name: '极限定义', reason_code: 'repeated_independent_failure', confidence: 'high',
      evidence_refs: ['attempt-1', 'attempt-2'], observed_at: '2026-07-14T00:00:00Z',
      valid_until: '2026-08-13T00:00:00Z',
    }],
    self_reports: [],
    evidence_catalog: [
      { source_id: 'attempt-1', type: 'practice_attempt', status: 'graded' },
      { source_id: 'attempt-2', type: 'practice_attempt', status: 'graded' },
    ],
    model_policy: {
      deterministic: true, ai_writable: false, reading_is_mastery: false,
      legacy_profile_included: false, learning_os_included: false,
    },
  }
  progressStore.runtime = {
    learner_model: null,
    continuation: {
      primary_action: {
        action_type: 'start_mastery_check', reason_code: 'mastery_needs_review',
        availability: 'available', node_id: 'node-1',
      },
    },
  } as any
  const loadModel = vi.spyOn(modelStore, 'load').mockResolvedValue(modelStore.model)
  const loadRuntime = vi.spyOn(progressStore, 'loadRuntime').mockResolvedValue(progressStore.runtime)

  const wrapper = mount(LearningStats, { global: { plugins: [pinia] } })
  return { wrapper, loadModel, loadRuntime }
}

describe('LearningStats formal learning overview', () => {
  it('只呈现正式进度、证据与统一下一步，不显示伪画像', async () => {
    const { wrapper, loadModel, loadRuntime } = mountOverview()
    await flushPromises()

    expect(wrapper.text()).toContain('学习概况')
    expect(wrapper.text()).toContain('阅读与掌握')
    expect(wrapper.text()).toContain('多次独立练习尚未通过')
    expect(wrapper.text()).toContain('正式学习证据')
    expect(wrapper.text()).toContain('完成掌握检查')
    expect(wrapper.text()).toContain('阅读不等于掌握')
    expect(wrapper.text()).not.toContain('综合评分')
    expect(wrapper.text()).not.toContain('学习风格')
    expect(wrapper.text()).not.toContain('最佳学习时段')
    expect(loadModel).toHaveBeenCalledWith('course-1')
    expect(loadRuntime).toHaveBeenCalledWith('course-1', 'node-1')
  })

  it('不会把过期模型结论继续展示为当前待巩固项', async () => {
    const { wrapper } = mountOverview()
    const modelStore = useLearnerModelStore()
    modelStore.model!.needs_attention = [{
      objective_id: 'obj-expired', objective_revision_id: 'objr-expired', node_id: 'node-expired',
      node_name: '旧薄弱点', reason_code: 'repeated_independent_failure', confidence: 'high',
      evidence_refs: ['attempt-old'], valid_until: '2000-01-01T00:00:00+00:00',
    }]
    modelStore.model!.summary.needs_attention_objectives = 1
    await flushPromises()

    expect(wrapper.text()).not.toContain('旧薄弱点')
    expect(wrapper.find('.metric-grid .metric:nth-child(3) strong').text()).toBe('0')
  })
})
