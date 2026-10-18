import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentOwnedCourseList from '@/components/StudentOwnedCourseList.vue'
import StudentCreateCourseLink from '@/components/StudentCreateCourseLink.vue'

const { list } = vi.hoisted(() => ({ list:vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi:{ list } }))

beforeEach(() => { list.mockReset().mockResolvedValue([]) })
const course = { id:'own-a', title:'自建课程', purpose:'systematic' as const, status:'completed', task_id:'job-a', updated_at:'' }
async function routing() {
  const router = createRouter({ history:createMemoryHistory(), routes:[{ path:'/:pathMatch(.*)*', component:{ template:'<div />' } }] })
  await router.push('/study')
  return router
}

describe('student course creation navigation', () => {
  it('opens the one existing creator URL and disables the entry without an identity', async () => {
    const router = await routing()
    const wrapper = mount(StudentCreateCourseLink, { global:{ plugins:[router] } })
    await wrapper.get('a').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/study?create=1')
    await wrapper.setProps({ disabled:true })
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('reuses a provided course list and links to the owned material, without a second read', async () => {
    const router = await routing()
    const wrapper = mount(StudentOwnedCourseList, { props:{ userId:'student-a', materials:[course] }, global:{ plugins:[router] } })
    await flushPromises()
    expect(list).not.toHaveBeenCalled()
    expect(wrapper.get('a').attributes('href')).toBe('/study/own-a')
    await wrapper.setProps({ userId:'' })
    expect(wrapper.find('a').exists()).toBe(false)
    await wrapper.setProps({ userId:'student-b' })
    expect(wrapper.find('a').exists()).toBe(false)
    await wrapper.setProps({ materials:[{ ...course, id:'own-b', title:'B 的自建课程' }] })
    expect(wrapper.get('a').attributes('href')).toBe('/study/own-b')
    wrapper.unmount()
  })

  it('aborts the previous identity read and discards its late private course response', async () => {
    const router = await routing()
    let complete!: (value: unknown) => void
    list.mockImplementationOnce(() => new Promise(resolve => { complete=resolve }))
      .mockResolvedValueOnce([{ ...course, id:'own-b', title:'B 的课程' }])
    const wrapper = mount(StudentOwnedCourseList, { props:{ userId:'student-a' }, global:{ plugins:[router] } })
    const signal = list.mock.calls[0]![0] as AbortSignal
    await wrapper.setProps({ userId:'student-b' }); await flushPromises()
    expect(signal.aborted).toBe(true)
    complete([course]); await flushPromises()
    expect(wrapper.text()).toContain('B 的课程')
    expect(wrapper.find('a[href="/study/own-a"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
