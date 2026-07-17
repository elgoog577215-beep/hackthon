<template>
  <section class="slide-workbench">
    <header class="slide-workbench__toolbar">
      <div>
        <span class="slide-workbench__status" :data-state="error ? 'error' : building ? 'building' : qualityPassed ? 'ready' : 'warning'">
          <LoaderCircle v-if="building" :size="13" class="spinning" />
          <CircleCheck v-else-if="!error && qualityPassed" :size="13" />
          <TriangleAlert v-else :size="13" />
          {{ error ? t('teachingRepresentations.slides.buildFailed', '生成失败') : building ? stageLabel : qualityPassed ? t('teachingRepresentations.slides.qualityPassed', '质量检查通过') : t('teachingRepresentations.slides.qualityReview', '需要检查') }}
        </span>
        <strong>{{ deckTitle }}</strong>
        <small>{{ t('teachingRepresentations.slides.pageCount', '{count} 页').replace('{count}', String(slides.length)) }}</small>
      </div>
      <div class="slide-workbench__commands">
        <button type="button" :disabled="!activeSlide || building" :title="t('teachingRepresentations.slides.askAi', '交给 AI 老师讨论')" @click="askAi">
          <Sparkles :size="16" /><span>{{ t('teachingRepresentations.slides.askAi', '交给 AI 老师') }}</span>
        </button>
        <button type="button" :disabled="building" :title="t('teachingRepresentations.exportPptx', '导出 PPTX')" @click="store.downloadSlides(representationId)">
          <Download :size="16" /><span>{{ t('teachingRepresentations.exportPptx', '导出 PPTX') }}</span>
        </button>
      </div>
      <div v-if="building" class="slide-workbench__progress" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
        <i :style="{ width: `${progress}%` }"></i>
      </div>
    </header>

    <div class="slide-workbench__body">
      <aside class="slide-thumbnails" :aria-label="t('teachingRepresentations.slides.pageList', '幻灯片页列表')">
        <button
          v-for="(slide, index) in slides"
          :key="slide.unit_id"
          type="button"
          :class="{ active: slide.unit_id === activeUnitId, stale: staleUnitIds.includes(slide.unit_id) }"
          @click="selectSlide(slide.unit_id)"
        >
          <span>{{ index + 1 }}</span>
          <div class="slide-thumbnail" :data-layout="slide.layout">
            <i></i>
            <strong>{{ slide.title }}</strong>
            <small>{{ layoutLabel(slide.layout) }}</small>
          </div>
        </button>
        <div v-if="building" class="slide-thumbnails__generating">
          <LoaderCircle :size="15" class="spinning" />
          <span>{{ t('teachingRepresentations.slides.generatingPage', '正在生成第 {count} 页').replace('{count}', String(slides.length + 1)) }}</span>
        </div>
      </aside>

      <main class="slide-stage">
        <div v-if="activeSlide" class="slide-canvas" :data-layout="activeSlide.layout">
          <template v-if="activeSlide.layout === 'cover'">
            <i class="slide-canvas__rail"></i>
            <div class="slide-cover__brand">{{ t('teachingRepresentations.slides.brand', '灵知') }}</div>
            <div class="slide-cover__content">
              <small>{{ activeSlide.eyebrow }}</small>
              <h2>{{ activeSlide.title }}</h2>
              <p>{{ activeSlide.subtitle }}</p>
              <blockquote>{{ activeSlide.key_message }}</blockquote>
            </div>
          </template>

          <template v-else-if="activeSlide.layout === 'chapter'">
            <div class="slide-chapter__number">{{ chapterNumber(activeSlide.title) }}</div>
            <div class="slide-chapter__content">
              <small>{{ activeSlide.eyebrow }}</small>
              <h2>{{ activeSlide.title }}</h2>
              <blockquote>{{ activeSlide.key_message }}</blockquote>
            </div>
          </template>

          <template v-else>
            <header class="slide-canvas__heading">
              <small>{{ activeSlide.eyebrow || layoutLabel(activeSlide.layout) }}</small>
              <h2>{{ activeSlide.title }}</h2>
              <i></i>
            </header>
            <blockquote v-if="activeSlide.key_message && !['objective', 'misconception', 'practice'].includes(activeSlide.layout)" class="slide-canvas__message">
              {{ activeSlide.key_message }}
            </blockquote>
            <div class="slide-canvas__blocks" :data-layout="activeSlide.layout">
              <article v-for="block in activeSlide.blocks" :key="block.block_id" :data-type="block.type">
                <span v-if="block.title">{{ block.title }}</span>
                <pre v-if="block.type === 'code'"><code>{{ block.content }}</code></pre>
                <table v-else-if="block.type === 'comparison' && block.metadata?.rows?.length">
                  <thead><tr><th v-for="header in block.metadata.headers || []" :key="header">{{ header }}</th></tr></thead>
                  <tbody><tr v-for="(row, rowIndex) in block.metadata.rows" :key="rowIndex"><td v-for="cell in row" :key="cell">{{ cell }}</td></tr></tbody>
                </table>
                <ol v-else-if="block.type === 'process'">
                  <li v-for="(item, itemIndex) in block.items" :key="item"><b>{{ itemIndex + 1 }}</b>{{ item }}</li>
                </ol>
                <ul v-else-if="block.items?.length">
                  <li v-for="item in block.items" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ block.content }}</p>
              </article>
            </div>
            <footer><span>{{ activeIndex + 1 }} / {{ slides.length }}</span><span>{{ activeSlide.section_id || deckTitle }}</span></footer>
          </template>
        </div>
        <div v-else class="slide-stage__empty">
          <LoaderCircle v-if="building" :size="24" class="spinning" />
          <Presentation v-else :size="24" />
          <span>{{ building ? stageLabel : t('teachingRepresentations.slides.noSlides', '还没有可预览的页面') }}</span>
        </div>
      </main>

      <aside class="slide-inspector">
        <template v-if="activeSlide">
          <section>
            <header><span>{{ t('teachingRepresentations.slides.pageQuality', '本页质量') }}</span><b :data-passed="slideQualityPassed">{{ slideQualityPassed ? t('teachingRepresentations.slides.passed', '通过') : t('teachingRepresentations.slides.review', '检查') }}</b></header>
            <dl>
              <div><dt>{{ t('teachingRepresentations.slides.layout', '版式') }}</dt><dd>{{ layoutLabel(activeSlide.layout) }}</dd></div>
              <div><dt>{{ t('teachingRepresentations.slides.purpose', '教学作用') }}</dt><dd>{{ purposeLabel(activeSlide.slide_purpose) }}</dd></div>
              <div><dt>{{ t('teachingRepresentations.slides.textLoad', '文字负载') }}</dt><dd>{{ activeSlide.quality?.character_count || 0 }}</dd></div>
            </dl>
          </section>

          <section>
            <header><span>{{ t('teachingRepresentations.slides.source', '同源依据') }}</span><b>{{ sourceCount }}</b></header>
            <div class="slide-inspector__refs">
              <span v-for="label in activeSlide.knowledge_labels || []" :key="label">{{ label }}</span>
              <span v-for="label in activeSlide.ability_labels || []" :key="label" data-kind="ability">{{ label }}</span>
              <small v-if="!sourceCount">{{ t('teachingRepresentations.slides.noSource', '等待来源绑定') }}</small>
            </div>
            <p v-if="activeSlide.misconception_refs?.length"><TriangleAlert :size="13" />{{ t('teachingRepresentations.slides.misconceptionCount', '{count} 个易错点').replace('{count}', String(activeSlide.misconception_refs.length)) }}</p>
            <p v-if="activeSlide.practice_task_ids?.length"><ClipboardCheck :size="13" />{{ t('teachingRepresentations.slides.practiceCount', '{count} 道正式题目').replace('{count}', String(activeSlide.practice_task_ids.length)) }}</p>
          </section>

          <section class="slide-inspector__edit">
            <header><span>{{ t('teachingRepresentations.slides.pageEdit', '页面修改') }}</span><Pencil :size="14" /></header>
            <label>
              <span>{{ t('teachingRepresentations.slides.editField', '修改内容') }}</span>
              <select v-model="editField" :disabled="building" @change="resetEdit">
                <option value="title">{{ t('teachingRepresentations.slides.fields.title', '标题') }}</option>
                <option value="key_message">{{ t('teachingRepresentations.slides.fields.keyMessage', '核心信息') }}</option>
                <option value="speaker_notes">{{ t('teachingRepresentations.slides.fields.notes', '讲者备注') }}</option>
                <option value="layout">{{ t('teachingRepresentations.slides.fields.layout', '版式') }}</option>
              </select>
            </label>
            <label>
              <span>{{ t('teachingRepresentations.slides.updatedValue', '修改后') }}</span>
              <select v-if="editField === 'layout'" v-model="editValue" :disabled="building">
                <option v-for="layout in layouts" :key="layout" :value="layout">{{ layoutLabel(layout) }}</option>
              </select>
              <textarea v-else v-model="editValue" :disabled="building" rows="4"></textarea>
            </label>
            <div v-if="editPreview" class="slide-inspector__impact" data-state="affected">
              <strong>{{ classificationLabel(editPreview.classification) }}</strong>
              <p class="semantic-change">{{ editPreview.semantic_change?.summary || editPreview.reason }}</p>
              <ul v-if="editPreview.impact?.affected_representations?.length">
                <li v-for="item in editPreview.impact.affected_representations" :key="item.representation_id">
                  <span>{{ representationLabel(item.representation_type) }}</span>
                  <b>{{ t('teachingRepresentations.affectedUnits', '{count} 处需联动').replace('{count}', String(item.unit_ids?.length || 0)) }}</b>
                </li>
              </ul>
              <small>{{ t('teachingRepresentations.preciseImpactSummary', '预计联动 {affected} 处，保持 {unaffected} 处不变')
                .replace('{affected}', String(editPreview.impact?.affected_unit_count || 0))
                .replace('{unaffected}', String(editPreview.impact?.unaffected_unit_count || 0)) }}</small>
              <p class="protected"><ShieldCheck :size="12" />{{ t('teachingRepresentations.unrelatedProtected', '无来源关系的内容不会修改') }}</p>
            </div>
            <div v-if="pendingInlineItem" class="slide-inspector__confirmation" data-state="pending">
              <strong><Sparkles :size="13" />{{ t('teachingRepresentations.confirmCourseChange', '确认课程语义变化') }}</strong>
              <div class="objective-diff">
                <span>{{ proposalContent(pendingInlineItem.before) }}</span>
                <i>→</i>
                <b>{{ proposalContent(pendingInlineItem.after) }}</b>
              </div>
              <p>{{ pendingInlineItem.reason }}</p>
              <div class="slide-inspector__edit-actions">
                <button type="button" class="semantic" :disabled="editBusy" @click="confirmInlineChange"><CircleCheck :size="13" />{{ t('teachingRepresentations.confirmSync', '确认并同步相关内容') }}</button>
                <button type="button" :disabled="editBusy" @click="rejectInlineChange"><X :size="13" />{{ t('teachingRepresentations.rejectChange', '不应用') }}</button>
              </div>
            </div>
            <div v-if="syncReceipt" class="slide-inspector__receipt" :data-state="syncReceipt.status">
              <CircleCheck v-if="syncReceipt.status === 'synchronized'" :size="15" />
              <TriangleAlert v-else :size="15" />
              <div>
                <strong>{{ syncReceipt.status === 'synchronized'
                  ? t('teachingRepresentations.syncComplete', '课程同源同步完成')
                  : t('teachingRepresentations.syncFallback', '课程已更新，教学资源暂用上一版') }}</strong>
                <p v-if="syncReceipt.status === 'synchronized'">{{ t('teachingRepresentations.syncCounts', '{rebuilt} 处已更新，{reused} 处确认无需修改')
                  .replace('{rebuilt}', String(syncRebuiltCount))
                  .replace('{reused}', String(syncReusedCount)) }}</p>
              </div>
            </div>
            <div v-if="!pendingInlineItem" class="slide-inspector__edit-actions">
              <button v-if="!editPreview" type="button" :disabled="editBusy || building || !changed" @click="previewEdit"><ScanSearch :size="14" />{{ t('teachingRepresentations.previewEdit', '分析影响') }}</button>
              <template v-else>
                <button type="button" :disabled="editBusy" @click="applyEdit('representation_only')">{{ t('teachingRepresentations.onlyThisPpt', '只改当前 PPT') }}</button>
                <button type="button" class="semantic" :disabled="editBusy || editField === 'layout' || editField === 'speaker_notes'" @click="applyEdit('course_semantic')">{{ t('teachingRepresentations.changeCourseMeaning', '改变课程含义并联动') }}</button>
              </template>
            </div>
            <output v-if="editResult">{{ editResult }}</output>
          </section>

          <details v-if="activeSlide.speaker_notes">
            <summary>{{ t('teachingRepresentations.slides.speakerNotes', '讲者备注') }}</summary>
            <p>{{ activeSlide.speaker_notes }}</p>
          </details>
        </template>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { CircleCheck, ClipboardCheck, Download, LoaderCircle, Pencil, Presentation, ScanSearch, ShieldCheck, Sparkles, TriangleAlert, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useTeachingRepresentationsStore } from '../stores/teachingRepresentations'
import type { ChangeProposal, ChangeProposalContent, ChangeProposalItem } from '../types/changeProposal'

interface SlideBlock {
  block_id: string
  type: string
  title?: string
  content?: string
  items?: string[]
  metadata?: Record<string, any>
}

interface Slide {
  unit_id: string
  layout: string
  slide_purpose: string
  eyebrow?: string
  title: string
  subtitle?: string
  key_message?: string
  speaker_notes?: string
  section_id?: string
  blocks: SlideBlock[]
  source_section_ids?: string[]
  source_block_ids?: string[]
  source_keys?: string[]
  knowledge_refs?: string[]
  ability_refs?: string[]
  misconception_refs?: string[]
  practice_task_ids?: string[]
  knowledge_labels?: string[]
  ability_labels?: string[]
  quality?: { passed?: boolean; character_count?: number; issues?: Array<Record<string, any>> }
}

const props = defineProps<{
  courseId: string
  representationId: string
  deckTitle: string
  slides: Slide[]
  staleUnitIds: string[]
  building: boolean
  progress: number
  stage: string
  error: string
  quality?: Record<string, any> | null
}>()

const emit = defineEmits<{
  (event: 'ask-ai', payload: { text: string; nodeId: string; anchor: Record<string, unknown>; prefill: string }): void
}>()

const store = useTeachingRepresentationsStore()
const changeProposalsStore = useChangeProposalsStore()
const activeUnitId = ref('')
const userSelected = ref(false)
const editField = ref('title')
const editValue = ref('')
const editPreview = ref<Record<string, any> | null>(null)
const editResult = ref('')
const editBusy = ref(false)
const inlineProposal = ref<ChangeProposal | null>(null)
const syncReceipt = ref<Record<string, any> | null>(null)
const layouts = ['cover', 'roadmap', 'chapter', 'objective', 'concept', 'comparison', 'process', 'code', 'misconception', 'practice', 'recap']

const activeIndex = computed(() => Math.max(0, props.slides.findIndex(slide => slide.unit_id === activeUnitId.value)))
const activeSlide = computed(() => props.slides[activeIndex.value] || null)
const qualityPassed = computed(() => props.quality?.passed === true)
const slideQualityPassed = computed(() => activeSlide.value?.quality?.passed === true)
const sourceCount = computed(() => {
  const slide = activeSlide.value
  if (!slide) return 0
  return new Set([
    ...(slide.source_section_ids || []),
    ...(slide.source_block_ids || []),
    ...(slide.source_keys || []),
    ...(slide.knowledge_refs || []),
    ...(slide.ability_refs || []),
  ]).size
})
const changed = computed(() => Boolean(activeSlide.value) && editValue.value.trim() !== currentFieldValue.value.trim())
const currentFieldValue = computed(() => String((activeSlide.value as Record<string, any> | null)?.[editField.value] || ''))
const pendingInlineItem = computed<ChangeProposalItem | null>(() => (
  inlineProposal.value?.items.find(item => item.status === 'pending') || null
))
const syncRebuiltCount = computed(() => (
  Number(syncReceipt.value?.rebuilt_unit_count)
  || (syncReceipt.value?.rebuilt || []).reduce(
    (total: number, item: Record<string, any>) => total + (item.rebuilt_unit_ids?.length || 0),
    0,
  )
))
const syncReusedCount = computed(() => (
  Number(syncReceipt.value?.reused_unit_count)
  || (syncReceipt.value?.rebuilt || []).reduce(
    (total: number, item: Record<string, any>) => total + (item.reused_unit_ids?.length || 0),
    0,
  )
))
const stageLabel = computed(() => ({
  planning: t('teachingRepresentations.slides.stages.planning', '正在准备课程结构'),
  slide_plan: t('teachingRepresentations.slides.stages.slidePlan', '正在规划页面'),
  slide_build: t('teachingRepresentations.slides.stages.slideBuild', '正在生成页面'),
  quality: t('teachingRepresentations.slides.stages.quality', '正在检查质量'),
  complete: t('teachingRepresentations.slides.stages.complete', '生成完成'),
}[props.stage] || t('teachingRepresentations.slides.stages.building', '正在生成课件')))

watch(() => props.slides.map(slide => slide.unit_id), unitIds => {
  if (!unitIds.length) {
    activeUnitId.value = ''
    return
  }
  if (!unitIds.includes(activeUnitId.value)) activeUnitId.value = unitIds[0] || ''
  if (props.building && !userSelected.value) activeUnitId.value = unitIds[unitIds.length - 1] || ''
}, { immediate: true })

watch(activeSlide, resetEdit, { immediate: true })

function selectSlide(unitId: string) {
  activeUnitId.value = unitId
  userSelected.value = true
}

function resetEdit() {
  editValue.value = currentFieldValue.value
  editPreview.value = null
  editResult.value = ''
  inlineProposal.value = null
  syncReceipt.value = null
}

async function previewEdit() {
  const slide = activeSlide.value
  if (!slide) return
  editBusy.value = true
  try {
    editPreview.value = await store.previewEdit(props.representationId, {
      unit_id: slide.unit_id,
      field: editField.value,
      before: currentFieldValue.value,
      after: editValue.value,
    })
  } finally {
    editBusy.value = false
  }
}

async function applyEdit(decision: 'representation_only' | 'course_semantic') {
  const slide = activeSlide.value
  if (!slide) return
  editBusy.value = true
  try {
    const result = await store.applyEdit(props.representationId, {
      unit_id: slide.unit_id,
      field: editField.value,
      before: currentFieldValue.value,
      after: editValue.value,
      decision,
      semantic_intent: decision === 'course_semantic',
    })
    if (decision === 'course_semantic') {
      await changeProposalsStore.fetchChangeProposals(props.courseId)
      inlineProposal.value = changeProposalsStore.findProposal(result.authoring_change?.proposal_id)
        || result.authoring_change
        || null
      editResult.value = t('teachingRepresentations.courseCandidateReady', '已生成课程修改候选，请确认影响范围')
    } else {
      editResult.value = t('teachingRepresentations.representationSaved', '当前 PPT 已更新，课程正文保持不变')
      editPreview.value = null
    }
  } finally {
    editBusy.value = false
  }
}

async function confirmInlineChange() {
  const proposal = inlineProposal.value
  const item = pendingInlineItem.value
  if (!proposal || !item) return
  editBusy.value = true
  try {
    const result = await changeProposalsStore.applyItem(proposal.proposal_id, item.item_id)
    await store.load(props.courseId)
    await store.select(props.representationId)
    // Loading the rebuilt deck replaces the active slide object and schedules
    // resetEdit(). Let that reset finish before exposing the durable sync receipt.
    await nextTick()
    inlineProposal.value = null
    editPreview.value = null
    syncReceipt.value = result?.representation_sync || null
    editResult.value = t('teachingRepresentations.syncComplete', '课程同源同步完成')
  } finally {
    editBusy.value = false
  }
}

async function rejectInlineChange() {
  const proposal = inlineProposal.value
  const item = pendingInlineItem.value
  if (!proposal || !item) return
  editBusy.value = true
  try {
    await changeProposalsStore.rejectItem(proposal.proposal_id, item.item_id)
    inlineProposal.value = null
    editResult.value = t('teachingRepresentations.changeRejected', '本次课程语义修改未应用')
  } finally {
    editBusy.value = false
  }
}

function proposalContent(content: ChangeProposalContent) {
  if (typeof content === 'string') return content
  if (!content || typeof content !== 'object') return ''
  const value = (
    'payload' in content && content.payload ? content.payload : content
  ) as Record<string, unknown>
  return String(value.learning_objective || value.markdown || value.summary || value.title || '')
}

function representationLabel(value: string) {
  return t(`teachingRepresentations.types.${value}`, ({
    outline: '课程大纲',
    lesson_plan: '教案',
    handout: '讲义',
    practice_sheet: '理解检查',
    slide_deck: 'PPT',
  } as Record<string, string>)[value] || value)
}

function askAi() {
  const slide = activeSlide.value
  if (!slide) return
  emit('ask-ai', {
    text: `${t('teachingRepresentations.slides.page', '幻灯片')} ${activeIndex.value + 1} · ${slide.title}\n${slide.key_message || ''}`.trim(),
    nodeId: slide.section_id || '',
    anchor: { representation_id: props.representationId, slide_unit_id: slide.unit_id },
    prefill: t('teachingRepresentations.slides.aiPrompt', '请从教学目标、知识依据和页面表达三个角度检查这一页，并给出可执行的改进建议。'),
  })
}

function layoutLabel(value: string) {
  return t(`teachingRepresentations.slides.layouts.${value}`, ({
    cover: '封面', roadmap: '路线', chapter: '章节', objective: '目标', concept: '概念', comparison: '对比', process: '过程', code: '代码', misconception: '易错', practice: '练习', recap: '小结',
  } as Record<string, string>)[value] || value)
}

function purposeLabel(value: string) {
  return t(`teachingRepresentations.slides.purposes.${value}`, value || t('teachingRepresentations.slides.purposes.teaching', '教学讲解'))
}

function classificationLabel(value: string) {
  return ({
    presentation: t('teachingRepresentations.classification.presentation', '表现修改'),
    equivalent_semantic: t('teachingRepresentations.classification.equivalent', '等义修改'),
    semantic: t('teachingRepresentations.classification.semantic', '语义修改'),
    ambiguous: t('teachingRepresentations.classification.ambiguous', '需要确认'),
  } as Record<string, string>)[value] || value
}

function chapterNumber(title: string) {
  return title.match(/\d+/)?.[0]?.padStart(2, '0') || '·'
}
</script>

<style scoped>
.slide-workbench { min-width:0; min-height:0; height:100%; display:grid; grid-template-rows:58px minmax(0,1fr); background:#f7f8fc; }
.slide-workbench__toolbar { position:relative; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 14px 0 18px; border-bottom:1px solid var(--lz-border); background:#fff; }
.slide-workbench__toolbar > div:first-child { min-width:0; display:flex; align-items:center; gap:10px; }.slide-workbench__toolbar strong { overflow:hidden; color:var(--lz-text-strong); font-size:13px; text-overflow:ellipsis; white-space:nowrap; }.slide-workbench__toolbar small { flex:none; color:var(--lz-text-muted); font-size:9px; }
.slide-workbench__status { min-height:24px; display:inline-flex; align-items:center; gap:5px; padding:0 8px; border-radius:6px; color:#047857; background:#ecfdf5; font-size:9px; font-weight:700; }.slide-workbench__status[data-state="building"] { color:#4f46e5; background:#eef2ff; }.slide-workbench__status[data-state="warning"] { color:#b45309; background:#fffbeb; }
.slide-workbench__status[data-state="error"] { color:#b42318; background:#fef3f2; }
.slide-workbench__commands { flex:none; display:flex; gap:6px; }.slide-workbench__commands button { min-height:34px; display:inline-flex; align-items:center; gap:6px; padding:0 10px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; cursor:pointer; }.slide-workbench__commands button:hover { color:var(--lz-brand-strong); border-color:#c7d2fe; background:var(--lz-brand-soft); }.slide-workbench__commands button:disabled { opacity:.45; cursor:not-allowed; }
.slide-workbench__progress { position:absolute; inset:auto 0 -1px; height:2px; background:#eef0f8; }.slide-workbench__progress i { display:block; height:100%; background:#6d5dfb; transition:width .2s ease; }
.slide-workbench__body { min-width:0; min-height:0; display:grid; grid-template-columns:176px minmax(430px,1fr) 236px; }
.slide-thumbnails { min-height:0; overflow:auto; padding:10px 8px 18px; border-right:1px solid var(--lz-border); background:#fbfcff; }.slide-thumbnails > button { width:100%; display:grid; grid-template-columns:20px minmax(0,1fr); align-items:start; gap:5px; margin:0 0 6px; padding:5px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }.slide-thumbnails > button:hover { background:#f3f5fb; }.slide-thumbnails > button.active { border-color:#a5b4fc; color:var(--lz-brand); background:#fff; box-shadow:0 4px 12px rgba(79,70,229,.08); }.slide-thumbnails > button.stale { border-left-color:#f59e0b; }.slide-thumbnails > button > span { padding-top:3px; font:700 8px ui-monospace,monospace; text-align:center; }
.slide-thumbnail { aspect-ratio:16/9; min-width:0; overflow:hidden; display:flex; flex-direction:column; padding:8px; border:1px solid #e4e7f0; border-radius:4px; background:#fff; text-align:left; }.slide-thumbnail i { width:24px; height:2px; margin-bottom:6px; background:#6d5dfb; }.slide-thumbnail strong { display:-webkit-box; overflow:hidden; color:#27324a; font-size:7px; line-height:1.35; -webkit-box-orient:vertical; -webkit-line-clamp:2; }.slide-thumbnail small { margin-top:auto; color:#98a2b3; font-size:6px; }.slide-thumbnail[data-layout="chapter"],.slide-thumbnail[data-layout="cover"] { background:linear-gradient(90deg,#eeeafe 0 31%,#fff 31%); }.slide-thumbnail[data-layout="code"] { background:linear-gradient(90deg,#202536 0 64%,#f6f7fc 64%); }.slide-thumbnail[data-layout="code"] strong { color:#fff; }
.slide-thumbnails__generating { display:flex; align-items:center; gap:6px; padding:9px 8px; color:var(--lz-brand); font-size:8px; }
.slide-stage { min-width:0; min-height:0; overflow:auto; display:grid; place-items:center; padding:24px; background:#eef0f6; }
.slide-canvas { position:relative; width:min(100%,860px); aspect-ratio:16/9; overflow:hidden; color:#172033; background:#fff; box-shadow:0 18px 38px rgba(35,45,75,.14); container-type:inline-size; }.slide-canvas h2 { margin:0; letter-spacing:0; }.slide-canvas blockquote { margin:0; }
.slide-canvas__heading { position:absolute; inset:6.8% 6% auto; }.slide-canvas__heading small { color:#6d5dfb; font-size:1.2cqw; font-weight:750; }.slide-canvas__heading h2 { margin-top:.8%; font-size:2.55cqw; line-height:1.18; }.slide-canvas__heading i { display:block; width:7%; height:3px; margin-top:1.25%; background:#6d5dfb; }
.slide-canvas__message { position:absolute; inset:23% 6% auto; min-height:9%; padding:1.6% 2.1%; border-radius:6px; color:#27324a; background:#eeeafe; font-size:1.45cqw; font-weight:700; line-height:1.35; }
.slide-canvas__blocks { position:absolute; inset:34% 6% 10%; display:grid; grid-template-columns:repeat(auto-fit,minmax(0,1fr)); gap:2%; }.slide-canvas__blocks[data-layout="objective"] { inset:26% 6% 10%; grid-template-columns:1fr 1.25fr; }.slide-canvas__blocks[data-layout="code"] { inset:25% 6% 10%; grid-template-columns:1.65fr 1fr; }.slide-canvas__blocks[data-layout="practice"],.slide-canvas__blocks[data-layout="misconception"] { inset:26% 6% 10%; grid-template-columns:1.5fr .8fr; }.slide-canvas__blocks[data-layout="roadmap"],.slide-canvas__blocks[data-layout="process"] { inset:27% 6% 12%; grid-template-columns:repeat(auto-fit,minmax(0,1fr)); }
.slide-canvas__blocks article { min-width:0; overflow:hidden; padding:6%; border:1px solid #e0e4ee; border-radius:7px; background:#fff; }.slide-canvas__blocks article > span { display:block; margin-bottom:6%; color:#6d5dfb; font-size:1.1cqw; font-weight:750; }.slide-canvas__blocks p,.slide-canvas__blocks li { margin:0; font-size:1.22cqw; line-height:1.5; }.slide-canvas__blocks ul { margin:0; padding-left:1.3em; }.slide-canvas__blocks li + li { margin-top:.55em; }.slide-canvas__blocks pre { height:100%; margin:0; overflow:hidden; color:#f5f7ff; background:#202536; white-space:pre-wrap; }.slide-canvas__blocks article[data-type="code"] { padding:4%; border-color:#202536; background:#202536; }.slide-canvas__blocks code { font:1.03cqw/1.45 ui-monospace,SFMono-Regular,monospace; }.slide-canvas__blocks article[data-type="misconception"] { border-color:#f7c6cc; background:#fdedef; }.slide-canvas__blocks article[data-type="exercise"] { border-color:#f2d2ab; background:#fff2e5; }.slide-canvas__blocks ol { display:grid; gap:4%; margin:0; padding:0; list-style:none; }.slide-canvas__blocks ol li { display:flex; gap:6%; align-items:flex-start; }.slide-canvas__blocks ol b { width:2em; height:2em; flex:none; display:grid; place-items:center; border-radius:5px; color:#fff; background:#6d5dfb; }.slide-canvas table { width:100%; border-collapse:collapse; font-size:1cqw; }.slide-canvas th,.slide-canvas td { padding:.45em .55em; border:1px solid #dfe3ee; text-align:left; }.slide-canvas th { color:#4f46e5; background:#eeeafe; }
.slide-canvas footer { position:absolute; inset:auto 6% 3.4%; display:flex; justify-content:space-between; color:#98a2b3; font-size:.8cqw; }.slide-canvas__rail { position:absolute; inset:7% auto 12% 4%; width:5px; border-radius:3px; background:#6d5dfb; }.slide-cover__brand { position:absolute; inset:8% 6% auto auto; width:8%; aspect-ratio:1; display:grid; place-items:center; border-radius:8px; color:#fff; background:#14866d; font-size:1.25cqw; font-weight:800; }.slide-cover__content { position:absolute; inset:13% 22% 12% 8%; }.slide-cover__content small,.slide-chapter__content small { color:#6d5dfb; font-size:1.35cqw; font-weight:750; }.slide-cover__content h2 { margin-top:6%; font-size:4.2cqw; line-height:1.14; }.slide-cover__content p { margin:5% 0 0; color:#667085; font-size:1.55cqw; }.slide-cover__content blockquote { margin-top:8%; padding:3% 4%; border-radius:7px; background:#f6f7fc; font-size:1.55cqw; font-weight:700; }.slide-chapter__number { position:absolute; inset:0 auto 0 0; width:31%; display:grid; place-items:center; color:#6d5dfb; background:#eeeafe; font-size:7cqw; font-weight:800; }.slide-chapter__content { position:absolute; inset:20% 8% 16% 36%; }.slide-chapter__content h2 { margin-top:6%; font-size:3.45cqw; line-height:1.18; }.slide-chapter__content blockquote { margin-top:10%; padding:4%; border:1px solid #dfe3ee; border-radius:7px; font-size:1.65cqw; font-weight:700; }
.slide-stage__empty { display:flex; flex-direction:column; align-items:center; gap:10px; color:var(--lz-text-muted); font-size:11px; }
.slide-inspector { min-height:0; overflow:auto; padding:12px; border-left:1px solid var(--lz-border); background:#fff; }.slide-inspector section { padding:4px 0 14px; border-bottom:1px solid #edf0f5; }.slide-inspector section + section { padding-top:14px; }.slide-inspector section > header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; color:var(--lz-text-strong); font-size:10px; font-weight:750; }.slide-inspector section > header b { padding:3px 6px; border-radius:5px; color:var(--lz-text-muted); background:#f3f4f7; font-size:8px; }.slide-inspector section > header b[data-passed="true"] { color:#047857; background:#ecfdf5; }
.slide-inspector dl { margin:0; }.slide-inspector dl div { display:flex; justify-content:space-between; gap:10px; padding:4px 0; font-size:9px; }.slide-inspector dt { color:var(--lz-text-muted); }.slide-inspector dd { margin:0; color:var(--lz-text-secondary); text-align:right; }.slide-inspector__refs { display:flex; flex-wrap:wrap; gap:4px; }.slide-inspector__refs span { max-width:100%; overflow:hidden; padding:4px 6px; border-radius:5px; color:#4f46e5; background:#eef2ff; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }.slide-inspector__refs span[data-kind="ability"] { color:#047857; background:#ecfdf5; }.slide-inspector__refs small { color:var(--lz-text-muted); font-size:8px; }.slide-inspector section > p { display:flex; align-items:center; gap:5px; margin:8px 0 0; color:var(--lz-text-secondary); font-size:8px; }
.slide-inspector__edit label { display:block; margin-top:9px; }.slide-inspector__edit label > span { display:block; margin-bottom:5px; color:var(--lz-text-muted); font-size:8px; }.slide-inspector__edit select,.slide-inspector__edit textarea { width:100%; box-sizing:border-box; border:1px solid var(--lz-border); border-radius:6px; color:var(--lz-text); background:#fff; font:9px/1.45 inherit; outline:none; }.slide-inspector__edit select { height:30px; padding:0 7px; }.slide-inspector__edit textarea { resize:vertical; min-height:72px; padding:7px; }.slide-inspector__edit select:focus,.slide-inspector__edit textarea:focus { border-color:#818cf8; }
.slide-inspector__impact { margin-top:9px; padding:9px; border-left:3px solid #eab308; background:#fffbea; }.slide-inspector__impact > strong { color:#854d0e; font-size:9px; }.slide-inspector__impact .semantic-change { margin:4px 0 7px; color:#713f12; font-size:9px; font-weight:700; line-height:1.45; }.slide-inspector__impact ul { display:grid; gap:3px; margin:0 0 7px; padding:0; list-style:none; }.slide-inspector__impact li { display:flex; align-items:center; justify-content:space-between; gap:6px; color:#475569; font-size:8px; }.slide-inspector__impact li b { color:#a16207; font-size:8px; }.slide-inspector__impact small { color:#78716c; font-size:8px; }.slide-inspector__impact .protected { display:flex; align-items:center; gap:4px; margin:6px 0 0; color:#64748b; font-size:8px; }
.slide-inspector__confirmation { margin-top:9px; padding:9px; border-left:3px solid #8b5cf6; background:#f7f3ff; }.slide-inspector__confirmation > strong { display:flex; align-items:center; gap:5px; color:#6d28d9; font-size:9px; }.objective-diff { display:grid; grid-template-columns:minmax(0,1fr) 12px minmax(0,1fr); gap:4px; margin-top:7px; color:#64748b; font-size:8px; line-height:1.4; }.objective-diff i { color:#8b5cf6; font-style:normal; }.objective-diff b { color:#4c1d95; }.slide-inspector__confirmation > p { margin:6px 0 0; color:#64748b; font-size:8px; line-height:1.45; }
.slide-inspector__receipt { display:grid; grid-template-columns:18px minmax(0,1fr); gap:6px; margin-top:9px; padding:9px; border-left:3px solid #10b981; color:#047857; background:#ecfdf5; }.slide-inspector__receipt[data-state="failed_using_last_available"] { border-left-color:#f59e0b; color:#92400e; background:#fffbeb; }.slide-inspector__receipt strong { display:block; font-size:9px; }.slide-inspector__receipt p { margin:3px 0 0; color:#64748b; font-size:8px; line-height:1.45; }
.slide-inspector__edit-actions { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }.slide-inspector__edit-actions button { min-height:29px; display:inline-flex; align-items:center; justify-content:center; gap:4px; padding:0 8px; border:1px solid var(--lz-border); border-radius:6px; color:var(--lz-text-secondary); background:#fff; font-size:8px; cursor:pointer; }.slide-inspector__edit-actions button.semantic { color:#fff; border-color:#6366f1; background:#6366f1; }.slide-inspector__edit-actions button:disabled { opacity:.45; cursor:not-allowed; }.slide-inspector output { display:block; margin-top:8px; color:#047857; font-size:8px; }.slide-inspector details { padding:13px 0; color:var(--lz-text-secondary); font-size:9px; }.slide-inspector summary { color:var(--lz-text-strong); font-weight:700; cursor:pointer; }.slide-inspector details p { white-space:pre-line; line-height:1.55; }
.spinning { animation:slide-spin .8s linear infinite; }@keyframes slide-spin { to { transform:rotate(360deg); } }
@media (max-width:1100px) { .slide-workbench__body { grid-template-columns:148px minmax(400px,1fr) 210px; }.slide-stage { padding:16px; } }
@media (max-width:840px) { .slide-workbench { grid-template-rows:auto minmax(0,1fr); }.slide-workbench__toolbar { min-height:58px; flex-wrap:wrap; padding:8px 10px; }.slide-workbench__commands button span { display:none; }.slide-workbench__body { grid-template-columns:1fr; grid-template-rows:96px minmax(260px,1fr) auto; }.slide-thumbnails { display:flex; overflow-x:auto; border-right:0; border-bottom:1px solid var(--lz-border); }.slide-thumbnails > button { width:130px; flex:none; }.slide-stage { padding:12px; }.slide-inspector { max-height:250px; border-top:1px solid var(--lz-border); border-left:0; }.slide-inspector section { padding-right:8px; padding-left:8px; } }
</style>
