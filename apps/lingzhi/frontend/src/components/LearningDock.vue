<template>
  <component
    :is="toolbar && placement === 'top' ? 'header' : 'footer'"
    class="learning-dock"
    :class="{ 'has-resume': resumeActionLabel, 'is-toolbar': toolbar, 'is-bottom': toolbar && placement === 'bottom', 'has-mobile-more': hasMobileMore }"
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
          <PencilLine :size="16" />
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
          :title="t('learningDock.statsHint', '查看知识点红绿痕迹与正式学习证据')"
          @click="emit('stats')"
        >
          <ChartNoAxesCombined :size="16" />
          <span>{{ t('learningDock.stats', '学习画像') }}</span>
        </button>
        <span class="learning-dock__divider" aria-hidden="true"></span>
        <button
          type="button"
          class="learning-dock__domain"
          data-domain="knowledge-library"
          :class="{ 'is-active': activeDomain === 'knowledge-library' }"
          :aria-current="activeDomain === 'knowledge-library' ? 'page' : undefined"
          :title="t('learningDock.knowledgeLibraryHint', '查看本课知识内容、例题与课程覆盖')"
          @click="emit('knowledge-library')"
        >
          <Library :size="16" />
          <span>{{ t('learningDock.knowledgeLibrary', '本课知识') }}</span>
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
      <button
        v-if="hasMobileMore"
        ref="moreButton"
        type="button"
        class="learning-dock__more"
        :class="{ 'is-active': mobileMoreOpen || isMoreToolActive }"
        :aria-expanded="mobileMoreOpen"
        :aria-pressed="mobileMoreOpen || isMoreToolActive"
        aria-controls="learning-dock-more-panel"
        @click="toggleMore"
      >
        <Ellipsis :size="20" />
        <span>{{ t('learningDock.more', '更多') }}</span>
      </button>
    </nav>

    <Transition name="learning-dock-more">
      <div v-if="hasMobileMore && mobileMoreOpen" class="learning-dock__more-layer">
        <button
          type="button"
          class="learning-dock__more-backdrop"
          :aria-label="t('common.close', '关闭')"
          @click="closeMore"
        ></button>
        <section
          id="learning-dock-more-panel"
          ref="morePanel"
          class="learning-dock__more-panel"
          role="dialog"
          aria-modal="true"
          :aria-label="t('learningDock.moreTools', '更多学习工具')"
          tabindex="-1"
          @keydown="handleMoreKeydown"
        >
          <header>
            <div>
              <h2>{{ t('learningDock.moreTools', '更多学习工具') }}</h2>
              <p>{{ moreHint || t('learningDock.moreToolsHint', '错题、知识树、课程目录与学习概况') }}</p>
            </div>
            <button type="button" :aria-label="t('common.close', '关闭')" @click="closeMore"><X :size="19" /></button>
          </header>
          <div class="learning-dock__more-actions" @click="closeMore">
            <slot name="mobile-more" />
          </div>
        </section>
      </div>
    </Transition>
  </component>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, toRefs, useSlots } from 'vue'
import {
  ArrowRight,
  BookOpenCheck,
  ChartNoAxesCombined,
  Ellipsis,
  Library,
  LoaderCircle,
  MapPin,
  NotebookTabs,
  PanelLeftOpen,
  PencilLine,
  X,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  location: string
  moreHint?: string
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
const { moreHint, location, assistantOpen, toolbar, placement, navigatorHidden, notebookOpen, activeDomain, noteCount, questionCount, resumeActionLabel, resumeActionAvailable, resumeActionBusy } = toRefs(props)

const emit = defineEmits<{
  (event: 'more-toggle', open: boolean): void
  (event: 'navigator' | 'notebook' | 'question-book' | 'stats' | 'knowledge-library' | 'ai' | 'resume' | 'reading' | 'mistakes'): void
}>()

const slots = useSlots()
const hasMobileMore = computed(() => Boolean(slots['mobile-more']))
const mobileMoreOpen = ref(false)
const moreButton = ref<HTMLButtonElement | null>(null)
const morePanel = ref<HTMLElement | null>(null)
const isMoreToolActive = computed(() => ['mistakes', 'overview', 'knowledge-library'].includes(props.activeDomain || ''))

async function toggleMore() {
  if (mobileMoreOpen.value) {
    closeMore()
    return
  }
  mobileMoreOpen.value = true
  emit('more-toggle', true)
  await nextTick()
  morePanel.value?.querySelector<HTMLElement>('button:not(:disabled), a[href], select:not(:disabled)')?.focus()
}

function closeMore() {
  if (!mobileMoreOpen.value) return
  mobileMoreOpen.value = false
  emit('more-toggle', false)
  void nextTick(() => moreButton.value?.focus())
}

function handleMoreKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMore()
    return
  }
  if (event.key !== 'Tab' || !morePanel.value) return
  const items = [...morePanel.value.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select:not(:disabled)')]
  if (!items.length) {
    event.preventDefault()
    morePanel.value.focus()
    return
  }
  const first = items[0]!
  const last = items[items.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
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
@media (max-width: 767px), (min-width: 768px) and (max-width: 1023px) and (max-height: 520px) {
  .learning-dock.is-toolbar.is-bottom {
    display: block;
    box-sizing: border-box;
    min-height: 62px;
    padding: 4px max(6px, env(safe-area-inset-right, 0px)) calc(4px + env(safe-area-inset-bottom, 0px)) max(6px, env(safe-area-inset-left, 0px));
    border-top: 1px solid #e3e7ef;
    background: rgba(255,255,255,.98);
    box-shadow: 0 -5px 18px rgba(29,39,66,.055);
  }
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    align-items: stretch;
    gap: 2px;
    margin: 0;
  }
  .learning-dock.is-toolbar.is-bottom.has-mobile-more .learning-dock__actions { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .learning-dock.is-toolbar.is-bottom .learning-dock__divider,
  .learning-dock.is-toolbar.is-bottom .learning-dock__resume,
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep([data-domain="navigator"]),
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep([data-domain="mistakes"]),
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep([data-domain="overview"]),
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep([data-domain="knowledge-library"]) { display: none; }
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep(.learning-dock__domain),
  .learning-dock.is-toolbar.is-bottom .learning-dock__more {
    position: relative;
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    min-height: 54px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    padding: 4px 1px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.2;
    white-space: normal;
  }
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep(.learning-dock__domain > svg),
  .learning-dock.is-toolbar.is-bottom .learning-dock__more > svg { flex: none; width: 19px; height: 19px; }
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep(.learning-dock__domain[data-domain="assistant"] > span:first-of-type) { font-size: 12px; }
  .learning-dock.is-toolbar.is-bottom .learning-dock__actions :deep(.learning-dock__count) { position: absolute; top: 2px; right: calc(50% - 24px); min-width: 15px; padding: 1px 3px; border-radius: 8px; color: #fff; background: var(--lz-brand-strong); font-size: 9px; line-height: 1.2; text-align: center; }
  .learning-dock.is-toolbar.is-bottom .learning-dock__more { display: flex; }
  .learning-dock__more-layer { position: fixed; inset: 0; z-index: 150; display: grid; align-items: end; padding: 8px 8px max(10px, env(safe-area-inset-bottom, 0px)); background: rgba(24,31,49,.28); }
  .learning-dock__more-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; cursor: default; }
  .learning-dock__more-panel { position: relative; z-index: 1; width: min(520px,100%); max-height: min(68dvh,620px); overflow: auto; box-sizing: border-box; margin: 0 auto; padding: 16px 15px max(14px, env(safe-area-inset-bottom, 0px)); border: 1px solid #e2e6ee; border-radius: 19px 19px 13px 13px; background: #fff; box-shadow: 0 18px 48px rgba(20,28,47,.2); overscroll-behavior: contain; }
  .learning-dock__more-panel > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
  .learning-dock__more-panel h2 { margin: 0; color: var(--lz-text-strong); font-size: 17px; line-height: 1.4; }
  .learning-dock__more-panel p { margin: 3px 0 0; color: var(--lz-text-secondary); font-size: 13px; line-height: 1.45; }
  .learning-dock__more-panel > header > button { flex: none; width: 42px; min-height: 42px; padding: 0; border: 1px solid var(--lz-border); border-radius: 10px; background: #fff; }
  .learning-dock__more-actions { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; }
  .learning-dock__more-actions :slotted(.learning-dock__more-action) { box-sizing: border-box; min-width: 0; min-height: 58px; display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid #e1e5ed; border-radius: 12px; color: var(--lz-text-strong); background: #fff; font: inherit; font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; }
  .learning-dock__more-actions :slotted(.learning-dock__more-action:hover),
  .learning-dock__more-actions :slotted(.learning-dock__more-action:focus-visible) { border-color: #c7c4f3; color: var(--lz-brand-strong); background: #f8f7ff; outline: none; }
  .learning-dock__more-actions :slotted(.learning-dock__more-action.is-active) { border-color: #d4d1f4; color: var(--lz-brand-strong); background: #f5f4ff; }
  .learning-dock__more-actions :slotted(.learning-dock__more-action > svg) { flex: none; color: var(--lz-brand-strong); }
  .learning-dock-more-enter-active,.learning-dock-more-leave-active { transition: opacity .18s ease; }
  .learning-dock-more-enter-active .learning-dock__more-panel,.learning-dock-more-leave-active .learning-dock__more-panel { transition: transform .2s cubic-bezier(.2,.8,.2,1); }
  .learning-dock-more-enter-from,.learning-dock-more-leave-to { opacity: 0; }
  .learning-dock-more-enter-from .learning-dock__more-panel,.learning-dock-more-leave-to .learning-dock__more-panel { transform: translateY(12px); }
}
@media (min-width:768px) and (min-height:521px), (min-width:1024px) { .learning-dock__more { display: none !important; } .learning-dock__more-layer { display: none !important; } }
@media (prefers-reduced-motion: reduce) { .learning-dock-more-enter-active,.learning-dock-more-leave-active,.learning-dock-more-enter-active .learning-dock__more-panel,.learning-dock-more-leave-active .learning-dock__more-panel { transition: none; } }
@media(prefers-reduced-motion: reduce) { .learning-dock__spin { animation: none; } }
</style>
