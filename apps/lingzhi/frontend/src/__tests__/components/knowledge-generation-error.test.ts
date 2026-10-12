import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import View from '../../components/TeacherKnowledgeManager.vue'
import { setLocale } from '../../shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const mock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../utils/http', () => ({ default: mock }))

describe('knowledge generation failures', () => {
  it.each(['zh', 'en'] as const)('explains persisted budget failures in %s without starting a retry', async locale => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zh : en })))
    await setLocale(locale)
    mock.get.mockResolvedValue({ data: { title: '课程', enabled: true, can_edit: true, history: [], handouts: [],
      jobs: [{ id: 'failed-job', status: 'failed', error: { code: 'AIRequestBudgetExceeded', message: 'Generic retained historical error' }, partial_text: '' }] } })
    const wrapper = mount(View, { props: { courseId: 'c' } })
    await flushPromises()
    expect(wrapper.text()).toContain(locale === 'zh' ? '输入超过' : 'input exceeds')
    expect(wrapper.text()).toContain(locale === 'zh' ? '尚未调用模型' : 'No model request was sent')
    expect(wrapper.text()).not.toContain('Generic retained historical error')
    expect(mock.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
