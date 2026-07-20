import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DiagramSpecRenderer from '@/components/DiagramSpecRenderer.vue'

function buildUnit(overrides: Record<string, any> = {}) {
  return {
    unit_id: 'diagram:sec-1',
    section_id: 'sec-1',
    title: '函数与映射 · 知识路径',
    diagram_kind: 'concept_map',
    nodes: [
      { node_id: 'objective::obj-1', label: '理解函数的定义', kind: 'objective', source_ref: 'objective:obj-1' },
      { node_id: 'knowledge::kp-domain', label: '定义域', kind: 'knowledge', source_ref: 'kp-domain' },
      { node_id: 'knowledge::kp-range', label: '值域', kind: 'knowledge', source_ref: 'kp-range' },
    ],
    edges: [
      { edge_id: 'dge_a', source_node_id: 'objective::obj-1', target_node_id: 'knowledge::kp-domain', relation: 'supports' },
      { edge_id: 'dge_b', source_node_id: 'knowledge::kp-domain', target_node_id: 'knowledge::kp-range', relation: 'prepares' },
    ],
    source_section_ids: ['sec-1'],
    source_block_ids: ['blk-1'],
    mermaid: 'flowchart LR',
    ...overrides,
  }
}

function renderSvg(unit: unknown) {
  const wrapper = mount(DiagramSpecRenderer, { props: { unit } })
  const svg = wrapper.find('[data-testid="diagram-svg"]')
  const markup = svg.exists() ? svg.element.outerHTML : ''
  wrapper.unmount()
  return markup
}

describe('DiagramSpecRenderer', () => {
  it('按 DiagramSpec 渲染出预期的节点与边', () => {
    const wrapper = mount(DiagramSpecRenderer, { props: { unit: buildUnit() } })

    expect(wrapper.attributes('data-render-state')).toBe('ready')
    expect(wrapper.find('[data-testid="diagram-fallback"]').exists()).toBe(false)

    const nodes = wrapper.findAll('.diagram-node')
    expect(nodes).toHaveLength(3)
    expect(nodes.map(node => node.attributes('data-node-id'))).toEqual([
      'objective::obj-1',
      'knowledge::kp-domain',
      'knowledge::kp-range',
    ])
    expect(nodes.map(node => node.find('.diagram-node-label').text())).toEqual([
      '理解函数的定义',
      '定义域',
      '值域',
    ])
    // objective 单独成列（x=20），两个内容节点同在第二列（x=380）
    expect(nodes.map(node => node.find('rect').attributes('x'))).toEqual(['20', '380', '380'])
    // 同列内按下标纵向排布，行距确定
    expect(nodes.map(node => node.find('rect').attributes('y'))).toEqual(['20', '20', '98'])

    const edges = wrapper.findAll('.diagram-edge')
    expect(edges).toHaveLength(2)
    expect(edges.map(edge => edge.attributes('data-edge-id'))).toEqual(['dge_a', 'dge_b'])
    expect(edges.map(edge => edge.attributes('data-relation'))).toEqual(['supports', 'prepares'])
    expect(edges.map(edge => edge.find('.diagram-edge-label').text())).toEqual(['支撑', '承接'])

    wrapper.unmount()
  })

  it('同一份 spec 两次渲染输出逐字节一致的 SVG', () => {
    const first = renderSvg(buildUnit())
    const second = renderSvg(buildUnit())

    expect(first).not.toBe('')
    expect(second).toBe(first)
    // 不含随机 id / 时间戳派生的属性
    expect(first).not.toMatch(/mermaid-\d/)
  })

  it.each([
    ['missing_spec', undefined],
    ['missing_spec', 'not-an-object'],
    ['missing_spec', ['nodes']],
    ['invalid_nodes', buildUnit({ nodes: [] })],
    ['invalid_nodes', buildUnit({ nodes: 'oops' })],
    ['invalid_nodes', buildUnit({ nodes: [{ label: '缺少 node_id', kind: 'knowledge' }], edges: [] })],
    ['invalid_nodes', buildUnit({
      nodes: [
        { node_id: 'dup', label: 'A', kind: 'knowledge' },
        { node_id: 'dup', label: 'B', kind: 'knowledge' },
      ],
      edges: [],
    })],
    ['too_many_nodes', buildUnit({
      nodes: Array.from({ length: 41 }, (_, index) => ({
        node_id: `knowledge::n-${index}`,
        label: `节点 ${index}`,
        kind: 'knowledge',
      })),
      edges: [],
    })],
    ['unknown_diagram_kind', buildUnit({ diagram_kind: 'sankey_of_doom' })],
    ['unknown_diagram_kind', buildUnit({ diagram_kind: 42 })],
    ['invalid_edges', buildUnit({
      edges: [{ edge_id: 'x', source_node_id: 'objective::obj-1', target_node_id: 'ghost', relation: 'supports' }],
    })],
    ['invalid_edges', buildUnit({
      edges: [{ edge_id: 'x', source_node_id: 'objective::obj-1', target_node_id: 'knowledge::kp-range', relation: 'teleports' }],
    })],
    ['invalid_edges', buildUnit({ edges: 'nope' })],
  ])('降级路径 %s 不抛异常且标注原因', (reason, unit) => {
    const wrapper = mount(DiagramSpecRenderer, { props: { unit } })

    expect(wrapper.attributes('data-render-state')).toBe('degraded')
    expect(wrapper.find('[data-testid="diagram-svg"]').exists()).toBe(false)

    const note = wrapper.find('[data-testid="diagram-fallback-reason"]')
    expect(note.exists()).toBe(true)
    expect(note.attributes('data-reason')).toBe(reason)
    expect(note.text().length).toBeGreaterThan(0)

    wrapper.unmount()
  })

  it('降级时把仍可读的节点标签渲染为纯文本列表', () => {
    const wrapper = mount(DiagramSpecRenderer, { props: { unit: buildUnit({ diagram_kind: 'unknown' }) } })

    const items = wrapper.findAll('[data-testid="diagram-fallback-list"] li')
    expect(items.map(item => item.text())).toEqual(['理解函数的定义', '定义域', '值域'])

    wrapper.unmount()
  })

  it('spec 文本被转义而非当作 HTML 注入', () => {
    const payload = '<img src=x onerror="alert(1)">恶意标签'
    const wrapper = mount(DiagramSpecRenderer, {
      props: {
        unit: buildUnit({
          nodes: [{ node_id: 'knowledge::evil', label: payload, kind: 'knowledge' }],
          edges: [],
        }),
      },
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.html()).toContain('&lt;img')
    expect(wrapper.find('.diagram-node-label').text()).toContain('<img src=x')

    wrapper.unmount()
  })

  it('降级列表中的文本同样不会被解析为 HTML', () => {
    const wrapper = mount(DiagramSpecRenderer, {
      props: {
        unit: buildUnit({
          diagram_kind: 'unknown',
          nodes: [{ node_id: 'n1', label: '<script>alert(1)</scr' + 'ipt>', kind: 'knowledge' }],
        }),
      },
    })

    expect(wrapper.find('[data-testid="diagram-fallback-list"] script').exists()).toBe(false)
    expect(wrapper.find('[data-testid="diagram-fallback-list"] li').text()).toContain('<script>')

    wrapper.unmount()
  })
})
