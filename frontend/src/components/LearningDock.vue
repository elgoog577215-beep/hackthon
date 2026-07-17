<template>
  <footer class="learning-dock" :class="{ 'has-resume': resumeActionLabel }" :aria-label="t('learningDock.title', '学习工具')">
    <div class="learning-dock__location" :title="location">
      <MapPin :size="14" />
      <span>{{ t('learningDock.location', '当前位置') }}</span>
      <strong>{{ location }}</strong>
    </div>

    <div v-if="resumeActionLabel" class="learning-dock__resume">
      <button
        type="button"
        :disabled="resumeActionBusy || !resumeActionAvailable"
        :title="resumeActionLabel"
        @click="emit('resume')"
      >
        <LoaderCircle v-if="resumeActionBusy" :size="15" class="learning-dock__spin" />
        <ArrowRight v-else :size="15" />
        <span>{{ resumeActionLabel }}</span>
      </button>
    </div>

    <nav class="learning-dock__actions" :aria-label="t('learningDock.primaryNavigation', '学习空间导航')">
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="learning"
        :class="{ 'is-active': activeDomain === 'learning' }"
        :aria-current="activeDomain === 'learning' ? 'page' : undefined"
        :title="t('learningDock.learningHint', '切换学习功能')"
        @click="emit('learning')"
      >
        <GraduationCap :size="16" />
        <span>{{ t('learningDock.learning', '学习') }}</span>
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="resources"
        :class="{ 'is-active': activeDomain === 'resources' }"
        :aria-current="activeDomain === 'resources' ? 'page' : undefined"
        :title="t('learningDock.resourceDomainHint', '切换知识库、大纲、教案、讲义与练习册')"
        @click="emit('resources')"
      >
        <Layers3 :size="16" />
        <span>{{ t('learningDock.resourceDomain', '资源') }}</span>
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="assistant"
        :class="{ 'is-active': activeDomain === 'assistant' }"
        :aria-current="activeDomain === 'assistant' ? 'page' : undefined"
        :title="t('learningDock.assistantHint', '在当前页面打开 AI 老师')"
        @click="emit('ai')"
      >
        <MessageSquareText :size="16" />
        <span>{{ t('learningDock.assistant', '智能助教') }}</span>
      </button>
    </nav>
  </footer>
</template>

<script setup lang="ts">
import { ArrowRight, GraduationCap, Layers3, LoaderCircle, MapPin, MessageSquareText } from 'lucide-vue-next'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  location: string
  activeDomain?: 'learning' | 'resources' | 'assistant'
  recordCount?: number
  practiceAvailable?: boolean
  resumeActionLabel?: string
  resumeActionAvailable?: boolean
  resumeActionBusy?: boolean
}>(), {
  activeDomain: 'learning',
  recordCount: 0,
  practiceAvailable: false,
  resumeActionLabel: '',
  resumeActionAvailable: true,
  resumeActionBusy: false,
})

const emit = defineEmits<{
  (event: 'learning' | 'resources' | 'ai' | 'resume'): void
}>()
</script>

<style scoped>
.learning-dock { min-width:0; min-height:54px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:14px; padding:7px 10px 7px 14px; border-top:1px solid rgba(224,231,255,.9); background:linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,250,255,.98)); box-shadow:0 -8px 24px rgba(79,70,229,.05); }
.learning-dock__location { min-width:0; display:grid; grid-template-columns:14px auto minmax(0,1fr); align-items:center; gap:6px; color:var(--lz-text-muted); }
.learning-dock__location svg { color:#818cf8; }
.learning-dock__location span { font-size:10px; white-space:nowrap; }
.learning-dock__location strong { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-secondary); font-size:11px; font-weight:650; }
.learning-dock__resume { min-width:0; flex:0 1 auto; display:flex; align-items:center; }
.learning-dock__resume > button { min-width:0; color:#fff; border-color:#15803d; background:#15803d; box-shadow:0 4px 10px rgba(21,128,61,.16); }
.learning-dock__resume > button:hover:not(:disabled) { color:#fff; border-color:#166534; background:#166534; }
.learning-dock__resume > button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.learning-dock__spin { animation:learning-dock-spin .8s linear infinite; }
.learning-dock__actions { flex:0 0 auto; display:flex; align-items:center; gap:4px; }
.learning-dock button { position:relative; min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border:1px solid transparent; border-radius:9px; color:var(--lz-text-secondary); background:transparent; font-size:11px; font-weight:650; cursor:pointer; transition:background .16s ease, border-color .16s ease, color .16s ease, box-shadow .16s ease; }
.learning-dock button:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#e0e7ff; background:#f5f7ff; }
.learning-dock button:focus-visible { outline:2px solid #818cf8; outline-offset:2px; }
.learning-dock button:disabled { color:#cbd5e1; cursor:not-allowed; }
.learning-dock__domain.is-active { color:var(--lz-brand-strong); border-color:#dfe4ff; background:linear-gradient(180deg,#f7f7ff,#eef0ff); box-shadow:0 3px 10px rgba(79,70,229,.09); }
@container (max-width: 760px) {
  .learning-dock__location span { display:none; }
  .learning-dock__location strong { max-width:140px; }
  .learning-dock__resume > button { width:36px; padding:0; }
  .learning-dock__resume > button span { display:none; }
  .learning-dock__domain { width:40px; padding:0; }
  .learning-dock__domain span { display:none; }
}
@keyframes learning-dock-spin { to { transform:rotate(360deg); } }
@media (max-width: 767px) { .learning-dock { display:none; } }
</style>
