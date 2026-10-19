<template>
  <component
    :is="toolbar && placement === 'top' ? 'header' : 'footer'"
    class="learning-dock"
    :class="{ 'has-resume': resumeActionLabel, 'is-toolbar': toolbar, 'is-bottom': toolbar && placement === 'bottom' }"
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
      <slot name="tools">
        <button v-if="navigatorHidden" type="button" class="learning-dock__domain" data-domain="navigator" :aria-label="t('learningShell.openNavigator')" @click="emit('navigator')"><PanelLeftOpen :size="16" /><span>{{ t('learningNavigator.title') }}</span></button>
        <button v-if="toolbar" type="button" class="learning-dock__domain" data-domain="reading" :class="{ 'is-active': activeDomain === 'course' }" :aria-current="activeDomain === 'course' ? 'page' : undefined" @click="emit('reading')"><BookOpenCheck :size="16" /><span>{{ t('studentWorkspace.reading') }}</span></button>
        <button
          type="button"
          class="learning-dock__domain"
          data-domain="question-book"
          :class="{ 'is-active': activeDomain === 'question-book' }"
          :aria-current="activeDomain === 'question-book' ? 'page' : undefined"
          :title="t('learningDock.questionBookHint', '查看本课程题目、练习与作答记录')"
          @click="emit('question-book')"
        >
          <BookOpenCheck :size="16" />
          <span>{{ t('learningDock.questionBook', '题库本') }}</span>
          <b v-if="questionCount" class="learning-dock__count">{{ questionCount }}</b>
        </button>
        <button v-if="toolbar" type="button" class="learning-dock__domain" data-domain="mistakes" :class="{ 'is-active': activeDomain === 'mistakes' }" :aria-current="activeDomain === 'mistakes' ? 'page' : undefined" @click="emit('mistakes')"><BookOpenCheck :size="16" /><span>{{ t('studentWorkspace.mistakes') }}</span></button>
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
          <span>{{ t('learningDock.knowledgeLibrary', '知识树') }}</span>
        </button>
        <button
          type="button"
          class="learning-dock__domain"
          data-domain="notebook"
          :class="{ 'is-active': notebookOpen || activeDomain === 'notebook' }"
          :aria-current="activeDomain === 'notebook' ? 'page' : undefined"
          :aria-pressed="notebookOpen || activeDomain === 'notebook'"
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
          data-domain="assistant"
          :class="{ 'is-active': assistantOpen || activeDomain === 'assistant' }"
          :aria-pressed="assistantOpen || activeDomain === 'assistant'"
          :aria-expanded="assistantOpen"
          :title="t('learningDock.assistantHint', '在当前页面打开 AI 老师')"
          @click="emit('ai')"
        >
          <span>{{ t('learningDock.assistant', 'AI 助手') }}</span>
        </button>
      </slot>
    </nav>
  </component>
</template>

<script setup lang="ts">
import {
  ArrowRight,
  BookOpenCheck,
  ChartNoAxesCombined,
  Library,
  LoaderCircle,
  MapPin,
  NotebookTabs,
  PanelLeftOpen,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  location: string
  assistantOpen?: boolean
  toolbar?: boolean
  placement?: 'top' | 'bottom'
  navigatorHidden?: boolean
  notebookOpen?: boolean
  activeDomain?: 'mistakes' | 'course' | 'notebook' | 'question-book' | 'overview' | 'knowledge-library' | 'assistant'
  noteCount?: number
  questionCount?: number
  resumeActionLabel?: string
  resumeActionAvailable?: boolean
  resumeActionBusy?: boolean
}>(), {
  toolbar: false,
  placement: 'top',
  navigatorHidden: false,
  notebookOpen: false,
  activeDomain: 'course',
  assistantOpen: false,
  noteCount: 0,
  questionCount: 0,
  resumeActionLabel: '',
  resumeActionAvailable: true,
  resumeActionBusy: false,
})

const emit = defineEmits<{
  (event: 'navigator' | 'notebook' | 'question-book' | 'stats' | 'knowledge-library' | 'ai' | 'resume' | 'reading' | 'mistakes'): void
}>()
</script>

<style scoped>
.learning-dock {
  position: relative; min-width: 0; flex: none; min-height: 60px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px 16px; padding: 9px 16px; border-top: 1px solid #e1e5f0;
  background: linear-gradient(180deg, #fff, #fcfcff);
}
.learning-dock.is-toolbar:not(.is-bottom) { border-top: 0; border-bottom: 1px solid #e1e5f0; }
.learning-dock__location { min-width: 0; display: flex; align-items: center; gap: 7px; color: var(--lz-text-muted); }
.learning-dock__location span { display: none; }
.learning-dock__location strong { max-width: 230px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 500; }
.learning-dock__actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 4px; margin-left: auto; }
.learning-dock :deep(button) { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 7px 10px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--lz-text-secondary); font: inherit; font-size: 15px; cursor: pointer; white-space: nowrap; }
.learning-dock :deep(button:hover:not(:disabled)), .learning-dock :deep(button.is-active) { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.learning-dock :deep(button:focus-visible) { outline: 2px solid var(--lz-brand); outline-offset: 2px; }
.learning-dock :deep(button:disabled) { opacity: .5; cursor: not-allowed; }
.learning-dock__count { font-size: 13px; font-weight: 500; color: var(--lz-text-muted); }
.learning-dock__divider { height: 20px; width: 1px; margin: 0 4px; background: #e2e8f0; }
.learning-dock__resume { min-width: 0; }
.learning-dock__resume > button { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.learning-dock__spin { animation: learning-dock-spin .8s linear infinite; }
@keyframes learning-dock-spin { to { transform: rotate(360deg); } }
@media(max-width: 1280px) { .learning-dock { flex-wrap: wrap; } .learning-dock__location { display: none; } }
@media(prefers-reduced-motion: reduce) { .learning-dock__spin { animation: none; } }
</style>
