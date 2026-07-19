import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FeedbackReviewBlock from '@/components/FeedbackReviewBlock.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const global = {
  stubs: {
    MarkdownRenderer: {
      name: 'MarkdownRenderer',
      props: ['content', 'searchWords'],
      template: '<div class="markdown-renderer">{{ content }}</div>',
    },
  },
}

describe('FeedbackReviewBlock', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  afterEach(async () => {
    await setLocale('zh')
    vi.unstubAllGlobals()
  })

  it('把旧课程的粗体任务标题编译成默认折叠的逐项核对', () => {
    const content = [
      '**任务1 答案方向**：',
      '1. `N^2` 对应第二种情况。',
      '',
      '**任务2 反馈**：',
      '- 比值逐渐趋近 4。',
      '',
      '**任务3 评价标准**：',
      '- 增大样本后再次核对。',
    ].join('\n')

    const wrapper = mount(FeedbackReviewBlock, { props: { content }, global })
    const details = wrapper.findAll('details')

    expect(details).toHaveLength(3)
    expect(details.every(section => section.attributes('open') === undefined)).toBe(true)
    expect(wrapper.findAll('.feedback-review__copy strong').map(node => node.text())).toEqual([
      '任务1 答案方向', '任务2 反馈', '任务3 评价标准',
    ])
  })

  it('短的单段核对直接呈现，不增加折叠交互', () => {
    const wrapper = mount(FeedbackReviewBlock, {
      props: { content: '结论正确，请继续下一节。' },
      global,
    })

    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.get('.markdown-renderer').text()).toBe('结论正确，请继续下一节。')
  })

  it('只把旧反馈中的数学内联代码转成公式边界', () => {
    const wrapper = mount(FeedbackReviewBlock, {
      props: { content: '比较 `N^2` 与 `log_2(N)`，运行 `npm test`。' },
      global,
    })
    const renderer = wrapper.findComponent({ name: 'MarkdownRenderer' })

    expect(renderer.props('content')).toBe('比较 $N^2$ 与 $log_2(N)$，运行 `npm test`。')
  })

  it('保留搜索高亮契约，并在英文模式下不泄露中文或原始 key', async () => {
    await setLocale('en')
    const wrapper = mount(FeedbackReviewBlock, {
      props: {
        content: '**Task**',
        searchWords: ['Task'],
        structure: {
          schema_version: 'course_feedback_v1',
          mode: 'static_reference',
          sections: [
            { section_id: 'task-1', title: 'Task 1', markdown: 'Reference', summary: 'Check the result', collapsed_by_default: true },
            { section_id: 'task-2', title: 'Task 2', markdown: 'Criteria', summary: 'Review the criteria', collapsed_by_default: true },
          ],
        },
      },
      global,
    })

    expect(wrapper.get('.feedback-review__intro').text()).toContain('Review item by item')
    expect(wrapper.get('.feedback-review__intro').text()).not.toContain('逐项核对')
    expect(wrapper.get('.expand-label').text()).toBe('Show reference')
    expect(wrapper.text()).not.toContain('courseBlocks.feedbackReview')
    expect(wrapper.findAllComponents({ name: 'MarkdownRenderer' })[0]?.props('searchWords')).toEqual(['Task'])
  })
})
