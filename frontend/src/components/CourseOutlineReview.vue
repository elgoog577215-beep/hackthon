<template>
  <section class="outline-review" :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程目录确认')">
    <article class="outline-review__sheet">
      <header class="outline-review__header">
        <div>
          <span class="outline-review__eyebrow">
            <CircleCheckBig :size="14" />
            {{ t('courseGeneration.outlineReview.eyebrow', '需要你的判断') }}
          </span>
          <h1>{{ t('courseGeneration.outlineReview.title', '确认这门课怎样展开') }}</h1>
          <p>{{ t('courseGeneration.outlineReview.help', '只检查课程名称、章节顺序和学习目标。确认后，教案与正文会沿用这份结构在当前页面继续生长。') }}</p>
        </div>
        <span class="outline-review__count">
          {{ t('courseGeneration.outlineReview.sectionCount', '{count} 个目录节点').replace('{count}', String(blueprintNodes.length)) }}
        </span>
      </header>

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
        <div class="outline-review__setup">
          <label class="outline-review__course-name">
            <span>{{ t('courseWorkspace.blueprint.courseName', '课程名称') }}</span>
            <input
              v-model="blueprintDraft.course_name"
              type="text"
              :placeholder="courseName"
              :disabled="adjustmentBusy"
              @input="invalidateProposal"
            />
          </label>

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
              <span>{{ t('courseGeneration.outlineReview.startingPoint', '你的项目起点（暂定）') }}</span>
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
            <footer>{{ t('courseGeneration.outlineReview.startingPointGuard', '起点来自你的自述，只用于安排第一版路径，不等同于已经掌握。') }}</footer>
          </section>

          <section class="outline-review__adjustment" :aria-busy="generatingProposal">
            <div>
              <label for="outline-adjustment-instruction">
                {{ t('courseGeneration.outlineReview.adjustmentTitle', '一句话调整目录') }}
              </label>
              <p>{{ t('courseGeneration.outlineReview.adjustmentHelp', '可以增删、排序、跨章移动、拆章、并章，也可以修改标题和学习目标。系统会先展示整套差异。') }}</p>
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

        <ol class="outline-review__nodes">
          <li
            v-for="(node, index) in blueprintNodes"
            :key="node.node_id || index"
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
      </template>

      <footer class="outline-review__footer">
        <div>
          <strong>{{ footerTitle }}</strong>
          <p>{{ t('courseGeneration.outlineReview.guard', '这是唯一需要编辑课程结构的步骤；下一步还会确认全课教案，再开始生成正文。') }}</p>
          <p v-if="actionError" class="outline-review__action-error">{{ actionError }}</p>
        </div>
        <div class="outline-review__actions">
          <button
            type="button"
            class="secondary"
            :disabled="loading || acting || !!adjustmentProposal || !dirty || !blueprintNodes.length"
            @click="saveDraft"
          >
            <LoaderCircle v-if="saving" :size="15" />
            <Save v-else :size="15" />
            {{ saving
              ? t('courseGeneration.outlineReview.saving', '保存中')
              : dirty
                ? t('courseGeneration.outlineReview.save', '保存修改')
                : t('courseGeneration.outlineReview.saved', '修改已保存') }}
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
import { ArrowRight, CircleCheckBig, LoaderCircle, Save, Sparkles, TriangleAlert } from 'lucide-vue-next'
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
const isProjectCourse = computed(() => (
  String(blueprintDraft.value?.course_type || props.task?.courseType || '') === 'project'
))
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
const footerTitle = computed(() => {
  if (confirming.value) return t('courseGeneration.outlineReview.confirming', '正在确认目录')
  if (saving.value) return t('courseGeneration.outlineReview.savingChanges', '正在保存修改')
  if (dirty.value) return t('courseGeneration.outlineReview.unsaved', '有未保存的修改')
  const progress = Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0))))
  return t('courseGeneration.outlineReview.ready', '目录已就绪 · 当前生产进度 {progress}%')
    .replace('{progress}', String(progress))
})

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
  min-height:0;
  flex:1;
  display:flex;
  overflow:hidden;
  padding:18px clamp(18px,3vw,40px) 26px;
  background:radial-gradient(circle at 88% 2%,rgba(99,102,241,.065),transparent 28%),linear-gradient(180deg,#f8f9fc 0%,#f4f6f9 100%);
}
.outline-review__sheet {
  position:relative;
  width:min(1100px,100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:auto auto minmax(0,1fr) auto;
  margin:0 auto;
  overflow:hidden;
  border:1px solid rgba(208,213,223,.88);
  border-radius:16px;
  background:rgba(255,255,255,.98);
  box-shadow:0 18px 48px rgba(30,41,59,.075),0 2px 7px rgba(30,41,59,.035);
}
.outline-review__sheet::before {
  content:"";
  position:absolute;
  z-index:3;
  top:0;
  right:0;
  left:0;
  height:3px;
  background:linear-gradient(90deg,#5963d8,#7a63e4 58%,#9956d9);
}
.outline-review__header {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:28px;
  padding:26px 30px 22px;
  border-bottom:1px solid #e7e9ee;
}
.outline-review__eyebrow {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#087a5b;
  font-size:12px;
  font-weight:850;
  letter-spacing:.08em;
}
.outline-review__header h1 {
  margin:7px 0 6px;
  color:#182230;
  font:700 clamp(27px,2.6vw,36px)/1.18 Georgia,"Noto Serif SC",serif;
  letter-spacing:-.025em;
}
.outline-review__header p {
  max-width:660px;
  margin:0;
  color:#687386;
  font-size:13px;
  line-height:1.65;
}
.outline-review__count {
  flex:0 0 auto;
  padding:7px 11px;
  border:1px solid #d9e5e0;
  border-radius:999px;
  color:#26715d;
  background:#f2faf7;
  font-size:12px;
  font-weight:750;
}
.outline-review__loading,
.outline-review__load-error {
  grid-row:2/4;
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
.outline-review__setup {
  min-width:0;
  border-bottom:1px solid #eceef2;
}
.outline-review__course-name {
  display:grid;
  grid-template-columns:100px minmax(0,1fr);
  align-items:center;
  gap:14px;
  margin:0 30px;
  padding:14px 0 12px;
}
.outline-review__course-name span {
  color:#7b8494;
  font-size:12px;
  font-weight:750;
}
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
.outline-review__course-name input {
  height:36px;
  padding:0 10px;
  font-size:14px;
  font-weight:780;
}
.outline-review__starting-point {
  margin:0 30px;
  padding:13px 0 15px 114px;
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
  padding:4px 8px;
  border:1px solid #c7dbd2;
  border-radius:5px;
  color:#087a5b;
  background:#f2faf7;
  font-size:10px;
}
.outline-review__starting-point[data-status="insufficient"] > header strong {
  border-color:#e7c790;
  color:#9a5b17;
  background:#fff9ef;
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
  font-size:10px;
  font-weight:750;
}
.outline-review__starting-point p span {
  display:block;
  overflow-wrap:anywhere;
  color:#455166;
  font-size:11px;
  line-height:1.5;
}
.outline-review__starting-point > footer {
  margin-top:9px;
  color:#7b8494;
  font-size:10px;
  line-height:1.5;
}
.outline-retrieval { margin:14px 30px 2px; border:1px solid #c7d2fe; border-radius:12px; padding:13px; background:linear-gradient(135deg,#eef2ff,#fafaff); }
.outline-retrieval > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-retrieval > header div { display:grid; gap:2px; }
.outline-retrieval > header strong { color:#312e81; font-size:13px; }
.outline-retrieval > header small,.outline-retrieval > header > span { color:#6366f1; font-size:9px; }
.outline-retrieval > header > span { border-radius:999px; padding:3px 7px; background:#e0e7ff; white-space:nowrap; }
.outline-retrieval > p { margin:9px 0; color:#475569; font-size:11px; line-height:1.55; }
.outline-retrieval__shape { display:flex; align-items:center; gap:6px; color:#4338ca; font-size:10px; }
.outline-retrieval__diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; margin-top:10px; }
.outline-retrieval__diff section { border-radius:8px; padding:8px; background:rgba(255,255,255,.75); }
.outline-retrieval__diff h3 { margin:0 0 4px; color:#475569; font-size:9px; }
.outline-retrieval__diff ul { margin:0; padding-left:15px; }
.outline-retrieval__diff li { color:#334155; font-size:10px; }
.outline-retrieval__diff li small { display:block; color:#64748b; font-size:9px; }
.outline-retrieval__sources { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.outline-retrieval__source { max-width:240px; display:grid; gap:1px; border:1px solid #e0e7ff; border-radius:8px; padding:6px 8px; color:#3730a3; background:#fff; text-decoration:none; }
.outline-retrieval__source:hover { border-color:#a5b4fc; }
.outline-retrieval__source strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.outline-retrieval__source small { color:#64748b; font-size:8px; }
.outline-retrieval--notice { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; border-color:#fed7aa; background:#fff7ed; }
.outline-retrieval--notice strong { color:#9a3412; font-size:12px; }
.outline-retrieval--notice p { margin:2px 0 0; color:#9a3412; font-size:10px; }
.outline-retrieval--notice button { border:1px solid #fdba74; border-radius:8px; padding:6px 9px; color:#9a3412; background:#fff; font-size:10px; cursor:pointer; }
.outline-retrieval--notice > small { grid-column:1/-1; color:#7c2d12; font-size:9px; }
.outline-review__adjustment {
  display:grid;
  grid-template-columns:minmax(180px,.8fr) minmax(280px,1.7fr) auto;
  align-items:center;
  gap:14px;
  margin:0 30px;
  padding:13px 0;
  border-top:1px solid #eceef2;
}
.outline-review__adjustment label {
  color:#344054;
  font-size:12px;
  font-weight:850;
}
.outline-review__adjustment p {
  margin:3px 0 0;
  color:#7b8494;
  font-size:10px;
  line-height:1.45;
}
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
  margin:0 30px;
  padding:7px 0 10px 114px;
  color:#087a5b;
  font-size:11px;
  font-weight:750;
}
.outline-review__proposal {
  margin:0 30px 13px 144px;
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
  font-size:10px;
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
  padding:8px 9px;
  border:1px solid #e5e7ef;
  border-radius:7px;
  background:#fff;
}
.outline-review__diff-groups h3 { margin:0 0 5px; color:#596579; font-size:10px; }
.outline-review__diff-groups ul,
.outline-review__blockers { margin:0; padding-left:16px; }
.outline-review__diff-groups li { margin:3px 0; color:#344054; font-size:10px; }
.outline-review__diff-groups li span,
.outline-review__diff-groups li small { display:block; overflow-wrap:anywhere; }
.outline-review__diff-groups li small { margin-top:1px; color:#7b8494; font-size:9px; }
.outline-review__blockers {
  margin-top:9px;
  color:#b42318;
  font-size:10px;
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
  overflow:auto;
  margin:0;
  padding:6px 30px 18px;
  list-style:none;
}
.outline-review__nodes li {
  position:relative;
  display:grid;
  grid-template-columns:34px 14px minmax(0,1fr);
  gap:9px;
  padding:10px 0;
  border-bottom:1px solid #eef0f3;
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
  font-size:9px;
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
  font-size:10px;
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
  grid-row:3;
  margin:0;
  padding:42px 30px;
  color:#8a93a3;
  text-align:center;
  font-size:13px;
}
.outline-review__footer {
  grid-row:4;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
  padding:13px 18px 14px 30px;
  border-top:1px solid #dfe3e9;
  background:#fafbfc;
}
.outline-review__footer > div:first-child { min-width:0; }
.outline-review__footer strong { color:#344054; font-size:13px; }
.outline-review__footer p { margin:3px 0 0; color:#7b8494; font-size:11px; line-height:1.5; }
.outline-review__footer p.outline-review__action-error { color:#b42318; }
.outline-review__actions {
  flex:0 0 auto;
  display:flex;
  gap:8px;
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
  .outline-review { padding:8px 6px 14px; }
  .outline-review__sheet { border-radius:13px; }
  .outline-review__header { display:grid; gap:9px; padding:19px 16px 15px; }
  .outline-review__header h1 { font-size:27px; }
  .outline-review__count { justify-self:start; }
  .outline-review__setup { min-height:0; }
  .outline-review__course-name { grid-template-columns:1fr; gap:3px; margin:0 16px; padding:10px 0 8px; }
  .outline-review__starting-point { margin:0 16px; padding:11px 0 13px; }
  .outline-review__starting-point > div { grid-template-columns:1fr; gap:8px; }
  .outline-review__adjustment {
    grid-template-columns:1fr;
    gap:8px;
    margin:0 16px;
    padding:11px 0;
  }
  .outline-review__adjustment button { width:100%; }
  .outline-review__proposal-notice { margin:0 16px; padding:6px 0 10px; }
  .outline-review__proposal { width:auto; margin:0 16px 11px; }
  .outline-review__proposal summary { align-items:flex-start; flex-direction:column; gap:4px; }
  .outline-review__diff-groups { grid-template-columns:1fr; }
  .outline-review__proposal-actions { display:grid; grid-template-columns:1fr 1.25fr; }
  .outline-review__proposal-actions button { width:100%; }
  .outline-review__nodes { padding:4px 16px 12px; }
  .outline-review__nodes li { grid-template-columns:26px 12px minmax(0,1fr); gap:6px; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:9px; padding:11px 12px 13px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg { animation:none!important; }
}
</style>
