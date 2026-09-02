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
  it('lets a teacher regenerate a draft before confirming it', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第6章 微积分基本定理',
        state: {
          ...emptyState,
          status: 'draft',
          confirmable: true,
          manuscript: { page_count: 1, pages: [] },
        },
      },
    })

    await wrapper.get('[data-testid="regenerate-ppt-manuscript"]').trigger('click')

    expect(wrapper.emitted('regenerate-manuscript')).toHaveLength(1)
    expect(wrapper.find('[data-testid="confirm-ppt-manuscript"]').exists()).toBe(true)
  })

  it('lets a teacher reopen and regenerate a confirmed manuscript', async () => {
    const wrapper = mount(PptManuscriptWorkflow, {
      props: {
        title: '第1章 变化与累积',
        state: {
          ...emptyState,
          status: 'confirmed',
          can_generate_ppt: true,
          manuscript: { page_count: 1, pages: [] },
        },
      },
    })

    await wrapper.get('[data-testid="regenerate-ppt-manuscript"]').trigger('click')

    expect(wrapper.emitted('regenerate-manuscript')).toHaveLength(1)
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(true)
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
})
