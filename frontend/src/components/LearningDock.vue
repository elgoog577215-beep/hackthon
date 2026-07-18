<template>
  <footer
    class="learning-dock"
    :class="{ 'has-resume': resumeActionLabel }"
    :aria-label="t('learningDock.title', '学习工具')"
  >
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

    <nav class="learning-dock__actions" :aria-label="t('learningDock.primaryNavigation', '学习辅助导航')">
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="notebook"
        :class="{ 'is-active': activeDomain === 'notebook' }"
        :aria-current="activeDomain === 'notebook' ? 'page' : undefined"
        :title="t('learningDock.notebookHint', '查看本课程的笔记与学习标记')"
        @click="emit('notebook')"
      >
        <NotebookTabs :size="16" />
        <span>{{ t('learningDock.notebook', '笔记本') }}</span>
        <b v-if="noteCount" class="learning-dock__count">{{ noteCount }}</b>
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="mistake-book"
        :class="{ 'is-active': activeDomain === 'mistake-book' }"
        :aria-current="activeDomain === 'mistake-book' ? 'page' : undefined"
        :title="t('learningDock.mistakeBookHint', '查看未通过或需要继续巩固的正式练习')"
        @click="emit('mistake-book')"
      >
        <BookX :size="16" />
        <span>{{ t('learningDock.mistakeBook', '错题本') }}</span>
        <b v-if="mistakeCount" class="learning-dock__count is-error">{{ mistakeCount }}</b>
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="overview"
        :class="{ 'is-active': activeDomain === 'overview' }"
        :aria-current="activeDomain === 'overview' ? 'page' : undefined"
        :title="t('learningDock.statsHint', '查看阅读、掌握与正式学习证据')"
        @click="emit('stats')"
      >
        <ChartNoAxesCombined :size="16" />
        <span>{{ t('learningDock.stats', '学习概况') }}</span>
      </button>
      <span class="learning-dock__divider" aria-hidden="true"></span>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="knowledge-library"
        :class="{ 'is-active': activeDomain === 'knowledge-library' }"
        :aria-current="activeDomain === 'knowledge-library' ? 'page' : undefined"
        :title="t('learningDock.knowledgeLibraryHint', '查看学科知识与本课覆盖')"
        @click="emit('knowledge-library')"
      >
        <Library :size="16" />
        <span>{{ t('learningDock.knowledgeLibrary', '知识库') }}</span>
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
import {
  ArrowRight,
  BookX,
  ChartNoAxesCombined,
  Library,
  LoaderCircle,
  MapPin,
  MessageSquareText,
  NotebookTabs,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  location: string
  activeDomain?: 'course' | 'notebook' | 'mistake-book' | 'overview' | 'knowledge-library' | 'assistant'
  noteCount?: number
  mistakeCount?: number
  resumeActionLabel?: string
  resumeActionAvailable?: boolean
  resumeActionBusy?: boolean
}>(), {
  activeDomain: 'course',
  noteCount: 0,
  mistakeCount: 0,
  resumeActionLabel: '',
  resumeActionAvailable: true,
  resumeActionBusy: false,
})

const emit = defineEmits<{
  (event: 'notebook' | 'mistake-book' | 'stats' | 'knowledge-library' | 'ai' | 'resume'): void
}>()
</script>

<style scoped>
.learning-dock { position:relative; min-width:0; min-height:58px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:14px; overflow:visible; padding:8px 12px 8px 16px; border-top:1px solid rgba(224,231,255,.94); background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(248,250,255,.99)); box-shadow:0 -8px 24px rgba(79,70,229,.05); }
.learning-dock__location { min-width:0; display:grid; grid-template-columns:14px auto minmax(0,1fr); align-items:center; gap:7px; color:var(--lz-text-muted); }
.learning-dock__location svg { color:#818cf8; }
.learning-dock__location span { font-size:10px; white-space:nowrap; }
.learning-dock__location strong { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-secondary); font-size:11px; font-weight:650; }
.learning-dock__resume { min-width:0; flex:0 1 auto; display:flex; align-items:center; }
.learning-dock__resume > button { min-width:0; color:#fff; border-color:#15803d; background:#15803d; box-shadow:0 4px 10px rgba(21,128,61,.16); }
.learning-dock__resume > button:hover:not(:disabled) { color:#fff; border-color:#166534; background:#166534; }
.learning-dock__resume > button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.learning-dock__spin { animation:learning-dock-spin .8s linear infinite; }
.learning-dock__actions { flex:0 0 auto; display:flex; align-items:center; gap:4px; }
.learning-dock button { position:relative; min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 12px; border:1px solid transparent; border-radius:10px; color:var(--lz-text-secondary); background:transparent; font-size:11px; font-weight:680; cursor:pointer; transition:background .16s ease,border-color .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease; }
.learning-dock button:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#dfe4ff; background:#f5f7ff; }
.learning-dock button:focus-visible { outline:3px solid rgba(99,102,241,.26); outline-offset:2px; }
.learning-dock button:disabled { color:#a9b4c8; cursor:not-allowed; }
.learning-dock__domain.is-active { color:var(--lz-brand-strong); border-color:#cfd6ff; background:linear-gradient(180deg,#f8f7ff,#eef0ff); box-shadow:0 3px 10px rgba(79,70,229,.1); }
.learning-dock__divider { width:1px; height:24px; margin:0 3px; background:#e2e8f0; }
.learning-dock__count { position:absolute; top:-5px; right:-3px; min-width:18px; height:18px; display:grid; place-items:center; padding:0 5px; border:2px solid #fff; border-radius:999px; color:#fff; background:#6366f1; font-size:9px; line-height:1; box-sizing:border-box; }
.learning-dock__count.is-error { background:#ef4444; }
@container (max-width:860px) {
  .learning-dock__location span { display:none; }
  .learning-dock__location strong { max-width:120px; }
  .learning-dock__resume > button { width:38px; padding:0; }
  .learning-dock__resume > button span { display:none; }
  .learning-dock__domain { padding-inline:9px; }
}
@keyframes learning-dock-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .learning-dock { position:fixed; left:0; right:0; bottom:0; z-index:120; min-height:calc(58px + env(safe-area-inset-bottom,0px)); padding:4px 4px env(safe-area-inset-bottom,0px); }
  .learning-dock__location,.learning-dock__resume,.learning-dock__divider { display:none; }
  .learning-dock__actions { width:100%; display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:2px; }
  .learning-dock__domain { min-width:0; min-height:50px; flex-direction:column; gap:2px; padding:3px 1px; border-radius:9px; font-size:9px; line-height:1.1; }
  .learning-dock__domain > span { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .learning-dock__count { top:1px; right:max(2px,calc(50% - 23px)); }
}
@media (prefers-reduced-motion:reduce) {
  .learning-dock button { transition:none; }
}
</style>
