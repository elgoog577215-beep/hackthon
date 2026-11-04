import { describe, expect, it, vi } from 'vitest'
import { captureReadingPosition, restoreReadingPosition } from '../utils/reading-position'
function documentFixture() {
  const root = document.createElement('div')
  root.innerHTML = '<section data-section-id="s1"><div data-block-id="b1"></div><div data-block-id="b2"></div></section>'
  root.scrollTop = 1000
  const rect = (top: number) => ({ top } as DOMRect)
  root.getBoundingClientRect = () => rect(80)
  const section = root.firstElementChild as HTMLElement
  section.getBoundingClientRect = () => rect(-900)
  const blocks = [...section.children] as HTMLElement[]
  blocks[0]!.getBoundingClientRect = () => rect(-700)
  blocks[1]!.getBoundingClientRect = () => rect(-40)
  root.scrollTo = vi.fn()
  return { root, blocks }
}
describe('reading bookmarks', () => {
  it('restores the exact offset within the visible block after earlier content reflows', () => {
    const { root, blocks } = documentFixture()
    const position = captureReadingPosition(root)
    expect(position).toEqual({ sectionId: 's1', blockId: 'b2', offset: 120, atTop: false, expandedAnswers: [] })
    blocks[1]!.getBoundingClientRect = () => ({ top: 200 } as DOMRect)
    expect(restoreReadingPosition(root, JSON.stringify(position))).toBe(true)
    expect(root.scrollTo).toHaveBeenCalledWith({ top: 1240, behavior: 'instant' })
  })
  it('handles old bookmarks and rejects missing or malformed locations', () => {
    const { root } = documentFixture()
    expect(restoreReadingPosition(root, 's1')).toBe(true)
    expect(restoreReadingPosition(root, 'missing')).toBe(false)
    expect(restoreReadingPosition(root, 'null')).toBe(false)
    expect(restoreReadingPosition(root, '{"sectionId":"s1","offset":"bad"}')).toBe(false)
  })
  it('keeps the start of the document at the top', () => {
    const { root } = documentFixture()
    root.scrollTop = 0
    restoreReadingPosition(root, JSON.stringify(captureReadingPosition(root)))
    expect(root.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'instant' })
  })
})


it('restores expanded answers before locating the passage', () => {
  const { root, blocks } = documentFixture()
  blocks[1]!.innerHTML = '<details class="handout-block--answer" open><summary>Answer</summary>Explanation</details>'
  const position = captureReadingPosition(root)
  const answer = blocks[1]!.querySelector('details')!
  answer.open = false
  restoreReadingPosition(root, JSON.stringify(position))
  expect(answer.open).toBe(true)
  answer.open = false
  expect(restoreReadingPosition(root, JSON.stringify({ ...position, sectionId: 'deleted' }))).toBe(false)
  expect(answer.open).toBe(false)
})
