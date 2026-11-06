import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/utils/markdown'
import { resolveReferenceAnchor } from '@/utils/reference-source-anchor'
function range(source: string, content: string, at = source.indexOf(content)) {
  const start = Array.from(source.slice(0, at)).length
  return { start, end: start + Array.from(content).length, content }
}
describe('reference source ranges in rendered prose', () => {
  it('locates different statements within the same block including Unicode and math', () => {
    const a = '当 $P(B)>0$ 时，\n\n$$P(A|B)=1$$', b = '字典键必须**可哈希**。'
    const content = `动机🙂。\n\n${a}\n\n证明保持连续。\n\n${b}`
    const root = document.createElement('div'); root.innerHTML = renderMarkdown(content)
    const first = resolveReferenceAnchor(root, content, range(content, a))
    const second = resolveReferenceAnchor(root, content, range(content, b))
    expect(first).not.toBeNull(); expect(second?.toString()).toBe('字典键必须可哈希。')
    expect(first!.startContainer).not.toBe(second!.startContainer)
  })
  it('disambiguates repeated expressions using the original preceding passage', () => {
    const sentence = '这是同一个结论。', content = `第一种情况。\n\n${sentence}\n\n第二种情况。\n\n${sentence}`
    const root = document.createElement('div'); root.innerHTML = renderMarkdown(content)
    const result = resolveReferenceAnchor(root, content, range(content, sentence, content.lastIndexOf(sentence)))
    expect(result?.startContainer.parentElement).toBe(root.lastElementChild)
  })
  it('rejects stale ranges and does not guess an absent passage', () => {
    const root = document.createElement('div'); root.innerHTML = '<p>变化后的正文。</p>'
    expect(resolveReferenceAnchor(root, '旧正文', {start:0,end:2,content:'不是'})).toBeNull()
    expect(resolveReferenceAnchor(root, '旧正文', {start:0,end:3,content:'旧正文'})).toBeNull()
  })
})
