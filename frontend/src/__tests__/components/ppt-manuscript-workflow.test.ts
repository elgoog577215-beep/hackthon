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
    expect(failure.text()).toContain('文书输入已自动压缩')
    expect(failure.text()).toContain('保留全部讲稿块')
    expect(failure.text()).toContain('story_ai_batch_request_budget_exceeded')
    expect(wrapper.get('[data-testid="generate-ppt-manuscript"]').text()).toContain('重新生成 PPT 文书')

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
    expect(wrapper.text()).toContain('确认文书后解锁')
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(false)
  })
})
