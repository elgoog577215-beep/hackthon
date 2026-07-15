import type { ContentBlock } from '@/stores/types'

export interface ViewportContentAnchor {
  block_id: string
  block_revision_id: string
  content_fingerprint: string
  block_type: string
  title: string
  progress: number
  text_quote: string
}

const cleanTitle = (value: string) => value.trim().replace(/\s+/g, ' ')

export function applyContentBlockAnchors(root: HTMLElement, blocks: ContentBlock[] = []): void {
  const headings = Array.from(root.querySelectorAll('h1,h2,h3,h4,h5,h6')) as HTMLElement[]
  const available = [...blocks].sort((a, b) => a.order - b.order)
  const used = new Set<string>()

  headings.forEach((heading, index) => {
    const headingTitle = cleanTitle(heading.dataset.headingTitle || heading.textContent || '')
    const exact = available.find((block) => !used.has(block.block_id) && cleanTitle(block.title) === headingTitle)
    const block = exact || available.find((item) => !used.has(item.block_id)) || available[index]
    if (!block) return
    used.add(block.block_id)
    heading.dataset.contentBlockId = block.block_id
    heading.dataset.contentBlockRevisionId = block.block_revision_id || ''
    heading.dataset.contentFingerprint = block.content_fingerprint || ''
    heading.dataset.contentBlockType = block.type
    heading.dataset.contentBlockTitle = block.title
  })
}

export function captureViewportAnchor(nodeElement: HTMLElement, containerTop: number): ViewportContentAnchor | null {
  const anchors = Array.from(nodeElement.querySelectorAll<HTMLElement>('[data-content-block-id]'))
    .filter((element) => element.offsetParent !== null || element.getClientRects().length > 0)
  if (!anchors.length) return null

  let selected = anchors[0]!
  for (const anchor of anchors) {
    if (anchor.getBoundingClientRect().top <= containerTop) selected = anchor
    else break
  }
  const index = anchors.indexOf(selected)
  const next = anchors[index + 1]
  const top = selected.getBoundingClientRect().top
  const bottom = next?.getBoundingClientRect().top ?? nodeElement.getBoundingClientRect().bottom
  const span = Math.max(1, bottom - top)
  const progress = Math.max(0, Math.min(1, (containerTop - top) / span))

  return {
    block_id: selected.dataset.contentBlockId || '',
    block_revision_id: selected.dataset.contentBlockRevisionId || '',
    content_fingerprint: selected.dataset.contentFingerprint || '',
    block_type: selected.dataset.contentBlockType || '',
    title: selected.dataset.contentBlockTitle || cleanTitle(selected.textContent || ''),
    progress,
    text_quote: cleanTitle(selected.textContent || '').slice(0, 500),
  }
}

export function resolvedAnchorScrollTop(
  container: HTMLElement,
  anchorElement: HTMLElement,
  nextElement: HTMLElement | null,
  progress: number,
  topOffset = 24,
): number {
  const containerRect = container.getBoundingClientRect()
  const anchorRect = anchorElement.getBoundingClientRect()
  const nextTop = nextElement?.getBoundingClientRect().top ?? anchorElement.parentElement?.getBoundingClientRect().bottom ?? anchorRect.bottom
  const span = Math.max(0, nextTop - anchorRect.top)
  const ratio = Math.max(0, Math.min(1, progress || 0))
  return Math.max(0, container.scrollTop + (anchorRect.top - containerRect.top) + span * ratio - topOffset)
}
