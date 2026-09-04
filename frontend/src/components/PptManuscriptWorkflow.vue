<template>
  <section class="ppt-manuscript-workflow" data-testid="ppt-manuscript-workflow">
    <header class="ppt-manuscript-workflow__header">
      <button type="button" class="ppt-manuscript-workflow__back" @click="emit('back')">
        <ArrowLeft :size="18" />
      </button>
      <div>
        <small>{{ t('pptWorkspace.manuscriptWorkflowEyebrow', 'PPT 生成') }}</small>
        <h1><MathText :content="title" /></h1>
        <p>{{ t('pptWorkspace.manuscriptWorkflowDescription', '先确认逐页页面内容稿，再生成可编辑 PPT。') }}</p>
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
        <li :class="stepClass(1)">
          <span>1</span>
          <div>
            <strong>{{ t('pptWorkspace.stepGenerateManuscript', '生成页面内容稿') }}</strong>
            <small>{{ manuscriptStepStatus }}</small>
          </div>
        </li>
        <li :class="stepClass(2)">
          <span>2</span>
          <div>
            <strong>{{ t('pptWorkspace.stepGenerateDeck', '生成 PPT') }}</strong>
            <small>{{ deckStepStatus }}</small>
          </div>
        </li>
      </ol>

      <div v-if="state.source_state === 'stale'" class="ppt-manuscript-workflow__warning">
        <TriangleAlert :size="18" />
        <span>{{ t('pptWorkspace.manuscriptStale', '教案、讲义或资料已经变化，请重新生成页面内容稿。') }}</span>
      </div>
      <div
        v-if="failureView"
        class="ppt-manuscript-workflow__warning is-error"
        role="alert"
        data-testid="ppt-manuscript-failure"
      >
        <TriangleAlert :size="18" />
        <div>
          <strong>{{ failureView.title }}</strong>
          <p>{{ failureView.message }}</p>
          <small v-if="failureView.code">{{ t('pptWorkspace.failureCode', '问题代码') }}：<code>{{ failureView.code }}</code></small>
        </div>
      </div>

      <main v-if="manuscript" class="ppt-manuscript-workflow__content">
        <div class="ppt-manuscript-workflow__summary">
          <div>
            <small>{{ t('pptWorkspace.manuscriptLabel', '页面内容稿') }}</small>
            <h2>{{ t('pptWorkspace.manuscriptReviewTitle', '逐页内容与来源') }}</h2>
          </div>
          <span>{{ manuscript.page_count }} {{ t('pptWorkspace.pageUnit', '页') }}</span>
        </div>
        <div class="ppt-manuscript-workflow__pages">
          <article v-for="page in manuscript.pages || []" :key="page.page_id">
            <div class="ppt-manuscript-workflow__page-number">{{ String(page.page_number).padStart(2, '0') }}</div>
            <div class="ppt-manuscript-workflow__page-copy">
              <small>{{ pageTypeLabel(page.page_type) }} · {{ page.layout_id }}</small>
              <h3><MathText :content="page.title" /></h3>
              <p v-if="page.page_goal"><b>{{ t('pptWorkspace.pageGoal', '页面目标') }}：</b><MathText :content="page.page_goal" /></p>
              <p v-if="page.primary_claim"><b>{{ t('pptWorkspace.primaryClaim', '核心结论') }}：</b><MathText :content="page.primary_claim" /></p>
              <ul v-if="page.visible_copy?.length">
                <li v-for="(line, index) in page.visible_copy" :key="`${page.page_id}-${index}`"><MathText :content="line" /></li>
              </ul>
              <p v-if="page.transition" class="ppt-manuscript-workflow__transition">
                <b>{{ t('pptWorkspace.pageTransition', '衔接') }}：</b><MathText :content="page.transition" />
              </p>
              <dl v-if="hasSourceRefs(page)" class="ppt-manuscript-workflow__sources">
                <div v-if="sourceIds(page, 'source_script_block_ids').length">
                  <dt>{{ t('pptWorkspace.sourceScriptBlockIds', '讲义来源块') }}</dt>
                  <dd><code v-for="sourceId in sourceIds(page, 'source_script_block_ids')" :key="sourceId">{{ sourceId }}</code></dd>
                </div>
                <div v-if="sourceIds(page, 'source_section_ids').length">
                  <dt>{{ t('pptWorkspace.sourceSectionIds', '教案小节') }}</dt>
                  <dd><code v-for="sourceId in sourceIds(page, 'source_section_ids')" :key="sourceId">{{ sourceId }}</code></dd>
                </div>
                <div v-if="sourceIds(page, 'source_material_evidence_ids').length">
                  <dt>{{ t('pptWorkspace.sourceMaterialEvidenceIds', '资料证据') }}</dt>
                  <dd><code v-for="sourceId in sourceIds(page, 'source_material_evidence_ids')" :key="sourceId">{{ sourceId }}</code></dd>
                </div>
              </dl>
            </div>
          </article>
        </div>
      </main>

      <div v-else class="ppt-manuscript-workflow__empty">
        <ScrollText :size="34" />
        <h2>{{ t('pptWorkspace.manuscriptNotGenerated', '尚未生成页面内容稿') }}</h2>
        <p>{{ t('pptWorkspace.manuscriptNotGeneratedDescription', '系统会先形成页序、标题、核心内容、讲解衔接与版式建议，供你确认。') }}</p>
      </div>

      <footer class="ppt-manuscript-workflow__actions">
        <button
          v-if="!manuscript || state.source_state === 'stale'"
          type="button"
          class="is-primary"
          :disabled="busy"
          data-testid="generate-ppt-manuscript"
          @click="emit('generate-manuscript')"
        >
          <Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : retryLabel }}
        </button>
        <template v-else-if="state.status === 'draft'">
          <button
            type="button"
            :disabled="busy"
            data-testid="regenerate-ppt-manuscript"
            @click="emit('regenerate-manuscript')"
          >
            <Sparkles :size="17" />{{ t('pptWorkspace.regenerateManuscript', '重新生成页面内容稿') }}
          </button>
          <button
            type="button"
            class="is-primary"
            :disabled="busy || !state.confirmable"
            data-testid="confirm-ppt-manuscript"
            @click="emit('confirm-manuscript')"
          >
            <Check :size="17" />{{ confirming ? t('pptWorkspace.confirmingManuscript', '正在确认…') : t('pptWorkspace.confirmManuscript', '确认页面内容稿') }}
          </button>
        </template>
        <template v-else>
          <button
            v-if="state.status === 'confirmed'"
            type="button"
            :disabled="busy"
            data-testid="regenerate-ppt-manuscript"
            @click="emit('regenerate-manuscript')"
          >
            <Sparkles :size="17" />{{ t('pptWorkspace.regenerateManuscript', '重新生成页面内容稿') }}
          </button>
          <button
            type="button"
            class="is-primary"
            :disabled="busy || !state.can_generate_ppt"
            data-testid="generate-ppt-from-manuscript"
            @click="emit('generate-ppt')"
          >
            <Presentation :size="17" />{{ busy ? t('pptWorkspace.generatingDeck', '正在生成 PPT…') : t('pptWorkspace.generateDeck', '根据已确认页面内容稿生成 PPT') }}
          </button>
        </template>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Check, FileCheck2, Presentation, ScrollText, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'

const props = defineProps<{
  title: string
  state: Record<string, any>
  busy?: boolean
  confirming?: boolean
  error?: string
  failure?: Record<string, any> | null
}>()

const emit = defineEmits<{
  (event: 'back'): void
  (event: 'generate-manuscript'): void
  (event: 'regenerate-manuscript'): void
  (event: 'confirm-manuscript'): void
  (event: 'generate-ppt'): void
}>()

const manuscript = computed(() => props.state.manuscript || null)
const failureView = computed(() => {
  const failure = props.failure || null
  const code = String(failure?.code || '')
  if (code === 'story_ai_batch_request_budget_exceeded') {
    return {
      code,
      title: t('pptWorkspace.manuscriptBudgetRecoveredTitle', '页面内容稿输入已自动压缩'),
      message: t('pptWorkspace.manuscriptBudgetRecoveredMessage', '系统已移除重复上下文并保留全部讲义块，可直接重新生成当前页面内容稿。'),
    }
  }
  if (code.startsWith('story_title_') || code === 'duplicate_slide_title') {
    return {
      code,
      title: t('pptWorkspace.manuscriptTitleRecoveryTitle', '页面标题候选不足'),
      message: t('pptWorkspace.manuscriptTitleRecoveryMessage', '系统会优先使用当前可用讲义块标题重新规划，不会发布重复或残缺标题页。'),
    }
  }
  if (code.endsWith('_rate_limited')) {
    return {
      code,
      title: t('pptWorkspace.manuscriptRateLimitedTitle', '页面内容稿模型暂时繁忙'),
      message: t('pptWorkspace.manuscriptRateLimitedMessage', '已完成内容和旧版本均已保留，稍后可直接重试。'),
    }
  }
  if (code.endsWith('_authentication') || code.endsWith('_balance_unavailable')) {
    return {
      code,
      title: t('pptWorkspace.manuscriptProviderBlockedTitle', '页面内容稿模型当前不可用'),
      message: String(failure?.message || t('pptWorkspace.manuscriptProviderBlockedMessage', '请检查模型凭证或额度后再重试；系统没有发布不完整页面内容稿。')),
    }
  }
  if (failure) {
    return {
      code,
      title: t('pptWorkspace.manuscriptGenerationFailedTitle', '页面内容稿未生成'),
      message: String(failure.message || t('pptWorkspace.manuscriptGenerationFailedMessage', '系统已保留现有内容，可重新生成。')),
    }
  }
  if (props.error) {
    return {
      code: '',
      title: t('pptWorkspace.manuscriptOperationFailedTitle', '当前操作未完成'),
      message: props.error,
    }
  }
  return null
})
const retryLabel = computed(() => (
  failureView.value
    ? t('pptWorkspace.retryManuscript', '重新生成页面内容稿')
    : t('pptWorkspace.generateManuscript', '生成页面内容稿')
))
const manuscriptStepStatus = computed(() => {
  if (props.state.source_state === 'stale') return t('pptWorkspace.stepStale', '需要重新生成')
  if (props.state.status === 'confirmed') return t('pptWorkspace.stepConfirmed', '已确认')
  if (manuscript.value) return t('pptWorkspace.stepAwaitingConfirmation', '待确认')
  return t('pptWorkspace.stepNotStarted', '未开始')
})
const deckStepStatus = computed(() => (
  props.state.generated_representation_id
    ? t('pptWorkspace.stepCompleted', '已生成')
    : props.state.can_generate_ppt
      ? t('pptWorkspace.stepReady', '可生成')
      : t('pptWorkspace.stepLocked', '确认页面内容稿后解锁')
))

function sourceIds(page: Record<string, any>, field: string): string[] {
  const values = page?.[field]
  return Array.isArray(values) ? values.map(value => String(value)).filter(Boolean) : []
}

function hasSourceRefs(page: Record<string, any>): boolean {
  return ['source_script_block_ids', 'source_section_ids', 'source_material_evidence_ids']
    .some(field => sourceIds(page, field).length > 0)
}

function stepClass(step: number) {
  if (step === 1) return { 'is-active': true, 'is-complete': props.state.status === 'confirmed' }
  return { 'is-active': props.state.can_generate_ppt, 'is-complete': Boolean(props.state.generated_representation_id) }
}

function pageTypeLabel(value: string) {
  const labels: Record<string, string> = {
    cover: t('pptWorkspace.manuscriptPageTypes.cover', '封面'),
    agenda: t('pptWorkspace.manuscriptPageTypes.agenda', '导览'),
    concept: t('pptWorkspace.manuscriptPageTypes.concept', '概念'),
    reasoning: t('pptWorkspace.manuscriptPageTypes.reasoning', '推理'),
    example: t('pptWorkspace.manuscriptPageTypes.example', '例题'),
    practice: t('pptWorkspace.manuscriptPageTypes.practice', '练习'),
    comparison: t('pptWorkspace.manuscriptPageTypes.comparison', '对照'),
    code: t('pptWorkspace.manuscriptPageTypes.code', '代码'),
    formula: t('pptWorkspace.manuscriptPageTypes.formula', '公式'),
    table: t('pptWorkspace.manuscriptPageTypes.table', '表格'),
    data: t('pptWorkspace.manuscriptPageTypes.data', '数据'),
    diagram: t('pptWorkspace.manuscriptPageTypes.diagram', '图示'),
    summary: t('pptWorkspace.manuscriptPageTypes.summary', '总结'),
    content: t('pptWorkspace.manuscriptPageTypes.content', '正文'),
  }
  return labels[value] || value
}
</script>

<style scoped>
.ppt-manuscript-workflow { width:100%; height:100%; overflow:auto; padding:28px 36px 110px; background:#f5f6f8; color:#172033; }
.ppt-manuscript-workflow__header { display:flex; gap:18px; align-items:flex-start; max-width:1120px; margin:0 auto 22px; }
.ppt-manuscript-workflow__header h1 { margin:4px 0 6px; font-size:25px; }
.ppt-manuscript-workflow__header p { margin:0; color:#667085; }
.ppt-manuscript-workflow__header small { color:#3857d6; font-weight:750; letter-spacing:.08em; }
.ppt-manuscript-workflow__back { width:38px; height:38px; border:1px solid #d8dde7; border-radius:10px; background:white; display:grid; place-items:center; }
.ppt-manuscript-workflow__steps { list-style:none; padding:0; max-width:1120px; margin:0 auto 18px; display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.ppt-manuscript-workflow__steps li { display:flex; align-items:center; gap:12px; padding:14px 16px; border:1px solid #dfe3eb; border-radius:12px; background:#fff; color:#98a2b3; }
.ppt-manuscript-workflow__steps li > span { width:30px; height:30px; display:grid; place-items:center; border-radius:50%; background:#eef0f4; font-weight:800; }
.ppt-manuscript-workflow__steps li div { display:flex; flex-direction:column; gap:2px; }
.ppt-manuscript-workflow__steps li.is-active { color:#243b86; border-color:#bac7f6; }
.ppt-manuscript-workflow__steps li.is-active > span { color:white; background:#3857d6; }
.ppt-manuscript-workflow__steps li.is-complete > span { background:#16845b; }
.ppt-manuscript-workflow__warning, .ppt-manuscript-workflow__original { max-width:1120px; margin:0 auto 16px; padding:13px 16px; border-radius:10px; background:#fff7e8; color:#8a5a08; display:flex; gap:9px; align-items:center; }
.ppt-manuscript-workflow__warning.is-error { align-items:flex-start; background:#fff0f0; color:#8f1712; }
.ppt-manuscript-workflow__warning.is-error > div { display:flex; flex-direction:column; gap:4px; }
.ppt-manuscript-workflow__warning.is-error p { max-width:72ch; margin:0; line-height:1.5; }
.ppt-manuscript-workflow__warning.is-error small { color:#a23a32; }
.ppt-manuscript-workflow__warning.is-error code { font-family:ui-monospace, SFMono-Regular, Menlo, monospace; }
.ppt-manuscript-workflow__content, .ppt-manuscript-workflow__empty, .ppt-manuscript-workflow__original { max-width:1120px; margin-left:auto; margin-right:auto; background:white; border:1px solid #e1e5ec; border-radius:14px; }
.ppt-manuscript-workflow__summary { display:flex; justify-content:space-between; align-items:center; padding:20px 22px; border-bottom:1px solid #e8ebf0; }
.ppt-manuscript-workflow__summary h2 { margin:3px 0 0; font-size:19px; }
.ppt-manuscript-workflow__summary small { color:#667085; }
.ppt-manuscript-workflow__summary > span { font-weight:700; color:#3857d6; }
.ppt-manuscript-workflow__pages article { display:grid; grid-template-columns:56px 1fr; gap:16px; padding:20px 22px; border-bottom:1px solid #eceff3; }
.ppt-manuscript-workflow__pages article:last-child { border-bottom:0; }
.ppt-manuscript-workflow__page-number { color:#98a2b3; font-size:18px; font-weight:800; }
.ppt-manuscript-workflow__page-copy h3 { margin:5px 0 10px; font-size:18px; }
.ppt-manuscript-workflow__page-copy > small { color:#667085; }
.ppt-manuscript-workflow__page-copy p { margin:7px 0; line-height:1.65; }
.ppt-manuscript-workflow__page-copy ul { margin:8px 0; padding-left:20px; line-height:1.7; }
.ppt-manuscript-workflow__transition { color:#475467; }
.ppt-manuscript-workflow__sources { display:grid; gap:8px; margin:14px 0 0; padding-top:12px; border-top:1px solid #eceff3; }
.ppt-manuscript-workflow__sources > div { display:grid; grid-template-columns:88px minmax(0,1fr); gap:10px; align-items:start; }
.ppt-manuscript-workflow__sources dt { color:#667085; font-size:12px; font-weight:700; }
.ppt-manuscript-workflow__sources dd { display:flex; flex-wrap:wrap; gap:5px; min-width:0; margin:0; }
.ppt-manuscript-workflow__sources code { max-width:100%; padding:2px 6px; overflow-wrap:anywhere; border-radius:5px; color:#344054; background:#f2f4f7; font-size:11px; }
.ppt-manuscript-workflow__empty { padding:60px 28px; text-align:center; color:#667085; }
.ppt-manuscript-workflow__empty h2 { color:#172033; margin:12px 0 8px; }
.ppt-manuscript-workflow__original { padding:50px 28px; text-align:center; flex-direction:column; color:#475467; }
.ppt-manuscript-workflow__original h2 { color:#172033; margin:4px 0; }
.ppt-manuscript-workflow__original button { padding:10px 16px; border:0; border-radius:9px; background:#3857d6; color:white; }
.ppt-manuscript-workflow__actions { position:fixed; left:0; right:0; bottom:0; z-index:5; padding:14px 36px; border-top:1px solid #dfe3eb; background:rgba(255,255,255,.96); display:flex; justify-content:flex-end; gap:10px; }
.ppt-manuscript-workflow__actions button { min-width:220px; padding:11px 18px; border:0; border-radius:9px; display:flex; align-items:center; justify-content:center; gap:8px; font-weight:750; }
.ppt-manuscript-workflow__actions button:not(.is-primary) { background:#eef1f7; color:#28344d; }
.ppt-manuscript-workflow__actions button.is-primary { background:#3857d6; color:white; }
.ppt-manuscript-workflow__actions button:disabled { opacity:.55; }
</style>
