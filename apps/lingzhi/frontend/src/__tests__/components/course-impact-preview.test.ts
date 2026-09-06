/**
 * The scope preview must state how many sections a change touches, and the
 * number has to be the truth.
 *
 * The confirmation UI already listed affected *blocks*, which is the wrong unit
 * for a broad-intent request: a learner who says "this whole chapter is too
 * fast" needs to know how many sections move, not how many internal blocks. And
 * per the owner's decision (2026-08-12) the preview is the precondition for
 * letting the scope widen at all — so a wrong N is worse than no N, because it
 * is the only thing standing between a broad request and a broad edit.
 *
 * These tests therefore pin the count to the plan's own `affected_section_ids`
 * (the same field the domain uses when it applies the change) and check that
 * the sections are individually visible rather than hidden behind a number.
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseImpactPreview from '@/components/CourseImpactPreview.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'
import enMessages from '../../../public/locales/en/translation.json'

const sections = [
  { node_id: 'node-1', node_name: '1.1 向量的定义' },
  { node_id: 'node-2', node_name: '1.2 线性相关' },
  { node_id: 'node-3', node_name: '1.3 基与维数' },
]

function mountPreview(affected: string[], extra: Record<string, unknown> = {}) {
  return mount(CourseImpactPreview, {
    props: { affectedSectionIds: affected, sections, ...extra },
  })
}

describe('CourseImpactPreview', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('展示的 N 与实际受影响小节数一致', () => {
    expect(mountPreview(['node-1']).text()).toContain('将影响 1 个小节')
    expect(mountPreview(['node-1', 'node-2']).text()).toContain('将影响 2 个小节')
    expect(mountPreview(['node-1', 'node-2', 'node-3']).text()).toContain('将影响 3 个小节')
  })

  it('重复的小节 ID 不会把数字灌水', () => {
    // The domain derives affected sections from block ids, so duplicates are
    // possible; counting them twice would overstate the blast radius.
    const wrapper = mountPreview(['node-1', 'node-1', 'node-2'])

    expect(wrapper.text()).toContain('将影响 2 个小节')
    expect(wrapper.findAll('[data-testid="impact-section"]')).toHaveLength(2)
  })

  it('逐项列出受影响的小节，而不是只给一个数字', () => {
    const wrapper = mountPreview(['node-1', 'node-3'])
    const items = wrapper.findAll('[data-testid="impact-section"]')

    expect(items).toHaveLength(2)
    expect(items[0]!.text()).toContain('1.1 向量的定义')
    expect(items[1]!.text()).toContain('1.3 基与维数')
    expect(wrapper.text()).not.toContain('1.2 线性相关')
  })

  it('列出的条目数量始终等于展示的 N', () => {
    for (const affected of [['node-1'], ['node-1', 'node-2'], ['node-1', 'node-2', 'node-3']]) {
      const wrapper = mountPreview(affected)
      const shown = wrapper.findAll('[data-testid="impact-section"]').length
      expect(wrapper.text()).toContain(`将影响 ${shown} 个小节`)
      expect(shown).toBe(affected.length)
    }
  })

  it('课程目录里找不到的小节仍然计数并标注，不被悄悄丢掉', () => {
    // Silently dropping an unknown id would under-report the blast radius —
    // the one direction of error this preview must never make.
    const wrapper = mountPreview(['node-1', 'node-unknown'])

    expect(wrapper.text()).toContain('将影响 2 个小节')
    expect(wrapper.findAll('[data-testid="impact-section"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('node-unknown')
  })

  it('没有受影响小节时不展示预览', () => {
    expect(mountPreview([]).find('[data-testid="course-impact-preview"]').exists()).toBe(false)
  })

  it('说明确认之前不会发生任何写入', () => {
    expect(mountPreview(['node-1']).text()).toContain('确认前不会修改正式课程')
  })

  it('英文模式使用英文文案且数字一致', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('en')

    try {
      const wrapper = mountPreview(['node-1', 'node-2'])
      expect(wrapper.text()).toContain('Affects 2 sections')
      expect(wrapper.findAll('[data-testid="impact-section"]')).toHaveLength(2)
      expect(wrapper.text()).not.toMatch(/将影响|个小节/)
    } finally {
      await setLocale('zh')
      vi.unstubAllGlobals()
    }
  })

  it('英文单数使用 section 而不是 sections', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('en')

    try {
      expect(mountPreview(['node-1']).text()).toContain('Affects 1 section')
      expect(mountPreview(['node-1']).text()).not.toContain('1 sections')
    } finally {
      await setLocale('zh')
      vi.unstubAllGlobals()
    }
  })
})
