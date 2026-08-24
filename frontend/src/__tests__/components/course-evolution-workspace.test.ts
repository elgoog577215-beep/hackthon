import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'

describe('CourseEvolutionWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
  })

  it('把课程调整放进独立工作区并保留严格范围上下文', async () => {
    const pinia = createPinia()
    const wrapper = mount(CourseEvolutionWorkspace, {
      attachTo: document.body,
      props: {
        modelValue: true,
        courseId: 'course-1',
        courseTitle: '大学物理',
        sectionId: 'section-1',
        sectionTitle: '第一章 质点力学基础',
      },
      global: {
        plugins: [pinia],
        stubs: {
          Teleport: true,
          Transition: false,
          CourseEvolutionPanel: {
            props: ['courseId', 'sectionId', 'focusPlanId', 'surface', 'showHeading'],
            template: '<div class="evolution-workspace-stub" :data-course-id="courseId" :data-section-id="sectionId" :data-surface="surface" :data-heading="showHeading" />',
          },
        },
      },
    })

    expect(wrapper.get('.course-adjustment-title').text()).toContain('全课联动修改')
    expect(wrapper.get('.course-adjustment-context').text()).toContain('大学物理 · 第一章 质点力学基础')
    expect(wrapper.findAll('.course-change-asset')).toHaveLength(5)
    expect(wrapper.get('.course-change-ai-empty').text()).toContain('不用先选“内容修改”还是“结构修改”')
    expect(wrapper.text()).not.toContain('范围是硬边界，AI 不会自行扩大')
    expect(wrapper.get('.evolution-workspace-stub').attributes()).toMatchObject({
      'data-course-id': 'course-1',
      'data-section-id': 'section-1',
      'data-surface': 'workspace',
      'data-heading': 'false',
    })

    await wrapper.get('.course-adjustment-close').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    wrapper.unmount()
  })

  it('同时展示五类影响、老师原话、AI 理解和结构确认点', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.applyPayload('course-1', {
      course_evolution_plans: [{
        change_set_id: 'change-1',
        hypothesis_id: 'hypothesis-1',
        evidence_ids: [],
        operations: [],
        allowed_scopes: ['current', 'current_and_next'],
        impact_summary: {},
        expected_effect: '',
        status: 'pending',
        effect_evaluation: {},
        teacher_change_planning: {
          schema_version: 'course_change_plan_v1',
          scenario_matrix_version: 'course_change_scenario_matrix_v1',
          plan_id: 'teacher-change-1',
          course_id: 'course-1',
          intent: {
            schema_version: 'course_change_intent_v1',
            intent_id: 'intent-1',
            course_id: 'course-1',
            raw_request: '第三章太散了，重新整理，但原来的项目案例要保留。',
            interpreted_goal: '将第三章拆分为原理与实践，保留并重新绑定原项目案例。',
            scope_hint: {},
            hard_constraints: [],
            soft_preferences: [],
            protected_requirements: ['保留原项目案例'],
            source_refs: [],
            signals: [],
            assumptions: [],
            blocking_questions: [],
            can_proceed_without_clarification: true,
            interpretation_revision: 'intent-2',
          },
          base_revision_vector: { blueprint: 'blueprint-1' },
          execution_strategies: ['structural_regeneration', 'semantic_impact'],
          strategy_status: 'resolved',
          scenario_tags: [],
          structural_operations: [{ operation_type: 'SPLIT_OUTLINE_NODE' }],
          unit_migrations: [
            { migration_id: 'm1', asset_type: 'outline', unit_type: 'section', source_unit_ids: ['s1'], target_unit_ids: ['s2'], disposition: 'rewrite_partial', reason: '结构变化', confidence: 0.9, requires_review: false, candidate_status: 'ready' },
            { migration_id: 'm2', asset_type: 'teacher_script', unit_type: 'block', source_unit_ids: ['b1'], target_unit_ids: ['b2'], disposition: 'regenerate', reason: '叙事变化', confidence: 0.8, requires_review: false, candidate_status: 'ready' },
            { migration_id: 'm3', asset_type: 'slide_deck', unit_type: 'slide', source_unit_ids: ['p1'], target_unit_ids: ['p2'], disposition: 'regenerate', reason: '来源变化', confidence: 0.8, requires_review: false, candidate_status: 'ready' },
          ],
          structure_review_status: 'pending',
          status: 'impact_ready',
          supersedes_plan_id: 'teacher-change-0',
          replan_reasons: ['影响扫描发现章节边界也需要调整。'],
          created_at: '2026-08-25T10:00:00Z',
          updated_at: '2026-08-25T10:05:00Z',
        },
      }],
    })

    const wrapper = mount(CourseEvolutionWorkspace, {
      attachTo: document.body,
      props: { modelValue: true, courseId: 'course-1', focusPlanId: 'change-1' },
      global: {
        plugins: [pinia],
        stubs: {
          Teleport: true,
          Transition: false,
          CourseEvolutionPanel: { template: '<div class="evolution-workspace-stub" />' },
        },
      },
    })

    expect(wrapper.get('.course-change-impact').text()).toContain('课程大纲')
    expect(wrapper.get('.course-change-impact').text()).toContain('PPT')
    expect(wrapper.get('.course-change-ai').text()).toContain('第三章太散了')
    expect(wrapper.get('.course-change-ai').text()).toContain('将第三章拆分为原理与实践')
    expect(wrapper.get('.course-change-ai').text()).toContain('已根据新证据升级方案')
    expect(wrapper.get('.course-change-checkpoint').text()).toContain('等待确认新结构')
    wrapper.unmount()
  })
})
