<template>
  <section v-if="sectionId || visiblePlans.length" class="evolution-panel" aria-live="polite">
    <header>
      <span><GitBranchPlus :size="14" /></span>
      <div><small>{{ t('courseEvolution.eyebrow', '统一课程调整') }}</small><strong>{{ t('courseEvolution.title', '调整课程') }}</strong></div>
      <button type="button" :title="t('courseEvolution.refresh', '重新分析学习证据')" :aria-label="t('courseEvolution.refresh', '重新分析学习证据')" :disabled="store.loading" @click="store.evaluate(courseId)"><RefreshCw :size="14" :class="{ spinning: store.loading }" /></button>
    </header>

    <div class="growth-insight-switcher">
      <button type="button" :class="{ active: mapOpen }" @click="mapOpen = !mapOpen; evidenceOpen = false">
        <MapPinned :size="12" />
        <span>{{ t('courseEvolution.personalMap.open', '个人学习地图') }}</span>
        <b>{{ learningMapSummary.changed }}</b>
      </button>
      <button type="button" :class="{ active: evidenceOpen }" @click="evidenceOpen = !evidenceOpen; mapOpen = false">
        <History :size="12" />
        <span>{{ t('courseEvolution.evidenceTimeline.open', '学习证据轨迹') }}</span>
        <b>{{ evidenceTimeline.length }}</b>
      </button>
    </div>

    <section v-if="mapOpen" class="personal-learning-map" aria-live="polite">
      <header>
        <span><MapPinned :size="14" /></span>
        <div>
          <small>{{ t('courseEvolution.personalMap.eyebrow', '每个学生留下不同的课程版本') }}</small>
          <strong>{{ t('courseEvolution.personalMap.title', '我的学习地图与成长教材') }}</strong>
        </div>
      </header>
      <dl class="personal-map-stats">
        <div><dt>{{ t('courseEvolution.personalMap.retained', '按原路径') }}</dt><dd>{{ learningMapSummary.retained }}</dd></div>
        <div><dt>{{ t('courseEvolution.personalMap.supplemented', '已补充') }}</dt><dd>{{ learningMapSummary.supplemented }}</dd></div>
        <div><dt>{{ t('courseEvolution.personalMap.upgraded', '已升级') }}</dt><dd>{{ learningMapSummary.upgraded }}</dd></div>
        <div><dt>{{ t('courseEvolution.personalMap.folded', '已折叠') }}</dt><dd>{{ learningMapSummary.folded }}</dd></div>
      </dl>
      <ol class="personal-map-path">
        <li v-for="item in learningMapItems" :key="item.sectionId" :data-state="item.state">
          <span>{{ item.order }}</span>
          <div>
            <strong>{{ item.title }}</strong>
            <small>{{ personalMapStateLabel(item.state) }} · {{ item.reason }}</small>
          </div>
          <b>{{ item.evidenceCount }}</b>
        </li>
      </ol>
      <p><ShieldCheck :size="12" />{{ t('courseEvolution.personalMap.guard', '地图只属于当前学生；原始提问、笔记、错题和作答仍保留在证据轨迹中。') }}</p>
    </section>

    <section v-if="evidenceOpen" class="evidence-timeline">
      <header>
        <span><History :size="14" /></span>
        <div>
          <small>{{ t('courseEvolution.evidenceTimeline.eyebrow', '先保留事实，再形成判断') }}</small>
          <strong>{{ t('courseEvolution.evidenceTimeline.title', '可追溯的学习证据轨迹') }}</strong>
        </div>
      </header>
      <ol v-if="evidenceTimeline.length">
        <li v-for="evidence in evidenceTimeline" :key="evidence.evidence_id" :data-counter="Boolean(evidence.is_counterevidence)">
          <span><component :is="evidenceIcon(evidence.source_type)" :size="12" /></span>
          <div>
            <b>{{ evidenceKindLabel(evidence) }}</b>
            <p>{{ evidence.summary }}</p>
            <small>{{ evidenceLocationLabel(evidence) }} · {{ evidenceStrengthLabel(evidence) }}</small>
          </div>
          <button type="button" :title="t('courseEvolution.locateEvidence', '回到证据位置')" @click="locateEvidence(evidence)"><LocateFixed :size="12" /></button>
        </li>
      </ol>
      <p v-else class="evidence-empty">{{ t('courseEvolution.evidenceTimeline.empty', '继续提问、记笔记或完成练习后，证据会出现在这里。') }}</p>
    </section>

    <div v-if="sectionId" class="section-growth-request">
      <ol class="growth-steps" :aria-label="t('courseEvolution.sectionGrowth.stepsLabel', '课程生长六步')">
        <li v-for="step in growthSteps" :key="step.index" :class="{ active: step.index === currentGrowthStep, done: step.index < currentGrowthStep }">
          <b>{{ step.index }}</b><span>{{ step.label }}</span>
        </li>
      </ol>
      <label>
        <span>{{ t('courseEvolution.sectionGrowth.prompt', '你希望课程怎样变化？') }}</span>
        <input
          v-model="sectionInstruction"
          type="text"
          :placeholder="t('courseEvolution.sectionGrowth.placeholder', '例如：以后所有例子都讲得更详细一点')"
        >
      </label>
      <div class="request-scope-control" role="radiogroup" :aria-label="t('courseEvolution.scope.label', '选择这句话可以影响的课程范围')">
        <button
          type="button"
          data-scope="current_section"
          role="radio"
          :aria-checked="requestScope === 'current_section'"
          :class="{ active: requestScope === 'current_section' }"
          @click="requestScope = 'current_section'"
        >
          <LocateFixed :size="12" />
          <span><b>{{ t('courseEvolution.scope.currentSection', '只影响当前小节') }}</b><small>{{ t('courseEvolution.scope.currentSectionHint', 'AI 只能在这一节内找目标') }}</small></span>
        </button>
        <button
          type="button"
          data-scope="whole_course"
          role="radio"
          :aria-checked="requestScope === 'whole_course'"
          :class="{ active: requestScope === 'whole_course' }"
          @click="requestScope = 'whole_course'"
        >
          <BookOpenText :size="12" />
          <span><b>{{ t('courseEvolution.scope.wholeCourse', '应用到全课程') }}</b><small>{{ t('courseEvolution.scope.wholeCourseHint', 'AI 解析语义后匹配相关节点') }}</small></span>
        </button>
      </div>
      <button type="button" class="generate-plan" :disabled="store.generating || !sectionInstruction.trim()" @click="createSectionPlan">
        <LoaderCircle v-if="store.generating" :size="13" class="spinning" />
        <Sparkles v-else :size="13" />
        {{
          store.generating
            ? t('courseEvolution.sectionGrowth.generating', '正在生成候选')
            : requestScope === 'whole_course'
              ? t('courseEvolution.sectionGrowth.generateWholeCourse', '解析并生成全课程影响预览')
              : t('courseEvolution.sectionGrowth.generate', '生成本节调整方案')
        }}
      </button>
      <p v-if="store.generationError" class="generation-error"><TriangleAlert :size="12" />{{ store.generationError }}</p>
    </div>

    <button
      v-for="plan in workbenchPlans"
      :key="`scan-${plan.change_set_id}`"
      type="button"
      class="whole-course-scan-summary"
      :data-status="plan.generation_status || 'ready'"
      @click="openReview(plan)"
    >
      <span>
        <LoaderCircle v-if="plan.generation_status === 'generating'" :size="16" class="spinning" />
        <TriangleAlert v-else-if="plan.generation_status === 'failed'" :size="16" />
        <CheckCircle2 v-else :size="16" />
      </span>
      <div>
        <small>{{ reviewPlanStatus(plan) }}</small>
        <strong>{{ plan.request_text || diagnosisFor(plan) }}</strong>
        <em>{{ reviewPlanSummary(plan) }}</em>
      </div>
      <ArrowRight :size="15" />
    </button>

    <article
      v-for="plan in inlinePlans"
      :key="plan.change_set_id"
      :ref="element => setPlanElement(plan.change_set_id, element)"
      :class="{ 'is-focus-plan': props.focusPlanId === plan.change_set_id }"
      :data-status="plan.status"
      :data-effect="planEffectState(plan)"
    >
      <template v-if="plan.status === 'pending'">
        <div v-if="plan.generation_status === 'suggested'" class="challenge-suggestion">
          <span><BadgeCheck :size="14" />{{ t('courseEvolution.sectionGrowth.challengeReady', '当前难度已稳定通过') }}</span>
          <strong>{{ diagnosisFor(plan) }}</strong>
          <p>{{ t('courseEvolution.sectionGrowth.masteryPreserved', '旧难度掌握记录会保留；先生成更高挑战候选，确认后才更新课程。') }}</p>
          <button type="button" :disabled="store.actingId === plan.change_set_id" @click="generateSuggested(plan)">
            <LoaderCircle v-if="store.actingId === plan.change_set_id" :size="13" class="spinning" />
            <ArrowRight v-else :size="13" />
            {{ t('courseEvolution.sectionGrowth.generateChallenge', '生成升级方案') }}
          </button>
        </div>
        <template v-else>
        <div class="plan-source">
          <span>{{ isManualPlan(plan) ? t('courseEvolution.sectionGrowth.manualSource', '按你的要求') : t('courseEvolution.sectionGrowth.evidenceSource', '由学习证据触发') }}</span>
          <b v-if="plan.growth_direction === 'challenge'">{{ t('courseEvolution.sectionGrowth.challenge', '提高挑战') }}</b>
        </div>
        <div
          v-if="isStrongScopedPlan(plan)"
          class="strong-evidence-trigger"
          role="status"
          :aria-label="t('courseEvolution.strongTrigger.eyebrow', '已识别强学习证据')"
        >
          <span><Sparkles :size="13" />{{ t('courseEvolution.strongTrigger.eyebrow', '已识别强学习证据') }}</span>
          <strong>
            {{
              (plan.impact_summary?.dependent_block_ids?.length || 0) > 0
                ? t('courseEvolution.strongTrigger.scopeSummary', '已生成本小节与 {count} 个相关后续节点的生长方案')
                  .replace('{count}', String(plan.impact_summary?.dependent_block_ids?.length || 0))
                : t('courseEvolution.strongTrigger.localSummary', '已生成本小节的生长方案')
            }}
          </strong>
          <small>{{ evidenceAssessment(plan).gate_reason || t('courseEvolution.strongTrigger.reason', '系统同时识别了已会内容、持续困难、需要的讲法和明确范围；确认前课程保持不变。') }}</small>
          <div class="strong-evidence-dimensions">
            <template v-for="dimension in contractDimensions(plan)" :key="dimension.key">
              <b>{{ dimension.label }}</b>
              <em v-if="dimension.value">{{ dimension.value }}</em>
            </template>
          </div>
        </div>
        <div
          v-if="isStrongScopedPlan(plan)"
          class="strong-growth-plan"
          :aria-label="t('courseEvolution.strongTrigger.planTitle', '课程生长方案')"
        >
          <div class="strong-growth-heading">
            <span><Layers3 :size="13" />{{ t('courseEvolution.strongTrigger.planTitle', '课程生长方案') }}</span>
            <small>
              {{
                t('courseEvolution.strongTrigger.planCount', '{count} 项课程变化，确认后一次写入')
                  .replace('{count}', String(contentOperations(plan).length))
              }}
            </small>
          </div>
          <div
            v-for="group in strongGrowthGroups(plan)"
            :key="group.key"
            class="strong-growth-group"
            :data-scope="group.key"
          >
            <span>{{ group.label }}</span>
            <p>
              <b v-for="item in group.items" :key="item">{{ item }}</b>
            </p>
          </div>
        </div>
        <div v-if="isManualPlan(plan)" class="semantic-scope-summary" :data-scope="plan.scope_selection || 'current_section'">
          <span>
            <component :is="plan.scope_selection === 'whole_course' ? BookOpenText : LocateFixed" :size="13" />
            {{ planScopeLabel(plan) }}
          </span>
          <strong>{{ planScopeSummary(plan) }}</strong>
          <small>{{ String(plan.impact_summary?.matching_policy || '') }}</small>
        </div>
        <div v-if="evidenceFor(plan).length" class="evolution-evidence" :aria-label="t('courseEvolution.evidenceConvergence', '多类证据汇聚')">
          <template v-for="(evidence, index) in evidenceFor(plan)" :key="evidence.evidence_id">
            <span :data-source="evidence.source_type">
              <component :is="evidenceIcon(evidence.source_type)" :size="12" />{{ evidenceLabel(evidence.source_type) }}
            </span>
            <ArrowRight v-if="index < evidenceFor(plan).length - 1" :size="10" />
          </template>
        </div>
        <div v-if="evidenceFor(plan).length" class="evidence-maturity" :data-maturity="evidenceAssessment(plan).maturity || 'observing'">
          <span>
            <Network :size="11" />
            {{ t('courseEvolution.independentSources', '{count} 类独立来源').replace('{count}', String(evidenceAssessment(plan).independent_source_count || 0)) }}
          </span>
          <span v-if="evidenceAssessment(plan).has_formal_evidence">
            <BadgeCheck :size="11" />{{ t('courseEvolution.formalEvidenceIncluded', '含正式证据') }}
          </span>
          <span v-if="evidenceAssessment(plan).has_explicit_scope">
            <LocateFixed :size="11" />{{ t('courseEvolution.explicitScopeIncluded', '范围由学生明确指定') }}
          </span>
          <span>
            <ShieldCheck :size="11" />
            {{
              evidenceAssessment(plan).counterevidence_count
                ? t('courseEvolution.counterevidenceIncluded', '已纳入 {count} 条反证').replace('{count}', String(evidenceAssessment(plan).counterevidence_count))
                : t('courseEvolution.noCounterevidence', '暂无反证冲突')
            }}
          </span>
        </div>
        <div class="evolution-diagnosis">
          <span><BrainCircuit :size="14" />{{ sceneLabelFor(plan) }}</span>
          <strong>{{ sceneSummaryFor(plan) }}</strong>
          <small v-if="sceneRationaleFor(plan)">{{ sceneRationaleFor(plan) }}</small>
        </div>
        <p
          v-if="sourceMessageFor(plan)"
          class="source-requirement"
          :data-status="sceneAnalysisFor(plan).source_status || 'verification_required'"
        >
          <TriangleAlert :size="13" />{{ sourceMessageFor(plan) }}
        </p>
        <div v-if="impactLabels(plan).length" class="evolution-impact">
          <span v-for="label in impactLabels(plan)" :key="label">{{ label }}</span>
          <small v-if="plan.impact_summary?.dependent_block_ids?.length">
            {{ t('courseEvolution.dependentBlocks', '关联后续 {count} 个教学块').replace('{count}', String(plan.impact_summary.dependent_block_ids.length)) }}
          </small>
        </div>
        <p class="evolution-effect"><Sparkles :size="13" />{{ plan.expected_effect }}</p>
        <button type="button" class="evolution-details-toggle" @click="expandedId = expandedId === plan.change_set_id ? '' : plan.change_set_id">
          <ChevronUp v-if="expandedId === plan.change_set_id" :size="13" /><ChevronDown v-else :size="13" />
          {{ expandedId === plan.change_set_id ? t('courseEvolution.hideDetails', '收起依据与范围') : t('courseEvolution.showDetails', '查看依据与范围') }}
        </button>
        <div v-if="expandedId === plan.change_set_id" class="evolution-details">
          <p v-for="evidence in evidenceFor(plan)" :key="evidence.evidence_id">
            <b>{{ evidenceLabel(evidence.source_type) }}</b>
            <span>{{ evidence.summary }}</span>
            <button type="button" :title="t('courseEvolution.locateEvidence', '回到证据位置')" :aria-label="t('courseEvolution.locateEvidence', '回到证据位置')" @click="locateEvidence(evidence)"><LocateFixed :size="12" /></button>
          </p>
          <ul v-if="plan.scope_selection !== 'whole_course'" class="operation-list">
            <li v-for="operation in contentOperations(plan)" :key="operation.operation_id">
              <span :data-action="operation.payload?.action">{{ operationActionLabel(operation) }}</span>
              <div>
                <b>{{ operationLabel(operation.operation_type, operation.payload?.desired_role) }}</b>
                <p>{{ operation.reason }}</p>
                <details v-if="operation.payload?.after_preview">
                  <summary>{{ t('courseEvolution.sectionGrowth.preview', '查看候选') }}</summary>
                  <div v-if="operation.payload?.before_preview" class="candidate-before">
                    <small>{{ t('courseEvolution.sectionGrowth.before', '原内容') }}</small>
                    <p>{{ operation.payload.before_preview }}</p>
                  </div>
                  <div class="candidate-after">
                    <small>{{ operation.payload?.action === 'INSERT' ? t('courseEvolution.sectionGrowth.newContent', '新增内容') : t('courseEvolution.sectionGrowth.after', '升级后') }}</small>
                    <p>{{ operation.payload.after_preview }}</p>
                  </div>
                </details>
              </div>
            </li>
          </ul>
          <button
            v-else
            type="button"
            class="whole-course-review-trigger"
            @click="openReview(plan)"
          >
            <Layers3 :size="14" />
            <span>
              <b>{{ t('courseEvolution.review.open', '打开多节点生成预览') }}</b>
              <small>{{ t('courseEvolution.review.openHint', '逐项查看、纳入或排除 {count} 个节点').replace('{count}', String(contentOperations(plan).length)) }}</small>
            </span>
            <ArrowRight :size="13" />
          </button>
          <p v-if="plan.impact_summary?.quality_report?.passed" class="same-source-check">
            <BadgeCheck :size="13" />
            {{ t('courseEvolution.sectionGrowth.sameSourcePassed', '结构化同源检查已通过：所有候选仍绑定本节知识点、能力点与掌握标准') }}
          </p>
          <p class="validation-plan"><ScanSearch :size="13" /><b>{{ t('courseEvolution.validation', '效果复验') }}</b>{{ validationFor(plan) }}</p>
          <p class="protected"><ShieldCheck :size="13" />{{ t('courseEvolution.protected', '只修改当前课程所选范围；不修改其他课程、历史作答和笔记原文') }}</p>
        </div>
        <div class="scope-control" v-if="plan.allowed_scopes.length > 1">
          <button type="button" :class="{ active: selectedScope[plan.change_set_id] !== 'current_and_next' }" @click="selectedScope[plan.change_set_id] = 'current'">{{ t('courseEvolution.currentOnly', '只应用本小节') }}</button>
          <button type="button" :class="{ active: selectedScope[plan.change_set_id] === 'current_and_next' }" @click="selectedScope[plan.change_set_id] = 'current_and_next'">{{ t('courseEvolution.currentAndNext', '本小节及后续') }}</button>
        </div>
        <div class="evolution-actions">
          <button
            v-if="requiresWorkbench(plan)"
            type="button"
            class="primary"
            :disabled="store.actingId === plan.change_set_id || plan.generation_status !== 'ready'"
            @click="openReview(plan)"
          >
            <Layers3 :size="13" />
            {{ t('courseEvolution.review.reviewNodes', '审阅 {count} 个节点').replace('{count}', String(contentOperations(plan).length)) }}
          </button>
          <button v-else type="button" class="primary" :disabled="store.actingId === plan.change_set_id || plan.generation_status !== 'ready'" @click="accept(plan)"><LoaderCircle v-if="store.actingId === plan.change_set_id" :size="13" class="spinning" /><Check v-else :size="13" />{{ t('courseEvolution.accept', '整体确认并更新课程') }}</button>
          <button type="button" :disabled="store.actingId === plan.change_set_id" @click="store.reject(plan.change_set_id)"><X :size="13" />{{ t('courseEvolution.reject', '暂不调整') }}</button>
        </div>
        </template>
      </template>
      <template v-else>
        <div class="applied-growth">
          <component :is="effectIcon(plan)" :size="15" />
          <span>
            <strong>{{ effectTitle(plan) }}</strong>
            <small>{{ effectLabel(plan) }}</small>
          </span>
          <button v-if="plan.effect_evaluation?.status === 'ineffective'" type="button" :disabled="store.actingId === plan.change_set_id" @click="adjust(plan)"><RefreshCw :size="13" />{{ t('courseEvolution.adjust', '生成调整方案') }}</button>
          <button v-else type="button" @click="undo(plan)"><Undo2 :size="13" />{{ plan.effect_evaluation?.status === 'harmful' ? t('courseEvolution.rollback', '确认回退') : t('courseEvolution.undo', '撤销') }}</button>
        </div>
        <p class="applied-diagnosis">{{ diagnosisFor(plan) }}</p>
        <div v-if="verificationFor(plan)" class="verification-flow">
          <div>
            <small>{{ t('courseEvolution.verification.baseline', '调整前') }}</small>
            <strong>{{ attemptResultLabel(verificationFor(plan).baseline) }}</strong>
          </div>
          <ArrowRight :size="12" />
          <div>
            <small>{{ t('courseEvolution.verification.courseChange', '课程生长') }}</small>
            <strong>{{ t('courseEvolution.verification.blockCount', '{count} 个教学块').replace('{count}', String(verificationFor(plan).course_change?.applied_block_count || 0)) }}</strong>
          </div>
          <ArrowRight :size="12" />
          <div>
            <small>{{ t('courseEvolution.verification.followUp', '独立复验') }}</small>
            <strong>{{ attemptResultLabel(verificationFor(plan).follow_up) }}</strong>
          </div>
        </div>
        <p v-if="verificationFor(plan)?.interpretation" class="verification-interpretation">
          <ScanSearch :size="12" />{{ verificationFor(plan).interpretation }}
        </p>
      </template>
    </article>
  </section>
  <CourseEvolutionReviewOverlay
    v-if="reviewOverlayOpen"
    :plan="reviewPlan"
    :instruction="reviewInstruction"
    :generating="reviewGenerating"
    :error="reviewError"
    :selected-scope="reviewPlan ? (selectedScope[reviewPlan.change_set_id] || 'current') : 'current'"
    :selected-operation-ids="reviewSelectionIds"
    :acting="Boolean(reviewPlan && store.actingId === reviewPlan.change_set_id)"
    @update:selected-operation-ids="reviewPlan && updateReviewSelection(reviewPlan.change_set_id, $event)"
    @apply="reviewPlan && acceptSelected(reviewPlan)"
    @close="closeReview"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ArrowRight, BadgeCheck, BookOpenText, BrainCircuit, Check, CheckCircle2, ChevronDown, ChevronUp, CircleDot, FileQuestion, GitBranchPlus, History, Layers3, LoaderCircle, LocateFixed, MapPinned, Network, NotebookTabs, RefreshCw, ScanSearch, Sparkles, TriangleAlert, Undo2, X, ShieldCheck } from 'lucide-vue-next'
import CourseEvolutionReviewOverlay from './CourseEvolutionReviewOverlay.vue'
import {
  useCourseEvolutionStore,
  type CourseEvolutionApplicationPresentation,
  type CourseEvolutionPlan,
  type EvolutionEvidence,
  type EvolutionOperation,
} from '../stores/courseEvolution'
import { useCourseStore } from '../stores/course'
import { useLearningProgressStore } from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = defineProps<{ courseId: string; sectionId?: string; focusPlanId?: string }>()
const emit = defineEmits<{
  courseApplied: [presentation: CourseEvolutionApplicationPresentation]
}>()
const store = useCourseEvolutionStore()
const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const expandedId = ref('')
const mapOpen = ref(false)
const evidenceOpen = ref(false)
const sectionInstruction = ref('')
const requestScope = ref<'current_section' | 'whole_course'>('current_section')
const reviewPlanId = ref('')
const reviewOverlayOpen = ref(false)
const reviewScanInFlight = ref(false)
const reviewInstruction = ref('')
const reviewError = ref('')
const selectedScope = reactive<Record<string, 'current' | 'current_and_next'>>({})
const reviewSelections = reactive<Record<string, string[]>>({})
const reviewSeenOperations = reactive<Record<string, string[]>>({})
const planElements = new Map<string, HTMLElement>()
const visiblePlans = computed(() => {
  const matchesSection = (plan: CourseEvolutionPlan) => (
    !props.sectionId
    || plan.target_section_id === props.sectionId
    || (plan.impact_summary?.affected_section_ids || []).includes(props.sectionId)
  )
  return [
    ...store.pendingPlans.filter(matchesSection),
    ...store.appliedPlans.filter(matchesSection).slice(-1),
  ]
})
const inlinePlans = computed(() => visiblePlans.value.filter(plan => !requiresWorkbench(plan)))
const workbenchPlans = computed(() => visiblePlans.value.filter(requiresWorkbench))
const reviewPlan = computed(() => (
  store.plans.find(plan => plan.change_set_id === reviewPlanId.value) || null
))
const reviewGenerating = computed(() => Boolean(
  reviewScanInFlight.value || reviewPlan.value?.generation_status === 'generating',
))
const reviewSelectionIds = computed(() => (
  reviewPlan.value ? reviewSelections[reviewPlan.value.change_set_id] || [] : []
))
const growthSteps = computed(() => [
  { index: 1, label: t('courseEvolution.sectionGrowth.steps.request', '需求') },
  { index: 2, label: t('courseEvolution.sectionGrowth.steps.structure', '结构') },
  { index: 3, label: t('courseEvolution.sectionGrowth.steps.candidates', '候选') },
  { index: 4, label: t('courseEvolution.sectionGrowth.steps.sameSource', '同源') },
  { index: 5, label: t('courseEvolution.sectionGrowth.steps.confirm', '确认') },
  { index: 6, label: t('courseEvolution.sectionGrowth.steps.validate', '复验') },
])
const currentGrowthStep = computed(() => {
  if (store.generating) return 3
  const current = visiblePlans.value[0]
  if (!current) return 1
  if (current.status === 'applied') return 6
  if (current.generation_status === 'suggested') return 2
  if (current.generation_status === 'ready') return 5
  return 3
})
type PersonalMapState = 'retained' | 'supplemented' | 'upgraded' | 'folded' | 'reorganized'
const evidenceTimeline = computed(() => (
  [...store.evidenceItems]
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
    .slice(0, 12)
))
const learningMapItems = computed(() => (
  courseStore.nodes
    .filter(node => Boolean(node.course_blocks?.length))
    .map((node, index) => {
      const sectionId = String(node.node_id || '')
      const sectionPlans = store.plans.filter(plan => (
        plan.target_section_id === sectionId
        || (plan.impact_summary?.affected_section_ids || []).map(String).includes(sectionId)
        || plan.operations.some(operation => operation.target_section_id === sectionId)
      ))
      const activePlans = sectionPlans.filter(plan => ['pending', 'applied'].includes(plan.status))
      const operations = activePlans.flatMap(plan => plan.operations.filter(operation => (
        operation.target_section_id === sectionId
      )))
      let state: PersonalMapState = 'retained'
      if (operations.some(operation => operation.operation_type === 'FOLD_COURSE_BLOCK')) state = 'folded'
      else if (operations.some(operation => operation.operation_type === 'REORDER_COURSE_BLOCK')) state = 'reorganized'
      else if (activePlans.some(plan => plan.growth_direction === 'challenge')) state = 'upgraded'
      else if (operations.length) state = 'supplemented'
      const sectionEvidence = store.evidenceItems.filter(evidence => evidence.anchor?.section_id === sectionId)
      const latestPlan = activePlans.at(-1)
      return {
        sectionId,
        order: String(index + 1).padStart(2, '0'),
        title: String(node.node_name || sectionId),
        state,
        evidenceCount: sectionEvidence.length,
        reason: String(
          latestPlan?.impact_summary?.diagnosis
          || latestPlan?.expected_effect
          || (
            progressStore.nodeProgress(sectionId)?.mastery_status === 'mastered'
              ? t('courseEvolution.personalMap.masteredReason', '正式学习证据已掌握，复习时可快速通过')
              : t('courseEvolution.personalMap.retainedReason', '当前证据支持保留原有学习路径')
          ),
        ),
      }
    })
))
const learningMapSummary = computed(() => {
  const counts = {
    retained: 0,
    supplemented: 0,
    upgraded: 0,
    folded: 0,
    reorganized: 0,
    changed: 0,
  }
  for (const item of learningMapItems.value) counts[item.state] += 1
  counts.changed = learningMapItems.value.length - counts.retained
  return counts
})

function evidenceFor(plan: CourseEvolutionPlan) { return store.evidenceItems.filter(item => plan.evidence_ids.includes(item.evidence_id)) }
function hypothesisFor(plan: CourseEvolutionPlan) { return store.hypotheses.find(item => item.hypothesis_id === plan.hypothesis_id) }
function diagnosisFor(plan: CourseEvolutionPlan) { return String(plan.impact_summary?.diagnosis || hypothesisFor(plan)?.claim || t('courseEvolution.diagnosisFallback', '多条证据共同指向当前理解缺口')) }
function sceneAnalysisFor(plan: CourseEvolutionPlan) { return (plan.impact_summary?.scene_analysis || {}) as Record<string, any> }
function sceneLabelFor(plan: CourseEvolutionPlan) {
  const source = sceneAnalysisFor(plan).analysis_source
  if (source === 'ai_semantic') return t('courseEvolution.sectionGrowth.aiScene', 'AI 场景理解')
  if (source === 'deterministic_fallback') return t('courseEvolution.sectionGrowth.ruleFallback', '规则保底判断')
  return t('courseEvolution.diagnosis', 'AI 学习判断')
}
function sceneSummaryFor(plan: CourseEvolutionPlan) { return String(sceneAnalysisFor(plan).scene_summary || diagnosisFor(plan)) }
function sceneRationaleFor(plan: CourseEvolutionPlan) { return String(sceneAnalysisFor(plan).rationale || '') }
function sourceMessageFor(plan: CourseEvolutionPlan) {
  const scene = sceneAnalysisFor(plan)
  if (!scene.source_requirement || scene.source_requirement === 'course_only') return ''
  if (scene.source_status === 'available_materials') {
    return t('courseEvolution.sectionGrowth.boundMaterialsOnly', '这次生成只会使用当前课程已绑定并允许引用的资料。')
  }
  return scene.source_requirement === 'verified_current_sources'
    ? t('courseEvolution.sectionGrowth.currentSourcesRequired', '这个要求涉及最新、前沿或当前行业事实，目前需要可信时效资料；候选不会把模型记忆当成行业证据。')
    : t('courseEvolution.sectionGrowth.materialsRequired', '这个要求需要可信资料；在资料完成绑定前，候选只生成不依赖外部事实的教学框架。')
}
function validationFor(plan: CourseEvolutionPlan) { return String(plan.impact_summary?.validation_plan || hypothesisFor(plan)?.validation_plan || t('courseEvolution.validationFallback', '用后续同能力正式题检验调整是否有效')) }
function evidenceLabel(source: EvolutionEvidence['source_type']) { return ({ learning_event: t('courseEvolution.sources.dialogue', '对话与反馈'), learning_record: t('courseEvolution.sources.record', '学习记录'), practice_attempt: t('courseEvolution.sources.practice', '正式练习') })[source] }
function evidenceIcon(source: EvolutionEvidence['source_type']) { return ({ learning_event: FileQuestion, learning_record: NotebookTabs, practice_attempt: BookOpenText })[source] }
function evidenceKindLabel(evidence: EvolutionEvidence) {
  return ({
    learner_question: t('courseEvolution.evidenceTimeline.question', 'AI 问答'),
    explicit_comprehension_gap: t('courseEvolution.evidenceTimeline.selfReport', '思维自述'),
    adaptive_feedback: t('courseEvolution.evidenceTimeline.feedback', '学习反馈'),
    record_note: t('courseEvolution.evidenceTimeline.note', '个性化笔记'),
    record_issue: t('courseEvolution.evidenceTimeline.wrong', '错题与疑点'),
    record_review_task: t('courseEvolution.evidenceTimeline.reviewTask', '复习任务'),
    formal_success: t('courseEvolution.evidenceTimeline.practiceSuccess', '正式练习通过'),
    formal_failure: t('courseEvolution.evidenceTimeline.practiceFailure', '正式练习未通过'),
  } as Record<string, string>)[evidence.evidence_kind] || evidenceLabel(evidence.source_type)
}
function evidenceLocationLabel(evidence: EvolutionEvidence) {
  const node = courseStore.nodes.find(item => item.node_id === evidence.anchor?.section_id)
  return String(node?.node_name || t('courseEvolution.evidenceTimeline.courseLevel', '课程级证据'))
}
function evidenceStrengthLabel(evidence: EvolutionEvidence) {
  if (evidence.is_counterevidence) return t('courseEvolution.evidenceTimeline.counter', '反证/已会信号')
  if (evidence.strength >= 0.82) return t('courseEvolution.evidenceTimeline.strong', '强证据')
  if (evidence.strength >= 0.55) return t('courseEvolution.evidenceTimeline.medium', '中等证据')
  return t('courseEvolution.evidenceTimeline.weak', '观察信号')
}
function personalMapStateLabel(state: PersonalMapState) {
  return ({
    retained: t('courseEvolution.personalMap.retained', '按原路径'),
    supplemented: t('courseEvolution.personalMap.supplemented', '已补充'),
    upgraded: t('courseEvolution.personalMap.upgraded', '已升级'),
    folded: t('courseEvolution.personalMap.folded', '已折叠'),
    reorganized: t('courseEvolution.personalMap.reorganized', '已重组'),
  } as Record<PersonalMapState, string>)[state]
}
function operationLabel(type: string, role = '') { return ({ INSERT_COURSE_SUPPORT: t('courseEvolution.operations.explanation', '补充解释'), INSERT_PERSONAL_SUPPORT: t('courseEvolution.operations.explanation', '补充解释'), ADD_TRANSITION_SUPPORT: t('courseEvolution.operations.transition', '后续承接'), ADD_CHECKPOINT: t('courseEvolution.operations.checkpoint', '理解检查'), ADD_TARGETED_PRACTICE: t('courseEvolution.operations.targetedPractice', '针对性练习'), ADD_ANIMATION: t('courseEvolution.operations.animation', '分步演示'), REPLACE_COURSE_BLOCK: roleLabel(role), INSERT_COURSE_BLOCK: roleLabel(role), FOLD_COURSE_BLOCK: t('courseEvolution.operations.fold', '折叠已会内容'), REORDER_COURSE_BLOCK: t('courseEvolution.operations.reorder', '重组学习顺序') } as Record<string, string>)[type] || type }
function roleLabel(role: string) { return ({ reasoning: t('courseEvolution.sectionGrowth.roles.reasoning', '理论推导'), application: t('courseEvolution.sectionGrowth.roles.application', '实战应用'), example: t('courseEvolution.sectionGrowth.roles.example', '例子讲解'), checkpoint: t('courseEvolution.sectionGrowth.roles.checkpoint', '理解检查'), concept: t('courseEvolution.sectionGrowth.roles.concept', '核心概念') } as Record<string, string>)[role] || role }
function operationActionLabel(operation: any) { return operation.payload?.action === 'INSERT' ? t('courseEvolution.sectionGrowth.insert', '新增') : operation.payload?.action === 'REPLACE' ? t('courseEvolution.sectionGrowth.replace', '升级') : operation.payload?.action === 'FOLD' ? t('courseEvolution.sectionGrowth.fold', '折叠') : operation.payload?.action === 'REORDER' ? t('courseEvolution.sectionGrowth.reorder', '重组') : t('courseEvolution.sectionGrowth.adjust', '调整') }
function contentOperations(plan: CourseEvolutionPlan) { return plan.operations.filter(item => item.operation_type !== 'ADJUST_COURSE_DIFFICULTY') }
function requiresWorkbench(plan: CourseEvolutionPlan) {
  // A complete strong self-report is already one learner-approved growth
  // package. Keep its evidence, scope, course outline and confirmation visible
  // together in the AI-teacher rail; detailed evidence remains available in
  // the inline expansion without taking the learner out of the course.
  if (isStrongScopedPlan(plan)) return false
  const affectedSections = new Set(
    (plan.impact_summary?.affected_section_ids || []).map(String),
  )
  return plan.scope_selection === 'whole_course'
    || affectedSections.size > 1
    || contentOperations(plan).length > 1
}
function isManualPlan(plan: CourseEvolutionPlan) {
  return ['manual_request', 'manual_section_request'].includes(String(plan.source_kind || ''))
}
function planScopeLabel(plan: CourseEvolutionPlan) {
  if (plan.scope_selection === 'current_block') {
    return t('courseEvolution.scope.currentBlock', '只影响当前内容')
  }
  if (plan.scope_selection === 'whole_course') {
    return t('courseEvolution.scope.wholeCourse', '应用到全课程')
  }
  return t('courseEvolution.scope.currentSection', '只影响当前小节')
}
function planScopeSummary(plan: CourseEvolutionPlan) {
  if (plan.scope_selection === 'current_block') {
    return t('courseEvolution.scope.blockSummary', 'AI 只处理当前内容，不扩展到其他位置')
  }
  if (plan.scope_selection === 'whole_course') {
    return t('courseEvolution.scope.matchedSummary', 'AI 识别 {roles}，匹配 {count} 个节点')
      .replace('{roles}', targetRoleLabels(plan).join('、'))
      .replace('{count}', String(contentOperations(plan).length))
  }
  return t('courseEvolution.scope.currentSummary', 'AI 只在本节内处理：{roles}')
    .replace('{roles}', targetRoleLabels(plan).join('、'))
}
function readyOperationCount(plan: CourseEvolutionPlan) {
  return contentOperations(plan).filter(item => item.payload?.candidate_status === 'ready').length
}
function reviewPlanStatus(plan: CourseEvolutionPlan) {
  if (plan.generation_status === 'generating') return t('courseEvolution.review.liveEyebrow', '正在生成调整候选')
  if (plan.generation_status === 'failed') return t('courseEvolution.review.scanFailed', '生成未完成')
  return t('courseEvolution.review.scanComplete', '候选已就绪，可以逐项审阅')
}
function reviewPlanSummary(plan: CourseEvolutionPlan) {
  const matched = Number(plan.impact_summary?.matched_block_count || contentOperations(plan).length)
  if (plan.generation_status === 'generating') {
    return t('courseEvolution.review.compactProgress', '已生成 {ready}/{total} 个候选，点击查看实时结果')
      .replace('{ready}', String(readyOperationCount(plan)))
      .replace('{total}', String(matched || '—'))
  }
  if (plan.generation_status === 'failed') {
    return String(plan.impact_summary?.generation_error || t('courseEvolution.review.openFailed', '打开查看已保留的结果'))
  }
  return t('courseEvolution.review.openHint', '逐项查看、纳入或排除 {count} 个节点')
    .replace('{count}', String(contentOperations(plan).length))
}
function targetRoleLabels(plan: CourseEvolutionPlan) {
  const labels = plan.impact_summary?.target_role_labels || []
  return labels.length ? labels : (plan.requested_roles || []).map(roleLabel)
}
function impactLabels(plan: CourseEvolutionPlan) { return [...(plan.impact_summary?.knowledge_labels || []), ...(plan.impact_summary?.ability_labels || []), ...(plan.impact_summary?.misconception_labels || [])].slice(0, 4) }
function evidenceAssessment(plan: CourseEvolutionPlan) { return plan.impact_summary?.evidence_assessment || hypothesisFor(plan)?.evidence_assessment || {} }
function isStrongScopedPlan(plan: CourseEvolutionPlan) {
  const assessment = evidenceAssessment(plan)
  return (assessment.maturity === 'explicit_scoped_request'
    && assessment.explicit_scope === 'current_and_next')
    || Boolean(assessment.has_strong_self_report)
}
function requestContract(plan: CourseEvolutionPlan): Record<string, any> {
  return evidenceAssessment(plan).explicit_request_contract || {}
}
const SUPPORT_LABELS: Record<string, string> = {
  explanation: '分步解释',
  animation: '几何动画',
  practice: '再进行计算',
}
function supportSummary(contract: Record<string, any>) {
  const supports = new Set<string>(
    (contract.requested_supports || []).map((item: unknown) => String(item)),
  )
  const labels: string[] = []
  if (supports.has('animation') && supports.has('explanation')) {
    labels.push(t('courseEvolution.strongTrigger.animationExplanation', '几何动画解释'))
  } else {
    if (supports.has('explanation')) {
      labels.push(t('courseEvolution.strongTrigger.stepExplanation', '分步解释'))
    }
    if (supports.has('animation')) {
      labels.push(t('courseEvolution.strongTrigger.animation', '几何动画'))
    }
  }
  if (supports.has('practice')) {
    labels.push(t('courseEvolution.strongTrigger.practice', '再进行计算'))
  }
  for (const support of supports) {
    if (!['explanation', 'animation', 'practice'].includes(support)) {
      labels.push(SUPPORT_LABELS[support] || support)
    }
  }
  return labels.join('、')
}
function contractDimensions(plan: CourseEvolutionPlan) {
  const contract = requestContract(plan)
  const scope = String(contract.scope || evidenceAssessment(plan).explicit_scope || '')
  return [
    {
      key: 'ability',
      label: t('courseEvolution.strongTrigger.ability', '已会内容'),
      value: String(contract.capability_text || ''),
    },
    {
      key: 'gap',
      label: t('courseEvolution.strongTrigger.gap', '持续困难'),
      value: String(contract.gap_text || ''),
    },
    {
      key: 'method',
      label: t('courseEvolution.strongTrigger.method', '教学要求'),
      value: supportSummary(contract),
    },
    {
      key: 'scope',
      label: t('courseEvolution.strongTrigger.scope', '影响范围'),
      value: scope === 'current_and_next'
        ? t('courseEvolution.strongTrigger.scopeNext', '本节及相关后续内容')
        : scope === 'current'
          ? t('courseEvolution.strongTrigger.scopeCurrent', '仅当前小节')
          : '',
    },
  ]
}
function strongGrowthGroups(plan: CourseEvolutionPlan) {
  const labelsFor = (scope: 'current' | 'next') => Array.from(new Set(
    contentOperations(plan)
      .filter(operation => operation.scope === scope)
      .map(operation => operationLabel(operation.operation_type, operation.payload?.desired_role)),
  ))
  return [
    {
      key: 'current',
      label: t('courseEvolution.strongTrigger.currentGroup', '当前位置'),
      items: labelsFor('current'),
    },
    {
      key: 'next',
      label: t('courseEvolution.strongTrigger.nextGroup', '相关后续'),
      items: labelsFor('next'),
    },
  ].filter(group => group.items.length)
}
function setPlanElement(planId: string, element: unknown) {
  if (element instanceof HTMLElement) planElements.set(planId, element)
  else planElements.delete(planId)
}
async function focusPlan(planId: string) {
  expandedId.value = planId
  const plan = visiblePlans.value.find(item => item.change_set_id === planId)
  if (plan && requiresWorkbench(plan)) {
    openReview(plan)
    return
  }
  await nextTick()
  const element = planElements.get(planId)
  if (element && typeof element.scrollIntoView === 'function') {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
function planEffectState(plan: CourseEvolutionPlan) { return plan.status === 'pending' ? 'pending' : String(plan.effect_evaluation?.status || 'insufficient_evidence') }
function effectIcon(plan: CourseEvolutionPlan) { return plan.effect_evaluation?.status === 'effective' ? CheckCircle2 : plan.effect_evaluation?.status === 'ineffective' || plan.effect_evaluation?.status === 'harmful' ? TriangleAlert : CircleDot }
function effectTitle(plan: CourseEvolutionPlan) {
  if (plan.effect_evaluation?.status === 'effective') {
    return plan.effect_evaluation?.verification_level === 'confirmed'
      ? t('courseEvolution.confirmed', '持续证据已确认')
      : t('courseEvolution.initiallyValidated', '本轮独立复验通过')
  }
  return plan.effect_evaluation?.status === 'ineffective' || plan.effect_evaluation?.status === 'harmful'
    ? t('courseEvolution.needsReview', '当前课程变化需要复核')
    : t('courseEvolution.applied', '课程新版本已应用')
}
function effectLabel(plan: CourseEvolutionPlan) { return ({ effective: t('courseEvolution.effects.effective', '原判断获得新证据支持，继续观察后续迁移'), ineffective: t('courseEvolution.effects.ineffective', '后续证据显示需要调整'), harmful: t('courseEvolution.effects.harmful', '后续证据显示有副作用，建议回退'), insufficient_evidence: t('courseEvolution.effects.insufficient', '等待独立复验：后续同能力正式题') } as Record<string, string>)[plan.effect_evaluation?.status || ''] || t('courseEvolution.effects.insufficient', '等待独立复验：后续同能力正式题') }
function verificationFor(plan: CourseEvolutionPlan) { return plan.effect_evaluation?.verification_summary || null }
function attemptResultLabel(value: Record<string, any> | undefined) {
  if (!value || value.attempt_count === 0) return t('courseEvolution.verification.noEvidence', '暂无')
  if (typeof value.score === 'number') return `${Math.round(value.score)} ${t('courseEvolution.verification.points', '分')}`
  return value.passed
    ? t('courseEvolution.verification.passed', '已通过')
    : t('courseEvolution.verification.failed', '未通过')
}
function locateEvidence(evidence: EvolutionEvidence) {
  const sectionId = String(evidence.anchor?.section_id || '')
  const node = courseStore.courseTree.find(item => item.node_id === sectionId)
  if (node) courseStore.selectNode(node)
  if (sectionId) courseStore.scrollToNode(sectionId)
  if (evidence.source_type === 'learning_record') courseStore.scrollToNote(evidence.source_id)
}
async function refreshCourseAndRuntime() {
  await courseStore.refreshCourseData(props.courseId)
  await progressStore.loadRuntime(props.courseId)
}

function applicationOperationPriority(operation: EvolutionOperation) {
  return ({
    ADD_ANIMATION: 0,
    INSERT_COURSE_SUPPORT: 1,
    ADD_TARGETED_PRACTICE: 2,
    ADD_TRANSITION_SUPPORT: 3,
    ADD_CHECKPOINT: 4,
  } as Record<string, number>)[operation.operation_type] ?? 10
}

function buildApplicationPresentation(
  sourcePlan: CourseEvolutionPlan,
  selectedOperationIds?: string[],
): CourseEvolutionApplicationPresentation {
  const appliedPlan = store.plans.find(
    item => item.change_set_id === sourcePlan.change_set_id,
  ) || sourcePlan
  const selectedIds = new Set(
    selectedOperationIds?.length
      ? selectedOperationIds
      : appliedPlan.selected_operation_ids?.length
        ? appliedPlan.selected_operation_ids
        : appliedPlan.operations.map(operation => operation.operation_id),
  )
  const selectedCourseOperations = appliedPlan.operations
    .filter(operation => (
      operation.operation_type !== 'ADJUST_COURSE_DIFFICULTY'
      && selectedIds.has(operation.operation_id)
      && (appliedPlan.selected_scope !== 'current' || operation.scope === 'current')
    ))
    .sort((left, right) => applicationOperationPriority(left) - applicationOperationPriority(right))
  const appliedBlockIds = (appliedPlan.applied_block_ids || []).map(String)
  const appliedBlockIdSet = new Set(appliedBlockIds)
  const documentEntries = courseStore.nodes.flatMap(node => (
    (node.course_blocks || []).map(block => ({ node, block }))
  ))
  const evolvedEntries = documentEntries.filter(({ block }) => {
    const metadata = block.payload?.course_evolution as Record<string, unknown> | undefined
    return appliedBlockIdSet.has(block.block_id)
      || String(metadata?.change_set_id || '') === appliedPlan.change_set_id
  })
  const preferredOperation = selectedCourseOperations.find(operation => (
    evolvedEntries.some(({ block }) => (
      String((block.payload?.course_evolution as Record<string, unknown> | undefined)?.operation_id || '')
      === operation.operation_id
    ))
  )) || selectedCourseOperations[0]
  const targetEntry = evolvedEntries.find(({ block }) => (
    String((block.payload?.course_evolution as Record<string, unknown> | undefined)?.operation_id || '')
    === preferredOperation?.operation_id
  )) || evolvedEntries[0]
  const affectedSectionIds = [...new Set(
    selectedCourseOperations.map(operation => operation.target_section_id).filter(Boolean),
  )]
  if (!affectedSectionIds.length) {
    for (const sectionId of appliedPlan.impact_summary?.affected_section_ids || []) {
      affectedSectionIds.push(String(sectionId))
    }
  }
  return {
    planId: appliedPlan.change_set_id,
    affectedSectionIds,
    appliedBlockIds,
    operationIds: selectedCourseOperations.map(operation => operation.operation_id),
    targetSectionId: targetEntry?.node.node_id
      || preferredOperation?.target_section_id
      || appliedPlan.target_section_id
      || props.sectionId
      || '',
    targetBlockId: targetEntry?.block.block_id || appliedBlockIds[0] || '',
    targetOperationId: preferredOperation?.operation_id || '',
  }
}

async function accept(plan: CourseEvolutionPlan) {
  const scope = selectedScope[plan.change_set_id] || 'current'
  await store.accept(plan.change_set_id, scope)
  await refreshCourseAndRuntime()
  emit('courseApplied', buildApplicationPresentation(plan))
}

type ReviewScanContext = {
  token: number
  baselinePlanIds: Set<string>
  instruction: string
  targetPlanId?: string
}

let progressPollTimer: ReturnType<typeof setTimeout> | undefined
let scanSession = 0
let activeScanContext: ReviewScanContext | null = null

function syncReviewSelection(plan: CourseEvolutionPlan) {
  const operationIds = contentOperations(plan).map(operation => operation.operation_id)
  const seen = new Set(reviewSeenOperations[plan.change_set_id] || [])
  const selected = new Set(reviewSelections[plan.change_set_id] || [])
  for (const operationId of operationIds) {
    if (!seen.has(operationId)) selected.add(operationId)
  }
  reviewSeenOperations[plan.change_set_id] = [...operationIds]
  reviewSelections[plan.change_set_id] = operationIds.filter(operationId => selected.has(operationId))
}

function findGeneratedWholeCoursePlan(context: ReviewScanContext) {
  if (context.targetPlanId) {
    const target = store.plans.find(plan => plan.change_set_id === context.targetPlanId)
    if (target) return target
  }
  const candidates = [...store.plans].reverse().filter(plan => (
    !context.baselinePlanIds.has(plan.change_set_id)
    && plan.target_section_id === props.sectionId
  ))
  const wholeCourseCandidates = candidates.filter(plan => (
    isManualPlan(plan) && plan.scope_selection === 'whole_course'
  ))
  return wholeCourseCandidates.find(plan => (
    !context.baselinePlanIds.has(plan.change_set_id)
    && plan.request_text === context.instruction
  )) || wholeCourseCandidates[0]
    // A semantically complete learner statement can be promoted by the
    // backend into an evidence-driven current-and-next plan. It still belongs
    // to the whole-course review flow the learner explicitly opened, so bind
    // that real plan instead of leaving the preview in an endless scan state.
    || candidates.find(plan => plan.request_text === context.instruction)
    || candidates[0]
    || null
}

function syncActiveReview(context: ReviewScanContext) {
  const plan = findGeneratedWholeCoursePlan(context)
  if (!plan) return null
  context.targetPlanId = plan.change_set_id
  reviewPlanId.value = plan.change_set_id
  reviewInstruction.value = plan.request_text || context.instruction
  syncReviewSelection(plan)
  if (plan.generation_status === 'failed') {
    reviewError.value = String(plan.impact_summary?.generation_error || store.generationError)
  }
  return plan
}

function clearProgressPoll() {
  if (progressPollTimer) clearTimeout(progressPollTimer)
  progressPollTimer = undefined
}

function scheduleProgressPoll(delay = 500) {
  clearProgressPoll()
  const context = activeScanContext
  if (!context || context.token !== scanSession || !reviewOverlayOpen.value) return
  progressPollTimer = setTimeout(async () => {
    if (!activeScanContext || context.token !== scanSession || !reviewOverlayOpen.value) return
    try {
      await store.refreshProgress(props.courseId)
      syncActiveReview(context)
    } catch {
      // The generation request remains authoritative when a progress read briefly fails.
    }
    const plan = syncActiveReview(context)
    if (
      activeScanContext
      && context.token === scanSession
      && reviewOverlayOpen.value
      && (reviewScanInFlight.value || plan?.generation_status === 'generating')
    ) {
      scheduleProgressPoll(650)
    }
  }, delay)
}

function openReview(plan: CourseEvolutionPlan) {
  reviewPlanId.value = plan.change_set_id
  reviewInstruction.value = plan.request_text || diagnosisFor(plan)
  reviewError.value = plan.generation_status === 'failed'
    ? String(plan.impact_summary?.generation_error || store.generationError)
    : ''
  syncReviewSelection(plan)
  reviewOverlayOpen.value = true
  if (plan.generation_status === 'generating') {
    const token = ++scanSession
    activeScanContext = {
      token,
      baselinePlanIds: new Set(),
      instruction: plan.request_text || '',
      targetPlanId: plan.change_set_id,
    }
    scheduleProgressPoll(100)
  }
}
function closeReview() {
  reviewOverlayOpen.value = false
  clearProgressPoll()
}
function updateReviewSelection(planId: string, operationIds: string[]) {
  reviewSelections[planId] = [...operationIds]
}
async function acceptSelected(plan: CourseEvolutionPlan) {
  const operationIds = reviewSelections[plan.change_set_id] || []
  if (!operationIds.length) return
  await store.accept(
    plan.change_set_id,
    selectedScope[plan.change_set_id] || 'current',
    operationIds,
  )
  closeReview()
  await refreshCourseAndRuntime()
  emit('courseApplied', buildApplicationPresentation(plan, operationIds))
}
async function undo(plan: CourseEvolutionPlan) {
  await store.undo(plan.change_set_id)
  store.clearApplicationVisual(plan.change_set_id)
  await refreshCourseAndRuntime()
}
async function adjust(plan: CourseEvolutionPlan) { await store.adjust(plan.change_set_id) }
async function createSectionPlan() {
  if (!props.sectionId || !sectionInstruction.value.trim()) return
  const instruction = sectionInstruction.value.trim()
  const scopeSelection = requestScope.value
  const baselinePlanIds = new Set(store.plans.map(plan => plan.change_set_id))
  let context: ReviewScanContext | null = null
  if (scopeSelection === 'whole_course') {
    const token = ++scanSession
    context = {
      token,
      baselinePlanIds,
      instruction,
    }
    activeScanContext = context
    reviewPlanId.value = ''
    reviewInstruction.value = instruction
    reviewError.value = ''
    reviewScanInFlight.value = true
    reviewOverlayOpen.value = true
    scheduleProgressPoll(350)
  }
  try {
    await store.createSectionPlan(props.sectionId, instruction, scopeSelection)
    if (context) syncActiveReview(context)
    if (!context) {
      const createdPlan = [...store.plans].reverse().find(plan => (
        !baselinePlanIds.has(plan.change_set_id)
        && plan.target_section_id === props.sectionId
        && plan.request_text === instruction
      )) || [...store.plans].reverse().find(plan => (
        !baselinePlanIds.has(plan.change_set_id)
        && plan.target_section_id === props.sectionId
      ))
      if (createdPlan) await focusPlan(createdPlan.change_set_id)
    }
    sectionInstruction.value = ''
  } catch {
    if (context) {
      try {
        await store.refreshProgress(props.courseId)
      } catch {
        // Keep the original generation error when the final checkpoint cannot be read.
      }
      syncActiveReview(context)
      reviewError.value = store.generationError
    }
    // The store also exposes the exact generation error beside the request.
  } finally {
    if (context && context.token === scanSession) {
      reviewScanInFlight.value = false
      syncActiveReview(context)
      clearProgressPoll()
    }
  }
}
async function generateSuggested(plan: CourseEvolutionPlan) {
  try {
    await store.generateSuggested(plan.change_set_id)
    const generated = store.plans.find(item => item.change_set_id === plan.change_set_id)
    if (generated) await focusPlan(generated.change_set_id)
  } catch {
    // The store exposes the exact generation error beside the request.
  }
}
async function load() {
  if (!props.courseId) return
  if (import.meta.env.MODE === 'test') return
  try {
    await store.load(props.courseId)
  } catch {
    // The AI teacher remains usable when the evolution projection is offline.
  }
}
watch(
  () => visiblePlans.value.map(plan => [
    plan.change_set_id,
    plan.status,
    evidenceAssessment(plan).maturity,
    evidenceAssessment(plan).explicit_scope,
  ].join(':')).join('|'),
  () => {
    for (const plan of visiblePlans.value) {
      if (!selectedScope[plan.change_set_id]) {
        selectedScope[plan.change_set_id] = (
          plan.allowed_scopes.includes('current_and_next')
          && evidenceAssessment(plan).explicit_scope === 'current_and_next'
        ) ? 'current_and_next' : 'current'
      }
      if (
        plan.status === 'pending'
        && (
          (
            props.focusPlanId === plan.change_set_id
            && (
              !requiresWorkbench(plan)
              || reviewPlanId.value !== plan.change_set_id
            )
          )
          || (!expandedId.value && isStrongScopedPlan(plan))
        )
      ) {
        void focusPlan(plan.change_set_id)
      }
    }
  },
  { immediate: true },
)
watch(
  () => props.focusPlanId,
  (planId) => {
    const plan = visiblePlans.value.find(item => item.change_set_id === planId)
    if (plan) {
      void focusPlan(plan.change_set_id)
    }
  },
  { immediate: true },
)
watch(
  () => reviewPlan.value
    ? [
        reviewPlan.value.change_set_id,
        reviewPlan.value.generation_status,
        ...contentOperations(reviewPlan.value).map(operation => (
          `${operation.operation_id}:${operation.payload?.candidate_status || ''}`
        )),
      ].join('|')
    : '',
  () => {
    const plan = reviewPlan.value
    if (!plan) return
    syncReviewSelection(plan)
    if (plan.generation_status === 'failed') {
      reviewError.value = String(plan.impact_summary?.generation_error || store.generationError)
    }
    if (plan.generation_status !== 'generating' && !reviewScanInFlight.value) clearProgressPoll()
  },
)
watch(() => props.courseId, load)
onMounted(load)
onUnmounted(clearProgressPoll)
</script>

<style scoped>
.evolution-panel { min-height:0; max-height:58%; overflow:auto; margin:0 12px 10px; padding:10px 11px; border:1px solid rgba(221,214,254,.9); border-radius:10px; background:linear-gradient(110deg,rgba(245,243,255,.78),rgba(248,250,252,.66)); }
.evolution-panel > header { display:grid; grid-template-columns:24px minmax(0,1fr) 28px; align-items:center; gap:6px; margin-bottom:8px; color:#6d28d9; }
.evolution-panel > header > span { display:grid; place-items:center; }
.evolution-panel header div { display:flex; flex-direction:column; }
.evolution-panel header small { color:#6b7280; font-size:8px; }
.evolution-panel header strong { font-size:11px; }
.evolution-panel header button { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:#6d28d9; background:transparent; cursor:pointer; }
.growth-insight-switcher { display:grid; grid-template-columns:1fr 1fr; gap:5px; margin:0 0 8px; }
.growth-insight-switcher button { min-width:0; display:grid; grid-template-columns:14px minmax(0,1fr) auto; align-items:center; gap:5px; min-height:32px; padding:5px 7px; border:1px solid #e2e8f0; border-radius:7px; color:#64748b; background:rgba(255,255,255,.82); font-size:8px; text-align:left; cursor:pointer; }
.growth-insight-switcher button.active { color:#6d28d9; border-color:#c4b5fd; background:#f5f3ff; }
.growth-insight-switcher button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.growth-insight-switcher button b { min-width:18px; padding:2px 5px; border-radius:999px; color:#6d28d9; background:#ede9fe; font-size:7px; text-align:center; }
.personal-learning-map,.evidence-timeline { display:grid; gap:8px; margin:0 0 9px; padding:9px; border:1px solid #ddd6fe; border-radius:9px; background:linear-gradient(135deg,#fff,#faf5ff); }
.personal-learning-map > header,.evidence-timeline > header { display:grid; grid-template-columns:24px minmax(0,1fr); align-items:center; gap:6px; }
.personal-learning-map > header > span,.evidence-timeline > header > span { width:24px; height:24px; display:grid; place-items:center; border-radius:7px; color:#fff; background:#7c3aed; }
.personal-learning-map > header div,.evidence-timeline > header div { display:flex; flex-direction:column; }
.personal-learning-map > header small,.evidence-timeline > header small { color:#7c3aed; font-size:7px; }
.personal-learning-map > header strong,.evidence-timeline > header strong { color:#2e1065; font-size:10px; }
.personal-map-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:4px; margin:0; }
.personal-map-stats div { display:grid; justify-items:center; gap:2px; padding:6px 3px; border-radius:6px; background:#f8fafc; }
.personal-map-stats dt { color:#64748b; font-size:7px; }
.personal-map-stats dd { margin:0; color:#4c1d95; font-size:12px; font-weight:850; }
.personal-map-path,.evidence-timeline ol { display:grid; gap:4px; margin:0; padding:0; list-style:none; }
.personal-map-path li { display:grid; grid-template-columns:25px minmax(0,1fr) 20px; align-items:center; gap:6px; padding:6px 7px; border-left:3px solid #cbd5e1; border-radius:6px; background:#f8fafc; }
.personal-map-path li[data-state="supplemented"] { border-left-color:#8b5cf6; background:#faf5ff; }
.personal-map-path li[data-state="upgraded"] { border-left-color:#2563eb; background:#eff6ff; }
.personal-map-path li[data-state="folded"] { border-left-color:#16a34a; background:#f0fdf4; }
.personal-map-path li[data-state="reorganized"] { border-left-color:#d97706; background:#fffbeb; }
.personal-map-path li > span { color:#94a3b8; font-size:8px; font-weight:850; }
.personal-map-path li > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.personal-map-path strong { overflow:hidden; color:#1e293b; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.personal-map-path small { display:block; overflow:hidden; color:#64748b; font-size:7px; text-overflow:ellipsis; white-space:nowrap; }
.personal-map-path li > b { width:20px; height:20px; display:grid; place-items:center; border-radius:50%; color:#6d28d9; background:#ede9fe; font-size:7px; }
.personal-learning-map > p { display:flex; align-items:flex-start; gap:5px; margin:0; color:#047857; font-size:7px; line-height:1.45; }
.evidence-timeline ol { max-height:250px; overflow:auto; padding-right:2px; }
.evidence-timeline li { display:grid; grid-template-columns:24px minmax(0,1fr) 24px; gap:6px; padding:7px; border:1px solid #e2e8f0; border-radius:7px; background:#fff; }
.evidence-timeline li[data-counter="true"] { border-color:#bbf7d0; background:#f0fdf4; }
.evidence-timeline li > span { width:24px; height:24px; display:grid; place-items:center; border-radius:7px; color:#6d28d9; background:#f5f3ff; }
.evidence-timeline li > div { min-width:0; }
.evidence-timeline li b { color:#334155; font-size:8px; }
.evidence-timeline li p { margin:2px 0; color:#475569; font-size:8px; line-height:1.45; overflow-wrap:anywhere; }
.evidence-timeline li small { color:#94a3b8; font-size:7px; }
.evidence-timeline li > button { width:24px; height:24px; display:grid; place-items:center; border:0; border-radius:6px; color:#64748b; background:#f8fafc; cursor:pointer; }
.evidence-empty { margin:0; padding:10px; color:#64748b; background:#f8fafc; font-size:8px; line-height:1.5; text-align:center; }
.section-growth-request { display:grid; gap:8px; margin:0 0 10px; padding:9px; border:1px solid #e2e8f0; border-radius:8px; background:rgba(255,255,255,.86); }
.growth-steps { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:3px; margin:0; padding:0; list-style:none; }
.growth-steps li { min-width:0; display:grid; justify-items:center; gap:2px; color:#94a3b8; font-size:7px; }
.growth-steps li b { width:18px; height:18px; display:grid; place-items:center; border:1px solid #cbd5e1; border-radius:50%; background:#fff; font-size:8px; }
.growth-steps li span { overflow:hidden; max-width:100%; text-overflow:ellipsis; white-space:nowrap; }
.growth-steps li.done,.growth-steps li.active { color:#6d28d9; }
.growth-steps li.done b { color:#fff; border-color:#8b5cf6; background:#8b5cf6; }
.growth-steps li.active b { border:2px solid #7c3aed; box-shadow:0 0 0 2px #ede9fe; }
.section-growth-request label { display:grid; gap:5px; color:#334155; font-size:9px; font-weight:700; }
.section-growth-request input { width:100%; min-height:36px; padding:7px 8px; border:1px solid #cbd5e1; border-radius:7px; color:#1f2937; background:#fff; font:inherit; line-height:1.5; box-sizing:border-box; }
.section-growth-request input:focus { outline:2px solid #ddd6fe; border-color:#8b5cf6; }
.request-scope-control { display:grid; grid-template-columns:1fr 1fr; gap:5px; }
.request-scope-control > button { min-width:0; min-height:44px; display:grid; grid-template-columns:16px minmax(0,1fr); align-items:center; gap:5px; padding:6px 7px; border:1px solid #dbe3ef; border-radius:7px; color:#64748b; background:#f8fafc; text-align:left; cursor:pointer; }
.request-scope-control > button.active { color:#4338ca; border-color:#a5b4fc; background:#eef2ff; box-shadow:0 0 0 1px rgba(99,102,241,.08); }
.request-scope-control > button > span { min-width:0; display:flex; flex-direction:column; gap:1px; }
.request-scope-control b { overflow:hidden; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.request-scope-control small { overflow:hidden; color:#94a3b8; font-size:7px; text-overflow:ellipsis; white-space:nowrap; }
.request-scope-control button.active small { color:#6366f1; }
.generate-plan,.challenge-suggestion button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; border:1px solid #7c3aed; border-radius:6px; color:#fff; background:#7c3aed; font-size:9px; font-weight:700; cursor:pointer; }
.generate-plan:disabled,.challenge-suggestion button:disabled { opacity:.55; cursor:not-allowed; }
.generation-error { display:flex; align-items:flex-start; gap:5px; margin:0; color:#b91c1c; font-size:8px; line-height:1.4; }
.whole-course-scan-summary { width:100%; display:grid; grid-template-columns:32px minmax(0,1fr) 18px; align-items:center; gap:9px; margin:0 0 8px; padding:10px; border:1px solid #c7d2fe; border-radius:9px; color:#4338ca; background:#fff; text-align:left; cursor:pointer; }
.whole-course-scan-summary > span { width:32px; height:32px; display:grid; place-items:center; border-radius:9px; color:#fff; background:#6366f1; }
.whole-course-scan-summary[data-status="generating"] > span { background:#7c3aed; }
.whole-course-scan-summary[data-status="failed"] { color:#9a3412; border-color:#fed7aa; background:#fffaf5; }
.whole-course-scan-summary[data-status="failed"] > span { background:#ea580c; }
.whole-course-scan-summary > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.whole-course-scan-summary small { color:currentColor; font-size:8px; font-weight:800; }
.whole-course-scan-summary strong { overflow:hidden; color:#1e293b; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.whole-course-scan-summary em { overflow:hidden; color:#64748b; font-size:8px; font-style:normal; text-overflow:ellipsis; white-space:nowrap; }
.evolution-panel article { padding:9px 10px; border:1px solid #e5e7eb; border-left:3px solid #8b5cf6; border-radius:8px; background:#fff; }
.evolution-panel article + article { margin-top:7px; }
.evolution-panel article.is-focus-plan { border-color:#8b5cf6; box-shadow:0 0 0 2px rgba(139,92,246,.13),0 10px 24px rgba(91,33,182,.1); animation:evolution-focus-pulse .9s ease-out; }
.strong-evidence-trigger { display:grid; gap:7px; margin:7px 0 8px; padding:10px; border:1px solid rgba(124,58,237,.28); border-radius:9px; background:linear-gradient(125deg,rgba(237,233,254,.96),rgba(250,245,255,.86)); box-shadow:0 8px 20px rgba(91,33,182,.08); }
.strong-evidence-trigger > span { display:flex; align-items:center; gap:5px; color:#6d28d9; font-size:9px; font-weight:850; letter-spacing:.03em; }
.strong-evidence-trigger > strong { color:#3b0764; font-size:11px; line-height:1.5; }
.strong-evidence-trigger > small { color:#6b7280; font-size:8px; line-height:1.55; }
.strong-evidence-trigger > div { display:flex; flex-wrap:wrap; gap:4px; }
.strong-evidence-trigger > div b { padding:3px 6px; border:1px solid rgba(139,92,246,.2); border-radius:999px; color:#6d28d9; background:rgba(255,255,255,.82); font-size:8px; font-weight:750; }
.strong-evidence-dimensions { display:grid !important; grid-template-columns:auto minmax(0,1fr); align-items:start; gap:5px 7px; padding-top:2px; }
.strong-evidence-dimensions em { min-width:0; color:#4c1d95; font-size:9px; font-style:normal; line-height:1.5; overflow-wrap:anywhere; }
.strong-growth-plan { display:grid; gap:6px; margin:0 0 8px; padding:9px; border:1px solid #ddd6fe; border-radius:8px; background:#fff; }
.strong-growth-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.strong-growth-heading > span { display:inline-flex; align-items:center; gap:5px; color:#6d28d9; font-size:9px; font-weight:800; }
.strong-growth-heading > small { color:#94a3b8; font-size:7px; text-align:right; }
.strong-growth-group { display:grid; grid-template-columns:54px minmax(0,1fr); align-items:start; gap:6px; padding:6px 7px; border-radius:6px; background:#f8fafc; }
.strong-growth-group[data-scope="next"] { background:#fffbeb; }
.strong-growth-group > span { color:#475569; font-size:8px; font-weight:800; line-height:1.7; }
.strong-growth-group > p { display:flex; flex-wrap:wrap; gap:4px; margin:0; }
.strong-growth-group b { padding:2px 5px; border:1px solid #ddd6fe; border-radius:999px; color:#6d28d9; background:#faf5ff; font-size:8px; line-height:1.45; }
.strong-growth-group[data-scope="next"] b { color:#a16207; border-color:#fde68a; background:#fff; }
@keyframes evolution-focus-pulse { 0% { transform:translateY(4px); opacity:.76; box-shadow:0 0 0 7px rgba(139,92,246,.2); } 100% { transform:translateY(0); opacity:1; box-shadow:0 0 0 2px rgba(139,92,246,.13),0 10px 24px rgba(91,33,182,.1); } }
.challenge-suggestion { display:grid; gap:6px; }
.challenge-suggestion > span { display:flex; align-items:center; gap:5px; color:#047857; font-size:8px; font-weight:800; }
.challenge-suggestion strong { color:#1e293b; font-size:11px; line-height:1.5; }
.challenge-suggestion p { margin:0; color:#64748b; font-size:9px; line-height:1.5; }
.plan-source { display:flex; align-items:center; gap:5px; margin-bottom:7px; }
.plan-source span,.plan-source b { padding:3px 6px; border-radius:999px; color:#475569; background:#f1f5f9; font-size:8px; }
.plan-source b { color:#7c3aed; background:#f5f3ff; }
.semantic-scope-summary { display:grid; gap:4px; margin-bottom:7px; padding:8px; border:1px solid #dbeafe; border-radius:7px; background:#f8fbff; }
.semantic-scope-summary[data-scope="whole_course"] { border-color:#c7d2fe; background:#eef2ff; }
.semantic-scope-summary > span { display:flex; align-items:center; gap:5px; color:#1d4ed8; font-size:8px; font-weight:800; }
.semantic-scope-summary > strong { color:#1e293b; font-size:10px; line-height:1.45; }
.semantic-scope-summary > small { color:#64748b; font-size:8px; line-height:1.45; }
.evolution-panel article[data-effect="insufficient_evidence"] { border-left-color:#3b82f6; }
.evolution-panel article[data-effect="effective"] { border-color:#bbf7d0; border-left-color:#16a34a; background:#f7fef9; }
.evolution-panel article[data-effect="ineffective"],.evolution-panel article[data-effect="harmful"] { border-color:#fde68a; border-left-color:#d97706; background:#fffbeb; }
.evolution-evidence { display:flex; flex-wrap:wrap; align-items:center; gap:3px; color:#a78bfa; }
.evolution-evidence span { display:inline-flex; align-items:center; gap:4px; padding:3px 6px; border-radius:4px; color:#475569; background:#f1f5f9; font-size:8px; }
.evolution-evidence span[data-source="practice_attempt"] { color:#075985; background:#f0f9ff; }
.evolution-evidence span[data-source="learning_record"] { color:#6d28d9; background:#f5f3ff; }
.evidence-maturity { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
.evidence-maturity span { display:inline-flex; align-items:center; gap:3px; color:#475569; font-size:8px; }
.evidence-maturity[data-maturity="confirmed_gap"] span { color:#047857; }
.evolution-diagnosis { display:grid; gap:4px; margin-top:8px; padding:8px 9px; border:1px solid #ddd6fe; border-radius:7px; background:#faf5ff; }
.evolution-diagnosis span { display:inline-flex; align-items:center; gap:5px; color:#7c3aed; font-size:8px; font-weight:800; }
.evolution-diagnosis strong { color:#2e1065; font-size:11px; line-height:1.55; }
.evolution-diagnosis small { color:#6b7280; font-size:8px; line-height:1.5; }
.source-requirement { display:flex; align-items:flex-start; gap:5px; margin:6px 0 0; padding:7px 8px; border:1px solid #fed7aa; border-radius:6px; color:#9a3412; background:#fff7ed; font-size:8px; line-height:1.5; }
.source-requirement svg { flex:0 0 auto; margin-top:1px; }
.source-requirement[data-status="available_materials"] { color:#1d4ed8; border-color:#bfdbfe; background:#eff6ff; }
.evolution-impact { display:flex; flex-wrap:wrap; align-items:center; gap:4px; margin-top:7px; }
.evolution-impact span { max-width:100%; overflow:hidden; padding:3px 6px; border:1px solid #dbeafe; border-radius:5px; color:#1d4ed8; background:#eff6ff; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.evolution-impact small { color:#64748b; font-size:8px; }
.evolution-effect { display:flex; align-items:flex-start; gap:5px; margin:8px 0 0; color:#475569; font-size:9px; line-height:1.5; }
.evolution-effect svg { flex:0 0 auto; margin-top:1px; color:#8b5cf6; }
.evolution-details-toggle { min-height:28px; display:flex; align-items:center; gap:4px; margin-top:3px; padding:0; border:0; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }
.evolution-details { margin:4px 0 9px; padding:8px 0; border-top:1px solid #ede9fe; border-bottom:1px solid #ede9fe; }
.evolution-details > p { display:grid; grid-template-columns:60px minmax(0,1fr) 24px; align-items:start; gap:6px; margin:4px 0; color:#64748b; font-size:9px; line-height:1.45; }
.evolution-details p b { color:#334155; }
.evolution-details > p > button { width:24px; height:24px; display:grid; place-items:center; border:0; border-radius:5px; color:#64748b; background:#f8fafc; cursor:pointer; }
.evolution-details ul { display:grid; gap:5px; margin:8px 0 0; padding:0; list-style:none; }
.evolution-details li { color:#64748b; font-size:9px; line-height:1.45; }
.evolution-details li > span { display:inline-block; min-width:58px; color:#7c3aed; font-weight:700; }
.operation-list li { display:grid; grid-template-columns:44px minmax(0,1fr); gap:7px; padding:7px; border:1px solid #e2e8f0; border-radius:7px; }
.operation-list li > span { min-width:0; align-self:start; padding:2px 5px; border-radius:4px; text-align:center; background:#ede9fe; }
.operation-list li > span[data-action="INSERT"] { color:#047857; background:#dcfce7; }
.operation-list li b { color:#1e293b; font-size:9px; }
.operation-list li p { margin:2px 0 0; }
.operation-list details { margin-top:5px; }
.operation-list summary { color:#2563eb; cursor:pointer; }
.candidate-before,.candidate-after { margin-top:5px; padding:6px; border-radius:5px; background:#f8fafc; }
.candidate-after { background:#f5f3ff; }
.candidate-before small,.candidate-after small { color:#64748b; font-size:7px; font-weight:800; }
.candidate-before p,.candidate-after p { max-height:92px; overflow:auto; white-space:pre-wrap; }
.whole-course-review-trigger { width:100%; display:grid; grid-template-columns:22px minmax(0,1fr) 16px; align-items:center; gap:7px; margin-top:8px; padding:8px 9px; border:1px solid #a5b4fc; border-radius:8px; color:#4338ca; background:#eef2ff; text-align:left; cursor:pointer; }
.whole-course-review-trigger > span { min-width:0; display:flex; flex-direction:column; gap:2px; }
.whole-course-review-trigger b { font-size:9px; }
.whole-course-review-trigger small { color:#6366f1; font-size:8px; }
.same-source-check { display:flex !important; align-items:flex-start !important; gap:5px !important; color:#047857 !important; }
.evolution-details .validation-plan,.evolution-details .protected { display:flex; grid-template-columns:none; align-items:flex-start; gap:5px; margin-top:8px; }
.evolution-details .validation-plan { color:#1d4ed8; }
.evolution-details .validation-plan b { white-space:nowrap; }
.evolution-details .protected { color:#047857; }
.scope-control { display:grid; grid-template-columns:1fr 1fr; gap:4px; margin:7px 0; padding:3px; border-radius:7px; background:#f1f5f9; }
.scope-control button { min-height:28px; border:0; border-radius:5px; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }
.scope-control button.active { color:#6d28d9; background:#fff; box-shadow:0 1px 4px rgba(15,23,42,.08); font-weight:700; }
.evolution-actions { display:flex; gap:5px; margin-top:8px; }
.evolution-actions button,.applied-growth button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 8px; border:1px solid #d1d5db; border-radius:6px; color:#64748b; background:#fff; font-size:9px; cursor:pointer; }
.evolution-actions button.primary { color:#fff; border-color:#7c3aed; background:#7c3aed; }
.applied-growth { display:grid; grid-template-columns:20px minmax(0,1fr) auto; align-items:center; gap:7px; color:#2563eb; }
article[data-effect="effective"] .applied-growth { color:#15803d; }
article[data-effect="ineffective"] .applied-growth,article[data-effect="harmful"] .applied-growth { color:#b45309; }
.applied-growth > span { display:flex; flex-direction:column; }
.applied-growth strong { font-size:10px; }
.applied-growth small { margin-top:2px; color:#64748b; font-size:8px; }
.applied-diagnosis { margin:7px 0 0 27px; color:#475569; font-size:9px; line-height:1.45; }
.verification-flow { display:grid; grid-template-columns:minmax(0,1fr) 12px minmax(0,1fr) 12px minmax(0,1fr); align-items:center; gap:4px; margin:9px 0 0 27px; padding:7px; border-radius:7px; background:rgba(255,255,255,.72); }
.verification-flow > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.verification-flow small { color:#64748b; font-size:7px; }
.verification-flow strong { overflow:hidden; color:#1f2937; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.verification-flow > svg { color:#94a3b8; }
.verification-interpretation { display:flex; align-items:flex-start; gap:5px; margin:7px 0 0 27px; color:#475569; font-size:8px; line-height:1.5; }
.verification-interpretation svg { flex:0 0 auto; margin-top:1px; color:#2563eb; }
.spinning { animation:evolution-spin .8s linear infinite; }
@keyframes evolution-spin { to { transform:rotate(360deg); } }
</style>
