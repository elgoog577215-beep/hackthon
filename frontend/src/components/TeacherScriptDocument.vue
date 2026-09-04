<template>
  <section ref="documentRoot" class="script-document" :class="{ 'is-ai-candidate': pendingCandidate }">
    <header v-if="!externalToolbar" class="script-header">
      <div class="script-title">
        <h3><MathText :content="lesson.title" /></h3>
      </div>
      <div class="script-actions">
        <template v-if="pendingCandidate">
          <template v-if="!assistantOpen">
            <button type="button" :disabled="aiBusy || requestBusy" @click="openInlineAi">
              <Sparkles :size="15" />{{ tr('courseWorkbench.aiCollaboration.iterateCandidate') }}
            </button>
            <button type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(false)">
              <X :size="15" />{{ tr('courseWorkbench.scriptDocument.discardAi') }}
            </button>
            <button class="resolved-action" type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(true)">
              <LoaderCircle v-if="aiBusy || requestBusy" :size="15" class="spin" />
              <Check v-else :size="15" />
              {{ aiBusy || requestBusy ? tr('courseWorkbench.scriptDocument.applyingAi') : tr('courseWorkbench.scriptDocument.applyAi') }}
            </button>
          </template>
        </template>
        <template v-else-if="editing">
          <button type="button" :disabled="saving" @click="cancelEditing">
            <X :size="15" />{{ tr('courseWorkbench.scriptDocument.cancel') }}
          </button>
          <button class="resolved-action" type="button" :disabled="saving" @click="saveDraft">
            <LoaderCircle v-if="saving" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ saving ? tr('courseWorkbench.scriptDocument.saving') : tr('courseWorkbench.scriptDocument.finishEditing') }}
          </button>
        </template>
        <template v-else>
          <button type="button" :disabled="!lesson.script.ready || !selectedNode || aiBusy || requestBusy" @click="openInlineAi">
            <Sparkles :size="15" />{{ tr('courseWorkbench.scriptDocument.aiImprove') }}
          </button>
          <button type="button" :disabled="!lesson.script.ready || !scriptSections.length" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.scriptDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <AppErrorNotice v-if="documentError" :presentation="documentError" compact />

    <div v-if="pendingCandidate" class="candidate-canvas-notice" role="status">
      <div>
        <Sparkles :size="16" />
        <span>
          <strong>{{ tr('courseWorkbench.scriptDocument.candidateCanvasTitle') }}</strong>
          <small>{{ tr('courseWorkbench.aiCollaboration.inlineCandidateBoundary') }}</small>
        </span>
      </div>
      <nav :aria-label="tr('courseWorkbench.aiCollaboration.inlineCandidateActions')">
        <button type="button" :disabled="aiBusy || requestBusy" @click="openInlineAi">
          <Sparkles :size="14" />{{ tr('courseWorkbench.aiCollaboration.iterateCandidate') }}
        </button>
        <button type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(false)">
          <X :size="14" />{{ tr('courseWorkbench.aiCollaboration.keepOriginal') }}
        </button>
        <button class="primary" type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(true)">
          <LoaderCircle v-if="aiBusy || requestBusy" :size="14" class="spin" />
          <Check v-else :size="14" />{{ tr('courseWorkbench.aiCollaboration.applyCandidate') }}
        </button>
      </nav>
    </div>

    <TextSelectionAiAction
      ref="inlineAiAction"
      :container="documentRoot"
      :disabled="editing || !lesson.script.ready"
      :busy="aiBusy || requestBusy"
      :label="tr('courseWorkbench.aiCollaboration.selectionModify')"
      :composer-title="tr('courseWorkbench.aiCollaboration.inlineComposerTitle')"
      :placeholder="tr('courseWorkbench.aiCollaboration.selectionPlaceholder')"
      :submit-label="tr('courseWorkbench.aiCollaboration.inlineGenerate')"
      :cancel-label="tr('common.cancel')"
      :working-label="tr('courseWorkbench.aiCollaboration.inlineWorking')"
      :selection-label="tr('courseWorkbench.aiCollaboration.inlineSelectionScope')"
      :block-label="tr('courseWorkbench.aiCollaboration.inlineBlockScope')"
      :document-label="tr('courseWorkbench.aiCollaboration.inlineDocumentScope')"
      :boundary-label="tr('courseWorkbench.aiCollaboration.inlineBoundary')"
      @invoke="emit('open-ai-selection', $event)"
    />

    <aside v-if="scriptStatusNotice && !externalToolbar" class="script-status-notice" :data-state="scriptStatusNotice.state">
      <strong>{{ scriptStatusNotice.title }}</strong>
      <span>{{ scriptStatusNotice.detail }}</span>
    </aside>

    <slot v-if="externalToolbar" name="toolbar" />

    <section v-if="!lesson.script.ready" class="script-generation-panel" :class="{ 'has-partial': scriptSections.length }">
      <form v-if="showGenerationForm" class="script-source-review" @submit.prevent="requestGeneration">
        <ol v-if="!externalToolbar" class="script-source-steps" :aria-label="tr('courseWorkbench.scriptDocument.flowLabel')">
          <li class="active">
            <span>1</span>
            <div>
              <strong>{{ tr('courseWorkbench.scriptDocument.reviewPlan') }}</strong>
              <small>{{ tr('courseWorkbench.scriptDocument.reviewPlanDetail') }}</small>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>{{ tr('courseWorkbench.scriptDocument.generateStep') }}</strong>
              <small>{{ tr('courseWorkbench.scriptDocument.generateStepDetail') }}</small>
            </div>
          </li>
        </ol>
        <div v-if="!externalToolbar || !canGenerate" class="script-source-review__heading" :data-state="canGenerate ? 'ready' : 'blocked'">
          <div v-if="canGenerate">
            <strong>{{ tr('courseWorkbench.scriptDocument.mappingTitle') }}</strong>
            <span>{{ tr('courseWorkbench.scriptDocument.mappingReady') }}</span>
          </div>
          <div v-else class="script-source-review__blocked" role="status" aria-live="polite">
            <TriangleAlert :size="22" aria-hidden="true" />
            <div>
              <strong>{{ scriptGenerationBlockStatus.title }}</strong>
              <span>{{ scriptGenerationBlockStatus.detail }}</span>
            </div>
          </div>
          <button
            v-if="!externalToolbar"
            type="submit"
            :disabled="generating || !canGenerate"
            :title="!canGenerate ? scriptGenerationBlockStatus.detail : ''"
          >
            <LoaderCircle v-if="generating" :size="16" class="spin" />
            <Sparkles v-else :size="16" />
            {{ generationActionLabel }}
          </button>
        </div>
        <ol v-if="mappedPlanBlocks.length" class="script-source-blocks">
          <li v-for="(block, index) in mappedPlanBlocks" :key="block.id">
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div>
              <strong><MathText :content="block.label" /></strong>
              <MathText v-if="block.sectionTitle" tag="small" :content="block.sectionTitle" />
              <MathText tag="p" :content="block.summary" />
            </div>
            <em v-if="block.minutes">{{ block.minutes }} {{ tr('courseWorkbench.scriptDocument.minutes') }}</em>
          </li>
        </ol>
        <p v-else-if="canGenerate" class="script-source-empty">{{ tr('courseWorkbench.scriptDocument.mappingEmpty') }}</p>
      </form>
      <div v-if="generationJob && !externalToolbar" class="script-generation-progress" :data-status="generationJob.status">
        <div>
          <span>{{ generationJob.message }}</span>
          <span class="script-generation-progress__actions">
            <strong>{{ generationJob.completed_blocks || 0 }}/{{ generationJob.total_blocks || 0 }}</strong>
            <button v-if="generating" type="button" @click="emit('pause-generation')">{{ tr('courseWorkbench.pause') }}</button>
            <button v-if="generating" type="button" @click="emit('cancel-generation')">{{ tr('common.cancel') }}</button>
          </span>
        </div>
        <i><span :style="{ width: `${generationProgress}%` }" /></i>
      </div>
    </section>

    <nav v-if="scriptSections.length > 1" class="script-tabs" :aria-label="tr('courseWorkbench.scriptDocument.sectionNavigation')">
      <button
        v-for="(node, index) in scriptSections"
        :key="node.section_node_id"
        type="button"
        :class="{ active: selectedNodeId === node.section_node_id }"
        :disabled="Boolean(pendingCandidate) && selectedNodeId !== node.section_node_id"
        @click="activateNode(node)"
      >
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        <MathText :content="node.title" />
      </button>
    </nav>

    <div v-if="scriptSections.length" class="script-continuous" :data-state="lesson.script.ready ? 'ready' : 'partial'">
      <article
        v-for="(node, nodeIndex) in scriptSections"
        :id="sectionAnchor(node)"
        :key="node.section_node_id"
        class="script-body"
        :class="{ active: selectedNodeId === node.section_node_id }"
        @focusin="activateNode(node, false)"
      >
        <header>
          <span>{{ String(nodeIndex + 1).padStart(2, '0') }}</span>
          <h4><MathText :content="node.title" /></h4>
        </header>
        <div v-if="editing && node.blocks?.length" class="script-block-editor">
          <section v-for="block in node.blocks" :key="block.block_id">
            <header>
              <div><span>{{ blockRoleLabel(block.role) }}</span><h5><MathText :content="block.title" /></h5></div>
              <small v-if="block.planned_minutes">{{ block.planned_minutes }} {{ tr('courseWorkbench.scriptDocument.minutes') }}</small>
            </header>
            <textarea v-model="blockDrafts[block.block_id]" rows="10" :aria-label="block.title" @input="recordEditSnapshot" />
          </section>
        </div>
        <textarea v-else-if="editing" v-model="drafts[node.section_node_id]" rows="24" :aria-label="node.title" @input="recordEditSnapshot" />
        <div v-else-if="pendingCandidate?.section_node_id === node.section_node_id && contentFor(node)" ref="candidateRef" class="script-content" data-state="candidate" tabindex="-1">
          <aside class="script-ai-change-bubble"><Sparkles :size="13" /><strong>{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</strong><MathText :content="node.title" /></aside>
          <MarkdownRenderer :key="`candidate-${pendingCandidate.candidate_id || pendingCandidate.section_node_id}`" :content="contentFor(node)" />
        </div>
        <div v-else-if="node.blocks?.length" class="script-modules">
          <section v-for="block in node.blocks" :key="block.block_id" class="script-module">
            <header>
              <div><span>{{ blockRoleLabel(block.role) }}</span><h5><MathText :content="block.title" /></h5></div>
              <small v-if="block.planned_minutes">{{ block.planned_minutes }} {{ tr('courseWorkbench.scriptDocument.minutes') }}</small>
            </header>
            <div class="script-streamed-block" :data-streaming="blockIsStreaming(block.block_id) ? 'true' : undefined">
              <MarkdownRenderer :key="`${block.block_id}-${block.content.length}-${generationJob?.stream_sequence || 0}`" :content="block.content" />
              <span v-if="blockIsStreaming(block.block_id)" class="stream-caret" aria-hidden="true" />
            </div>
            <ScriptVisualStudio
              v-if="lesson.script.ready"
              :course-id="courseId"
              :lesson-unit-id="lesson.lesson_unit_id"
              :script-revision-id="lesson.script.current_revision_id"
              :section-node-id="node.section_node_id"
              :block-id="block.block_id"
              :block-title="block.title"
            />
          </section>
          <div v-if="!lesson.script.ready && generating && nodeIndex === scriptSections.length - 1" class="script-block-waiting">
            <LoaderCircle :size="15" class="spin" />
            {{ generationJob?.current_block_title || tr('courseWorkbench.scriptDocument.waitingForNextBlock') }}
          </div>
        </div>
        <div v-else-if="contentFor(node)" class="script-content" data-state="current"><MarkdownRenderer :content="contentFor(node)" /></div>
        <div v-else class="script-empty">{{ tr('courseWorkbench.scriptPending') }}</div>
      </article>
    </div>

  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { Check, LoaderCircle, Pencil, Sparkles, TriangleAlert, X } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import ScriptVisualStudio from './ScriptVisualStudio.vue'
import TextSelectionAiAction, { type TeacherInlineAiRequest } from './TextSelectionAiAction.vue'
import { useDocumentEditHistory } from '../composables/useDocumentEditHistory'
import { t } from '../shared/i18n'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import { useTeacherScriptVisualStore } from '../stores/teacherScriptVisuals'
import type { TeacherLessonJob, TeacherLessonProjection, TeacherLessonScriptCandidate, TeacherLessonScriptState } from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'

const props = withDefaults(defineProps<{
  courseId: string
  lesson: TeacherLessonProjection
  externalError?: string
  generating?: boolean
  generationJob?: TeacherLessonJob
  generationError?: string
  canGenerate?: boolean
  generationBlockedReason?: string
  assistantOpen?: boolean
  materialAssetIds?: string[]
  externalToolbar?: boolean
  requestBusy?: boolean
}>(), {
  generating: false,
  externalError: '',
  generationJob: undefined,
  generationError: '',
  canGenerate: false,
  generationBlockedReason: '',
  assistantOpen: false,
  materialAssetIds: () => [],
  externalToolbar: false,
  requestBusy: false,
})

const emit = defineEmits<{
  (event: 'saved'): void
  (event: 'generate', requirement: string): void
  (event: 'pause-generation'): void
  (event: 'cancel-generation'): void
  (event: 'open-ai'): void
  (event: 'open-ai-selection', value: TeacherInlineAiRequest): void
  (event: 'ai-candidate-change', candidate: TeacherLessonScriptCandidate | null): void
  (event: 'ai-resolving', result: { accept: boolean }): void
  (event: 'ai-resolved', result: { accept: boolean }): void
  (event: 'ai-error', message: string): void
  (event: 'ai-scope-change', scope: { id: string; title: string }): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
const scriptVisualStore = useTeacherScriptVisualStore()
const selectedNodeId = ref('')
const editing = ref(false)
const saving = ref(false)
const saveError = ref<unknown>(null)
const drafts = reactive<Record<string, string>>({})
const blockDrafts = reactive<Record<string, string>>({})
const aiBusy = ref(false)
const aiError = ref<unknown>(null)
const pendingCandidate = ref<TeacherLessonScriptCandidate | null>(null)
const candidateRef = ref<HTMLElement | null>(null)
const documentRoot = ref<HTMLElement | null>(null)
const inlineAiAction = ref<{ openForDocument: (text?: string) => void } | null>(null)
onUnmounted(() => scriptVisualStore.releaseAssets())
type ScriptEditSnapshot = { drafts: Record<string, string>; blockDrafts: Record<string, string> }
const editHistory = useDocumentEditHistory<ScriptEditSnapshot>(snapshot => {
  Object.keys(drafts).forEach(key => { delete drafts[key] })
  Object.keys(blockDrafts).forEach(key => { delete blockDrafts[key] })
  Object.assign(drafts, snapshot.drafts)
  Object.assign(blockDrafts, snapshot.blockDrafts)
})

const documentError = computed(() => {
  if (saveError.value) return toAppError(saveError.value, {
    title: tr('courseWorkbench.scriptDocument.saveFailed').replace(/，?请重试。?$/, ''),
    fallback: tr('courseWorkbench.scriptDocument.saveFailed'),
  })
  if (aiError.value) return toAppError(aiError.value, {
    title: tr('courseWorkbench.scriptDocument.aiFailed').replace(/，?请重试。?$/, ''),
    fallback: tr('courseWorkbench.scriptDocument.aiFailed'),
  })
  if (props.generationError && !props.lesson.script.ready) return toAppError(props.generationError, {
    title: tr('courseWorkbench.scriptDocument.generateFailed'),
    fallback: props.generationError,
  })
  if (props.externalError) return toAppError(props.externalError, {
    title: tr('courseWorkbench.scriptDocument.operationFailed'),
    fallback: props.externalError,
  })
  return null
})

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.scriptDocument.edit': '编辑讲义',
  'courseWorkbench.scriptDocument.editing': '编辑中',
  'courseWorkbench.scriptDocument.cancel': '取消',
  'courseWorkbench.scriptDocument.finishEditing': '完成编辑',
  'courseWorkbench.scriptDocument.saving': '正在保存…',
  'courseWorkbench.scriptDocument.saveFailed': '讲义保存失败，请重试。',
  'courseWorkbench.scriptDocument.operationFailed': '讲义操作失败',
  'courseWorkbench.scriptDocument.aiImprove': 'AI 优化',
  'courseWorkbench.aiCollaboration.selectionModify': 'AI 修改',
  'courseWorkbench.aiCollaboration.inlineComposerTitle': '告诉 AI 怎么改',
  'courseWorkbench.aiCollaboration.inlineGenerate': '生成修改',
  'courseWorkbench.aiCollaboration.inlineWorking': '正在生成候选…',
  'courseWorkbench.aiCollaboration.inlineSelectionScope': '修改选中内容',
  'courseWorkbench.aiCollaboration.inlineBlockScope': '修改当前段落',
  'courseWorkbench.aiCollaboration.inlineDocumentScope': '修改当前讲义',
  'courseWorkbench.aiCollaboration.inlineBoundary': 'AI 只生成候选，采用后才会写入正式讲义。',
  'courseWorkbench.aiCollaboration.inlineCandidateBoundary': '原文仍然保留，只有采用后候选才会写入正式讲义。',
  'courseWorkbench.aiCollaboration.inlineCandidateActions': 'AI 候选操作',
  'courseWorkbench.aiCollaboration.iterateCandidate': '继续调整',
  'courseWorkbench.aiCollaboration.keepOriginal': '保留原文',
  'courseWorkbench.aiCollaboration.applyCandidate': '采用修改',
  'courseWorkbench.scriptDocument.aiPlaceholder': '输入你想调整的内容…',
  'courseWorkbench.scriptDocument.generateAi': '生成方案',
  'courseWorkbench.scriptDocument.aiGenerating': '生成中…',
  'courseWorkbench.scriptDocument.aiCandidate': 'AI 方案',
  'courseWorkbench.scriptDocument.candidateCanvasTitle': 'AI 候选已嵌入讲义正文',
  'courseWorkbench.scriptDocument.discardAi': '放弃',
  'courseWorkbench.scriptDocument.applyAi': '采用',
  'courseWorkbench.scriptDocument.applyingAi': '正在采用…',
  'courseWorkbench.scriptDocument.aiFailed': 'AI 优化失败，请重试。',
  'courseWorkbench.scriptDocument.sectionNavigation': '讲义小节',
  'courseWorkbench.scriptDocument.sourceRecovery': '续写补全稿',
  'courseWorkbench.scriptDocument.sourceTeacherEdit': '教师编辑',
  'courseWorkbench.scriptDocument.sourceAiOptimization': 'AI 优化',
  'courseWorkbench.scriptDocument.sourceModel': 'AI 生成',
  'courseWorkbench.scriptDocument.sourceLegacy': '旧版讲义',
  'courseWorkbench.scriptDocument.statusCurrentReady': '当前正文可用',
  'courseWorkbench.scriptDocument.statusGenerated': '已生成',
  'courseWorkbench.scriptDocument.statusPreviousFailureDetail': '最近一次 AI 生成没有完成；当前展示的是已经单独保存并通过检查的正文，不是该次失败任务的输出。',
  'courseWorkbench.scriptDocument.statusGeneratedDetail': '当前修订已是页面内容稿与 PPT 的生成依据。',
  'courseWorkbench.scriptDocument.flowLabel': '讲义生成步骤',
  'courseWorkbench.scriptDocument.reviewPlan': '检查教案映射',
  'courseWorkbench.scriptDocument.reviewPlanDetail': '核对本讲教学块',
  'courseWorkbench.scriptDocument.generateStep': '生成讲义',
  'courseWorkbench.scriptDocument.generateStepDetail': '按映射内容直接生成',
  'courseWorkbench.scriptDocument.mappingTitle': '本讲讲义将按以下教案生成',
  'courseWorkbench.scriptDocument.mappingReady': '教学块已映射，核对后可直接开始。',
  'courseWorkbench.scriptDocument.mappingBlockedTitle': '暂无可用教案',
  'courseWorkbench.scriptDocument.mappingBlockedDetail': '请先完成本讲教案，再生成讲义。',
  'courseWorkbench.scriptDocument.generationBlockedTitle': '暂时无法生成讲义',
  'courseWorkbench.scriptDocument.mappingEmpty': '教案中还没有可映射的教学块。',
  'courseWorkbench.scriptDocument.generate': '生成本讲讲义',
  'courseWorkbench.scriptDocument.generating': '正在生成…',
  'courseWorkbench.scriptDocument.stopGeneration': '停止',
  'courseWorkbench.scriptDocument.continueGenerating': '继续生成剩余内容',
  'courseWorkbench.scriptDocument.waitingForNextBlock': '正在准备下一个教学块',
  'courseWorkbench.scriptDocument.generateFailed': '讲义生成失败',
  'courseWorkbench.scriptDocument.planRequired': '请先生成本讲教案',
  'courseWorkbench.scriptDocument.minutes': '分钟',
  'courseWorkbench.scriptPending': '本讲暂时没有可用讲义。',
}

function tr(key: string): string {
  return t(key, fallbackMessages[key] || key)
}

type ScriptSection = TeacherLessonScriptState['sections'][number]
const sourceLabel = computed(() => {
  const source = String(props.lesson.script.generation_source || '')
  if (source.includes('recovery') || source.includes('fallback')) return tr('courseWorkbench.scriptDocument.sourceRecovery')
  if (source === 'teacher_edit') return tr('courseWorkbench.scriptDocument.sourceTeacherEdit')
  if (source === 'ai_optimization') return tr('courseWorkbench.scriptDocument.sourceAiOptimization')
  if (source.includes('model')) return tr('courseWorkbench.scriptDocument.sourceModel')
  return tr('courseWorkbench.scriptDocument.sourceLegacy')
})
const scriptStatusNotice = computed(() => {
  if (!props.lesson.script.ready) return null
  if (['failed', 'cancelled'].includes(String(props.generationJob?.status || ''))) {
    return {
      state: 'info',
      title: `${sourceLabel.value} · ${tr('courseWorkbench.scriptDocument.statusCurrentReady')}`,
      detail: tr('courseWorkbench.scriptDocument.statusPreviousFailureDetail'),
    }
  }
  if (!props.lesson.script.generation_source && !props.lesson.script.quality_report) return null
  return {
    state: 'ready',
    title: `${sourceLabel.value} · ${tr('courseWorkbench.scriptDocument.statusGenerated')}`,
    detail: tr('courseWorkbench.scriptDocument.statusGeneratedDetail'),
  }
})
const scriptSections = computed<ScriptSection[]>(() => {
  if (props.lesson.script.ready) return props.lesson.script.sections || []
  const sections = (props.generationJob?.result_sections || []).map(section => ({
    ...section,
    blocks: section.blocks?.map(block => ({ ...block })),
  }))
  const streamedBlocks = props.generationJob?.streamed_block_content || {}
  Object.entries(streamedBlocks).forEach(([blockId, content]) => {
    const arrangementBlock = props.lesson.arrangement?.blocks?.find(block => block.block_id === blockId)
    const sectionId = arrangementBlock?.section_node_id || props.lesson.sections[0]?.section_node_id || `stream-${blockId}`
    let section = sections.find(item => item.section_node_id === sectionId)
    if (!section) {
      section = {
        section_node_id: sectionId,
        title: arrangementBlock?.section_title
          || props.lesson.sections.find(item => item.section_node_id === sectionId)?.title
          || props.generationJob?.current_block_title
          || tr('courseWorkbench.scriptDocument.generating'),
        content: '',
        schema_version: 'teacher_script_v2',
        blocks: [],
      }
      sections.push(section)
    }
    const existing = section.blocks?.find(block => block.block_id === blockId)
    if (existing) {
      if (props.generationJob?.block_states?.[blockId] !== 'completed') existing.content = content
      return
    }
    section.blocks = [
      ...(section.blocks || []),
      {
        block_id: blockId,
        module_id: arrangementBlock?.module_id || 'streaming',
        role: arrangementBlock?.role || 'concept',
        title: arrangementBlock?.name || props.generationJob?.current_block_title || blockId,
        content,
        planned_minutes: arrangementBlock?.planned_minutes,
      },
    ]
  })
  return sections
})
const generationProgress = computed(() => Math.max(0, Math.min(100, Number(props.generationJob?.progress || 0))))
const showGenerationForm = computed(() => (
  !props.generating
  && !['completed', 'completed_with_warnings'].includes(String(props.generationJob?.status || ''))
))
const generationActionLabel = computed(() => {
  if (props.generating) return tr('courseWorkbench.scriptDocument.generating')
  if (['failed', 'cancelled'].includes(String(props.generationJob?.status || '')) && Number(props.generationJob?.completed_blocks || 0) > 0) {
    return tr('courseWorkbench.scriptDocument.continueGenerating')
  }
  return tr('courseWorkbench.scriptDocument.generate')
})
type MappedPlanBlock = {
  id: string
  label: string
  sectionTitle: string
  summary: string
  minutes: number
}
const mappedPlanBlocks = computed<MappedPlanBlock[]>(() => {
  const plan = props.lesson.plan
  const revision = plan.current_revision
  const sections = Array.isArray(revision?.plan?.sections) ? revision.plan.sections : []
  const arrangementById = new Map(
    (props.lesson.arrangement?.blocks || []).map(block => [block.block_id, block]),
  )
  const blocks = sections.flatMap((section: Record<string, any>) => {
    const sectionTitle = props.lesson.sections.find(item => item.section_node_id === section.node_id)?.title || ''
    return (Array.isArray(section.teaching_modules) ? section.teaching_modules : []).map((module: Record<string, any>, index: number) => {
      const arrangement = arrangementById.get(String(module.arrangement_block_id || ''))
      return {
        id: String(module.arrangement_block_id || `${section.node_id || 'section'}:${module.module_id || index}`),
        label: String(module.label || arrangement?.name || blockRoleLabel(String(module.role || arrangement?.role || ''))),
        sectionTitle,
        summary: String(module.teacher_activity || module.teaching_purpose || module.teaching_guidance || arrangement?.content_summary || arrangement?.purpose || ''),
        minutes: Number(module.planned_minutes || arrangement?.planned_minutes || 0),
      }
    })
  })
  if (blocks.length) return blocks
  return (props.lesson.arrangement?.blocks || []).map((block, index) => ({
    id: block.block_id || `arrangement:${index}`,
    label: block.name || blockRoleLabel(block.role),
    sectionTitle: block.section_title || '',
    summary: block.teacher_activity || block.content_summary || block.purpose || '',
    minutes: Number(block.planned_minutes || 0),
  }))
})
const scriptGenerationBlockStatus = computed(() => (
  props.generationBlockedReason
    ? {
        title: tr('courseWorkbench.scriptDocument.generationBlockedTitle'),
        detail: props.generationBlockedReason,
      }
    : {
        title: tr('courseWorkbench.scriptDocument.mappingBlockedTitle'),
        detail: tr('courseWorkbench.scriptDocument.mappingBlockedDetail'),
      }
))
const selectedNode = computed(() => scriptSections.value.find(node => node.section_node_id === selectedNodeId.value) || scriptSections.value[0] || null)

function blockIsStreaming(blockId: string): boolean {
  return Boolean(
    !props.lesson.script.ready
    && props.generating
    && props.generationJob?.current_block_id === blockId
    && props.generationJob?.block_states?.[blockId] !== 'completed',
  )
}

function contentFor(node: ScriptSection): string {
  if (pendingCandidate.value?.section_node_id === node.section_node_id) return pendingCandidate.value.replacement_text
  return node.content || ''
}

function sectionAnchor(node: ScriptSection): string {
  return `script-section-${node.section_node_id.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

function activateNode(node: ScriptSection, scroll = true) {
  if (pendingCandidate.value && pendingCandidate.value.section_node_id !== node.section_node_id) return
  selectedNodeId.value = node.section_node_id
  if (scroll) document.getElementById(sectionAnchor(node))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function requestGeneration() {
  if (!props.generating && props.canGenerate) emit('generate', '')
}

function beginEditing() {
  scriptSections.value.forEach(node => {
    drafts[node.section_node_id] = node.content || ''
    node.blocks?.forEach(block => { blockDrafts[block.block_id] = block.content || '' })
  })
  editHistory.reset({ drafts: { ...drafts }, blockDrafts: { ...blockDrafts } })
  editing.value = true
  saveError.value = null
}

function cancelEditing() {
  editing.value = false
  saveError.value = null
  Object.keys(drafts).forEach(key => { delete drafts[key] })
  Object.keys(blockDrafts).forEach(key => { delete blockDrafts[key] })
  editHistory.clear()
}

function recordEditSnapshot() {
  queueMicrotask(() => {
    if (editing.value) editHistory.record({ drafts: { ...drafts }, blockDrafts: { ...blockDrafts } })
  })
}

async function saveDraft() {
  if (saving.value) return
  saving.value = true
  saveError.value = null
  try {
    const sections = scriptSections.value.map(node => (
      node.blocks?.length
        ? {
            ...node,
            blocks: node.blocks.map(block => ({
              ...block,
              content: blockDrafts[block.block_id] ?? block.content ?? '',
            })),
          }
        : { ...node, content: drafts[node.section_node_id] ?? node.content ?? '' }
    ))
    await lessonStore.saveScriptDraft(
      props.courseId,
      props.lesson.lesson_unit_id,
      props.lesson.script.current_revision_id,
      sections,
    )
    cancelEditing()
    emit('saved')
  } catch (error: any) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

async function requestAiCandidate(value: string) {
  const node = selectedNode.value
  const instruction = value.trim()
  if (!node || !instruction || aiBusy.value || !node.content.trim()) return null
  aiBusy.value = true
  aiError.value = null
  try {
    const result = await lessonStore.rewriteScriptSection(
      props.courseId,
      props.lesson.lesson_unit_id,
      props.lesson.script.current_revision_id,
      node.section_node_id,
      instruction,
      props.materialAssetIds,
    )
    pendingCandidate.value = result
    emit('ai-candidate-change', pendingCandidate.value)
    return pendingCandidate.value
  } catch (error: any) {
    aiError.value = error
    emit('ai-error', error?.response?.data?.detail?.message || tr('courseWorkbench.scriptDocument.aiFailed'))
    return null
  } finally {
    aiBusy.value = false
  }
}

async function resolveAiCandidate(accept: boolean) {
  if (!pendingCandidate.value || aiBusy.value) return false
  emit('ai-resolving', { accept })
  aiBusy.value = true
  aiError.value = null
  try {
    await lessonStore.resolveScriptAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      pendingCandidate.value.candidate_id,
      accept,
    )
    pendingCandidate.value = null
    emit('ai-candidate-change', null)
    if (accept) emit('saved')
    emit('ai-resolved', { accept })
    return true
  } catch (error: any) {
    aiError.value = error
    emit('ai-error', error?.response?.data?.detail?.message || tr('courseWorkbench.scriptDocument.aiFailed'))
    return false
  } finally {
    aiBusy.value = false
  }
}

function focusAiCandidate() {
  candidateRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  candidateRef.value?.focus({ preventScroll: true })
}

function openInlineAi() {
  inlineAiAction.value?.openForDocument(selectedNode.value?.content || '')
}

function selectAiScope(scopeId: string) {
  if (pendingCandidate.value || aiBusy.value || !scriptSections.value.some(node => node.section_node_id === scopeId)) return false
  selectedNodeId.value = scopeId
  return true
}

function blockRoleLabel(role: string) {
  const fallbacks: Record<string, string> = {
    orientation: '课堂导向', prerequisite: '前置衔接', objective: '教学目标', concept: '概念讲解',
    reasoning: '推理过程', example: '示例讲解', counterexample: '反例辨析', application: '应用迁移',
    activity: '课堂活动', feedback: '检查反馈', misconception: '易错辨析', checkpoint: '课堂检查',
    remediation: '补充讲解', summary: '课堂小结', transfer: '综合迁移',
  }
  return t(`courseWorkbench.scriptDocument.roles.${role}`, fallbacks[role] || '教学环节')
}

watch(() => props.lesson.lesson_unit_id, () => {
  cancelEditing()
  pendingCandidate.value = null
  emit('ai-candidate-change', null)
  aiError.value = null
  selectedNodeId.value = scriptSections.value[0]?.section_node_id || ''
}, { immediate: true })

watch(() => ({
  courseId: props.courseId,
  lessonUnitId: props.lesson.lesson_unit_id,
  scriptRevisionId: props.lesson.script.current_revision_id,
  ready: props.lesson.script.ready,
}), ({ courseId, lessonUnitId, scriptRevisionId, ready }) => {
  if (!ready || !courseId || !lessonUnitId || !scriptRevisionId) return
  const current = scriptVisualStore.view(courseId, lessonUnitId)
  const force = Boolean(current && current.script_revision_id !== scriptRevisionId)
  void scriptVisualStore.load(courseId, lessonUnitId, force).catch(() => {
    // Each block keeps the scoped load error visible without interrupting script reading.
  })
}, { immediate: true })

watch(() => [
  props.lesson.script.current_revision_id,
  props.lesson.script.ai_candidate,
], () => {
  const restored = props.lesson.script.ai_candidate
  pendingCandidate.value = restored?.status === 'pending'
    && restored.base_revision_id === props.lesson.script.current_revision_id
    ? restored
    : null
  if (pendingCandidate.value?.section_node_id) {
    selectedNodeId.value = pendingCandidate.value.section_node_id
  }
  emit('ai-candidate-change', pendingCandidate.value)
}, { immediate: true, deep: true })

watch(scriptSections, sections => {
  if (!sections.some(node => node.section_node_id === selectedNodeId.value)) {
    selectedNodeId.value = sections[0]?.section_node_id || ''
  }
})

watch(selectedNode, node => emit('ai-scope-change', { id: node?.section_node_id || '', title: node?.title || '' }), { immediate: true })

defineExpose({
  requestAiCandidate,
  resolveAiCandidate,
  focusAiCandidate,
  selectAiScope,
  openInlineAi,
  editing,
  saving,
  aiBusy,
  beginEditing,
  cancelEditing,
  saveDraft,
  canUndo: editHistory.canUndo,
  canRedo: editHistory.canRedo,
  undoEdit: editHistory.undo,
  redoEdit: editHistory.redo,
})
</script>

<style scoped>
.script-document{background:#fff}.script-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}.script-title{min-width:0;display:flex;align-items:center;gap:9px}.script-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}.script-actions{flex:none;display:flex;align-items:center;gap:2px}.script-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:14px;font-weight:750;cursor:pointer}.script-actions button:hover{color:#3730a3;background:#f2f3fa}.script-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-actions button:disabled{opacity:.45;cursor:not-allowed}.script-actions .resolved-action{margin-left:4px;border-color:#d7ddea;background:#fff}.script-ai{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;gap:10px;padding:12px 28px;border-bottom:1px solid #e8ecf2;background:#fbfcff}.script-ai textarea{min-height:58px;padding:9px 11px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:14px;line-height:1.5;resize:vertical}.script-ai textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-ai button,.script-generate button{display:flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:14px;font-weight:750;cursor:pointer}.script-ai button:disabled,.script-generate button:disabled{opacity:.45;cursor:not-allowed}.script-generation-panel{border-bottom:1px solid #e8ecf2;background:#fbfcfe}.script-generate{min-height:320px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-content:start;gap:12px;padding:28px}.script-generation-panel.has-partial .script-generate{min-height:auto;padding-bottom:14px}.script-generate textarea{min-height:112px;box-sizing:border-box;padding:13px 14px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:15px;line-height:1.65;resize:vertical}.script-generate textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-generate textarea:disabled{color:#64748b;background:#f7f8fa}.script-generate button{min-height:42px;padding-inline:18px}.script-generation-progress{display:grid;gap:7px;padding:0 28px 18px}.script-generation-progress>div{display:flex;align-items:center;justify-content:space-between;gap:18px;color:#5d6879;font-size:14px}.script-generation-progress strong{color:#4338ca;font-size:14px}.script-generation-progress>i{height:4px;overflow:hidden;border-radius:4px;background:#e6e8f0}.script-generation-progress>i span{height:100%;display:block;border-radius:inherit;background:#5b57e8}.script-generation-progress[data-status="failed"]>i span{background:#e08a2e}.script-tabs{display:flex;gap:24px;overflow:auto;padding:0 28px;border-bottom:1px solid #e8ecf2}.script-tabs button{max-width:280px;min-height:48px;display:flex;align-items:center;gap:7px;padding:0;border:0;border-bottom:2px solid transparent;color:#64748b;background:transparent;font-size:14px;white-space:nowrap;cursor:pointer}.script-tabs button span{color:#94a3b8;font-size:14px;font-weight:800}.script-tabs button:hover{color:#3730a3}.script-tabs button.active{border-bottom-color:#5b57e8;color:#3730a3;font-weight:750}.script-tabs button.active span{color:#6366f1}.script-body{min-height:360px;padding:28px}.script-body[data-state="partial"]{background:#fff}.script-body>header{display:flex;align-items:center;gap:10px;margin-bottom:22px}.script-body>header span{color:#6366f1;font-size:14px;font-weight:850}.script-body>header h4{margin:0;color:#172033;font-size:16px}.script-body>textarea,.script-block-editor textarea{width:100%;box-sizing:border-box;padding:14px 15px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:15px;line-height:1.75;resize:vertical}.script-body>textarea{min-height:520px}.script-block-editor textarea{min-height:220px}.script-body>textarea:focus,.script-block-editor textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-content{color:#405068;font-size:15px;line-height:1.75}.script-content[data-state="candidate"]{padding:12px 14px;border-radius:8px;background:#f7f7ff}.script-modules,.script-block-editor{display:grid}.script-module,.script-block-editor>section{padding:0 0 30px;margin:0 0 30px;border-bottom:1px solid #e8ecf2}.script-module:last-child,.script-block-editor>section:last-child{padding-bottom:0;margin-bottom:0;border-bottom:0}.script-module>header,.script-block-editor>section>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}.script-module>header div,.script-block-editor>section>header div{display:grid;gap:4px}.script-module h5,.script-block-editor h5{margin:0;color:#172033;font-size:15px}.script-module header span,.script-block-editor header span{color:#6366f1;font-size:14px;font-weight:800}.script-module header small,.script-block-editor header small{flex:none;color:#7a8699;font-size:14px}.script-module{color:#405068;font-size:15px;line-height:1.75}.script-block-waiting{min-height:44px;display:flex;align-items:center;gap:8px;color:#6366f1;font-size:14px}.script-empty{min-height:260px;display:grid;place-items:center;color:#7a8699;font-size:14px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.script-generation-progress__actions{display:flex;align-items:center;gap:10px}.script-generation-progress__actions button{min-height:28px;padding:0 10px;border:1px solid #d7ddea;border-radius:7px;color:#526077;background:#fff;font-size:14px;font-weight:750;cursor:pointer}.script-generation-progress__actions button:hover{color:#3730a3;border-color:#b9b9f4;background:#f7f7ff}.script-generation-progress[data-status="cancelled"]>i span{background:#e08a2e}
.script-document{position:relative}
.script-document>:deep(.app-error-notice){margin:12px 28px 0}
.candidate-canvas-notice{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 28px;border-bottom:1px solid #d9ddf5;color:#4338ca;background:#f5f5ff}.candidate-canvas-notice>div{min-width:0;display:flex;align-items:center;gap:9px}.candidate-canvas-notice>div>span{display:grid;gap:2px}.candidate-canvas-notice strong{font-size:15px}.candidate-canvas-notice small{color:#676aa0;font-size:11px}.candidate-canvas-notice nav{flex:none;display:flex;align-items:center;gap:6px}.candidate-canvas-notice button{min-height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d0d1ee;border-radius:7px;color:#4f55a9;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.candidate-canvas-notice button.primary{border-color:#5148dc;color:#fff;background:#5148dc}.candidate-canvas-notice button:hover:not(:disabled){border-color:#9692e8;color:#4338ca;background:#f8f7ff}.candidate-canvas-notice button.primary:hover:not(:disabled){border-color:#433bc4;color:#fff;background:#433bc4}.candidate-canvas-notice button:focus-visible{outline:3px solid rgba(91,84,232,.22);outline-offset:2px}.candidate-canvas-notice button:disabled{opacity:.5;cursor:not-allowed}
.script-status-notice{display:grid;gap:3px;margin:14px 28px 0;padding:11px 13px;border:1px solid #d8dff0;border-radius:8px;color:#4b5870;background:#f8faff;font-size:14px;line-height:1.55}.script-status-notice strong{color:#29334a;font-size:14px}.script-status-notice[data-state="suggestion"]{border-color:#efd2a8;background:#fff9ef}.script-status-notice[data-state="suggestion"] strong{color:#9a4c0c}.script-status-notice[data-state="ready"]{border-color:#cce4d5;background:#f5fbf7}.script-status-notice[data-state="ready"] strong{color:#276749}
.script-continuous{width:min(100%,940px);margin:0 auto}.script-continuous .script-body{min-height:0;scroll-margin-top:72px;border-bottom:1px solid #e4e8ef}.script-continuous .script-body:last-child{border-bottom:0}.script-continuous .script-body.active>header h4{color:#3730a3}.script-continuous .script-body.active>header span{color:#4f46e5}.script-continuous[data-state="partial"] .script-body:last-child{min-height:280px}
@media(max-width:760px){.script-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.script-actions{width:100%;justify-content:flex-end}.script-ai,.script-generate{grid-template-columns:1fr;padding-inline:18px}.script-ai button,.script-generate button{min-height:38px}.script-tabs{padding-inline:18px}.script-body{padding:22px 18px}.candidate-canvas-notice{align-items:flex-start;flex-direction:column;padding-inline:18px}.candidate-canvas-notice nav{width:100%;justify-content:flex-end;flex-wrap:wrap}}
.script-content[data-state="candidate"]{border:1px solid #c8c7f2;background:#f8f8ff;outline:0}.script-content[data-state="candidate"]:focus{box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-tabs button:disabled{opacity:.45;cursor:not-allowed}
.script-ai-change-bubble{width:max-content;max-width:100%;display:flex;align-items:center;gap:6px;margin:-3px 0 14px;padding:5px 9px;border:1px solid #c8c7f2;border-radius:999px;color:#4338ca;background:#fff;box-shadow:0 4px 12px rgba(67,56,202,.08);font-size:14px}.script-ai-change-bubble strong{font-size:14px}.script-ai-change-bubble span{overflow:hidden;color:#667085;text-overflow:ellipsis;white-space:nowrap}
.script-document,.script-generation-panel{background:var(--teacher-component-surface,#fff)}
.script-ai{background:var(--teacher-component-tint,#f7f7ff)}
.script-actions button:hover,.script-generate textarea:disabled{background:var(--teacher-component-tint,#f7f7ff)}
.script-streamed-block .stream-caret{width:2px;height:17px;display:inline-block;margin-left:3px;vertical-align:-2px;background:#5b57e8;animation:blink .8s steps(1) infinite}@keyframes blink{50%{opacity:0}}
.script-source-review{display:grid;gap:22px;padding:24px 28px 30px}.script-source-steps{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin:0;padding:3px;border:1px solid #dfe4ed;border-radius:11px;background:#eef1f6;list-style:none}.script-source-steps li{min-width:0;min-height:48px;display:grid;grid-template-columns:24px minmax(0,1fr);align-items:center;gap:8px;padding:5px 10px;border-radius:8px;color:#69768a}.script-source-steps li>span{width:22px;height:22px;display:grid;place-items:center;border:1px solid #cbd3df;border-radius:50%;font-size:13px;font-weight:800}.script-source-steps li>div{min-width:0;display:grid;gap:1px}.script-source-steps strong{overflow:hidden;font-size:14px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.script-source-steps small{overflow:hidden;color:#7c8899;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.script-source-steps li.active{color:#312e81;background:#fff;box-shadow:0 2px 8px rgba(30,41,59,.08)}.script-source-steps li.active>span{border-color:#6965d8;color:#fff;background:#6965d8}.script-source-review__heading{display:flex;align-items:center;justify-content:space-between;gap:24px}.script-source-review__heading>div{min-width:0;display:grid;gap:5px}.script-source-review__heading strong{color:#263147;font-size:18px;font-weight:760}.script-source-review__heading span{color:#68768b;font-size:15px;line-height:1.5}.script-source-review__heading>.script-source-review__blocked{grid-template-columns:22px minmax(0,1fr);align-items:start;gap:10px}.script-source-review__blocked>svg{margin-top:2px;color:#b56a18}.script-source-review__blocked>div{min-width:0;display:grid;gap:4px}.script-source-review__blocked strong{color:#7a410f;font-size:19px}.script-source-review__blocked span{color:#8a561f}.script-source-review__heading button{min-height:42px;flex:none;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 18px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:14px;font-weight:750;cursor:pointer}.script-source-review__heading button:hover:not(:disabled){background:#4338ca}.script-source-review__heading button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-source-review__heading button:disabled{opacity:.45;cursor:not-allowed}.script-source-blocks{display:grid;gap:0;margin:0;padding:0;border-top:1px solid #e8ecf2;list-style:none}.script-source-blocks li{min-height:72px;display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:start;gap:12px;padding:14px 0;border-bottom:1px solid #e8ecf2}.script-source-blocks>li>span{padding-top:2px;color:#817dcf;font-size:14px;font-weight:800;font-variant-numeric:tabular-nums}.script-source-blocks li>div{min-width:0;display:grid;gap:3px}.script-source-blocks strong{color:#303b50;font-size:15px;font-weight:720}.script-source-blocks small{color:#68768b;font-size:14px}.script-source-blocks p{max-width:75ch;margin:2px 0 0;color:#566277;font-size:15px;line-height:1.55}.script-source-blocks em{padding-top:2px;color:#68768b;font-size:14px;font-style:normal;white-space:nowrap}.script-source-empty{margin:0;padding:18px 0;border-top:1px solid #e8ecf2;color:#68768b;font-size:15px}
</style>
