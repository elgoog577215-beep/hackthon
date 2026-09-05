import { describe, expect, it } from 'vitest'
import { buildTextQuoteAnchor, resolveTextQuoteAnchor } from '@/utils/text-anchor'

describe('text anchor', () => {
  it('记录选区在正文中的位置和前后文', () => {
    const root = document.createElement('div')
    root.textContent = '第一处向量用于定义。第二处向量用于例题。'
    document.body.appendChild(root)
    const text = root.firstChild!
    const start = root.textContent!.lastIndexOf('向量')
    const range = document.createRange()
    range.setStart(text, start)
    range.setEnd(text, start + 2)

    const anchor = buildTextQuoteAnchor(range, root)

    expect(anchor.text_quote).toBe('向量')
    expect(anchor.text_position.start).toBe(start)
    expect(anchor.text_position.occurrence).toBe(1)
    expect(anchor.text_position.prefix).toContain('第二处')
    root.remove()
  })

  it('重复文本依靠上下文稳定定位第二处', () => {
    const original = '第一处向量用于定义。第二处向量用于例题。'
    const start = original.lastIndexOf('向量')
    const anchor = {
      start,
      end: start + 2,
      prefix: original.slice(Math.max(0, start - 80), start),
      suffix: original.slice(start + 2),
      occurrence: 1,
    }
    const changed = `新增导读。${original}`

    const resolved = resolveTextQuoteAnchor(changed, '向量', anchor)

    expect(resolved.status).toBe('quote_remap')
    expect(resolved.occurrence).toBe(1)
    expect(changed.slice(resolved.start, resolved.end)).toBe('向量')
  })
})
