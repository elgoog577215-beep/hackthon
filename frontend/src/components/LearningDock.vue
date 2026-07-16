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

    <div class="learning-dock__actions">
      <button type="button" :title="t('learningDock.recordsHint', '查看本课程的笔记、问答与待复习记录')" @click="emit('records')">
        <NotebookTabs :size="15" />
        <span>{{ t('learningDock.records', '学习记录') }}</span>
        <strong v-if="recordCount" class="learning-dock__count">{{ recordCount }}</strong>
      </button>
      <button
        type="button"
        class="learning-dock__practice"
        :disabled="!practiceAvailable"
        :title="practiceAvailable ? t('learningDock.practiceHint', '打开当前章节的正式练习') : t('learningDock.practiceUnavailable', '当前章节暂时没有正式练习')"
        @click="emit('practice')"
      >
        <ClipboardCheck :size="15" />
        <span>{{ t('learningDock.practice', '当前练习') }}</span>
      </button>
      <button type="button" :title="t('learningDock.statsHint', '查看学习进度与练习统计')" @click="emit('stats')">
        <ChartNoAxesCombined :size="15" />
        <span>{{ t('learningDock.stats', '学习概况') }}</span>
      </button>
      <button type="button" :title="t('learningDock.knowledgeLibraryHint', '查看学科知识与本课覆盖')" @click="emit('knowledge-library')">
        <Library :size="15" />
        <span>{{ t('learningDock.knowledgeLibrary', '知识库') }}</span>
      </button>
      <button type="button" :title="t('learningDock.resourcesHint', '查看由当前课程同步生成的大纲、教案、讲义、练习册和演示文稿')" @click="emit('resources')">
        <Layers3 :size="15" />
        <span>{{ t('learningDock.resources', '教学资源') }}</span>
      </button>
      <button type="button" :title="t('learningDock.aiHint', '打开 AI 老师')" @click="emit('ai')">
        <MessageSquareText :size="15" />
        <span>{{ t('learningDock.ai', 'AI 老师') }}</span>
      </button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { ArrowRight, ChartNoAxesCombined, ClipboardCheck, Layers3, Library, LoaderCircle, MapPin, MessageSquareText, NotebookTabs } from 'lucide-vue-next'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  location: string
  recordCount?: number
  practiceAvailable?: boolean
  resumeActionLabel?: string
  resumeActionAvailable?: boolean
  resumeActionBusy?: boolean
}>(), {
  recordCount: 0,
  practiceAvailable: false,
  resumeActionLabel: '',
  resumeActionAvailable: true,
  resumeActionBusy: false,
})

const emit = defineEmits<{
  (event: 'records' | 'practice' | 'stats' | 'knowledge-library' | 'resources' | 'ai' | 'resume'): void
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
.learning-dock__actions { flex:0 0 auto; display:flex; align-items:center; gap:3px; }
.learning-dock button { position:relative; min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 10px; border:1px solid transparent; border-radius:9px; color:var(--lz-text-secondary); background:transparent; font-size:11px; font-weight:600; cursor:pointer; transition:background .16s ease, border-color .16s ease, color .16s ease, box-shadow .16s ease; }
.learning-dock button:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#e0e7ff; background:#f5f7ff; }
.learning-dock button:focus-visible { outline:2px solid #818cf8; outline-offset:2px; }
.learning-dock button:disabled { color:#cbd5e1; cursor:not-allowed; }
.learning-dock button.learning-dock__practice { padding:0 13px; color:#fff; border-color:#6366f1; background:linear-gradient(135deg, #6366f1, #7c3aed); box-shadow:0 5px 12px rgba(99,102,241,.2); }
.learning-dock button.learning-dock__practice:hover:not(:disabled) { color:#fff; border-color:#4f46e5; background:linear-gradient(135deg, #4f46e5, #6d28d9); box-shadow:0 7px 16px rgba(99,102,241,.25); }
.learning-dock button.learning-dock__practice:disabled { color:#94a3b8; border-color:#e2e8f0; background:#f1f5f9; box-shadow:none; }
.learning-dock.has-resume button.learning-dock__practice { color:var(--lz-text-secondary); border-color:transparent; background:transparent; box-shadow:none; }
.learning-dock.has-resume button.learning-dock__practice:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#e0e7ff; background:#f5f7ff; box-shadow:none; }
.learning-dock__count { min-width:17px; height:17px; display:grid; place-items:center; padding:0 4px; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:9px; }
@container (max-width: 760px) {
  .learning-dock__location span { display:none; }
  .learning-dock__location strong { max-width:140px; }
  .learning-dock__resume > button { width:36px; padding:0; }
  .learning-dock__resume > button span { display:none; }
  .learning-dock button { width:36px; padding:0; }
  .learning-dock button span { display:none; }
  .learning-dock button.learning-dock__practice { width:40px; padding:0; }
  .learning-dock__count { position:absolute; top:0; right:0; min-width:14px; height:14px; font-size:8px; }
}
@keyframes learning-dock-spin { to { transform:rotate(360deg); } }
@media (max-width: 767px) { .learning-dock { display:none; } }
</style>
