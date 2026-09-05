import { describe, expect, it, vi } from 'vitest'
import { applyContentBlockAnchors, captureViewportAnchor, resolvedAnchorScrollTop } from '@/utils/learning-position'

const rect = (top: number, bottom: number) => ({
  top,
  bottom,
  left: 0,
  right: 100,
  width: 100,
  height: bottom - top,
  x: 0,
  y: top,
  toJSON: () => ({}),
}) as DOMRect

describe('learning position helpers', () => {
  it('把后端内容块修订映射到对应标题 DOM', () => {
    const root = document.createElement('div')
    root.innerHTML = '<h2>核心概念</h2><p>正文</p><h2>应用</h2>'

    applyContentBlockAnchors(root, [
      { block_id: 'b1', type: 'concept', title: '核心概念', content: '正文', order: 0, block_revision_id: 'r1', content_fingerprint: 'f1' },
      { block_id: 'b2', type: 'application', title: '应用', content: '应用', order: 1, block_revision_id: 'r2', content_fingerprint: 'f2' },
    ])

    const headings = root.querySelectorAll<HTMLElement>('h2')
    expect(headings[0]?.dataset.contentBlockId).toBe('b1')
    expect(headings[0]?.dataset.contentBlockRevisionId).toBe('r1')
    expect(headings[1]?.dataset.contentFingerprint).toBe('f2')
  })

  it('采集视口顶部最近内容块和块内相对进度', () => {
    const node = document.createElement('article')
    node.innerHTML = '<h2 data-content-block-id="b1" data-content-block-revision-id="r1" data-content-fingerprint="f1" data-content-block-type="concept" data-content-block-title="概念">概念</h2><h2 data-content-block-id="b2">例子</h2>'
    const [first, second] = Array.from(node.querySelectorAll<HTMLElement>('h2'))
    vi.spyOn(first!, 'getBoundingClientRect').mockReturnValue(rect(100, 130))
    vi.spyOn(second!, 'getBoundingClientRect').mockReturnValue(rect(300, 330))
    vi.spyOn(node, 'getBoundingClientRect').mockReturnValue(rect(80, 500))
    vi.spyOn(first!, 'getClientRects').mockReturnValue([rect(100, 130)] as unknown as DOMRectList)
    vi.spyOn(second!, 'getClientRects').mockReturnValue([rect(300, 330)] as unknown as DOMRectList)

    const anchor = captureViewportAnchor(node, 200)

    expect(anchor?.block_id).toBe('b1')
    expect(anchor?.progress).toBe(0.5)
    expect(anchor?.block_revision_id).toBe('r1')
  })

  it('按内容块比例计算跨视口恢复位置', () => {
    const container = document.createElement('div')
    const anchor = document.createElement('h2')
    const next = document.createElement('h2')
    Object.defineProperty(container, 'scrollTop', { value: 400, writable: true })
    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue(rect(50, 650))
    vi.spyOn(anchor, 'getBoundingClientRect').mockReturnValue(rect(150, 180))
    vi.spyOn(next, 'getBoundingClientRect').mockReturnValue(rect(350, 380))

    expect(resolvedAnchorScrollTop(container, anchor, next, 0.5, 20)).toBe(580)
  })
})
