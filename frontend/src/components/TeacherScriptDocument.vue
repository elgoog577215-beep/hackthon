<template>
  <section class="script-document">
    <header v-if="!externalToolbar" class="script-header">
      <div class="script-title">
        <h3>{{ lesson.title }}</h3>
      </div>
      <div class="script-actions">
        <template v-if="pendingCandidate">
          <template v-if="!assistantOpen">
            <button type="button" :disabled="aiBusy" @click="resolveAiCandidate(false)">
              <X :size="15" />{{ tr('courseWorkbench.scriptDocument.discardAi') }}
            </button>
            <button class="resolved-action" type="button" :disabled="aiBusy" @click="resolveAiCandidate(true)">
              <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
              <Check v-else :size="15" />
              {{ aiBusy ? tr('courseWorkbench.scriptDocument.applyingAi') : tr('courseWorkbench.scriptDocument.applyAi') }}
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
          <button type="button" :aria-pressed="assistantOpen" :disabled="!lesson.script.ready || !selectedNode || aiBusy" @click="emit('open-ai')">
            <Sparkles :size="15" />{{ tr('courseWorkbench.scriptDocument.aiImprove') }}
          </button>
          <button type="button" :disabled="!lesson.script.ready || !scriptSections.length" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.scriptDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <AppErrorNotice v-if="documentError" :presentation="documentError" compact />

    <aside v-if="scriptStatusNotice" class="script-status-notice" :data-state="scriptStatusNotice.state">
      <strong>{{ scriptStatusNotice.title }}</strong>
      <span>{{ scriptStatusNotice.detail }}</span>
    </aside>

    <section v-if="!lesson.script.ready" class="script-generation-panel" :class="{ 'has-partial': scriptSections.length }">
      <form v-if="showGenerationForm" class="script-generate" @submit.prevent="requestGeneration">
        <textarea
          v-model="generationRequirement"
          rows="4"
          :disabled="generating"
          :placeholder="tr('courseWorkbench.scriptDocument.generationPlaceholder')"
          :aria-label="tr('courseWorkbench.scriptDocument.generationRequirement')"
        />
        <button
          type="submit"
          :disabled="generating || !canGenerate"
          :title="!canGenerate ? tr('courseWorkbench.scriptDocument.planRequired') : ''"
        >
          <LoaderCircle v-if="generating" :size="16" class="spin" />
          <Sparkles v-else :size="16" />
          {{ generationActionLabel }}
        </button>
      </form>
      <div v-if="generationJob" class="script-generation-progress" :data-status="generationJob.status">
        <div>
          <span>{{ generationJob.message }}</span>
          <span class="script-generation-progress__actions">
            <strong>{{ generationJob.completed_blocks || 0 }}/{{ generationJob.total_blocks || 0 }}</strong>
            <button v-if="generating" type="button" @click="emit('cancel-generation')">
              {{ tr('courseWorkbench.scriptDocument.stopGeneration') }}
            </button>
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
        @click="selectedNodeId = node.section_node_id"
      >
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        {{ node.title }}
      </button>
    </nav>

    <slot v-if="externalToolbar" name="toolbar" />

    <article v-if="selectedNode" class="script-body" :data-state="lesson.script.ready ? 'ready' : 'partial'">
      <header>
        <span>{{ String(selectedNodeIndex + 1).padStart(2, '0') }}</span>
        <h4>{{ selectedNode.title }}</h4>
      </header>
      <div v-if="editing && selectedNode.blocks?.length" class="script-block-editor">
        <section v-for="block in selectedNode.blocks" :key="block.block_id">
          <header>
            <div>
              <span>{{ blockRoleLabel(block.role) }}</span>
              <h5>{{ block.title }}</h5>
            </div>
            <small v-if="block.planned_minutes">{{ block.planned_minutes }} {{ tr('courseWorkbench.scriptDocument.minutes') }}</small>
          </header>
          <textarea v-model="blockDrafts[block.block_id]" rows="10" :aria-label="block.title" />
        </section>
      </div>
      <textarea
        v-else-if="editing"
        v-model="drafts[selectedNode.section_node_id]"
        rows="24"
        :aria-label="selectedNode.title"
      />
      <div v-else-if="pendingCandidate && visibleContent" ref="candidateRef" class="script-content" data-state="candidate" tabindex="-1">
        <MarkdownRenderer :key="`candidate-${pendingCandidate.candidate_id || pendingCandidate.section_node_id}`" :content="visibleContent" />
      </div>
      <div v-else-if="selectedNode.blocks?.length" class="script-modules">
        <section v-for="block in selectedNode.blocks" :key="block.block_id" class="script-module">
          <header>
            <div>
              <span>{{ blockRoleLabel(block.role) }}</span>
              <h5>{{ block.title }}</h5>
            </div>
            <small v-if="block.planned_minutes">{{ block.planned_minutes }} {{ tr('courseWorkbench.scriptDocument.minutes') }}</small>
          </header>
          <MarkdownRenderer :content="block.content" />
        </section>
        <div v-if="!lesson.script.ready && generating" class="script-block-waiting">
          <LoaderCircle :size="15" class="spin" />
          {{ generationJob?.current_block_title || tr('courseWorkbench.scriptDocument.waitingForNextBlock') }}
        </div>
      </div>
      <div v-else-if="visibleContent" class="script-content" data-state="current">
        <MarkdownRenderer :content="visibleContent" />
      </div>
      <div v-else class="script-empty">{{ tr('courseWorkbench.scriptPending') }}</div>
    </article>

    <footer v-if="!externalToolbar && lesson.script.ready && !pendingCandidate && !editing && !confirmed" class="script-footer">
      <button
        type="button"
        :disabled="confirming || !lesson.script.ready || lesson.script.publication_eligible === false"
        :title="confirmationBlockReason"
        @click="emit('confirm')"
      >
        <LoaderCircle v-if="confirming" :size="15" class="spin" />
        <Check v-else :size="15" />
        {{ confirming
          ? tr('courseWorkbench.scriptDocument.confirming')
          : tr('courseWorkbench.scriptDocument.confirm') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Check, LoaderCircle, Pencil, Sparkles, X } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { t } from '../shared/i18n'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import type { TeacherLessonJob, TeacherLessonProjection, TeacherLessonScriptCandidate, TeacherLessonScriptState } from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'

const props = withDefaults(defineProps<{
  courseId: string
  lesson: TeacherLessonProjection
  confirmed?: boolean
  confirming?: boolean
  confirmError?: string
  generating?: boolean
  generationJob?: TeacherLessonJob
  generationError?: string
  canGenerate?: boolean
  assistantOpen?: boolean
  materialAssetIds?: string[]
  externalToolbar?: boolean
}>(), {
  confirmed: false,
  confirming: false,
  confirmError: '',
  generating: false,
  generationJob: undefined,
  generationError: '',
  canGenerate: false,
  assistantOpen: false,
  materialAssetIds: () => [],
  externalToolbar: false,
})

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'saved'): void
  (event: 'generate', requirement: string): void
  (event: 'cancel-generation'): void
  (event: 'open-ai'): void
  (event: 'ai-candidate-change', candidate: TeacherLessonScriptCandidate | null): void
  (event: 'ai-resolving', result: { accept: boolean }): void
  (event: 'ai-resolved', result: { accept: boolean }): void
  (event: 'ai-error', message: string): void
  (event: 'ai-scope-change', scope: { id: string; title: string }): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
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
const generationRequirement = ref('')

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
  if (props.confirmError) return toAppError(props.confirmError, {
    title: tr('courseWorkbench.scriptDocument.confirmFailed'),
    fallback: props.confirmError,
  })
  return null
})

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.scriptDocument.edit': '编辑讲稿',
  'courseWorkbench.scriptDocument.editing': '编辑中',
  'courseWorkbench.scriptDocument.cancel': '取消',
  'courseWorkbench.scriptDocument.finishEditing': '完成编辑',
  'courseWorkbench.scriptDocument.saving': '正在保存…',
  'courseWorkbench.scriptDocument.saveFailed': '讲稿保存失败，请重试。',
  'courseWorkbench.scriptDocument.aiImprove': 'AI 优化',
  'courseWorkbench.scriptDocument.aiPlaceholder': '输入你想调整的内容…',
  'courseWorkbench.scriptDocument.generateAi': '生成方案',
  'courseWorkbench.scriptDocument.aiGenerating': '生成中…',
  'courseWorkbench.scriptDocument.aiCandidate': 'AI 方案',
  'courseWorkbench.scriptDocument.discardAi': '放弃',
  'courseWorkbench.scriptDocument.applyAi': '采用',
  'courseWorkbench.scriptDocument.applyingAi': '正在采用…',
  'courseWorkbench.scriptDocument.aiFailed': 'AI 优化失败，请重试。',
  'courseWorkbench.scriptDocument.sectionNavigation': '讲稿小节',
  'courseWorkbench.scriptDocument.pendingReview': '待确认',
  'courseWorkbench.scriptDocument.confirmed': '已确认',
  'courseWorkbench.scriptDocument.confirming': '正在确认…',
  'courseWorkbench.scriptDocument.confirm': '确认本讲讲稿',
  'courseWorkbench.scriptDocument.incomplete': '请先补全本讲所有小节内容',
  'courseWorkbench.scriptDocument.qualityBlocked': '讲稿尚未通过当前质量与来源检查',
  'courseWorkbench.scriptDocument.sourceRecovery': '恢复草稿',
  'courseWorkbench.scriptDocument.sourceTeacherEdit': '教师编辑稿',
  'courseWorkbench.scriptDocument.sourceAiOptimization': 'AI 优化稿',
  'courseWorkbench.scriptDocument.sourceModel': 'AI 生成稿',
  'courseWorkbench.scriptDocument.sourceLegacy': '旧版讲稿',
  'courseWorkbench.scriptDocument.statusCannotConfirm': '尚不能确认',
  'courseWorkbench.scriptDocument.statusCurrentReady': '当前正文可用',
  'courseWorkbench.scriptDocument.statusPassed': '已通过当前检查',
  'courseWorkbench.scriptDocument.statusBlockedDetail': '当前内容尚未通过最新质量与来源检查，请继续编辑或重新生成。',
  'courseWorkbench.scriptDocument.statusPreviousFailureDetail': '最近一次 AI 生成没有完成；当前展示的是已经单独保存并通过检查的正文，不是该次失败任务的输出。',
  'courseWorkbench.scriptDocument.statusPassedDetail': '确认后，这一修订才会成为 PPT 文书与 PPT 的唯一内容上游。',
  'courseWorkbench.scriptDocument.generationRequirement': '讲稿生成要求',
  'courseWorkbench.scriptDocument.generationPlaceholder': '例如：增加一个贴近学生的课堂案例，保留教案时间安排',
  'courseWorkbench.scriptDocument.generate': '生成本讲讲稿',
  'courseWorkbench.scriptDocument.generating': '正在生成…',
  'courseWorkbench.scriptDocument.stopGeneration': '停止',
  'courseWorkbench.scriptDocument.continueGenerating': '继续生成剩余内容',
  'courseWorkbench.scriptDocument.waitingForNextBlock': '正在准备下一个教学块',
  'courseWorkbench.scriptDocument.generateFailed': '讲稿生成失败',
  'courseWorkbench.scriptDocument.confirmFailed': '讲稿确认失败',
  'courseWorkbench.scriptDocument.planRequired': '请先确认本讲教案',
  'courseWorkbench.scriptDocument.minutes': '分钟',
  'courseWorkbench.scriptPending': '本讲暂时没有可用讲稿。',
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
const qualityBlockMessage = computed(() => String(
  props.lesson.script.quality_report?.blocking_issues?.[0]?.message || '',
))
const scriptStatusNotice = computed(() => {
  if (!props.lesson.script.ready) return null
  if (props.lesson.script.publication_eligible === false) {
    return {
      state: 'blocked',
      title: `${sourceLabel.value} · ${tr('courseWorkbench.scriptDocument.statusCannotConfirm')}`,
      detail: qualityBlockMessage.value || tr('courseWorkbench.scriptDocument.statusBlockedDetail'),
    }
  }
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
    title: `${sourceLabel.value} · ${tr('courseWorkbench.scriptDocument.statusPassed')}`,
    detail: tr('courseWorkbench.scriptDocument.statusPassedDetail'),
  }
})
const confirmationBlockReason = computed(() => {
  if (!props.lesson.script.ready) return tr('courseWorkbench.scriptDocument.incomplete')
  if (props.lesson.script.publication_eligible === false) {
    return qualityBlockMessage.value || tr('courseWorkbench.scriptDocument.qualityBlocked')
  }
  return ''
})
const scriptSections = computed<ScriptSection[]>(() => (
  props.lesson.script.ready
    ? props.lesson.script.sections || []
    : props.generationJob?.result_sections || []
))
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
const selectedNode = computed(() => scriptSections.value.find(node => node.section_node_id === selectedNodeId.value) || scriptSections.value[0] || null)
const selectedNodeIndex = computed(() => Math.max(0, scriptSections.value.indexOf(selectedNode.value as ScriptSection)))
const visibleContent = computed(() => {
  if (!selectedNode.value) return ''
  if (pendingCandidate.value?.section_node_id === selectedNode.value.section_node_id) return pendingCandidate.value.replacement_text
  return selectedNode.value.content || ''
})

function requestGeneration() {
  if (!props.generating && props.canGenerate) emit('generate', generationRequirement.value.trim())
}

function beginEditing() {
  scriptSections.value.forEach(node => {
    drafts[node.section_node_id] = node.content || ''
    node.blocks?.forEach(block => { blockDrafts[block.block_id] = block.content || '' })
  })
  editing.value = true
  saveError.value = null
}

function cancelEditing() {
  editing.value = false
  saveError.value = null
  Object.keys(drafts).forEach(key => { delete drafts[key] })
  Object.keys(blockDrafts).forEach(key => { delete blockDrafts[key] })
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
  generationRequirement.value = ''
  selectedNodeId.value = scriptSections.value[0]?.section_node_id || ''
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

watch(() => props.generationJob, job => {
  if (!generationRequirement.value && job?.requirements) {
    generationRequirement.value = job.requirements
  }
}, { immediate: true })

watch(selectedNode, node => emit('ai-scope-change', { id: node?.section_node_id || '', title: node?.title || '' }), { immediate: true })

defineExpose({
  requestAiCandidate,
  resolveAiCandidate,
  focusAiCandidate,
  selectAiScope,
  editing,
  saving,
  aiBusy,
  beginEditing,
  cancelEditing,
  saveDraft,
})
</script>

<style scoped>
.script-document{background:#fff}.script-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}.script-title{min-width:0;display:flex;align-items:center;gap:9px}.script-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}.script-actions{flex:none;display:flex;align-items:center;gap:2px}.script-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:12px;font-weight:750;cursor:pointer}.script-actions button:hover{color:#3730a3;background:#f2f3fa}.script-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-actions button:disabled{opacity:.45;cursor:not-allowed}.script-actions .resolved-action{margin-left:4px;border-color:#d7ddea;background:#fff}.script-ai{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;gap:10px;padding:12px 28px;border-bottom:1px solid #e8ecf2;background:#fbfcff}.script-ai textarea{min-height:58px;padding:9px 11px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.5;resize:vertical}.script-ai textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-ai button,.script-footer button,.script-generate button{display:flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.script-ai button:disabled,.script-footer button:disabled,.script-generate button:disabled{opacity:.45;cursor:not-allowed}.script-generation-panel{border-bottom:1px solid #e8ecf2;background:#fbfcfe}.script-generate{min-height:320px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-content:start;gap:12px;padding:28px}.script-generation-panel.has-partial .script-generate{min-height:auto;padding-bottom:14px}.script-generate textarea{min-height:112px;box-sizing:border-box;padding:13px 14px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:13px;line-height:1.65;resize:vertical}.script-generate textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-generate textarea:disabled{color:#64748b;background:#f7f8fa}.script-generate button{min-height:42px;padding-inline:18px}.script-generation-progress{display:grid;gap:7px;padding:0 28px 18px}.script-generation-progress>div{display:flex;align-items:center;justify-content:space-between;gap:18px;color:#5d6879;font-size:12px}.script-generation-progress strong{color:#4338ca;font-size:11px}.script-generation-progress>i{height:4px;overflow:hidden;border-radius:4px;background:#e6e8f0}.script-generation-progress>i span{height:100%;display:block;border-radius:inherit;background:#5b57e8}.script-generation-progress[data-status="failed"]>i span{background:#e08a2e}.script-tabs{display:flex;gap:24px;overflow:auto;padding:0 28px;border-bottom:1px solid #e8ecf2}.script-tabs button{max-width:280px;min-height:48px;display:flex;align-items:center;gap:7px;padding:0;border:0;border-bottom:2px solid transparent;color:#64748b;background:transparent;font-size:12px;white-space:nowrap;cursor:pointer}.script-tabs button span{color:#94a3b8;font-size:10px;font-weight:800}.script-tabs button:hover{color:#3730a3}.script-tabs button.active{border-bottom-color:#5b57e8;color:#3730a3;font-weight:750}.script-tabs button.active span{color:#6366f1}.script-body{min-height:360px;padding:28px}.script-body[data-state="partial"]{background:#fff}.script-body>header{display:flex;align-items:center;gap:10px;margin-bottom:22px}.script-body>header span{color:#6366f1;font-size:11px;font-weight:850}.script-body>header h4{margin:0;color:#172033;font-size:16px}.script-body>textarea,.script-block-editor textarea{width:100%;box-sizing:border-box;padding:14px 15px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:13px;line-height:1.75;resize:vertical}.script-body>textarea{min-height:520px}.script-block-editor textarea{min-height:220px}.script-body>textarea:focus,.script-block-editor textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-content{color:#405068;font-size:13px;line-height:1.75}.script-content[data-state="candidate"]{padding:12px 14px;border-radius:8px;background:#f7f7ff}.script-modules,.script-block-editor{display:grid}.script-module,.script-block-editor>section{padding:0 0 30px;margin:0 0 30px;border-bottom:1px solid #e8ecf2}.script-module:last-child,.script-block-editor>section:last-child{padding-bottom:0;margin-bottom:0;border-bottom:0}.script-module>header,.script-block-editor>section>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}.script-module>header div,.script-block-editor>section>header div{display:grid;gap:4px}.script-module h5,.script-block-editor h5{margin:0;color:#172033;font-size:15px}.script-module header span,.script-block-editor header span{color:#6366f1;font-size:10px;font-weight:800}.script-module header small,.script-block-editor header small{flex:none;color:#7a8699;font-size:11px}.script-module{color:#405068;font-size:13px;line-height:1.75}.script-block-waiting{min-height:44px;display:flex;align-items:center;gap:8px;color:#6366f1;font-size:12px}.script-empty{min-height:260px;display:grid;place-items:center;color:#7a8699;font-size:13px}.script-footer{min-height:64px;display:flex;align-items:center;justify-content:flex-end;gap:18px;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.script-footer button{min-height:38px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.script-generation-progress__actions{display:flex;align-items:center;gap:10px}.script-generation-progress__actions button{min-height:28px;padding:0 10px;border:1px solid #d7ddea;border-radius:7px;color:#526077;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.script-generation-progress__actions button:hover{color:#3730a3;border-color:#b9b9f4;background:#f7f7ff}.script-generation-progress[data-status="cancelled"]>i span{background:#e08a2e}
.script-document>:deep(.app-error-notice){margin:12px 28px 0}
.script-status-notice{display:grid;gap:3px;margin:14px 28px 0;padding:11px 13px;border:1px solid #d8dff0;border-radius:8px;color:#4b5870;background:#f8faff;font-size:12px;line-height:1.55}.script-status-notice strong{color:#29334a;font-size:12px}.script-status-notice[data-state="blocked"]{border-color:#efd2a8;background:#fff9ef}.script-status-notice[data-state="blocked"] strong{color:#9a4c0c}.script-status-notice[data-state="ready"]{border-color:#cce4d5;background:#f5fbf7}.script-status-notice[data-state="ready"] strong{color:#276749}
@media(max-width:760px){.script-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.script-actions{width:100%;justify-content:flex-end}.script-ai,.script-generate{grid-template-columns:1fr;padding-inline:18px}.script-ai button,.script-generate button{min-height:38px}.script-tabs{padding-inline:18px}.script-body{padding:22px 18px}.script-footer{padding-inline:18px}}
.script-content[data-state="candidate"]{border:1px solid #c8c7f2;background:#f8f8ff;outline:0}.script-content[data-state="candidate"]:focus{box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-tabs button:disabled{opacity:.45;cursor:not-allowed}
.script-document,.script-generation-panel{background:var(--teacher-component-surface,#fff)}
.script-ai,.script-footer{background:var(--teacher-component-tint,#f7f7ff)}
.script-actions button:hover,.script-generate textarea:disabled{background:var(--teacher-component-tint,#f7f7ff)}
</style>
