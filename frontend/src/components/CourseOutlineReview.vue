<template>
  <section
    class="outline-review"
    :class="{ 'is-editing': editable }"
    :data-mode="editable ? 'edit' : 'view'"
    :data-variant="variant"
    :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程大纲')"
  >
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
          <div v-if="inlineSetupVisible" class="outline-review__setup">
          <section
            v-if="!isInline && coverageVerdict"
            class="outline-coverage"
            :data-status="coverageVerdict.status"
            data-testid="outline-coverage-verdict"
          >
            <header>
              <strong>{{ coverageHeadline }}</strong>
              <small v-if="coverageVerdict.class_hours">
                {{ t('courseGeneration.outlineReview.coverageHours', '{hours} 课时').replace('{hours}', String(coverageVerdict.class_hours)) }}
              </small>
            </header>
            <p v-if="coverageVerdict.coverage_promise">{{ coverageVerdict.coverage_promise }}</p>
            <div
              v-if="coverageUncovered.length"
              class="outline-coverage__uncovered"
              data-testid="outline-coverage-uncovered"
            >
              <span>{{ t('courseGeneration.outlineReview.coverageUncovered', '本次不覆盖') }}</span>
              <ul>
                <li v-for="topic in coverageUncovered" :key="topic">{{ topic }}</li>
              </ul>
            </div>
            <ul v-if="coverageAdvisories.length" class="outline-coverage__advisories">
              <li v-for="item in coverageAdvisories" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section
            v-if="!isInline && retrievalProposal"
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
            v-else-if="!isInline && (retrievalNotice || retrievalErrorKey)"
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

          <section v-if="!isInline && isProjectCourse" class="outline-review__starting-point" :data-status="startingProfileStatus">
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
          <section v-else-if="!isInline && courseType === 'inquiry'" class="outline-review__starting-point" data-status="tentative">
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

          <section v-else-if="!isInline && courseType === 'exam'" class="outline-review__starting-point" data-status="tentative">
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

          <section v-if="!isInline || (editable && inlineToolsOpen)" class="outline-review__adjustment" :aria-busy="generatingProposal">
            <div class="outline-review__adjustment-heading">
              <label for="outline-adjustment-instruction">
                {{ t('courseGeneration.outlineReview.adjustmentTitle', '目录调整') }}
              </label>
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

          <div class="outline-review__chapters" data-testid="outline-chapter-list">
            <div v-if="!isInline || editable" class="outline-review__list-toolbar">
              <strong v-if="!isInline">{{ t('courseGeneration.outlineReview.manualEditTitle', '课程结构') }}</strong>
              <div class="outline-review__toolbar-actions">
                <button
                  v-if="isInline"
                  type="button"
                  :aria-expanded="inlineToolsOpen"
                  :disabled="adjustmentBusy"
                  @click="inlineToolsOpen = !inlineToolsOpen"
                >
                  <Sparkles :size="14" />{{ t('courseWorkbench.aiAdjustOutline', 'AI 调整') }}
                </button>
                <button type="button" :disabled="adjustmentBusy" @click="addChapter">
                  <Plus :size="14" />{{ t('courseGeneration.outlineReview.addChapter', '新增章') }}
                </button>
              </div>
            </div>
            <section
              v-for="(group, groupIndex) in outlineGroups"
              :key="group.key"
              class="outline-review__chapter"
              :class="{ 'outline-review__chapter--ungrouped': !group.chapter }"
            >
              <header v-if="group.chapter" class="outline-review__chapter-heading">
                <span v-if="isInline" class="outline-review__chapter-index">{{ String(groupIndex + 1).padStart(2, '0') }}</span>
                <div v-if="!isInline && group.chapter.node.learning_path_role" class="outline-review__node-meta">
                  <span :data-role="normalizedPathRole(group.chapter.node.learning_path_role)">
                    {{ pathRoleLabel(group.chapter.node.learning_path_role) }}
                  </span>
                  <p v-if="group.chapter.node.path_reason">{{ group.chapter.node.path_reason }}</p>
                </div>
                <div class="outline-review__node-fields">
                  <input
                    v-model="group.chapter.node.node_name"
                    type="text"
                    :disabled="adjustmentBusy"
                    :readonly="isInline && !editable"
                    :tabindex="isInline && !editable ? -1 : undefined"
                    :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
                    @input="invalidateProposal"
                  />
                  <textarea
                    v-if="'learning_objective' in group.chapter.node"
                    v-model="group.chapter.node.learning_objective"
                    rows="1"
                    :disabled="adjustmentBusy"
                    :readonly="isInline && !editable"
                    :tabindex="isInline && !editable ? -1 : undefined"
                    :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）')"
                    :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                    @input="invalidateProposal"
                  />
                </div>
                <div v-if="!isInline || editable" class="outline-review__node-actions">
                  <button type="button" :title="t('courseGeneration.outlineReview.addSection', '新增小节')" :disabled="adjustmentBusy" @click="addSection(group.chapter.node)"><Plus :size="14" /></button>
                  <button type="button" :title="t('courseGeneration.outlineReview.moveUp', '上移')" :disabled="adjustmentBusy || !canMoveNode(group.chapter.node, -1)" @click="moveOutlineNode(group.chapter.node, -1)"><ArrowUp :size="14" /></button>
                  <button type="button" :title="t('courseGeneration.outlineReview.moveDown', '下移')" :disabled="adjustmentBusy || !canMoveNode(group.chapter.node, 1)" @click="moveOutlineNode(group.chapter.node, 1)"><ArrowDown :size="14" /></button>
                  <button type="button" class="danger" :title="t('courseGeneration.outlineReview.removeChapter', '删除本章')" :disabled="adjustmentBusy" @click="removeOutlineNode(group.chapter.node)"><Trash2 :size="14" /></button>
                </div>
              </header>

              <div v-if="group.sections.length" class="outline-review__section-list">
                <article
                  v-for="(item, sectionIndex) in group.sections"
                  :key="item.node.node_id || item.index"
                  class="outline-review__section"
                >
                  <span v-if="isInline" class="outline-review__section-index">{{ groupIndex + 1 }}.{{ sectionIndex + 1 }}</span>
                  <div v-if="!isInline && item.node.learning_path_role" class="outline-review__node-meta">
                    <span :data-role="normalizedPathRole(item.node.learning_path_role)">
                      {{ pathRoleLabel(item.node.learning_path_role) }}
                    </span>
                    <p v-if="item.node.path_reason">{{ item.node.path_reason }}</p>
                  </div>
                  <div class="outline-review__node-fields">
                    <input
                      v-model="item.node.node_name"
                      type="text"
                      :disabled="adjustmentBusy"
                      :readonly="isInline && !editable"
                      :tabindex="isInline && !editable ? -1 : undefined"
                      :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
                      @input="invalidateProposal"
                    />
                    <textarea
                      v-model="item.node.learning_objective"
                      rows="1"
                      :disabled="adjustmentBusy"
                      :readonly="isInline && !editable"
                      :tabindex="isInline && !editable ? -1 : undefined"
                      :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）')"
                      :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                      @input="invalidateProposal"
                    />
                  </div>
                  <div v-if="!isInline || editable" class="outline-review__node-actions">
                    <button type="button" :title="t('courseGeneration.outlineReview.moveUp', '上移')" :disabled="adjustmentBusy || !canMoveNode(item.node, -1)" @click="moveOutlineNode(item.node, -1)"><ArrowUp :size="14" /></button>
                    <button type="button" :title="t('courseGeneration.outlineReview.moveDown', '下移')" :disabled="adjustmentBusy || !canMoveNode(item.node, 1)" @click="moveOutlineNode(item.node, 1)"><ArrowDown :size="14" /></button>
                    <button type="button" class="danger" :title="t('courseGeneration.outlineReview.removeSection', '删除小节')" :disabled="adjustmentBusy" @click="removeOutlineNode(item.node)"><Trash2 :size="14" /></button>
                  </div>
                </article>
              </div>
            </section>
          </div>

          <p v-if="!blueprintNodes.length" class="outline-review__empty">
            {{ t('courseGeneration.outlineReview.empty', '目录尚未形成，请重新载入后再确认。') }}
          </p>
        </div>
      </template>

      <footer v-if="!isInline || requiresConfirmation || (editable && dirty) || (isInline && surface === 'teacher' && !editable) || actionError" class="outline-review__footer">
        <p v-if="actionError" class="outline-review__action-error" role="alert">{{ actionError }}</p>
        <div class="outline-review__actions">
          <span
            v-if="editable && !dirty && !saving && !loading && blueprintNodes.length"
            class="outline-review__saved-state"
            role="status"
          >
            <CircleCheck :size="15" />
            {{ t('courseGeneration.outlineReview.savedState', '已保存') }}
          </span>
          <button
            v-else-if="editable"
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
            v-if="!isInline || requiresConfirmation"
            type="button"
            class="primary"
            :disabled="loading || acting || !!adjustmentProposal || !blueprintNodes.length"
            @click="confirmOutline"
          >
            <LoaderCircle v-if="confirming" :size="15" />
            <ArrowRight v-else :size="15" />
            {{ surface === 'teacher'
              ? t('courseWorkbench.confirmOutlineAndContinue', '确认大纲，进入教案')
              : t('courseGeneration.gate.confirmOutline', '确认目录并继续') }}
          </button>
          <button
            v-else-if="surface === 'teacher' && !editable"
            type="button"
            class="primary"
            @click="emit('next')"
          >
            <ArrowRight :size="15" />
            {{ t('courseWorkbench.nextToLesson', '进入教案') }}
          </button>
        </div>
      </footer>
    </article>
    <span class="outline-review__sr-only" aria-live="polite">{{ liveStatus }}</span>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, ArrowUp, CircleCheck, LoaderCircle, Plus, Save, Sparkles, Trash2, TriangleAlert } from 'lucide-vue-next'
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
  surface?: 'student' | 'teacher'
  editable?: boolean
  variant?: 'full' | 'inline'
  requiresConfirmation?: boolean
}>(), {
  courseName: '',
  nodes: () => [],
  task: undefined,
  surface: 'student',
  editable: true,
  variant: 'full',
  requiresConfirmation: true,
})

const emit = defineEmits<{
  (event: 'confirmed'): void
  (event: 'next'): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const blueprintDraft = ref<Record<string, any>>({})
const retrievalArtifact = ref<Record<string, any>>({})
// D-1：课程规格与覆盖度判定。只在后端真的给出判定时展示——没有判定时保持沉默，
// 而不是显示"完整"，因为"沉默被当成完整"正是这个问题的由来。
const coverageArtifact = ref<Record<string, any>>({})
const coverageVerdict = computed(() => (
  coverageArtifact.value?.available ? coverageArtifact.value : null
))
const coverageUncovered = computed<string[]>(() => (
  Array.isArray(coverageVerdict.value?.uncovered_topics)
    ? coverageVerdict.value.uncovered_topics.map((item: any) => String(item))
    : []
))
const coverageAdvisories = computed<string[]>(() => (
  Array.isArray(coverageVerdict.value?.advisories)
    ? coverageVerdict.value.advisories.map((item: any) => String(item))
    : []
))
const coverageHeadline = computed(() => {
  const verdict = coverageVerdict.value
  if (!verdict) return ''
  const label = String(verdict.scale_label || '')
  if (verdict.may_claim_complete_subject) {
    return t(
      'courseGeneration.outlineReview.coverageComplete',
      '本次为{label}，可按完整课程组织',
    ).replace('{label}', label)
  }
  return t(
    'courseGeneration.outlineReview.coveragePartial',
    '本次为{label}，不承担学科完整覆盖',
  ).replace('{label}', label)
})
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
const inlineToolsOpen = ref(false)

const isInline = computed(() => props.variant === 'inline')
const inlineSetupVisible = computed(() => !isInline.value || (
  props.editable
  && (inlineToolsOpen.value || Boolean(adjustmentProposal.value))
))
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
const outlineGroups = computed(() => {
  const chapters = blueprintNodes.value
    .map((node, index) => ({ node, index }))
    .filter(item => Number(item.node.node_level || 2) === 1)
    .map(item => ({
      key: String(item.node.node_id || `chapter-${item.index}`),
      chapter: item,
      sections: [] as Array<{ node: any; index: number }>,
    }))
  const chapterById = new Map(chapters.map(group => [String(group.chapter.node.node_id || ''), group]))
  const ungrouped = {
    key: 'ungrouped-sections',
    chapter: null as null,
    sections: [] as Array<{ node: any; index: number }>,
  }

  blueprintNodes.value.forEach((node, index) => {
    if (Number(node.node_level || 2) === 1) return
    const parent = chapterById.get(String(node.parent_node_id || ''))
    ;(parent || ungrouped).sections.push({ node, index })
  })

  return ungrouped.sections.length ? [...chapters, ungrouped] : chapters
})
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
    parent_node_id: node.parent_node_id,
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
watch(() => props.editable, editable => {
  if (!editable) inlineToolsOpen.value = false
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
    coverageArtifact.value = clone(data.coverage || {})
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

function outlineNodeId(prefix: string) {
  const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${suffix}`
}

function markManualChange(message: string) {
  invalidateProposal()
  proposalNotice.value = message
  liveStatus.value = message
}

function addChapter() {
  const chapterCount = blueprintNodes.value.filter(node => Number(node.node_level || 2) === 1).length
  blueprintNodes.value.push({
    node_id: outlineNodeId('chapter'),
    parent_node_id: 'root',
    node_name: t('courseGeneration.outlineReview.newChapterName', '新章节 {number}').replace('{number}', String(chapterCount + 1)),
    node_level: 1,
    learning_objective: '',
    prerequisite_node_ids: [],
  })
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
}

function addSection(chapter: any) {
  const parentId = String(chapter?.node_id || '')
  if (!parentId) return
  const siblings = blueprintNodes.value.filter(node => String(node.parent_node_id || '') === parentId)
  const chapterIndex = blueprintNodes.value.indexOf(chapter)
  let insertAt = chapterIndex + 1
  while (insertAt < blueprintNodes.value.length && Number(blueprintNodes.value[insertAt]?.node_level || 2) !== 1) insertAt += 1
  blueprintNodes.value.splice(insertAt, 0, {
    node_id: outlineNodeId('section'),
    parent_node_id: parentId,
    node_name: t('courseGeneration.outlineReview.newSectionName', '新小节 {number}').replace('{number}', String(siblings.length + 1)),
    node_level: 2,
    learning_objective: '',
    prerequisite_node_ids: [],
  })
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
}

function siblingNodes(node: any) {
  const level = Number(node?.node_level || 2)
  return blueprintNodes.value.filter(candidate => level === 1
    ? Number(candidate.node_level || 2) === 1
    : Number(candidate.node_level || 2) !== 1 && String(candidate.parent_node_id || '') === String(node.parent_node_id || ''))
}

function canMoveNode(node: any, direction: -1 | 1) {
  const siblings = siblingNodes(node)
  const index = siblings.indexOf(node)
  return direction < 0 ? index > 0 : index >= 0 && index < siblings.length - 1
}

function moveOutlineNode(node: any, direction: -1 | 1) {
  if (!canMoveNode(node, direction)) return
  if (Number(node.node_level || 2) !== 1) {
    const siblings = siblingNodes(node)
    const target = siblings[siblings.indexOf(node) + direction]
    const sourceIndex = blueprintNodes.value.indexOf(node)
    const targetIndex = blueprintNodes.value.indexOf(target)
    blueprintNodes.value.splice(sourceIndex, 1)
    blueprintNodes.value.splice(targetIndex, 0, node)
  } else {
    const chapters = siblingNodes(node)
    const target = chapters[chapters.indexOf(node) + direction]
    const blockFor = (chapter: any) => blueprintNodes.value.filter(candidate => candidate === chapter || String(candidate.parent_node_id || '') === String(chapter.node_id || ''))
    const blocks = chapters.map(blockFor)
    const sourceBlockIndex = chapters.indexOf(node)
    const targetBlockIndex = chapters.indexOf(target)
    const sourceBlock = blocks[sourceBlockIndex]!
    const targetBlock = blocks[targetBlockIndex]!
    blocks[sourceBlockIndex] = targetBlock
    blocks[targetBlockIndex] = sourceBlock
    const chapterIds = new Set(chapters.flatMap(chapter => blockFor(chapter).map(item => item.node_id)))
    const untouched = blueprintNodes.value.filter(candidate => !chapterIds.has(candidate.node_id))
    blueprintNodes.value.splice(0, blueprintNodes.value.length, ...blocks.flat(), ...untouched)
  }
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
}

function removeOutlineNode(node: any) {
  const removedIds = new Set<string>([String(node.node_id || '')])
  if (Number(node.node_level || 2) === 1) {
    blueprintNodes.value.forEach(candidate => {
      if (String(candidate.parent_node_id || '') === String(node.node_id || '')) removedIds.add(String(candidate.node_id || ''))
    })
  }
  const kept = blueprintNodes.value.filter(candidate => !removedIds.has(String(candidate.node_id || '')))
  kept.forEach(candidate => {
    if (Array.isArray(candidate.prerequisite_node_ids)) {
      candidate.prerequisite_node_ids = candidate.prerequisite_node_ids.filter((id: string) => !removedIds.has(String(id)))
    }
  })
  blueprintNodes.value.splice(0, blueprintNodes.value.length, ...kept)
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
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

async function finishEditing() {
  if (acting.value) return false
  if (!dirty.value) return true
  saving.value = true
  actionError.value = ''
  try {
    await persistDraft()
    return true
  } catch {
    actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
    return false
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
    if (props.surface === 'teacher') {
      await courseStore.refreshGenerationPreview(props.courseId, 'teacher')
      ElMessage.success(t('courseWorkbench.outlineConfirmed', '大纲已确认，正在进入教案'))
    } else {
      await courseStore.refreshCourseData(props.courseId)
      ElMessage.success(t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
    }
    emit('confirmed')
  } catch {
    actionError.value = t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。')
  } finally {
    confirming.value = false
  }
}

defineExpose({ finishEditing })
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
  font-size:12px;
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
  font-size:12px;
  font-weight:750;
}
.outline-review__starting-point p span {
  display:block;
  overflow-wrap:anywhere;
  color:#455166;
  font-size:12px;
  line-height:1.5;
}
.outline-review__starting-point > footer {
  margin-top:9px;
  color:#7b8494;
  font-size:10px;
  line-height:1.5;
}
.outline-coverage { margin:14px 30px 2px; border:1px solid #fed7aa; border-radius:12px; padding:13px; background:linear-gradient(135deg,#fff7ed,#fffbf5); }
.outline-coverage[data-status="complete"] { border-color:#bbf7d0; background:linear-gradient(135deg,#f0fdf4,#fafffb); }
.outline-coverage > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-coverage > header strong { color:#9a3412; font-size:13px; }
.outline-coverage[data-status="complete"] > header strong { color:#166534; }
.outline-coverage > header small { border-radius:999px; padding:3px 7px; color:#9a3412; background:#ffedd5; font-size:9px; white-space:nowrap; }
.outline-coverage[data-status="complete"] > header small { color:#166534; background:#dcfce7; }
.outline-coverage > p { margin:9px 0 0; color:#475569; font-size:11px; line-height:1.55; }
.outline-coverage__uncovered { margin-top:10px; border-radius:8px; padding:8px; background:rgba(255,255,255,.75); }
.outline-coverage__uncovered > span { color:#9a3412; font-size:9px; }
.outline-coverage__uncovered ul { display:flex; flex-wrap:wrap; gap:4px 6px; margin:5px 0 0; padding:0; list-style:none; }
.outline-coverage__uncovered li { border:1px solid #fed7aa; border-radius:999px; padding:2px 7px; color:#7c2d12; background:#fff; font-size:10px; }
.outline-coverage__advisories { margin:9px 0 0; padding-left:15px; }
.outline-coverage__advisories li { color:#7c2d12; font-size:10px; line-height:1.5; }
.outline-retrieval { margin:0; padding:18px 0 20px 114px; border-top:1px solid #eceef2; }
.outline-retrieval > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-retrieval > header div { display:grid; gap:2px; }
.outline-retrieval > header strong { color:#312e81; font-size:14px; }
.outline-retrieval > header small,.outline-retrieval > header > span { color:#6366f1; font-size:12px; }
.outline-retrieval > header > span { padding:2px 0; white-space:nowrap; }
.outline-retrieval > p { max-width:880px; margin:10px 0; color:#475569; font-size:13px; line-height:1.65; }
.outline-retrieval__shape { display:flex; align-items:center; gap:7px; color:#4338ca; font-size:12px; }
.outline-retrieval__diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; border-bottom:1px solid #e4e7f5; }
.outline-retrieval__diff section { min-width:0; padding:12px 18px 13px 0; }
.outline-retrieval__diff section + section { padding-left:18px; border-left:1px solid #e4e7f5; }
.outline-retrieval__diff h3 { margin:0 0 7px; color:#475569; font-size:12px; }
.outline-retrieval__diff ul { margin:0; padding-left:17px; }
.outline-retrieval__diff li { margin:4px 0; color:#334155; font-size:12px; line-height:1.5; }
.outline-retrieval__diff li small { display:block; color:#64748b; font-size:12px; }
.outline-retrieval__sources { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; }
.outline-retrieval__source { min-width:0; display:grid; gap:3px; padding:11px 14px 0 0; color:#3730a3; text-decoration:none; }
.outline-retrieval__source + .outline-retrieval__source { padding-left:14px; border-left:1px solid #e4e7f5; }
.outline-retrieval__source:hover strong { text-decoration:underline; }
.outline-retrieval__source strong { overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.outline-retrieval__source small { color:#64748b; font-size:12px; }
.outline-retrieval--notice { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; }
.outline-retrieval--notice strong { color:#9a3412; font-size:13px; }
.outline-retrieval--notice p { margin:2px 0 0; color:#9a3412; font-size:12px; }
.outline-retrieval--notice .outline-retrieval__stats { color:#7c2d12; font-size:12px; }
.outline-retrieval--notice button { border:1px solid #fdba74; border-radius:8px; padding:6px 9px; color:#9a3412; background:#fff; font-size:12px; cursor:pointer; }
.outline-retrieval--notice > small { grid-column:1/-1; color:#7c2d12; font-size:12px; }
.outline-review__adjustment {
  display:grid;
  grid-template-columns:140px minmax(280px,1fr) auto;
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
.outline-review__adjustment-heading { display:flex; align-items:center; }
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
  font-size:12px;
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
  font-size:12px;
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
  font-size:12px;
  font-weight:850;
  cursor:pointer;
}
.outline-review__proposal summary strong {
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#60687b;
  font-size:12px;
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
.outline-review__diff-groups h3 { margin:0 0 5px; color:#596579; font-size:12px; }
.outline-review__diff-groups ul,
.outline-review__blockers { margin:0; padding-left:16px; }
.outline-review__diff-groups li { margin:3px 0; color:#344054; font-size:12px; }
.outline-review__diff-groups li span,
.outline-review__diff-groups li small { display:block; overflow-wrap:anywhere; }
.outline-review__diff-groups li small { margin-top:1px; color:#7b8494; font-size:12px; }
.outline-review__blockers {
  margin-top:9px;
  color:#b42318;
  font-size:12px;
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
.outline-review__chapters {
  display:grid;
  gap:0;
  min-height:0;
  overflow:visible;
  margin:0;
  padding:24px 0 28px;
}
.outline-review__list-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:50px; border-bottom:1px solid #dfe3e9; }.outline-review__list-toolbar strong { color:#273144; font-size:15px; }.outline-review__list-toolbar button { min-height:34px; display:inline-flex; align-items:center; gap:5px; padding:0 10px; border:1px solid #d9dee7; border-radius:7px; color:#454ca8; background:#fff; font-size:12px; font-weight:700; cursor:pointer; }
.outline-review__chapter {
  min-width:0;
  border-bottom:1px solid #e4e7ec;
}
.outline-review__chapter-heading {
  min-width:0;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:start;
  gap:6px 10px;
  padding:18px 8px 16px;
  background:#fff;
}
.outline-review__chapter-heading input {
  height:40px;
  padding:0 8px;
  color:#172033;
  font-size:18px;
  font-weight:800;
}
.outline-review__chapter-heading textarea {
  min-height:36px;
  margin-top:2px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:12px;
  line-height:1.5;
}
.outline-review__section-list {
  margin-left:32px;
}
.outline-review__section {
  min-width:0;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:start;
  gap:6px 10px;
  padding:14px 8px 14px 14px;
  border-bottom:1px solid #edf0f4;
}
.outline-review__section:last-child { border-bottom:0; }
.outline-review__chapter--ungrouped .outline-review__section-list { margin-left:0; }
.outline-review__chapter--ungrouped .outline-review__section { padding-left:8px; }
.outline-review__section input {
  height:34px;
  padding:0 8px;
  color:#273144;
  font-size:15px;
  font-weight:750;
}
.outline-review__section textarea {
  min-height:36px;
  margin-top:2px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:12px;
  line-height:1.5;
}
.outline-review__node-fields { min-width:0; display:grid; gap:2px; }.outline-review__node-actions { display:flex; align-items:center; gap:3px; padding-top:4px; }.outline-review__node-actions button { width:28px; height:28px; display:grid; place-items:center; padding:0; border:1px solid transparent; border-radius:7px; color:#687386; background:transparent; cursor:pointer; }.outline-review__node-actions button:hover:not(:disabled),.outline-review__node-actions button:focus-visible { border-color:#d9dee7; color:#454ca8; background:#fff; outline:0; }.outline-review__node-actions button.danger:hover:not(:disabled) { color:#b42318; background:#fff5f5; }.outline-review__node-actions button:disabled { opacity:.3; cursor:not-allowed; }.outline-review__node-meta { grid-column:1/-1; }
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
  font-size:12px;
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
  font-size:12px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
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
.outline-review__footer p.outline-review__action-error { min-width:0; margin:0 auto 0 0; color:#b42318; font-size:12px; line-height:1.5; }
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
  font-size:12px;
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
}
.outline-review__actions button:not(:disabled):hover { filter:brightness(.98); }
.outline-review__actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
.outline-review__toolbar-actions { display:flex; align-items:center; gap:7px; margin-left:auto; }

.outline-review[data-variant="inline"] {
  height:auto;
  display:block;
  overflow:visible;
  padding:0;
  background:transparent;
}
.outline-review[data-variant="inline"] .outline-review__sheet {
  width:100%;
  height:auto;
  display:block;
  overflow:visible;
  background:transparent;
}
.outline-review[data-variant="inline"] .outline-review__body { overflow:visible; }
.outline-review[data-variant="inline"] .outline-review__loading,
.outline-review[data-variant="inline"] .outline-review__load-error { min-height:180px; }
.outline-review[data-variant="inline"] .outline-review__setup {
  padding:0 20px;
  border-bottom:1px solid #e7ebf2;
}
.outline-review[data-variant="inline"] .outline-review__adjustment {
  grid-template-columns:minmax(0,1fr) auto;
  gap:10px;
  padding:14px 0;
  border:0;
}
.outline-review[data-variant="inline"] .outline-review__adjustment-heading {
  position:absolute;
  width:1px;
  height:1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
}
.outline-review[data-variant="inline"] .outline-review__adjustment textarea { min-height:42px; resize:none; }
.outline-review[data-variant="inline"] .outline-review__proposal-notice { padding:0 0 12px; }
.outline-review[data-variant="inline"] .outline-review__proposal { margin:0 0 14px; }
.outline-review[data-variant="inline"] .outline-review__chapters {
  gap:12px;
  padding:18px 20px 22px;
}
.outline-review[data-variant="inline"] .outline-review__list-toolbar {
  min-height:34px;
  justify-content:flex-end;
  margin-bottom:-2px;
  border:0;
}
.outline-review[data-variant="inline"] .outline-review__chapter {
  overflow:hidden;
  border:1px solid #e1e7f0;
  border-radius:11px;
  background:#fff;
}
.outline-review[data-variant="inline"] .outline-review__chapter-heading {
  grid-template-columns:30px minmax(0,1fr) auto;
  align-items:center;
  gap:11px;
  min-height:62px;
  padding:11px 14px;
}
.outline-review[data-variant="inline"] .outline-review__chapter-index {
  width:28px;
  height:28px;
  display:grid;
  place-items:center;
  border-radius:50%;
  color:#047857;
  background:#ecfdf5;
  font-size:10px;
  font-weight:800;
}
.outline-review[data-variant="inline"] .outline-review__chapter-heading input {
  height:28px;
  padding:0;
  color:#263147;
  font-size:13px;
  font-weight:800;
}
.outline-review[data-variant="inline"] .outline-review__chapter-heading textarea {
  min-height:24px;
  margin:0;
  padding:2px 0;
  resize:none;
  color:#64748b;
  font-size:11px;
  line-height:1.45;
}
.outline-review[data-variant="inline"] .outline-review__section-list { margin:0; padding:0 14px 10px 55px; }
.outline-review[data-variant="inline"] .outline-review__section {
  grid-template-columns:46px minmax(0,1fr) auto;
  align-items:center;
  gap:8px;
  min-height:48px;
  padding:7px 0;
  border-top:1px solid #eef2f6;
  border-bottom:0;
}
.outline-review[data-variant="inline"] .outline-review__section-index {
  color:#6366f1;
  font-size:11px;
  font-weight:750;
}
.outline-review[data-variant="inline"] .outline-review__section input {
  height:26px;
  padding:0;
  color:#334155;
  font-size:12px;
  font-weight:750;
}
.outline-review[data-variant="inline"] .outline-review__section textarea {
  min-height:22px;
  margin:0;
  padding:1px 0;
  resize:none;
  color:#64748b;
  font-size:11px;
  line-height:1.45;
}
.outline-review[data-variant="inline"] input[readonly],
.outline-review[data-variant="inline"] textarea[readonly] {
  pointer-events:none;
  cursor:default;
}
.outline-review[data-variant="inline"].is-editing .outline-review__node-fields input,
.outline-review[data-variant="inline"].is-editing .outline-review__node-fields textarea { padding-inline:7px; }
.outline-review[data-variant="inline"] .outline-review__node-actions { align-self:center; padding:0; }
.outline-review[data-variant="inline"] .outline-review__footer { padding:12px 20px; }
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
  .outline-review__chapters { gap:16px; padding:16px 0 20px; }
  .outline-review__chapter-heading { padding:11px 10px; border-radius:8px; }
  .outline-review__chapter-heading input { font-size:16px; }
  .outline-review__section-list { margin-left:14px; }
  .outline-review__section { padding:11px 2px 11px 10px; }
  .outline-review__chapter-heading,.outline-review__section { grid-template-columns:minmax(0,1fr); }
  .outline-review__node-actions { justify-content:flex-end; padding-top:0; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:9px; padding:11px 0 13px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg { animation:none!important; }
}
</style>
