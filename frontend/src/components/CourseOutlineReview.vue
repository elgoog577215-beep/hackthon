<template>
  <section class="outline-review" :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程目录确认')">
    <article class="outline-review__sheet">
      <div v-if="loading" class="outline-review__loading" aria-live="polite">
        <LoaderCircle :size="18" />
        <span>{{ t('courseGeneration.outlineReview.loading', '正在载入可编辑目录') }}</span>
      </div>

      <div v-else-if="loadError" class="outline-review__load-error" role="alert">
        <TriangleAlert :size="17" />
        <div>
          <strong>{{ loadError }}</strong>
          <p>{{ t('courseGeneration.outlineReview.loadErrorHelp', '已生成结果仍然保留，重新载入不会重复创建课程。') }}</p>
        </div>
        <button type="button" @click="loadBlueprint">{{ t('courseGeneration.outlineReview.retry', '重试') }}</button>
      </div>

      <template v-else>
        <div class="outline-review__body">
          <div class="outline-review__setup">
          <section
            v-if="retrievalProposal"
            class="outline-retrieval"
            data-testid="retrieval-outline-proposal"
          >
            <header>
              <div>
                <strong>{{ t('courseGeneration.outlineReview.retrievalTitle', '联网研究调整提案') }}</strong>
                <small>{{ t('courseGeneration.outlineReview.retrievalRevision', '检索包修订 {revision}').replace('{revision}', String(retrievalProposal.retrieval_package_revision || 1)) }}</small>
              </div>
              <span>{{ t('courseGeneration.outlineReview.retrievalPending', '确认目录后生效') }}</span>
            </header>
            <p>{{ retrievalProposal.reason || t('courseGeneration.outlineReview.retrievalReasonFallback', '外部资料建议调整当前课程结构。') }}</p>
            <div class="outline-retrieval__shape">
              <span>{{ shapeSummary(retrievalProposal.diff?.before) }}</span>
              <ArrowRight :size="13" />
              <span>{{ shapeSummary(retrievalProposal.diff?.after) }}</span>
            </div>
            <div class="outline-retrieval__diff">
              <section v-for="group in retrievalDiffGroups" :key="group.key" v-show="group.items.length">
                <h3>{{ group.label }}</h3>
                <ul>
                  <li v-for="item in group.items" :key="`${group.key}-${item.node_id || item.node_name}`">
                    <span>{{ item.node_name || item.title }}</span>
                    <small>{{ item.old_position && item.new_position
                      ? `${item.old_position} → ${item.new_position}`
                      : item.new_position || item.old_position || changedFieldSummary(item.changes) }}</small>
                  </li>
                </ul>
              </section>
            </div>
            <div v-if="retrievalProposal.sources?.length" class="outline-retrieval__sources">
              <a
                v-for="source in retrievalProposal.sources"
                v-show="safeExternalUrl(source.url)"
                :key="source.source_id"
                class="outline-retrieval__source"
                :href="safeExternalUrl(source.url)"
                target="_blank"
                rel="noopener noreferrer"
              >
                <strong>{{ source.title || source.domain }}</strong>
                <small>{{ source.domain }} · {{ source.trust_tier }}<template v-if="source.published_date"> · {{ source.published_date }}</template></small>
              </a>
            </div>
          </section>

          <section
            v-else-if="retrievalNotice || retrievalErrorKey"
            class="outline-retrieval outline-retrieval--notice"
            data-testid="retrieval-outline-notice"
            role="status"
          >
            <div>
              <strong>{{ t('courseGeneration.outlineReview.retrievalIncomplete', '联网核验未完成') }}</strong>
              <p>{{ retrievalFailureDetail }}</p>
              <p v-if="retrievalFailureStats" class="outline-retrieval__stats">
                {{ retrievalFailureStats }}
              </p>
            </div>
            <button type="button" :disabled="retryingRetrieval" @click="retryRetrieval">
              <LoaderCircle v-if="retryingRetrieval" :size="14" />
              {{ retryingRetrieval
                ? t('courseGeneration.outlineReview.retrievalRetrying', '正在重试')
                : t('courseGeneration.outlineReview.retrievalRetry', '重试联网核验') }}
            </button>
            <small>{{ t('courseGeneration.outlineReview.retrievalOffline', '也可以直接确认当前本地蓝图，离线继续。') }}</small>
          </section>

          <section v-if="isProjectCourse" class="outline-review__starting-point" :data-status="startingProfileStatus">
            <header>
              <span>{{ t('courseGeneration.outlineReview.startingPoint', '项目起点') }}</span>
              <strong>{{ startingProfileStatusLabel }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.deliverable', '最终交付物') }}</small>
                <span>{{ projectDeliverable || t('courseGeneration.outlineReview.deliverablePending', '按项目目标确定') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.experience', '已有经验') }}</small>
                <span>{{ startingStrengths || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.focusAreas', '重点补充') }}</small>
                <span>{{ startingFocus || t('courseGeneration.outlineReview.discoverInProject', '将在项目过程中继续识别') }}</span>
              </p>
            </div>
          </section>
          <section v-else-if="courseType === 'inquiry'" class="outline-review__starting-point" data-status="tentative">
            <header>
              <span>{{ t('courseGeneration.outlineReview.inquiryContract', '探究信息') }}</span>
              <strong>{{ t('courseGeneration.outlineReview.inquiryGuard', '待验证') }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.coreQuestion', '核心问题') }}</small>
                <span>{{ courseIntent.core_question }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.evidenceScope', '证据范围') }}</small>
                <span>{{ courseIntent.evidence_scope || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.desiredOutput', '结论形态') }}</small>
                <span>{{ courseIntent.desired_output }}</span>
              </p>
            </div>
          </section>

          <section v-else-if="courseType === 'exam'" class="outline-review__starting-point" data-status="tentative">
            <header>
              <span>{{ t('courseGeneration.outlineReview.examContract', '考试信息') }}</span>
              <strong>{{ courseIntent.exam_date || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.examName', '考试') }}</small>
                <span>{{ courseIntent.exam_name }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.examScope', '考纲范围') }}</small>
                <span>{{ courseIntent.exam_scope }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.currentPreparation', '当前准备度') }}</small>
                <span>{{ courseIntent.current_preparation || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
            </div>
          </section>

          <section class="outline-review__adjustment" :aria-busy="generatingProposal">
            <div class="outline-review__adjustment-heading">
              <label for="outline-adjustment-instruction">
                {{ t('courseGeneration.outlineReview.adjustmentTitle', '目录调整') }}
              </label>
              <span class="outline-review__count">
                {{ t('courseGeneration.outlineReview.sectionCount', '{count} 个目录节点').replace('{count}', String(blueprintNodes.length)) }}
              </span>
            </div>
            <textarea
              id="outline-adjustment-instruction"
              v-model="adjustmentInstruction"
              rows="2"
              maxlength="3000"
              :disabled="adjustmentBusy"
              :placeholder="t('courseGeneration.outlineReview.adjustmentPlaceholder', '例如：把生命周期移到工程实践章最前面，再新增一节组件组合实战')"
            />
            <button
              type="button"
              data-testid="generate-outline-adjustment"
              :disabled="adjustmentBusy || !adjustmentInstruction.trim() || !blueprintNodes.length"
              @click="generateAdjustmentProposal"
            >
              <LoaderCircle v-if="generatingProposal" :size="15" />
              <Sparkles v-else :size="15" />
              {{ generatingProposal
                ? t('courseGeneration.outlineReview.adjustmentGenerating', '正在生成方案')
                : t('courseGeneration.outlineReview.adjustmentGenerate', '生成调整方案') }}
            </button>
          </section>

          <p v-if="proposalNotice" class="outline-review__proposal-notice" role="status">
            {{ proposalNotice }}
          </p>

          <section
            v-if="adjustmentProposal"
            ref="proposalSummaryRef"
            class="outline-review__proposal"
            tabindex="-1"
            aria-labelledby="outline-adjustment-summary"
          >
            <details open>
              <summary id="outline-adjustment-summary">
                <span>{{ t('courseGeneration.outlineReview.proposalTitle', '调整方案预览') }}</span>
                <strong>
                  {{ shapeSummary(adjustmentProposal.diff?.before) }}
                  <ArrowRight :size="13" />
                  {{ shapeSummary(adjustmentProposal.diff?.after) }}
                </strong>
              </summary>
              <p class="outline-review__proposal-summary">{{ adjustmentProposal.summary }}</p>

              <div class="outline-review__diff-groups">
                <section v-if="adjustmentProposal.diff?.added?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffAdded', '新增') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.added" :key="`added-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span><small>{{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.removed?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffRemoved', '删除') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.removed" :key="`removed-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span><small>{{ item.old_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.moved?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffMoved', '移动') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.moved" :key="`moved-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span>
                      <small>{{ item.old_position }} → {{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.updated?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffUpdated', '内容修改') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.updated" :key="`updated-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span>
                      <small>{{ changedFieldSummary(item.changes) }}</small>
                    </li>
                  </ul>
                </section>
              </div>

              <ul v-if="adjustmentProposal.blocking_issues?.length" class="outline-review__blockers" role="alert">
                <li v-for="issue in adjustmentProposal.blocking_issues" :key="issue.code || issue.message">
                  {{ issue.message }}
                </li>
              </ul>

              <div class="outline-review__proposal-actions">
                <button
                  type="button"
                  data-testid="cancel-outline-adjustment"
                  :disabled="applyingProposal"
                  @click="cancelAdjustmentProposal"
                >
                  {{ t('courseGeneration.outlineReview.proposalCancel', '取消') }}
                </button>
                <button
                  type="button"
                  class="primary"
                  data-testid="apply-outline-adjustment"
                  :disabled="applyingProposal || !adjustmentProposal.can_apply"
                  @click="applyAdjustmentProposal"
                >
                  <LoaderCircle v-if="applyingProposal" :size="15" />
                  {{ applyingProposal
                    ? t('courseGeneration.outlineReview.proposalApplying', '正在应用')
                    : t('courseGeneration.outlineReview.proposalApply', '应用整套方案') }}
                </button>
              </div>
            </details>
          </section>
          </div>

          <nav
            v-if="chapterJumps.length > 1"
            class="outline-review__chapter-nav"
            :aria-label="t('courseGeneration.outlineReview.chapterNavigation', '按章快速定位')"
          >
            <span>{{ t('courseGeneration.outlineReview.chapterNavigationShort', '快速定位') }}</span>
            <div>
              <button
                v-for="chapter in chapterJumps"
                :key="chapter.node.node_id || chapter.index"
                type="button"
                :title="chapter.node.node_name"
                @click="jumpToChapter(chapter.index)"
              >
                {{ chapter.node.node_name }}
              </button>
            </div>
          </nav>

          <ol class="outline-review__nodes">
            <li
              v-for="(node, index) in blueprintNodes"
              :key="node.node_id || index"
              :id="outlineNodeId(index)"
              :data-level="node.node_level || 2"
            >
              <span class="outline-review__index">{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="outline-review__branch" aria-hidden="true"></span>
              <div>
                <div v-if="node.learning_path_role" class="outline-review__node-meta">
                  <span :data-role="normalizedPathRole(node.learning_path_role)">
                    {{ pathRoleLabel(node.learning_path_role) }}
                  </span>
                  <p v-if="node.path_reason">{{ node.path_reason }}</p>
                </div>
                <input
                  v-model="node.node_name"
                  type="text"
                  :disabled="adjustmentBusy"
                  :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
                  @input="invalidateProposal"
                />
                <textarea
                  v-if="Number(node.node_level || 2) >= 2 || 'learning_objective' in node"
                  v-model="node.learning_objective"
                  rows="1"
                  :disabled="adjustmentBusy"
                  :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '写清这一节结束后，学习者能够做到什么')"
                  :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                  @input="invalidateProposal"
                />
              </div>
            </li>
          </ol>

          <p v-if="!blueprintNodes.length" class="outline-review__empty">
            {{ t('courseGeneration.outlineReview.empty', '目录尚未形成，请重新载入后再确认。') }}
          </p>
        </div>
      </template>

      <footer class="outline-review__footer">
        <p v-if="actionError" class="outline-review__action-error" role="alert">{{ actionError }}</p>
        <div class="outline-review__actions">
          <span
            v-if="!dirty && !saving && !loading && blueprintNodes.length"
            class="outline-review__saved-state"
            role="status"
          >
            <CircleCheck :size="15" />
            {{ t('courseGeneration.outlineReview.savedState', '已保存') }}
          </span>
          <button
            v-else
            type="button"
            class="secondary"
            :disabled="loading || acting || !!adjustmentProposal || !dirty || !blueprintNodes.length"
            @click="saveDraft"
          >
            <LoaderCircle v-if="saving" :size="15" />
            <Save v-else :size="15" />
            {{ saving
              ? t('courseGeneration.outlineReview.saving', '保存中')
              : t('courseGeneration.outlineReview.save', '保存修改') }}
          </button>
          <button
            type="button"
            class="primary"
            :disabled="loading || acting || !!adjustmentProposal || !blueprintNodes.length"
            @click="confirmOutline"
          >
            <LoaderCircle v-if="confirming" :size="15" />
            <ArrowRight v-else :size="15" />
            {{ t('courseGeneration.gate.confirmOutline', '确认目录并继续') }}
          </button>
        </div>
      </footer>
    </article>
    <span class="outline-review__sr-only" aria-live="polite">{{ liveStatus }}</span>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowRight, CircleCheck, LoaderCircle, Save, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import type { Node, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'
import { retrievalErrorTranslationKey } from '../utils/retrieval-errors'

const props = withDefaults(defineProps<{
  courseId: string
  courseName?: string
  nodes?: Node[]
  task?: Task
}>(), {
  courseName: '',
  nodes: () => [],
  task: undefined,
})

const emit = defineEmits<{
  (event: 'confirmed'): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const blueprintDraft = ref<Record<string, any>>({})
const retrievalArtifact = ref<Record<string, any>>({})
const baseline = ref('')
const loading = ref(false)
const saving = ref(false)
const confirming = ref(false)
const loadError = ref('')
const actionError = ref('')
const adjustmentInstruction = ref('')
const adjustmentProposal = ref<Record<string, any> | null>(null)
const generatingProposal = ref(false)
const applyingProposal = ref(false)
const retryingRetrieval = ref(false)
const proposalNotice = ref('')
const liveStatus = ref('')
const proposalSummaryRef = ref<HTMLElement | null>(null)
const adjustmentRequestId = ref('')

const adjustmentBusy = computed(() => generatingProposal.value || applyingProposal.value)
const retrievalProposal = computed<Record<string, any> | null>(() => (
  retrievalArtifact.value?.proposal || null
))
const retrievalNotice = computed(() => String(retrievalArtifact.value?.notice || '').trim())
const retrievalErrorKey = computed(() => retrievalErrorTranslationKey(retrievalArtifact.value))
const retrievalFailureDetail = computed(() => {
  return retrievalErrorKey.value
    ? t(retrievalErrorKey.value, retrievalNotice.value)
    : retrievalNotice.value
})
const retrievalPackage = computed<Record<string, any>>(() => (
  retrievalArtifact.value?.package
  || retrievalArtifact.value?.retrieval_package
  || retrievalArtifact.value
  || {}
))
const retrievalFailureStats = computed(() => {
  const receipt = retrievalPackage.value?.receipt || {}
  const admittedValue = Number(receipt.admitted_count ?? receipt.source_count ?? 0)
  const admitted = Number.isFinite(admittedValue) ? Math.max(0, admittedValue) : 0
  const rejectedSources = retrievalPackage.value?.rejected_sources
  const rejectedValue = Array.isArray(rejectedSources)
    ? rejectedSources.length
    : Number(receipt.tier_distribution?.tier_c ?? 0)
  const rejected = Number.isFinite(rejectedValue) ? Math.max(0, rejectedValue) : 0
  const total = admitted + rejected
  if (total <= 0) return ''
  return t(
    'courseGeneration.outlineReview.retrievalStats',
    '已检查 {total} 个候选来源，其中 {admitted} 个符合准入标准。',
  )
    .replace('{total}', String(total))
    .replace('{admitted}', String(admitted))
})
const retrievalDiffGroups = computed(() => {
  const diff = retrievalProposal.value?.diff || {}
  return [
    { key: 'added', label: t('courseGeneration.outlineReview.diffAdded', '新增'), items: diff.added || [] },
    { key: 'removed', label: t('courseGeneration.outlineReview.diffRemoved', '删除'), items: diff.removed || [] },
    { key: 'moved', label: t('courseGeneration.outlineReview.diffMoved', '移动'), items: diff.moved || [] },
    { key: 'updated', label: t('courseGeneration.outlineReview.diffUpdated', '内容修改'), items: diff.updated || [] },
  ]
})
const acting = computed(() => saving.value || confirming.value || adjustmentBusy.value)
const blueprintNodes = computed<any[]>(() => (
  Array.isArray(blueprintDraft.value?.nodes)
    ? blueprintDraft.value.nodes
    : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes)
      ? blueprintDraft.value.course_blueprint.nodes
      : []
))
const chapterJumps = computed(() => blueprintNodes.value
  .map((node, index) => ({ node, index }))
  .filter(item => Number(item.node.node_level || 2) === 1))
const courseType = computed(() => String(blueprintDraft.value?.course_type || props.task?.courseType || 'systematic'))
const isProjectCourse = computed(() => courseType.value === 'project')
const courseIntent = computed<Record<string, any>>(() => blueprintDraft.value?.course_intent || {})
const startingProfile = computed<Record<string, any>>(() => blueprintDraft.value?.learner_starting_profile || {})
const startingProfileStatus = computed(() => String(startingProfile.value.status || 'insufficient'))
const projectDeliverable = computed(() => String(courseIntent.value.expected_deliverable || '').trim())
const startingStrengths = computed(() => listText(startingProfile.value.self_reported_strengths))
const startingFocus = computed(() => listText(startingProfile.value.focus_areas))
const startingProfileStatusLabel = computed(() => startingProfileStatus.value === 'insufficient'
  ? t('courseGeneration.outlineReview.startingPointInsufficient', '起点信息不足')
  : t('courseGeneration.outlineReview.startingPointTentative', '暂定起点'))
const draftSignature = computed(() => JSON.stringify({
  course_name: blueprintDraft.value?.course_name || '',
  nodes: blueprintNodes.value.map(node => ({
    node_id: node.node_id,
    node_name: node.node_name,
    node_level: node.node_level,
    learning_objective: node.learning_objective || '',
    prerequisite_node_ids: node.prerequisite_node_ids || [],
  })),
}))
const dirty = computed(() => Boolean(baseline.value && draftSignature.value !== baseline.value))

onMounted(loadBlueprint)
watch(() => props.courseId, (courseId, previous) => {
  if (courseId && courseId !== previous) void loadBlueprint()
})

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function listText(value: unknown) {
  if (!Array.isArray(value)) return ''
  return value.map(item => String(item || '').trim()).filter(Boolean).join('；')
}

function outlineNodeId(index: number) {
  return `outline-review-node-${index}`
}

function jumpToChapter(index: number) {
  const target = document.getElementById(outlineNodeId(index))
  if (!target) return
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
}

function normalizedPathRole(value: unknown) {
  const role = String(value || '')
  return ['focus', 'standard', 'compressed', 'verify_in_project', 'milestone'].includes(role)
    ? role
    : 'standard'
}

function pathRoleLabel(value: unknown) {
  const labels = {
    focus: t('courseGeneration.outlineReview.pathRoles.focus', '重点补充'),
    standard: t('courseGeneration.outlineReview.pathRoles.standard', '正常学习'),
    compressed: t('courseGeneration.outlineReview.pathRoles.compressed', '快速通过'),
    verify_in_project: t('courseGeneration.outlineReview.pathRoles.verifyInProject', '项目中验证'),
    milestone: t('courseGeneration.outlineReview.pathRoles.milestone', '项目节点'),
  }
  return labels[normalizedPathRole(value) as keyof typeof labels]
}

function seedNodesFromCourse() {
  if (blueprintNodes.value.length || !props.nodes.length) return
  blueprintDraft.value.nodes = props.nodes
    .filter(node => node.node_level <= 2)
    .map(node => ({
      node_id: node.node_id,
      parent_node_id: node.parent_node_id,
      node_name: node.node_name,
      node_level: node.node_level,
      learning_objective: node.learning_objective || '',
      learning_path_role: node.learning_path_role,
      path_reason: node.path_reason,
    }))
}

function syncNavigationFromDraft() {
  if (courseStore.currentCourseId !== props.courseId || !blueprintNodes.value.length) return
  courseStore.applyGenerationOutlineDraft(blueprintNodes.value)
}

async function loadBlueprint() {
  if (!props.courseId || loading.value) return
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    const data = await workspace.loadBlueprint(props.courseId)
    retrievalArtifact.value = clone(data.retrieval || {})
    blueprintDraft.value = clone(data.draft || data.current || data || {})
    seedNodesFromCourse()
    if (!blueprintDraft.value.course_name) blueprintDraft.value.course_name = props.courseName
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    adjustmentProposal.value = null
    proposalNotice.value = ''
  } catch {
    loadError.value = t('courseGeneration.gate.loadFailed', '当前确认内容读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function draftPayload(
  source: Record<string, any> = blueprintDraft.value,
  expectedDraftRevisionId?: string,
  proposalId?: string,
  adjustmentOperations?: Record<string, any>[],
) {
  const draft = source
  return {
    base_blueprint_revision_id: draft.base_blueprint_revision_id,
    expected_draft_revision_id: expectedDraftRevisionId || draft.draft_revision_id,
    adjustment_proposal_id: proposalId,
    adjustment_operations: adjustmentOperations,
    course_name: draft.course_name,
    course_purpose: draft.course_purpose,
    course_type: draft.course_type,
    course_intent: draft.course_intent,
    learner_starting_profile: draft.learner_starting_profile,
    course_blueprint: draft.course_blueprint,
    nodes: draft.nodes,
    learning_asset_plan: draft.learning_asset_plan,
    blueprint_locks: draft.blueprint_locks || {},
  }
}

async function persistDraft(showMessage = true) {
  if (!blueprintNodes.value.length) return
  const result = await workspace.saveBlueprint(props.courseId, draftPayload())
  if (result?.draft) blueprintDraft.value = clone(result.draft)
  syncNavigationFromDraft()
  baseline.value = draftSignature.value
  if (showMessage) ElMessage.success(t('courseGeneration.outlineReview.savedMessage', '目录修改已保存'))
}

function safeExternalUrl(value: unknown) {
  try {
    const parsed = new URL(String(value || ''))
    return parsed.protocol === 'https:' ? parsed.toString() : ''
  } catch {
    return ''
  }
}

async function retryRetrieval() {
  if (!props.courseId || retryingRetrieval.value) return
  retryingRetrieval.value = true
  actionError.value = ''
  try {
    const result = await workspace.retryBlueprintRetrieval(props.courseId)
    retrievalArtifact.value = clone(result.retrieval || {})
    const candidate = retrievalArtifact.value?.proposal?.candidate_draft
    if (candidate) {
      blueprintDraft.value = clone(candidate)
      baseline.value = draftSignature.value
      syncNavigationFromDraft()
    }
  } catch (error: any) {
    actionError.value = error?.response?.data?.detail?.message || t(
      'courseGeneration.outlineReview.retrievalRetryFailed',
      '联网核验重试失败，当前本地蓝图仍然保留。',
    )
  } finally {
    retryingRetrieval.value = false
  }
}

function requestId() {
  return `outline-adjustment-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function shapeSummary(shape: Record<string, any> | undefined) {
  const chapters = Number(shape?.chapter_count || 0)
  const sections = Number(shape?.section_count || 0)
  return t('courseGeneration.outlineReview.shapeSummary', '{chapters} 章 · {sections} 节')
    .replace('{chapters}', String(chapters))
    .replace('{sections}', String(sections))
}

function changedFieldSummary(changes: Record<string, any> | undefined) {
  const labels: Record<string, string> = {
    node_name: t('courseGeneration.outlineReview.changedName', '标题'),
    learning_objective: t('courseGeneration.outlineReview.changedObjective', '学习目标'),
    prerequisite_node_ids: t('courseGeneration.outlineReview.changedDependencies', '前置依赖'),
  }
  return Object.keys(changes || {}).map(field => labels[field] || field).join('、')
}

function invalidateProposal() {
  if (!adjustmentProposal.value) return
  adjustmentProposal.value = null
  proposalNotice.value = t(
    'courseGeneration.outlineReview.proposalInvalidated',
    '目录已被手动修改，请重新生成方案',
  )
  liveStatus.value = proposalNotice.value
}

async function generateAdjustmentProposal() {
  const instruction = adjustmentInstruction.value.trim()
  if (!instruction || acting.value || !blueprintNodes.value.length) return
  generatingProposal.value = true
  adjustmentProposal.value = null
  proposalNotice.value = ''
  actionError.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.adjustmentGenerating', '正在生成方案')
  try {
    if (dirty.value) await persistDraft(false)
    adjustmentRequestId.value = requestId()
    const proposal = await workspace.previewBlueprintAdjustment(props.courseId, {
      request_id: adjustmentRequestId.value,
      base_blueprint_revision_id: blueprintDraft.value.base_blueprint_revision_id,
      expected_draft_revision_id: blueprintDraft.value.draft_revision_id,
      instruction,
    })
    adjustmentProposal.value = clone(proposal)
    liveStatus.value = proposal.can_apply
      ? t('courseGeneration.outlineReview.proposalReady', '调整方案已生成，请检查整套差异')
      : t('courseGeneration.outlineReview.proposalBlocked', '调整方案存在阻断项，不能应用')
    await nextTick()
    proposalSummaryRef.value?.focus()
  } catch (error: any) {
    const status = Number(error?.response?.status || 0)
    actionError.value = status === 409
      ? t('courseGeneration.outlineReview.proposalConflict', '目录版本已变化，请重新载入后生成方案。')
      : status === 503
        ? t('courseGeneration.outlineReview.proposalUnavailable', 'AI 调整服务暂时不可用，请稍后重试。')
        : t('courseGeneration.outlineReview.proposalFailed', '调整方案生成失败，请换一种说法后重试。')
    liveStatus.value = actionError.value
  } finally {
    generatingProposal.value = false
  }
}

function cancelAdjustmentProposal() {
  const proposalId = String(adjustmentProposal.value?.proposal_id || '')
  if (proposalId && adjustmentRequestId.value) {
    void workspace.cancelBlueprintAdjustment(
      props.courseId,
      proposalId,
      adjustmentRequestId.value,
    ).catch(() => undefined)
  }
  adjustmentProposal.value = null
  proposalNotice.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.proposalCancelled', '已取消调整方案，目录没有变化')
}

async function applyAdjustmentProposal() {
  const proposal = adjustmentProposal.value
  if (!proposal?.can_apply || acting.value) return
  applyingProposal.value = true
  actionError.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.proposalApplying', '正在应用')
  try {
    const candidate = clone(proposal.draft || {})
    const result = await workspace.saveBlueprint(
      props.courseId,
      draftPayload(
        candidate,
        proposal.source_draft_revision_id,
        proposal.proposal_id,
        proposal.operations,
      ),
    )
    adjustmentProposal.value = null
    blueprintDraft.value = clone(result?.draft || candidate)
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    proposalNotice.value = t('courseGeneration.outlineReview.proposalApplied', '方案已应用并保存')
    liveStatus.value = proposalNotice.value
    ElMessage.success(proposalNotice.value)
  } catch (error: any) {
    const status = Number(error?.response?.status || 0)
    actionError.value = status === 409
      ? t('courseGeneration.outlineReview.proposalConflict', '目录版本已变化，请重新载入后生成方案。')
      : t('courseGeneration.outlineReview.proposalApplyFailed', '方案应用失败，原目录草稿未改变。')
    liveStatus.value = actionError.value
  } finally {
    applyingProposal.value = false
  }
}

async function saveDraft() {
  if (!dirty.value || acting.value) return
  saving.value = true
  actionError.value = ''
  try {
    await persistDraft()
  } catch {
    actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
  } finally {
    saving.value = false
  }
}

async function confirmOutline() {
  if (!blueprintNodes.value.length || acting.value) return
  confirming.value = true
  actionError.value = ''
  try {
    if (dirty.value) await persistDraft(false)
    await workspace.confirmGenerationStep(props.courseId, 'outline')
    generationStore.startGlobalMonitor()
    await courseStore.refreshCourseData(props.courseId)
    ElMessage.success(t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
    emit('confirmed')
  } catch {
    actionError.value = t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。')
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.outline-review {
  box-sizing:border-box;
  height:100%;
  min-height:0;
  flex:1;
  display:flex;
  overflow:hidden;
  padding:0 clamp(24px,4vw,64px);
  background:#fff;
}
.outline-review__sheet {
  width:min(1280px,100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:minmax(0,1fr) auto;
  margin:0 auto;
  overflow:hidden;
  background:#fff;
}
.outline-review__count {
  flex:0 0 auto;
  color:#7b8494;
  font-size:11px;
  font-weight:750;
}
.outline-review__loading,
.outline-review__load-error {
  grid-row:1;
  min-height:260px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:9px;
  padding:30px;
  color:#687386;
  font-size:13px;
}
.outline-review__loading svg {
  color:#4f46d9;
  animation:outline-review-spin .9s linear infinite;
}
.outline-review__load-error {
  min-height:150px;
  color:#9a4d13;
}
.outline-review__load-error > div { max-width:520px; }
.outline-review__load-error p { margin:4px 0 0; color:#84664c; font-size:12px; }
.outline-review__load-error button {
  min-height:38px;
  padding:0 14px;
  border:1px solid #e2a753;
  border-radius:7px;
  color:#9a4d13;
  background:#fffaf0;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__body {
  min-height:0;
  overflow:auto;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  scrollbar-color:#c9ced8 transparent;
}
.outline-review__setup {
  min-width:0;
  border-bottom:1px solid #eceef2;
}
.outline-review__setup > :first-child { border-top:0; }
.outline-review input,
.outline-review textarea {
  width:100%;
  border:1px solid transparent;
  border-radius:7px;
  color:#273144;
  background:transparent;
  outline:none;
  transition:border-color .16s ease,background .16s ease,box-shadow .16s ease;
}
.outline-review input:hover,
.outline-review textarea:hover { background:#f8f9fb; }
.outline-review input:focus,
.outline-review textarea:focus {
  border-color:#aeb4e9;
  background:#fff;
  box-shadow:0 0 0 3px rgba(79,70,217,.08);
}
.outline-review__starting-point {
  margin:0;
  padding:16px 0 18px 114px;
  border-top:1px solid #eceef2;
}
.outline-review__starting-point > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.outline-review__starting-point > header span {
  color:#344054;
  font-size:12px;
  font-weight:800;
}
.outline-review__starting-point > header strong {
  padding:0;
  color:#087a5b;
  font-size:11px;
}
.outline-review__starting-point[data-status="insufficient"] > header strong {
  color:#9a5b17;
}
.outline-review__starting-point > div {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:16px;
}
.outline-review__starting-point p { min-width:0; margin:0; }
.outline-review__starting-point small {
  display:block;
  margin-bottom:3px;
  color:#8a93a3;
  font-size:11px;
  font-weight:750;
}
.outline-review__starting-point p span {
  display:block;
  overflow-wrap:anywhere;
  color:#455166;
  font-size:12px;
  line-height:1.5;
}
.outline-retrieval { margin:0; padding:18px 0 20px 114px; border-top:1px solid #eceef2; }
.outline-retrieval > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-retrieval > header div { display:grid; gap:2px; }
.outline-retrieval > header strong { color:#312e81; font-size:14px; }
.outline-retrieval > header small,.outline-retrieval > header > span { color:#6366f1; font-size:11px; }
.outline-retrieval > header > span { padding:2px 0; white-space:nowrap; }
.outline-retrieval > p { max-width:880px; margin:10px 0; color:#475569; font-size:13px; line-height:1.65; }
.outline-retrieval__shape { display:flex; align-items:center; gap:7px; color:#4338ca; font-size:12px; }
.outline-retrieval__diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; border-bottom:1px solid #e4e7f5; }
.outline-retrieval__diff section { min-width:0; padding:12px 18px 13px 0; }
.outline-retrieval__diff section + section { padding-left:18px; border-left:1px solid #e4e7f5; }
.outline-retrieval__diff h3 { margin:0 0 7px; color:#475569; font-size:12px; }
.outline-retrieval__diff ul { margin:0; padding-left:17px; }
.outline-retrieval__diff li { margin:4px 0; color:#334155; font-size:12px; line-height:1.5; }
.outline-retrieval__diff li small { display:block; color:#64748b; font-size:11px; }
.outline-retrieval__sources { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; }
.outline-retrieval__source { min-width:0; display:grid; gap:3px; padding:11px 14px 0 0; color:#3730a3; text-decoration:none; }
.outline-retrieval__source + .outline-retrieval__source { padding-left:14px; border-left:1px solid #e4e7f5; }
.outline-retrieval__source:hover strong { text-decoration:underline; }
.outline-retrieval__source strong { overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.outline-retrieval__source small { color:#64748b; font-size:11px; }
.outline-retrieval--notice { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; }
.outline-retrieval--notice strong { color:#9a3412; font-size:13px; }
.outline-retrieval--notice p { margin:2px 0 0; color:#9a3412; font-size:12px; }
.outline-retrieval--notice .outline-retrieval__stats { color:#7c2d12; font-size:11px; }
.outline-retrieval--notice button { border:1px solid #fdba74; border-radius:8px; padding:6px 9px; color:#9a3412; background:#fff; font-size:11px; cursor:pointer; }
.outline-retrieval--notice > small { grid-column:1/-1; color:#7c2d12; font-size:11px; }
.outline-review__adjustment {
  display:grid;
  grid-template-columns:minmax(180px,.8fr) minmax(280px,1.7fr) auto;
  align-items:center;
  gap:14px;
  margin:0;
  padding:16px 0;
  border-top:1px solid #eceef2;
}
.outline-review__adjustment label {
  color:#344054;
  font-size:12px;
  font-weight:850;
}
.outline-review__adjustment-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.outline-review__adjustment textarea {
  min-height:56px;
  padding:9px 11px;
  border-color:#d9ddea;
  background:#fbfbfe;
  resize:vertical;
  font-size:12px;
  line-height:1.5;
}
.outline-review__adjustment button,
.outline-review__proposal-actions button {
  min-height:39px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 13px;
  border:1px solid #c9cdea;
  border-radius:8px;
  color:#454ca8;
  background:#f7f7ff;
  font-size:11px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__adjustment button:disabled,
.outline-review__proposal-actions button:disabled { opacity:.5; cursor:not-allowed; }
.outline-review__adjustment svg.lucide-loader-circle,
.outline-review__proposal-actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
.outline-review__proposal-notice {
  margin:0;
  padding:7px 0 10px 114px;
  color:#087a5b;
  font-size:11px;
  font-weight:750;
}
.outline-review__proposal {
  margin:0 0 16px 114px;
  border:1px solid #d9dcef;
  border-radius:10px;
  background:#fbfbff;
  outline:none;
}
.outline-review__proposal:focus { box-shadow:0 0 0 3px rgba(79,70,217,.1); }
.outline-review__proposal details { padding:10px 12px 12px; }
.outline-review__proposal summary {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  color:#343b86;
  font-size:11px;
  font-weight:850;
  cursor:pointer;
}
.outline-review__proposal summary strong {
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#60687b;
  font-size:11px;
}
.outline-review__proposal-summary {
  margin:9px 0;
  color:#3e485b;
  font-size:12px;
  line-height:1.55;
}
.outline-review__diff-groups {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
.outline-review__diff-groups section {
  min-width:0;
  padding:10px 14px 10px 0;
  border-top:1px solid #e5e7ef;
}
.outline-review__diff-groups section + section { padding-left:14px; border-left:1px solid #e5e7ef; }
.outline-review__diff-groups h3 { margin:0 0 5px; color:#596579; font-size:11px; }
.outline-review__diff-groups ul,
.outline-review__blockers { margin:0; padding-left:16px; }
.outline-review__diff-groups li { margin:3px 0; color:#344054; font-size:11px; }
.outline-review__diff-groups li span,
.outline-review__diff-groups li small { display:block; overflow-wrap:anywhere; }
.outline-review__diff-groups li small { margin-top:1px; color:#7b8494; font-size:11px; }
.outline-review__blockers {
  margin-top:9px;
  color:#b42318;
  font-size:11px;
}
.outline-review__proposal-actions {
  display:flex;
  justify-content:flex-end;
  gap:7px;
  margin-top:10px;
}
.outline-review__proposal-actions button.primary {
  border-color:#454ca8;
  color:#fff;
  background:#454ca8;
}
.outline-review__sr-only {
  position:absolute;
  width:1px;
  height:1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
}
.outline-review__nodes {
  display:grid;
  min-height:0;
  overflow:visible;
  margin:0;
  padding:8px 0 20px;
  list-style:none;
}
.outline-review__chapter-nav {
  position:sticky;
  z-index:2;
  top:0;
  min-height:40px;
  display:flex;
  align-items:center;
  gap:10px;
  padding:7px 0;
  border-bottom:1px solid #e7e9ee;
  background:rgba(255,255,255,.97);
}
.outline-review__chapter-nav > span {
  flex:0 0 auto;
  color:#7b8494;
  font-size:11px;
  font-weight:750;
}
.outline-review__chapter-nav > div {
  min-width:0;
  display:flex;
  gap:4px;
  overflow-x:auto;
  scrollbar-width:none;
}
.outline-review__chapter-nav > div::-webkit-scrollbar { display:none; }
.outline-review__chapter-nav button {
  max-width:150px;
  height:28px;
  flex:0 0 auto;
  overflow:hidden;
  padding:0 9px;
  border:1px solid transparent;
  border-radius:6px;
  color:#596579;
  background:transparent;
  cursor:pointer;
  font-size:11px;
  font-weight:700;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.outline-review__chapter-nav button:hover,
.outline-review__chapter-nav button:focus-visible {
  border-color:#c9cdea;
  color:#454ca8;
  background:#f7f7ff;
  outline:none;
}
.outline-review__nodes li {
  position:relative;
  display:grid;
  grid-template-columns:34px 14px minmax(0,1fr);
  gap:9px;
  padding:10px 0;
  border-bottom:1px solid #eef0f3;
  scroll-margin-top:44px;
}
.outline-review__nodes li:last-child { border-bottom:0; }
.outline-review__nodes li[data-level="1"] { margin-top:2px; }
.outline-review__index {
  padding-top:8px;
  color:#969eac;
  font:700 11px/1 ui-monospace,SFMono-Regular,monospace;
}
.outline-review__branch {
  width:8px;
  height:8px;
  margin-top:7px;
  border:1.5px solid #8f96a5;
  border-radius:50%;
  background:#fff;
}
.outline-review__nodes li[data-level="1"] .outline-review__branch {
  width:10px;
  height:10px;
  margin-top:6px;
  border:0;
  border-radius:3px;
  background:#4f5b70;
}
.outline-review__node-meta {
  min-width:0;
  display:flex;
  align-items:center;
  gap:8px;
  padding:0 8px 2px;
}
.outline-review__node-meta > span {
  flex:0 0 auto;
  padding:3px 6px;
  border:1px solid #d9dee7;
  border-radius:4px;
  color:#596579;
  background:#f8f9fb;
  font-size:11px;
  font-weight:800;
}
.outline-review__node-meta > span[data-role="focus"] {
  border-color:#e7c790;
  color:#9a5b17;
  background:#fff9ef;
}
.outline-review__node-meta > span[data-role="compressed"] {
  border-color:#bfd7cc;
  color:#087a5b;
  background:#f2faf7;
}
.outline-review__node-meta > span[data-role="verify_in_project"] {
  border-color:#c8c9ed;
  color:#4f55b5;
  background:#f4f4ff;
}
.outline-review__node-meta > span[data-role="milestone"] {
  border-color:#b9c7db;
  color:#35506f;
  background:#f3f7fb;
}
.outline-review__node-meta p {
  min-width:0;
  overflow:hidden;
  margin:0;
  color:#7b8494;
  font-size:11px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.outline-review__nodes input {
  height:31px;
  padding:0 8px;
  font-size:14px;
  font-weight:750;
}
.outline-review__nodes li[data-level="1"] input {
  color:#182230;
  font-size:15px;
}
.outline-review__nodes textarea {
  height:38px;
  min-height:38px;
  margin-top:3px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:13px;
  line-height:1.55;
}
.outline-review__empty {
  margin:0;
  padding:42px 30px;
  color:#8a93a3;
  text-align:center;
  font-size:13px;
}
.outline-review__footer {
  grid-row:2;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:24px;
  padding:13px 0 14px;
  border-top:1px solid #dfe3e9;
  background:rgba(255,255,255,.98);
}
.outline-review__footer p.outline-review__action-error { min-width:0; margin:0 auto 0 0; color:#b42318; font-size:11px; line-height:1.5; }
.outline-review__actions {
  flex:0 0 auto;
  display:flex;
  align-items:center;
  gap:8px;
}
.outline-review__saved-state {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0 8px;
  color:#087a5b;
  font-size:11px;
  font-weight:750;
  white-space:nowrap;
}
.outline-review__actions button {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 16px;
  border-radius:9px;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__actions button:disabled { opacity:.5; cursor:not-allowed; }
.outline-review__actions .secondary {
  border:1px solid #d5dae3;
  color:#596579;
  background:#fff;
}
.outline-review__actions .primary {
  border:1px solid #3f47a8;
  color:#fff;
  background:#3f47a8;
  box-shadow:0 7px 18px rgba(63,71,168,.18);
}
.outline-review__actions button:not(:disabled):hover { transform:translateY(-1px); }
.outline-review__actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
@keyframes outline-review-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .outline-review { padding:0 16px; }
  .outline-review__setup { min-height:0; }
  .outline-review__starting-point { margin:0; padding:11px 0 13px; }
  .outline-review__starting-point > div { grid-template-columns:1fr; gap:8px; }
  .outline-retrieval { padding:14px 0 16px; }
  .outline-retrieval__diff,.outline-retrieval__sources { grid-template-columns:1fr; }
  .outline-retrieval__diff section + section,.outline-retrieval__source + .outline-retrieval__source { padding-left:0; border-left:0; border-top:1px solid #e4e7f5; }
  .outline-review__adjustment {
    grid-template-columns:1fr;
    gap:8px;
    margin:0;
    padding:11px 0;
  }
  .outline-review__adjustment button { width:100%; }
  .outline-review__proposal-notice { margin:0; padding:6px 0 10px; }
  .outline-review__proposal { width:auto; margin:0 0 11px; }
  .outline-review__proposal summary { align-items:flex-start; flex-direction:column; gap:4px; }
  .outline-review__diff-groups { grid-template-columns:1fr; }
  .outline-review__proposal-actions { display:grid; grid-template-columns:1fr 1.25fr; }
  .outline-review__proposal-actions button { width:100%; }
  .outline-review__nodes { padding:4px 0 12px; }
  .outline-review__chapter-nav { padding:6px 0; }
  .outline-review__nodes li { grid-template-columns:26px 12px minmax(0,1fr); gap:6px; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:9px; padding:11px 0 13px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg { animation:none!important; }
}
</style>
