import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PresentationPreview from '@/components/presentation/PresentationPreview.vue'
import { aggregatePresentationMeasurements } from '@/components/presentation/presentationPreviewMeasurement'
import type { PresentationSlide } from '@/types/presentation'

const slide: PresentationSlide = {
  slide_id: 'slide-1', position: 0, layout_id: 'L04', status: 'ready', title: '指针与地址',
  subtitle: '一个变量如何引用另一个变量', key_message: '指针保存内存地址', speaker_notes: '先画内存格。',
  blocks: [{ block_id: 'b1', type: 'code', title: '代码', content: 'int *p = &x;', items: [], metadata: {} }],
  source_refs: { section_ids: ['s1'], block_ids: ['b1'], block_revision_ids: ['br1'], objective_ids: ['o1'], asset_ids: [] },
  quality: { issues: [], capacity: {} },
}

const rect = (left: number, top: number, width: number, height: number): DOMRect => ({
  x: left, y: top, left, top, width, height,
  right: left + width, bottom: top + height,
  toJSON: () => ({}),
} as DOMRect)

const setBox = (element: HTMLElement, values: { clientHeight: number; scrollHeight: number; clientWidth: number; scrollWidth: number }) => {
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(element, key, { configurable: true, value })
  }
}

describe('PresentationPreview', () => {
  it('仅接受指定沙箱 iframe 的 opaque-origin、同 deck/revision 选页消息', async () => {
    const wrapper = mount(PresentationPreview, {
      props: { deckId: 'deck-1', revisionId: 'rev-1', revisionChecksum: 'checksum-1', slides: [slide], selectedSlideId: 'slide-1' },
      attachTo: document.body,
    })
    const frame = wrapper.get('iframe').element as HTMLIFrameElement
    const validData = {
      version: 'presentation-preview/v1', type: 'slide:selected', deck_id: 'deck-1', revision_id: 'rev-1', revision_checksum: 'checksum-1', slide_id: 'slide-1', payload: {},
    }

    window.dispatchEvent(new MessageEvent('message', { data: validData, origin: 'null', source: window }))
    window.dispatchEvent(new MessageEvent('message', { data: { ...validData, revision_id: 'rev-other' }, origin: 'null', source: frame.contentWindow }))
    window.dispatchEvent(new MessageEvent('message', { data: { ...validData, revision_checksum: 'checksum-other' }, origin: 'null', source: frame.contentWindow }))
    window.dispatchEvent(new MessageEvent('message', { data: validData, origin: 'https://untrusted.example', source: frame.contentWindow }))
    expect(wrapper.emitted('select')).toBeUndefined()

    window.dispatchEvent(new MessageEvent('message', { data: validData, origin: 'null', source: frame.contentWindow }))
    expect(wrapper.emitted('select')).toEqual([['slide-1']])
    wrapper.unmount()
  })

  it('课件源内容作为文本进入 srcdoc，不能插入脚本', () => {
    const hostile = { ...slide, title: '<script>window.hacked=true</script>' }
    const wrapper = mount(PresentationPreview, {
      props: { deckId: 'deck-1', revisionId: 'rev-1', revisionChecksum: 'checksum-1', slides: [hostile], selectedSlideId: 'slide-1' },
    })
    const srcdoc = wrapper.get('iframe').attributes('srcdoc') || ''
    expect(srcdoc).toContain('&lt;script&gt;window.hacked=true&lt;/script&gt;')
    expect(srcdoc).not.toContain('<script>window.hacked=true</script>')
    expect(wrapper.get('iframe').attributes('sandbox')).toBe('allow-scripts')
  })

  it('生成中的 outline 缺少 blocks 时仍可渲染骨架', () => {
    const planned = { ...slide, status: 'planned', blocks: undefined } as unknown as PresentationSlide
    const wrapper = mount(PresentationPreview, {
      props: { deckId: 'deck-1', revisionId: 'working:gen-1', revisionChecksum: '', slides: [planned], selectedSlideId: 'slide-1' },
    })
    expect(wrapper.get('iframe').attributes('srcdoc')).toContain('aria-label="正在生成"')
  })

  it('测量结果必须明确绑定 revision checksum 和布局布尔值', () => {
    const wrapper = mount(PresentationPreview, {
      props: { deckId: 'deck-1', revisionId: 'rev-1', revisionChecksum: 'checksum-1', slides: [slide], selectedSlideId: 'slide-1' },
      attachTo: document.body,
    })
    const frame = wrapper.get('iframe').element as HTMLIFrameElement
    const base = {
      version: 'presentation-preview/v1', type: 'render:measured', deck_id: 'deck-1', revision_id: 'rev-1',
      revision_checksum: 'checksum-1', slide_id: 'slide-1',
    }
    window.dispatchEvent(new MessageEvent('message', {
      data: { ...base, payload: { overflow: 'false', collision: false, slide_count: 1, overflow_slide_ids: [], collision_slide_ids: [] } }, origin: 'null', source: frame.contentWindow,
    }))
    expect(wrapper.emitted('measured')).toBeUndefined()

    window.dispatchEvent(new MessageEvent('message', {
      data: { ...base, payload: { overflow: false, collision: false, slide_count: 1, overflow_slide_ids: [], collision_slide_ids: [] } }, origin: 'null', source: frame.contentWindow,
    }))
    expect(wrapper.emitted('measured')).toEqual([[
      {
        revision_id: 'rev-1', revision_checksum: 'checksum-1', overflow: false, collision: false, slide_count: 1,
        overflow_slide_ids: [], collision_slide_ids: [],
      },
    ]])
    wrapper.unmount()
  })

  it('聚合整套课件时能发现非当前页的 overflow', () => {
    const current = document.createElement('section')
    current.dataset.slideId = 'slide-current'
    const nonCurrent = document.createElement('section')
    nonCurrent.dataset.slideId = 'slide-non-current'
    setBox(current, { clientHeight: 100, scrollHeight: 100, clientWidth: 100, scrollWidth: 100 })
    setBox(nonCurrent, { clientHeight: 100, scrollHeight: 138, clientWidth: 100, scrollWidth: 100 })

    const result = aggregatePresentationMeasurements([current, nonCurrent])
    expect(result).toMatchObject({
      overflow: true,
      collision: false,
      slide_count: 2,
      overflow_slide_ids: ['slide-non-current'],
    })
  })

  it('用真实区域矩形相交判断 collision，不再硬编码 false', () => {
    const page = document.createElement('section')
    page.dataset.slideId = 'slide-collision'
    const header = document.createElement('header')
    const blocks = document.createElement('div')
    blocks.className = 'blocks'
    const block = document.createElement('section')
    block.className = 'block'
    const footer = document.createElement('footer')
    blocks.append(block)
    page.append(header, blocks, footer)
    setBox(page, { clientHeight: 100, scrollHeight: 100, clientWidth: 100, scrollWidth: 100 })
    header.getBoundingClientRect = () => rect(0, 0, 100, 42)
    block.getBoundingClientRect = () => rect(0, 36, 100, 40)
    footer.getBoundingClientRect = () => rect(0, 90, 100, 10)

    const result = aggregatePresentationMeasurements([page])
    expect(result.collision).toBe(true)
    expect(result.collision_slide_ids).toEqual(['slide-collision'])
  })

  it('srcdoc 为每一页创建等尺寸离屏测量页', () => {
    const second = { ...slide, slide_id: 'slide-2', position: 1, title: '非当前页' }
    const wrapper = mount(PresentationPreview, {
      props: { deckId: 'deck-1', revisionId: 'rev-1', revisionChecksum: 'checksum-1', slides: [slide, second], selectedSlideId: 'slide-1' },
    })
    const srcdoc = wrapper.get('iframe').attributes('srcdoc') || ''
    expect(srcdoc.match(/data-measure-slide/g)).toHaveLength(3)
    expect(srcdoc).toContain('data-slide-id="slide-2"')
    expect(srcdoc).toContain('aggregatePresentationMeasurements(pages)')
    expect(srcdoc).not.toContain('collision:false')
  })
})
