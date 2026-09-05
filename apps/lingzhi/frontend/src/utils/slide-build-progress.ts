export const SLIDE_BUILD_STEP_COUNT = 10

export const SLIDE_BUILD_STAGE_STEP_INDEX: Readonly<Record<string, number>> = {
  fragmenting: 0,
  planning: 0,
  story_plan: 1,
  chapter_plan: 2,
  episode_progress: 2,
  slide_plan: 3,
  bundle_plan: 3,
  layout_plan: 4,
  visual_plan: 5,
  asset_compilation: 5,
  bundle_part_build: 6,
  slide_build: 6,
  semantic_repair: 7,
  image_search: 7,
  reviewing: 8,
  quality: 8,
  visual_quality: 8,
  quality_fallback: 8,
  render_review: 9,
  render_repair: 9,
  repair_progress: 9,
  complete: 9,
}

export function inferSlideBuildStepIndex(stage: string, progress: number) {
  const explicit = SLIDE_BUILD_STAGE_STEP_INDEX[stage]
  if (explicit != null) return explicit

  const normalized = Math.max(0, Math.min(100, Number(progress || 0)))
  if (normalized >= 98) return 9
  if (normalized >= 96) return 8
  if (normalized >= 93) return 7
  if (normalized >= 22) return 6
  if (normalized >= 18) return 5
  if (normalized >= 14) return 4
  if (normalized >= 10) return 3
  if (normalized >= 6) return 2
  if (normalized >= 2) return 1
  return 0
}

export function advanceSlideBuildStep(
  currentStep: number,
  stage: string,
  progress: number,
) {
  const boundedCurrent = Math.max(
    0,
    Math.min(SLIDE_BUILD_STEP_COUNT - 1, Number(currentStep || 0)),
  )
  return Math.max(boundedCurrent, inferSlideBuildStepIndex(stage, progress))
}

export function isFinalV5CandidateReplay(event: {
  event?: string
  engine_schema?: string
  candidate_stage?: string
}) {
  return (
    ['slide_reset', 'slide_upsert'].includes(String(event.event || ''))
    && event.engine_schema === 'slide_deck_v5'
    && ['final_contract', 'render_verified'].includes(String(event.candidate_stage || ''))
  )
}
