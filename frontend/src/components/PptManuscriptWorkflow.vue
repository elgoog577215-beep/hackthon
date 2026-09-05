<template>
  <section class="ppt-manuscript-workflow" data-testid="ppt-manuscript-workflow">
    <header class="ppt-manuscript-workflow__header">
      <button type="button" class="ppt-manuscript-workflow__back" @click="emit('back')"><ArrowLeft :size="18" /></button>
      <div>
        <small>{{ t('pptWorkspace.manuscriptWorkflowEyebrow', 'PPT 生成') }}</small>
        <h1><MathText :content="title" /></h1>
        <p>{{ t('pptWorkspace.manuscriptWorkflowDescription', '先确认每页怎样教，再生成可编辑 PPT。') }}</p>
      </div>
    </header>

    <div v-if="state.generation_branch === 'original_ppt_review'" class="ppt-manuscript-workflow__original">
      <FileCheck2 :size="28" />
      <h2>{{ t('pptWorkspace.originalPptBranchTitle', '本讲已有原版 PPT') }}</h2>
      <p>{{ t('pptWorkspace.originalPptBranchDescription', '请返回课程生产页，继续原版 PPT 的审阅与确认。') }}</p>
      <button type="button" @click="emit('back')">{{ t('pptWorkspace.backToProduction', '返回课程生产页') }}</button>
    </div>

    <template v-else>
      <ol class="ppt-manuscript-workflow__steps">
        <li :class="stepClass(1)"><span>1</span><div><strong>{{ t('pptWorkspace.stepGenerateManuscript', '生成页面内容稿') }}</strong><small>{{ manuscriptStepStatus }}</small></div></li>
        <li :class="stepClass(2)"><span>2</span><div><strong>{{ t('pptWorkspace.stepGenerateDeck', '生成 PPT') }}</strong><small>{{ deckStepStatus }}</small></div></li>
      </ol>

      <div v-if="state.source_state === 'stale'" class="ppt-manuscript-workflow__warning"><TriangleAlert :size="18" /><span>{{ t('pptWorkspace.manuscriptStale', '教案、讲义或资料已经变化，请重新生成页面内容稿。') }}</span></div>
      <div v-if="failureView" class="ppt-manuscript-workflow__warning is-error" role="alert" data-testid="ppt-manuscript-failure"><TriangleAlert :size="18" /><div><strong>{{ failureView.title }}</strong><p>{{ failureView.message }}</p><small v-if="failureView.code">{{ t('pptWorkspace.failureCode', '问题代码') }}：<code>{{ failureView.code }}</code></small></div></div>

      <main v-if="manuscript" class="ppt-manuscript-workflow__content">
        <div class="ppt-manuscript-workflow__summary">
          <div><small>{{ t('pptWorkspace.manuscriptLabel', '页面内容稿') }}</small><h2>{{ t('pptWorkspace.manuscriptReviewTitle', '逐页教学内容') }}</h2></div>
          <div class="ppt-manuscript-workflow__save-state"><span v-if="manuscript.teaching_content_contract_version === 'page_teaching_v2'">{{ manuscriptPageCounts }}</span><span v-else>{{ manuscript.page_count }} {{ t('pptWorkspace.pageUnit', '页') }}</span><small>{{ saveStateLabel }}</small></div>
        </div>

        <section v-if="narrativeBrief" class="ppt-manuscript-workflow__brief" data-testid="ppt-narrative-brief">
          <div><small>{{ t('pptWorkspace.narrativeQuestion', '整讲中心问题') }}</small><strong>{{ narrativeBrief.central_question }}</strong></div>
          <div><small>{{ t('pptWorkspace.learningPath', '学习路径') }}</small><span>{{ listText(narrativeBrief.learning_path) }}</span></div>
          <div><small>{{ t('pptWorkspace.observableCheckpoints', '可观察检查点') }}</small><span>{{ listText(narrativeBrief.observable_checkpoints) }}</span></div>
          <span class="ppt-manuscript-workflow__time">{{ narrativeBrief.time_budget_minutes }} {{ t('pptWorkspace.minutes', '分钟') }}</span>
        </section>

        <div class="ppt-manuscript-workflow__pages">
          <article v-for="page in draftPages" :key="page.page_id" :class="{ 'is-selected': selectedPageIds.has(page.page_id), 'is-locked': page.teacher_locked }">
            <aside class="ppt-manuscript-workflow__page-rail">
              <span>{{ String(page.page_number).padStart(2, '0') }}</span>
              <input type="checkbox" :aria-label="t('pptWorkspace.selectPage', '选择页面')" :checked="selectedPageIds.has(page.page_id)" :disabled="!canRegenerate(page)" @change="toggleSelected(page.page_id)">
            </aside>
            <div class="ppt-manuscript-workflow__page-copy">
              <div class="ppt-manuscript-workflow__page-meta">
                <small>{{ pageTypeLabel(page.page_type) }}<template v-if="!page.teaching"> · {{ page.layout_id }}</template></small>
                <button type="button" class="ppt-manuscript-workflow__lock" :disabled="busy" @click="toggleLock(page)"><Lock v-if="page.teacher_locked" :size="15" /><Unlock v-else :size="15" />{{ page.teacher_locked ? t('pptWorkspace.pageLocked', '已锁定') : t('pptWorkspace.lockPage', '锁定本页') }}</button>
              </div>

              <label class="ppt-manuscript-workflow__title-field"><span>{{ t('pptWorkspace.pageTitle', '页面标题') }}</span><input v-model="page.title" :disabled="busy" @input="syncTitleRegion(page)"></label>
              <div class="ppt-manuscript-workflow__field-grid">
                <label><span>{{ t('pptWorkspace.pageGoal', '页面目标') }}</span><textarea v-model="page.page_goal" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.primaryClaim', '核心结论') }}</span><textarea v-model="page.primary_claim" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.audienceQuestion', '学习者问题') }}</span><textarea v-model="page.audience_question" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.audienceAction', '学习者行动') }}</span><textarea v-model="page.audience_action" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.expectedResponse', '预期反应') }}</span><textarea v-model="page.expected_response" :disabled="busy" rows="2" /></label>
                <label><span>{{ t('pptWorkspace.observableEvidence', '达成证据') }}</span><textarea v-model="page.observable_evidence" :disabled="busy" rows="2" /></label>
              </div>

              <PptTeachingEditor v-if="page.teaching" :page="page" :disabled="Boolean(busy)" />
              <div v-else class="ppt-manuscript-workflow__visible-copy"><span>{{ t('pptWorkspace.visibleCopy', '台上可见内容') }}</span><textarea v-for="(_line, index) in page.visible_copy || []" :key="`${page.page_id}-copy-${index}`" v-model="page.visible_copy[index]" :disabled="busy" rows="2" /></div>
              <label v-if="!page.teaching"><span>{{ t('pptWorkspace.revealSteps', '揭示顺序') }}</span><textarea :value="listLines(page.reveal_steps)" :disabled="busy" rows="3" @input="setLines(page, 'reveal_steps', $event)" /></label>
              <label><span>{{ t('pptWorkspace.pageTransition', '与前后页的衔接') }}</span><textarea v-model="page.transition" :disabled="busy" rows="2" /></label>
              <label><span>{{ t('pptWorkspace.compositionNotes', '构图意图') }}</span><textarea v-model="page.composition_notes" :disabled="busy" rows="2" /></label>

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

      <footer class="ppt-manuscript-workflow__actions">
        <template v-if="manuscript && state.source_state === 'stale'">
          <button type="button" :disabled="busy || dirty" data-testid="regenerate-affected-ppt-pages" @click="emit('regenerate-pages', [])"><RefreshCw :size="17" />{{ regenerating ? t('pptWorkspace.regeneratingPages', '正在重新生成…') : t('pptWorkspace.regenerateAffectedPages', '只重新生成受影响页') }}</button>
          <button type="button" class="is-primary" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')"><Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : t('pptWorkspace.regenerateManuscript', '重新生成整份页面内容稿') }}</button>
        </template>
        <button v-else-if="!manuscript" type="button" class="is-primary" :disabled="busy" data-testid="generate-ppt-manuscript" @click="emit('generate-manuscript')"><Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : retryLabel }}</button>
        <template v-else>
          <button type="button" :disabled="busy || selectedPageIds.size === 0 || dirty" data-testid="regenerate-selected-ppt-pages" @click="emit('regenerate-pages', [...selectedPageIds])"><RefreshCw :size="17" />{{ regenerating ? t('pptWorkspace.regeneratingPages', '正在重新生成…') : t('pptWorkspace.regenerateSelectedPages', '重新生成选中页') }}</button>
          <button type="button" :disabled="busy || !dirty" data-testid="save-ppt-manuscript" @click="saveDraft"><Save :size="17" />{{ saving ? t('pptWorkspace.savingManuscript', '正在保存…') : t('pptWorkspace.saveManuscript', '保存修改') }}</button>
          <button v-if="state.status === 'draft'" type="button" class="is-primary" :disabled="busy || dirty || !state.confirmable" data-testid="confirm-ppt-manuscript" @click="emit('confirm-manuscript')"><Check :size="17" />{{ confirming ? t('pptWorkspace.confirmingManuscript', '正在确认…') : t('pptWorkspace.confirmManuscript', '确认页面内容稿') }}</button>
          <button v-else type="button" class="is-primary" :disabled="busy || dirty || !state.can_generate_ppt" data-testid="generate-ppt-from-manuscript" @click="emit('generate-ppt')"><Presentation :size="17" />{{ busy ? t('pptWorkspace.generatingDeck', '正在生成 PPT…') : t('pptWorkspace.generateDeck', '根据已确认页面内容稿生成 PPT') }}</button>
        </template>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Check, FileCheck2, Lock, Presentation, RefreshCw, Save, ScrollText, Sparkles, TriangleAlert, Unlock } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'
import PptTeachingEditor from './PptTeachingEditor.vue'

const props = defineProps<{ title: string; state: Record<string, any>; busy?: boolean; confirming?: boolean; saving?: boolean; regenerating?: boolean; error?: string; failure?: Record<string, any> | null }>()
const emit = defineEmits<{
  (event: 'back'): void
  (event: 'generate-manuscript'): void
  (event: 'regenerate-manuscript'): void
  (event: 'confirm-manuscript'): void
  (event: 'generate-ppt'): void
  (event: 'save-manuscript', updates: Record<string, any>[]): void
  (event: 'regenerate-pages', pageIds: string[]): void
}>()

const manuscript = computed(() => props.state.manuscript || null)
const manuscriptPageCounts = computed(() => t('pptWorkspace.manuscriptPageCounts')
  .replace('{logical}', String(manuscript.value?.pages?.length || 0))
  .replace('{physical}', String(manuscript.value?.page_count || 0)))
const draftPages = ref<Record<string, any>[]>([])
const originalPages = ref<Record<string, any>[]>([])
const selectedPageIds = ref(new Set<string>())

watch(() => props.state.revision, () => {
  const pages = Array.isArray(manuscript.value?.pages) ? manuscript.value.pages : []
  draftPages.value = JSON.parse(JSON.stringify(pages))
  originalPages.value = JSON.parse(JSON.stringify(pages))
  selectedPageIds.value = new Set()
}, { immediate: true })

const narrativeBrief = computed(() => manuscript.value?.narrative_brief || null)
const dirtyUpdates = computed(() => draftPages.value.flatMap((page, index): Record<string, any>[] => {
  const original = originalPages.value[index]
  if (!original || JSON.stringify(page) === JSON.stringify(original)) return []
  if (page.teaching) return [{ page_id: page.page_id, title: page.title, teaching: page.teaching, page_goal: page.page_goal,
    primary_claim: page.primary_claim, audience_question: page.audience_question, audience_action: page.audience_action,
    expected_response: page.expected_response, observable_evidence: page.observable_evidence, transition: page.transition,
    composition_notes: page.composition_notes, teacher_locked: Boolean(page.teacher_locked) }]
  return [{ page_id: page.page_id, title: page.title, visible_copy: page.visible_copy, page_goal: page.page_goal, primary_claim: page.primary_claim, audience_question: page.audience_question, audience_action: page.audience_action, expected_response: page.expected_response, observable_evidence: page.observable_evidence, transition: page.transition, reveal_steps: page.reveal_steps, composition_notes: page.composition_notes, teacher_locked: Boolean(page.teacher_locked) }]
}))
const dirty = computed(() => dirtyUpdates.value.length > 0)
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
const manuscriptStepStatus = computed(() => props.state.source_state === 'stale' ? t('pptWorkspace.stepStale', '需要重新生成') : props.state.status === 'confirmed' ? t('pptWorkspace.stepConfirmed', '已确认') : manuscript.value ? t('pptWorkspace.stepAwaitingConfirmation', '待确认') : t('pptWorkspace.stepNotStarted', '未开始'))
const deckStepStatus = computed(() => props.state.generated_representation_id ? t('pptWorkspace.stepCompleted', '已生成') : props.state.can_generate_ppt ? t('pptWorkspace.stepReady', '可生成') : t('pptWorkspace.stepLocked', '确认页面内容稿后解锁'))

function saveDraft() { if (dirtyUpdates.value.length) emit('save-manuscript', dirtyUpdates.value) }
function syncTitleRegion(page: Record<string, any>) { const regions = Array.isArray(page.regions) ? page.regions.filter((item: any) => item.content_kind !== 'notes') : []; const titleIndex = regions.findIndex((item: any) => item.content_kind === 'title'); if (titleIndex >= 0 && Array.isArray(page.visible_copy)) page.visible_copy[titleIndex] = page.title }
function toggleLock(page: Record<string, any>) { page.teacher_locked = !page.teacher_locked; if (page.teacher_locked) selectedPageIds.value.delete(page.page_id) }
function toggleSelected(pageId: string) { const next = new Set(selectedPageIds.value); next.has(pageId) ? next.delete(pageId) : next.add(pageId); selectedPageIds.value = next }
function canRegenerate(page: Record<string, any>) { return !page.teacher_locked && !page.continuation_of_page_id && !['cover', 'agenda', 'summary'].includes(page.page_type) }
function setLines(page: Record<string, any>, field: string, event: Event) { page[field] = (event.target as HTMLTextAreaElement).value.split('\n').map(value => value.trim()).filter(Boolean) }
function listLines(value: unknown) { return Array.isArray(value) ? value.join('\n') : '' }
function listText(value: unknown) { return Array.isArray(value) ? value.join(' → ') : '' }
function pageIssues(pageId: string) { return (manuscript.value?.quality_issues || []).filter((item: any) => !item.page_id || item.page_id === pageId) }
function sourceIds(page: Record<string, any>, field: string): string[] { const values = page?.[field]; return Array.isArray(values) ? values.map(String).filter(Boolean) : [] }
function hasSourceRefs(page: Record<string, any>) { return ['source_script_block_ids', 'source_section_ids', 'source_material_evidence_ids'].some(field => sourceIds(page, field).length) }
function stepClass(step: number) { return step === 1 ? { 'is-active': true, 'is-complete': props.state.status === 'confirmed' } : { 'is-active': props.state.can_generate_ppt, 'is-complete': Boolean(props.state.generated_representation_id) } }
function pageTypeLabel(value: string) { const labels: Record<string, string> = { cover: t('pptWorkspace.manuscriptPageTypes.cover', '封面'), agenda: t('pptWorkspace.manuscriptPageTypes.agenda', '导览'), concept: t('pptWorkspace.manuscriptPageTypes.concept', '概念'), reasoning: t('pptWorkspace.manuscriptPageTypes.reasoning', '推理'), example: t('pptWorkspace.manuscriptPageTypes.example', '例题'), practice: t('pptWorkspace.manuscriptPageTypes.practice', '练习'), comparison: t('pptWorkspace.manuscriptPageTypes.comparison', '对照'), code: t('pptWorkspace.manuscriptPageTypes.code', '代码'), formula: t('pptWorkspace.manuscriptPageTypes.formula', '公式'), table: t('pptWorkspace.manuscriptPageTypes.table', '表格'), data: t('pptWorkspace.manuscriptPageTypes.data', '数据'), diagram: t('pptWorkspace.manuscriptPageTypes.diagram', '图示'), summary: t('pptWorkspace.manuscriptPageTypes.summary', '总结'), content: t('pptWorkspace.manuscriptPageTypes.content', '正文') }; return labels[value] || value }
</script>

<style scoped>
.ppt-manuscript-workflow{width:100%;height:100%;overflow:auto;padding:28px 36px 110px;background:#f5f6f8;color:#172033}.ppt-manuscript-workflow__header{display:flex;gap:18px;align-items:flex-start;max-width:1080px;margin:0 auto 20px}.ppt-manuscript-workflow__header h1{margin:4px 0 5px;font-size:25px}.ppt-manuscript-workflow__header p{margin:0;color:#667085}.ppt-manuscript-workflow__header small{color:#3857d6;font-weight:750;letter-spacing:.08em}.ppt-manuscript-workflow__back{width:38px;height:38px;border:1px solid #d8dde7;border-radius:10px;background:#fff;display:grid;place-items:center}.ppt-manuscript-workflow__steps{list-style:none;padding:0;max-width:1080px;margin:0 auto 16px;display:flex;gap:22px}.ppt-manuscript-workflow__steps li{display:flex;align-items:center;gap:9px;color:#98a2b3}.ppt-manuscript-workflow__steps li>span{width:27px;height:27px;display:grid;place-items:center;border-radius:8px;background:#e8ebf0;font-weight:800}.ppt-manuscript-workflow__steps li div{display:flex;flex-direction:column}.ppt-manuscript-workflow__steps li.is-active{color:#243b86}.ppt-manuscript-workflow__steps li.is-active>span{color:#fff;background:#3857d6}.ppt-manuscript-workflow__steps li.is-complete>span{background:#16845b}.ppt-manuscript-workflow__warning,.ppt-manuscript-workflow__original{max-width:1080px;margin:0 auto 15px;padding:13px 16px;border-radius:10px;background:#fff7e8;color:#8a5a08;display:flex;gap:9px;align-items:center}.ppt-manuscript-workflow__warning.is-error{align-items:flex-start;background:#fff0f0;color:#8f1712}.ppt-manuscript-workflow__warning p{margin:4px 0}.ppt-manuscript-workflow__content,.ppt-manuscript-workflow__empty,.ppt-manuscript-workflow__original{max-width:1080px;margin-left:auto;margin-right:auto;background:#fff;border:1px solid #e1e5ec;border-radius:12px}.ppt-manuscript-workflow__summary{display:flex;justify-content:space-between;align-items:center;padding:20px 28px;border-bottom:1px solid #e8ebf0}.ppt-manuscript-workflow__summary h2{margin:3px 0 0;font-size:19px}.ppt-manuscript-workflow__save-state{display:flex;align-items:flex-end;flex-direction:column;gap:2px;color:#3857d6;font-weight:700}.ppt-manuscript-workflow__save-state small{color:#667085;font-weight:500}.ppt-manuscript-workflow__brief{position:relative;padding:20px 28px;background:#f8f9fc;border-bottom:1px solid #e8ebf0;display:grid;gap:10px}.ppt-manuscript-workflow__brief div{display:grid;grid-template-columns:130px 1fr;gap:12px}.ppt-manuscript-workflow__brief small,.ppt-manuscript-workflow__page-copy label>span,.ppt-manuscript-workflow__visible-copy>span{color:#667085;font-size:12px;font-weight:700}.ppt-manuscript-workflow__time{position:absolute;right:28px;top:20px;color:#3857d6;font-size:13px}.ppt-manuscript-workflow__pages article{display:grid;grid-template-columns:54px 1fr;gap:16px;padding:26px 28px;border-bottom:1px solid #e8ebf0}.ppt-manuscript-workflow__pages article:last-child{border-bottom:0}.ppt-manuscript-workflow__pages article.is-selected{box-shadow:inset 3px 0 #3857d6}.ppt-manuscript-workflow__pages article.is-locked{background:#fbfcfe}.ppt-manuscript-workflow__page-rail{display:flex;align-items:center;flex-direction:column;gap:13px;color:#98a2b3;font-size:18px;font-weight:800}.ppt-manuscript-workflow__page-rail input{width:16px;height:16px}.ppt-manuscript-workflow__page-meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;color:#667085}.ppt-manuscript-workflow__lock{display:flex;align-items:center;gap:5px;padding:5px 8px;border:0;background:transparent;color:#475467}.ppt-manuscript-workflow__page-copy label,.ppt-manuscript-workflow__visible-copy{display:flex;flex-direction:column;gap:5px;margin:10px 0}.ppt-manuscript-workflow__page-copy input,.ppt-manuscript-workflow__page-copy textarea{width:100%;padding:8px 0;border:0;border-bottom:1px solid #d8dde7;border-radius:0;background:transparent;color:#172033;font:inherit;line-height:1.55;resize:vertical}.ppt-manuscript-workflow__page-copy input:focus,.ppt-manuscript-workflow__page-copy textarea:focus{outline:none;border-color:#3857d6;box-shadow:0 1px 0 #3857d6}.ppt-manuscript-workflow__title-field input{font-size:20px;font-weight:750}.ppt-manuscript-workflow__field-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}.ppt-manuscript-workflow__visible-copy{margin-top:15px;padding-top:10px;border-top:1px dashed #d8dde7}.ppt-manuscript-workflow__issues{margin:14px 0 0;padding:10px 14px 10px 32px;border-radius:8px;background:#fff0f0;color:#9b2018;line-height:1.5}.ppt-manuscript-workflow__sources{margin-top:13px;color:#667085}.ppt-manuscript-workflow__sources dl{display:grid;gap:8px}.ppt-manuscript-workflow__sources dl>div{display:grid;grid-template-columns:100px 1fr;gap:8px}.ppt-manuscript-workflow__sources dd{display:flex;flex-wrap:wrap;gap:5px;margin:0}.ppt-manuscript-workflow__sources code{padding:2px 5px;border-radius:4px;background:#f2f4f7;font-size:11px}.ppt-manuscript-workflow__empty{padding:60px 28px;text-align:center;color:#667085}.ppt-manuscript-workflow__original{padding:50px 28px;text-align:center;flex-direction:column;color:#475467}.ppt-manuscript-workflow__original button{padding:10px 16px;border:0;border-radius:9px;background:#3857d6;color:#fff}.ppt-manuscript-workflow__actions{position:fixed;left:0;right:0;bottom:0;z-index:5;padding:14px 36px;border-top:1px solid #dfe3eb;background:rgba(255,255,255,.97);display:flex;justify-content:flex-end;gap:10px}.ppt-manuscript-workflow__actions button{min-width:150px;padding:10px 15px;border:0;border-radius:8px;display:flex;align-items:center;justify-content:center;gap:7px;font-weight:750;background:#eef1f7;color:#28344d}.ppt-manuscript-workflow__actions button.is-primary{background:#3857d6;color:#fff}.ppt-manuscript-workflow__actions button:disabled{opacity:.5}
</style>
