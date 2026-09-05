import { describe, expect, it } from 'vitest'
import {
  productionActionTaskIds,
  productionPrimaryIssue,
  productionAssetPrimaryAction,
  productionStagePrimaryAction,
  readCourseProductionState,
  readCourseProductionStateWithLegacy,
  type AssetProductionState,
  type CourseProductionAllowedAction,
  type CourseProductionPrimaryAction,
  type StageProductionState,
} from '@/shared/teacher-production-state'

const stage = (overrides: Partial<StageProductionState> = {}): StageProductionState => ({
  display_state: 'not_generated',
  task_state: 'idle',
  availability: 'missing',
  source_state: 'missing',
  latest_attempt_failed: false,
  update_required: false,
  task_ids: [],
  action_targets: {},
  counts: { total: 2, available: 0, generating: 0, failed: 0, stale: 0 },
  issues: [],
  allowed_actions: [],
  ...overrides,
})

describe('teacher production state actions', () => {
  const snapshot = (script: StageProductionState) => ({
    schema_version: 'course_production_state_v1' as const,
    course_id: 'course-1',
    preparation_state: 'preparing' as const,
    stages: { outline: stage(), lesson_plan: stage(), script, ppt: stage() },
    lessons: [],
    issues: [],
  })

  it.each([
    'pause_generation',
    'cancel_generation',
    'resume_generation',
    'provide_input',
    'review_generation',
    'retry_generation',
  ] as CourseProductionAllowedAction[])('rejects task-bound %s without exact action targets', action => {
    const invalid = snapshot(stage({
      task_state: 'failed',
      task_ids: ['script-current'],
      allowed_actions: [action],
      action_targets: {},
    }))

    expect(readCourseProductionState(invalid)).toBeNull()
  })

  it('keeps mixed action targets separate and never falls back to all task ids', () => {
    const input = snapshot(stage({
      task_state: 'failed',
      task_ids: ['script-retry', 'script-inspect'],
      allowed_actions: ['retry_generation', 'inspect_failure'],
      action_targets: {
        retry_generation: ['script-retry'],
        inspect_failure: ['script-inspect'],
      },
    }))
    const parsed = readCourseProductionState(input)

    expect(parsed).not.toBeNull()
    expect(productionActionTaskIds(parsed?.stages.script, 'retry_generation')).toEqual(['script-retry'])
    expect(productionActionTaskIds(parsed?.stages.script, 'inspect_failure')).toEqual(['script-inspect'])
    expect(productionActionTaskIds(parsed?.stages.script, 'resume_generation')).toEqual([])
  })

  it('promotes only explicit issue recovery from the original v1 projection shape', () => {
    const retryIssue = {
      issue_id: 'script-retry',
      stage: 'script',
      lesson_unit_id: 'L1-2',
      task_id: 'script-job-2',
      code: 'lesson_script_shard_incomplete',
      summary: '3 个教学块生成失败，已保留其他成功结果。',
      recovery: { action: 'retry_generation', automatic: false, requires_confirmation: true },
    }
    const oldStage = (overrides: Record<string, unknown> = {}) => ({
      display_state: 'available',
      task_state: 'completed',
      availability: 'usable',
      source_state: 'current',
      latest_attempt_failed: false,
      update_required: false,
      counts: { total: 1, available: 1, generating: 0, failed: 0, stale: 0 },
      issues: [],
      ...overrides,
    })
    const parsed = readCourseProductionState({
      schema_version: 'course_production_state_v1',
      course_id: 'course-1',
      preparation_state: 'preparing',
      stages: {
        outline: oldStage(),
        lesson_plan: oldStage(),
        script: oldStage({
          display_state: 'failed',
          task_state: 'failed',
          availability: 'stale',
          latest_attempt_failed: true,
          counts: { total: 2, available: 1, generating: 0, failed: 1, stale: 0 },
          latest_attempt: { task_ids: ['script-job-2'] },
          issues: [retryIssue],
        }),
        ppt: oldStage(),
      },
      lessons: [{
        lesson_unit_id: 'L1-2',
        title: '第二讲',
        stages: {
          script: {
            ...oldStage({
              display_state: 'failed',
              task_state: 'failed',
              availability: 'missing',
              latest_attempt_failed: true,
              issues: [retryIssue],
            }),
            counts: undefined,
          },
        },
      }],
      issues: [retryIssue],
    })

    expect(parsed).not.toBeNull()
    expect(parsed?.stages.script.allowed_actions).toEqual(['retry_generation'])
    expect(productionActionTaskIds(parsed?.stages.script, 'retry_generation')).toEqual(['script-job-2'])
    expect(parsed?.lessons[0]?.stages.script?.allowed_actions).toEqual(['retry_generation'])
    expect(productionActionTaskIds(parsed?.lessons[0]?.stages.script, 'retry_generation')).toEqual(['script-job-2'])
  })

  it('does not infer retry from an old v1 failed status without explicit recovery authority', () => {
    const oldFailedStage = {
      display_state: 'failed', task_state: 'failed', availability: 'missing', source_state: 'missing',
      latest_attempt_failed: true, update_required: false,
      counts: { total: 1, available: 0, generating: 0, failed: 1, stale: 0 }, issues: [],
    }
    const parsed = readCourseProductionState({
      schema_version: 'course_production_state_v1', course_id: 'course-1', preparation_state: 'preparing',
      stages: { outline: oldFailedStage, lesson_plan: oldFailedStage, script: oldFailedStage, ppt: oldFailedStage },
      lessons: [], issues: [],
    })

    expect(parsed).not.toBeNull()
    expect(parsed?.stages.script.allowed_actions).toEqual(['inspect_failure'])
    expect(productionActionTaskIds(parsed?.stages.script, 'retry_generation')).toEqual([])
  })

  it.each([
    ['waiting_for_input', ['provide_input', 'cancel_generation'], { provide_input: ['task-1'], cancel_generation: ['task-1'] }],
    ['waiting_for_review', ['review_generation', 'resume_generation'], { review_generation: ['task-1'], resume_generation: ['task-1'] }],
    ['unknown', ['inspect_failure', 'retry_generation'], { retry_generation: ['task-1'] }],
  ] as const)('rejects forbidden actions for %s instead of relying on page-level hiding', (taskState, allowedActions, actionTargets) => {
    expect(readCourseProductionState(snapshot(stage({
      task_state: taskState,
      task_ids: ['task-1'],
      allowed_actions: [...allowedActions],
      action_targets: Object.fromEntries(
        Object.entries(actionTargets).map(([action, taskIds]) => [action, [...taskIds]]),
      ),
    })))).toBeNull()
  })

  it('requires an exact task target for outline draft regeneration but not for a new PPT attempt', () => {
    const invalidOutline = snapshot(stage())
    invalidOutline.stages.outline = stage({
      has_unconfirmed_draft: true,
      task_ids: ['outline-completed'],
      allowed_actions: ['regenerate_from_latest_source'],
      action_targets: {},
    })
    expect(readCourseProductionState(invalidOutline)).toBeNull()

    const validPpt = snapshot(stage())
    validPpt.stages.ppt = stage({
      display_state: 'available',
      task_state: 'completed',
      availability: 'usable',
      source_state: 'current',
      allowed_actions: ['regenerate_from_latest_source'],
      action_targets: {},
    })
    expect(readCourseProductionState(validPpt)).not.toBeNull()
  })

  it.each([
    ['missing asset without permission', stage(), 'none'],
    ['active controls only', stage({
      display_state: 'generating',
      task_state: 'running',
      allowed_actions: ['pause_generation', 'cancel_generation'],
    }), 'none'],
    ['explicit generate', stage({ allowed_actions: ['generate'] }), 'generate'],
    ['explicit resume', stage({
      display_state: 'generating',
      task_state: 'paused',
      allowed_actions: ['resume_generation'],
    }), 'resume_generation'],
    ['explicit input gate', stage({
      display_state: 'generating',
      task_state: 'waiting_for_input',
      allowed_actions: ['provide_input', 'cancel_generation'],
    }), 'provide_input'],
    ['explicit review gate', stage({
      display_state: 'generating',
      task_state: 'waiting_for_review',
      allowed_actions: ['review_generation', 'cancel_generation'],
    }), 'review_generation'],
  ] as Array<[string, StageProductionState, CourseProductionPrimaryAction]>)('%s reads only allowed_actions', (_name, input, expected) => {
    expect(productionStagePrimaryAction(input)).toBe(expected)
  })

  it('does not infer a retry from issues, failure state, or missing counts', () => {
    const input = stage({
      display_state: 'failed',
      task_state: 'failed',
      counts: { total: 2, available: 0, generating: 0, failed: 2, stale: 0 },
      issues: [{
        issue_id: 'retryable', stage: 'script', lesson_unit_id: 'L1-2', task_id: 'task-2',
        code: 'provider_unavailable', summary: '可重试',
        recovery: { action: 'retry_generation', automatic: false, requires_confirmation: true },
      }],
      allowed_actions: [],
    })

    expect(productionStagePrimaryAction(input)).toBe('none')
    expect(productionAssetPrimaryAction(input)).toBe('none')
  })

  it('uses a stable priority when several primary actions are explicitly allowed', () => {
    const allowed_actions: CourseProductionAllowedAction[] = [
      'generate',
      'inspect_failure',
      'retry_generation',
      'review_generation',
      'cancel_generation',
    ]

    expect(productionStagePrimaryAction(stage({ allowed_actions }))).toBe('review_generation')
  })

  it('uses one stable issue priority instead of page-owned array order', () => {
    const issues = [
      {
        issue_id: 'review-first', stage: 'outline' as const, lesson_unit_id: '', blocking: false,
        code: 'review_source', summary: '待核对',
        recovery: { action: 'inspect_failure', automatic: false as const, requires_confirmation: true as const },
      },
      {
        issue_id: 'retry-second', stage: 'script' as const, lesson_unit_id: 'L1-2', blocking: true,
        code: 'provider_unavailable', summary: '可重试',
        recovery: { action: 'retry_generation', automatic: false as const, requires_confirmation: true as const },
      },
    ]

    expect(productionPrimaryIssue(issues)?.issue_id).toBe('retry-second')
  })

  const assetActionCases: Array<[
    string,
    Partial<AssetProductionState>,
    CourseProductionPrimaryAction,
  ]> = [
    ['paused without permission', { display_state: 'generating', task_state: 'paused' }, 'none'],
    ['paused with permission', { display_state: 'generating', task_state: 'paused', allowed_actions: ['resume_generation'] }, 'resume_generation'],
    ['retryable failure', { display_state: 'failed', task_state: 'failed', allowed_actions: ['retry_generation'] }, 'retry_generation'],
    ['inspection-only failure', { display_state: 'failed', task_state: 'failed', allowed_actions: ['inspect_failure'] }, 'inspect_failure'],
    ['last-good without permission', { display_state: 'available', task_state: 'failed', availability: 'usable', latest_attempt_failed: true }, 'none'],
  ]

  it.each(assetActionCases)('maps PPT asset %s from allowed_actions', (_name, overrides, expected) => {
    expect(productionAssetPrimaryAction({
      display_state: 'not_generated', task_state: 'idle', availability: 'missing', source_state: 'missing',
      latest_attempt_failed: false, update_required: false, task_ids: [], issues: [], allowed_actions: [],
      action_targets: {},
      ...overrides,
    })).toBe(expected)
  })
})

describe('legacy production state safety compiler', () => {
  const legacyCourse = (readyHandouts = 0) => ({
    course_id: 'legacy-course',
    node_count: 1,
    preparation_summary: { planned_lessons: 1, ready_handouts: readyHandouts },
  })

  it.each([
    ['active', 'running', 'none'],
    ['waiting_for_input', 'waiting_for_input', 'provide_input'],
    ['waiting_for_review', 'waiting_for_review', 'review_generation'],
    ['mystery_status', 'unknown', 'inspect_failure'],
  ] as const)('preserves legacy %s as %s with an explicit safe action', (status, taskState, action) => {
    const state = readCourseProductionStateWithLegacy(
      legacyCourse(),
      { id: `task-${status}`, status, currentPhase: 'script_generation' },
    )
    const projected = state.stages.script

    expect(projected.task_state).toBe(taskState)
    expect(productionStagePrimaryAction(projected)).toBe(action)
    expect(projected.allowed_actions).not.toContain('generate')
    expect(projected.allowed_actions).not.toContain('resume_generation')
    if (status === 'waiting_for_input' || status === 'waiting_for_review') {
      expect(projected.allowed_actions).not.toContain('cancel_generation')
    }
    if (status === 'mystery_status') {
      expect(projected.display_state).toBe('failed')
      expect(projected.issues[0]?.code).toBe('legacy_unknown_task_state')
      expect(projected.issues[0]?.blocking).toBe(true)
    }
  })

  it.each([
    [false, 'quality_blocked', false, 'inspect_failure'],
    [false, 'quality_blocked', true, 'retry_generation'],
    [undefined, 'none', false, 'inspect_failure'],
  ] as const)('fails closed for unpublished warning: publication=%s recovery=%s resumable=%s', (publicationAllowed, recoveryState, canResume, action) => {
    const state = readCourseProductionStateWithLegacy(
      legacyCourse(),
      {
        id: 'warning-task',
        taskType: 'teacher_lesson_script_generation',
        status: 'completed_with_warnings',
        currentPhase: 'quality_failed',
        publicationAllowed,
        recovery: { state: recoveryState, can_resume: canResume },
      },
    )
    const projected = state.stages.script

    expect(projected.task_state).toBe('failed')
    expect(projected.display_state).toBe('failed')
    expect(projected.allowed_actions).not.toContain('generate')
    expect(productionStagePrimaryAction(projected)).toBe(action)
    expect(projected.issues[0]?.code).toBe('legacy_quality_blocked')
  })

  it.each([
    [{ publicationAllowed: true }, 'completed'],
    [{ recovery: { state: 'completed' } }, 'completed'],
  ] as const)('treats warning completion as completed only with publication evidence', (proof, taskState) => {
    const state = readCourseProductionStateWithLegacy(
      legacyCourse(1),
      {
        id: 'published-warning',
        taskType: 'teacher_lesson_script_generation',
        status: 'completed_with_warnings',
        currentPhase: 'script_generation',
        ...proof,
      },
    )

    expect(state.stages.script.task_state).toBe(taskState)
    expect(state.stages.script.allowed_actions).toEqual([])
    expect(productionStagePrimaryAction(state.stages.script)).toBe('none')
  })

  it('only resumes a recovery-less paused legacy task when its teacher asset owner is known', () => {
    const legacyPaused = readCourseProductionStateWithLegacy(
      legacyCourse(),
      { id: 'paused-legacy', taskType: 'teacher_lesson_script_generation', status: 'paused', currentPhase: 'script_generation' },
    )
    const unknownOwner = readCourseProductionStateWithLegacy(
      legacyCourse(),
      { id: 'paused-unknown-owner', status: 'paused', currentPhase: 'script_generation' },
    )
    const rejectedRecovery = readCourseProductionStateWithLegacy(
      legacyCourse(),
      {
        id: 'paused-rejected',
        status: 'paused',
        currentPhase: 'script_generation',
        recovery: { state: 'unavailable', can_resume: false, checkpoint: { phase: 'script' } },
      },
    )

    expect(productionStagePrimaryAction(legacyPaused.stages.script)).toBe('resume_generation')
    expect(productionStagePrimaryAction(unknownOwner.stages.script)).toBe('inspect_failure')
    expect(productionStagePrimaryAction(rejectedRecovery.stages.script)).toBe('inspect_failure')
  })

  it.each(['active', 'waiting_for_input', 'waiting_for_review', 'paused', 'failed'])(
    'fails closed for legacy %s when no task id can authorize the write',
    status => {
      const state = readCourseProductionStateWithLegacy(
        legacyCourse(),
        { status, currentPhase: 'script_generation', recovery: { state: 'manual_resume', can_resume: true } },
      )

      expect(state.stages.script.task_ids).toEqual([])
      expect(state.stages.script.allowed_actions).toEqual(['inspect_failure'])
      expect(productionStagePrimaryAction(state.stages.script)).toBe('inspect_failure')
    },
  )

  it('keeps a last-good asset visible while an unknown attempt remains inspection-only', () => {
    const state = readCourseProductionStateWithLegacy(
      legacyCourse(1),
      { id: 'unknown-with-last-good', status: 'future_status', currentPhase: 'script_generation' },
    )

    expect(state.stages.script.display_state).toBe('available')
    expect(state.stages.script.task_state).toBe('unknown')
    expect(state.stages.script.allowed_actions).toEqual(['inspect_failure'])
    expect(productionStagePrimaryAction(state.stages.script)).toBe('inspect_failure')
  })

  it('synthesizes generate only when the whole new projection and active legacy task are absent', () => {
    const state = readCourseProductionStateWithLegacy(legacyCourse())

    expect(state.stages.script.task_state).toBe('idle')
    expect(state.stages.script.allowed_actions).toEqual(['generate'])
    expect(productionStagePrimaryAction(state.stages.script)).toBe('generate')
  })

  it('fails closed instead of consulting legacy task state when a new projection is present but invalid', () => {
    const invalidProjection = {
      schema_version: 'course_production_state_v1',
      course_id: 'legacy-course',
      preparation_state: 'preparing',
      stages: {
        outline: stage({ task_state: 'paused', allowed_actions: undefined as never }),
        lesson_plan: stage({ allowed_actions: undefined as never }),
        script: stage({ allowed_actions: undefined as never }),
        ppt: stage({ allowed_actions: undefined as never }),
      },
      lessons: [],
      issues: [],
    }
    const course = {
      ...legacyCourse(),
      course_production_state: invalidProjection,
    }

    expect(readCourseProductionState(course)).toBeNull()
    const state = readCourseProductionStateWithLegacy(course, {
      id: 'legacy-resumable',
      status: 'paused',
      currentPhase: 'script_generation',
      recovery: { state: 'manual_resume', can_resume: true },
    })
    expect(state.stages.outline.task_state).toBe('unknown')
    expect(state.stages.outline.allowed_actions).toEqual(['inspect_failure'])
    expect(productionStagePrimaryAction(state.stages.outline)).toBe('inspect_failure')
    expect(state.stages.script.allowed_actions).toEqual(['inspect_failure'])
  })

  it('builds a complete safe stage when an invalid v1 projection is severely partial', () => {
    const course = {
      ...legacyCourse(),
      course_production_state: {
        schema_version: 'course_production_state_v1',
        course_id: 'legacy-course',
        preparation_state: 'preparing',
        stages: { outline: {}, lesson_plan: {}, script: {}, ppt: {} },
        lessons: [],
        issues: [],
      },
    }

    const state = readCourseProductionStateWithLegacy(course)

    expect(state.stages.outline).toMatchObject({
      display_state: 'failed',
      task_state: 'unknown',
      availability: 'missing',
      source_state: 'missing',
      task_ids: [],
      action_targets: {},
      allowed_actions: ['inspect_failure'],
      counts: { total: 0, available: 0, generating: 0, failed: 0, stale: 0 },
      issues: [],
    })
    expect(() => JSON.stringify(state.stages)).not.toThrow()
  })
})
