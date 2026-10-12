export interface CompanionPoint { x: number; y: number }
export interface CompanionSize { width: number; height: number }
export interface CompanionRect extends CompanionPoint, CompanionSize {}

/** Find the nearest free boundary of the viewport or an occupied surface.
 * Obstacles include the full reading surface, so text density never matters. */
export function placeCompanion(viewport: CompanionSize, size: CompanionSize, preferred: CompanionPoint, obstacles: CompanionRect[]): CompanionPoint | null {
  const gap = 6
  const maxX = viewport.width - size.width - gap
  const maxY = viewport.height - size.height - gap
  if (maxX < gap || maxY < gap) return null
  const clampX = (x: number) => Math.max(gap, Math.min(x, maxX))
  const clampY = (y: number) => Math.max(gap, Math.min(y, maxY))
  const xs = new Set([gap, maxX])
  const ys = new Set([gap, maxY, clampY(preferred.y)])
  for (const box of obstacles) {
    xs.add(clampX(box.x - size.width - gap))
    xs.add(clampX(box.x + box.width + gap))
    ys.add(clampY(box.y - size.height - gap))
    ys.add(clampY(box.y + box.height + gap))
  }
  let best: CompanionPoint | null = null
  let distance = Infinity
  for (const x of xs) for (const y of ys) {
    const blocked = obstacles.some(box => x < box.x + box.width + gap && x + size.width + gap > box.x
      && y < box.y + box.height + gap && y + size.height + gap > box.y)
    if (blocked) continue
    const score = (x - preferred.x) ** 2 + (y - preferred.y) ** 2
    if (score < distance) { best = { x, y }; distance = score }
  }
  return best
}
