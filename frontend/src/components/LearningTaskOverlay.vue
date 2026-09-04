<template>
  <section
    ref="modalRoot"
    class="question-book-modal"
    tabindex="-1"
    @keydown.esc.prevent="emit('close')"
  >
    <button
      class="question-book-modal__backdrop"
      type="button"
      :aria-label="t('taskOverlay.close', '关闭并返回正文')"
      @click="emit('close')"
    ></button>

    <section
      class="question-book-dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="dialogTitleId"
      :aria-describedby="dialogDescriptionId"
      data-testid="question-book-dialog"
    >
      <header class="question-book-dialog__header">
        <div class="question-book-dialog__identity">
          <span class="question-book-dialog__mark" aria-hidden="true">
            <BookOpenCheck :size="19" />
          </span>
          <div>
            <strong :id="dialogTitleId">{{ t('questionBook.title', '题库本') }}</strong>
            <span :id="dialogDescriptionId">
              <MathText :content="t('questionBook.currentTarget', '当前目标 · {target}')
                .replace('{target}', nodeLabel || t('courseWorkspace.allCourse', '全课程'))" />
            </span>
          </div>
        </div>

        <nav class="question-book-dialog__views" :aria-label="t('courseWorkspace.practice.views', '练习视图')">
          <button :class="{ active: practiceView === 'current' }" @click="setPracticeView('current')">
            {{ t('courseWorkspace.practice.current', '当前练习') }}
          </button>
          <button :class="{ active: practiceView === 'history' }" @click="setPracticeView('history')">
            {{ t('courseWorkspace.practice.history', '练习历史') }}
          </button>
          <button :class="{ active: practiceView === 'needs_review' }" @click="setPracticeView('needs_review')">
            {{ t('courseWorkspace.practice.needsReview', '错题本') }}
          </button>
        </nav>

        <div class="question-book-dialog__actions">
          <span v-if="recordCount" class="question-book-dialog__count">
            {{ t('questionBook.savedCount', '已收录 {count} 项').replace('{count}', String(recordCount)) }}
          </span>
          <button
            ref="closeButton"
            class="question-book-dialog__close"
            type="button"
            :title="t('taskOverlay.close', '关闭并返回正文')"
            :aria-label="t('taskOverlay.close', '关闭并返回正文')"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </div>
      </header>

      <PracticeWorkspace
        ref="practiceWorkspace"
        class="question-book-dialog__workspace"
        :course-id="courseId"
        :node-id="nodeId"
        :node-label="nodeLabel"
        hide-view-switch
        scope="node"
        @ask-teacher="emit('askTeacher', $event)"
        @graded="emit('graded')"
        @view-change="practiceView = $event"
      />
    </section>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { BookOpenCheck, X } from 'lucide-vue-next'
import PracticeWorkspace from './PracticeWorkspace.vue'
import MathText from './MathText.vue'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  courseId: string
  nodeId?: string
  nodeLabel?: string
  originRect?: { top: number; left: number; width: number; height: number } | null
  recordCount?: number
}>(), {
  recordCount: 0,
})
const emit = defineEmits<{
  (event: 'close' | 'graded'): void
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
}>()

const modalRoot = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
type PracticeView = 'current' | 'history' | 'needs_review'
const practiceView = ref<PracticeView>('current')
const practiceWorkspace = ref<InstanceType<typeof PracticeWorkspace> | null>(null)
const dialogTitleId = `question-book-title-${Math.random().toString(36).slice(2, 9)}`
const dialogDescriptionId = `question-book-description-${Math.random().toString(36).slice(2, 9)}`

function setPracticeView(view: PracticeView) {
  practiceView.value = view
  if (view === 'current') practiceWorkspace.value?.selectView('current')
  else void practiceWorkspace.value?.openHistory(view === 'history' ? 'all' : 'needs_review')
}

onMounted(async () => {
  await nextTick()
  closeButton.value?.focus()
})
</script>

<style scoped>
.question-book-modal {
  position: fixed;
  inset: 0;
  z-index: 130;
  display: grid;
  place-items: center;
  padding: 32px;
  outline: none;
}

.question-book-modal__backdrop {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: rgba(24, 29, 50, .42);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  cursor: default;
}

.question-book-dialog {
  position: relative;
  width: min(1040px, calc(100vw - 64px));
  height: min(680px, calc(100dvh - 96px));
  min-height: 480px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 28px 72px rgba(20, 25, 48, .24), 0 8px 24px rgba(20, 25, 48, .12);
  animation: question-book-enter .22s cubic-bezier(.16, 1, .3, 1);
}

.question-book-dialog__header {
  min-height: 64px;
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 20px;
  padding: 10px 14px 10px 18px;
  border-bottom: 1px solid var(--lz-border);
  background: #fff;
}

.question-book-dialog__identity,
.question-book-dialog__actions {
  min-width: 0;
  display: flex;
  align-items: center;
}

.question-book-dialog__identity { gap: 11px; }
.question-book-dialog__actions { justify-self: end; gap: 10px; }

.question-book-dialog__views {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 3px;
  border: 1px solid #e1e5ee;
  border-radius: 10px;
  background: #f5f6fa;
}

.question-book-dialog__views button {
  min-height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  color: #646c80;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}

.question-book-dialog__views button:hover { color: #292f43; }

.question-book-dialog__views button.active {
  color: var(--lz-brand-strong);
  background: #fff;
  box-shadow: 0 2px 8px rgba(35, 40, 67, .09);
  font-weight: 700;
}

.question-book-dialog__views button:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}

.question-book-dialog__mark {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #fff;
  background: var(--lz-brand-strong);
}

.question-book-dialog__identity > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.question-book-dialog__identity strong {
  color: var(--lz-text-strong);
  font-size: 15px;
  line-height: 1.3;
}

.question-book-dialog__identity div > span {
  overflow: hidden;
  color: var(--lz-text-secondary);
  font-size: 11px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-book-dialog__count {
  color: var(--lz-text-muted);
  font-size: 11px;
}

.question-book-dialog__close {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 8px;
  color: var(--lz-text-secondary);
  background: transparent;
  cursor: pointer;
}

.question-book-dialog__close:hover {
  color: var(--lz-text-strong);
  background: var(--lz-surface-muted);
}

.question-book-dialog__close:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}

.question-book-dialog__workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

@keyframes question-book-enter {
  from { opacity: .72; transform: translateY(14px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@media (max-width: 767px) {
  .question-book-modal {
    place-items: end center;
    padding: 8px 8px max(10px, env(safe-area-inset-bottom));
  }

  .question-book-modal__backdrop { backdrop-filter: none; -webkit-backdrop-filter: none; }

  .question-book-dialog {
    width: 100%;
    height: min(78dvh, 680px);
    min-height: 430px;
    border-radius: 16px;
    box-shadow: 0 20px 52px rgba(20, 25, 48, .28);
  }

  .question-book-dialog__header {
    min-height: 58px;
    padding: 9px 10px 9px 13px;
  }

  .question-book-dialog__mark { width: 34px; height: 34px; }
  .question-book-dialog__count { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .question-book-dialog { animation: none; }
}
</style>
