import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock mobile tools', () => {
  it('opens and closes the secondary tools panel from the More action', async () => {
    const wrapper = mount(LearningDock, {
      props: { location: 'C语言 · 指针', toolbar: true, placement: 'bottom' },
      slots: {
        'mobile-more': '<button type="button" class="learning-dock__more-action" data-more-domain="overview">学习概况</button>',
      },
    })

    expect(wrapper.find('.learning-dock__more').exists()).toBe(true)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    await wrapper.get('.learning-dock__more').trigger('click')
    await flushPromises()
    expect(wrapper.get('.learning-dock__more').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[role="dialog"]').text()).toContain('学习概况')

    await wrapper.get('[data-more-domain="overview"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.learning-dock__more').attributes('aria-expanded')).toBe('false')
  })

  it('closes the secondary tools panel with Escape and returns focus to More', async () => {
    const wrapper = mount(LearningDock, {
      attachTo: document.body,
      props: { location: 'C语言 · 指针', toolbar: true, placement: 'bottom' },
      slots: {
        'mobile-more': '<button type="button" class="learning-dock__more-action">课程目录</button>',
      },
    })

    const moreButton = wrapper.get('.learning-dock__more')
    await moreButton.trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(moreButton.element)
    wrapper.unmount()
  })

  it('keeps the current desktop tool actions when no mobile overflow is needed', () => {
    const wrapper = mount(LearningDock, {
      props: { location: 'C语言 · 指针', toolbar: true, placement: 'bottom' },
    })

    expect(wrapper.find('.learning-dock__more').exists()).toBe(false)
    expect(wrapper.findAll('.learning-dock__actions [data-domain]').map(button => button.attributes('data-domain'))).toEqual([
      'reading', 'question-book', 'mistakes', 'overview', 'knowledge-library', 'notebook', 'assistant',
    ])
  })
})
