<template>
  <section class="knowledge-command-panel" :aria-label="t('knowledgeCommands.title', '知识维护')">
    <header class="knowledge-command-head">
      <div>
        <Wrench :size="15" aria-hidden="true" />
        <strong>{{ t('knowledgeCommands.title', '知识维护') }}</strong>
      </div>
      <span class="knowledge-command-scope">
        {{ t('knowledgeCommands.candidateOnly', '需确认后生效') }}
      </span>
    </header>

    <p v-if="!point" class="knowledge-command-empty">
      {{ t('knowledgeCommands.selectPoint', '选择一个知识点后可发起维护') }}
    </p>

    <template v-else>
      <p class="knowledge-command-target">
        {{ t('knowledgeCommands.target', '当前知识点') }}
        <strong>{{ point.name }}</strong>
      </p>

      <label class="knowledge-command-field">
        <span>{{ t('knowledgeCommands.operation', '操作') }}</span>
        <select v-model="operation" :disabled="busy">
          <option v-for="item in operations" :key="item" :value="item">
            {{ operationLabel(item) }}
          </option>
        </select>
      </label>

      <label class="knowledge-command-field">
        <span>{{ valueLabel }}</span>
        <textarea
          v-model="value"
          rows="3"
          :disabled="busy"
          :placeholder="valuePlaceholder"
        ></textarea>
      </label>

      <label class="knowledge-command-field">
        <span>{{ t('knowledgeCommands.reason', '修改理由') }}</span>
        <textarea
          v-model="reason"
          rows="2"
          :disabled="busy"
          :placeholder="t('knowledgeCommands.reasonPlaceholder', '说明为什么要改，审阅时需要')"
        ></textarea>
      </label>

      <p v-if="errorText" class="knowledge-command-error" role="alert">
        <AlertCircle :size="14" aria-hidden="true" />
        <span>{{ errorText }}</span>
      </p>

      <!--
        AI 拆分建议：模型只提建议，产出的仍是待确认候选，走同一套质量门。
        与手工编辑共用下方的候选区，避免两套确认语义。
      -->
      <div class="knowledge-command-actions">
        <button type="button" class="is-propose" :disabled="busy" @click="proposeSplit">
          <LoaderCircle v-if="proposing" :size="14" class="is-spinning" aria-hidden="true" />
          <Scissors v-else :size="14" aria-hidden="true" />
          {{ proposing
            ? t('knowledgeCommands.proposing', 'AI 正在判断')
            : t('knowledgeCommands.proposeSplit', '让 AI 判断是否该拆分') }}
        </button>
      </div>

      <p v-if="splitVerdict" class="knowledge-command-note">{{ splitVerdict }}</p>

      <ul v-if="splitParts.length" class="knowledge-command-detail-list">
        <li v-for="part in splitParts" :key="part.knowledge_id">
          <span class="knowledge-command-detail-kind is-ok">
            {{ t('knowledgeCommands.newNode', '新知识点') }}
          </span>
          <span class="knowledge-command-detail-title">{{ part.name }}</span>
          <span class="knowledge-command-detail-excerpt">{{ part.statement }}</span>
        </li>
      </ul>

      <div class="knowledge-command-actions">
        <button type="button" class="is-preview" :disabled="!canPreview" @click="preview">
          <LoaderCircle v-if="previewing" :size="14" class="is-spinning" aria-hidden="true" />
          <Eye v-else :size="14" aria-hidden="true" />
          {{ previewing
            ? t('knowledgeCommands.previewing', '正在计算影响')
            : t('knowledgeCommands.preview', '预览影响') }}
        </button>
      </div>

      <!--
        候选区：这是"候选式确认"的界面表达。预览已经算出完整影响面，
        但活动知识库此刻仍未改变，教师看过影响再决定确认或放弃。
      -->
      <div v-if="candidate" class="knowledge-command-candidate">
        <header>
          <FileSearch :size="14" aria-hidden="true" />
          <strong>{{ t('knowledgeCommands.candidateTitle', '待确认候选') }}</strong>
          <span :class="['knowledge-command-badge', candidate.confirmable ? 'is-ok' : 'is-blocked']">
            {{ candidate.confirmable
              ? t('knowledgeCommands.confirmable', '可确认')
              : t('knowledgeCommands.notConfirmable', '不可确认') }}
          </span>
        </header>

        <p class="knowledge-command-note">
          {{ t('knowledgeCommands.notAppliedYet', '当前知识库尚未改变，确认后才会生效。') }}
        </p>

        <ul class="knowledge-command-impact">
          <li>
            <button
              type="button"
              :disabled="!impact.needsRegeneration || busy"
              @click="toggleDetail('needs_regeneration')"
            >
              <span>{{ t('knowledgeCommands.needsRegeneration', '需重建') }}</span>
              <strong>{{ impact.needsRegeneration }}</strong>
            </button>
          </li>
          <li>
            <button
              type="button"
              :disabled="!impact.stale || busy"
              @click="toggleDetail('stale')"
            >
              <span>{{ t('knowledgeCommands.stale', '待复核') }}</span>
              <strong>{{ impact.stale }}</strong>
            </button>
          </li>
          <li>
            <button
              type="button"
              :disabled="!impact.blocked || busy"
              @click="toggleDetail('blocked')"
            >
              <span>{{ t('knowledgeCommands.blocked', '被阻断') }}</span>
              <strong>{{ impact.blocked }}</strong>
            </button>
          </li>
        </ul>

        <p v-if="impact.needsRegeneration || impact.stale" class="knowledge-command-note">
          {{ t('knowledgeCommands.expandHint', '点计数可展开，查看具体是哪些正文块、练习和课件。') }}
        </p>

        <!--
          明细区：教师要能判断"这 52 个值不值得改"，就必须看到是哪些对象。
          只在展开时才请求，避免每次预览都拉一份可能上百行的列表。
        -->
        <div v-if="openGroup" class="knowledge-command-detail">
          <header>
            <strong>{{ groupLabel(openGroup) }}</strong>
            <button type="button" @click="openGroup = ''">
              {{ t('knowledgeCommands.collapse', '收起') }}
            </button>
          </header>
          <p v-if="detailLoading" class="knowledge-command-note">
            {{ t('knowledgeCommands.detailLoading', '正在读取明细') }}
          </p>
          <p v-else-if="detailError" class="knowledge-command-error">{{ detailError }}</p>
          <template v-else>
            <ul class="knowledge-command-detail-list">
              <li v-for="row in detailRows" :key="`${row.type}:${row.id}`">
                <span class="knowledge-command-detail-kind">{{ typeLabel(row) }}</span>
                <span class="knowledge-command-detail-title">{{ row.title }}</span>
                <span v-if="row.location" class="knowledge-command-detail-loc">{{ row.location }}</span>
                <span v-if="row.excerpt" class="knowledge-command-detail-excerpt">{{ row.excerpt }}</span>
                <span v-if="row.missing" class="knowledge-command-detail-missing">
                  {{ t('knowledgeCommands.objectMissing', '该对象已不在当前课程中') }}
                </span>
              </li>
            </ul>
            <p v-if="detailTruncated" class="knowledge-command-note">
              {{ t('knowledgeCommands.detailTruncated', '仅显示前一部分，完整列表请在重建后复核。') }}
            </p>
          </template>
        </div>

        <p v-if="impact.dependents" class="knowledge-command-note">
          {{ t('knowledgeCommands.dependentPoints', '经知识关系受影响的知识点') }}：
          {{ impact.dependents }}
        </p>

        <ul v-if="blockingIssues.length" class="knowledge-command-issues">
          <li v-for="(issue, index) in blockingIssues" :key="index">{{ issue }}</li>
        </ul>

        <div class="knowledge-command-actions">
          <button
            type="button"
            class="is-primary"
            :disabled="!candidate.confirmable || busy"
            @click="confirm"
          >
            <LoaderCircle v-if="confirming" :size="14" class="is-spinning" aria-hidden="true" />
            <CheckCircle2 v-else :size="14" aria-hidden="true" />
            {{ confirming
              ? t('knowledgeCommands.confirming', '正在确认')
              : t('knowledgeCommands.confirm', '确认应用') }}
          </button>
          <button type="button" :disabled="busy" @click="discard">
            {{ t('knowledgeCommands.discard', '放弃候选') }}
          </button>
        </div>
      </div>

      <p v-if="receiptText" class="knowledge-command-receipt" role="status">
        <CheckCircle2 :size="14" aria-hidden="true" />
        <span>{{ receiptText }}</span>
      </p>

      <!--
        重建入口只在知识修订生效后出现：没生效就没有"待重建"的下游产物。
        它调用共享的重建命令接口，不自带重建实现。
      -->
      <div v-if="rebuildAvailable" class="knowledge-command-rebuild">
        <button type="button" :disabled="rebuilding" @click="triggerRebuild">
          <LoaderCircle v-if="rebuilding" :size="14" class="is-spinning" aria-hidden="true" />
          <RefreshCw v-else :size="14" aria-hidden="true" />
          {{ rebuilding
            ? t('knowledgeCommands.rebuilding', '正在请求重建')
            : t('knowledgeCommands.rebuild', '重建受影响产物') }}
        </button>
        <p v-if="rebuildNotice" class="knowledge-command-note">{{ rebuildNotice }}</p>
        <ul v-if="rebuildReceipts.length" class="knowledge-command-detail-list">
          <li v-for="row in rebuildReceipts" :key="`${row.type}:${row.id}`">
            <span :class="['knowledge-command-detail-kind', receiptClass(row.outcome)]">
              {{ outcomeLabel(row.outcome) }}
            </span>
            <span class="knowledge-command-detail-title">{{ row.id }}</span>
            <span v-if="row.detail" class="knowledge-command-detail-excerpt">{{ row.detail }}</span>
          </li>
        </ul>
        <ul v-else-if="rebuildTargets.length" class="knowledge-command-detail-list">
          <li v-for="row in rebuildTargets" :key="`${row.type}:${row.id}`">
            <span class="knowledge-command-detail-kind">{{ row.type }}</span>
            <span class="knowledge-command-detail-title">{{ row.id }}</span>
            <span class="knowledge-command-detail-loc">{{ row.owner }}</span>
          </li>
        </ul>
      </div>

      <!--
        修订历史：知识演进的可审计回执本来就存在（course_knowledge_revision_log），
        此前只有 API、没有界面，教师无法回答"这个知识点上次是谁、为什么改的"。
      -->
      <div class="knowledge-command-history">
        <button type="button" :disabled="busy" @click="toggleHistory">
          <History :size="14" aria-hidden="true" />
          {{ historyOpen
            ? t('knowledgeCommands.hideHistory', '收起修订历史')
            : t('knowledgeCommands.showHistory', '查看修订历史') }}
        </button>
        <template v-if="historyOpen">
          <p v-if="historyLoading" class="knowledge-command-note">
            {{ t('knowledgeCommands.historyLoading', '正在读取修订历史') }}
          </p>
          <p v-else-if="historyError" class="knowledge-command-error">{{ historyError }}</p>
          <p v-else-if="!historyRows.length" class="knowledge-command-note">
            {{ t('knowledgeCommands.historyEmpty', '这门课程还没有知识修订记录') }}
          </p>
          <ul v-else class="knowledge-command-history-list">
            <li v-for="(entry, index) in historyRows" :key="entry.command_id || index">
              <span class="knowledge-command-history-op">{{ operationLabelOf(entry.operation) }}</span>
              <span class="knowledge-command-history-actor">{{ entry.actor }}</span>
              <span class="knowledge-command-history-reason">{{ entry.reason }}</span>
            </li>
          </ul>
        </template>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  FileSearch,
  History,
  LoaderCircle,
  RefreshCw,
  Scissors,
  Wrench,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http from '../utils/http'
import logger from '../utils/logger'

interface KnowledgePointLike {
  knowledge_id: string
  name: string
  statement?: string
}

const props = defineProps<{
  courseId: string
  point: KnowledgePointLike | null
}>()

const emit = defineEmits<{ (event: 'applied'): void }>()

// Only the operations a teacher can drive from this minimal panel. The backend
// whitelist is larger; the ones left out (split/merge/retire) move stable
// knowledge IDs and need an explicit old->new mapping UI, which this panel
// deliberately does not fake.
const operations = ['revise_knowledge_point', 'rename_knowledge_point'] as const
type Operation = (typeof operations)[number]

const operation = ref<Operation>('revise_knowledge_point')
const value = ref('')
const reason = ref('')
const candidate = ref<any>(null)
const previewing = ref(false)
const confirming = ref(false)
const errorText = ref('')
const receiptText = ref('')
const openGroup = ref('')
const detailRows = ref<any[]>([])
const detailTruncated = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const historyOpen = ref(false)
const historyRows = ref<any[]>([])
const historyLoading = ref(false)
const historyError = ref('')
const rebuildAvailable = ref(false)
const rebuilding = ref(false)
const rebuildNotice = ref('')
const rebuildTargets = ref<any[]>([])
const rebuildReceipts = ref<any[]>([])
const lastReceiptId = ref('')
const proposing = ref(false)
const splitVerdict = ref('')
const splitParts = ref<any[]>([])

const busy = computed(() => previewing.value || confirming.value || proposing.value)
const canPreview = computed(
  () => !busy.value && Boolean(props.point) && reason.value.trim().length > 0 && value.value.trim().length > 0,
)

const valueLabel = computed(() =>
  operation.value === 'revise_knowledge_point'
    ? t('knowledgeCommands.statement', '知识陈述')
    : t('knowledgeCommands.newName', '新名称'),
)

const valuePlaceholder = computed(() =>
  operation.value === 'revise_knowledge_point'
    ? t('knowledgeCommands.statementPlaceholder', '写清这个知识点表达的命题')
    : t('knowledgeCommands.namePlaceholder', '输入新的知识点名称'),
)

const impact = computed(() => {
  const report = candidate.value?.impact_report || {}
  return {
    needsRegeneration: (report.needs_regeneration || []).length,
    stale: (report.stale || []).length,
    blocked: (report.blocked || []).length,
    dependents: (report.dependent_knowledge_ids || []).length,
  }
})

const blockingIssues = computed(() =>
  (candidate.value?.blocking_issues || [])
    .map((issue: any) => String(issue?.message || '').trim())
    .filter(Boolean)
    .slice(0, 5),
)

function operationLabel(value: Operation): string {
  return value === 'revise_knowledge_point'
    ? t('knowledgeCommands.opRevise', '修订知识陈述')
    : t('knowledgeCommands.opRename', '重命名知识点')
}

// Reset whenever the teacher moves to another knowledge point: a candidate is
// pinned to the point and base revision it was computed from, so carrying it
// across selections would let a confirm apply to the wrong target.
watch(
  () => props.point?.knowledge_id,
  () => {
    value.value = props.point?.statement || ''
    reason.value = ''
    candidate.value = null
    errorText.value = ''
    receiptText.value = ''
    rebuildAvailable.value = false
    rebuildNotice.value = ''
    rebuildTargets.value = []
    rebuildReceipts.value = []
    splitVerdict.value = ''
    splitParts.value = []
  },
  { immediate: true },
)

// Switching operation changes which field `value` means, so seed it with the
// current content of the newly targeted field rather than leaving the old one.
watch(operation, next => {
  value.value = next === 'revise_knowledge_point'
    ? props.point?.statement || ''
    : props.point?.name || ''
  candidate.value = null
})

function errorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}

async function preview(): Promise<void> {
  if (!canPreview.value || !props.point) return
  previewing.value = true
  errorText.value = ''
  receiptText.value = ''
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/preview-edit`,
      {
        knowledge_id: props.point.knowledge_id,
        operation: operation.value,
        value: value.value.trim(),
        reason: reason.value.trim(),
      },
      { silentError: true },
    )
    candidate.value = response.data?.candidate || null
  } catch (error: any) {
    logger.error(error)
    candidate.value = null
    errorText.value = errorMessage(
      error,
      t('knowledgeCommands.previewFailed', '影响预览失败，知识库未发生变化'),
    )
  } finally {
    previewing.value = false
  }
}

async function confirm(): Promise<void> {
  if (!candidate.value?.confirmable || !props.point) return
  const candidateId = String(candidate.value.candidate_id || '')
  confirming.value = true
  errorText.value = ''
  try {
    await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/confirm-edit`,
      {
        command_id: `kc-${candidate.value.candidate_id}`,
        knowledge_id: props.point.knowledge_id,
        operation: operation.value,
        value: value.value.trim(),
        reason: reason.value.trim(),
      },
      { silentError: true },
    )
    candidate.value = null
    reason.value = ''
    receiptText.value = t('knowledgeCommands.applied', '知识修订已生效，下游产物已标记待重建。')
    openGroup.value = ''
    historyRows.value = []
    rebuildAvailable.value = true
    lastReceiptId.value = candidateId
    rebuildNotice.value = ''
    rebuildTargets.value = []
    rebuildReceipts.value = []
    emit('applied')
  } catch (error: any) {
    logger.error(error)
    // A stale base is not a dead end: try to re-anchor the candidate onto the
    // current revision instead of telling the teacher their work is gone.
    if (error?.response?.data?.detail?.code === 'knowledge_base_revision_changed') {
      const relocated = await relocate()
      if (relocated) return
    }
    errorText.value = errorMessage(
      error,
      t('knowledgeCommands.confirmFailed', '确认失败，知识库保持原修订'),
    )
  } finally {
    confirming.value = false
  }
}

async function relocate(): Promise<boolean> {
  if (!props.point || !candidate.value) return false
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/relocate-edit`,
      {
        knowledge_id: props.point.knowledge_id,
        operation: operation.value,
        value: value.value.trim(),
        reason: reason.value.trim(),
        base_knowledge_revision_id: candidate.value.base_knowledge_revision_id,
      },
      { silentError: true },
    )
    const relocation = response.data?.relocation
    if (relocation?.outcome === 'relocated' && relocation.candidate) {
      // Re-offer, never auto-apply: the impact was recomputed against a base
      // the teacher has not seen, so it needs a fresh confirmation.
      candidate.value = relocation.candidate
      errorText.value = t(
        'knowledgeCommands.relocated',
        '知识库已变化，影响已按当前版本重新计算，请再次确认。',
      )
      return true
    }
    if (relocation?.outcome === 'conflict') {
      candidate.value = null
      errorText.value = relocation.message
        || t('knowledgeCommands.relocateConflict', '知识库已变化且无法自动衔接，请重新发起。')
      return true
    }
  } catch (relocateError: any) {
    logger.error(relocateError)
  }
  return false
}

function discard(): void {
  candidate.value = null
  errorText.value = ''
  openGroup.value = ''
}

function operationLabelOf(value: string): string {
  if (value === 'revise_knowledge_point') return t('knowledgeCommands.opRevise', '修订知识陈述')
  if (value === 'rename_knowledge_point') return t('knowledgeCommands.opRename', '重命名知识点')
  return value
}

async function proposeSplit(): Promise<void> {
  if (!props.point) return
  proposing.value = true
  errorText.value = ''
  splitVerdict.value = ''
  splitParts.value = []
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/propose-split`,
      { knowledge_id: props.point.knowledge_id },
      { silentError: true, timeout: 180000 },
    )
    const proposal = response.data?.proposal || {}
    const proposed = response.data?.candidate || null
    if (proposed) {
      // AI 的建议进入与手工编辑同一个候选区，教师照样要看影响、再确认。
      candidate.value = proposed
      splitParts.value = proposal.parts || []
      splitVerdict.value = proposal.reason
        || t('knowledgeCommands.splitSuggested', 'AI 建议拆分该知识点。')
    } else if (proposal.should_split) {
      splitVerdict.value = t('knowledgeCommands.splitRejected', 'AI 提出了拆分，但未通过质量门：')
        + (proposal.rejected_reason || '')
    } else {
      splitVerdict.value = proposal.reason
        || t('knowledgeCommands.splitNotNeeded', 'AI 判断该知识点无需拆分。')
    }
  } catch (error: any) {
    logger.error(error)
    errorText.value = errorMessage(
      error,
      t('knowledgeCommands.proposeFailed', 'AI 判断失败，请重试'),
    )
  } finally {
    proposing.value = false
  }
}

async function triggerRebuild(): Promise<void> {
  if (!props.point) return
  rebuilding.value = true
  rebuildNotice.value = ''
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/rebuild-downstream`,
      { request_id: `rb-${props.point.knowledge_id}-${lastReceiptId.value}` },
      { silentError: true },
    )
    const rebuild = response.data?.rebuild || {}
    rebuildTargets.value = rebuild.targets || []
    rebuildReceipts.value = rebuild.receipts || []
    // 逐对象如实转达：成功几个、仍待重建几个，都要让教师看到。
    if (rebuild.status === 'executed') {
      const summary = rebuild.summary || {}
      rebuildNotice.value = t('knowledgeCommands.rebuildDone', '重建完成')
        + `：${summary.content_changed || 0} ${t('knowledgeCommands.rebuiltUnit', '个已更新')}`
        + `，${summary.stale || 0} ${t('knowledgeCommands.stillStaleUnit', '个仍待重建')}`
    } else if (rebuild.status === 'nothing_to_rebuild') {
      rebuildNotice.value = t('knowledgeCommands.rebuildNothing', '当前没有需要重建的下游对象。')
    } else {
      rebuildNotice.value = rebuild.message
        || t('knowledgeCommands.rebuildUnavailable', '下游重建管线尚未接入，本次未触发重建。')
    }
  } catch (error: any) {
    logger.error(error)
    rebuildNotice.value = errorMessage(
      error,
      t('knowledgeCommands.rebuildFailed', '重建请求失败，请重试'),
    )
  } finally {
    rebuilding.value = false
  }
}

async function toggleHistory(): Promise<void> {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value || historyRows.value.length) return
  historyLoading.value = true
  historyError.value = ''
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/knowledge-library/revisions`,
      { silentError: true },
    )
    // 最近的改动最相关，倒序展示。
    historyRows.value = [...(response.data?.revisions || [])].reverse()
  } catch (error: any) {
    logger.error(error)
    historyError.value = errorMessage(
      error,
      t('knowledgeCommands.historyFailed', '修订历史读取失败，请重试'),
    )
  } finally {
    historyLoading.value = false
  }
}

// 后端给的 type_label 是中文兜底；界面文案必须走 i18n，否则英文模式下
// 明细行会显示"正文块""练习题"这类中文（真机验收时发现）。
const DETAIL_TYPE_KEYS: Record<string, string> = {
  section_content: 'sectionContent', practice: 'practice', slide_deck: 'slideDeck',
  lecture: 'lecture', handout: 'handout', practice_sheet: 'practiceSheet',
  lesson_plan: 'lessonPlan', outline: 'outline', mastery_criterion: 'masteryCriterion',
  learning_objective: 'learningObjective', knowledge_binding: 'knowledgeBinding',
  knowledge_point: 'knowledgePoint', teaching_representation: 'teachingRepresentation',
  course_knowledge_base: 'courseKnowledgeBase', course_document: 'courseDocument',
}

function typeLabel(row: any): string {
  const key = DETAIL_TYPE_KEYS[String(row?.type || '')]
  // 有 i18n 键就走 i18n；没有则退回后端标签，总比显示裸类型名强。
  return key
    ? t(`knowledgeCommands.objectType.${key}`, row?.type_label || row?.type || '')
    : (row?.type_label || row?.type || '')
}

function outcomeLabel(outcome: string): string {
  if (outcome === 'content_changed') return t('knowledgeCommands.outcomeChanged', '已更新')
  if (outcome === 'source_verified') return t('knowledgeCommands.outcomeVerified', '已核对')
  if (outcome === 'blocked') return t('knowledgeCommands.outcomeBlocked', '被阻断')
  if (outcome === 'unchanged') return t('knowledgeCommands.outcomeUnchanged', '未受影响')
  return t('knowledgeCommands.outcomeStale', '仍待重建')
}

function receiptClass(outcome: string): string {
  return outcome === 'content_changed' || outcome === 'source_verified'
    ? 'is-ok'
    : 'is-pending'
}

function groupLabel(group: string): string {
  if (group === 'needs_regeneration') return t('knowledgeCommands.needsRegeneration', '需重建')
  if (group === 'stale') return t('knowledgeCommands.stale', '待复核')
  return t('knowledgeCommands.blocked', '被阻断')
}

async function toggleDetail(group: string): Promise<void> {
  if (openGroup.value === group) {
    openGroup.value = ''
    return
  }
  openGroup.value = group
  if (!props.point) return
  detailLoading.value = true
  detailError.value = ''
  detailRows.value = []
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/knowledge-library/points/impact-detail`,
      {
        knowledge_id: props.point.knowledge_id,
        operation: operation.value,
        value: value.value.trim(),
        reason: reason.value.trim(),
      },
      { silentError: true },
    )
    const detail = response.data?.detail || {}
    detailRows.value = detail.groups?.[group] || []
    detailTruncated.value = Boolean(detail.truncated?.[group])
  } catch (error: any) {
    logger.error(error)
    detailError.value = errorMessage(
      error,
      t('knowledgeCommands.detailFailed', '明细读取失败，请重试'),
    )
  } finally {
    detailLoading.value = false
  }
}
</script>

<style scoped>
.knowledge-command-panel { display:flex; flex-direction:column; gap:10px; padding:14px 16px; border-top:1px solid #e7e9f2; background:#fbfbfe; }
.knowledge-command-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.knowledge-command-head > div { display:flex; align-items:center; gap:6px; color:#453b7a; }
.knowledge-command-head strong { font-size:12px; }
.knowledge-command-scope { color:#8a8fa3; font-size:10px; }
.knowledge-command-empty { margin:0; color:#8a8fa3; font-size:11px; }
.knowledge-command-target { margin:0; color:#6b7189; font-size:11px; }
.knowledge-command-target strong { color:#3b3560; }
.knowledge-command-field { display:flex; flex-direction:column; gap:4px; }
.knowledge-command-field > span { color:#6b7189; font-size:10.5px; font-weight:700; }
.knowledge-command-field select,
.knowledge-command-field textarea { padding:6px 8px; border:1px solid #e1e3ed; border-radius:7px; color:#33304d; font-size:11.5px; font-family:inherit; background:#fff; resize:vertical; }
.knowledge-command-field textarea:disabled { background:#f4f5f9; color:#9aa0b4; }
.knowledge-command-actions { display:flex; flex-wrap:wrap; gap:8px; }
.knowledge-command-actions button { min-height:28px; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:1px solid #e1e3ed; border-radius:7px; color:#5d5a80; background:#fff; font-size:10.5px; font-weight:700; cursor:pointer; }
.knowledge-command-actions button:disabled { color:#b3b7c6; cursor:not-allowed; }
.knowledge-command-actions button.is-primary { border-color:transparent; color:#fff; background:linear-gradient(135deg,#6a4fdb,#8b5cf6); }
.knowledge-command-actions button.is-primary:disabled { background:#cfcbe6; }
.knowledge-command-candidate { display:flex; flex-direction:column; gap:8px; padding:10px 12px; border:1px solid #ddd8f5; border-radius:9px; background:#fff; }
.knowledge-command-candidate > header { display:flex; align-items:center; gap:6px; color:#453b7a; font-size:11.5px; }
.knowledge-command-badge { margin-left:auto; padding:1px 7px; border-radius:20px; font-size:9.5px; font-weight:700; }
.knowledge-command-badge.is-ok { color:#1f7a4d; background:#e4f6ec; }
.knowledge-command-badge.is-blocked { color:#9a3a2f; background:#fdecea; }
.knowledge-command-note { margin:0; color:#8a8fa3; font-size:10.5px; }
.knowledge-command-impact { display:flex; flex-wrap:wrap; gap:8px; margin:0; padding:0; list-style:none; }
.knowledge-command-impact li { flex:1 1 auto; }
/* 计数是可点开的入口：给足触摸目标（>=32px 高），移动端也能点中。 */
.knowledge-command-impact button { width:100%; min-height:34px; display:flex; align-items:baseline; justify-content:center; gap:5px; padding:4px 9px; border:1px solid #e6e3f5; border-radius:8px; color:#6b7189; background:#fff; font-size:10.5px; font-family:inherit; cursor:pointer; }
.knowledge-command-impact button:hover:not(:disabled) { border-color:#c9c0ef; color:#5d46d7; }
.knowledge-command-impact button:disabled { color:#b3b7c6; cursor:default; }
.knowledge-command-impact strong { color:#3b3560; font-size:13px; }
.knowledge-command-detail { display:flex; flex-direction:column; gap:6px; padding:8px 10px; border:1px solid #e6e3f5; border-radius:8px; background:#fbfbfe; }
.knowledge-command-detail > header { display:flex; align-items:center; justify-content:space-between; gap:8px; color:#453b7a; font-size:11px; }
.knowledge-command-detail > header button { padding:2px 8px; border:1px solid #e1e3ed; border-radius:6px; color:#6b7189; background:#fff; font-size:10px; cursor:pointer; }
.knowledge-command-detail-list { max-height:240px; overflow:auto; display:flex; flex-direction:column; gap:7px; margin:0; padding:0; list-style:none; }
.knowledge-command-detail-list li { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; padding-bottom:6px; border-bottom:1px solid #eeecf8; }
.knowledge-command-detail-list li:last-child { border-bottom:0; padding-bottom:0; }
.knowledge-command-detail-kind { flex:0 0 auto; padding:1px 6px; border-radius:20px; color:#5d46d7; background:#eeebfd; font-size:9.5px; font-weight:700; }
.knowledge-command-detail-title { flex:1 1 160px; color:#33304d; font-size:11px; font-weight:600; overflow-wrap:anywhere; }
.knowledge-command-detail-loc { flex:0 0 auto; color:#8a8fa3; font-size:10px; }
.knowledge-command-detail-excerpt { flex:1 1 100%; color:#8a8fa3; font-size:10px; line-height:1.5; overflow-wrap:anywhere; }
.knowledge-command-detail-missing { flex:1 1 100%; color:#9a3a2f; font-size:10px; }
.knowledge-command-rebuild { display:flex; flex-direction:column; gap:6px; padding:8px 10px; border:1px solid #dcefe3; border-radius:8px; background:#f6fbf8; }
.knowledge-command-rebuild > button { min-height:30px; align-self:flex-start; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:1px solid #bfe3cd; border-radius:7px; color:#1f7a4d; background:#fff; font-size:10.5px; font-weight:700; cursor:pointer; }
.knowledge-command-rebuild > button:disabled { color:#a8b5ad; cursor:not-allowed; }
.knowledge-command-history { display:flex; flex-direction:column; gap:6px; }
.knowledge-command-history > button { min-height:30px; align-self:flex-start; display:inline-flex; align-items:center; gap:6px; padding:0 10px; border:1px solid #e1e3ed; border-radius:7px; color:#5d5a80; background:#fff; font-size:10.5px; font-weight:700; cursor:pointer; }
.knowledge-command-history-list { display:flex; flex-direction:column; gap:6px; margin:0; padding:0; list-style:none; }
.knowledge-command-history-list li { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; font-size:10.5px; }
.knowledge-command-history-op { padding:1px 6px; border-radius:20px; color:#1f7a4d; background:#e4f6ec; font-size:9.5px; font-weight:700; }
.knowledge-command-history-actor { color:#6b7189; font-weight:600; }
.knowledge-command-history-reason { flex:1 1 100%; color:#8a8fa3; overflow-wrap:anywhere; }
.knowledge-command-issues { margin:0; padding-left:16px; color:#9a3a2f; font-size:10.5px; }
.knowledge-command-error,
.knowledge-command-receipt { display:flex; align-items:flex-start; gap:6px; margin:0; font-size:10.5px; }
.knowledge-command-error { color:#9a3a2f; }
.knowledge-command-receipt { color:#1f7a4d; }
.is-spinning { animation:knowledge-command-spin 1s linear infinite; }
@keyframes knowledge-command-spin { to { transform:rotate(360deg); } }
@media (max-width: 720px) {
  .knowledge-command-panel { padding:12px; }
  .knowledge-command-impact li { flex:1 1 100%; }
  .knowledge-command-detail-list { max-height:200px; }
  .knowledge-command-actions button { flex:1 1 auto; justify-content:center; }
}
</style>
