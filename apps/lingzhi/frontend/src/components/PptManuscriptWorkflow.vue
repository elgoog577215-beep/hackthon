<template>
  <section class="ppt-manuscript-workflow" data-testid="ppt-manuscript-workflow">
    <header class="ppt-manuscript-workflow__header">
      <button type="button" :aria-label="t('pptWorkspace.backToProduction')" class="ppt-manuscript-workflow__back" @click="emit('back')"><ArrowLeft :size="18" /></button>
      <div>
        <h1><MathText :content="title" /></h1>
      </div>
      <footer v-if="state.generation_branch !== 'original_ppt_review'" class="ppt-manuscript-workflow__actions">
        <template v-if="manuscript && state.source_state === 'stale'">
          <button type="button" :disabled="busy || dirty" data-testid="regenerate-affected-ppt-pages" @click="emit('regenerate-pages', [])"><RefreshCw :size="17" />{{ regenerating ? t('pptWorkspace.regeneratingPages', '正在重新生成…') : t('pptWorkspace.regenerateAffectedPages', '只重新生成受影响页') }}</button>
          <button type="button" class="is-primary" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')"><Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : t('pptWorkspace.regenerateManuscript', '重新生成整份页面内容稿') }}</button>
        </template>
        <button v-else-if="!manuscript" type="button" class="is-primary" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')"><Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : retryLabel }}</button>
        <template v-else>
          <span class="ppt-manuscript-workflow__save-state" role="status">{{ saveStateLabel }}</span>
          <button type="button" :disabled="busy || selectedPageIds.size === 0 || dirty" data-testid="regenerate-selected-ppt-pages" @click="emit('regenerate-pages', [...selectedPageIds])"><RefreshCw :size="17" />{{ regenerating ? t('pptWorkspace.regeneratingPages', '正在重新生成…') : t('pptWorkspace.regenerateSelectedPages', '重新生成选中页') }}</button>
          <button type="button" :disabled="busy || !dirty" data-testid="save-ppt-manuscript" @click="saveDraft"><Save :size="17" />{{ saving ? t('pptWorkspace.savingManuscript', '正在保存…') : t('pptWorkspace.saveManuscript', '保存修改') }}</button>
          <button v-if="state.status === 'draft'" type="button" class="is-primary" :disabled="busy || dirty || !state.confirmable" data-testid="confirm-ppt-manuscript" @click="emit('confirm-manuscript')"><Check :size="17" />{{ confirming ? t('pptWorkspace.confirmingManuscript', '正在确认…') : t('pptWorkspace.confirmManuscript', '确认页面内容稿') }}</button>
          <button v-else type="button" class="is-primary" :disabled="busy || dirty || !state.can_generate_ppt" data-testid="generate-ppt-from-manuscript" @click="emit('generate-ppt')"><Presentation :size="17" />{{ busy ? t('pptWorkspace.generatingDeck', '正在生成 PPT…') : t('pptWorkspace.generateDeck', '根据已确认页面内容稿生成 PPT') }}</button>
        </template>
      </footer>
    </header>

    <div v-if="state.generation_branch === 'original_ppt_review'" class="ppt-manuscript-workflow__original">
      <FileCheck2 :size="28" />
      <h2>{{ t('pptWorkspace.originalPptBranchTitle', '本讲已有原版 PPT') }}</h2>
      <p>{{ t('pptWorkspace.originalPptBranchDescription', '请返回课程生产页，继续原版 PPT 的审阅与确认。') }}</p>
      <button type="button" @click="emit('back')">{{ t('pptWorkspace.backToProduction', '返回课程生产页') }}</button>
    </div>

    <template v-else>
      <div v-if="state.source_state === 'stale'" class="ppt-manuscript-workflow__warning"><TriangleAlert :size="18" /><span>{{ t('pptWorkspace.manuscriptStale', '教案、讲义或资料已经变化，请重新生成页面内容稿。') }}</span></div>
      <div v-if="failureView" class="ppt-manuscript-workflow__warning is-error" role="alert" data-testid="ppt-manuscript-failure"><TriangleAlert :size="18" /><div><strong>{{ failureView.title }}</strong><p>{{ failureView.message }}</p><small v-if="failureView.code">{{ t('pptWorkspace.failureCode', '问题代码') }}：<code>{{ failureView.code }}</code></small></div></div>

      <main v-if="manuscript" class="ppt-manuscript-workflow__content">
        <details class="ppt-manuscript-workflow__lesson-plan">
          <summary>{{ t('pptWorkspace.lessonArrangement') }} · {{ manuscriptPageCounts }}</summary>
        <section v-if="narrativeBrief" class="ppt-manuscript-workflow__brief" data-testid="ppt-narrative-brief">
          <div><small>{{ t('pptWorkspace.narrativeQuestion', '整讲中心问题') }}</small><strong>{{ narrativeBrief.central_question }}</strong></div>
          <div><small>{{ t('pptWorkspace.learningPath', '学习路径') }}</small><span>{{ listText(narrativeBrief.learning_path) }}</span></div>
          <div><small>{{ t('pptWorkspace.observableCheckpoints', '可观察检查点') }}</small><span>{{ listText(narrativeBrief.observable_checkpoints) }}</span></div>
          <span v-if="narrativeBrief.time_budget_minutes > 0" class="ppt-manuscript-workflow__time">{{ narrativeBrief.time_budget_minutes }} {{ t('pptWorkspace.minutes', '分钟') }}</span>
        </section>

        <section v-if="draftPacing" class="ppt-manuscript-workflow__pacing" data-testid="ppt-pacing-plan">
          <label><span>{{ t('pptWorkspace.pacingBudget') }}</span><input v-model.number="draftPacing.max_physical_pages" type="number" min="1" max="5000" :disabled="busy" data-testid="ppt-pacing-budget"></label>
          <label><span>{{ t('pptWorkspace.pacingRationale') }}</span><textarea v-model="draftPacing.rationale" :disabled="busy" rows="2" /></label>
          <p>{{ t('pptWorkspace.pacingSavedCount').replace('{count}', String(manuscript.page_count)) }}</p>
        </section>
        </details>
        <ul v-if="lessonIssues.length" class="ppt-manuscript-workflow__issues" role="alert"><li v-for="issue in lessonIssues" :key="issue.code">{{ issue.message }}</li></ul>
        <div class="ppt-manuscript-workflow__pages">
          <nav class="ppt-manuscript-workflow__page-list" :aria-label="t('pptWorkspace.pageNavigation')">
            <div v-for="item in draftPages" :key="item.page_id" class="ppt-manuscript-workflow__page-rail" :class="{ 'is-active': activePageId === item.page_id }">
              <input type="checkbox" :aria-label="`${t('pptWorkspace.selectPage')} ${item.page_number}`" :checked="selectedPageIds.has(item.page_id)" :disabled="busy || !canRegenerate(item)" @change="toggleSelected(item.page_id)">
              <button type="button" :aria-current="activePageId === item.page_id ? 'page' : undefined" :data-page-id="item.page_id" @click="activePageId = item.page_id">
                <span>{{ item.page_number }}</span><MathText :content="item.title" />
                <Lock v-if="item.teacher_locked" :size="15" :aria-label="t('pptWorkspace.pageLocked')" />
              </button>
            </div>
          </nav>
          <article v-for="page in focusedPages" :key="page.page_id" :class="{ 'is-selected': selectedPageIds.has(page.page_id), 'is-locked': page.teacher_locked }">
            <div class="ppt-manuscript-workflow__page-copy">
              <div class="ppt-manuscript-workflow__page-meta">
                <UiSegmentedControl v-model="editorMode" :options="editorModes" :accessibility-label="t('pptWorkspace.pageEditing')" />
                <button type="button" class="ppt-manuscript-workflow__lock" :disabled="busy" @click="toggleLock(page)"><Lock v-if="page.teacher_locked" :size="15" /><Unlock v-else :size="15" />{{ page.teacher_locked ? t('pptWorkspace.pageLocked', '已锁定') : t('pptWorkspace.lockPage', '锁定本页') }}</button>
              </div>

              <div class="ppt-manuscript-workflow__preview" data-testid="ppt-page-preview">
                <PptSceneCanvas v-if="activeScene" :scene="activeScene" />
                <div v-else class="ppt-manuscript-workflow__text-preview"><h2><MathText :content="page.title" /></h2><MathText v-for="(line, index) in (page.visible_copy || []).filter((line: string) => line !== page.title)" :key="index" :content="line" /></div>
                <div class="ppt-manuscript-workflow__preview-status">
                  <span>{{ dirty ? t('pptWorkspace.previewSaveRequired') : t('pptWorkspace.savedPagePreview') }}</span>
                  <label v-if="page.resolved_scenes?.length > 1"><span>{{ t('pptWorkspace.previewState') }}</span><select v-model.number="sceneIndex"><option v-for="(_scene, index) in page.resolved_scenes" :key="index" :value="index">{{ index + 1 }} / {{ page.resolved_scenes.length }}</option></select></label>
                </div>
              </div>
              <template v-if="editorMode === 'content'">
              <label class="ppt-manuscript-workflow__title-field"><span>{{ t('pptWorkspace.pageTitle', '页面标题') }}</span><input v-model="page.title" :disabled="busy" @input="syncTitleRegion(page)"></label>
              </template>
              <PptTeachingEditor v-if="page.teaching" :page="page" :disabled="Boolean(busy)" :section="editorMode" :layouts="state.layouts || []" />
              <template v-else>
                <div v-if="editorMode === 'content'" class="ppt-manuscript-workflow__visible-copy"><span>{{ t('pptWorkspace.visibleCopy') }}</span><textarea v-for="(_line, index) in page.visible_copy || []" :key="`${page.page_id}-copy-${index}`" v-model="page.visible_copy[index]" :disabled="busy" rows="2" :aria-label="`${t('pptWorkspace.visibleCopy')} ${index + 1}`" /></div>
                <label v-else><span>{{ t('pptWorkspace.revealSteps') }}</span><textarea :value="listLines(page.reveal_steps)" :disabled="busy" rows="3" @input="setLines(page, 'reveal_steps', $event)" /></label>
              </template>
              <details class="ppt-manuscript-workflow__teaching-notes"><summary>{{ t('pptWorkspace.teachingNotes') }}</summary>
              <div class="ppt-manuscript-workflow__field-grid">
                <label><span>{{ t('pptWorkspace.pageGoal', '页面目标') }}</span><textarea v-model="page.page_goal" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.primaryClaim', '核心结论') }}</span><textarea v-model="page.primary_claim" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.audienceQuestion', '学习者问题') }}</span><textarea v-model="page.audience_question" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.audienceAction', '学习者行动') }}</span><textarea v-model="page.audience_action" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.expectedResponse', '预期反应') }}</span><textarea v-model="page.expected_response" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.observableEvidence', '达成证据') }}</span><textarea v-model="page.observable_evidence" :disabled="busy" rows="2" /></label>
              </div>

              <label><span>{{ t('pptWorkspace.pageTransition', '与前后页的衔接') }}</span><textarea v-model="page.transition" :disabled="busy" rows="2" /></label>
              <label><span>{{ t('pptWorkspace.compositionNotes', '构图意图') }}</span><textarea v-model="page.composition_notes" :disabled="busy" rows="2" /></label>

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
import { ArrowLeft, Check, FileCheck2, Lock, Presentation, RefreshCw, Save, ScrollText, Sparkles, TriangleAlert, Unlock } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'
import PptTeachingEditor from './PptTeachingEditor.vue'
import PptSceneCanvas from './PptSceneCanvas.vue'
import UiSegmentedControl from './UiSegmentedControl.vue'

const props = defineProps<{ title: string; state: Record<string, any>; busy?: boolean; confirming?: boolean; saving?: boolean; regenerating?: boolean; error?: string; failure?: Record<string, any> | null }>()
const emit = defineEmits<{
  (event: 'back'): void
  (event: 'generate-manuscript'): void
  (event: 'regenerate-manuscript'): void
  (event: 'confirm-manuscript'): void
  (event: 'generate-ppt'): void
  (event: 'save-manuscript', updates: Record<string, any>[], pacing?: Record<string, any>): void
  (event: 'regenerate-pages', pageIds: string[]): void
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
const sceneIndex = ref(0)
const editorModes = computed(() => [{ value: 'content', label: t('pptWorkspace.editPageContent') }, { value: 'layout', label: t('pptWorkspace.editPageLayout') }])
const focusedPages = computed(() => draftPages.value.filter(page => page.page_id === activePageId.value))
const activeScene = computed(() => focusedPages.value[0]?.resolved_scenes?.[sceneIndex.value])
watch(activePageId, () => { sceneIndex.value = 0 })

watch(() => props.state.revision, () => {
  const pages = Array.isArray(manuscript.value?.pages) ? manuscript.value.pages : []
  draftPages.value = JSON.parse(JSON.stringify(pages))
  originalPages.value = JSON.parse(JSON.stringify(pages))
  draftPacing.value = manuscript.value?.pacing ? JSON.parse(JSON.stringify(manuscript.value.pacing)) : null
  selectedPageIds.value = new Set()
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
const allIssues = computed(() => props.state.quality_report ? [...props.state.quality_report.issues, ...props.state.quality_report.suggestions] : [...(manuscript.value?.quality_issues || []), ...(manuscript.value?.quality_suggestions || [])])
const lessonIssues = computed(() => allIssues.value.filter((item: any) => !item.page_id))
const saveStateLabel = computed(() => props.saving ? t('pptWorkspace.savingManuscript', '正在保存…') : dirty.value ? t('pptWorkspace.manuscriptUnsaved', '有未保存修改') : t('pptWorkspace.manuscriptSaved', '已保存'))

const failureView = computed(() => {
  const failure = props.failure || null
  const code = String(failure?.code || '')
  if (code === 'story_ai_batch_request_budget_exceeded') return { code, title: t('pptWorkspace.manuscriptBudgetRecoveredTitle', '页面内容稿输入已自动压缩'), message: t('pptWorkspace.manuscriptBudgetRecoveredMessage', '系统已移除重复上下文并保留全部讲义块，可直接重新生成当前页面内容稿。') }
  if (code.startsWith('story_title_') || code === 'duplicate_slide_title') return { code, title: t('pptWorkspace.manuscriptTitleRecoveryTitle', '页面标题候选不足'), message: t('pptWorkspace.manuscriptTitleRecoveryMessage', '系统会优先使用当前可用讲义块标题重新规划，不会发布重复或残缺标题页。') }
  if (code.endsWith('_rate_limited')) return { code, title: t('pptWorkspace.manuscriptRateLimitedTitle', '页面内容稿模型暂时繁忙'), message: t('pptWorkspace.manuscriptRateLimitedMessage', '已完成内容和旧版本均已保留，稍后可直接重试。') }
  if (code.endsWith('_authentication') || code.endsWith('_balance_unavailable')) return { code, title: t('pptWorkspace.manuscriptProviderBlockedTitle', '页面内容稿模型当前不可用'), message: String(failure?.message || t('pptWorkspace.manuscriptProviderBlockedMessage', '请检查模型凭证或额度后再重试。')) }
  if (failure) return { code, title: t('pptWorkspace.manuscriptGenerationFailedTitle', '页面内容稿未生成'), message: String(failure.message || t('pptWorkspace.manuscriptGenerationFailedMessage', '系统已保留现有内容，可重新生成。')) }
  if (props.error) return { code: '', title: t('pptWorkspace.manuscriptOperationFailedTitle', '当前操作未完成'), message: props.error }
  return null
})
const retryLabel = computed(() => failureView.value ? t('pptWorkspace.retryManuscript', '重新生成页面内容稿') : t('pptWorkspace.generateManuscript', '生成页面内容稿'))

function saveDraft() { if (pacingDirty.value && draftPacing.value) emit('save-manuscript', dirtyUpdates.value, draftPacing.value); else if (dirtyUpdates.value.length) emit('save-manuscript', dirtyUpdates.value) }
function syncTitleRegion(page: Record<string, any>) { const regions = Array.isArray(page.regions) ? page.regions.filter((item: any) => item.content_kind !== 'notes') : []; const titleIndex = regions.findIndex((item: any) => item.content_kind === 'title'); if (titleIndex >= 0 && Array.isArray(page.visible_copy)) page.visible_copy[titleIndex] = page.title }
function toggleLock(page: Record<string, any>) { page.teacher_locked = !page.teacher_locked; if (page.teacher_locked) selectedPageIds.value.delete(page.page_id) }
function toggleSelected(pageId: string) { const next = new Set(selectedPageIds.value); next.has(pageId) ? next.delete(pageId) : next.add(pageId); selectedPageIds.value = next }
function canRegenerate(page: Record<string, any>) { return !page.teacher_locked && !page.continuation_of_page_id && !['cover', 'agenda', 'summary'].includes(page.page_type) }
function setLines(page: Record<string, any>, field: string, event: Event) { page[field] = (event.target as HTMLTextAreaElement).value.split('\n').map(value => value.trim()).filter(Boolean) }
function listLines(value: unknown) { return Array.isArray(value) ? value.join('\n') : '' }
function listText(value: unknown) { return Array.isArray(value) ? value.join(' → ') : '' }
function pageIssues(pageId: string) { return allIssues.value.filter((item: any) => item.page_id === pageId) }
function sourceIds(page: Record<string, any>, field: string): string[] { const values = page?.[field]; return Array.isArray(values) ? values.map(String).filter(Boolean) : [] }
function hasSourceRefs(page: Record<string, any>) { return ['source_script_block_ids', 'source_section_ids', 'source_material_evidence_ids'].some(field => sourceIds(page, field).length) }
</script>

<style scoped>
.ppt-manuscript-workflow{height:100%;width:100%;overflow:auto;padding:24px 28px;background:var(--lz-bg-page,#f5f6f8);color:var(--lz-text-primary,#172033);font-size:16px;line-height:1.6}
.ppt-manuscript-workflow__header{display:flex;align-items:center;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.ppt-manuscript-workflow__header h1{margin:0;font-size:24px;line-height:1.4}
.ppt-manuscript-workflow button{font:inherit;cursor:pointer;border:1px solid #d8dde7;border-radius:8px;background:#fff;color:#344054;padding:8px 12px;display:inline-flex;align-items:center;justify-content:center;gap:8px}
.ppt-manuscript-workflow button:hover:not(:disabled){background:#eef0ff;border-color:#a5a5ed}
.ppt-manuscript-workflow button:active:not(:disabled){background:#e4e7ff}
.ppt-manuscript-workflow :is(button,input,textarea,select,summary):focus-visible{outline:2px solid var(--lz-brand-strong,#4f46e5);outline-offset:2px}
.ppt-manuscript-workflow button:disabled{opacity:.5;cursor:not-allowed}
.ppt-manuscript-workflow__back{width:40px;height:40px;flex-shrink:0}
.ppt-manuscript-workflow__actions{margin-left:auto;display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap}
.ppt-manuscript-workflow button.is-primary{color:#fff;background:var(--lz-brand-strong,#4f46e5);border-color:transparent}
.ppt-manuscript-workflow button.is-primary:hover:not(:disabled){background:#4338ca}
.ppt-manuscript-workflow__save-state{color:#475467;font-size:15px}
.ppt-manuscript-workflow__lesson-plan{margin-bottom:16px}
.ppt-manuscript-workflow summary{cursor:pointer;padding:8px 0;font-weight:600}
.ppt-manuscript-workflow__brief{display:grid;gap:8px;padding:12px 0}
.ppt-manuscript-workflow__brief div{display:flex;gap:16px}.ppt-manuscript-workflow__brief small{min-width:130px;font-size:15px;color:#475467}
.ppt-manuscript-workflow__pacing{display:grid;grid-template-columns:160px 1fr;gap:12px 20px;max-width:820px}.ppt-manuscript-workflow__pacing p{grid-column:1/-1;margin:0}
.ppt-manuscript-workflow__pages{display:grid;grid-template-columns:240px minmax(0,1fr);gap:28px;align-items:start}
.ppt-manuscript-workflow__page-list{position:sticky;top:0;max-height:calc(100vh - 180px);overflow:auto}
.ppt-manuscript-workflow__page-rail{display:flex;align-items:center;gap:6px;margin-bottom:6px;padding:4px;border-radius:8px}
.ppt-manuscript-workflow__page-rail.is-active{background:#e9ebff}
.ppt-manuscript-workflow__page-rail button{flex:1;justify-content:flex-start;text-align:left;border-color:transparent;background:transparent;min-width:0;align-items:baseline;padding:8px}
.ppt-manuscript-workflow__page-rail button>span:first-child{flex-shrink:0;width:24px;color:#475467}
.ppt-manuscript-workflow__page-rail :deep(.math-text){overflow-wrap:anywhere}
.ppt-manuscript-workflow__pages article{min-width:0;background:#fff;padding:20px 24px;border-radius:12px}
.ppt-manuscript-workflow__page-meta{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;gap:16px}
.ppt-manuscript-workflow__page-meta :deep(.ui-segmented-control button){font-size:15px}
.ppt-manuscript-workflow__preview{margin-bottom:20px}
.ppt-manuscript-workflow__preview :deep(.ppt-scene){height:auto;border:1px solid #d8dde7}
.ppt-manuscript-workflow__preview-status{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#475467;font-size:15px;margin-top:8px}
.ppt-manuscript-workflow__preview-status label{display:flex;align-items:center;gap:8px;margin:0}
.ppt-manuscript-workflow__text-preview{padding:24px;background:#f8f9fc;display:grid;gap:16px}.ppt-manuscript-workflow__text-preview h2{margin:0;font-size:24px}
.ppt-manuscript-workflow__page-copy label,.ppt-manuscript-workflow__pacing label{display:flex;flex-direction:column;gap:6px;margin:12px 0}
.ppt-manuscript-workflow :is(input:not([type=checkbox]),textarea,select){font:inherit;line-height:1.6;padding:8px 10px;border:1px solid #cdd3df;border-radius:6px;color:inherit;background:#fff;max-width:100%;box-sizing:border-box}
.ppt-manuscript-workflow textarea{width:100%;resize:vertical}.ppt-manuscript-workflow__title-field input{font-size:20px;font-weight:650}
.ppt-manuscript-workflow__teaching-notes,.ppt-manuscript-workflow__sources{border-top:1px solid #e4e7ec;margin-top:18px;padding-top:8px}
.ppt-manuscript-workflow__field-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}
.ppt-manuscript-workflow__sources dl>div{display:grid;grid-template-columns:110px 1fr;gap:12px;margin:8px 0}.ppt-manuscript-workflow__sources dd{margin:0;overflow-wrap:anywhere}.ppt-manuscript-workflow__sources code{display:block;font-size:15px}
.ppt-manuscript-workflow__warning{display:flex;align-items:flex-start;gap:10px;margin-bottom:16px;padding:12px 16px;background:#fff7e8;color:#85520b;border-radius:8px}.ppt-manuscript-workflow__warning.is-error{background:#fff0f0;color:#8f1712}.ppt-manuscript-workflow__warning p{margin:4px 0}
.ppt-manuscript-workflow__issues{padding:12px 16px 12px 32px;background:#fff7e8;color:#85520b;border-radius:8px}
.ppt-manuscript-workflow__empty,.ppt-manuscript-workflow__original{padding:60px 24px;text-align:center;color:#475467}.ppt-manuscript-workflow__empty h2{font-size:24px}
</style>
