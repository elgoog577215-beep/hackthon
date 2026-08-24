<template>
  <form class="arrangement-editor" data-testid="lesson-arrangement-editor" @submit.prevent="submit">
    <header class="arrangement-heading">
      <div class="heading-copy">
        <h3>{{ t('courseWorkbench.arrangement.title', '确认本讲怎么组织') }}</h3>
        <div class="arrangement-summary">
          <span>{{ t('courseWorkbench.arrangement.blocks', '教学块') }} {{ draft.blocks.length }}</span>
          <span>{{ t('courseWorkbench.arrangement.totalMinutes', '合计') }} {{ totalMinutes }} {{ t('courseWorkbench.minutes', '分钟') }}</span>
        </div>
      </div>
      <label class="lesson-type-field">
        <span>{{ t('courseWorkbench.arrangement.lessonType', '本讲课型') }}</span>
        <select v-model="draft.lesson_type" data-testid="lesson-type-select">
          <option v-for="option in lessonTypes" :key="option.id" :value="option.id">{{ t(option.labelKey, option.fallback) }}</option>
        </select>
      </label>
    </header>

    <label class="lesson-requirements">
      <span>{{ t('courseWorkbench.form.lessonFocus', '本讲重点') }}</span>
      <textarea
        :value="requirements"
        rows="2"
        :placeholder="t('courseWorkbench.form.lessonFocusPlaceholder', '填写重难点、教学方法或课堂活动要求')"
        @input="updateRequirements"
      />
    </label>

    <div class="block-column-headings" aria-hidden="true">
      <span />
      <div>
        <span>{{ t('courseWorkbench.arrangement.blockName', '环节名称') }}</span>
        <span>{{ t('courseWorkbench.arrangement.section', '归属小节') }}</span>
        <span>{{ t('courseWorkbench.arrangement.minutes', '分钟') }}</span>
      </div>
      <span />
    </div>
    <ol class="block-list">
      <li v-for="(block, index) in draft.blocks" :key="block.block_id">
        <span class="block-index">{{ String(index + 1).padStart(2, '0') }}</span>
        <div class="block-fields">
          <div class="block-primary-row">
            <label>
              <span class="sr-only">{{ t('courseWorkbench.arrangement.blockName', '环节名称') }}</span>
              <input v-model.trim="block.name" required />
            </label>
            <label>
              <span class="sr-only">{{ t('courseWorkbench.arrangement.section', '归属小节') }}</span>
              <select v-model="block.section_node_id" required @change="syncSectionTitle(block)">
                <option v-for="section in sections" :key="section.section_node_id" :value="section.section_node_id">{{ section.title }}</option>
              </select>
            </label>
            <label class="minute-field">
              <span class="sr-only">{{ t('courseWorkbench.arrangement.minutes', '分钟') }}</span>
              <input v-model.number="block.planned_minutes" type="number" min="1" max="240" required />
            </label>
          </div>
          <label class="block-summary-field">
            <span class="sr-only">{{ t('courseWorkbench.arrangement.summary', '这一环节做什么') }}</span>
            <textarea v-model.trim="block.content_summary" rows="1" :placeholder="t('courseWorkbench.arrangement.summaryPlaceholder', '简要说明教师怎样组织、学生形成什么产出')" />
          </label>
        </div>
        <div class="block-actions">
          <button type="button" :title="t('courseWorkbench.arrangement.moveUp', '上移')" :disabled="index === 0" @click="move(index, -1)"><ChevronUp :size="15" /></button>
          <button type="button" :title="t('courseWorkbench.arrangement.moveDown', '下移')" :disabled="index === draft.blocks.length - 1" @click="move(index, 1)"><ChevronDown :size="15" /></button>
          <button class="danger" type="button" :title="t('courseWorkbench.arrangement.remove', '删除')" :disabled="draft.blocks.length <= 1" @click="remove(index)"><Trash2 :size="15" /></button>
        </div>
      </li>
    </ol>

    <button class="add-block" type="button" @click="addBlock"><Plus :size="15" />{{ t('courseWorkbench.arrangement.add', '添加教学块') }}</button>
    <p v-if="error" class="arrangement-error" role="alert">{{ error }}</p>
    <footer>
      <span>{{ t('courseWorkbench.arrangement.hint', '确认后，AI 按这个顺序生成完整教案') }}</span>
      <button class="primary" type="submit" :disabled="busy || !valid">
        <LoaderCircle v-if="busy" :size="16" class="spin" />
        <Sparkles v-else :size="16" />
        {{ error ? t('courseWorkbench.retryLessonPlan', '重新生成本讲教案') : t('courseWorkbench.arrangement.confirmAndGenerate', '确认编排并生成教案') }}
      </button>
    </footer>
  </form>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ChevronDown, ChevronUp, LoaderCircle, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { TeacherLessonArrangement, TeacherLessonArrangementBlock } from '../stores/teacherLessonAuthoring'

const props = defineProps<{
  arrangement?: TeacherLessonArrangement
  sections: Array<{ section_node_id: string; title: string }>
  busy?: boolean
  error?: string
  requirements?: string
}>()
const emit = defineEmits<{
  confirm: [value: Pick<TeacherLessonArrangement, 'lesson_type' | 'blocks'>]
  'update:requirements': [value: string]
}>()

const lessonTypes: Array<{ id: TeacherLessonArrangement['lesson_type']; labelKey: string; fallback: string }> = [
  { id: 'theory', labelKey: 'courseWorkbench.arrangement.lessonTypes.theory', fallback: '理论讲授' },
  { id: 'practice', labelKey: 'courseWorkbench.arrangement.lessonTypes.practice', fallback: '实践操作' },
  { id: 'theory_practice', labelKey: 'courseWorkbench.arrangement.lessonTypes.theoryPractice', fallback: '理论与实践' },
  { id: 'case_discussion', labelKey: 'courseWorkbench.arrangement.lessonTypes.caseDiscussion', fallback: '案例研讨' },
  { id: 'experiment_inquiry', labelKey: 'courseWorkbench.arrangement.lessonTypes.experimentInquiry', fallback: '实验探究' },
  { id: 'project_workshop', labelKey: 'courseWorkbench.arrangement.lessonTypes.projectWorkshop', fallback: '项目工作坊' },
  { id: 'review_assessment', labelKey: 'courseWorkbench.arrangement.lessonTypes.reviewAssessment', fallback: '复习测评' },
]

const draft = reactive<Pick<TeacherLessonArrangement, 'lesson_type' | 'blocks'>>({
  lesson_type: 'theory',
  blocks: [],
})

function cloneBlocks(value: TeacherLessonArrangementBlock[]) {
  return JSON.parse(JSON.stringify(value || [])) as TeacherLessonArrangementBlock[]
}

function reset() {
  draft.lesson_type = props.arrangement?.lesson_type || 'theory'
  draft.blocks = cloneBlocks(props.arrangement?.blocks || [])
}

watch(() => props.arrangement, reset, { immediate: true, deep: true })

const totalMinutes = computed(() => draft.blocks.reduce((sum, item) => sum + Math.max(0, Number(item.planned_minutes) || 0), 0))
const valid = computed(() => Boolean(
  draft.blocks.length
  && draft.blocks.every(item => item.name.trim() && item.section_node_id && Number(item.planned_minutes) > 0)
  && props.sections.every(section => draft.blocks.some(item => item.section_node_id === section.section_node_id)),
))

function syncSectionTitle(block: TeacherLessonArrangementBlock) {
  block.section_title = props.sections.find(item => item.section_node_id === block.section_node_id)?.title || ''
}

function move(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= draft.blocks.length) return
  const next = [...draft.blocks]
  const [item] = next.splice(index, 1)
  if (!item) return
  next.splice(target, 0, item)
  draft.blocks = next
}

function remove(index: number) {
  if (draft.blocks.length <= 1) return
  draft.blocks = draft.blocks.filter((_item, itemIndex) => itemIndex !== index)
}

function addBlock() {
  const section = props.sections[0]
  const sequence = Date.now().toString(36)
  draft.blocks = [...draft.blocks, {
    block_id: `teacher-block-${sequence}`,
    module_id: `teacher_custom_${sequence}`,
    section_node_id: section?.section_node_id || '',
    section_title: section?.title || '',
    name: '新教学环节',
    role: 'activity',
    purpose: '',
    content_summary: '',
    planned_minutes: 5,
    teacher_activity: '',
    student_activity: '',
    expected_output: '',
    required: true,
  }]
}

function updateRequirements(event: Event) {
  emit('update:requirements', (event.target as HTMLTextAreaElement).value)
}

function submit() {
  if (!valid.value || props.busy) return
  emit('confirm', {
    lesson_type: draft.lesson_type,
    blocks: cloneBlocks(draft.blocks),
  })
}
</script>

<style scoped>
.arrangement-editor {
  display:flex;
  flex-direction:column;
  padding:18px 28px 0;
  background:var(--lz-surface);
}
.arrangement-heading { display:flex; align-items:center; justify-content:space-between; gap:24px; padding:0 4px 14px; }
.heading-copy { display:flex; min-width:0; align-items:baseline; gap:18px; }
.arrangement-editor h3 { margin:0; color:var(--lz-text-strong); font-size:20px; letter-spacing:-.02em; }
.arrangement-editor label>span,.arrangement-editor footer>span { color:var(--lz-text-muted); font-size:12px; }
.arrangement-summary { display:flex; gap:14px; color:var(--lz-text-muted); font-size:12px; white-space:nowrap; }
.lesson-type-field { display:flex; flex:0 0 auto; align-items:center; gap:10px; }
select,input,textarea {
  width:100%;
  border:0;
  border-radius:0;
  background:transparent;
  box-shadow:inset 0 -1px 0 var(--lz-border-strong);
  color:var(--lz-text-strong);
  font:inherit;
  transition:background-color .16s ease, box-shadow .16s ease;
}
select,input { min-height:34px; padding:0 8px; }
textarea { min-height:38px; padding:7px 8px; line-height:1.55; resize:vertical; }
select:hover,input:hover,textarea:hover { background:var(--lz-surface-subtle); }
select:focus-visible,input:focus-visible,textarea:focus-visible { outline:2px solid transparent; background:color-mix(in srgb, var(--lz-primary) 4%, var(--lz-surface)); box-shadow:inset 0 -2px 0 var(--lz-primary); }
.lesson-type-field select { width:164px; }
.lesson-requirements { display:grid; grid-template-columns:68px minmax(0,1fr); gap:16px; align-items:start; padding:10px 4px; border-top:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); }
.lesson-requirements>span { padding-top:7px; }
.lesson-requirements textarea { min-height:52px; }
.block-column-headings { display:grid; grid-template-columns:34px minmax(0,1fr) 98px; gap:10px; padding:11px 4px 5px; color:var(--lz-text-muted); font-size:12px; }
.block-column-headings>div { display:grid; grid-template-columns:minmax(180px,1fr) minmax(160px,.72fr) 72px; gap:16px; padding:0 8px; }
.block-list { display:flex; flex-direction:column; margin:0; padding:0; list-style:none; border-top:1px solid var(--lz-border); }
.block-list li { display:grid; grid-template-columns:34px minmax(0,1fr) 98px; gap:10px; align-items:start; padding:9px 4px 10px; border-bottom:1px solid var(--lz-border); }
.block-index { padding-top:9px; color:var(--lz-primary); font-size:12px; font-weight:700; }
.block-fields { display:flex; min-width:0; flex-direction:column; gap:3px; }
.block-primary-row { display:grid; grid-template-columns:minmax(180px,1fr) minmax(160px,.72fr) 72px; gap:16px; }
.block-fields label { display:block; min-width:0; }
.block-primary-row input,.block-primary-row select { font-weight:560; }
.block-summary-field textarea { color:var(--lz-text-muted); font-size:13px; }
.block-actions { display:flex; gap:2px; padding-top:3px; }
.block-actions button { display:grid; width:30px; height:30px; place-items:center; border:0; border-radius:7px; background:transparent; color:var(--lz-text-muted); }
.block-actions button:hover:not(:disabled) { background:var(--lz-surface-subtle); color:var(--lz-primary); }
.block-actions button:focus-visible,.add-block:focus-visible,.primary:focus-visible { outline:2px solid var(--lz-primary); outline-offset:2px; }
.block-actions button.danger:hover:not(:disabled) { color:#c2413a; }
.add-block { align-self:flex-start; display:flex; align-items:center; gap:6px; margin:9px 0; padding:6px 4px; border:0; background:transparent; color:var(--lz-primary); font-weight:650; }
.add-block:hover { text-decoration:underline; text-underline-offset:3px; }
.arrangement-error { margin:0 0 8px; color:#b42318; font-size:13px; }
.arrangement-editor>footer { position:sticky; z-index:2; bottom:0; display:flex; align-items:center; justify-content:space-between; gap:18px; margin:0 -28px; padding:10px 28px; border-top:1px solid var(--lz-border); background:color-mix(in srgb, var(--lz-surface) 94%, transparent); backdrop-filter:blur(10px); }
.primary { display:flex; min-height:38px; align-items:center; justify-content:center; gap:8px; padding:0 16px; border:0; border-radius:9px; background:var(--lz-primary); color:#fff; font-weight:700; }
.sr-only { position:absolute; width:1px; height:1px; margin:-1px; padding:0; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
button:disabled { cursor:not-allowed; opacity:.45; }
.spin { animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

@media (max-width:900px) {
  .arrangement-editor { padding-right:18px; padding-left:18px; }
  .arrangement-heading { align-items:flex-start; }
  .heading-copy { flex-direction:column; gap:5px; }
  .block-column-headings { display:none; }
  .block-list { border-top:1px solid var(--lz-border); }
  .block-list li { grid-template-columns:26px minmax(0,1fr); }
  .block-primary-row { grid-template-columns:1fr; gap:5px; }
  .block-actions { grid-column:2; padding-top:0; }
  .arrangement-editor>footer { margin-right:-18px; margin-left:-18px; padding-right:18px; padding-left:18px; }
}
</style>
