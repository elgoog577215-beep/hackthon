import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZjuCourseScheduleGrid, { type CourseScheduleSlot } from '@/components/ZjuCourseScheduleGrid.vue'

describe('ZjuCourseScheduleGrid', () => {
  it('把每个格子固定为 45 分钟，并允许任意选择多个时段', async () => {
    const wrapper = mount(ZjuCourseScheduleGrid, { props: { modelValue: [] } })

    expect(wrapper.text()).toContain('每格 45 分钟')
    expect(wrapper.findAll('.schedule-cell')).toHaveLength(7 * 13)
    const cells = wrapper.findAll('.schedule-cell')
    await cells[0]!.trigger('click')
    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue')?.at(-1)?.[0] as CourseScheduleSlot[] })
    await cells[1]!.trigger('click')
    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue')?.at(-1)?.[0] as CourseScheduleSlot[] })
    await cells[15]!.trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual([
      { weekday: 1, period: 1 },
      { weekday: 2, period: 1 },
      { weekday: 2, period: 3 },
    ])
  })
})
