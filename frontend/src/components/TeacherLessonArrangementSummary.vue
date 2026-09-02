<template>
  <section
    class="arrangement-summary"
    :class="{ 'has-sticky-actions': stickyActions }"
    data-testid="lesson-arrangement-summary"
    :data-state="arrangement.confirmed ? 'confirmed' : 'suggested'"
  >
    <header class="arrangement-toolbar">
      <div class="arrangement-context">
        <label class="arrangement-type">
          <span>{{ t('courseWorkbench.arrangement.recommendedType', '本讲课型') }}</span>
          <select
            :value="selectedLessonType || arrangement.lesson_type"
            :disabled="busy || generating"
            :title="arrangement.lesson_type_recommendation_reason || ''"
            @change="updateLessonType"
          >
            <option v-for="option in lessonTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <span class="arrangement-state" role="status">
          <Check v-if="arrangement.confirmed && !needsConfirmation" :size="17" />
          <Sparkles v-else :size="17" />
          {{ arrangement.confirmed && !needsConfirmation
            ? t('courseWorkbench.arrangement.confirmedShort', '已确认')
            : t('courseWorkbench.arrangement.awaitingConfirmation', '生成前需确认') }}
        </span>
      </div>
      <div class="arrangement-actions">
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
        <div v-if="$slots['generation-actions']" class="arrangement-generation-actions">
          <slot name="generation-actions" />
        </div>
      </div>
    </header>

    <p v-if="error" class="arrangement-error" role="alert"><TriangleAlert :size="14" />{{ error }}</p>

    <section v-if="!generating" class="arrangement-document">
      <div class="arrangement-blocks">
        <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
          <header>
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div><strong>{{ block.name }}</strong><span>{{ block.section_title }}</span></div>
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
  error?: string
}>(), {
  impactLabels: () => [],
  selectedLessonType: '',
  busy: false,
  generating: false,
  stickyActions: false,
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
.arrangement-summary{position:relative;background:#fff}.arrangement-toolbar{position:relative;z-index:2;min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 16px;border-bottom:1px solid #dfe5ee;background:#fff}.arrangement-summary.has-sticky-actions .arrangement-toolbar{position:sticky;z-index:8;top:0}.arrangement-context,.arrangement-actions{min-width:0;display:flex;align-items:center;gap:11px;white-space:nowrap}.arrangement-actions{flex:none;justify-content:flex-end}.arrangement-type{flex:none;display:flex;align-items:center;gap:8px}.arrangement-type>span{color:#68758a;font-size:15px;font-weight:700;white-space:nowrap}.arrangement-type select{min-width:122px;min-height:36px;padding:0 30px 0 10px;border:1px solid #cfd7e3;border-radius:8px;color:#243044;background:#fff;font:inherit;font-size:15px;font-weight:700;cursor:pointer}.arrangement-type select:hover:not(:disabled){border-color:#aeb8c8}.arrangement-type select:focus{border-color:#5b57e8;outline:3px solid rgba(91,87,232,.12)}.arrangement-type select:disabled{opacity:.52;cursor:not-allowed}.arrangement-state{flex:none;display:flex;align-items:center;gap:6px;color:#8a671f;font-size:15px;font-weight:680;white-space:nowrap}.arrangement-summary[data-state="confirmed"] .arrangement-state{color:#207148}.arrangement-confirm{min-height:36px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 11px;border:1px solid #d4b467;border-radius:8px;color:#755312;background:#fffaf0;font-size:15px;font-weight:720;cursor:pointer}.arrangement-confirm:hover:not(:disabled){border-color:#bc9850;background:#fff7e4}.arrangement-confirm:focus-visible{outline:3px solid rgba(179,131,39,.16);outline-offset:2px}.arrangement-confirm:disabled{opacity:.5;cursor:not-allowed}.arrangement-generation-actions{flex:none;display:flex;align-items:center;justify-content:flex-end}.arrangement-error{display:flex;align-items:center;gap:7px;margin:0;padding:12px 20px;color:#a33a31;background:#fff3f2;font-size:15px}.arrangement-document{padding:0 24px 12px}.arrangement-blocks{display:grid}.arrangement-blocks article{padding:22px 2px 24px;border-bottom:1px solid #e7ebf1}.arrangement-blocks article:last-child{border-bottom:0}.arrangement-blocks article>header{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:start;gap:12px}.arrangement-blocks article>header>span{width:30px;height:30px;display:grid;place-items:center;border:1px solid #d8deea;border-radius:50%;color:#5e5ab9;font-size:15px;font-weight:800}.arrangement-blocks article>header>div{min-width:0;display:grid;gap:4px}.arrangement-blocks article>header strong{color:#243044;font-size:17px;line-height:1.45}.arrangement-blocks article>header>div>span{overflow:hidden;color:#667386;font-size:15px;line-height:1.55;text-overflow:ellipsis;white-space:nowrap}.arrangement-blocks article>header b{padding-top:4px;color:#59667a;font-size:15px;white-space:nowrap}.arrangement-blocks dl{display:grid;gap:11px;margin:16px 0 0 46px}.arrangement-blocks dl>div{display:grid;grid-template-columns:76px minmax(0,1fr);gap:14px}.arrangement-blocks dt{color:#68758a;font-size:15px;font-weight:720}.arrangement-blocks dd{margin:0;color:#3f4d62;font-size:16px;line-height:1.75}.arrangement-summary>footer{display:flex;align-items:flex-start;gap:10px;margin:0 24px;padding:14px 2px 4px;border-top:1px solid #eadfb8;color:#776513}.arrangement-summary>footer>div{display:grid;gap:4px}.arrangement-summary>footer strong,.arrangement-summary>footer span{font-size:15px;line-height:1.6}.arrangement-summary>footer span{color:#6d685a}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:900px){.arrangement-toolbar{gap:10px;padding-inline:12px}.arrangement-context,.arrangement-actions{gap:8px}.arrangement-type>span{display:none}.arrangement-type select{min-width:112px}.arrangement-document{padding-inline:18px}.arrangement-blocks article>header{grid-template-columns:34px minmax(0,1fr)}.arrangement-blocks article>header b{grid-column:2}.arrangement-blocks dl{margin-left:46px}}
</style>
