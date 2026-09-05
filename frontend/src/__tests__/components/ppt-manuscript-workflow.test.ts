import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PptManuscriptWorkflow from '@/components/PptManuscriptWorkflow.vue'

const emptyState = {
  generation_branch: 'manuscript_first',
  status: 'not_generated',
  source_state: 'current',
  confirmable: false,
  can_generate_ppt: false,
  manuscript: null,
}

describe('PptManuscriptWorkflow', () => {
  it('shows the lesson narrative and emits a synchronized page draft save', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第6章 微积分基本定理',
        state: {
          ...emptyState,
          revision: 'pptman-1',
          status: 'draft',
          confirmable: true,
          manuscript: {
            page_count: 1,
            narrative_brief: {
              central_question: '变化率怎样连接局部变化与整体累积？',
              learning_path: ['观察变化', '建立关系'],
              observable_checkpoints: ['能解释两者的联系'],
              time_budget_minutes: 18,
            },
            pages: [{
              page_id: 'page-1', page_number: 1, page_type: 'concept', layout_id: 'content-stack',
              title: '平均变化率刻画区间变化', visible_copy: ['平均变化率刻画区间变化', '先比较输入与输出的增量'],
              page_goal: '建立平均变化率', primary_claim: '两个增量的比值刻画区间变化',
              audience_question: '', audience_action: '', expected_response: '', observable_evidence: '',
              reveal_steps: ['输入增量', '输出增量', '形成比值'], transition: '从变化现象进入数量关系',
              composition_notes: '先呈现两个增量，再形成比值', teacher_locked: false,
              regions: [{ content_kind: 'title' }, { content_kind: 'body' }],
            }],
          },
        },
      },
    })

    expect(wrapper.get('[data-testid="ppt-narrative-brief"]').text()).toContain('变化率怎样连接局部变化与整体累积')
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('平均变化率连接两个增量')
    await wrapper.get('[data-testid="save-ppt-manuscript"]').trigger('click')

    expect(wrapper.emitted('save-manuscript')).toEqual([[expect.arrayContaining([
      expect.objectContaining({
        page_id: 'page-1',
        title: '平均变化率连接两个增量',
        visible_copy: ['平均变化率连接两个增量', '先比较输入与输出的增量'],
      }),
    ])]])
  })

  it('regenerates only selected eligible pages and removes a page when it is locked', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第1章 变化与累积',
        state: {
          ...emptyState,
          revision: 'pptman-1',
          status: 'draft',
          confirmable: true,
          manuscript: {
            page_count: 2,
            pages: [
              { page_id: 'page-1', page_number: 1, page_type: 'concept', layout_id: 'content-stack', title: '局部变化', visible_copy: ['局部变化'], reveal_steps: ['局部变化'], teacher_locked: false },
              { page_id: 'page-2', page_number: 2, page_type: 'summary', layout_id: 'chapter-recap', title: '本讲回顾', visible_copy: ['本讲回顾'], reveal_steps: ['本讲回顾'], teacher_locked: false },
            ],
          },
        },
      },
    })

    const selectors = wrapper.findAll('.ppt-manuscript-workflow__page-rail input')
    expect(selectors[0]!.attributes('disabled')).toBeUndefined()
    expect(selectors[1]!.attributes('disabled')).toBeDefined()
    await selectors[0]!.trigger('change')
    await wrapper.get('[data-testid="regenerate-selected-ppt-pages"]').trigger('click')
    expect(wrapper.emitted('regenerate-pages')).toEqual([[['page-1']]])

    await wrapper.findAll('.ppt-manuscript-workflow__lock')[0]!.trigger('click')
    expect(wrapper.get('[data-testid="regenerate-selected-ppt-pages"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="save-ppt-manuscript"]').attributes('disabled')).toBeUndefined()
  })

  it('offers source-impact regeneration while keeping the full rebuild path', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第1章 变化与累积',
        state: {
          ...emptyState,
          revision: 'pptman-stale',
          status: 'confirmed',
          source_state: 'stale',
          manuscript: {
            page_count: 1,
            pages: [{
              page_id: 'page-1', page_number: 1, page_type: 'concept', layout_id: 'content-stack',
              title: '局部变化', visible_copy: ['局部变化'], reveal_steps: ['局部变化'], teacher_locked: false,
            }],
          },
        },
      },
    })

    expect(wrapper.text()).toContain('只重新生成受影响页')
    expect(wrapper.get('[data-testid="generate-ppt-manuscript"]').text()).toContain('重新生成整份页面内容稿')
    await wrapper.get('[data-testid="regenerate-affected-ppt-pages"]').trigger('click')
    expect(wrapper.emitted('regenerate-pages')).toEqual([[[]]])
  })

  it('shows the handout, lesson-plan, and material sources for every page', () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第2讲 变化率',
        state: {
          ...emptyState,
          status: 'draft',
          confirmable: true,
          manuscript: {
            page_count: 1,
            pages: [{
              page_id: 'page-1', page_number: 1, title: '从平均变化率到瞬时变化率',
              source_script_block_ids: ['script-block-1'],
              source_section_ids: ['section-2'],
              source_material_evidence_ids: ['evidence-3'],
            }],
          },
        },
      },
    })

    const page = wrapper.get('.ppt-manuscript-workflow__page-copy')
    expect(page.text()).toContain('讲义来源块script-block-1')
    expect(page.text()).toContain('教案小节section-2')
    expect(page.text()).toContain('资料证据evidence-3')
  })

  it('explains an oversized request as a recoverable manuscript failure', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第1章 行列式',
        state: emptyState,
        failure: {
          code: 'story_ai_batch_request_budget_exceeded',
          message: '模型请求输入超过硬预算',
          retryable: true,
        },
      },
    })

    const failure = wrapper.get('[data-testid="ppt-manuscript-failure"]')
    expect(failure.text()).toContain('页面内容稿输入已自动压缩')
    expect(failure.text()).toContain('保留全部讲义块')
    expect(failure.text()).toContain('story_ai_batch_request_budget_exceeded')
    expect(wrapper.get('[data-testid="generate-ppt-manuscript"]').text()).toContain('重新生成页面内容稿')

    await wrapper.get('[data-testid="generate-ppt-manuscript"]').trigger('click')
    expect(wrapper.emitted('generate-manuscript')).toHaveLength(1)
  })

  it('keeps step two locked when manuscript generation fails', () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第1章 行列式',
        state: emptyState,
        failure: {
          code: 'story_title_assignment_unsatisfiable',
          message: 'titles unavailable',
          retryable: true,
        },
      },
    })

    expect(wrapper.text()).toContain('页面标题候选不足')
    expect(wrapper.text()).toContain('确认页面内容稿后解锁')
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(false)
  })
  it('saves a budget-only edit while blocking confirmation and keeps failed saves dirty', async () => {
    const state = { ...emptyState, revision: 'pacing-1', status: 'draft', manuscript: {
      teaching_content_contract_version: 'page_teaching_v2', page_count: 3,
      pacing: { schema_version: 'ppt_pacing_v1', max_physical_pages: 2, rationale: '留出课堂练习时间' },
      quality_issues: [{ code: 'ppt_pacing_budget_exceeded', message: '当前导出 3 页，超过预算 2 页。' }],
      pages: [],
    } }
    const wrapper = mount(PptManuscriptWorkflow, { props: { title: '执行方式', state } })
    expect(wrapper.get('[data-testid="confirm-ppt-manuscript"]').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(1)
    await wrapper.get('[data-testid="ppt-pacing-budget"]').setValue('4')
    await wrapper.get('[data-testid="save-ppt-manuscript"]').trigger('click')
    expect(wrapper.emitted('save-manuscript')).toEqual([[[], expect.objectContaining({ max_physical_pages: 4 })]])
    expect(state.manuscript.pacing.max_physical_pages).toBe(2)
    await wrapper.setProps({ error: '保存冲突，请重新载入' })
    expect((wrapper.get('[data-testid="ppt-pacing-budget"]').element as HTMLInputElement).value).toBe('4')
    expect(wrapper.get('[data-testid="save-ppt-manuscript"]').attributes('disabled')).toBeUndefined()
  })

})
