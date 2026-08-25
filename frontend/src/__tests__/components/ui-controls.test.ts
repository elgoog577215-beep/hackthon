import { mount } from '@vue/test-utils'
import { Grid2X2, List } from 'lucide-vue-next'
import { describe, expect, it } from 'vitest'
import UiSegmentedControl from '../../components/UiSegmentedControl.vue'
import UiSelectMenu from '../../components/UiSelectMenu.vue'

describe('shared refined controls', () => {
  it('分段控件用共享滑块表达当前项并只发送真实切换', async () => {
    const wrapper = mount(UiSegmentedControl, {
      props: {
        modelValue: 'list',
        accessibilityLabel: '课程展示方式',
        options: [
          { value: 'grid', label: '卡片', icon: Grid2X2 },
          { value: 'list', label: '列表', icon: List },
        ],
      },
    })

    expect(wrapper.attributes('style')).toContain('--ui-segment-count: 2')
    expect(wrapper.attributes('style')).toContain('--ui-segment-index: 1')
    expect(wrapper.get('button[title="列表"]').attributes('aria-pressed')).toBe('true')

    await wrapper.get('button[title="卡片"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['grid']])
  })

  it('选项菜单完整支持文案、数量、展开状态、选择和 Escape 恢复焦点', async () => {
    const wrapper = mount(UiSelectMenu, {
      attachTo: document.body,
      props: {
        modelValue: 'all',
        label: '状态',
        accessibilityLabel: '按备课状态筛选课程',
        options: [
          { value: 'all', label: '全部课程', count: 6 },
          { value: 'attention', label: '待处理', count: 2, hint: '需要教师确认' },
        ],
      },
    })
    const trigger = wrapper.get('.ui-select-menu__trigger')

    expect(trigger.text()).toContain('状态全部课程6')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')

    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-option-value="all"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-option-value="attention"]').text()).toContain('待处理需要教师确认2')

    await wrapper.get('[data-option-value="attention"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['attention']])
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })
})
