<template>
  <section class="ppt-manuscript-workflow" :class="{ 'is-embedded': embedded, 'has-external-actions': externalActions }" data-testid="ppt-manuscript-workflow">
    <header v-if="!reviewOnly" class="ppt-manuscript-workflow__header">
      <button v-if="!embedded" type="button" :aria-label="t('pptWorkspace.backToProduction')" class="ppt-manuscript-workflow__back" @click="emit('back')"><ArrowLeft :size="18" /></button>
      <div v-if="!embedded">
        <h1><MathText :content="title" /></h1>
      </div>
      <TeacherDocumentCommandBar v-if="state.generation_branch !== 'original_ppt_review'"
        class="ppt-manuscript-command-bar" :label="t('pptWorkspace.editor.actions')"
        :show-status="Boolean(manuscript) && (!externalActions || editing)" :status-label="saveStateLabel" :status-tone="saving ? 'busy' : dirty ? 'warning' : 'normal'">
        <template v-if="manuscript" #context>
          <CompactPagination v-if="externalActions" style="--pagination-font-size:15px" :page="activePageNumber" :page-count="draftPages.length" range-text="" :label="t('pptWorkspace.editor.pages')" :previous-label="t('pptWorkspace.sidebar.previousPage')" :next-label="t('pptWorkspace.sidebar.nextPage')" :page-select-label="t('pptWorkspace.sidebar.selectPage')" test-id-prefix="ppt-manuscript" @update:page="selectPage(draftPages[$event - 1]?.page_id)" />
          <span v-if="!externalActions" class="ppt-manuscript-page-count">{{ manuscriptPageCounts }}</span>
        </template>
        <template v-if="!externalActions && manuscript && state.source_state === 'stale'">
          <button v-if="allowPageRegeneration !== false" type="button" :disabled="busy || dirty" data-testid="regenerate-affected-ppt-pages" @click="emit('regenerate-pages', [])"><RefreshCw :size="16" />{{ t('pptWorkspace.regenerateAffectedPages') }}</button>
          <button type="button" class="primary-action" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')">{{ t('pptWorkspace.regenerateManuscript') }}</button>
        </template>
        <button v-else-if="!manuscript" type="button" class="primary-action" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')"><Sparkles :size="16" />{{ busy ? t('pptWorkspace.generatingManuscript') : retryLabel }}</button>
        <template v-else-if="editing">
          <button type="button" :disabled="busy" data-testid="cancel-ppt-edit" @click="cancelEditing"><X :size="16" />{{ t('common.cancel') }}</button>
          <button type="button" class="primary-action" :disabled="busy" data-testid="save-ppt-manuscript" @click="finishEditing"><Check :size="16" />{{ saving ? t('pptWorkspace.savingManuscript') : t('pptWorkspace.editor.finishEditing') }}</button>
        </template>
        <template v-else>
          <button v-if="externalActions && allowPageRegeneration !== false" type="button" :disabled="busy || dirty" :aria-pressed="selectingPages" data-testid="select-ppt-pages" @click="togglePageSelection">{{ selectingPages ? t('common.cancel') : t('pptWorkspace.editor.selectPages') }}</button>
          <button type="button" :disabled="busy" :aria-expanded="arrangementOpen" data-testid="ppt-lesson-arrangement" @click="arrangementOpen = !arrangementOpen"><ListTree :size="16" />{{ t('pptWorkspace.lessonArrangement') }}</button>
          <button type="button" :disabled="busy" data-testid="edit-ppt-manuscript" @click="editing = true"><Pencil :size="16" />{{ t('pptWorkspace.editor.editPage') }}</button>
          <button v-if="!externalActions && state.status === 'draft'" type="button" class="primary-action" :disabled="busy || dirty || !state.confirmable" data-testid="confirm-ppt-manuscript" @click="emit('confirm-manuscript')"><Check :size="16" />{{ confirming ? t('pptWorkspace.confirmingManuscript') : t('pptWorkspace.confirmManuscript') }}</button>
          <button v-else-if="!externalActions" type="button" class="primary-action" :disabled="busy || dirty || !state.can_generate_ppt" data-testid="generate-ppt-from-manuscript" @click="emit('generate-ppt')">{{ embedded ? t('pptWorkspace.flow.continueToRender') : t('pptWorkspace.generateDeck') }}<ArrowRight :size="16" /></button>
        </template>
      </TeacherDocumentCommandBar>
    </header>

    <div v-if="state.generation_branch === 'original_ppt_review'" class="ppt-manuscript-workflow__original">
      <FileCheck2 :size="28" />
      <h2>{{ t('pptWorkspace.originalPptBranchTitle', '本讲已有原版 PPT') }}</h2>
      <p>{{ t('pptWorkspace.originalPptBranchDescription', '请返回课程准备页，继续原版 PPT 的审阅与确认。') }}</p>
      <button type="button" @click="emit('back')">{{ t('pptWorkspace.backToProduction', '返回课程准备页') }}</button>
    </div>

    <template v-else>
      <div v-if="!externalActions && manuscript && state.source_state === 'stale'" class="ppt-manuscript-workflow__warning"><TriangleAlert :size="18" /><span>{{ t('pptWorkspace.manuscriptStale', '教案、讲义或资料已经变化，请重新生成页面内容稿。') }}</span></div>
      <AppErrorNotice v-if="!externalActions && failureView" :presentation="failureView" compact data-testid="ppt-manuscript-failure" />

      <main v-if="manuscript" class="ppt-manuscript-workflow__content">
        <div v-if="externalActions && reviewOnly" class="ppt-manuscript-pagination">
          <CompactPagination style="--pagination-font-size:15px" :page="activePageNumber" :page-count="draftPages.length" range-text="" :label="t('pptWorkspace.editor.pages')" :previous-label="t('pptWorkspace.sidebar.previousPage')" :next-label="t('pptWorkspace.sidebar.nextPage')" :page-select-label="t('pptWorkspace.sidebar.selectPage')" test-id-prefix="ppt-manuscript" @update:page="selectPage(draftPages[$event - 1]?.page_id)" />
        </div>
        <section v-if="arrangementOpen" class="ppt-manuscript-workflow__lesson-plan">
        <section v-if="narrativeBrief" class="ppt-manuscript-workflow__brief" data-testid="ppt-narrative-brief">
          <div><small>{{ t('pptWorkspace.narrativeQuestion', '整讲中心问题') }}</small><strong>{{ narrativeBrief.central_question }}</strong></div>
          <div><small>{{ t('pptWorkspace.learningPath', '学习路径') }}</small><span>{{ listText(narrativeBrief.learning_path) }}</span></div>
          <div><small>{{ t('pptWorkspace.observableCheckpoints', '课堂检查') }}</small><span>{{ listText(narrativeBrief.observable_checkpoints) }}</span></div>
          <span v-if="narrativeBrief.time_budget_minutes > 0" class="ppt-manuscript-workflow__time">{{ narrativeBrief.time_budget_minutes }} {{ t('pptWorkspace.minutes', '分钟') }}</span>
        </section>

        <section v-if="draftPacing" class="ppt-manuscript-workflow__pacing" data-testid="ppt-pacing-plan">
          <label><span>{{ t('pptWorkspace.pacingBudget') }}</span><input v-model.number="draftPacing.max_physical_pages" type="number" min="1" max="5000" :disabled="busy || !editing" data-testid="ppt-pacing-budget"></label>
          <label><span>{{ t('pptWorkspace.pacingRationale') }}</span><textarea v-model="draftPacing.rationale" :disabled="busy || !editing" rows="2" /></label>
          <p>{{ t('pptWorkspace.pacingSavedCount').replace('{count}', String(manuscript.page_count)) }}</p>
        </section>
        </section>
        <ul v-if="lessonIssues.length" class="ppt-manuscript-workflow__issues" role="alert"><li v-for="issue in lessonIssues" :key="issue.code">{{ issue.message }}</li></ul>
        <div class="ppt-manuscript-workflow__pages">
          <nav v-if="!externalActions || selectingPages" class="ppt-manuscript-workflow__page-list" :aria-label="t('pptWorkspace.pageNavigation')">
            <header class="ppt-page-list-heading"><strong>{{ t('pptWorkspace.editor.pages') }}</strong><button v-if="!reviewOnly && !externalActions && allowPageRegeneration !== false" type="button" :disabled="busy || dirty" :aria-pressed="selectingPages" data-testid="select-ppt-pages" @click="togglePageSelection">{{ selectingPages ? t('common.cancel') : t('pptWorkspace.editor.selectPages') }}</button></header>
            <div v-if="selectingPages" class="ppt-page-list-selection"><button type="button" :disabled="busy || selectedPageIds.size === 0 || dirty" data-testid="regenerate-selected-ppt-pages" @click="emit('regenerate-pages', [...selectedPageIds])"><RefreshCw :size="15" />{{ t('pptWorkspace.editor.regenerateSelected').replace('{count}', String(selectedPageIds.size)) }}</button></div>
            <div v-for="item in draftPages" :key="item.page_id" class="ppt-manuscript-workflow__page-rail" :class="{ 'is-active': activePageId === item.page_id }">
              <input v-if="selectingPages" type="checkbox" :aria-label="`${t('pptWorkspace.selectPage')} ${item.page_number}`" :checked="selectedPageIds.has(item.page_id)" :disabled="busy || !canRegenerate(item)" @change="toggleSelected(item.page_id)">
              <button type="button" :aria-current="activePageId === item.page_id ? 'page' : undefined" :data-page-id="item.page_id" @click="selectPage(item.page_id)">
                <span>{{ item.page_number }}</span><MathText :content="item.title" />
                <Lock v-if="item.teacher_locked" :size="15" :aria-label="t('pptWorkspace.pageLocked')" />
              </button>
            </div>
          </nav>
          <article v-for="page in focusedPages" :key="page.page_id" :class="{ 'is-selected': selectedPageIds.has(page.page_id), 'is-locked': page.teacher_locked }">
            <div class="ppt-manuscript-workflow__page-copy">
              <div class="ppt-manuscript-workflow__page-meta">
                <UiSegmentedControl style="--ui-segment-font-size:15px" v-model="editorMode" :options="editorModes" :accessibility-label="t('pptWorkspace.pageEditing')" />
                <button v-if="editing" type="button" class="ppt-manuscript-workflow__lock" :disabled="busy" @click="toggleLock(page)"><Lock v-if="page.teacher_locked" :size="15" /><Unlock v-else :size="15" />{{ page.teacher_locked ? t('pptWorkspace.pageLocked', '已锁定') : t('pptWorkspace.lockPage', '锁定本页') }}</button>
              </div>

              <div v-if="!editing && editorMode === 'content'" class="ppt-manuscript-workflow__reading" data-testid="ppt-page-reading">
                <h2><MathText :content="page.title" /></h2>
                <PptTeachingEditor v-if="page.teaching" :page="page" :disabled="true" readonly section="content" />
                <div v-else class="ppt-page-reading-copy"><MathText v-for="(line, index) in (page.visible_copy || []).filter((line: string) => line !== page.title)" :key="index" tag="p" :content="line" /></div>
              </div>
              <div v-if="editorMode === 'layout'" class="ppt-manuscript-workflow__preview" data-testid="ppt-page-preview">
                <PptSceneCanvas v-if="activeScene" :scene="activeScene" />
                <p v-else class="ppt-layout-pending">{{ t('pptWorkspace.editor.layoutPending') }}</p>
                <div v-if="activeScene" class="ppt-manuscript-workflow__preview-status">
                  <span>{{ dirty ? t('pptWorkspace.previewSaveRequired') : t('pptWorkspace.savedPagePreview') }}</span>
                  <label v-if="page.resolved_scenes?.length > 1"><span>{{ t('pptWorkspace.previewState') }}</span><select v-model.number="sceneIndex"><option v-for="(_scene, index) in page.resolved_scenes" :key="index" :value="index">{{ index + 1 }} / {{ page.resolved_scenes.length }}</option></select></label>
                </div>
              </div>
              <template v-if="editing">
              <template v-if="editorMode === 'content'">
              <label class="ppt-manuscript-workflow__title-field"><span>{{ t('pptWorkspace.pageTitle', '页面标题') }}</span><input v-model="page.title" :disabled="busy" @input="syncTitleRegion(page)"></label>
              </template>
              <PptTeachingEditor v-if="page.teaching" :page="page" :disabled="Boolean(busy)" :section="editorMode" :layouts="state.layouts || []" />
              <template v-else>
                <div v-if="editorMode === 'content'" class="ppt-manuscript-workflow__visible-copy"><span>{{ t('pptWorkspace.visibleCopy') }}</span><textarea v-for="(_line, index) in page.visible_copy || []" :key="`${page.page_id}-copy-${index}`" v-model="page.visible_copy[index]" :disabled="busy" rows="2" :aria-label="`${t('pptWorkspace.visibleCopy')} ${index + 1}`" /></div>
                <label v-else><span>{{ t('pptWorkspace.revealSteps') }}</span><textarea :value="listLines(page.reveal_steps)" :disabled="busy" rows="3" @input="setLines(page, 'reveal_steps', $event)" /></label>
              </template>
              </template>
              <details class="ppt-manuscript-workflow__teaching-notes"><summary>{{ t('pptWorkspace.teachingNotes') }}</summary>
              <div class="ppt-manuscript-workflow__field-grid">
                <label><span>{{ t('pptWorkspace.pageGoal', '页面目标') }}</span><textarea v-if="editing" v-model="page.page_goal" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.page_goal || '—'" /></label>
                <label><span>{{ t('pptWorkspace.primaryClaim', '核心结论') }}</span><textarea v-if="editing" v-model="page.primary_claim" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.primary_claim || '—'" /></label>
                <label><span>{{ t('pptWorkspace.audienceQuestion', '学生思考的问题') }}</span><textarea v-if="editing" v-model="page.audience_question" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.audience_question || '—'" /></label>
                <label><span>{{ t('pptWorkspace.audienceAction', '学生活动') }}</span><textarea v-if="editing" v-model="page.audience_action" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.audience_action || '—'" /></label>
                <label><span>{{ t('pptWorkspace.expectedResponse', '预期反应') }}</span><textarea v-if="editing" v-model="page.expected_response" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.expected_response || '—'" /></label>
                <label><span>{{ t('pptWorkspace.observableEvidence', '达成证据') }}</span><textarea v-if="editing" v-model="page.observable_evidence" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.observable_evidence || '—'" /></label>
              </div>

              <label><span>{{ t('pptWorkspace.pageTransition', '与前后页的衔接') }}</span><textarea v-if="editing" v-model="page.transition" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.transition || '—'" /></label>
              <label><span>{{ t('pptWorkspace.compositionNotes', '构图意图') }}</span><textarea v-if="editing" v-model="page.composition_notes" :disabled="busy" rows="2" /><MathText v-else tag="p" :content="page.composition_notes || '—'" /></label>

              </details>
              <ul v-if="pageIssues(page.page_id).length" class="ppt-manuscript-workflow__issues"><li v-for="issue in pageIssues(page.page_id)" :key="`${page.page_id}-${issue.code}`">{{ issue.message || issue.code }}</li></ul>
              <details v-if="hasSourceRefs(page)" class="ppt-manuscript-workflow__sources"><summary>{{ t('pptWorkspace.viewSources', '查看本页来源') }}</summary><dl>
                <div v-if="sourceIds(page, 'source_script_block_ids').length"><dt>{{ t('pptWorkspace.sourceScriptBlockIds', '讲义来源块') }}</dt><dd><code v-for="sourceId in sourceIds(page, 'source_script_block_ids')" :key="sourceId">{{ sourceId }}</code></dd></div>
                <div v-if="sourceIds(page, 'source_section_ids').length"><dt>{{ t('pptWorkspace.sourceSectionIds', '教案小节') }}</dt><dd><code v-for="sourceId in sourceIds(page, 'source_section_ids')" :key="sourceId">{{ sourceId }}</code></dd></div>
                <div v-if="sourceIds(page, 'source_material_evidence_ids').length"><dt>{{ t('pptWorkspace.sourceMaterialEvidenceIds', '资料证据') }}</dt><dd><code v-for="sourceId in sourceIds(page, 'source_material_evidence_ids')" :key="sourceId">{{ sourceId }}</code></dd></div>
              </dl></details>
            </div>
          </article>
        </div>
      </main>

      <div v-else class="ppt-manuscript-workflow__empty"><ScrollText :size="34" /><h2>{{ t('pptWorkspace.manuscriptNotGenerated', '尚未生成页面内容稿') }}</h2><p>{{ t('pptWorkspace.manuscriptNotGeneratedDescription', '系统会先形成整讲叙事与逐页教学内容，供你编辑和确认。') }}</p></div>


    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Check, FileCheck2, ListTree, Lock, Pencil, RefreshCw, ScrollText, Sparkles, TriangleAlert, Unlock, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'
import PptTeachingEditor from './PptTeachingEditor.vue'
import PptSceneCanvas from './PptSceneCanvas.vue'
import UiSegmentedControl from './UiSegmentedControl.vue'
import TeacherDocumentCommandBar from './TeacherDocumentCommandBar.vue'
import CompactPagination from './CompactPagination.vue'
import AppErrorNotice from './AppErrorNotice.vue'
import { pptFailurePresentation } from '../utils/ppt-workspace-error'
import { teacherFacingTeachingLabel } from '../utils/teaching-terminology'

const props = withDefaults(defineProps<{ title: string; state: Record<string, any>; allowPageRegeneration?: boolean; embedded?: boolean; externalActions?: boolean; reviewOnly?: boolean; busy?: boolean; confirming?: boolean; saving?: boolean; regenerating?: boolean; error?: string; failure?: Record<string, any> | null }>(), { allowPageRegeneration: true })
const emit = defineEmits<{
  (event: 'back'): void
  (event: 'generate-manuscript'): void
  (event: 'regenerate-manuscript'): void
  (event: 'confirm-manuscript'): void
  (event: 'generate-ppt'): void
  (event: 'save-manuscript', updates: Record<string, any>[], pacing?: Record<string, any>): void
  (event: 'regenerate-pages', pageIds: string[]): void
  (event: 'dirty-change', dirty: boolean): void
}>()

const manuscript = computed(() => props.state.manuscript || null)
const manuscriptPageCounts = computed(() => t('pptWorkspace.manuscriptPageCounts')
  .replace('{logical}', String(manuscript.value?.pages?.length || 0))
  .replace('{physical}', String(manuscript.value?.page_count || 0)))
const draftPages = ref<Record<string, any>[]>([])
const originalPages = ref<Record<string, any>[]>([])
const draftPacing = ref<Record<string, any> | null>(null)
const selectedPageIds = ref(new Set<string>())
const activePageId = ref('')
const editorMode = ref('content')
const editing = ref(false)
const arrangementOpen = ref(false)
const selectingPages = ref(false)
let finishRequested = false
const sceneIndex = ref(0)
const editorModes = computed(() => [{ value: 'content', label: t('pptWorkspace.editPageContent') }, { value: 'layout', label: t('pptWorkspace.editPageLayout') }])
const focusedPages = computed(() => draftPages.value.filter(page => page.page_id === activePageId.value))
const activePageNumber = computed(() => Math.max(1, draftPages.value.findIndex(page => page.page_id === activePageId.value) + 1))
const activeScene = computed(() => focusedPages.value[0]?.resolved_scenes?.[sceneIndex.value])
watch(activePageId, () => { sceneIndex.value = 0 })
watch(() => props.reviewOnly, value => {
  if (value) { editing.value = false; selectingPages.value = false; arrangementOpen.value = false }
})

watch(() => props.state.revision, () => {
  const pages = Array.isArray(manuscript.value?.pages) ? manuscript.value.pages : []
  draftPages.value = teacherFacingPages(pages)
  originalPages.value = teacherFacingPages(pages)
  draftPacing.value = manuscript.value?.pacing ? JSON.parse(JSON.stringify(manuscript.value.pacing)) : null
  selectedPageIds.value = new Set()
  if (finishRequested) { editing.value = false; finishRequested = false }
  if (!pages.some((page: any) => page.page_id === activePageId.value)) activePageId.value = pages[0]?.page_id || ''
  sceneIndex.value = 0
}, { immediate: true })

const narrativeBrief = computed(() => manuscript.value?.narrative_brief || null)
const dirtyUpdates = computed(() => draftPages.value.flatMap((page, index): Record<string, any>[] => {
  const original = originalPages.value[index]
  if (!original || JSON.stringify(page) === JSON.stringify(original)) return []
  if (page.teaching) return [{ page_id: page.page_id, title: page.title, teaching: page.teaching, layout_id: page.layout_id, page_goal: page.page_goal,
    primary_claim: page.primary_claim, audience_question: page.audience_question, audience_action: page.audience_action,
    expected_response: page.expected_response, observable_evidence: page.observable_evidence, transition: page.transition,
    composition_notes: page.composition_notes, teacher_locked: Boolean(page.teacher_locked) }]
  return [{ page_id: page.page_id, title: page.title, visible_copy: page.visible_copy, page_goal: page.page_goal, primary_claim: page.primary_claim, audience_question: page.audience_question, audience_action: page.audience_action, expected_response: page.expected_response, observable_evidence: page.observable_evidence, transition: page.transition, reveal_steps: page.reveal_steps, composition_notes: page.composition_notes, teacher_locked: Boolean(page.teacher_locked) }]
}))
const pacingDirty = computed(() => JSON.stringify(draftPacing.value) !== JSON.stringify(manuscript.value?.pacing || null))
const dirty = computed(() => dirtyUpdates.value.length > 0 || pacingDirty.value)
watch(dirty, value => emit('dirty-change', value), { immediate: true })
function pendingChanges() {
  return { updates: dirtyUpdates.value, pacing: pacingDirty.value && draftPacing.value ? draftPacing.value : undefined }
}
defineExpose({ pendingChanges })
const allIssues = computed(() => props.state.quality_report ? [...props.state.quality_report.issues, ...props.state.quality_report.suggestions] : [...(manuscript.value?.quality_issues || []), ...(manuscript.value?.quality_suggestions || [])])
const lessonIssues = computed(() => allIssues.value.filter((item: any) => !item.page_id))
const saveStateLabel = computed(() => props.saving ? t('pptWorkspace.savingManuscript', '正在保存…') : dirty.value ? t('pptWorkspace.manuscriptUnsaved', '有未保存修改') : t('pptWorkspace.manuscriptSaved', '已保存'))

const failureView = computed(() => pptFailurePresentation(props.failure, props.error, 'manuscript', Boolean(manuscript.value)))
const retryLabel = computed(() => failureView.value ? t('pptWorkspace.retryManuscript', '重新生成页面内容稿') : t('pptWorkspace.generateManuscript', '生成页面内容稿'))

function togglePageSelection() { selectingPages.value = !selectingPages.value; selectedPageIds.value = new Set() }
function selectPage(pageId: string) { activePageId.value = pageId }
function cancelEditing() {
  draftPages.value = JSON.parse(JSON.stringify(originalPages.value))
  draftPacing.value = manuscript.value?.pacing ? JSON.parse(JSON.stringify(manuscript.value.pacing)) : null
  finishRequested = false
  editing.value = false
}
function finishEditing() {
  if (!dirty.value) { editing.value = false; return }
  finishRequested = true
  saveDraft()
}
function saveDraft() { if (pacingDirty.value && draftPacing.value) emit('save-manuscript', dirtyUpdates.value, draftPacing.value); else if (dirtyUpdates.value.length) emit('save-manuscript', dirtyUpdates.value) }
function syncTitleRegion(page: Record<string, any>) { const regions = Array.isArray(page.regions) ? page.regions.filter((item: any) => item.content_kind !== 'notes') : []; const titleIndex = regions.findIndex((item: any) => item.content_kind === 'title'); if (titleIndex >= 0 && Array.isArray(page.visible_copy)) page.visible_copy[titleIndex] = page.title }
function toggleLock(page: Record<string, any>) { page.teacher_locked = !page.teacher_locked; if (page.teacher_locked) selectedPageIds.value.delete(page.page_id) }
function toggleSelected(pageId: string) { const next = new Set(selectedPageIds.value); next.has(pageId) ? next.delete(pageId) : next.add(pageId); selectedPageIds.value = next }
function canRegenerate(page: Record<string, any>) { return !page.teacher_locked && !page.continuation_of_page_id && !['cover', 'agenda', 'summary'].includes(page.page_type) }
function setLines(page: Record<string, any>, field: string, event: Event) { page[field] = (event.target as HTMLTextAreaElement).value.split('\n').map(value => value.trim()).filter(Boolean) }
function listLines(value: unknown) { return Array.isArray(value) ? value.join('\n') : '' }
function listText(value: unknown) { return Array.isArray(value) ? value.join(' → ') : '' }
function teacherFacingPages(pages: Record<string, any>[]) {
  return JSON.parse(JSON.stringify(pages)).map((page: Record<string, any>) => {
    const previousTitle = String(page.title || '')
    const currentTitle = teacherFacingTeachingLabel(previousTitle)
    page.title = currentTitle
    if (Array.isArray(page.visible_copy)) {
      page.visible_copy = page.visible_copy.map((line: unknown) => String(line || '') === previousTitle ? currentTitle : line)
    }
    return page
  })
}
function pageIssues(pageId: string) { return allIssues.value.filter((item: any) => item.page_id === pageId) }
function sourceIds(page: Record<string, any>, field: string): string[] { const values = page?.[field]; return Array.isArray(values) ? values.map(String).filter(Boolean) : [] }
function hasSourceRefs(page: Record<string, any>) { return ['source_script_block_ids', 'source_section_ids', 'source_material_evidence_ids'].some(field => sourceIds(page, field).length) }
</script>

<style scoped>
.ppt-manuscript-workflow{height:100%;width:100%;min-height:0;display:flex;flex-direction:column;background:var(--lz-bg-page,#f5f6f8);color:var(--lz-text-primary,#172033);font-size:16px;line-height:1.65;padding:20px 24px;box-sizing:border-box;overflow:auto}
.ppt-manuscript-workflow__header{flex:none;display:flex;align-items:center;gap:14px}
.ppt-manuscript-workflow__header h1{margin:0;font-size:24px}
.ppt-manuscript-command-bar{max-width:none;flex:1;margin-bottom:12px}
.ppt-manuscript-page-count{font-size:15px;color:#526077}
.ppt-manuscript-workflow__content{flex:1;min-height:0;display:flex;flex-direction:column}
.ppt-manuscript-workflow__pages{flex:1;min-height:0;display:grid;grid-template-columns:200px minmax(0,1fr);overflow:hidden;background:#fff;border:1px solid #e3e7ef;border-radius:10px}
.ppt-manuscript-workflow__page-list{min-width:0;overflow:auto;border-right:1px solid #e5e9f0;padding:12px 8px}
.ppt-page-list-heading{display:flex;justify-content:space-between;align-items:center;padding:0 8px 12px;font-size:15px}
.ppt-page-list-heading strong{font-weight:650}
.ppt-page-list-heading button,.ppt-page-list-selection button,.ppt-manuscript-workflow__lock{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:4px 8px;border:1px solid #e0e5ee;border-radius:6px;background:#fff;color:#526077;font:inherit;font-size:15px;cursor:pointer}
.ppt-page-list-selection{padding:0 4px 12px}
.ppt-page-list-selection button{width:100%;font-size:15px;justify-content:center}
.ppt-manuscript-workflow__page-rail{display:flex;align-items:center;gap:6px;margin-bottom:3px;border-radius:6px;padding:0 3px}
.ppt-manuscript-workflow__page-rail.is-active{background:#f0effc}
.ppt-manuscript-workflow__page-rail button{flex:1;min-width:0;display:grid;grid-template-columns:22px minmax(0,1fr) auto;align-items:baseline;gap:6px;padding:10px 5px;border:0;border-radius:6px;background:transparent;color:#475569;text-align:left;font:inherit;font-size:15px;line-height:1.65;cursor:pointer}
.ppt-manuscript-workflow__page-rail.is-active button{color:#4338ca;font-weight:650}
.ppt-manuscript-workflow__page-rail button>span:first-child{color:#667085;font-size:15px}
.ppt-manuscript-workflow__page-rail button:hover{background:#f3f4f8}
.ppt-manuscript-workflow__page-rail input{accent-color:#514bdc;width:16px;height:16px;flex:none}
.ppt-manuscript-workflow__page-rail :deep(.math-text){overflow-wrap:anywhere}
.ppt-manuscript-workflow__pages article{min-width:0;overflow:auto;padding:20px 30px 40px}
.ppt-manuscript-workflow__page-copy{max-width:900px;margin:auto}
.ppt-manuscript-workflow__page-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:24px}
.ppt-manuscript-workflow__reading h2{margin:0 0 24px;font-size:25px;font-weight:700;line-height:1.5;color:#202b40}
.ppt-page-reading-copy{font-size:17px;line-height:1.9}
.ppt-page-reading-copy :deep(p){margin:0 0 16px}
.ppt-manuscript-workflow__lesson-plan{padding:12px 18px;margin-bottom:12px;background:#fff;border:1px solid #e3e7ef;border-radius:8px;max-height:40vh;overflow:auto}
.ppt-manuscript-workflow__brief{display:grid;gap:8px}
.ppt-manuscript-workflow__brief div{display:flex;gap:16px}.ppt-manuscript-workflow__brief small{min-width:120px;font-size:15px;color:#526077}
.ppt-manuscript-workflow__pacing{display:grid;grid-template-columns:160px 1fr;gap:10px 20px}.ppt-manuscript-workflow__pacing p{grid-column:1/-1;margin:0}
.ppt-manuscript-workflow__page-copy label,.ppt-manuscript-workflow__pacing label{display:flex;flex-direction:column;gap:7px;margin:16px 0;color:#526077;font-size:15px}
.ppt-manuscript-workflow :is(input:not([type=checkbox]),textarea,select){font:inherit;line-height:1.7;padding:9px 12px;border:1px solid #d6dce6;border-radius:7px;color:#243247;background:#fff;max-width:100%;box-sizing:border-box}
.ppt-manuscript-workflow textarea{width:100%;resize:vertical}
.ppt-manuscript-workflow__title-field input{font-size:22px;font-weight:650}
.ppt-manuscript-workflow__preview{margin-bottom:20px}
.ppt-manuscript-workflow__preview :deep(.ppt-scene){height:auto;border:1px solid #e3e7ef}
.ppt-layout-pending{padding:24px 0;margin:0;color:#526077;font-size:16px}
.ppt-manuscript-workflow__preview-status{display:flex;justify-content:space-between;align-items:center;gap:10px;color:#526077;font-size:15px;margin-top:8px}
.ppt-manuscript-workflow__preview-status label{display:flex;flex-direction:row;align-items:center;margin:0}
.ppt-manuscript-workflow__teaching-notes,.ppt-manuscript-workflow__sources{border-top:1px solid #e8ebf1;margin-top:32px;padding-top:12px;color:#526077;font-size:15px}
.ppt-manuscript-workflow summary{width:fit-content;cursor:pointer;font-weight:600;padding:4px 0}
.ppt-manuscript-workflow__field-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}
.ppt-manuscript-workflow__field-grid :deep(p),.ppt-manuscript-workflow__teaching-notes label :deep(p){margin:0;color:#243247;font-size:16px}
.ppt-manuscript-workflow__sources dl>div{display:grid;grid-template-columns:110px 1fr;gap:12px}.ppt-manuscript-workflow__sources dd{margin:0;overflow-wrap:anywhere}.ppt-manuscript-workflow__sources code{display:block;font-size:15px}
.ppt-manuscript-workflow__warning{display:flex;gap:10px;margin:0 0 12px;padding:10px 14px;background:#fff8ec;color:#85520b;font-size:15px}
.ppt-manuscript-workflow__issues{margin:0 0 12px;padding:10px 14px 10px 30px;color:#85520b;background:#fff8ec;font-size:15px}
.ppt-manuscript-workflow :deep(.app-error-notice){margin-bottom:12px}
.ppt-manuscript-workflow :deep(.app-error-notice :is(strong,p,summary)){font-size:15px}
.ppt-manuscript-workflow__empty,.ppt-manuscript-workflow__original{margin:auto;max-width:520px;padding:40px;text-align:center;color:#526077}
.ppt-manuscript-workflow__empty h2,.ppt-manuscript-workflow__original h2{font-size:22px;color:#202b40}
.ppt-manuscript-workflow :is(button,input,textarea,select,summary):focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.ppt-manuscript-workflow button:disabled{opacity:.48;cursor:not-allowed}
.ppt-manuscript-workflow.is-embedded{padding:12px 0 0;background:transparent}
.ppt-manuscript-workflow.is-embedded :deep(.teacher-document-command-bar__context){gap:12px;flex-wrap:wrap;white-space:normal}
@media (max-width:1366px){.ppt-manuscript-workflow__pages{grid-template-columns:180px minmax(0,1fr)}.ppt-manuscript-workflow__pages article{padding:18px 24px 32px}.ppt-manuscript-page-count{display:none}}
.has-external-actions .ppt-manuscript-workflow__pages{display:flex;flex-direction:column;border:0;border-radius:0;min-height:0}
.has-external-actions .ppt-manuscript-workflow__pages article{flex:1;padding:24px 28px 40px}
.has-external-actions .ppt-manuscript-workflow__page-list{max-height:240px;border-right:0;border-bottom:1px solid #e5e9f0}
.ppt-manuscript-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 24px;border-bottom:1px solid #e5e9f0;background:#fff}
.has-external-actions .ppt-manuscript-workflow__page-copy{max-width:860px}
</style>
