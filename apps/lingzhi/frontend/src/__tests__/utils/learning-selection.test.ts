import { afterEach, describe, expect, it } from 'vitest'
import { learningSelectionQuote } from '@/utils/learning-selection'

afterEach(() => { document.body.innerHTML = '' })

function fixture() {
  const root = document.createElement('div')
  root.innerHTML = '<article id="node-n1"><p data-content-block-id="b1" data-content-block-revision-id="r1">前文。重复定义。后文。</p><p data-content-block-id="b2">另一个段落。</p><textarea>私人输入</textarea></article><article id="node-n2"><p>第二讲</p></article>'
  document.body.append(root)
  return root
}

function rangeAt(start: Node, startOffset: number, end = start, endOffset = startOffset + 4) {
  const range = document.createRange()
  range.setStart(start, startOffset)
  range.setEnd(end, endOffset)
  return range
}

describe('lecture selection references', () => {
  it('captures the exact quotation, lecture, text position and block revision before the UI reflows', () => {
    const root = fixture()
    const range = rangeAt(root.querySelector('p')!.firstChild!, 3, undefined, 7)
    const quote = learningSelectionQuote(range, root, new Set(['n1', 'n2']))!
    expect(quote).toMatchObject({ text: '重复定义', nodeId: 'n1', anchor: { text_quote:'重复定义', text_position:{start:3,end:7}, block_id:'b1', block_revision_id:'r1' } })
    range.collapse()
    expect(quote.text).toBe('重复定义')
    expect(quote.anchor.text_position).toMatchObject({start:3,end:7})
  })

  it('keeps a same-lecture multi-block quotation without pretending it is all in the first block', () => {
    const root = fixture(), paragraphs = root.querySelectorAll('p')
    const quote = learningSelectionQuote(rangeAt(paragraphs[0]!.firstChild!, 3, paragraphs[1]!.firstChild!, 4), root, new Set(['n1']))!
    expect(quote.nodeId).toBe('n1')
    expect(quote.anchor.block_id).toBeUndefined()
    expect(quote.text).toContain('另一个段')
  })

  it('rejects another lecture, unknown nodes, empty text, editable input and selection outside the reading area', () => {
    const root = fixture(), paragraphs = root.querySelectorAll('p'), first = paragraphs[0]!.firstChild!
    expect(learningSelectionQuote(rangeAt(first, 0, paragraphs[2]!.firstChild!, 2), root, new Set(['n1','n2']))).toBeNull()
    expect(learningSelectionQuote(rangeAt(first, 0), root, new Set(['n2']))).toBeNull()
    expect(learningSelectionQuote(rangeAt(first, 0, first, 0), root, new Set(['n1']))).toBeNull()
    expect(learningSelectionQuote(rangeAt(root.querySelector('textarea')!.firstChild!, 0), root, new Set(['n1']))).toBeNull()
    const other = document.createElement('p'); other.textContent = '外部文字'; document.body.append(other)
    expect(learningSelectionQuote(rangeAt(other.firstChild!, 0), root, new Set(['n1']))).toBeNull()
  })
})
