<template>
  <section v-if="!dismissed" class="adaptive-block" :data-kind="block.kind">
    <header>
      <span class="adaptive-block__icon"><component :is="kindIcon" :size="17" /></span>
      <div>
        <small>{{ acceptedGrowth ? t('adaptiveBlocks.acceptedEyebrow', '个人课程已生长') : t('adaptiveBlocks.eyebrow', 'AI 临时支持') }}</small>
        <strong>{{ kindLabel }}</strong>
      </div>
      <div class="adaptive-block__actions">
        <button type="button" :title="collapsed ? t('adaptiveBlocks.expand', '展开') : t('adaptiveBlocks.collapse', '收起')" @click="collapsed = !collapsed">
          <ChevronDown v-if="collapsed" :size="16" />
          <ChevronUp v-else :size="16" />
        </button>
        <button type="button" :title="t('adaptiveBlocks.dismiss', '跳过这条支持')" @click="sendFeedback('dismissed')">
          <X :size="16" />
        </button>
      </div>
    </header>

    <div v-if="!collapsed" class="adaptive-block__body">
      <p>{{ block.payload.body }}</p>
      <p v-if="block.payload.contrast" class="adaptive-block__contrast">{{ block.payload.contrast }}</p>
      <ol v-if="block.payload.steps?.length" class="adaptive-block__steps">
        <li v-for="step in block.payload.steps" :key="step.index"><span>{{ step.index }}</span>{{ step.label }}</li>
      </ol>
      <div v-if="block.kind === 'understanding_check' && block.payload.prompt" class="adaptive-block__check">
        <CircleHelp :size="16" />
        <span>{{ block.payload.prompt }}</span>
        <small>{{ t('adaptiveBlocks.informal', '不计入掌握判断') }}</small>
      </div>
      <footer>
        <span><ShieldCheck :size="14" />{{ t(`adaptiveBlocks.reasons.${block.reason_code}`, t('adaptiveBlocks.evidenceBased', '基于当前学习证据')) }}</span>
        <div :aria-label="t('adaptiveBlocks.feedback', '这条支持是否有帮助')">
          <button type="button" :class="{ active: feedback === 'helpful' }" :title="t('adaptiveBlocks.helpful', '有帮助')" @click="sendFeedback('helpful')">
            <ThumbsUp :size="15" />
          </button>
          <button type="button" :class="{ active: feedback === 'not_helpful' }" :title="t('adaptiveBlocks.notHelpful', '没有帮助')" @click="sendFeedback('not_helpful')">
            <ThumbsDown :size="15" />
          </button>
        </div>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, ChevronDown, ChevronUp, CircleHelp, Lightbulb, ScanSearch, ShieldCheck, ThumbsDown, ThumbsUp, X } from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useLearningProgressStore, type AdaptiveBlockFeedback, type AdaptiveLearningBlock } from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = defineProps<{ block: AdaptiveLearningBlock }>()
const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const collapsed = ref(false)
const dismissed = ref(false)
const feedback = ref<AdaptiveBlockFeedback>(props.block.feedback.value)
const acceptedGrowth = computed(() => props.block.role === 'accepted_personal_course_growth')
const kindIcon = computed(() => ({
  explanation: Lightbulb,
  counterexample: ScanSearch,
  transition: ArrowRight,
  understanding_check: CircleHelp,
}[props.block.kind]))
const kindLabel = computed(() => t(`adaptiveBlocks.kinds.${props.block.kind}`, t('adaptiveBlocks.kinds.explanation', '补充解释')))

const sendFeedback = (value: Exclude<AdaptiveBlockFeedback, 'unrated'>) => {
  feedback.value = value
  if (value === 'dismissed') dismissed.value = true
  void progressStore.feedbackAdaptiveBlock(courseStore.currentCourseId, props.block, value)
}
</script>

<style scoped>
.adaptive-block { position:relative; margin:24px 0 4px; padding:17px 0 15px 18px; border-left:3px solid #818cf8; color:var(--lz-text); background:linear-gradient(90deg,rgba(238,242,255,.72),rgba(255,255,255,0)); }
.adaptive-block[data-kind="counterexample"] { border-left-color:#f59e0b; background:linear-gradient(90deg,rgba(255,251,235,.78),rgba(255,255,255,0)); }
.adaptive-block[data-kind="transition"] { border-left-color:#22c55e; background:linear-gradient(90deg,rgba(240,253,244,.72),rgba(255,255,255,0)); }
.adaptive-block header { min-height:34px; display:grid; grid-template-columns:34px minmax(0,1fr) auto; align-items:center; gap:10px; }
.adaptive-block__icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:#4f46e5; background:rgba(255,255,255,.88); box-shadow:0 2px 8px rgba(79,70,229,.09); }
.adaptive-block header div:nth-child(2) { min-width:0; display:flex; flex-direction:column; gap:2px; }
.adaptive-block header small { color:var(--lz-text-muted); font-size:9px; font-weight:700; }
.adaptive-block header strong { color:var(--lz-text-strong); font-size:14px; }
.adaptive-block__actions { display:flex; gap:3px; }
.adaptive-block button { width:30px; height:30px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.adaptive-block button:hover,.adaptive-block button.active { color:var(--lz-brand-strong); background:rgba(255,255,255,.9); }
.adaptive-block__body { padding:12px 40px 0 44px; }
.adaptive-block__body > p { margin:0; color:var(--lz-text-secondary); font-size:13px; line-height:1.75; }
.adaptive-block__contrast { margin-top:7px!important; color:var(--lz-text)!important; }
.adaptive-block__steps { display:grid; gap:7px; margin:12px 0 0; padding:0; list-style:none; }.adaptive-block__steps li { display:grid; grid-template-columns:22px minmax(0,1fr); align-items:center; gap:8px; color:var(--lz-text-secondary); font-size:12px; }.adaptive-block__steps span { width:22px; height:22px; display:grid; place-items:center; border-radius:50%; color:#fff; background:#6366f1; font-size:9px; font-weight:800; }
.adaptive-block__check { margin-top:11px; display:grid; grid-template-columns:18px minmax(0,1fr) auto; align-items:center; gap:8px; padding:9px 10px; border:1px solid rgba(165,180,252,.56); border-radius:8px; background:rgba(255,255,255,.7); color:var(--lz-text); font-size:12px; }
.adaptive-block__check small { color:var(--lz-text-muted); font-size:9px; white-space:nowrap; }
.adaptive-block footer { margin-top:12px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
.adaptive-block footer > span { display:inline-flex; align-items:center; gap:5px; color:var(--lz-text-muted); font-size:9px; }
.adaptive-block footer > div { display:flex; gap:3px; }
@media (max-width:640px) {
  .adaptive-block { margin-top:20px; padding-left:13px; }
  .adaptive-block__body { padding:10px 4px 0 44px; }
  .adaptive-block__check { grid-template-columns:18px minmax(0,1fr); }
  .adaptive-block__check small { grid-column:2; white-space:normal; }
}
</style>
