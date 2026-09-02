<template>
  <section
    class="arrangement-summary"
    :class="{
      'has-sticky-actions': stickyActions,
      'is-supporting': supporting,
      'is-generating': generating,
    }"
    data-testid="lesson-arrangement-summary"
    :data-state="arrangement.confirmed ? 'confirmed' : 'suggested'"
  >
    <header class="arrangement-toolbar">
      <div class="arrangement-controls">
        <label class="arrangement-type">
          <span>{{ t('courseWorkbench.arrangement.recommendedType', '本讲课型') }}：</span>
          <select
            :value="selectedLessonType || arrangement.lesson_type"
            :disabled="busy || generating"
            :title="arrangement.lesson_type_recommendation_reason || ''"
            @change="updateLessonType"
          >
            <option v-for="option in lessonTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <span v-if="needsConfirmation" class="arrangement-state" role="status">
          <Sparkles :size="17" />
          {{ t('courseWorkbench.arrangement.awaitingConfirmation', '生成前需确认') }}
        </span>
        <button
          v-if="needsConfirmation"
          class="arrangement-confirm"
          type="button"
          :disabled="busy || generating"
          @click="emit('confirm')"
        >
          <LoaderCircle v-if="busy" :size="15" class="spin" />
          <Check v-else :size="15" />
          {{ busy
            ? t('courseWorkbench.arrangement.confirming', '正在确认…')
            : t('courseWorkbench.arrangement.confirmShort', '确认教学结构') }}
        </button>
      </div>
      <div v-if="$slots['generation-actions']" class="arrangement-generation-actions">
        <slot name="generation-actions" />
      </div>
    </header>

    <p v-if="error" class="arrangement-error" role="alert"><TriangleAlert :size="14" />{{ error }}</p>

    <section v-if="!generating && !supporting" class="arrangement-document">
      <div class="arrangement-blocks">
        <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
          <header>
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div><strong>{{ block.name }}</strong><span v-if="block.section_title && block.section_title !== block.name">{{ block.section_title }}</span></div>
            <b>{{ block.planned_minutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }}</b>
          </header>
          <dl>
            <div><dt>{{ t('courseWorkbench.arrangement.blockGoal', '环节目标') }}</dt><dd>{{ block.purpose }}</dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.classroomActivity', '课堂活动') }}</dt><dd>{{ blockActivity(block) }}</dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.attainmentJudgement', '达成判断') }}</dt><dd>{{ blockAttainment(block) }}</dd></div>
          </dl>
        </article>
      </div>
    </section>

    <footer v-if="!generating && impactLabels.length">
      <TriangleAlert :size="14" />
      <div>
        <strong>{{ t('courseWorkbench.arrangement.changeImpact', '调整后的影响') }}</strong>
        <span>{{ impactLabels.join('；') }}。{{ t('courseWorkbench.arrangement.lastUsable', '最后可用版本会保留，不会被静默覆盖。') }}</span>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, LoaderCircle, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { TeacherLessonArrangement } from '../stores/teacherLessonAuthoring'

const props = withDefaults(defineProps<{
  arrangement: TeacherLessonArrangement
  impactLabels?: string[]
  selectedLessonType?: string
  busy?: boolean
  generating?: boolean
  stickyActions?: boolean
  supporting?: boolean
  error?: string
}>(), {
  impactLabels: () => [],
  selectedLessonType: '',
  busy: false,
  generating: false,
  stickyActions: false,
  supporting: false,
  error: '',
})

const emit = defineEmits<{
  (event: 'update:selectedLessonType', value: string): void
  (event: 'confirm'): void
}>()

const needsConfirmation = computed(() => !props.arrangement.confirmed || Boolean(props.selectedLessonType && props.selectedLessonType !== props.arrangement.lesson_type))
const lessonTypeOptions = computed(() => [
  { value: 'theory', label: t('courseWorkbench.arrangement.lessonTypes.theory', '理论讲授') },
  { value: 'practice', label: t('courseWorkbench.arrangement.lessonTypes.practice', '技能训练') },
  { value: 'theory_practice', label: t('courseWorkbench.arrangement.lessonTypes.theoryPractice', '讲练结合') },
  { value: 'case_discussion', label: t('courseWorkbench.arrangement.lessonTypes.caseDiscussion', '案例研讨') },
  { value: 'experiment_inquiry', label: t('courseWorkbench.arrangement.lessonTypes.experimentInquiry', '实验探究') },
  { value: 'project_workshop', label: t('courseWorkbench.arrangement.lessonTypes.projectWorkshop', '项目工作坊') },
  { value: 'review_assessment', label: t('courseWorkbench.arrangement.lessonTypes.reviewAssessment', '复习测评') },
])
function uniqueText(values: unknown[]): string {
  return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))].join('；')
}

function blockActivity(block: TeacherLessonArrangement['blocks'][number]): string {
  return uniqueText([block.content_summary, block.teacher_activity, block.student_activity]) || '-'
}

function blockAttainment(block: TeacherLessonArrangement['blocks'][number]): string {
  return uniqueText([block.expected_output, block.check_method]) || '-'
}

function updateLessonType(event: Event) {
  emit('update:selectedLessonType', (event.target as HTMLSelectElement).value)
}
</script>

<style scoped>
.arrangement-summary {
  position: relative;
  container-type: inline-size;
  background: #fff;
}

.arrangement-toolbar {
  position: relative;
  z-index: 2;
  min-height: 68px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 20px;
  padding: 11px 24px;
  border-bottom: 1px solid #dfe5ee;
  background: #fff;
}

.arrangement-summary.has-sticky-actions .arrangement-toolbar {
  position: sticky;
  z-index: 8;
  top: 0;
}

.arrangement-summary.has-sticky-actions:is(.is-supporting, .is-generating) {
  position: sticky;
  z-index: 8;
  top: 0;
}

.arrangement-summary.has-sticky-actions:is(.is-supporting, .is-generating) .arrangement-toolbar {
  position: relative;
}

.arrangement-controls {
  min-width: 0;
  display: flex;
  flex: 1 1 320px;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.arrangement-type {
  min-height: 42px;
  display: inline-flex;
  flex: none;
  align-items: center;
  overflow: hidden;
  border: 1px solid #cfd7e3;
  border-radius: 8px;
  background: #fff;
  transition: border-color .14s ease, box-shadow .14s ease;
}

.arrangement-type:hover {
  border-color: #aeb8c8;
}

.arrangement-type:focus-within {
  border-color: #5b57e8;
  box-shadow: 0 0 0 3px rgba(91, 87, 232, .14);
}

.arrangement-type > span {
  flex: none;
  padding-left: 13px;
  color: #647187;
  font-size: 15px;
  font-weight: 700;
  white-space: nowrap;
}

.arrangement-type select {
  min-width: 138px;
  min-height: 40px;
  padding: 0 34px 0 2px;
  border: 0;
  border-radius: 7px;
  color: #243044;
  background: transparent;
  font: inherit;
  font-size: 15px;
  font-weight: 720;
  cursor: pointer;
}

.arrangement-type select:focus {
  outline: 0;
}

.arrangement-type select:disabled {
  color: #7d899a;
  cursor: not-allowed;
}

.arrangement-state {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #8a671f;
  font-size: 15px;
  font-weight: 680;
  white-space: nowrap;
}

.arrangement-confirm {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border: 1px solid #d4b467;
  border-radius: 8px;
  color: #755312;
  background: #fffaf0;
  font-size: 15px;
  font-weight: 720;
  cursor: pointer;
}

.arrangement-confirm:hover:not(:disabled) {
  border-color: #bc9850;
  background: #fff7e4;
}

.arrangement-confirm:focus-visible {
  outline: 3px solid rgba(179, 131, 39, .16);
  outline-offset: 2px;
}

.arrangement-confirm:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.arrangement-generation-actions {
  min-width: 0;
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  justify-content: flex-end;
}

.arrangement-error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 12px 24px;
  color: #a33a31;
  background: #fff3f2;
  font-size: 15px;
}

.arrangement-document {
  padding: 4px 30px 14px;
}

.arrangement-blocks {
  display: grid;
}

.arrangement-blocks article {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) auto;
  gap: 18px;
  padding: 28px 0 30px;
  border-bottom: 1px solid #e7ebf1;
}

.arrangement-blocks article:last-child {
  border-bottom: 0;
}

.arrangement-blocks article > header {
  display: contents;
}

.arrangement-blocks article > header > span {
  padding-top: 3px;
  color: #727f92;
  font-size: 16px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
  letter-spacing: .08em;
}

.arrangement-blocks article > header > div {
  min-width: 0;
  display: grid;
  grid-column: 2;
  gap: 4px;
}

.arrangement-blocks article > header strong {
  color: #1d293d;
  font-size: 20px;
  font-weight: 730;
  line-height: 1.45;
}

.arrangement-blocks article > header > div > span {
  color: #647187;
  font-size: 16px;
  line-height: 1.6;
}

.arrangement-blocks article > header b {
  grid-column: 3;
  grid-row: 1;
  align-self: start;
  padding-top: 4px;
  color: #68758a;
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
}

.arrangement-blocks dl {
  min-width: 0;
  display: grid;
  grid-column: 2 / -1;
  gap: 9px;
  margin: 13px 0 0;
}

.arrangement-blocks dl > div {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 16px;
}

.arrangement-blocks dt {
  color: #748195;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.72;
}

.arrangement-blocks dd {
  max-width: 75ch;
  margin: 0;
  color: #475569;
  font-size: 16px;
  line-height: 1.72;
}

.arrangement-summary > footer {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0 30px;
  padding: 14px 0 8px;
  border-top: 1px solid #eadfb8;
  color: #776513;
}

.arrangement-summary > footer > div {
  display: grid;
  gap: 4px;
}

.arrangement-summary > footer strong,
.arrangement-summary > footer span {
  font-size: 15px;
  line-height: 1.6;
}

.arrangement-summary > footer span {
  color: #6d685a;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@container (max-width: 760px) {
  .arrangement-toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    padding: 12px 20px 14px;
  }

  .arrangement-controls,
  .arrangement-type,
  .arrangement-generation-actions {
    width: 100%;
  }

  .arrangement-controls {
    flex: 0 1 auto;
  }

  .arrangement-type {
    flex: 1 1 auto;
  }

  .arrangement-type select {
    width: 100%;
  }

  .arrangement-generation-actions {
    justify-content: flex-start;
  }

  .arrangement-generation-actions :deep(.lesson-generation-actions) {
    width: 100%;
    display: grid;
    grid-template-columns: minmax(0, .82fr) minmax(0, 1.18fr);
  }

  .arrangement-generation-actions :deep(.lesson-generation-actions button) {
    width: 100%;
    min-width: 0;
    padding-inline: 12px;
    white-space: nowrap;
  }

  .arrangement-document {
    padding-inline: 20px;
  }

  .arrangement-blocks article {
    grid-template-columns: 38px minmax(0, 1fr) auto;
    gap: 10px;
  }

  .arrangement-blocks dl > div {
    grid-template-columns: 84px minmax(0, 1fr);
    gap: 12px;
  }
}

@container (max-width: 440px) {
  .arrangement-generation-actions :deep(.lesson-generation-actions) {
    grid-template-columns: minmax(0, 1fr);
  }

  .arrangement-blocks article {
    grid-template-columns: minmax(0, 1fr);
  }

  .arrangement-blocks article > header > div,
  .arrangement-blocks article > header b,
  .arrangement-blocks dl {
    grid-column: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .arrangement-type {
    transition: none;
  }
}
</style>
