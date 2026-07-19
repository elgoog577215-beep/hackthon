<template>
  <div v-if="blocks.length" class="course-block-stream">
    <template v-for="item in streamItems" :key="item.block.block_revision_id || item.block.block_id">
      <article
        :id="`course-block-${item.block.block_id}`"
        class="course-content-block"
        :data-content-block-id="item.block.block_id"
        :data-content-block-revision-id="item.block.block_revision_id"
        :data-content-block-type="item.block.type"
        :data-content-block-kind="String(item.block.metadata?.kind || '')"
        :class="{ 'can-improve-formal': canImproveBlock(item.block.block_id) }"
      >
        <header v-if="item.block.title" class="block-heading">
          <span>{{ blockLabel(item.block.type) }}</span>
          <h4>{{ item.block.title }}</h4>
        </header>
        <button
          v-if="canImproveBlock(item.block.block_id)"
          type="button"
          class="block-formal-improvement"
          :title="t('courseWorkspace.personalization.open', '调整这段')"
          :aria-label="t('courseWorkspace.personalization.open', '调整这段')"
          @click="requestBlockImprovement(item.block.block_id)"
        >
          <PencilLine :size="13" />
          <span>{{ t('courseWorkspace.personalization.open', '调整这段') }}</span>
        </button>
        <CourseEvolutionContentBlock
          v-if="item.block.metadata?.course_evolution"
          :block-id="item.block.block_id"
          :node-id="node.node_id"
          :kind="String(item.block.metadata?.kind || '')"
          :content="item.block.content || ''"
          :metadata="item.block.metadata"
          :search-words="searchWords"
          @start-practice="emit('startPractice', $event)"
        />
        <FeedbackReviewBlock
          v-else-if="item.block.type === 'feedback'"
          :content="item.block.content || ''"
          :structure="item.block.metadata?.feedback_structure"
          :search-words="searchWords"
        />
        <MarkdownRenderer v-else :content="item.block.content || ''" :search-words="searchWords" />
        <InlineCourseBlockAI
          v-if="!isCanonicalBlock(item.block.block_id)"
          :node="node"
          :block="item.block"
          :active="activeBlockId === item.block.block_id"
          :regeneration-request="regenerationRequests[item.block.block_id]"
          @activate="activeBlockId = $event"
          @record-persisted="liveRecordIds.add($event)"
          @record-released="liveRecordIds.delete($event)"
        />
      </article>
      <InlineLearningRecordBlock
        v-for="record in item.records"
        :key="record.id"
        :note="record"
        @open="emit('openRecord', $event)"
        @regenerate="regenerateAiRecord"
        @delete="deleteAiRecord"
      />
    </template>
    <span v-if="isStreaming" class="stream-cursor"></span>
  </div>
  <template v-else>
    <MarkdownDocumentEditor
      :node="node"
      :content="content"
      :search-words="searchWords"
      :is-streaming="isStreaming"
    />
    <div v-if="projectableRecords.length" class="legacy-inline-records">
      <InlineLearningRecordBlock
        v-for="record in projectableRecords"
        :key="record.id"
        :note="record"
        @open="emit('openRecord', $event)"
        @regenerate="regenerateAiRecord"
        @delete="deleteAiRecord"
      />
    </div>
  </template>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { PencilLine } from 'lucide-vue-next'
import InlineCourseBlockAI from './InlineCourseBlockAI.vue'
import InlineLearningRecordBlock from './InlineLearningRecordBlock.vue'
import CourseEvolutionContentBlock from './CourseEvolutionContentBlock.vue'
import FeedbackReviewBlock from './FeedbackReviewBlock.vue'
import MarkdownDocumentEditor from './MarkdownDocumentEditor.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import type { ContentBlock, CourseBlockEditTarget, Node, Note } from '../stores/types'
import { useNoteStore } from '../stores/notes'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  node: Node
  content: string
  records?: Note[]
  searchWords?: string[]
  isStreaming?: boolean
  canImproveBlocks?: boolean
}>(), { records: () => [], canImproveBlocks: false })
const emit = defineEmits<{
  openRecord: [payload: { note: Note; x: number; y: number }]
  improveBlock: [payload: CourseBlockEditTarget]
  startPractice: [taskRevisionId: string]
}>()
const activeBlockId = ref('')
const noteStore = useNoteStore()
const liveRecordIds = reactive(new Set<string>())
const regenerationRequests = reactive<Record<string, { token: number; prompt: string; action?: 'explain' | 'example' | 'simplify' | 'ask' }>>({})
const blocks = computed(() => (props.node.course_blocks?.length
  ? props.node.course_blocks.map(block => ({
      block_id: block.block_id,
      parent_block_id: block.parent_group_id,
      type: block.role,
      title: String(block.payload.title || ''),
      content: String(block.payload.markdown || block.payload.text || ''),
      summary: String(block.payload.summary || ''),
      order: block.position,
      status: block.status === 'draft' ? 'draft' : 'final',
      metadata: {
        kind: block.kind,
        role: block.role,
        feedback_structure: block.payload.feedback_structure,
        course_evolution: block.payload.course_evolution,
        animation_spec: block.payload.animation_spec,
        practice_task_id: block.payload.practice_task_id,
        practice_intent: block.payload.practice_intent,
      },
      block_revision_id: block.internal_revision,
    } as ContentBlock))
  : [...(props.node.content_blocks || [])])
  .filter(block => block && (String(block.content || '').trim() || block.status === 'draft'))
  .sort((left, right) => (left.order || 0) - (right.order || 0)))
const projectableRecords = computed(() => props.records.filter(record => (
  record.sourceType !== 'format'
  && record.sourceType !== 'wrong'
  && record.migrationStatus !== 'needs_confirmation'
  && record.migrationStatus !== 'orphaned'
  && !liveRecordIds.has(record.id)
)))
const streamItems = computed(() => {
  const items = blocks.value.map(block => ({ block, records: [] as Note[] }))
  for (const record of projectableRecords.value) {
    const anchorBlockId = String(record.anchor?.block_id || '')
    let target = anchorBlockId ? items.find(item => item.block.block_id === anchorBlockId) : undefined
    if (!target && record.quote) {
      const normalizedQuote = record.quote.replace(/\s+/g, ' ').trim()
      const candidates = items.filter(item => item.block.content.replace(/\s+/g, ' ').includes(normalizedQuote))
      if (candidates.length === 1) target = candidates[0]
    }
    if (target) target.records.push(record)
  }
  return items
})

function blockLabel(type: ContentBlock['type'] | string) {
  return t(`courseBlocks.${type}`, ({
    intro: '引入', orientation: '引入', prerequisite: '前置', objective: '任务', concept: '概念',
    reasoning: '推理', example: '例子', counterexample: '辨析', application: '应用', activity: '行动',
    feedback: '反馈', exercise: '练习', checkpoint: '检查', misconception: '易错点', remediation: '补救',
    summary: '小结', transfer: '迁移',
  } as Record<string, string>)[type] || t('courseBlocks.content', '内容'))
}

function canImproveBlock(blockId: string) {
  return props.canImproveBlocks && isCanonicalBlock(blockId)
}

function isCanonicalBlock(blockId: string) {
  return Boolean(props.node.course_blocks?.some(block => block.block_id === blockId))
}

function requestBlockImprovement(blockId: string) {
  const block = props.node.course_blocks?.find(item => item.block_id === blockId)
  if (!block) return
  emit('improveBlock', {
    nodeId: props.node.node_id,
    nodeName: props.node.node_name,
    block,
  })
}

function regenerateAiRecord(note: Note) {
  const blockId = String(note.anchor?.block_id || '')
  const prompt = String(note.metadata?.ai_prompt || '').trim()
  if (!blockId || !prompt) return
  const action = String(note.metadata?.inline_ai_action || 'ask')
  regenerationRequests[blockId] = {
    token: (regenerationRequests[blockId]?.token || 0) + 1,
    prompt,
    action: ['explain', 'example', 'simplify', 'ask'].includes(action)
      ? action as 'explain' | 'example' | 'simplify' | 'ask'
      : 'ask',
  }
  activeBlockId.value = blockId
}

async function deleteAiRecord(note: Note) {
  liveRecordIds.delete(note.id)
  await noteStore.deleteNote(note.id)
}
</script>

<style scoped>
.course-block-stream { display:grid; gap:30px; }
.legacy-inline-records { display:grid; gap:12px; margin-top:24px; }
.course-content-block { --block-accent:#6366f1; --block-soft:#eef2ff; position:relative; min-width:0; scroll-margin-top:92px; }
.course-content-block + .course-content-block { padding-top:2px; border-top:0; }
.block-heading { display:flex; align-items:center; gap:10px; margin-bottom:14px; padding-right:34px; }
.course-content-block.can-improve-formal .block-heading { padding-right:120px; }
.block-heading span { flex:0 0 auto; display:inline-flex; align-items:center; min-height:25px; padding:3px 8px; border:1px solid color-mix(in srgb,var(--block-accent) 18%,white); border-radius:8px; color:var(--block-accent); background:var(--block-soft); font-size:11px; font-weight:800; line-height:1; }
.block-heading h4 { margin:0; color:var(--lz-text-strong); font-size:18px; font-weight:750; line-height:1.35; }
.block-formal-improvement { position:absolute; top:-2px; right:0; z-index:3; min-height:29px; display:inline-flex; align-items:center; gap:5px; padding:0 8px; border:1px solid rgba(203,213,225,.7); border-radius:8px; color:#1e293b; background:rgba(255,255,255,.9); font-size:10px; opacity:.68; pointer-events:auto; cursor:pointer; transition:opacity .16s ease,color .16s ease,border-color .16s ease,background .16s ease,transform .16s ease; }
.block-formal-improvement:hover,.block-formal-improvement:focus-visible,.course-content-block:hover > .block-formal-improvement { opacity:1; pointer-events:auto; color:var(--lz-text-secondary); border-color:#cbd5e1; background:#fff; outline:none; transform:translateY(-1px); }
.course-content-block[data-content-block-type="intro"],
.course-content-block[data-content-block-type="orientation"] { --block-accent:#7c3aed; --block-soft:#f5f3ff; }
.course-content-block[data-content-block-type="prerequisite"] { --block-accent:#475569; --block-soft:#f8fafc; }
.course-content-block[data-content-block-type="objective"] { --block-accent:#4f46e5; --block-soft:#eef2ff; }
.course-content-block[data-content-block-type="concept"] { --block-accent:#2563eb; --block-soft:#eff6ff; }
.course-content-block[data-content-block-type="reasoning"] { --block-accent:#0f766e; --block-soft:#f0fdfa; }
.course-content-block[data-content-block-type="example"] { --block-accent:#b45309; --block-soft:#fffbeb; }
.course-content-block[data-content-block-type="counterexample"],
.course-content-block[data-content-block-type="misconception"] { --block-accent:#b91c1c; --block-soft:#fef2f2; }
.course-content-block[data-content-block-type="application"] { --block-accent:#0e7490; --block-soft:#ecfeff; }
.course-content-block[data-content-block-type="activity"],
.course-content-block[data-content-block-type="exercise"],
.course-content-block[data-content-block-type="checkpoint"] { --block-accent:#be185d; --block-soft:#fdf2f8; }
.course-content-block[data-content-block-type="feedback"] { --block-accent:#047857; --block-soft:#ecfdf5; }
.course-content-block[data-content-block-type="remediation"] { --block-accent:#c2410c; --block-soft:#fff7ed; }
.course-content-block[data-content-block-type="transfer"] { --block-accent:#6d28d9; --block-soft:#f5f3ff; }
.course-content-block[data-content-block-type="summary"] { --block-accent:#4338ca; --block-soft:#eef2ff; margin-top:4px; }
.course-content-block[data-content-block-type="summary"] .block-heading { margin-bottom:16px; }
.course-content-block[data-content-block-type="summary"] .block-heading span { min-height:29px; padding:4px 10px; border-radius:9px; font-size:13px; }
.course-content-block[data-content-block-type="summary"] .block-heading h4 { font-size:21px; font-weight:800; }
.course-content-block :deep(hr) { display:none; }
.stream-cursor { display: inline-block; width: 2px; height: 18px; background: var(--lz-brand); animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
@media (max-width:880px) {
  .course-content-block.can-improve-formal .block-heading { padding-right:38px; }
  .block-formal-improvement { width:30px; padding:0; justify-content:center; opacity:.68; pointer-events:auto; }
  .block-formal-improvement span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
}
</style>
