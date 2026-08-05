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

      <div class="knowledge-command-actions">
        <button type="button" :disabled="!canPreview" @click="preview">
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
            <span>{{ t('knowledgeCommands.needsRegeneration', '需重建') }}</span>
            <strong>{{ impact.needsRegeneration }}</strong>
          </li>
          <li>
            <span>{{ t('knowledgeCommands.stale', '待复核') }}</span>
            <strong>{{ impact.stale }}</strong>
          </li>
          <li>
            <span>{{ t('knowledgeCommands.blocked', '被阻断') }}</span>
            <strong>{{ impact.blocked }}</strong>
          </li>
        </ul>

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
  LoaderCircle,
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

const busy = computed(() => previewing.value || confirming.value)
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
    emit('applied')
  } catch (error: any) {
    logger.error(error)
    errorText.value = errorMessage(
      error,
      t('knowledgeCommands.confirmFailed', '确认失败，知识库保持原修订'),
    )
  } finally {
    confirming.value = false
  }
}

function discard(): void {
  candidate.value = null
  errorText.value = ''
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
.knowledge-command-impact { display:flex; flex-wrap:wrap; gap:12px; margin:0; padding:0; list-style:none; }
.knowledge-command-impact li { display:flex; align-items:baseline; gap:5px; color:#6b7189; font-size:10.5px; }
.knowledge-command-impact strong { color:#3b3560; font-size:13px; }
.knowledge-command-issues { margin:0; padding-left:16px; color:#9a3a2f; font-size:10.5px; }
.knowledge-command-error,
.knowledge-command-receipt { display:flex; align-items:flex-start; gap:6px; margin:0; font-size:10.5px; }
.knowledge-command-error { color:#9a3a2f; }
.knowledge-command-receipt { color:#1f7a4d; }
.is-spinning { animation:knowledge-command-spin 1s linear infinite; }
@keyframes knowledge-command-spin { to { transform:rotate(360deg); } }
</style>
