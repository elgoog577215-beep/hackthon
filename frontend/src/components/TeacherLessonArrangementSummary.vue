<template>
  <section
    class="arrangement-summary"
    :class="{ 'has-sticky-actions': stickyActions }"
    data-testid="lesson-arrangement-summary"
    :data-state="arrangement.confirmed ? 'confirmed' : 'suggested'"
  >
    <header class="arrangement-toolbar">
      <div class="arrangement-settings">
        <label class="arrangement-type">
          <span class="sr-only">{{ t('courseWorkbench.arrangement.recommendedType', '本讲课型') }}</span>
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
            ? t('courseWorkbench.arrangement.confirmed', '课型与教学结构已确认')
            : t('courseWorkbench.arrangement.awaitingConfirmation', '生成前需确认') }}
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
            : t('courseWorkbench.arrangement.confirm', '确认课型与教学结构') }}
        </button>
      </div>
      <div v-if="$slots['generation-actions']" class="arrangement-generation-actions">
        <slot name="generation-actions" />
      </div>
    </header>

    <p v-if="error" class="arrangement-error" role="alert"><TriangleAlert :size="14" />{{ error }}</p>

    <section v-if="!generating" class="arrangement-document">
      <header class="arrangement-document-heading">
        <h3>{{ t('courseWorkbench.arrangement.structure', '教学结构') }}</h3>
        <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">
          {{ expanded
            ? t('courseWorkbench.arrangement.collapse', '收起教学块')
            : t('courseWorkbench.arrangement.expand', '展开教学块') }}
          <ChevronDown :size="16" :class="{ rotated: expanded }" />
        </button>
      </header>

      <div v-if="expanded" class="arrangement-blocks">
        <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
          <header>
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div><strong>{{ block.name }}</strong><span>{{ block.section_title }}</span></div>
            <b>{{ block.planned_minutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }}</b>
          </header>
          <p>{{ block.content_summary || block.purpose }}</p>
          <dl>
            <div><dt>{{ t('courseWorkbench.arrangement.teacherAction', '教师动作') }}</dt><dd>{{ block.teacher_activity }}</dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.studentAction', '学生行动') }}</dt><dd>{{ block.student_activity }}</dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.evidence', '课堂产出') }}</dt><dd>{{ block.expected_output }}</dd></div>
            <div v-if="block.check_method"><dt>{{ t('courseWorkbench.arrangement.check', '达成检查') }}</dt><dd>{{ block.check_method }}</dd></div>
            <div v-if="block.resource_refs?.length || block.tools?.length">
              <dt>{{ t('courseWorkbench.arrangement.resourcesTools', '资料与工具') }}</dt>
              <dd>{{ [...(block.resource_refs || []), ...(block.tools || [])].join('；') }}</dd>
            </div>
          </dl>
          <details>
            <summary>{{ t('courseWorkbench.arrangement.implementationPlan', '实施预案') }}</summary>
            <dl>
              <div v-if="block.feedback_strategy"><dt>{{ t('courseWorkbench.arrangement.feedback', '反馈调整') }}</dt><dd>{{ block.feedback_strategy }}</dd></div>
              <div v-if="block.adaptation_options?.length" class="adaptation-row">
                <dt>{{ t('courseWorkbench.arrangement.adaptation', '三档处理') }}</dt>
                <dd><span v-for="item in block.adaptation_options" :key="item">{{ item }}</span></dd>
              </div>
              <div v-if="block.access_support"><dt>{{ t('courseWorkbench.arrangement.accessSupport', '进入支持') }}</dt><dd>{{ block.access_support }}</dd></div>
              <div v-if="block.grouping"><dt>{{ t('courseWorkbench.arrangement.grouping', '分组方式') }}</dt><dd>{{ block.grouping }}</dd></div>
              <div v-if="block.transition"><dt>{{ t('courseWorkbench.arrangement.transition', '前后衔接') }}</dt><dd>{{ block.transition }}</dd></div>
              <div v-if="block.safety_boundary"><dt>{{ t('courseWorkbench.arrangement.safety', '专业边界') }}</dt><dd>{{ block.safety_boundary }}</dd></div>
            </dl>
          </details>
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
import { computed, ref } from 'vue'
import { Check, ChevronDown, LoaderCircle, Sparkles, TriangleAlert } from 'lucide-vue-next'
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

const expanded = ref(true)
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

function updateLessonType(event: Event) {
  emit('update:selectedLessonType', (event.target as HTMLSelectElement).value)
}
</script>

<style scoped>
.arrangement-summary{position:relative;background:#fff}.arrangement-toolbar{position:relative;z-index:2;min-height:78px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:16px 24px;border-bottom:1px solid #dfe5ee;background:rgba(255,255,255,.97);box-shadow:0 7px 18px rgba(32,43,68,.04);backdrop-filter:blur(12px)}.arrangement-summary.has-sticky-actions .arrangement-toolbar{position:sticky;z-index:8;top:0}.arrangement-settings{min-width:0;display:flex;align-items:center;gap:16px}.arrangement-type{flex:none}.arrangement-type select{min-width:144px;min-height:44px;padding:0 34px 0 13px;border:1px solid #cfd7e3;border-radius:8px;color:#243044;background:#fff;font:inherit;font-size:15px;font-weight:700;cursor:pointer}.arrangement-type select:hover:not(:disabled){border-color:#aeb8c8}.arrangement-type select:focus{border-color:#5b57e8;outline:3px solid rgba(91,87,232,.12)}.arrangement-type select:disabled{opacity:.52;cursor:not-allowed}.arrangement-state{flex:none;display:flex;align-items:center;gap:7px;padding-left:16px;border-left:1px solid #dfe5ee;color:#8a671f;font-size:15px;font-weight:680;white-space:nowrap}.arrangement-summary[data-state="confirmed"] .arrangement-state{color:#207148}.arrangement-confirm{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border:1px solid #d4b467;border-radius:8px;color:#755312;background:#fffaf0;font-size:15px;font-weight:720;cursor:pointer}.arrangement-confirm:hover:not(:disabled){border-color:#bc9850;background:#fff7e4}.arrangement-confirm:focus-visible{outline:3px solid rgba(179,131,39,.16);outline-offset:2px}.arrangement-confirm:disabled{opacity:.5;cursor:not-allowed}.arrangement-generation-actions{flex:none;display:flex;align-items:center;justify-content:flex-end}.arrangement-error{display:flex;align-items:center;gap:7px;margin:0;padding:12px 24px;color:#a33a31;background:#fff3f2;font-size:15px}.arrangement-document{padding:0 28px 18px}.arrangement-document-heading{min-height:74px;display:flex;align-items:center;justify-content:space-between;gap:18px;border-bottom:1px solid #e7ebf1}.arrangement-document-heading h3{margin:0;color:#202b40;font-size:20px;letter-spacing:-.015em}.arrangement-document-heading button{min-height:40px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 5px;border:0;color:#59667a;background:transparent;font-size:15px;font-weight:700;cursor:pointer}.arrangement-document-heading button:hover{color:#3730a3}.arrangement-document-heading button:focus-visible{outline:2px solid #5b57e8;outline-offset:3px}.arrangement-document-heading svg{transition:transform .16s ease}.arrangement-document-heading svg.rotated{transform:rotate(180deg)}.arrangement-blocks{display:grid}.arrangement-blocks article{padding:24px 2px 26px;border-bottom:1px solid #e7ebf1}.arrangement-blocks article:last-child{border-bottom:0}.arrangement-blocks article>header{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:start;gap:12px}.arrangement-blocks article>header>span{width:30px;height:30px;display:grid;place-items:center;border:1px solid #d8deea;border-radius:50%;color:#5e5ab9;font-size:15px;font-weight:800}.arrangement-blocks article>header>div{min-width:0;display:grid;gap:4px}.arrangement-blocks article>header strong{color:#243044;font-size:17px;line-height:1.4}.arrangement-blocks article>header>div>span{overflow:hidden;color:#667386;font-size:15px;line-height:1.5;text-overflow:ellipsis;white-space:nowrap}.arrangement-blocks article>header b{padding-top:4px;color:#59667a;font-size:15px;white-space:nowrap}.arrangement-blocks article>p{margin:14px 0 0 46px;color:#46556b;font-size:15px;line-height:1.75}.arrangement-blocks dl{display:grid;gap:11px;margin:17px 0 0 46px}.arrangement-blocks dl>div{display:grid;grid-template-columns:84px minmax(0,1fr);gap:14px}.arrangement-blocks dt{color:#68758a;font-size:15px;font-weight:720}.arrangement-blocks dd{margin:0;color:#3f4d62;font-size:15px;line-height:1.7}.arrangement-blocks details{margin:18px 0 0 46px;padding-top:15px;border-top:1px solid #edf0f4}.arrangement-blocks summary{width:max-content;color:#4e4aa8;font-size:15px;font-weight:720;cursor:pointer}.arrangement-blocks details dl{margin:13px 0 0}.adaptation-row dd{display:grid;gap:5px}.arrangement-summary>footer{display:flex;align-items:flex-start;gap:10px;margin:0 28px;padding:15px 2px 0;border-top:1px solid #eadfb8;color:#776513}.arrangement-summary>footer>div{display:grid;gap:4px}.arrangement-summary>footer strong,.arrangement-summary>footer span{font-size:15px;line-height:1.6}.arrangement-summary>footer span{color:#6d685a}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:900px){.arrangement-toolbar{align-items:stretch;flex-direction:column;gap:12px}.arrangement-settings{flex-wrap:wrap}.arrangement-generation-actions{justify-content:flex-start}.arrangement-document{padding-inline:18px}.arrangement-blocks article>header{grid-template-columns:34px minmax(0,1fr)}.arrangement-blocks article>header b{grid-column:2}.arrangement-blocks article>p,.arrangement-blocks dl,.arrangement-blocks details{margin-left:46px}}@media(prefers-reduced-motion:reduce){.arrangement-document-heading svg{transition:none}}
</style>
