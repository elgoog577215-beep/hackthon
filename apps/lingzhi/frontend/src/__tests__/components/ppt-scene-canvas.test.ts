import { mount } from '@vue/test-utils'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import PptSceneCanvas from '../../components/PptSceneCanvas.vue'

vi.mock('../../utils/http', () => ({ default: { get: vi.fn() } }))
vi.mock('../../shared/i18n', () => ({ t: (key: string) => key }))

describe('frozen scene typography', () => {
  beforeAll(() => vi.stubGlobal('URL', class extends URL { static revokeObjectURL = vi.fn() }))
  afterAll(() => vi.unstubAllGlobals())
  it('uses the exported background and alignment, with legacy defaults', () => {
    const object = { object_id: 'title', kind: 'text', element_id: '', x: 100, y: 80, width: 200, height: 100,
      font_size: 20, text: '标题', lines: ['标题'], fill: '2B5876', color: 'FFFFFF', bold: true }
    const wrapper = mount(PptSceneCanvas, { props: { scene: { width: 960, height: 540, background: '2B5876',
      scene_digest: 'test', execution: { font_family: 'Noto Sans CJK SC' }, emphasized_element_ids: [], edges: [],
      objects: [object, { ...object, object_id: 'center', text_align: 'center', vertical_align: 'middle' }] } } })
    const texts = wrapper.findAll('text')
    expect(wrapper.find('rect').attributes('fill')).toBe('#2B5876')
    expect(texts).toHaveLength(2)
    expect(texts[0]!.attributes()).toMatchObject({ x: '108', y: '106', 'text-anchor': 'start', fill: '#FFFFFF' })
    expect(texts[1]!.attributes()).toMatchObject({ x: '200', y: '137', 'text-anchor': 'middle' })
    wrapper.unmount()
  })
})
