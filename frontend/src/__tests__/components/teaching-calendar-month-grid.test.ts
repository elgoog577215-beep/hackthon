import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import TeachingCalendarMonthGrid from '@/components/TeachingCalendarMonthGrid.vue'
import type { ClassSession } from '@/stores/teachingCalendar'

const ElPopoverStub = defineComponent({
  template: '<div class="popover-stub"><slot name="reference"/><div class="popover-content"><slot/></div></div>',
})

const session: ClassSession = {
  session_id: 'session-1',
  course_id: 'course-1',
  course_title: '高等数学：导数与极值判定',
  sequence: 1,
  date: '2026-08-20',
  start_time: '13:30:00',
  end_time: '15:05:00',
  content_summary: '1.1 导数符号与极值判定',
  requirements: '',
  location: '紫金港西2-105',
  teacher_name: '项老师',
  teaching_type: '理论课',
  group_code: '',
  notes: '',
  status: 'scheduled',
  source: 'outline',
}

describe('TeachingCalendarMonthGrid', () => {
  it('uses an anchored structured popover instead of a native title tooltip', async () => {
    const wrapper = mount(TeachingCalendarMonthGrid, {
      props: { month: '2026-08-01', sessions: [session], showCourse: true },
      global: { components: { ElPopover: ElPopoverStub } },
    })

    const event = wrapper.get('button.event')
    expect(event.attributes('title')).toBeUndefined()
    expect(event.attributes('aria-label')).toContain('高等数学：导数与极值判定')
    expect(wrapper.get('.popover-content').text()).toContain('第 1 课次')
    expect(wrapper.get('.popover-content').text()).toContain('2026/08/20 · 13:30–15:05')
    expect(wrapper.get('.popover-content').text()).toContain('紫金港西2-105')

    await event.trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([session])
  })
})
