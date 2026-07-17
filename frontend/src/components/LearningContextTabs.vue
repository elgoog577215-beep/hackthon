<template>
  <nav
    v-if="domain !== 'assistant'"
    class="learning-context-tabs"
    role="tablist"
    :aria-label="domain === 'learning'
      ? t('learningDock.learningTabs', '学习功能')
      : t('learningDock.resourceTabs', '资源功能')"
  >
    <template v-if="domain === 'learning'">
      <button
        type="button"
        role="tab"
        data-context-item="practice"
        :class="{ 'is-active': activeItem === 'practice' }"
        :aria-selected="activeItem === 'practice'"
        :disabled="!practiceAvailable"
        :title="practiceAvailable ? t('learningDock.practiceHint', '打开当前章节的正式练习') : t('learningDock.practiceUnavailable', '当前章节暂时没有正式练习')"
        @click="emit('practice')"
      >
        <ClipboardCheck :size="16" />
        <span>{{ t('learningDock.practice', '当前练习') }}</span>
      </button>
      <button
        type="button"
        role="tab"
        data-context-item="records"
        :class="{ 'is-active': activeItem === 'records' }"
        :aria-selected="activeItem === 'records'"
        :title="t('learningDock.recordsHint', '查看本课程的笔记、问答与待复习记录')"
        @click="emit('records')"
      >
        <NotebookTabs :size="16" />
        <span>{{ t('learningDock.records', '学习记录') }}</span>
        <strong v-if="recordCount" class="learning-context-tabs__count">{{ recordCount }}</strong>
      </button>
      <button
        type="button"
        role="tab"
        data-context-item="stats"
        :class="{ 'is-active': activeItem === 'stats' }"
        :aria-selected="activeItem === 'stats'"
        :title="t('learningDock.statsHint', '查看阅读、掌握与正式学习证据')"
        @click="emit('stats')"
      >
        <ChartNoAxesCombined :size="16" />
        <span>{{ t('learningDock.stats', '学习概况') }}</span>
      </button>
    </template>

    <template v-else>
      <button
        type="button"
        role="tab"
        data-context-item="knowledge-library"
        :class="{ 'is-active': activeItem === 'knowledge-library' }"
        :aria-selected="activeItem === 'knowledge-library'"
        :title="t('learningDock.knowledgeLibraryHint', '查看学科知识与本课覆盖')"
        @click="emit('knowledge-library')"
      >
        <Library :size="16" />
        <span>{{ t('learningDock.knowledgeLibrary', '知识库') }}</span>
      </button>
      <button
        type="button"
        role="tab"
        data-context-item="teaching-resources"
        :class="{ 'is-active': activeItem === 'teaching-resources' }"
        :aria-selected="activeItem === 'teaching-resources'"
        :title="t('learningDock.resourcesHint', '查看由当前课程同步生成的教学资源')"
        @click="emit('resources')"
      >
        <Layers3 :size="16" />
        <span>{{ t('learningDock.resources', '教学资源') }}</span>
      </button>
    </template>
  </nav>
</template>

<script setup lang="ts">
import { ChartNoAxesCombined, ClipboardCheck, Layers3, Library, NotebookTabs } from 'lucide-vue-next'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  domain: 'learning' | 'resources' | 'assistant'
  activeItem: 'practice' | 'records' | 'stats' | 'knowledge-library' | 'teaching-resources' | 'assistant'
  recordCount?: number
  practiceAvailable?: boolean
}>(), {
  recordCount: 0,
  practiceAvailable: false,
})

const emit = defineEmits<{
  (event: 'practice' | 'records' | 'stats' | 'knowledge-library' | 'resources'): void
}>()
</script>

<style scoped>
.learning-context-tabs { min-height:50px; flex:0 0 auto; display:flex; align-items:center; justify-content:center; gap:4px; padding:7px 14px; border-bottom:1px solid var(--lz-border); background:rgba(255,255,255,.96); }
.learning-context-tabs button { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 15px; border:1px solid transparent; border-radius:9px; color:var(--lz-text-secondary); background:transparent; font-size:11px; font-weight:650; cursor:pointer; transition:color .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease; }
.learning-context-tabs button:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#e0e7ff; background:#f7f7ff; }
.learning-context-tabs button:focus-visible { outline:2px solid #818cf8; outline-offset:2px; }
.learning-context-tabs button:disabled { color:#cbd5e1; cursor:not-allowed; }
.learning-context-tabs button.is-active { color:var(--lz-brand-strong); border-color:#dfe4ff; background:linear-gradient(180deg,#f8f7ff,#f0f1ff); box-shadow:0 2px 8px rgba(79,70,229,.08); }
.learning-context-tabs__count { min-width:17px; height:17px; display:grid; place-items:center; padding:0 4px; border-radius:9px; color:var(--lz-brand-strong); background:#e6e9ff; font-size:9px; }
@media (max-width: 767px) {
  .learning-context-tabs { min-height:44px; justify-content:flex-start; overflow-x:auto; padding:5px 8px; scrollbar-width:none; }
  .learning-context-tabs::-webkit-scrollbar { display:none; }
  .learning-context-tabs button { min-height:32px; flex:0 0 auto; padding:0 11px; font-size:10px; }
}
</style>
