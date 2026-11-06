import { describe, expect, it } from 'vitest'
import { capturePersonalAnchor, resolvePersonalAnchor } from '@/utils/personal-note-anchor'
describe('personal note source anchors', () => {
  it('locates repeated words using their surrounding passage', () => {
    const root = document.createElement('div'); root.textContent = '前一个定义。再看这个定义。'
    const text = root.firstChild!, range = document.createRange(); range.setStart(text, 10); range.setEnd(text, 12)
    const anchor = capturePersonalAnchor(root, range), found = resolvePersonalAnchor(root, anchor)
    expect(anchor.quote).toBe('定义'); expect(found?.startOffset).toBe(10)
    expect(resolvePersonalAnchor(root, { quote: '定义' })).toBeNull()
  })
  it('excludes note controls from whole-block selections', () => {
    const root = document.createElement('div'); root.innerHTML = '<p>原文定义</p><div data-note-controls><button>记录本块</button>已有批注</div>'
    const range = document.createRange(); range.selectNodeContents(root)
    const anchor = capturePersonalAnchor(root, range)
    expect(anchor.quote).toBe('原文定义'); expect(resolvePersonalAnchor(root, anchor)?.toString()).toBe('原文定义')
  })
  it('keeps rendered formulas intact and refuses missing source locations', () => {
    const root = document.createElement('div'); root.innerHTML = '<p>定义 <span class="katex"><span class="katex-mathml">duplicate</span><span class="katex-html">x = 1</span></span></p>'
    const original = root.innerHTML, range = resolvePersonalAnchor(root, { quote: 'x = 1' })
    expect(range?.toString()).toBe('x = 1'); expect(root.innerHTML).toBe(original)
    expect(resolvePersonalAnchor(root, { quote: 'deleted source' })).toBeNull()
  })
})


it('can recover legacy localized-label context only for a verified unchanged and unique quote', () => {
  const root = document.createElement('div'); root.innerHTML = '<p>这是一条原文。</p>'
  const legacy = {quote:'这是一条原文。',anchor_prefix:'ExplanationIntroduction'}
  expect(resolvePersonalAnchor(root,legacy)).toBeNull()
  expect(resolvePersonalAnchor(root,legacy,{allowUniqueQuote:true})?.toString()).toBe(legacy.quote)
  root.innerHTML += '<p>这是一条原文。</p>'
  expect(resolvePersonalAnchor(root,legacy,{allowUniqueQuote:true})).toBeNull()
})
