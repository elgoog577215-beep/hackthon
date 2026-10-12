import { describe, expect, it } from 'vitest'
import { placeCompanion } from '@/utils/companion-placement'

describe('free companion safe landing', () => {
  const viewport = { width: 1280, height: 720 }
  const pet = { width: 80, height: 108 }
  const obstacles = [
    { x: 10, y: 80, width: 292, height: 630 },
    { x: 314, y: 80, width: 624, height: 630 },
    { x: 950, y: 80, width: 320, height: 350 },
  ]
  it('lands outside the entire reading area and note controls', () => {
    const point = placeCompanion(viewport, pet, { x: 600, y: 300 }, obstacles)!
    expect(point).not.toBeNull()
    expect(point.x).toBeGreaterThanOrEqual(944)
    expect(point.y).toBeGreaterThanOrEqual(436)
  })
  it('can choose either side when that edge is free', () => {
    const body = [{ x: 120, y: 0, width: 1040, height: 720 }]
    expect(placeCompanion(viewport, pet, { x: 0, y: 300 }, body)?.x).toBe(6)
    expect(placeCompanion(viewport, pet, { x: 1270, y: 300 }, body)?.x).toBe(1194)
  })
  it('returns no full-size slot when occupied, but allows a compact header attachment', () => {
    const occupied = [{ x: 0, y: 80, width: 1280, height: 640 }]
    expect(placeCompanion(viewport, pet, { x: 900, y: 600 }, occupied)).toBeNull()
    const small = placeCompanion(viewport, { width: 48, height: 44 }, { x: 900, y: 600 }, occupied)!
    expect(small.y + 44).toBeLessThanOrEqual(74)
  })
  it('does not place a pet over a full-screen dialog or outside a tiny viewport', () => {
    expect(placeCompanion(viewport, pet, { x: 0, y: 0 }, [{ x: 0, y: 0, ...viewport }])).toBeNull()
    expect(placeCompanion({ width: 40, height: 40 }, pet, { x: 0, y: 0 }, [])).toBeNull()
  })
})
