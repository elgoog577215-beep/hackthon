import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AITeacherSuggestion from '@/components/AITeacherSuggestion.vue'
import type { AISuggestion } from '@/stores/aiTeacher'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'
import enMessages from '../../../public/locales/en/translation.json'

const suggestion: AISuggestion = {
  trigger_id: 'ait-1',
  trigger_type: 'runtime_support',
  moment: 'section_completed',
  node_id: 'node-1',
  scope_ref: { node_id: 'node-1' },
  severity: 'high',
  eligible_action: 'explain_runtime_action',
  runtime_action: { action_type: 'resume_diagnostic' },
  dedupe_key: 'dk-1',
  runtime_revision_id: 'runtime-1',
}

function mountCard(value: AISuggestion | null = suggestion) {
  return mount(AITeacherSuggestion, { props: { suggestion: value } })
}

describe('AITeacherSuggestion', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('没有候选时不占位，也不消费打扰预算', () => {
    const wrapper = mountCard(null)

    expect(wrapper.find('[data-testid="ai-suggestion-card"]').exists()).toBe(false)
    expect(wrapper.emitted('shown')).toBeUndefined()
  })

  it('卡片出现时才上报已展示，用于消费预算', () => {
    const wrapper = mountCard()

    expect(wrapper.find('[data-testid="ai-suggestion-card"]').exists()).toBe(true)
    expect(wrapper.emitted('shown')?.[0]?.[0]).toMatchObject({ trigger_id: 'ait-1' })
  })

  it('把运行时动作翻译成学生能读懂的一句话', () => {
    expect(mountCard().text()).toContain('你有一次诊断没有完成')
    expect(
      mountCard({ ...suggestion, runtime_action: { action_type: 'start_due_review' } }).text(),
    ).toContain('有一项复习到期了')
    // An unknown action still renders something sensible instead of a raw code.
    const unknown = mountCard({ ...suggestion, runtime_action: { action_type: 'brand_new_action' } })
    expect(unknown.text()).toContain('有一个学习任务等待继续')
    expect(unknown.text()).not.toContain('brand_new_action')
  })

  it('说明确认前不会改变任何内容', () => {
    expect(mountCard().text()).toContain('确认前不会改变任何内容')
  })

  it('接受只请求解释，不直接执行动作', async () => {
    const wrapper = mountCard()

    await wrapper.get('.ai-suggestion__primary').trigger('click')

    expect(wrapper.emitted('accept')?.[0]?.[0]).toMatchObject({ trigger_id: 'ait-1' })
    expect(wrapper.emitted('decline')).toBeUndefined()
  })

  it('区分「暂时不要」与「不再提醒」两种拒绝', async () => {
    const wrapper = mountCard()

    await wrapper.get('.ai-suggestion__secondary').trigger('click')
    await wrapper.get('.ai-suggestion__quiet').trigger('click')

    const declines = wrapper.emitted('decline') || []
    expect(declines[0]?.[0]).toMatchObject({ reason: 'not_now' })
    expect(declines[1]?.[0]).toMatchObject({ reason: 'never' })
  })

  it('关闭按钮等价于暂时不要，而不是永久忽略', async () => {
    const wrapper = mountCard()

    await wrapper.get('.ai-suggestion__close').trigger('click')

    expect((wrapper.emitted('decline') || [])[0]?.[0]).toMatchObject({ reason: 'not_now' })
  })

  it('英文模式使用英文文案，没有中文残留', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('en')

    try {
      const wrapper = mountCard()
      const text = wrapper.text()
      expect(text).toContain('You have an unfinished diagnostic')
      expect(text).toContain('Nothing changes until you confirm')
      expect(text).toContain('Not now')
      expect(text).not.toMatch(/[一-鿿]/)
    } finally {
      await setLocale('zh')
      vi.unstubAllGlobals()
    }
  })
})
