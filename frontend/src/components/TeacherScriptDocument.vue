<template>
  <section class="script-document">
    <header class="script-header">
      <div class="script-title">
        <div class="script-kicker">
          <span>{{ tr('courseWorkbench.scriptDocument.title') }}</span>
          <i :data-state="documentState">{{ documentStateLabel }}</i>
        </div>
        <h3>{{ lesson.title }}</h3>
        <p>{{ sectionCountLabel }}</p>
      </div>
      <div class="script-actions">
        <template v-if="pendingCandidate">
          <button type="button" :disabled="aiBusy" @click="discardCandidate">
            <X :size="15" />{{ tr('courseWorkbench.scriptDocument.discardAi') }}
          </button>
          <button class="resolved-action" type="button" :disabled="aiBusy" @click="applyCandidate">
            <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ aiBusy ? tr('courseWorkbench.scriptDocument.applyingAi') : tr('courseWorkbench.scriptDocument.applyAi') }}
          </button>
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
          <button type="button" :disabled="!lesson.script.ready || !selectedNode || aiBusy" @click="aiOpen = !aiOpen">
            <Sparkles :size="15" />{{ tr('courseWorkbench.scriptDocument.aiImprove') }}
          </button>
          <button type="button" :disabled="!lesson.script.ready || !scriptSections.length" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.scriptDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <form v-if="aiOpen && !pendingCandidate && !editing" class="script-ai" @submit.prevent="createAiCandidate">
      <textarea
        v-model="aiInstruction"
        rows="2"
        :placeholder="tr('courseWorkbench.scriptDocument.aiPlaceholder')"
        :aria-label="tr('courseWorkbench.scriptDocument.aiImprove')"
      />
      <button type="submit" :disabled="aiBusy || !aiInstruction.trim() || !selectedNode">
        <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
        <Sparkles v-else :size="15" />
        {{ aiBusy ? tr('courseWorkbench.scriptDocument.aiGenerating') : tr('courseWorkbench.scriptDocument.generateAi') }}
      </button>
    </form>

    <p v-if="saveError || aiError || generationError || confirmError" class="script-error" role="alert">
      {{ saveError || aiError || generationError || confirmError }}
    </p>

    <form v-if="!lesson.script.ready" class="script-generate" @submit.prevent="requestGeneration">
      <textarea
        v-model="generationRequirement"
        rows="4"
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
        {{ generating
          ? tr('courseWorkbench.scriptDocument.generating')
          : tr('courseWorkbench.scriptDocument.generate') }}
      </button>
    </form>

    <nav v-else-if="scriptSections.length > 1" class="script-tabs" :aria-label="tr('courseWorkbench.scriptDocument.sectionNavigation')">
      <button
        v-for="(node, index) in scriptSections"
        :key="node.section_node_id"
        type="button"
        :class="{ active: selectedNodeId === node.section_node_id }"
        @click="selectedNodeId = node.section_node_id"
      >
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        {{ node.title }}
      </button>
    </nav>

    <article v-if="lesson.script.ready && selectedNode" class="script-body">
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
      <div v-else-if="pendingCandidate && visibleContent" class="script-content" data-state="candidate">
        <MarkdownRenderer :content="visibleContent" />
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
      </div>
      <div v-else-if="visibleContent" class="script-content" data-state="current">
        <MarkdownRenderer :content="visibleContent" />
      </div>
      <div v-else class="script-empty">{{ tr('courseWorkbench.scriptPending') }}</div>
    </article>

    <footer v-if="lesson.script.ready && !pendingCandidate && !editing" class="script-footer">
      <span v-if="confirmed" class="script-saved"><Check :size="15" />{{ tr('courseWorkbench.scriptDocument.confirmed') }}</span>
      <span v-else />
      <button
        type="button"
        :disabled="confirming || !lesson.script.ready"
        :title="!lesson.script.ready ? tr('courseWorkbench.scriptDocument.incomplete') : ''"
        @click="continueWorkflow"
      >
        <LoaderCircle v-if="confirming" :size="15" class="spin" />
        <ArrowRight v-else :size="15" />
        {{ confirming
          ? tr('courseWorkbench.scriptDocument.confirming')
          : confirmed
            ? tr('courseWorkbench.scriptDocument.next')
            : tr('courseWorkbench.scriptDocument.confirmAndContinue') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ArrowRight, Check, LoaderCircle, Pencil, Sparkles, X } from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { t } from '../shared/i18n'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import type { TeacherLessonProjection, TeacherLessonScriptState } from '../stores/teacherLessonAuthoring'

const props = withDefaults(defineProps<{
  courseId: string
  lesson: TeacherLessonProjection
  confirmed?: boolean
  confirming?: boolean
  confirmError?: string
  generating?: boolean
  generationError?: string
  canGenerate?: boolean
}>(), {
  confirmed: false,
  confirming: false,
  confirmError: '',
  generating: false,
  generationError: '',
  canGenerate: false,
})

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'next'): void
  (event: 'saved'): void
  (event: 'generate', requirement: string): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
const selectedNodeId = ref('')
const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const drafts = reactive<Record<string, string>>({})
const blockDrafts = reactive<Record<string, string>>({})
const aiOpen = ref(false)
const aiInstruction = ref('')
const aiBusy = ref(false)
const aiError = ref('')
const pendingCandidate = ref<{ nodeId: string; content: string } | null>(null)
const generationRequirement = ref('')

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.scriptDocument.title': '课程讲稿',
  'courseWorkbench.scriptDocument.sectionCount': '{count} 个小节',
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
  'courseWorkbench.scriptDocument.confirmed': '讲稿已确认',
  'courseWorkbench.scriptDocument.confirming': '正在确认…',
  'courseWorkbench.scriptDocument.confirmAndContinue': '确认讲稿，进入 PPT',
  'courseWorkbench.scriptDocument.next': '进入 PPT',
  'courseWorkbench.scriptDocument.incomplete': '请先补全本讲所有小节内容',
  'courseWorkbench.scriptDocument.generationRequirement': '讲稿生成要求',
  'courseWorkbench.scriptDocument.generationPlaceholder': '例如：增加一个贴近学生的课堂案例，保留教案时间安排',
  'courseWorkbench.scriptDocument.generate': '生成本讲讲稿',
  'courseWorkbench.scriptDocument.generating': '正在生成…',
  'courseWorkbench.scriptDocument.planRequired': '请先确认本讲教案',
  'courseWorkbench.scriptDocument.minutes': '分钟',
  'courseWorkbench.scriptPending': '本讲暂时没有可用讲稿。',
}

function tr(key: string): string {
  return t(key, fallbackMessages[key] || key)
}

type ScriptSection = TeacherLessonScriptState['sections'][number]
const scriptSections = computed<ScriptSection[]>(() => props.lesson.script.sections || [])
const selectedNode = computed(() => scriptSections.value.find(node => node.section_node_id === selectedNodeId.value) || scriptSections.value[0] || null)
const selectedNodeIndex = computed(() => Math.max(0, scriptSections.value.indexOf(selectedNode.value as ScriptSection)))
const visibleContent = computed(() => {
  if (!selectedNode.value) return ''
  if (pendingCandidate.value?.nodeId === selectedNode.value.section_node_id) return pendingCandidate.value.content
  return selectedNode.value.content || ''
})
const sectionCountLabel = computed(() => tr('courseWorkbench.scriptDocument.sectionCount').replace('{count}', String(scriptSections.value.length)))
const documentState = computed(() => pendingCandidate.value ? 'candidate' : editing.value ? 'editing' : props.confirmed ? 'confirmed' : 'draft')
const documentStateLabel = computed(() => pendingCandidate.value
  ? tr('courseWorkbench.scriptDocument.aiCandidate')
  : editing.value
    ? tr('courseWorkbench.scriptDocument.editing')
    : props.confirmed
      ? tr('courseWorkbench.scriptDocument.confirmed')
      : tr('courseWorkbench.scriptDocument.pendingReview'))

function continueWorkflow() {
  if (props.confirmed) emit('next')
  else emit('confirm')
}

function requestGeneration() {
  if (!props.generating && props.canGenerate) emit('generate', generationRequirement.value.trim())
}

function beginEditing() {
  scriptSections.value.forEach(node => {
    drafts[node.section_node_id] = node.content || ''
    node.blocks?.forEach(block => { blockDrafts[block.block_id] = block.content || '' })
  })
  aiOpen.value = false
  editing.value = true
  saveError.value = ''
}

function cancelEditing() {
  editing.value = false
  saveError.value = ''
  Object.keys(drafts).forEach(key => { delete drafts[key] })
  Object.keys(blockDrafts).forEach(key => { delete blockDrafts[key] })
}

async function saveDraft() {
  if (saving.value) return
  saving.value = true
  saveError.value = ''
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
    saveError.value = String(error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || tr('courseWorkbench.scriptDocument.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function createAiCandidate() {
  const node = selectedNode.value
  const instruction = aiInstruction.value.trim()
  if (!node || !instruction || aiBusy.value || !node.content.trim()) return
  aiBusy.value = true
  aiError.value = ''
  try {
    const result = await lessonStore.rewriteScriptSection(
      props.courseId,
      props.lesson.lesson_unit_id,
      props.lesson.script.current_revision_id,
      node.section_node_id,
      instruction,
    )
    pendingCandidate.value = { nodeId: node.section_node_id, content: result.replacement_text }
    aiOpen.value = false
  } catch (error: any) {
    aiError.value = String(error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || tr('courseWorkbench.scriptDocument.aiFailed'))
  } finally {
    aiBusy.value = false
  }
}

function discardCandidate() {
  pendingCandidate.value = null
  aiInstruction.value = ''
}

async function applyCandidate() {
  const candidate = pendingCandidate.value
  const node = scriptSections.value.find(item => item.section_node_id === candidate?.nodeId)
  if (!candidate || !node || aiBusy.value) return
  aiBusy.value = true
  aiError.value = ''
  try {
    await lessonStore.saveScriptDraft(
      props.courseId,
      props.lesson.lesson_unit_id,
      props.lesson.script.current_revision_id,
      scriptSections.value.map(item => (
        item.section_node_id === candidate.nodeId
          ? { section_node_id: item.section_node_id, title: item.title, content: candidate.content }
          : item
      )),
    )
    discardCandidate()
    emit('saved')
  } catch (error: any) {
    aiError.value = String(error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || tr('courseWorkbench.scriptDocument.saveFailed'))
  } finally {
    aiBusy.value = false
  }
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
  aiOpen.value = false
  aiInstruction.value = ''
  aiError.value = ''
  generationRequirement.value = ''
  selectedNodeId.value = scriptSections.value[0]?.section_node_id || ''
}, { immediate: true })

watch(scriptSections, sections => {
  if (!sections.some(node => node.section_node_id === selectedNodeId.value)) {
    selectedNodeId.value = sections[0]?.section_node_id || ''
  }
})
</script>

<style scoped>
.script-document{background:#fff}.script-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}.script-title{min-width:0;display:grid;gap:5px}.script-kicker{display:flex;align-items:center;gap:9px;color:#6366f1;font-size:11px;font-weight:800}.script-kicker i{padding:3px 7px;border-radius:999px;color:#92400e;background:#fff7ed;font-style:normal;font-weight:750}.script-kicker i[data-state="confirmed"]{color:#047857;background:#ecfdf5}.script-kicker i[data-state="editing"],.script-kicker i[data-state="candidate"]{color:#4338ca;background:#eef2ff}.script-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}.script-title p{margin:0;color:#7a8699;font-size:12px}.script-actions{flex:none;display:flex;align-items:center;gap:2px}.script-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:12px;font-weight:750;cursor:pointer}.script-actions button:hover{color:#3730a3;background:#f2f3fa}.script-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-actions button:disabled{opacity:.45;cursor:not-allowed}.script-actions .resolved-action{margin-left:4px;border-color:#d7ddea;background:#fff}.script-ai{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;gap:10px;padding:12px 28px;border-bottom:1px solid #e8ecf2;background:#fbfcff}.script-ai textarea{min-height:58px;padding:9px 11px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.5;resize:vertical}.script-ai textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-ai button,.script-footer button,.script-generate button{display:flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.script-ai button:disabled,.script-footer button:disabled,.script-generate button:disabled{opacity:.45;cursor:not-allowed}.script-error{margin:0;padding:10px 28px;color:#b91c1c;background:#fff1f2;font-size:12px}.script-generate{min-height:320px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-content:start;gap:12px;padding:28px}.script-generate textarea{min-height:112px;box-sizing:border-box;padding:13px 14px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:13px;line-height:1.65;resize:vertical}.script-generate textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-generate button{min-height:42px;padding-inline:18px}.script-tabs{display:flex;gap:24px;overflow:auto;padding:0 28px;border-bottom:1px solid #e8ecf2}.script-tabs button{max-width:280px;min-height:48px;display:flex;align-items:center;gap:7px;padding:0;border:0;border-bottom:2px solid transparent;color:#64748b;background:transparent;font-size:12px;white-space:nowrap;cursor:pointer}.script-tabs button span{color:#94a3b8;font-size:10px;font-weight:800}.script-tabs button:hover{color:#3730a3}.script-tabs button.active{border-bottom-color:#5b57e8;color:#3730a3;font-weight:750}.script-tabs button.active span{color:#6366f1}.script-body{min-height:360px;padding:28px}.script-body>header{display:flex;align-items:center;gap:10px;margin-bottom:22px}.script-body>header span{color:#6366f1;font-size:11px;font-weight:850}.script-body>header h4{margin:0;color:#172033;font-size:16px}.script-body>textarea,.script-block-editor textarea{width:100%;box-sizing:border-box;padding:14px 15px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:13px;line-height:1.75;resize:vertical}.script-body>textarea{min-height:520px}.script-block-editor textarea{min-height:220px}.script-body>textarea:focus,.script-block-editor textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.script-content{color:#405068;font-size:13px;line-height:1.75}.script-content[data-state="candidate"]{padding-left:16px;border-left:2px solid #6366f1}.script-modules,.script-block-editor{display:grid}.script-module,.script-block-editor>section{padding:0 0 30px;margin:0 0 30px;border-bottom:1px solid #e8ecf2}.script-module:last-child,.script-block-editor>section:last-child{padding-bottom:0;margin-bottom:0;border-bottom:0}.script-module>header,.script-block-editor>section>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}.script-module>header div,.script-block-editor>section>header div{display:grid;gap:4px}.script-module h5,.script-block-editor h5{margin:0;color:#172033;font-size:15px}.script-module header span,.script-block-editor header span{color:#6366f1;font-size:10px;font-weight:800}.script-module header small,.script-block-editor header small{flex:none;color:#7a8699;font-size:11px}.script-module{color:#405068;font-size:13px;line-height:1.75}.script-empty{min-height:260px;display:grid;place-items:center;color:#7a8699;font-size:13px}.script-footer{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.script-saved{display:flex;align-items:center;gap:7px;color:#047857;font-size:12px;font-weight:700}.script-footer button{min-height:38px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.script-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.script-actions{width:100%;justify-content:flex-end}.script-ai,.script-generate{grid-template-columns:1fr;padding-inline:18px}.script-ai button,.script-generate button{min-height:38px}.script-tabs{padding-inline:18px}.script-body{padding:22px 18px}.script-footer{padding-inline:18px}}
</style>
