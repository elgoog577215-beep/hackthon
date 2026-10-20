import { mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import HandoutTypeSelect from '@/components/HandoutTypeSelect.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  await setLocale('zh')
})

it('选择已知类型后仍可回到原自定义类型，不自动改写未知类型', async () => {
  const wrapper = mount(HandoutTypeSelect, { props: { modelValue: '史料辨读', originalType: '史料辨读', currentLabel: '史料辨读' } })
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('史料辨读')
  await wrapper.get('select').setValue('guiding_question')
  await wrapper.setProps({ modelValue: 'guiding_question' })
  expect(wrapper.text()).toContain('验证方法')
  expect(wrapper.find('option[value="史料辨读"]').exists()).toBe(true)
  await wrapper.get('select').setValue('史料辨读')
  expect(wrapper.emitted('update:modelValue')).toEqual([['guiding_question'], ['史料辨读']])
  wrapper.unmount()
})

it('英文选择器保留三类分组和两种提问职责', async () => {
  await setLocale('en')
  const wrapper = mount(HandoutTypeSelect, { props: { modelValue: 'review_question' } })
  expect(wrapper.findAll('optgroup').map(item => item.attributes('label'))).toEqual(['Explanation', 'Practice', 'Question'])
  expect(wrapper.text()).toContain('Specific prior knowledge')
  expect(wrapper.text()).toContain('Guiding question')
  wrapper.unmount()
})
