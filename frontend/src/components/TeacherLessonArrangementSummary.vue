<template>
  <section class="arrangement-summary" :data-state="arrangement.confirmed ? 'confirmed' : 'suggested'">
    <header>
      <div class="arrangement-heading">
        <small>{{ t('courseWorkbench.arrangement.preparation', '本讲准备') }}</small>
        <strong>{{ arrangement.lesson_type_label }}</strong>
        <span>{{ totalMinutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }} · {{ sectionCount }} {{ t('courseWorkbench.arrangement.themes', '个内容主题') }} · {{ arrangement.blocks.length }} {{ t('courseWorkbench.arrangement.blocks', '个教学块') }}</span>
      </div>
      <span class="arrangement-state">
        <Check v-if="arrangement.confirmed" :size="13" />
        <Sparkles v-else :size="13" />
        {{ arrangement.confirmed
          ? t('courseWorkbench.arrangement.confirmed', '课型与教学结构已确认')
          : t('courseWorkbench.arrangement.awaitingConfirmation', '生成前需确认') }}
      </span>
    </header>

    <div class="arrangement-decision">
      <label>
        <span>{{ t('courseWorkbench.arrangement.recommendedType', '本讲课型') }}</span>
        <select :value="selectedLessonType || arrangement.lesson_type" :disabled="busy || generating" @change="updateLessonType">
          <option v-for="option in lessonTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <p v-if="arrangement.lesson_type_recommendation_reason">
        <b>{{ t('courseWorkbench.arrangement.recommendationReason', '推荐理由') }}</b>
        {{ arrangement.lesson_type_recommendation_reason }}
      </p>
      <div class="arrangement-actions">
        <button
          v-if="needsConfirmation"
          class="primary"
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
        <button
          v-else-if="canGenerate"
          class="primary"
          type="button"
          :disabled="busy || generating"
          @click="emit('generate')"
        >
          <LoaderCircle v-if="generating" :size="15" class="spin" />
          <Sparkles v-else :size="15" />
          {{ generating
            ? t('courseWorkbench.arrangement.generatingLesson', '正在生成本讲…')
            : t('courseWorkbench.arrangement.generateLesson', '只生成本讲') }}
        </button>
        <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">
          {{ expanded
            ? t('courseWorkbench.arrangement.collapse', '收起教学块')
            : t('courseWorkbench.arrangement.expand', '查看教学块') }}
          <ChevronDown :size="14" :class="{ rotated: expanded }" />
        </button>
      </div>
    </div>

    <p v-if="error" class="arrangement-error" role="alert"><TriangleAlert :size="14" />{{ error }}</p>

    <div v-if="expanded" class="arrangement-blocks">
      <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
        <header>
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <div><strong>{{ block.name }}</strong><small>{{ block.section_title }}</small></div>
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

    <footer v-if="impactLabels.length">
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
  canGenerate?: boolean
  error?: string
}>(), {
  impactLabels: () => [],
  selectedLessonType: '',
  busy: false,
  generating: false,
  canGenerate: false,
  error: '',
})

const emit = defineEmits<{
  (event: 'update:selectedLessonType', value: string): void
  (event: 'confirm'): void
  (event: 'generate'): void
}>()

const expanded = ref(false)
const totalMinutes = computed(() => props.arrangement.blocks.reduce((total, block) => total + Number(block.planned_minutes || 0), 0))
const sectionCount = computed(() => new Set(props.arrangement.blocks.map(block => block.section_node_id).filter(Boolean)).size)
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
.arrangement-summary{border-bottom:1px solid #e5eaf1;background:#fff}.arrangement-summary>header{min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 24px}.arrangement-heading{min-width:0;display:flex;align-items:baseline;gap:10px}.arrangement-heading small{color:#657286;font-size:10px;font-weight:800}.arrangement-heading strong{color:#29354a;font-size:14px}.arrangement-heading span{color:#7b8797;font-size:11px}.arrangement-state{flex:none;display:flex;align-items:center;gap:5px;color:#5f6b7d;font-size:10.5px}.arrangement-summary[data-state="confirmed"] .arrangement-state{color:#207148}.arrangement-decision{display:grid;grid-template-columns:minmax(150px,190px) minmax(260px,1fr) auto;align-items:end;gap:18px;padding:12px 24px 16px;border-top:1px solid #f0f2f6;background:#fbfcfe}.arrangement-decision label{display:grid;gap:6px}.arrangement-decision label>span{color:#657286;font-size:10px;font-weight:750}.arrangement-decision select{min-height:36px;padding:0 10px;border:1px solid #cfd7e3;border-radius:8px;color:#29354a;background:#fff;font:inherit;font-size:12px}.arrangement-decision select:focus{border-color:#5b57e8;outline:3px solid rgba(91,87,232,.12)}.arrangement-decision p{margin:0;color:#657286;font-size:11px;line-height:1.55}.arrangement-decision p b{display:block;margin-bottom:3px;color:#475467;font-size:10px}.arrangement-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px}.arrangement-actions button{min-height:36px;display:flex;align-items:center;justify-content:center;gap:6px;padding:0 11px;border:1px solid #d8dee8;border-radius:8px;color:#4f5d72;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.arrangement-actions button:hover:not(:disabled){border-color:#bfc4e8;color:#3730a3;background:#f8f8ff}.arrangement-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.arrangement-actions button:disabled{opacity:.48;cursor:not-allowed}.arrangement-actions .primary{border-color:#514bdc;color:#fff;background:#514bdc}.arrangement-actions .primary:hover:not(:disabled){border-color:#4338ca;color:#fff;background:#4338ca}.arrangement-actions svg{transition:transform .16s ease}.arrangement-actions svg.rotated{transform:rotate(180deg)}.arrangement-error{display:flex;align-items:center;gap:7px;margin:0;padding:10px 24px;color:#a33a31;background:#fff3f2;font-size:11px}.arrangement-blocks{display:grid;gap:10px;padding:14px 24px 20px;background:#f7f9fc}.arrangement-blocks article{padding:14px 16px;border:1px solid #e0e5ed;border-radius:12px;background:#fff}.arrangement-blocks article>header{display:grid;grid-template-columns:24px minmax(0,1fr) auto;align-items:center;gap:9px}.arrangement-blocks article>header>span{color:#7773d1;font-size:10px;font-weight:800}.arrangement-blocks article>header>div{min-width:0;display:grid;gap:2px}.arrangement-blocks article>header strong{color:#29354a;font-size:12.5px}.arrangement-blocks article>header small{overflow:hidden;color:#8a96a7;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.arrangement-blocks article>header b{color:#667085;font-size:10px}.arrangement-blocks article>p{margin:10px 0 0 33px;color:#667386;font-size:11.5px;line-height:1.55}.arrangement-blocks dl{display:grid;gap:7px;margin:12px 0 0 33px}.arrangement-blocks dl>div{display:grid;grid-template-columns:68px minmax(0,1fr);gap:10px}.arrangement-blocks dt{color:#8a96a7;font-size:10px;font-weight:750}.arrangement-blocks dd{margin:0;color:#4d5a6d;font-size:11.5px;line-height:1.55}.arrangement-blocks details{margin:13px 0 0 33px;padding-top:10px;border-top:1px solid #edf0f4}.arrangement-blocks summary{width:max-content;color:#5551ad;font-size:10.5px;font-weight:750;cursor:pointer}.arrangement-blocks details dl{margin:10px 0 0}.adaptation-row dd{display:grid;gap:3px}.arrangement-summary>footer{display:flex;align-items:flex-start;gap:9px;padding:11px 24px;border-top:1px solid #eceff4;color:#776513;background:#fffdf5}.arrangement-summary>footer>div{display:grid;gap:2px}.arrangement-summary>footer strong{font-size:11px}.arrangement-summary>footer span{color:#736f61;font-size:10.5px;line-height:1.5}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){.arrangement-decision{grid-template-columns:170px minmax(0,1fr)}.arrangement-actions{grid-column:1/-1}}@media(prefers-reduced-motion:reduce){.arrangement-actions svg{transition:none}}
</style>
