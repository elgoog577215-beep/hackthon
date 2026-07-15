export interface SlideMeasurementResult {
  overflow: boolean
  collision: boolean
  slide_count: number
  overflow_slide_ids: string[]
  collision_slide_ids: string[]
}

const hasBoxOverflow = (element: HTMLElement): boolean => (
  element.scrollHeight > element.clientHeight + 1
  || element.scrollWidth > element.clientWidth + 1
)

const rectanglesOverlap = (left: DOMRect, right: DOMRect): boolean => {
  if (!left.width || !left.height || !right.width || !right.height) return false
  const tolerance = 1
  return (
    left.left < right.right - tolerance
    && left.right > right.left + tolerance
    && left.top < right.bottom - tolerance
    && left.bottom > right.top + tolerance
  )
}

/** Measure one fully laid-out off-screen slide, including its content regions. */
export function measurePresentationSlide(slide: HTMLElement) {
  const overflowCandidates = [
    slide,
    ...Array.from(slide.querySelectorAll<HTMLElement>('header, .blocks, .block, h1, p, ul, pre, footer')),
  ]
  const overflow = overflowCandidates.some(hasBoxOverflow)
  const collisionRegions = Array.from(
    slide.querySelectorAll<HTMLElement>('header, .blocks > .block, footer'),
  )
  let collision = false
  for (const [leftIndex, leftRegion] of collisionRegions.entries()) {
    if (collision) break
    const left = leftRegion.getBoundingClientRect()
    for (const rightRegion of collisionRegions.slice(leftIndex + 1)) {
      if (rectanglesOverlap(left, rightRegion.getBoundingClientRect())) {
        collision = true
        break
      }
    }
  }
  return {
    slide_id: slide.dataset.slideId || '',
    overflow,
    collision,
  }
}

/** Aggregate every page; no currently selected page receives special treatment. */
export function aggregatePresentationMeasurements(slides: HTMLElement[]): SlideMeasurementResult {
  const pageResults = slides.map(measurePresentationSlide)
  return {
    overflow: pageResults.some(page => page.overflow),
    collision: pageResults.some(page => page.collision),
    slide_count: pageResults.length,
    overflow_slide_ids: pageResults.filter(page => page.overflow).map(page => page.slide_id),
    collision_slide_ids: pageResults.filter(page => page.collision).map(page => page.slide_id),
  }
}

/** Serialize the same tested functions into the opaque-origin srcdoc runtime. */
export function presentationMeasurementRuntime(): string {
  return [
    `const hasBoxOverflow=${hasBoxOverflow.toString()}`,
    `const rectanglesOverlap=${rectanglesOverlap.toString()}`,
    measurePresentationSlide.toString(),
    aggregatePresentationMeasurements.toString(),
  ].join(';')
}
