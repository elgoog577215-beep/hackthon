<template>
  <li v-if="visible" class="navigator-node">
    <button
      type="button"
      :class="['node-button', `level-${node.node_level}`, { active: activeId === node.node_id }]"
      :style="{ '--node-depth': String(depth) }"
      :aria-expanded="hasDisclosure ? disclosureExpanded : undefined"
      :aria-controls="hasDisclosure ? disclosureId : undefined"
      @click="handleNodeClick"
      @keydown.left.prevent="collapseDisclosure"
      @keydown.right.prevent="expandDisclosure"
    >
      <ChevronRight v-if="hasDisclosure" :size="13" :class="{ open: disclosureExpanded }" @click.stop="toggleDisclosure" />
      <span v-else class="node-spacer"></span>
      <span v-if="isChapter" class="node-kind chapter-kind"><BookOpenText :size="14" /></span>
      <span v-else class="node-kind leaf-kind" :class="[{ active: activeId === node.node_id, learned: isLearned }, generationState]"></span>
      <span class="node-label">{{ node.node_name }}</span>
      <span v-if="adaptationMarker" class="adaptation-marker" :data-state="adaptationMarker.state" :title="adaptationMarker.title">
        {{ adaptationMarker.label }}<b>{{ adaptationMarker.count }}</b>
      </span>
      <component v-if="isGenerationPreview && generationIcon" :is="generationIcon" :size="13" class="status generation" :class="[generationState, { spinning: generationState === 'generating' }]" />
      <CheckCircle2 v-else-if="progress?.mastery_status === 'mastered'" :size="13" class="status mastered" />
      <CircleDot v-else-if="activeId === node.node_id" :size="13" class="status current" />
      <span v-else-if="progress?.reading_status === 'learned'" class="read-dot"></span>
    </button>
    <ol
      v-if="showBlockOutline"
      :id="blockOutlineId"
      class="course-block-outline"
      :aria-label="t('learningNavigator.sectionBlocks', '本节内容')"
    >
      <li v-for="entry in visibleBlockEntries" :key="entry.block.block_id">
        <button
          type="button"
          class="course-block-link"
          :class="{ active: activeBlockId === entry.block.block_id }"
          :data-role="entry.block.role"
          :aria-current="activeBlockId === entry.block.block_id ? 'location' : undefined"
          :title="`${entry.roleLabel} · ${entry.title}`"
          @click.stop="emit('selectBlock', { node, blockId: entry.block.block_id })"
        >
          <span class="course-block-role">{{ entry.roleLabel }}</span>
          <span class="course-block-title">{{ entry.title }}</span>
        </button>
      </li>
    </ol>
    <ol v-if="growthTrail.length" class="growth-trail" :data-state="growthTrailState">
      <li v-for="step in growthTrail" :key="step.key">
        <span></span>
        <div>
          <b>{{ step.label }}</b>
          <small>{{ step.detail }}</small>
        </div>
      </li>
    </ol>
    <ul v-if="hasChildren && expanded" :id="`course-node-children-${node.node_id}`">
      <CourseNavigatorNode
        v-for="child in node.children"
        :key="child.node_id"
        :node="child"
        :active-id="activeId"
        :active-block-id="activeBlockId"
        :query="query"
        :depth="depth + 1"
        @select="emit('select', $event)"
        @select-block="emit('selectBlock', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BookOpenText, CheckCircle2, ChevronRight, CircleDot, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { CourseBlockNavigationTarget, CourseDocumentBlock, Node } from '../stores/types'
import { useLearningProgressStore } from '../stores/learningProgress'
import { useCourseStore } from '../stores/course'
import { useCourseEvolutionStore } from '../stores/courseEvolution'
import { t } from '../shared/i18n'

defineOptions({ name: 'CourseNavigatorNode' })
const props = withDefaults(defineProps<{
  node: Node
  activeId?: string
  activeBlockId?: string
  query?: string
  depth?: number
}>(), { activeId: '', activeBlockId: '', query: '', depth: 0 })
const emit = defineEmits<{
  (event: 'select', node: Node): void
  (event: 'selectBlock', target: CourseBlockNavigationTarget): void
}>()
const progressStore = useLearningProgressStore()
const courseStore = useCourseStore()
const evolutionStore = useCourseEvolutionStore()
const expanded = ref(props.depth < 2)
const hasChildren = computed(() => Boolean(props.node.children?.length))
const blockOutlineExpanded = ref(props.activeId === props.node.node_id)
const progress = computed(() => progressStore.nodeProgress(props.node.node_id))
const isChapter = computed(() => props.depth === 0 || props.node.node_level === 1)
const isLearned = computed(() => progress.value?.reading_status === 'learned' || progress.value?.mastery_status === 'mastered')
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const courseEvolutionPlans = computed(() => (
  evolutionStore.courseId && evolutionStore.courseId === progressStore.courseId
    ? evolutionStore.plans
    : progressStore.runtime?.course_evolution?.course_evolution_plans
      || progressStore.runtime?.course_evolution?.adaptation_plans
      || []
))
const relevantPlans = computed(() => {
  const ids = new Set<string>()
  const collect = (node: Node) => {
    ids.add(node.node_id)
    for (const child of node.children || []) collect(child)
  }
  collect(props.node)
  return courseEvolutionPlans.value.filter((plan: Record<string, any>) => {
    const affected = plan.impact_summary?.affected_section_ids || []
    return affected.some((sectionId: string) => ids.has(sectionId))
      || (plan.operations || []).some((operation: Record<string, any>) => ids.has(operation.target_section_id))
  })
})
const adaptationCounts = computed(() => {
  const counts = { pending: 0, active: 0, validated: 0, review: 0 }
  for (const plan of relevantPlans.value) {
    if (plan.status === 'pending') counts.pending += 1
    if (plan.status !== 'applied') continue
    const effect = String(plan.effect_evaluation?.status || 'insufficient_evidence')
    if (effect === 'effective') counts.validated += 1
    else if (effect === 'ineffective' || effect === 'harmful') counts.review += 1
    else counts.active += 1
  }
  return counts
})
const adaptationMarker = computed(() => {
  const value = adaptationCounts.value
  if (value.pending) return {
    state: 'pending',
    count: value.pending,
    label: t('courseEvolution.navigatorMarker', 'AI 建议'),
    title: t('courseEvolution.navigatorMarkerDetail', '该位置在待确认的课程调整范围内'),
  }
  if (value.review) return {
    state: 'review',
    count: value.review,
    label: t('courseEvolution.navigatorReview', '待复核'),
    title: t('courseEvolution.navigatorReviewDetail', '后续证据表明这里的课程变化需要复核'),
  }
  if (value.active) return {
    state: 'active',
    count: value.active,
    label: t('courseEvolution.navigatorApplied', '已应用'),
    title: t('courseEvolution.navigatorAppliedDetail', '当前课程已更新，等待正式复验'),
  }
  if (value.validated) return {
    state: 'validated',
    count: value.validated,
    label: t('courseEvolution.navigatorValidated', '已生长'),
    title: t('courseEvolution.navigatorValidatedDetail', '当前课程变化已获得后续正式证据支持'),
  }
  return null
})
const growthPlan = computed<Record<string, any> | null>(() => {
  if (hasChildren.value) return null
  return [...relevantPlans.value].reverse().find(plan => (
    plan.status === 'pending' || plan.status === 'applied'
  )) || null
})
const growthTrailState = computed(() => {
  const plan = growthPlan.value
  if (!plan) return ''
  if (plan.status === 'pending') return 'pending'
  const effect = String(plan.effect_evaluation?.status || 'insufficient_evidence')
  if (effect === 'effective') return 'validated'
  if (effect === 'ineffective' || effect === 'harmful') return 'review'
  return 'active'
})
const growthTrail = computed(() => {
  const operations = growthPlan.value?.operations || []
  const steps: Array<{ key: string; label: string; detail: string }> = []
  if (operations.some((item: Record<string, any>) => item.scope === 'current')) {
    steps.push({
      key: 'current',
      label: t('courseEvolution.growthTrail.current', '当前位置解释'),
      detail: t('courseEvolution.growthTrail.currentDetail', '解释与分步演示'),
    })
  }
  if (operations.some((item: Record<string, any>) => item.operation_type === 'ADD_TRANSITION_SUPPORT')) {
    steps.push({
      key: 'transition',
      label: t('courseEvolution.growthTrail.transition', '下一处承接'),
      detail: t('courseEvolution.growthTrail.transitionDetail', '补充概念过渡'),
    })
  }
  if (operations.some((item: Record<string, any>) => item.operation_type === 'ADD_CHECKPOINT')) {
    steps.push({
      key: 'checkpoint',
      label: t('courseEvolution.growthTrail.checkpoint', '后续顺序检查'),
      detail: t('courseEvolution.growthTrail.checkpointDetail', '在后续推导中复验'),
    })
  }
  return steps
})
const generationState = computed(() => {
  if (!isGenerationPreview.value) return ''
  const status = String(props.node.generation_status || '')
  if (status === 'generating') return 'generating'
  if (status === 'completed' || props.node.content_state === 'finalized') return 'finalized'
  if (status === 'error' || props.node.content_state === 'failed') return 'failed'
  if (props.node.content_state === 'draft' || Boolean(props.node.node_content)) return 'draft'
  return 'waiting'
})
const generationIcon = computed(() => {
  if (generationState.value === 'generating') return LoaderCircle
  if (generationState.value === 'finalized') return CheckCircle2
  if (generationState.value === 'failed') return TriangleAlert
  return null
})
const normalizedQuery = computed(() => props.query.trim().toLocaleLowerCase())
const blockRoleLabel = (role: CourseDocumentBlock['role']) => t(`courseBlocks.${role}`, ({
  orientation: '引入', prerequisite: '前置', objective: '任务', concept: '概念',
  reasoning: '推理', example: '例子', counterexample: '辨析', application: '应用',
  activity: '行动', feedback: '核对', misconception: '易错点', checkpoint: '检查',
  remediation: '补救', summary: '小结', transfer: '迁移',
} as Record<CourseDocumentBlock['role'], string>)[role] || t('courseBlocks.content', '内容'))
const blockEntries = computed(() => (props.node.course_blocks || [])
  .filter(block => block.status !== 'retired')
  .slice()
  .sort((left, right) => left.position - right.position)
  .map((block, index) => ({
    block,
    roleLabel: blockRoleLabel(block.role),
    title: String(block.payload.title || '').trim()
      || `${t('learningNavigator.blockFallback', '内容块')} ${index + 1}`,
  })))
const matchingBlockEntries = computed(() => {
  if (!normalizedQuery.value) return blockEntries.value
  return blockEntries.value.filter(entry => (
    `${entry.roleLabel} ${entry.title}`.toLocaleLowerCase().includes(normalizedQuery.value)
  ))
})
const hasBlockOutline = computed(() => blockEntries.value.length > 0 && !hasChildren.value)
const showBlockOutline = computed(() => hasBlockOutline.value && (
  blockOutlineExpanded.value
  || Boolean(normalizedQuery.value && matchingBlockEntries.value.length)
))
const visibleBlockEntries = computed(() => (
  normalizedQuery.value ? matchingBlockEntries.value : blockEntries.value
))
const hasDisclosure = computed(() => hasChildren.value || hasBlockOutline.value)
const disclosureExpanded = computed(() => (
  hasChildren.value ? expanded.value : showBlockOutline.value
))
const blockOutlineId = computed(() => `course-block-outline-${props.node.node_id}`)
const disclosureId = computed(() => (
  hasChildren.value ? `course-node-children-${props.node.node_id}` : blockOutlineId.value
))
const nodeMatchesQuery = (node: Node): boolean => {
  if (node.node_name.toLocaleLowerCase().includes(normalizedQuery.value)) return true
  if ((node.course_blocks || []).some(block => {
    const title = String(block.payload.title || '')
    return `${blockRoleLabel(block.role)} ${title}`.toLocaleLowerCase().includes(normalizedQuery.value)
  })) return true
  return node.children?.some(nodeMatchesQuery) || false
}
const visible = computed(() => {
  if (!normalizedQuery.value) return true
  return nodeMatchesQuery(props.node)
})
const toggleDisclosure = () => {
  if (hasChildren.value) expanded.value = !expanded.value
  else if (hasBlockOutline.value) {
    if (props.activeId !== props.node.node_id) {
      emit('select', props.node)
      return
    }
    blockOutlineExpanded.value = !blockOutlineExpanded.value
  }
}
const expandDisclosure = () => {
  if (hasChildren.value) expanded.value = true
  else if (hasBlockOutline.value) {
    if (props.activeId !== props.node.node_id) {
      emit('select', props.node)
      return
    }
    blockOutlineExpanded.value = true
  }
}
const collapseDisclosure = () => {
  if (hasChildren.value) expanded.value = false
  else if (hasBlockOutline.value) blockOutlineExpanded.value = false
}
const handleNodeClick = () => {
  if (hasBlockOutline.value && props.activeId === props.node.node_id) {
    toggleDisclosure()
    return
  }
  emit('select', props.node)
}
watch(normalizedQuery, value => { if (value) expanded.value = true })
watch(() => props.activeId, (value, previous) => {
  if (value === props.node.node_id && value !== previous) blockOutlineExpanded.value = true
  if (previous === props.node.node_id && value !== props.node.node_id) blockOutlineExpanded.value = false
})
</script>

<style scoped>
.navigator-node, .navigator-node ul { margin: 0; padding: 0; list-style: none; }
.navigator-node ul { position:relative; margin:1px 0 4px 19px; padding:1px 0 2px 12px; border-left:1px dashed rgba(167,180,214,.72); transition:border-color .18s ease; }
.navigator-node ul:hover { border-left-color:rgba(139,92,246,.52); }
.navigator-node ul::before { content:""; position:absolute; top:0; left:-1px; width:8px; height:1px; background:rgba(165,180,252,.48); }
.node-button { position:relative; width:100%; min-height:38px; display:grid; grid-template-columns:13px 24px minmax(0,1fr) auto auto; align-items:center; gap:7px; overflow:hidden; padding:5px 8px; border:1px solid transparent; border-radius:11px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease,box-shadow .16s ease; }
.node-button::before { content:""; position:absolute; left:0; top:50%; width:3px; height:0; border-radius:0 4px 4px 0; background:linear-gradient(180deg,#818cf8,#7c3aed); transform:translateY(-50%); transition:height .18s ease; }
.node-button:hover { transform:translateX(1px); color:var(--lz-text-strong); background:rgba(255,255,255,.7); }
.node-button.active { border-color:rgba(255,255,255,.9); color:var(--lz-brand-strong); background:linear-gradient(90deg,rgba(255,255,255,.96),rgba(238,242,255,.84)); box-shadow:0 7px 18px rgba(99,102,241,.11),inset 0 1px 0 #fff; font-weight:700; }
.node-button.active::before { height:28px; }
.node-button.level-1 { min-height:42px; margin-top:6px; color:var(--lz-text-strong); font-weight:750; }
.node-button.level-2 { font-weight: 600; }
.node-button > svg:first-child { color:var(--lz-text-muted); transition:transform .16s ease,color .16s ease; }
.node-button > svg:first-child.open { color:#7c3aed; transform:rotate(90deg); }
.node-spacer { width: 13px; }
.node-kind { width:24px; height:24px; display:grid; place-items:center; }
.chapter-kind { border:1px solid rgba(224,231,255,.88); border-radius:8px; color:#6366f1; background:linear-gradient(135deg,#eef2ff,#faf5ff); box-shadow:0 3px 8px rgba(99,102,241,.08); }
.leaf-kind { width:8px; height:8px; margin-left:8px; border:1.5px solid #cbd5e1; border-radius:50%; background:#fff; }
.leaf-kind.learned { border-color:#34d399; background:#d1fae5; }
.leaf-kind.active { border-color:#6366f1; background:#818cf8; box-shadow:0 0 0 3px rgba(129,140,248,.13); }
.leaf-kind.generating { border-color:#6366f1; background:#c7d2fe; }
.leaf-kind.finalized { border-color:#10b981; background:#a7f3d0; }
.leaf-kind.draft { border-color:#8b5cf6; background:#ddd6fe; }
.leaf-kind.failed { border-color:#ef4444; background:#fecaca; }
.node-label { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; letter-spacing:0; }
.adaptation-marker { display:inline-flex; align-items:center; gap:3px; padding:2px 5px; border:1px solid #c4b5fd; border-radius:5px; color:#6d28d9; background:#f5f3ff; font-size:8px; font-weight:700; white-space:nowrap; }
.adaptation-marker b { min-width:12px; height:12px; display:grid; place-items:center; border-radius:50%; color:#fff; background:#8b5cf6; font-size:7px; }
.adaptation-marker[data-state="active"] { border-color:#bfdbfe; color:#1d4ed8; background:#eff6ff; }
.adaptation-marker[data-state="active"] b { background:#3b82f6; }
.adaptation-marker[data-state="validated"] { border-color:#bbf7d0; color:#15803d; background:#f0fdf4; }
.adaptation-marker[data-state="validated"] b { background:#16a34a; }
.adaptation-marker[data-state="review"] { border-color:#fde68a; color:#b45309; background:#fffbeb; }
.adaptation-marker[data-state="review"] b { background:#d97706; }
.course-block-outline { position:relative; display:grid; gap:1px; margin:1px 7px 7px 55px; padding:3px 0 3px 10px; border-left:1px solid rgba(165,180,252,.52); list-style:none; }
.course-block-outline::before { content:""; position:absolute; top:0; left:-1px; width:7px; height:1px; background:rgba(165,180,252,.56); }
.course-block-outline li { min-width:0; margin:0; padding:0; }
.course-block-link { --block-role-color:#64748b; width:100%; min-height:28px; display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:6px; padding:3px 6px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-muted); background:transparent; text-align:left; cursor:pointer; transition:color .15s ease,background .15s ease,border-color .15s ease,transform .15s ease; }
.course-block-link:hover,.course-block-link:focus-visible { color:var(--lz-text-strong); border-color:rgba(224,231,255,.82); background:rgba(255,255,255,.82); outline:none; transform:translateX(1px); }
.course-block-link.active { border-color:rgba(199,210,254,.78); color:var(--lz-brand-strong); background:linear-gradient(90deg,rgba(238,242,255,.94),rgba(250,250,255,.72)); box-shadow:inset 2px 0 0 var(--block-role-color); }
.course-block-role { display:inline-flex; align-items:center; min-height:16px; padding:1px 4px; border-radius:4px; color:var(--block-role-color); background:color-mix(in srgb,var(--block-role-color) 8%,white); font-size:8px; font-weight:800; line-height:1; white-space:nowrap; }
.course-block-title { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:9px; font-weight:600; letter-spacing:0; }
.course-block-link[data-role="orientation"] { --block-role-color:#7c3aed; }
.course-block-link[data-role="objective"],.course-block-link[data-role="concept"] { --block-role-color:#4f46e5; }
.course-block-link[data-role="reasoning"] { --block-role-color:#0f766e; }
.course-block-link[data-role="example"] { --block-role-color:#b45309; }
.course-block-link[data-role="counterexample"],.course-block-link[data-role="misconception"] { --block-role-color:#b91c1c; }
.course-block-link[data-role="application"] { --block-role-color:#0e7490; }
.course-block-link[data-role="activity"],.course-block-link[data-role="checkpoint"] { --block-role-color:#be185d; }
.course-block-link[data-role="feedback"] { --block-role-color:#047857; }
.course-block-link[data-role="remediation"] { --block-role-color:#c2410c; }
.course-block-link[data-role="summary"],.course-block-link[data-role="transfer"] { --block-role-color:#6d28d9; }
.growth-trail { display:grid; gap:5px; margin:1px 8px 7px 56px; padding:4px 0 2px; list-style:none; }
.growth-trail li { min-width:0; display:grid; grid-template-columns:8px minmax(0,1fr); align-items:start; gap:7px; color:#6d28d9; }
.growth-trail li > span { width:7px; height:7px; margin-top:4px; border:2px solid currentColor; border-radius:50%; background:#fff; }
.growth-trail li:not(:last-child) > span::after { content:""; display:block; width:1px; height:23px; margin:5px 0 0 1px; background:currentColor; opacity:.28; }
.growth-trail li > div { min-width:0; display:flex; align-items:baseline; gap:6px; }
.growth-trail b { flex:0 0 auto; font-size:9px; letter-spacing:0; }
.growth-trail small { min-width:0; overflow:hidden; color:var(--lz-text-muted); text-overflow:ellipsis; white-space:nowrap; font-size:8px; letter-spacing:0; }
.growth-trail[data-state="active"] li { color:#2563eb; }
.growth-trail[data-state="validated"] li { color:#16a34a; }
.growth-trail[data-state="review"] li { color:#d97706; }
.status { flex: 0 0 auto; }
.status.mastered { color: var(--lz-success); }
.status.current { color: var(--lz-brand); }
.status.generation.generating { color:#4f46e5; }
.status.generation.finalized { color:#059669; }
.status.generation.failed { color:#dc2626; }
.status.spinning { animation:navigator-generation-spin .9s linear infinite; }
.read-dot { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; }
@media (max-width:1023px) {
  .course-block-link { min-height:36px; padding:5px 6px; }
  .course-block-role { min-height:18px; font-size:9px; }
  .course-block-title { font-size:10px; }
}
@keyframes navigator-generation-spin { to { transform:rotate(360deg); } }
</style>
