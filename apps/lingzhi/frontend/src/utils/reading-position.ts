/** The caller scopes each bookmark to its owner, material and revision. */
export interface ReadingPosition {
  sectionId: string
  blockId: string
  offset: number
  atTop: boolean
  expandedAnswers?: string[]
}
export function captureReadingPosition(root: HTMLElement): ReadingPosition {
  const top = root.getBoundingClientRect().top
  const sections = Array.from(root.querySelectorAll<HTMLElement>('[data-section-id]'))
  const section = sections.filter(node => node.getBoundingClientRect().top <= top + 40).at(-1) || sections[0]
  const blocks = Array.from(section?.querySelectorAll<HTMLElement>('[data-block-id]') || [])
  const block = blocks.filter(node => node.getBoundingClientRect().top <= top + 40).at(-1)
  const target = block || section
  return { sectionId: section?.dataset.sectionId || '', blockId: block?.dataset.blockId || '', offset: target ? top - target.getBoundingClientRect().top : 0, atTop: root.scrollTop <= 1, expandedAnswers: Array.from(root.querySelectorAll<HTMLDetailsElement>('details.handout-block--answer[open]')).map(node => node.closest<HTMLElement>('[data-block-id]')?.dataset.blockId || '').filter(Boolean) }
}
export function restoreReadingPosition(root: HTMLElement, stored: string): boolean {
  let position: ReadingPosition
  try { position = JSON.parse(stored) }
  catch { position = { sectionId: stored, blockId: '', offset: -24, atTop: false } }
  if (!position || typeof position.sectionId !== 'string' || !Number.isFinite(position.offset)) return false
  const section = Array.from(root.querySelectorAll<HTMLElement>('[data-section-id]')).find(node => node.dataset.sectionId === position.sectionId)
  if (!section) return false
  const expanded = new Set(Array.isArray(position.expandedAnswers) ? position.expandedAnswers : [])
  root.querySelectorAll<HTMLDetailsElement>('details.handout-block--answer').forEach(node => { node.open = expanded.has(node.closest<HTMLElement>('[data-block-id]')?.dataset.blockId || '') })
  const block = Array.from(section.querySelectorAll<HTMLElement>('[data-block-id]')).find(node => node.dataset.blockId === position.blockId)
  const target = block || section
  const offset = block || !position.blockId ? position.offset : -24
  root.scrollTo({ top: position.atTop ? 0 : Math.max(0, root.scrollTop + target.getBoundingClientRect().top - root.getBoundingClientRect().top + offset), behavior: 'instant' })
  return true
}
