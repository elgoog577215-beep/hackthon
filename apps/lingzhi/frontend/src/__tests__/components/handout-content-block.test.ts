import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HandoutContentBlock from '@/components/HandoutContentBlock.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  await setLocale('zh')
})

describe('HandoutContentBlock', () => {
  it('关联解答默认收起，普通例题保留完整解法', async () => {
    const wrapper = mount(HandoutContentBlock, { props: { contentType: 'answer', label: '解答', title: '核对差商', answerTo: 'exercise-1' }, slots: { default: '完整解答保留在同一正文中' } })
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('summary').text()).toContain('展开解答')
    expect(wrapper.get('.handout-block__body').text()).toContain('完整解答')
    await wrapper.setProps({ contentType: 'example', answerTo: '' })
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.classes()).toContain('handout-block--example')
  })

  it('流式和未完成草稿的解答始终可见，自定义类型不丢失', async () => {
    const wrapper = mount(HandoutContentBlock, { props: { contentType: '思想实验反馈', answerTo: 'task', label: '思想实验反馈', title: '再想一步', streaming: true }, slots: { default: '刚收到的片段' } })
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.text()).toContain('刚收到的片段')
    expect(wrapper.text()).toContain('思想实验反馈')
    await wrapper.setProps({ streaming: false, collapseAnswer: false })
    expect(wrapper.find('details').exists()).toBe(false)
    await wrapper.setProps({ collapseAnswer: true })
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.attributes('data-answer-to')).toBe('task')
  })

  it('英文显示对应的答案操作', async () => {
    await setLocale('en')
    const wrapper = mount(HandoutContentBlock, { props: { contentType: 'answer', answerTo: 'q', title: 'Check your reasoning' } })
    expect(wrapper.get('summary').text()).toContain('Show answer')
    expect(wrapper.get('summary').text()).toContain('Hide answer')
    expect(wrapper.text()).not.toContain('展开解答')
  })
})
