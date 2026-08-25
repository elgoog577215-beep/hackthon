<template>
  <Teleport to="body">
    <Transition name="course-adjustment-layer">
      <div v-if="modelValue" class="course-adjustment-layer" @keydown="handleKeydown">
        <button type="button" class="course-adjustment-backdrop" :aria-label="t('courseEvolution.workspace.close', '关闭课程调整工作台')" @click="close" />
        <section ref="workspaceRef" class="course-adjustment-workspace" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
          <header class="course-adjustment-header">
            <span class="course-adjustment-mark"><GitBranchPlus :size="20" /></span>
            <div class="course-adjustment-title">
              <small>{{ t('courseEvolution.workspace.kicker', '课程发布后维护') }}</small>
              <h2 :id="titleId">{{ t('courseEvolution.workspace.title', '全课联动修改') }}</h2>
            </div>
            <div class="course-adjustment-context" :title="contextLabel"><BookOpenText :size="15" /><span>{{ contextLabel }}</span></div>
            <button type="button" class="course-adjustment-refresh" :title="t('courseEvolution.workspace.refresh', '重新读取调整状态')" :aria-label="t('courseEvolution.workspace.refresh', '重新读取调整状态')" :disabled="store.loading" @click="store.evaluate(courseId)">
              <RefreshCw :size="17" :class="{ spinning: store.loading }" />
            </button>
            <button type="button" class="course-adjustment-close" :title="t('courseEvolution.workspace.close', '关闭课程调整工作台')" :aria-label="t('courseEvolution.workspace.close', '关闭课程调整工作台')" @click="close"><X :size="19" /></button>
          </header>

          <div :class="['course-adjustment-body', `course-adjustment-body--${workspaceState}`]">
            <nav class="course-change-journey" :aria-label="t('courseEvolution.workspace.journeyLabel', '课程修改流程')">
              <ol>
                <li
                  v-for="step in journeySteps"
                  :key="step.index"
                  :class="{ active: step.index === currentJourneyStep, complete: step.index < currentJourneyStep }"
                  :aria-current="step.index === currentJourneyStep ? 'step' : undefined"
                >
                  <span>{{ step.index }}</span>
                  <b>{{ step.label }}</b>
                </li>
              </ol>
            </nav>

            <section v-if="workspaceState !== 'request'" class="workspace-context-strip" :aria-label="t('courseEvolution.workspace.changeContext', '本次修改上下文')">
              <div>
                <small>{{ t('courseEvolution.workspace.teacherRequest', '老师原话') }}</small>
                <p :title="rawRequest">{{ rawRequest }}</p>
              </div>
              <div>
                <small>{{ t('courseEvolution.workspace.aiInterpretation', 'AI 当前的理解') }}</small>
                <p :title="interpretedGoal">{{ interpretedGoal }}</p>
              </div>
              <div class="context-protection">
                <small>{{ t('courseEvolution.workspace.protectedRequirements', '必须遵守') }}</small>
                <p :title="protectedRequirements.join('；')">{{ protectedRequirements.join('；') || t('courseEvolution.workspace.noProtectedRequirements', '无特别保护要求') }}</p>
              </div>
              <button v-if="workspaceState !== 'applied'" type="button" class="context-correct-action" @click="openCorrection"><PencilLine :size="14" />{{ t('courseEvolution.workspace.adjustUnderstanding', '调整理解') }}</button>
            </section>

            <form v-if="correctionOpen && workspaceState !== 'request' && workspaceState !== 'applied'" class="understanding-correction workspace-context-correction" @submit.prevent="submitCorrection">
              <label><span>{{ t('courseEvolution.workspace.correctionLabel', '请直接说哪里理解错了') }}</span><textarea v-model="correctionText" rows="2" :placeholder="t('courseEvolution.workspace.correctionPlaceholder', '例如：不是删除案例，而是把案例移到新章节并保留原始资料。')" /></label>
              <div><button type="button" class="text-action" @click="correctionOpen = false">{{ t('common.cancel', '取消') }}</button><button type="submit" class="primary-action" :disabled="store.generating || !correctionText.trim()"><LoaderCircle v-if="store.generating" :size="15" class="spinning" /><Check v-else :size="15" />{{ t('courseEvolution.workspace.submitCorrection', '按修正重新理解') }}</button></div>
            </form>

            <div class="course-adjustment-stage">
              <main v-if="workspaceState === 'request'" class="workspace-single workspace-state-request">
              <CourseEvolutionPanel :course-id="courseId" :section-id="sectionId" :focus-plan-id="focusPlanId" surface="workspace" workspace-state="request" :show-heading="false" @course-applied="emit('courseApplied', $event)" />
              <section class="recent-course-changes">
                <header><History :size="17" /><strong>{{ t('courseEvolution.workspace.recentChanges', '最近修改') }}</strong></header>
                <ol v-if="recentPlans.length">
                  <li v-for="plan in recentPlans" :key="plan.change_set_id">
                    <span :data-status="plan.status">{{ recentPlanStatus(plan) }}</span>
                    <div>
                      <b>{{ plan.request_text || plan.teacher_change_planning?.intent.raw_request || t('courseEvolution.workspace.courseAdjustment', '课程调整') }}</b>
                      <small>{{ plan.teacher_change_planning?.updated_at || plan.teacher_change_planning?.created_at || plan.change_set_id }}</small>
                    </div>
                  </li>
                </ol>
                <p v-else>{{ t('courseEvolution.workspace.noRecentChanges', '还没有课程修改记录。') }}</p>
              </section>
              </main>

              <main v-else-if="workspaceState === 'interpreting'" class="workspace-single workspace-state-interpreting">
              <section class="intent-review-card">
                <header class="state-heading">
                  <span><BrainCircuit :size="19" /></span>
                  <div><small>{{ t('courseEvolution.workspace.interpretingKicker', 'AI 正在理解') }}</small><h3>{{ t('courseEvolution.workspace.interpretingTitle', '正在确认目标与保护要求') }}</h3></div>
                  <LoaderCircle :size="19" class="spinning" />
                </header>
                <div v-if="planning?.intent.blocking_questions.length" class="blocking-questions">
                  <b>{{ t('courseEvolution.workspace.needsClarification', '还需要确认') }}</b>
                  <p v-for="question in planning.intent.blocking_questions" :key="question">{{ question }}</p>
                </div>
                <p v-if="actionError" class="workspace-error"><TriangleAlert :size="14" />{{ actionError }}</p>
              </section>
              </main>

              <main v-else-if="workspaceState === 'scanning'" class="workspace-single workspace-state-scanning">
              <section class="scan-progress-card" aria-live="polite">
                <header class="state-heading">
                  <span class="scan-icon"><ScanSearch :size="19" /></span>
                  <div><small>{{ t('courseEvolution.workspace.scanningKicker', '正在扫描') }}</small><h3>{{ t('courseEvolution.workspace.scanningTitle', '正在沿课程关系寻找真实影响') }}</h3></div>
                  <LoaderCircle :size="19" class="spinning" />
                </header>
                <div class="scan-track"><span /></div>
                <div v-if="discoveredAssetItems.length" class="discovered-impact">
                  <b>{{ impactStatusLabel }}</b>
                  <ul><li v-for="asset in discoveredAssetItems" :key="asset.key"><component :is="asset.icon" :size="16" /><span>{{ asset.label }}</span><strong>{{ asset.count }}</strong></li></ul>
                </div>
                <p v-else class="scan-awaiting">{{ t('courseEvolution.workspace.scanAwaiting', '正在读取课程结构与相关内容，发现一项就显示一项。') }}</p>
                <p class="scan-guard"><ShieldCheck :size="15" />{{ t('courseEvolution.workspace.scanGuard', '扫描只生成候选，确认前不会改变正式课程。') }}</p>
              </section>
              </main>

              <div v-else-if="workspaceState === 'content'" class="workspace-two-column workspace-state-content">
              <aside class="impact-navigation">
                <header><small>{{ t('courseEvolution.workspace.contentKicker', '内容变化') }}</small><strong>{{ t('courseEvolution.workspace.affectedContent', '受影响内容') }}</strong><p>{{ impactStatusLabel }}</p></header>
                <nav :aria-label="t('courseEvolution.workspace.affectedContent', '受影响内容')">
                  <button v-for="asset in affectedAssetItems" :key="asset.key" type="button" :class="{ active: selectedAsset === asset.key }" @click="selectedAsset = asset.key">
                    <component :is="asset.icon" :size="16" /><span>{{ asset.label }}</span><b>{{ asset.count }}</b>
                  </button>
                </nav>
                <section v-if="protectedRequirements.length" class="impact-protection"><ShieldCheck :size="16" /><div><b>{{ t('courseEvolution.workspace.protectedRequirements', '必须遵守') }}</b><small>{{ protectedRequirements.join('；') }}</small></div></section>
              </aside>
              <main class="content-diff-review">
                <header class="review-heading"><div><small>{{ selectedAssetLabel }}</small><h3>{{ t('courseEvolution.workspace.compareChanges', '核对原文与候选修改') }}</h3></div><span>{{ t('courseEvolution.workspace.formalUnchanged', '尚未应用') }}</span></header>
                <div v-if="contentDiffItems.length" class="content-diff-list">
                  <article v-for="item in contentDiffItems" :key="item.id" class="content-diff-card">
                    <header><b>{{ item.label }}</b><span :data-status="item.status">{{ migrationStatusLabel(item.status) }}</span></header>
                    <p class="diff-reason">{{ item.reason }}</p>
                    <div class="diff-columns">
                      <section><small>{{ t('courseEvolution.workspace.beforeChange', '当前正式内容') }}</small><p>{{ item.before }}</p></section>
                      <ArrowRight :size="17" />
                      <section><small>{{ t('courseEvolution.workspace.afterChange', '候选修改') }}</small><p>{{ item.after }}</p></section>
                    </div>
                  </article>
                </div>
                <p v-else class="empty-review">{{ t('courseEvolution.workspace.noDiffForAsset', '这一类资产尚未生成可审阅差异。') }}</p>
                <CourseEvolutionPanel :course-id="courseId" :section-id="sectionId" :focus-plan-id="focusedPlan?.change_set_id || focusPlanId" surface="workspace" workspace-state="content" :show-heading="false" @course-applied="emit('courseApplied', $event)" />
              </main>
              </div>

              <div v-else-if="workspaceState === 'structure'" class="workspace-structure-layout workspace-state-structure">
              <main class="structure-review">
                <header class="review-heading"><div><small>{{ t('courseEvolution.workspace.structureKicker', '结构变化') }}</small><h3>{{ t('courseEvolution.workspace.compareCourseTree', '核对新旧课程树') }}</h3></div><span :data-status="planning?.structure_review_status">{{ structureReviewLabel }}</span></header>
                <div class="course-tree-comparison">
                  <section><header><BookOpenText :size="16" /><b>{{ t('courseEvolution.workspace.currentTree', '当前课程树') }}</b></header><ol><li v-for="node in currentTreeItems" :key="node.id"><span />{{ node.label }}</li></ol></section>
                  <ArrowRight :size="20" />
                  <section class="proposed-tree"><header><GitMerge :size="16" /><b>{{ t('courseEvolution.workspace.proposedTree', '调整后课程树') }}</b></header><ol><li v-for="node in proposedTreeItems" :key="node.id"><span />{{ node.label }}</li></ol></section>
                </div>
                <CourseEvolutionPanel :course-id="courseId" :section-id="sectionId" :focus-plan-id="focusedPlan?.change_set_id || focusPlanId" surface="workspace" workspace-state="structure" :show-heading="false" @course-applied="emit('courseApplied', $event)" />
              </main>
              <aside class="migration-summary">
                <header><small>{{ t('courseEvolution.workspace.migrationKicker', '迁移结果') }}</small><strong>{{ t('courseEvolution.workspace.migrationTitle', '哪些保留，哪些重做') }}</strong></header>
                <dl><div v-for="item in migrationSummary" :key="item.key" :data-status="item.key"><dt>{{ item.label }}</dt><dd>{{ item.count }}</dd></div></dl>
                <section v-if="migrationConflicts.length" class="migration-conflicts"><header><TriangleAlert :size="16" /><b>{{ t('courseEvolution.workspace.conflicts', '需要人工处理的冲突') }}</b></header><ul><li v-for="conflict in migrationConflicts" :key="conflict.migration_id">{{ conflict.reason }}</li></ul></section>
                <p v-else class="no-conflicts"><CircleCheckBig :size="16" />{{ t('courseEvolution.workspace.noConflicts', '当前没有阻断冲突') }}</p>
                <p class="structure-guard"><ShieldCheck :size="16" />{{ t('courseEvolution.workspace.structureReviewHint', '只确认 AI 是否理解对了新结构；确认后才批量生成下游候选。') }}</p>
              </aside>
              </div>

              <main v-else class="workspace-single workspace-state-applied">
              <section class="application-receipt" :data-status="focusedPlan?.status">
                <header class="state-heading"><span><CircleCheckBig :size="20" /></span><div><small>{{ t('courseEvolution.workspace.appliedKicker', '应用完成') }}</small><h3>{{ applicationTitle }}</h3></div></header>
                <dl class="receipt-stats"><div><dt>{{ t('courseEvolution.workspace.appliedItems', '已更新') }}</dt><dd>{{ receiptSummary.applied }}</dd></div><div><dt>{{ t('courseEvolution.workspace.failedItems', '失败') }}</dt><dd>{{ receiptSummary.failed }}</dd></div><div><dt>{{ t('courseEvolution.workspace.unchangedItems', '未变化') }}</dt><dd>{{ receiptSummary.unchanged }}</dd></div></dl>
                <section v-if="receiptFailedItems.length" class="receipt-exceptions failed"><b>{{ t('courseEvolution.workspace.failedItems', '失败项') }}</b><ul><li v-for="item in receiptFailedItems" :key="item">{{ item }}</li></ul></section>
                <section v-if="receiptUnchangedItems.length" class="receipt-exceptions"><b>{{ t('courseEvolution.workspace.unchangedItems', '未变化项') }}</b><ul><li v-for="item in receiptUnchangedItems" :key="item">{{ item }}</li></ul></section>
                <div class="receipt-actions">
                  <button type="button" class="secondary-action" @click="startNewRequest"><Sparkles :size="15" />{{ t('courseEvolution.workspace.newChange', '继续修改课程') }}</button>
                  <button v-if="focusedPlan?.status === 'applied'" type="button" class="undo-action" :disabled="store.actingId === focusedPlan.change_set_id" @click="undoApplied"><LoaderCircle v-if="store.actingId === focusedPlan.change_set_id" :size="15" class="spinning" /><Undo2 v-else :size="15" />{{ t('courseEvolution.workspace.undoAll', '撤销本次修改') }}</button>
                </div>
                <p v-if="actionError" class="workspace-error"><TriangleAlert :size="14" />{{ actionError }}</p>
              </section>
              </main>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import { ArrowRight, BookOpenText, BookText, BrainCircuit, Check, CircleCheckBig, ClipboardList, FileQuestion, GitBranchPlus, GitMerge, History, LoaderCircle, PencilLine, Presentation, RefreshCw, ScanSearch, ScrollText, ShieldCheck, Sparkles, TriangleAlert, Undo2, X } from 'lucide-vue-next'
import CourseEvolutionPanel from './CourseEvolutionPanel.vue'
import { t } from '../shared/i18n'
import { useCourseEvolutionStore, type CourseEvolutionApplicationPresentation, type CourseEvolutionPlan, type TeacherCourseChangePlanning } from '../stores/courseEvolution'

type WorkspaceState = 'request' | 'interpreting' | 'scanning' | 'content' | 'structure' | 'applied'
type AssetDefinition = { key: string; label: string; icon: Component; count: number }
type UnitMigration = TeacherCourseChangePlanning['unit_migrations'][number]

const props = withDefaults(defineProps<{ modelValue: boolean; courseId: string; sectionId?: string; courseTitle?: string; sectionTitle?: string; focusPlanId?: string }>(), { sectionId: '', courseTitle: '', sectionTitle: '', focusPlanId: '' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; courseApplied: [presentation: CourseEvolutionApplicationPresentation] }>()
const store = useCourseEvolutionStore()
const workspaceRef = ref<HTMLElement | null>(null)
const previousFocus = ref<HTMLElement | null>(null)
const correctionOpen = ref(false)
const correctionText = ref('')
const actionError = ref('')
const selectedAsset = ref('')
const forceRequest = ref(false)
const requestBaselinePlanId = ref('')
const titleId = `course-adjustment-${Math.random().toString(36).slice(2)}`

const contextLabel = computed(() => props.courseTitle || t('courseEvolution.workspace.currentCourse', '当前课程'))
const focusedPlan = computed(() => {
  if (props.focusPlanId) {
    const focused = store.plans.find(plan => plan.change_set_id === props.focusPlanId || plan.plan_id === props.focusPlanId)
    if (focused) return focused
  }
  return [...store.plans].reverse().find(plan => plan.teacher_change_planning) || store.plans.at(-1) || null
})
const planning = computed(() => focusedPlan.value?.teacher_change_planning || null)
const workspaceState = computed<WorkspaceState>(() => {
  if (forceRequest.value || focusedPlan.value?.status === 'rejected') return 'request'
  if (focusedPlan.value?.status === 'applied' || focusedPlan.value?.status === 'undone' || focusedPlan.value?.application_receipt || focusedPlan.value?.undo_receipt) return 'applied'
  if (store.generating || focusedPlan.value?.generation_status === 'generating') return 'scanning'
  if (!focusedPlan.value) return 'request'
  if (planning.value?.status === 'draft' || planning.value?.status === 'needs_clarification') return 'interpreting'
  if (planning.value?.strategy_status === 'provisional') return planning.value.unit_migrations.length ? 'scanning' : 'interpreting'
  if (planning.value?.structural_operations.length || planning.value?.execution_strategies.includes('structural_regeneration')) return 'structure'
  return 'content'
})
const journeySteps = computed(() => [
  { index: 1, label: t('courseEvolution.workspace.journeyRequest', '说出要求') },
  { index: 2, label: t('courseEvolution.workspace.journeyAnalyze', '分析影响') },
  { index: 3, label: t('courseEvolution.workspace.journeyReview', '审阅修改') },
  { index: 4, label: t('courseEvolution.workspace.journeyApply', '应用完成') },
])
const currentJourneyStep = computed(() => ({
  request: 1,
  interpreting: 2,
  scanning: 2,
  content: 3,
  structure: 3,
  applied: 4,
})[workspaceState.value])
const rawRequest = computed(() => planning.value?.intent.raw_request || focusedPlan.value?.request_text || '')
const interpretedGoal = computed(() => planning.value?.intent.interpreted_goal || focusedPlan.value?.expected_effect || rawRequest.value)
const protectedRequirements = computed(() => [...(planning.value?.intent.hard_constraints || []), ...(planning.value?.intent.protected_requirements || [])])
const assetDefinitions = computed<AssetDefinition[]>(() => {
  const definitions = [
    { key: 'outline', label: t('courseEvolution.workspace.assetOutline', '课程大纲'), icon: BookText },
    { key: 'lesson_plan', label: t('courseEvolution.workspace.assetLessonPlan', '教案'), icon: ClipboardList },
    { key: 'question_bank', label: t('courseEvolution.workspace.assetQuestionBank', '题库'), icon: FileQuestion },
    { key: 'teacher_script', label: t('courseEvolution.workspace.assetTeacherScript', '讲稿'), icon: ScrollText },
    { key: 'slide_deck', label: t('courseEvolution.workspace.assetSlides', 'PPT'), icon: Presentation },
  ]
  return definitions.map(item => {
    const migrationCount = planning.value?.unit_migrations.filter(migration => normalizeAssetKey(migration.asset_type) === item.key).length || 0
    const operationCount = focusedPlan.value?.operations.filter(operation => normalizeAssetKey(String(operation.payload?.asset_type || 'teacher_script')) === item.key).length || 0
    return { ...item, count: migrationCount || operationCount }
  })
})
const discoveredAssetItems = computed(() => assetDefinitions.value.filter(item => item.count > 0))
const affectedAssetItems = computed(() => discoveredAssetItems.value.length ? discoveredAssetItems.value : focusedPlan.value?.operations.length ? assetDefinitions.value.map(item => item.key === 'teacher_script' ? { ...item, count: focusedPlan.value!.operations.length } : item).filter(item => item.count > 0) : [])
const selectedAssetLabel = computed(() => affectedAssetItems.value.find(item => item.key === selectedAsset.value)?.label || '')
const impactStatusLabel = computed(() => {
  const count = planning.value?.unit_migrations.length || focusedPlan.value?.operations.length || 0
  return (workspaceState.value === 'scanning' ? t('courseEvolution.workspace.impactExpanding', '已找到 {count} 个候选，影响范围仍在扩展。') : t('courseEvolution.workspace.impactResolved', '已确认 {count} 个受影响单元。')).replace('{count}', String(count))
})
const contentDiffItems = computed(() => {
  const migrations = (planning.value?.unit_migrations || []).filter(migration => normalizeAssetKey(migration.asset_type) === selectedAsset.value)
  if (migrations.length) return migrations.map(migrationToDiff)
  return (focusedPlan.value?.operations || []).filter(operation => normalizeAssetKey(String(operation.payload?.asset_type || 'teacher_script')) === selectedAsset.value).map(operation => ({ id: operation.operation_id, label: String(operation.payload?.title || operation.target_block_id || operation.target_section_id), reason: operation.reason, before: previewText(operation.payload?.before_preview, t('courseEvolution.workspace.beforePending', '原文正在载入')), after: previewText(operation.payload?.after_preview, t('courseEvolution.workspace.candidatePending', '候选正在生成')), status: String(operation.payload?.candidate_status || 'ready') }))
})
const currentTreeItems = computed(() => uniqueTreeRows(planning.value?.structural_operations.flatMap(operation => {
  const labels = asStringArray(operation.source_titles || operation.current_titles)
  const ids = asStringArray(operation.source_node_ids || operation.source_ids)
  return (labels.length ? labels : ids).map((label, index) => ({ id: `${index}-${label}`, label }))
}) || [], t('courseEvolution.workspace.currentTreePending', '当前结构节点名称待载入')))
const proposedTreeItems = computed(() => uniqueTreeRows(planning.value?.structural_operations.flatMap(operation => {
  const proposed = Array.isArray(operation.proposed_nodes) ? operation.proposed_nodes : []
  if (proposed.length) return proposed.map((node: Record<string, any>, index: number) => ({ id: String(node.provisional_id || node.node_id || index), label: String(node.title || node.node_name || node.provisional_id || node.node_id) }))
  const labels = asStringArray(operation.target_titles || operation.proposed_titles)
  const ids = asStringArray(operation.target_node_ids || operation.target_ids)
  return (labels.length ? labels : ids).map((label, index) => ({ id: `${index}-${label}`, label }))
}) || [], t('courseEvolution.workspace.proposedTreePending', '新结构节点名称待载入')))
const migrationSummary = computed(() => ([
  { key: 'reuse_exact', label: t('courseEvolution.workspace.migrationReuse', '原样保留') }, { key: 'reuse_rebind', label: t('courseEvolution.workspace.migrationRebind', '迁移重绑') }, { key: 'rewrite_partial', label: t('courseEvolution.workspace.migrationRewrite', '局部改写') }, { key: 'regenerate', label: t('courseEvolution.workspace.migrationRegenerate', '重新生成') }, { key: 'retire', label: t('courseEvolution.workspace.migrationRetire', '停用') }, { key: 'blocked', label: t('courseEvolution.workspace.migrationBlocked', '阻断') },
] as Array<{ key: UnitMigration['disposition']; label: string }>).map(item => ({ ...item, count: planning.value?.unit_migrations.filter(migration => migration.disposition === item.key).length || 0 })))
const migrationConflicts = computed(() => planning.value?.unit_migrations.filter(migration => migration.disposition === 'blocked' || migration.requires_review) || [])
const structureReviewLabel = computed(() => planning.value?.structure_review_status === 'confirmed' ? t('courseEvolution.workspace.structureConfirmed', '新结构已确认') : t('courseEvolution.workspace.structurePending', '等待确认新结构'))
const recentPlans = computed(() => [...store.plans].reverse().filter(plan => ['applied', 'rejected', 'undone'].includes(plan.status)).slice(0, 4))
const receiptFailedItems = computed(() => receiptItems(['failed_items', 'failed_block_ids', 'failed_operation_ids']))
const receiptUnchangedItems = computed(() => receiptItems(['unchanged_items', 'unchanged_block_ids', 'last_good_block_ids']))
const receiptSummary = computed(() => ({ applied: Number(focusedPlan.value?.application_receipt?.applied_count ?? focusedPlan.value?.applied_block_ids?.length ?? 0), failed: Number(focusedPlan.value?.application_receipt?.failed_count ?? receiptFailedItems.value.length), unchanged: Number(focusedPlan.value?.application_receipt?.unchanged_count ?? receiptUnchangedItems.value.length) }))
const applicationTitle = computed(() => focusedPlan.value?.status === 'undone' ? t('courseEvolution.workspace.undoneTitle', '本次修改已撤销') : t('courseEvolution.workspace.appliedTitle', '课程已按确认结果更新'))

watch(affectedAssetItems, items => { if (!items.some(item => item.key === selectedAsset.value)) selectedAsset.value = items[0]?.key || '' }, { immediate: true })
watch(() => focusedPlan.value?.change_set_id || '', planId => {
  if (forceRequest.value && planId && planId !== requestBaselinePlanId.value) forceRequest.value = false
})
watch(() => props.modelValue, async open => { if (!open) return; forceRequest.value = false; previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null; await nextTick(); workspaceRef.value?.focus() }, { immediate: true })

function normalizeAssetKey(value: string) { return ({ blueprint: 'outline', course_outline: 'outline', teaching_plan: 'lesson_plan', question: 'question_bank', questions: 'question_bank', script: 'teacher_script', course_document: 'teacher_script', ppt: 'slide_deck', slides: 'slide_deck' } as Record<string, string>)[value] || value }
function previewText(value: unknown, fallback: string) { return typeof value === 'string' && value.trim() ? value : value && typeof value === 'object' ? JSON.stringify(value, null, 2) : fallback }
function migrationToDiff(migration: UnitMigration) {
  const metadata = migration.metadata || {}
  const operation = focusedPlan.value?.operations.find(item => item.payload?.migration_id === migration.migration_id || migration.source_unit_ids.includes(item.target_block_id) || migration.target_unit_ids.includes(item.target_block_id))
  return { id: migration.migration_id, label: String(metadata.title || migration.source_unit_ids[0] || migration.target_unit_ids[0] || migration.unit_type), reason: migration.reason, before: previewText(metadata.before_preview ?? operation?.payload?.before_preview, t('courseEvolution.workspace.beforePending', '原文正在载入')), after: previewText(metadata.after_preview ?? operation?.payload?.after_preview, migration.candidate_status === 'ready' ? t('courseEvolution.workspace.candidateReadyNoPreview', '候选已生成，内容预览待载入') : t('courseEvolution.workspace.candidatePending', '候选正在生成')), status: migration.candidate_status }
}
function migrationStatusLabel(status: string) { return ({ ready: t('courseEvolution.workspace.candidateReady', '候选已就绪'), not_started: t('courseEvolution.workspace.candidateNotStarted', '待生成'), failed: t('courseEvolution.workspace.candidateFailed', '生成失败'), not_required: t('courseEvolution.workspace.candidateNotRequired', '无需修改') } as Record<string, string>)[status] || status }
function asStringArray(value: unknown): string[] { return Array.isArray(value) ? value.map(String).filter(Boolean) : [] }
function uniqueTreeRows(rows: Array<{ id: string; label: string }>, fallback: string) { const seen = new Set<string>(); const result = rows.filter(row => row.label && !seen.has(row.label) && Boolean(seen.add(row.label))); return result.length ? result : [{ id: 'pending', label: fallback }] }
function receiptItems(keys: string[]) { const receipt = focusedPlan.value?.application_receipt || focusedPlan.value?.undo_receipt || {}; return keys.flatMap(key => asStringArray(receipt[key])).filter((item, index, all) => all.indexOf(item) === index) }
function recentPlanStatus(plan: CourseEvolutionPlan) { return ({ applied: t('courseEvolution.workspace.recentApplied', '已应用'), rejected: t('courseEvolution.workspace.recentRejected', '已放弃'), undone: t('courseEvolution.workspace.recentUndone', '已撤销') } as Record<string, string>)[plan.status] || plan.status }
function openCorrection() { correctionText.value = ''; correctionOpen.value = true }
async function submitCorrection() { if (!correctionText.value.trim() || !props.sectionId) return; actionError.value = ''; try { await store.createSectionPlan(props.sectionId, correctionText.value.trim(), 'whole_course'); correctionOpen.value = false } catch (error: any) { actionError.value = String(error?.message || t('courseEvolution.workspace.correctionFailed', '重新理解失败，请重试。')) } }
function startNewRequest() { requestBaselinePlanId.value = focusedPlan.value?.change_set_id || ''; forceRequest.value = true; correctionOpen.value = false; actionError.value = '' }
async function undoApplied() { if (!focusedPlan.value) return; actionError.value = ''; try { await store.undo(focusedPlan.value.change_set_id) } catch (error: any) { actionError.value = String(error?.message || t('courseEvolution.workspace.undoFailed', '撤销失败，请重试。')) } }
function close() { emit('update:modelValue', false); nextTick(() => previousFocus.value?.focus()) }
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); close(); return }
  if (event.key !== 'Tab' || !workspaceRef.value) return
  const focusable = [...workspaceRef.value.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')].filter(element => !element.hasAttribute('hidden'))
  if (!focusable.length) { event.preventDefault(); workspaceRef.value.focus(); return }
  const first = focusable[0]!; const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
</script>

<style scoped>
.course-adjustment-layer{position:fixed;inset:0;z-index:1200;display:grid;place-items:center;padding:24px}.course-adjustment-backdrop{position:absolute;inset:0;width:100%;height:100%;border:0;background:rgba(15,23,42,.5);backdrop-filter:blur(4px);cursor:default}.course-adjustment-workspace{position:relative;width:min(1240px,calc(100vw - 48px));height:min(840px,calc(100dvh - 48px));display:grid;grid-template-rows:72px minmax(0,1fr);overflow:hidden;border-radius:16px;color:var(--lz-text);background:#f7f8fc;box-shadow:0 30px 80px rgba(15,23,42,.28);outline:0}.course-adjustment-header{display:grid;grid-template-columns:42px minmax(190px,1fr) auto minmax(150px,auto) 38px 38px;align-items:center;gap:11px;padding:0 18px 0 20px;border-bottom:1px solid var(--lz-border);background:#fff}.course-adjustment-mark{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;color:#fff;background:#5b54e8;box-shadow:0 9px 20px rgba(79,70,229,.22)}.course-adjustment-title{min-width:0}.course-adjustment-title small{display:block;color:var(--lz-text-muted);font-size:11px;font-weight:700}.course-adjustment-title h2{margin:2px 0 0;color:var(--lz-text-strong);font-family:inherit;font-size:19px;letter-spacing:-.02em}.course-adjustment-state{padding:5px 8px;border-radius:7px;color:#5148dc;background:#f1f0ff;font-size:11px;font-weight:750;white-space:nowrap}.course-adjustment-state[data-state=scanning]{color:#9a5b09;background:#fff7e8}.course-adjustment-state[data-state=applied]{color:#087354;background:#ecf9f4}.course-adjustment-context{min-width:0;max-width:280px;display:flex;align-items:center;justify-self:end;gap:7px;padding:8px 10px;border-radius:9px;color:var(--lz-text-secondary);background:#f4f5f8;font-size:12px}.course-adjustment-context svg{flex:none;color:var(--lz-brand)}.course-adjustment-context span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-adjustment-refresh,.course-adjustment-close{width:38px;height:38px;display:grid;place-items:center;border:0;border-radius:9px;color:var(--lz-text-secondary);background:transparent;cursor:pointer}.course-adjustment-refresh:hover:not(:disabled),.course-adjustment-close:hover{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-adjustment-refresh:focus-visible,.course-adjustment-close:focus-visible{outline:3px solid rgba(99,102,241,.24);outline-offset:1px}.course-adjustment-refresh:disabled{opacity:.45;cursor:not-allowed}.course-adjustment-body{min-height:0;overflow:auto}.workspace-single{width:min(820px,100%);min-height:100%;display:flex;flex-direction:column;gap:18px;margin:0 auto;padding:32px clamp(22px,5vw,54px) 46px;box-sizing:border-box}.recent-course-changes{display:grid;gap:12px;padding:18px 22px;border-top:1px solid var(--lz-border)}.recent-course-changes>header{display:flex;align-items:center;gap:8px;color:var(--lz-text-strong);font-size:13px}.recent-course-changes ol{display:grid;gap:7px;margin:0;padding:0;list-style:none}.recent-course-changes li{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:10px}.recent-course-changes li>span{padding:4px 6px;border-radius:6px;color:#087354;background:#ecf9f4;font-size:10px;font-weight:700}.recent-course-changes li>span[data-status=rejected],.recent-course-changes li>span[data-status=undone]{color:#667085;background:#eef1f5}.recent-course-changes li>div{min-width:0;display:grid;gap:2px}.recent-course-changes li b{overflow:hidden;color:var(--lz-text-strong);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.recent-course-changes li small,.recent-course-changes>p{margin:0;color:var(--lz-text-muted);font-size:10px}.intent-review-card,.scan-progress-card,.application-receipt{display:grid;gap:22px;margin:auto 0;padding:30px;border:1px solid #dfe3ec;border-radius:16px;background:#fff;box-shadow:0 16px 40px rgba(15,23,42,.07)}.state-heading{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:12px}.state-heading>span{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;color:#5148dc;background:#eeedff}.state-heading div{display:grid;gap:3px}.state-heading small,.impact-navigation header small,.migration-summary>header small,.review-heading small{color:var(--lz-brand-strong);font-size:10px;font-weight:800;letter-spacing:.06em}.state-heading h3,.review-heading h3{margin:0;color:var(--lz-text-strong);font-size:18px;letter-spacing:-.02em}.intent-comparison,.diff-columns,.course-tree-comparison{display:grid;grid-template-columns:minmax(0,1fr) 20px minmax(0,1fr);align-items:center;gap:14px}.intent-comparison article{min-height:118px;padding:17px;border-radius:12px;background:#f6f7fa}.intent-comparison article:last-child{background:#f3f2ff}.intent-comparison small,.compact-understanding b,.understanding-bar small,.diff-columns small{display:block;margin-bottom:7px;color:var(--lz-text-muted);font-size:10px;font-weight:750}.intent-comparison p,.understanding-bar p{margin:0;color:var(--lz-text-strong);font-size:13px;line-height:1.7}.protected-list{display:flex;flex-wrap:wrap;gap:7px;margin:0;padding:0;list-style:none}.protected-list li{display:flex;align-items:center;gap:5px;padding:7px 9px;border-radius:8px;color:#087354;background:#ecf9f4;font-size:11px}.blocking-questions{padding:13px 15px;border-radius:10px;color:#89590f;background:#fff7e8}.blocking-questions b{font-size:11px}.blocking-questions p{margin:5px 0 0;font-size:12px}.secondary-action,.primary-action,.undo-action,.text-action{width:fit-content;display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:0 13px;border-radius:9px;font-size:12px;font-weight:750;cursor:pointer}.secondary-action{border:1px solid #d7d9ff;color:#5148dc;background:#f8f8ff}.primary-action{border:1px solid #5148dc;color:#fff;background:#5148dc}.text-action{min-height:32px;padding:0 8px;border:0;color:#5148dc;background:transparent}.understanding-correction{display:grid;gap:12px}.understanding-correction label{display:grid;gap:7px;color:var(--lz-text-strong);font-size:12px;font-weight:700}.understanding-correction textarea{width:100%;padding:12px;border:1px solid #cfd6e3;border-radius:10px;color:var(--lz-text-strong);background:#fff;font:inherit;resize:vertical;box-sizing:border-box}.understanding-correction>div{display:flex;justify-content:flex-end;gap:8px}.scan-progress-card{min-height:420px;align-content:center}.scan-icon{color:#89590f!important;background:#fff7e8!important}.compact-understanding{display:grid;gap:8px;padding:14px 16px;border-radius:11px;background:#f6f7fa}.compact-understanding p{display:grid;grid-template-columns:92px minmax(0,1fr);gap:10px;margin:0;color:var(--lz-text-secondary);font-size:11px;line-height:1.5}.compact-understanding b{margin:0}.scan-track{height:6px;overflow:hidden;border-radius:999px;background:#e9ecf3}.scan-track span{width:38%;height:100%;display:block;border-radius:inherit;background:linear-gradient(90deg,#5b54e8,#9b8cff);animation:course-adjustment-scan 1.5s ease-in-out infinite alternate}.discovered-impact{display:grid;gap:12px}.discovered-impact>b{color:var(--lz-text-secondary);font-size:12px}.discovered-impact ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:0;padding:0;list-style:none}.discovered-impact li{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:8px;padding:11px 12px;border-radius:10px;color:#5148dc;background:#f3f2ff;font-size:12px}.scan-awaiting,.scan-guard{margin:0;color:var(--lz-text-secondary);font-size:12px}.scan-guard{display:flex;align-items:center;gap:7px;color:#087354}.workspace-two-column{min-height:100%;display:grid;grid-template-columns:230px minmax(0,1fr)}.impact-navigation,.migration-summary{min-height:0;overflow:auto;padding:26px 20px;border-right:1px solid var(--lz-border);background:#fff}.impact-navigation>header,.migration-summary>header{display:grid;gap:5px;margin-bottom:18px}.impact-navigation header strong,.migration-summary>header strong{color:var(--lz-text-strong);font-size:16px}.impact-navigation header p{margin:0;color:var(--lz-text-secondary);font-size:11px;line-height:1.5}.impact-navigation nav{display:grid;gap:6px}.impact-navigation nav button{display:grid;grid-template-columns:18px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:42px;padding:0 10px;border:1px solid transparent;border-radius:9px;color:var(--lz-text-secondary);background:#f6f7fa;font-size:12px;text-align:left;cursor:pointer}.impact-navigation nav button.active{border-color:#d7d9ff;color:#5148dc;background:#f1f0ff}.impact-protection{display:grid;grid-template-columns:18px minmax(0,1fr);gap:8px;margin-top:20px;padding:12px;border-radius:10px;color:#087354;background:#ecf9f4}.impact-protection div{display:grid;gap:4px}.impact-protection b{font-size:11px}.impact-protection small{font-size:10px;line-height:1.5}.content-diff-review,.structure-review{min-width:0;display:flex;flex-direction:column;gap:18px;overflow:auto;padding:24px clamp(20px,3vw,36px) 42px}.understanding-bar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 15px;border-radius:11px;background:#f1f0ff}.understanding-bar>div{min-width:0}.understanding-bar small{margin-bottom:3px;color:#5148dc}.understanding-bar p{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.review-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:12px}.review-heading>div{display:grid;gap:4px}.review-heading>span{padding:5px 8px;border-radius:7px;color:#89590f;background:#fff7e8;font-size:10px;font-weight:750}.review-heading>span[data-status=confirmed]{color:#087354;background:#ecf9f4}.content-diff-list{display:grid;gap:12px}.content-diff-card{padding:17px;border:1px solid #dfe3ec;border-radius:13px;background:#fff;box-shadow:0 6px 18px rgba(15,23,42,.035)}.content-diff-card>header{display:flex;align-items:center;justify-content:space-between;gap:10px}.content-diff-card>header b{color:var(--lz-text-strong);font-size:13px}.content-diff-card>header span{padding:4px 7px;border-radius:6px;color:#087354;background:#ecf9f4;font-size:9px}.content-diff-card>header span[data-status=failed]{color:#b42318;background:#fff0ee}.diff-reason{margin:6px 0 13px;color:var(--lz-text-secondary);font-size:11px}.diff-columns section{min-width:0;min-height:110px;padding:13px;border-radius:10px;background:#f6f7fa}.diff-columns section:last-child{background:#f3f2ff}.diff-columns p{max-height:160px;overflow:auto;margin:0;color:var(--lz-text-strong);font-size:11px;line-height:1.65;white-space:pre-wrap}.empty-review{display:grid;place-items:center;min-height:180px;margin:0;color:var(--lz-text-muted);font-size:12px}.content-diff-review :deep(.evolution-panel--workspace),.structure-review :deep(.evolution-panel--workspace){min-height:auto;overflow:visible;padding:0;background:transparent}.workspace-structure-layout{min-height:100%;display:grid;grid-template-columns:minmax(0,1fr) 270px}.migration-summary{border-right:0;border-left:1px solid var(--lz-border)}.course-tree-comparison{align-items:start}.course-tree-comparison>section{min-width:0;padding:16px;border:1px solid #dfe3ec;border-radius:13px;background:#fff}.course-tree-comparison>section.proposed-tree{border-color:#d7d9ff;background:#fbfaff}.course-tree-comparison section>header{display:flex;align-items:center;gap:7px;color:var(--lz-text-strong);font-size:12px}.course-tree-comparison ol{display:grid;gap:7px;margin:14px 0 0;padding:0;list-style:none}.course-tree-comparison li{display:grid;grid-template-columns:12px minmax(0,1fr);align-items:center;gap:7px;padding:9px 10px;border-radius:8px;color:var(--lz-text-secondary);background:#f6f7fa;font-size:11px}.course-tree-comparison li span{width:7px;height:7px;border:2px solid #8e96a8;border-radius:50%}.proposed-tree li{color:#5148dc;background:#f1f0ff}.proposed-tree li span{border-color:#5b54e8}.migration-summary dl{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:0}.migration-summary dl div{padding:11px;border-radius:9px;background:#f6f7fa}.migration-summary dt{color:var(--lz-text-secondary);font-size:10px}.migration-summary dd{margin:4px 0 0;color:var(--lz-text-strong);font-size:18px;font-weight:800}.migration-summary dl div[data-status=blocked]{color:#b42318;background:#fff0ee}.migration-conflicts{margin-top:18px;padding:12px;border-radius:10px;color:#b42318;background:#fff0ee}.migration-conflicts header{display:flex;gap:7px;align-items:center;font-size:11px}.migration-conflicts ul{margin:8px 0 0;padding-left:17px;font-size:10px;line-height:1.5}.no-conflicts,.structure-guard{display:flex;align-items:flex-start;gap:7px;margin:18px 0 0;color:#087354;font-size:11px;line-height:1.5}.structure-guard{padding-top:15px;border-top:1px solid var(--lz-border);color:var(--lz-text-secondary)}.application-receipt[data-status=undone] .state-heading>span{color:#667085;background:#eef1f5}.receipt-request{margin:0;padding-left:12px;border-left:2px solid #c9c5ff;color:var(--lz-text-secondary);font-size:12px;line-height:1.6}.receipt-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:0}.receipt-stats div{padding:14px;border-radius:11px;background:#f6f7fa;text-align:center}.receipt-stats dt{color:var(--lz-text-muted);font-size:10px}.receipt-stats dd{margin:5px 0 0;color:var(--lz-text-strong);font-size:22px;font-weight:800}.receipt-exceptions{padding:12px 14px;border-radius:10px;background:#f6f7fa}.receipt-exceptions.failed{color:#b42318;background:#fff0ee}.receipt-exceptions b{font-size:11px}.receipt-exceptions ul{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0;padding:0;list-style:none}.receipt-exceptions li{padding:5px 7px;border-radius:6px;background:rgba(255,255,255,.75);font-size:10px}.receipt-actions{display:flex;justify-content:space-between;gap:10px}.undo-action{border:1px solid #fecaca;color:#b42318;background:#fff7f6}.workspace-error{display:flex;align-items:center;gap:7px;margin:0;color:#b42318;font-size:11px}.spinning{animation:course-adjustment-spin .8s linear infinite}.course-adjustment-layer-enter-active,.course-adjustment-layer-leave-active{transition:opacity .2s ease}.course-adjustment-layer-enter-active .course-adjustment-workspace{transition:transform .28s cubic-bezier(.16,1,.3,1),filter .28s ease}.course-adjustment-layer-enter-from,.course-adjustment-layer-leave-to{opacity:0}.course-adjustment-layer-enter-from .course-adjustment-workspace{transform:translateY(18px) scale(.985);filter:blur(4px)}@keyframes course-adjustment-spin{to{transform:rotate(360deg)}}@keyframes course-adjustment-scan{from{transform:translateX(-20%)}to{transform:translateX(175%)}}@media(max-width:900px){.course-adjustment-header{grid-template-columns:42px minmax(140px,1fr) auto 38px 38px}.course-adjustment-context{display:none}.workspace-two-column{grid-template-columns:190px minmax(0,1fr)}.workspace-structure-layout{grid-template-columns:minmax(0,1fr) 230px}}@media(prefers-reduced-motion:reduce){.course-adjustment-layer-enter-active,.course-adjustment-layer-leave-active,.course-adjustment-layer-enter-active .course-adjustment-workspace{transition:none}.scan-track span{animation:none}}
/* The workflow frame persists while the task surface changes underneath it. */
.course-adjustment-header{grid-template-columns:42px minmax(190px,1fr) minmax(150px,auto) 38px 38px}
.course-adjustment-body{display:flex;flex-direction:column;overflow:hidden}
.course-change-journey{position:relative;z-index:2;flex:none;padding:12px clamp(28px,7vw,88px) 13px;border-bottom:1px solid var(--lz-border);background:#fff}
.course-change-journey ol{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;padding:0;list-style:none}
.course-change-journey li{position:relative;display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:8px;color:#737f92;font-size:11px}
.course-change-journey li::after{position:absolute;z-index:-1;top:13px;left:calc(50% + 19px);right:calc(-50% + 19px);height:1px;background:#dce1ea;content:""}
.course-change-journey li:last-child::after{display:none}
.course-change-journey li>span{width:28px;height:28px;display:grid;place-items:center;border:1px solid #aeb7c5;border-radius:50%;color:#5f6979;background:#fff;font-size:10px;font-weight:800}
.course-change-journey li>b{font-size:11px;font-weight:700;white-space:nowrap}
.course-change-journey li.complete{color:#5148dc}.course-change-journey li.complete::after{background:#9d98ee}.course-change-journey li.complete>span{border-color:#817af0;color:#fff;background:#817af0}
.course-change-journey li.active{color:#3730a3}.course-change-journey li.active>span{border:2px solid #5b54e8;color:#3730a3;background:#f1f0ff;box-shadow:0 0 0 3px #ecebff}
.workspace-context-strip{flex:none;display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.15fr) minmax(140px,.75fr) auto;align-items:center;gap:0;padding:9px 22px;border-bottom:1px solid #dddef7;background:#f7f7ff}
.workspace-context-strip>div{min-width:0;padding:0 14px;border-right:1px solid #dddef7}.workspace-context-strip>div:first-child{padding-left:0}.workspace-context-strip small{display:block;margin-bottom:2px;color:#5f59b9;font-size:9px;font-weight:750}.workspace-context-strip p{overflow:hidden;margin:0;color:#3e4655;font-size:11px;line-height:1.45;text-overflow:ellipsis;white-space:nowrap}
.context-correct-action{min-height:32px;display:inline-flex;align-items:center;gap:6px;margin-left:12px;padding:0 9px;border:0;border-radius:8px;color:#5148dc;background:transparent;font-size:11px;font-weight:750;cursor:pointer}.context-correct-action:hover{background:#ecebff}.context-correct-action:focus-visible{outline:2px solid #817af0;outline-offset:2px}
.workspace-context-correction{width:min(920px,calc(100% - 44px));flex:none;grid-template-columns:minmax(0,1fr) auto;align-items:end;margin:10px auto 0;padding:13px 15px;border:1px solid #d7d9ff;border-radius:12px;background:#fff;box-sizing:border-box}.workspace-context-correction>div{align-self:end}
.course-adjustment-stage{min-height:0;flex:1;overflow:auto}.course-adjustment-stage>.workspace-two-column,.course-adjustment-stage>.workspace-structure-layout{height:100%}
.workspace-state-request{width:min(920px,100%);gap:14px;padding-top:22px;padding-bottom:32px}.workspace-state-request .recent-course-changes{padding:16px 8px 0}
.workspace-state-interpreting,.workspace-state-scanning,.workspace-state-applied{padding-top:24px}
@media(max-width:900px){.course-adjustment-header{grid-template-columns:42px minmax(140px,1fr) auto 38px 38px}.course-change-journey{padding-right:24px;padding-left:24px}.course-change-journey li{grid-template-columns:26px minmax(0,1fr);gap:6px}.course-change-journey li>span{width:26px;height:26px}.workspace-context-strip{grid-template-columns:minmax(0,.8fr) minmax(0,1.05fr) minmax(110px,.65fr) auto;padding-right:14px;padding-left:14px}.workspace-context-strip>div{padding:0 10px}}
</style>
