<template>
  <section class="ppt-manuscript-workflow" data-testid="ppt-manuscript-workflow">
    <header class="ppt-manuscript-workflow__header">
      <button type="button" class="ppt-manuscript-workflow__back" @click="emit('back')">
        <ArrowLeft :size="18" />
      </button>
      <div>
        <small>{{ t('pptWorkspace.manuscriptWorkflowEyebrow', 'PPT 生成') }}</small>
        <h1>{{ title }}</h1>
        <p>{{ t('pptWorkspace.manuscriptWorkflowDescription', '先确认逐页文书，再生成可编辑 PPT。') }}</p>
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
            <strong>{{ t('pptWorkspace.stepGenerateManuscript', '生成 PPT 文书') }}</strong>
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
        <span>{{ t('pptWorkspace.manuscriptStale', '教案、讲稿或资料已经变化，请重新生成 PPT 文书。') }}</span>
      </div>
      <div v-if="error" class="ppt-manuscript-workflow__warning is-error">{{ error }}</div>

      <main v-if="manuscript" class="ppt-manuscript-workflow__content">
        <div class="ppt-manuscript-workflow__summary">
          <div>
            <small>{{ t('pptWorkspace.manuscriptLabel', 'PPT 文书') }}</small>
            <h2>{{ t('pptWorkspace.manuscriptReviewTitle', '逐页内容底稿') }}</h2>
          </div>
          <span>{{ manuscript.page_count }} {{ t('pptWorkspace.pageUnit', '页') }}</span>
        </div>
        <div class="ppt-manuscript-workflow__pages">
          <article v-for="page in manuscript.pages || []" :key="page.page_id">
            <div class="ppt-manuscript-workflow__page-number">{{ String(page.page_number).padStart(2, '0') }}</div>
            <div class="ppt-manuscript-workflow__page-copy">
              <small>{{ pageTypeLabel(page.page_type) }} · {{ page.layout_id }}</small>
              <h3>{{ page.title }}</h3>
              <p v-if="page.page_goal"><b>{{ t('pptWorkspace.pageGoal', '页面目标') }}：</b>{{ page.page_goal }}</p>
              <p v-if="page.primary_claim"><b>{{ t('pptWorkspace.primaryClaim', '核心结论') }}：</b>{{ page.primary_claim }}</p>
              <ul v-if="page.visible_copy?.length">
                <li v-for="(line, index) in page.visible_copy" :key="`${page.page_id}-${index}`">{{ line }}</li>
              </ul>
              <p v-if="page.transition" class="ppt-manuscript-workflow__transition">
                <b>{{ t('pptWorkspace.pageTransition', '衔接') }}：</b>{{ page.transition }}
              </p>
            </div>
          </article>
        </div>
      </main>

      <div v-else class="ppt-manuscript-workflow__empty">
        <ScrollText :size="34" />
        <h2>{{ t('pptWorkspace.manuscriptNotGenerated', '尚未生成 PPT 文书') }}</h2>
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
          <Sparkles :size="17" />{{ busy ? t('pptWorkspace.generatingManuscript', '正在生成文书…') : t('pptWorkspace.generateManuscript', '生成 PPT 文书') }}
        </button>
        <button
          v-else-if="state.status === 'draft'"
          type="button"
          class="is-primary"
          :disabled="busy || !state.confirmable"
          data-testid="confirm-ppt-manuscript"
          @click="emit('confirm-manuscript')"
        >
          <Check :size="17" />{{ confirming ? t('pptWorkspace.confirmingManuscript', '正在确认…') : t('pptWorkspace.confirmManuscript', '确认 PPT 文书') }}
        </button>
        <button
          v-else
          type="button"
          class="is-primary"
          :disabled="busy || !state.can_generate_ppt"
          data-testid="generate-ppt-from-manuscript"
          @click="emit('generate-ppt')"
        >
          <Presentation :size="17" />{{ busy ? t('pptWorkspace.generatingDeck', '正在生成 PPT…') : t('pptWorkspace.generateDeck', '根据已确认文书生成 PPT') }}
        </button>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Check, FileCheck2, Presentation, ScrollText, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = defineProps<{
  title: string
  state: Record<string, any>
  busy?: boolean
  confirming?: boolean
  error?: string
}>()

const emit = defineEmits<{
  (event: 'back'): void
  (event: 'generate-manuscript'): void
  (event: 'confirm-manuscript'): void
  (event: 'generate-ppt'): void
}>()

const manuscript = computed(() => props.state.manuscript || null)
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
      : t('pptWorkspace.stepLocked', '确认文书后解锁')
))

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
.ppt-manuscript-workflow__warning.is-error { background:#fff0f0; color:#b42318; }
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
.ppt-manuscript-workflow__empty { padding:60px 28px; text-align:center; color:#667085; }
.ppt-manuscript-workflow__empty h2 { color:#172033; margin:12px 0 8px; }
.ppt-manuscript-workflow__original { padding:50px 28px; text-align:center; flex-direction:column; color:#475467; }
.ppt-manuscript-workflow__original h2 { color:#172033; margin:4px 0; }
.ppt-manuscript-workflow__original button { padding:10px 16px; border:0; border-radius:9px; background:#3857d6; color:white; }
.ppt-manuscript-workflow__actions { position:fixed; left:0; right:0; bottom:0; z-index:5; padding:14px 36px; border-top:1px solid #dfe3eb; background:rgba(255,255,255,.96); display:flex; justify-content:flex-end; }
.ppt-manuscript-workflow__actions button { min-width:220px; padding:11px 18px; border:0; border-radius:9px; display:flex; align-items:center; justify-content:center; gap:8px; font-weight:750; }
.ppt-manuscript-workflow__actions button.is-primary { background:#3857d6; color:white; }
.ppt-manuscript-workflow__actions button:disabled { opacity:.55; }
</style>
