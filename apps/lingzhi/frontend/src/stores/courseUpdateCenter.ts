import { t } from '@/shared/i18n'
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  useTeacherMaterialAuditStore,
  type MaterialAuditAsset,
} from './teacherMaterialAudit'
import {
  useCourseEvolutionStore,
  type CourseEvolutionPlan,
} from './courseEvolution'

export type CourseUpdateSourceKind = 'material' | 'course_change' | 'new_change'

export interface CourseUpdateSource {
  key: string
  kind: CourseUpdateSourceKind
  sourceId: string
  title: string
  subtitle: string
  status: 'changed' | 'pending' | 'ready' | 'applied' | 'failed' | 'unchanged' | 'undone' | 'partial'
  updatedAt: string
  material?: MaterialAuditAsset
  plan?: CourseEvolutionPlan
}

function planUpdatedAt(plan: CourseEvolutionPlan) {
  return String(
    plan.teacher_change_planning?.updated_at
    || plan.teacher_change_planning?.created_at
    || '',
  )
}

function planStatus(plan: CourseEvolutionPlan): CourseUpdateSource['status'] {
  if (plan.status === 'undone') return 'undone'
  if (plan.status === 'applied') return plan.application_receipt?.status === 'partial' ? 'partial' : 'applied'
  if (plan.status === 'rejected') return 'unchanged'
  if (plan.status === 'stale' || plan.status === 'undo_partial') return 'failed'
  if (plan.generation_status === 'failed') return 'failed'
  if (plan.generation_status === 'generating') return 'pending'
  return 'ready'
}

export const useCourseUpdateCenterStore = defineStore('course-update-center', () => {
  const materialAudit = useTeacherMaterialAuditStore()
  const courseEvolution = useCourseEvolutionStore()
  const courseId = ref('')
  const activeSourceKey = ref('')
  const loading = ref(false)
  const error = ref('')

  const materialSources = computed<CourseUpdateSource[]>(() => {
    const plan = materialAudit.plan
    const executed = new Set(
      (plan?.execution?.receipts || [])
        .filter(receipt => receipt.plan_id === plan?.plan_id)
        .flatMap(receipt => receipt.target_ids || []),
    )
    return (materialAudit.coursePackage?.assets || []).map(asset => {
      const targets = (plan?.targets || []).filter(target => (
        target.sources.some(source => source.asset_id === asset.asset_id)
      ))
      const hasFailure = asset.parse_status === 'failed'
      const hasPendingTarget = targets.some(target => !executed.has(target.target_id))
      const changed = plan?.status === 'stale' || hasPendingTarget
      return {
        key: `material:${asset.asset_id}`,
        kind: 'material',
        sourceId: asset.asset_id,
        title: asset.filename,
        subtitle: asset.relative_path,
        status: hasFailure ? 'failed' : changed ? 'changed' : targets.length ? 'applied' : 'unchanged',
        updatedAt: '',
        material: asset,
      }
    })
  })

  const courseChangeSources = computed<CourseUpdateSource[]>(() => (
    [...courseEvolution.plans]
      .filter(plan => Boolean(plan.teacher_change_planning))
      .sort((left, right) => planUpdatedAt(right).localeCompare(planUpdatedAt(left)))
      .map(plan => ({
        key: `course-change:${plan.change_set_id}`,
        kind: 'course_change' as const,
        sourceId: plan.change_set_id,
        title: String(plan.request_text || plan.teacher_change_planning?.intent.interpreted_goal || '全课调整'),
        subtitle: String(plan.teacher_change_planning?.intent.interpreted_goal || plan.expected_effect || ''),
        status: planStatus(plan),
        updatedAt: planUpdatedAt(plan),
        plan,
      }))
  ))

  const sources = computed(() => [...materialSources.value, ...courseChangeSources.value])
  const activeSource = computed(() => (
    activeSourceKey.value === 'new-change'
      ? {
          key: 'new-change',
          kind: 'new_change' as const,
          sourceId: '',
          title: '提出全课调整',
          subtitle: '系统扫描大纲、教案、讲义与 PPT 的真实影响',
          status: 'ready' as const,
          updatedAt: '',
        }
      : sources.value.find(source => source.key === activeSourceKey.value) || null
  ))

  const pendingCount = computed(() => sources.value.filter(source => (
    ['changed', 'pending', 'ready', 'failed'].includes(source.status)
  )).length)

  function selectSource(key: string) {
    activeSourceKey.value = key
  }

  function selectFirstAvailable(preferred = '') {
    if (preferred === 'new-change' || (preferred && sources.value.some(source => source.key === preferred))) {
      activeSourceKey.value = preferred
      return
    }
    if (activeSourceKey.value && (
      activeSourceKey.value === 'new-change'
      || sources.value.some(source => source.key === activeSourceKey.value)
    )) return
    activeSourceKey.value = materialSources.value[0]?.key || courseChangeSources.value[0]?.key || 'new-change'
  }

  let loadSequence = 0

  async function load(targetCourseId: string, preferred = '') {
    if (courseId.value !== targetCourseId) activeSourceKey.value = ''
    courseId.value = targetCourseId
    const currentLoad = ++loadSequence
    loading.value = true
    error.value = ''
    const [materials, changes, context] = await Promise.allSettled([
      materialAudit.load(targetCourseId),
      courseEvolution.refreshProgress(targetCourseId),
      courseEvolution.loadCourseContext(targetCourseId),
    ])
    if (currentLoad !== loadSequence || courseId.value !== targetCourseId) return
    const failures = [materials, changes, context].filter(result => result.status === 'rejected')
    if (failures.length || materialAudit.error) error.value = t('courseEvolution.workspace.partialLoadFailed')
    selectFirstAvailable(preferred)
    loading.value = false
  }

  async function refreshAll() {
    if (!courseId.value) return
    const currentLoad = ++loadSequence
    const targetCourseId = courseId.value
    loading.value = true
    error.value = ''
    const tasks: Promise<unknown>[] = [
      courseEvolution.refreshProgress(courseId.value),
      courseEvolution.loadCourseContext(courseId.value),
    ]
    if (materialAudit.coursePackage) tasks.unshift(materialAudit.refresh())
    const results = await Promise.allSettled(tasks)
    if (currentLoad !== loadSequence || targetCourseId !== courseId.value) return
    if (results.some(result => result.status === 'rejected') || materialAudit.error) {
      error.value = t('courseEvolution.workspace.rescanFailed')
    }
    selectFirstAvailable()
    loading.value = false
  }

  return {
    materialAudit,
    courseEvolution,
    courseId,
    activeSourceKey,
    activeSource,
    materialSources,
    courseChangeSources,
    sources,
    pendingCount,
    loading,
    error,
    load,
    refreshAll,
    selectSource,
    selectFirstAvailable,
  }
})
