<template>
  <section ref="documentRoot" class="lesson-document" :class="{ 'is-ai-candidate': pendingCandidate }">
    <header v-if="!externalToolbar" class="document-header">
      <div class="document-title">
        <h3>{{ lesson.title }}</h3>
      </div>
      <div v-if="!pendingCandidate || !assistantOpen" class="document-actions">
        <template v-if="pendingCandidate">
          <button type="button" :disabled="aiBusy" @click="emit('open-ai')">
            <Sparkles :size="15" />{{ tr('courseWorkbench.lessonDocument.aiCandidate') }}
          </button>
          <button type="button" :disabled="aiBusy" @click="resolveAiCandidate(false)">
            <X :size="15" />{{ tr('courseWorkbench.lessonDocument.discardAi') }}
          </button>
          <button class="primary-action" type="button" :disabled="aiBusy" @click="resolveAiCandidate(true)">
            <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ aiBusy ? tr('courseWorkbench.lessonDocument.applyingAi') : tr('courseWorkbench.lessonDocument.applyAi') }}
          </button>
        </template>
        <template v-else-if="editing">
          <button type="button" :disabled="saving" @click="cancelEditing">
            <X :size="15" />{{ tr('courseWorkbench.lessonDocument.cancel') }}
          </button>
          <button class="primary-action" type="button" :disabled="saving" @click="saveDraft">
            <LoaderCircle v-if="saving" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ saving ? tr('courseWorkbench.lessonDocument.saving') : tr('courseWorkbench.lessonDocument.finishEditing') }}
          </button>
        </template>
        <template v-else>
          <button type="button" :disabled="aiBusy" @click="emit('open-ai')">
            <Sparkles :size="15" />{{ tr('courseWorkbench.lessonDocument.aiImprove') }}
          </button>
          <button type="button" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.lessonDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <div v-if="pendingCandidate" class="candidate-canvas-notice" role="status">
      <Sparkles :size="16" />
      <span>
        <strong>{{ tr('courseWorkbench.lessonDocument.candidateCanvasTitle') }}</strong>
      </span>
    </div>

    <AppErrorNotice v-if="documentError" :presentation="documentError" compact />

    <TextSelectionAiAction
      :container="documentRoot"
      :disabled="editing || aiBusy || Boolean(pendingCandidate)"
      :label="tr('courseWorkbench.aiCollaboration.selectionModify')"
      @invoke="emit('open-ai-selection', $event)"
    />

    <article v-if="selectedSection" class="document-body">
      <header v-if="!externalToolbar" class="section-title">
        <h4>{{ sectionTitle(selectedSection) }}</h4>
      </header>
      <section class="document-section lesson-identity">
        <div>
          <span>{{ tr('courseWorkbench.lessonDocument.courseName') }}</span>
          <strong>{{ courseTitle || emptyValue }}</strong>
        </div>
        <div>
          <span>{{ tr('courseWorkbench.lessonDocument.lessonName') }}</span>
          <strong>{{ lesson.title }}</strong>
        </div>
      </section>
      <section :class="['document-section', 'objective-section', { 'ai-change-target': objectiveCandidateChanged }]">
        <i v-if="objectiveCandidateChanged" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i>
        <h4>{{ tr('courseWorkbench.lessonDocument.objectives') }}</h4>
        <div class="objective-grid">
          <div>
            <h5>{{ tr('courseWorkbench.lessonDocument.knowledgeObjective') }}</h5>
            <textarea v-if="editing" :value="listText(selectedSection.knowledge_objectives)" rows="3" @input="updateList(selectedSection, 'knowledge_objectives', $event)" />
            <ul v-else-if="knowledgeObjectives.length"><li v-for="item in knowledgeObjectives" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p>
          </div>
          <div>
            <h5>{{ tr('courseWorkbench.lessonDocument.abilityObjective') }}</h5>
            <textarea v-if="editing" :value="listText(selectedSection.ability_objectives)" rows="3" @input="updateList(selectedSection, 'ability_objectives', $event)" />
            <ul v-else-if="abilityObjectives.length"><li v-for="item in abilityObjectives" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p>
          </div>
          <div>
            <h5>{{ tr('courseWorkbench.lessonDocument.educationObjective') }}</h5>
            <textarea v-if="editing" :value="listText(selectedSection.education_objectives)" rows="3" @input="updateList(selectedSection, 'education_objectives', $event)" />
            <ul v-else-if="educationObjectives.length"><li v-for="item in educationObjectives" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p>
          </div>
        </div>
      </section>

      <section class="document-section">
        <h4>{{ tr('courseWorkbench.lessonDocument.preClassPreparation') }}</h4>
        <textarea v-if="editing" :value="listText(selectedSection.pre_study)" rows="3" @input="updateList(selectedSection, 'pre_study', $event)" />
        <ul v-else-if="stringList(selectedSection.pre_study).length"><li v-for="item in stringList(selectedSection.pre_study)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p>
      </section>

      <section class="document-section">
        <h4>{{ tr('courseWorkbench.lessonDocument.keyAndDifficult') }}</h4>
        <div class="focus-grid">
          <div :class="{ 'ai-change-target': candidateChanged('key_points') }"><i v-if="candidateChanged('key_points')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.keyPoints') }}</h4><textarea v-if="editing" :value="listText(selectedSection.key_points)" rows="3" @input="updateList(selectedSection, 'key_points', $event)" /><ul v-else-if="stringList(selectedSection.key_points).length"><li v-for="item in stringList(selectedSection.key_points)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></div>
          <div :class="{ 'ai-change-target': candidateChanged('key_difficulties') }"><i v-if="candidateChanged('key_difficulties')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.difficulties') }}</h4><textarea v-if="editing" :value="listText(selectedSection.key_difficulties)" rows="3" @input="updateList(selectedSection, 'key_difficulties', $event)" /><ul v-else-if="stringList(selectedSection.key_difficulties).length"><li v-for="item in stringList(selectedSection.key_difficulties)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></div>
        </div>
      </section>

      <section :class="['document-section', 'flow-section', { 'ai-change-target': candidateChanged('teaching_modules') }]">
        <i v-if="candidateChanged('teaching_modules')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i>
        <div class="section-heading"><h4>{{ tr('courseWorkbench.lessonDocument.classroomProcess') }}</h4><span>{{ selectedSectionMinutes }} {{ tr('courseWorkbench.minutes') }}</span></div>
        <div class="teaching-block-list">
          <article v-for="(module, index) in teachingModules" :key="module.module_id || index" class="teaching-block">
            <header><strong>{{ moduleTitle(module, index) }}</strong><label class="block-duration"><span>{{ tr('courseWorkbench.lessonDocument.duration') }}</span><input v-if="editing" v-model.number="module.planned_minutes" type="number" min="0" max="300" @input="recordEditSnapshot" /><b v-else>{{ normalizedMinutes(module.planned_minutes) || emptyValue }} {{ tr('courseWorkbench.minutes') }}</b></label></header>
            <div class="block-fields">
              <label><span>{{ tr('courseWorkbench.lessonDocument.blockGoalContent') }}</span><textarea v-if="editing" v-model="module.teaching_purpose" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.teaching_purpose || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.teacherActivity') }}</span><textarea v-if="editing" v-model="module.teacher_activity" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.teacher_activity || module.teaching_guidance || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.studentActivity') }}</span><textarea v-if="editing" v-model="module.student_activity" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.student_activity || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.expectedOutput') }}</span><textarea v-if="editing" v-model="module.expected_output" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.expected_output || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.attainmentCheck') }}</span><textarea v-if="editing" v-model="module.check_method" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.check_method || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.feedbackAdjustment') }}</span><textarea v-if="editing" v-model="module.feedback_strategy" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.feedback_strategy || emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.adaptationOptions') }}</span><textarea v-if="editing" :value="listText(module.adaptation_options)" rows="4" @input="updateList(module, 'adaptation_options', $event)" /><ul v-else-if="stringList(module.adaptation_options).length"><li v-for="item in stringList(module.adaptation_options)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></label>
              <label><span>{{ tr('courseWorkbench.lessonDocument.transition') }}</span><textarea v-if="editing" v-model="module.transition" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.transition || emptyValue }}</p></label>
              <label class="wide"><span>{{ tr('courseWorkbench.lessonDocument.handoutPptMapping') }}</span><textarea v-if="editing" v-model="module.handout_ppt_mapping" rows="3" @input="recordEditSnapshot" /><p v-else>{{ module.handout_ppt_mapping || emptyValue }}</p></label>
            </div>
          </article>
          <div v-if="!teachingModules.length" class="flow-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>
        </div>
      </section>

      <section class="document-section"><h4>{{ tr('courseWorkbench.lessonDocument.classSummary') }}</h4><textarea v-if="editing" :value="listText(selectedSection.class_summary)" rows="4" @input="updateList(selectedSection, 'class_summary', $event)" /><ul v-else-if="summaryItems.length"><li v-for="item in summaryItems" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></section>

      <section class="document-section closing-grid">
        <div :class="{ 'ai-change-target': candidateChanged('homework') }"><i v-if="candidateChanged('homework')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.homework') }}</h4><textarea v-if="editing" :value="listText(selectedSection.homework)" rows="4" @input="updateList(selectedSection, 'homework', $event)" /><ol v-else-if="stringList(selectedSection.homework).length"><li v-for="item in stringList(selectedSection.homework)" :key="item">{{ item }}</li></ol><p v-else>{{ emptyValue }}</p></div>
        <div><h4>{{ tr('courseWorkbench.lessonDocument.extensionLearning') }}</h4><textarea v-if="editing" :value="listText(selectedSection.extension_learning)" rows="4" @input="updateList(selectedSection, 'extension_learning', $event)" /><ul v-else-if="extensionItems.length"><li v-for="item in extensionItems" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></div>
      </section>

      <section class="document-section materials-record"><h4>{{ tr('courseWorkbench.lessonDocument.materialsAndRecords') }}</h4><div class="closing-grid"><div><h4>{{ tr('courseWorkbench.lessonDocument.extensionReading') }}</h4><textarea v-if="editing" :value="listText(selectedSection.resource_refs)" rows="4" @input="updateList(selectedSection, 'resource_refs', $event)" /><ul v-else-if="stringList(selectedSection.resource_refs).length"><li v-for="item in stringList(selectedSection.resource_refs)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></div><div><h4>{{ tr('courseWorkbench.lessonDocument.activityPhotos') }}</h4><textarea v-if="editing" :value="listText(selectedSection.teaching_activity_photos)" rows="4" @input="updateList(selectedSection, 'teaching_activity_photos', $event)" /><ul v-else-if="stringList(selectedSection.teaching_activity_photos).length"><li v-for="item in stringList(selectedSection.teaching_activity_photos)" :key="item">{{ item }}</li></ul><p v-else>{{ tr('courseWorkbench.lessonDocument.activityPhotosPending') }}</p></div></div></section>

      <section class="document-section" :class="{ 'ai-change-target': candidateChanged('teaching_notes') }"><i v-if="candidateChanged('teaching_notes')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.notes') }}</h4><textarea v-if="editing" :value="listText(selectedSection.teaching_notes)" rows="4" @input="updateList(selectedSection, 'teaching_notes', $event)" /><ul v-else-if="stringList(selectedSection.teaching_notes).length"><li v-for="item in stringList(selectedSection.teaching_notes)" :key="item">{{ item }}</li></ul><p v-else>{{ emptyValue }}</p></section>
    </article>

    <div v-else class="document-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>

    <footer v-if="!externalToolbar && !pendingCandidate && !editing && !confirmed" class="document-footer">
      <button
        type="button"
        :disabled="confirming || qualityBlocked"
        :title="qualityBlocked ? qualityBlockMessage : ''"
        @click="emit('confirm')"
      >
        <LoaderCircle v-if="confirming" :size="15" class="spin" />
        <Check v-else :size="15" />
        {{ confirming
          ? tr('courseWorkbench.confirmingLessonPlan')
          : tr('courseWorkbench.confirmLessonPlan') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, LoaderCircle, Pencil, Sparkles, X } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import TextSelectionAiAction from './TextSelectionAiAction.vue'
import { useDocumentEditHistory } from '../composables/useDocumentEditHistory'
import { t } from '../shared/i18n'
import {
  useTeacherLessonAuthoringStore,
  type TeacherLessonPlanCandidate,
  type TeacherLessonProjection,
} from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'

const props = withDefaults(defineProps<{
  courseId: string
  courseTitle?: string
  lesson: TeacherLessonProjection
  confirmed?: boolean
  assistantOpen?: boolean
  confirming?: boolean
  confirmError?: string
  activeSectionId?: string
  materialAssetIds?: string[]
  externalToolbar?: boolean
}>(), {
  confirmed: false,
  assistantOpen: false,
  confirming: false,
  confirmError: '',
  activeSectionId: '',
  materialAssetIds: () => [],
  externalToolbar: false,
  courseTitle: '',
})

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'saved'): void
  (event: 'open-ai'): void
  (event: 'open-ai-selection', value: { text: string }): void
  (event: 'ai-candidate-change', value: TeacherLessonPlanCandidate | null): void
  (event: 'ai-busy-change', value: boolean): void
  (event: 'ai-resolving', value: { accept: boolean }): void
  (event: 'ai-resolved', value: { accept: boolean }): void
  (event: 'ai-error', value: string): void
  (event: 'update:activeSectionId', value: string): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
const editing = ref(false)
const saving = ref(false)
const saveError = ref<unknown>(null)
const draftPlan = ref<Record<string, any> | null>(null)
const localSectionId = ref('')
const aiBusy = ref(false)
const aiError = ref<unknown>(null)
const pendingCandidate = ref<TeacherLessonPlanCandidate | null>(null)
const documentRoot = ref<HTMLElement | null>(null)
const editHistory = useDocumentEditHistory<Record<string, any>>(snapshot => {
  draftPlan.value = clonePlan(snapshot)
})

const documentError = computed(() => {
  if (saveError.value) return toAppError(saveError.value, {
    title: tr('courseWorkbench.lessonDocument.saveFailed').replace(/，?请重试。?$/, ''),
    fallback: tr('courseWorkbench.lessonDocument.saveFailed'),
  })
  if (props.confirmError) return toAppError(props.confirmError, {
    title: tr('courseWorkbench.lessonDocument.confirmFailed'),
    fallback: props.confirmError,
  })
  return null
})

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.lessonDocument.edit': '编辑教案',
  'courseWorkbench.lessonDocument.editing': '编辑中',
  'courseWorkbench.lessonDocument.cancel': '取消',
  'courseWorkbench.lessonDocument.finishEditing': '完成编辑',
  'courseWorkbench.lessonDocument.saving': '正在保存…',
  'courseWorkbench.lessonDocument.saveFailed': '教案保存失败，请重试。',
  'courseWorkbench.lessonDocument.aiImprove': 'AI 修改',
  'courseWorkbench.lessonDocument.aiCandidate': 'AI 方案',
  'courseWorkbench.lessonDocument.discardAi': '放弃',
  'courseWorkbench.lessonDocument.applyAi': '采用',
  'courseWorkbench.lessonDocument.applyingAi': '正在采用…',
  'courseWorkbench.lessonDocument.aiFailed': 'AI 优化失败，请重试。',
  'courseWorkbench.lessonDocument.confirmFailed': '教案确认失败',
  'courseWorkbench.lessonDocument.candidateCanvasTitle': 'AI 候选正在左侧画布预览',
  'courseWorkbench.lessonDocument.changeMarker': 'AI 修改',
  'courseWorkbench.aiCollaboration.selectionModify': 'AI 修改',
  'courseWorkbench.lessonDocument.objective': '教学目标',
  'courseWorkbench.lessonDocument.courseName': '课程名称',
  'courseWorkbench.lessonDocument.lessonName': '课次',
  'courseWorkbench.lessonDocument.objectives': '教学目标',
  'courseWorkbench.lessonDocument.knowledgeObjective': '知识目标',
  'courseWorkbench.lessonDocument.abilityObjective': '能力目标',
  'courseWorkbench.lessonDocument.educationObjective': '育人目标',
  'courseWorkbench.lessonDocument.preClassPreparation': '课前准备（按需）',
  'courseWorkbench.lessonDocument.keyAndDifficult': '教学重点与难点',
  'courseWorkbench.lessonDocument.classroomProcess': '课堂教学过程',
  'courseWorkbench.lessonDocument.classSummary': '课程总结',
  'courseWorkbench.lessonDocument.extensionLearning': '拓展学习',
  'courseWorkbench.lessonDocument.activityPhotos': '教学活动照片',
  'courseWorkbench.lessonDocument.activityPhotosPending': '待教师课后补充，系统不编造照片。',
  'courseWorkbench.lessonDocument.keyPoints': '教学重点',
  'courseWorkbench.lessonDocument.difficulties': '教学难点',
  'courseWorkbench.lessonDocument.flow': '教学流程',
  'courseWorkbench.lessonDocument.duration': '时间',
  'courseWorkbench.lessonDocument.phase': '教学环节',
  'courseWorkbench.lessonDocument.phasePurpose': '环节目的',
  'courseWorkbench.lessonDocument.phaseFallback': '环节 {count}',
  'courseWorkbench.lessonDocument.teacherActivity': '教师活动',
  'courseWorkbench.lessonDocument.studentActivity': '学生活动',
  'courseWorkbench.lessonDocument.check': '检查与产出',
  'courseWorkbench.lessonDocument.blockGoalContent': '本块目标与内容',
  'courseWorkbench.lessonDocument.expectedOutput': '课堂产出',
  'courseWorkbench.lessonDocument.attainmentCheck': '达成检查',
  'courseWorkbench.lessonDocument.feedbackAdjustment': '反馈与调整',
  'courseWorkbench.lessonDocument.adaptationOptions': '不同达成状态下的处理',
  'courseWorkbench.lessonDocument.transition': '与前后教学块的衔接',
  'courseWorkbench.lessonDocument.handoutPptMapping': '讲义与 PPT 对应关系',
  'courseWorkbench.lessonDocument.materialsAndRecords': '教学资料与活动记录',
  'courseWorkbench.lessonDocument.extensionReading': '拓展阅读',
  'courseWorkbench.lessonDocument.homework': '课后作业',
  'courseWorkbench.lessonDocument.notes': '教学备注',
  'courseWorkbench.lessonDocument.empty': '-',
  'courseWorkbench.confirmingLessonPlan': '正在确认…',
  'courseWorkbench.confirmLessonPlan': '确认本讲教案',
  'courseWorkbench.lessonPlanConfirmed': '已确认',
  'courseWorkbench.lessonPlanPendingReview': '待确认',
  'courseWorkbench.lessonPlanPreparing': '教案内容正在整理，请稍后刷新。',
  'courseWorkbench.lessonSection': '本讲教案',
  'courseWorkbench.minutes': '分钟',
  'courseWorkbench.lessonModules.goal': '教学目标',
  'courseWorkbench.lessonModules.explanation': '核心讲解',
  'courseWorkbench.lessonModules.activity': '课堂活动',
  'courseWorkbench.lessonModules.example': '案例示范',
  'courseWorkbench.lessonModules.practice': '练习反馈',
  'courseWorkbench.lessonModules.feedback': '检查反馈',
  'courseWorkbench.lessonModules.concept': '概念梳理',
  'courseWorkbench.lessonModules.comparison': '对比辨析',
  'courseWorkbench.lessonModules.application': '迁移应用',
  'courseWorkbench.lessonModules.summary': '课堂小结',
  'courseWorkbench.lessonModules.transfer': '总结迁移',
  'courseWorkbench.lessonModules.assessment': '学习检查',
}

function tr(key: string): string {
  return t(key, fallbackMessages[key] || key)
}

const workingRevision = computed(() => props.lesson.plan.revisions.find(
  item => item.revision_id === props.lesson.plan.working_revision_id,
))
const currentPlan = computed(() => draftPlan.value || pendingCandidate.value?.plan || workingRevision.value?.plan || {})
const planSections = computed<any[]>(() => Array.isArray(currentPlan.value.sections) ? currentPlan.value.sections : [])
const selectedSectionId = computed({
  get: () => String(props.activeSectionId || localSectionId.value),
  set: (value: string) => {
    localSectionId.value = value
    emit('update:activeSectionId', value)
  },
})
const selectedSection = computed<any | null>(() => (
  planSections.value.find(section => String(section.node_id || '') === selectedSectionId.value)
  || planSections.value[0]
  || null
))
const basePlanSections = computed<any[]>(() => Array.isArray(workingRevision.value?.plan?.sections)
  ? workingRevision.value!.plan.sections
  : [])
const baseSelectedSection = computed<any | null>(() => (
  basePlanSections.value.find(section => String(section.node_id || '') === selectedSectionId.value)
  || basePlanSections.value[0]
  || null
))
const teachingModules = computed<any[]>(() => Array.isArray(selectedSection.value?.teaching_modules)
  ? selectedSection.value.teaching_modules
  : [])
const selectedSectionMinutes = computed(() => teachingModules.value.reduce(
  (total, module) => total + normalizedMinutes(module.planned_minutes),
  0,
))
const knowledgeObjectives = computed(() => stringList(selectedSection.value?.knowledge_objectives).length
  ? stringList(selectedSection.value?.knowledge_objectives)
  : uniqueItems([selectedSection.value?.learning_objective], 3))
const abilityObjectives = computed(() => stringList(selectedSection.value?.ability_objectives).length
  ? stringList(selectedSection.value?.ability_objectives)
  : uniqueItems([
      ...stringList(selectedSection.value?.student_activities),
      ...teachingModules.value.map(module => module.student_activity),
    ], 3))
const educationObjectives = computed(() => stringList(selectedSection.value?.education_objectives))
const objectiveCandidateChanged = computed(() => [
  'learning_objective', 'knowledge_objectives', 'ability_objectives', 'education_objectives',
].some(candidateChanged))
const summaryItems = computed(() => stringList(selectedSection.value?.class_summary).length
  ? stringList(selectedSection.value?.class_summary)
  : moduleItems(['summary', 'reflection', 'closure', 'transfer']))
const extensionItems = computed(() => stringList(selectedSection.value?.extension_learning).length
  ? stringList(selectedSection.value?.extension_learning)
  : [])
const qualityBlocked = computed(() => workingRevision.value?.quality_report?.passed === false)
const qualityBlockMessage = computed(() => String(
  workingRevision.value?.quality_report?.blocking_issues?.[0]?.message || '',
))

const emptyValue = computed(() => tr('courseWorkbench.lessonDocument.empty'))

const moduleLabels = computed<Record<string, string>>(() => ({
  lesson_goal: tr('courseWorkbench.lessonModules.goal'),
  core_explanation: tr('courseWorkbench.lessonModules.explanation'),
  learner_action: tr('courseWorkbench.lessonModules.activity'),
  explained_example: tr('courseWorkbench.lessonModules.example'),
  guided_practice: tr('courseWorkbench.lessonModules.practice'),
  feedback_check: tr('courseWorkbench.lessonModules.feedback'),
  general_concept_model: tr('courseWorkbench.lessonModules.concept'),
  general_comparison: tr('courseWorkbench.lessonModules.comparison'),
  general_explained_example: tr('courseWorkbench.lessonModules.example'),
  general_application: tr('courseWorkbench.lessonModules.application'),
  general_checklist: tr('courseWorkbench.lessonModules.summary'),
  summary_and_transfer: tr('courseWorkbench.lessonModules.transfer'),
  assessment: tr('courseWorkbench.lessonModules.assessment'),
}))

function clonePlan(plan: Record<string, any>): Record<string, any> {
  return JSON.parse(JSON.stringify(plan)) as Record<string, any>
}

function ensureFormalObjectiveFields(section: Record<string, any>) {
  if (!Array.isArray(section.knowledge_objectives)) {
    section.knowledge_objectives = stringList(section.learning_objective)
  }
  if (!Array.isArray(section.ability_objectives)) {
    section.ability_objectives = uniqueItems([
      ...stringList(section.student_activities),
      ...(Array.isArray(section.teaching_modules) ? section.teaching_modules.map((item: any) => item.student_activity) : []),
    ], 3)
  }
  if (!Array.isArray(section.education_objectives)) section.education_objectives = []
}

function stringList(value: unknown): string[] {
  if (typeof value === 'string') return value.split(/\n|；/).map(item => item.trim()).filter(Boolean)
  return Array.isArray(value) ? value.map(item => String(item).trim()).filter(Boolean) : []
}

function listText(value: unknown): string {
  return stringList(value).join('\n')
}

function uniqueItems(values: unknown[], limit = 8): string[] {
  return [...new Set(values.map(item => String(item || '').trim()).filter(Boolean))].slice(0, limit)
}

function moduleItems(signals: string[]): string[] {
  return uniqueItems(teachingModules.value.flatMap(module => {
    const identity = `${String(module.module_id || '').toLowerCase()} ${String(module.label || '').toLowerCase()}`
    if (!signals.some(signal => identity.includes(signal))) return []
    return [module.teacher_activity, module.student_activity]
  }))
}

function updateList(target: Record<string, any>, key: string, event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  target[key] = value.split('\n').map(item => item.trim()).filter(Boolean)
  recordEditSnapshot()
}

function recordEditSnapshot() {
  queueMicrotask(() => {
    if (editing.value && draftPlan.value) editHistory.record(draftPlan.value)
  })
}

function normalizedMinutes(value: unknown): number {
  const minutes = Number(value || 0)
  return Number.isFinite(minutes) ? Math.max(0, minutes) : 0
}

function sectionTitle(section: Record<string, any>): string {
  const nodeId = String(section.node_id || '')
  return props.lesson.sections.find(item => item.section_node_id === nodeId)?.title
    || tr('courseWorkbench.lessonSection')
}

function moduleTitle(module: Record<string, any>, index: number): string {
  return moduleLabels.value[String(module.module_id || '')]
    || tr('courseWorkbench.lessonDocument.phaseFallback').replace('{count}', String(index + 1))
}

function candidateChanged(key: string): boolean {
  if (!pendingCandidate.value || !selectedSection.value || !baseSelectedSection.value) return false
  return JSON.stringify(selectedSection.value[key] ?? null) !== JSON.stringify(baseSelectedSection.value[key] ?? null)
}

function beginEditing() {
  if (!workingRevision.value?.plan) return
  draftPlan.value = clonePlan(workingRevision.value.plan)
  for (const section of draftPlan.value.sections || []) ensureFormalObjectiveFields(section)
  editHistory.reset(draftPlan.value)
  editing.value = true
  saveError.value = null
}

async function requestAiCandidate(instructionValue: string): Promise<TeacherLessonPlanCandidate | null> {
  const instruction = instructionValue.trim()
  if (!instruction || aiBusy.value || !workingRevision.value?.revision_id) return null
  aiBusy.value = true
  aiError.value = null
  try {
    pendingCandidate.value = await lessonStore.createAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      workingRevision.value.revision_id,
      instruction,
      selectedSectionId.value,
      props.materialAssetIds,
    )
    return pendingCandidate.value
  } catch (error: any) {
    aiError.value = error
    return null
  } finally {
    aiBusy.value = false
  }
}

async function resolveAiCandidate(accept: boolean): Promise<boolean> {
  if (!pendingCandidate.value || aiBusy.value) return false
  emit('ai-resolving', { accept })
  aiBusy.value = true
  aiError.value = null
  try {
    await lessonStore.resolveAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      pendingCandidate.value.candidate_id,
      accept,
    )
    pendingCandidate.value = null
    emit('ai-resolved', { accept })
    return true
  } catch (error: any) {
    aiError.value = error
    return false
  } finally {
    aiBusy.value = false
  }
}

function focusCandidate() {
  const target = documentRoot.value?.querySelector<HTMLElement>('.ai-change-target')
  if (target && typeof target.scrollIntoView === 'function') {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function cancelEditing() {
  draftPlan.value = null
  editHistory.clear()
  editing.value = false
  saveError.value = null
}

async function saveDraft() {
  if (!draftPlan.value || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    for (const section of draftPlan.value.sections || []) {
      ensureFormalObjectiveFields(section)
      section.learning_objective = [...section.knowledge_objectives, ...section.ability_objectives].join('；')
    }
    await lessonStore.saveDraft(props.courseId, props.lesson.lesson_unit_id, draftPlan.value)
    draftPlan.value = null
    editing.value = false
    emit('saved')
  } catch (error: any) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

watch(() => [
  props.lesson.lesson_unit_id,
  props.lesson.plan.working_revision_id,
  props.lesson.plan.ai_candidates,
], () => {
  cancelEditing()
  aiError.value = null
  pendingCandidate.value = [...(props.lesson.plan.ai_candidates || [])]
    .reverse()
    .find(candidate => (
      candidate.status === 'pending'
      && candidate.base_revision_id === props.lesson.plan.working_revision_id
    )) || null
  selectedSectionId.value = String(
    pendingCandidate.value?.section_node_id
    || planSections.value[0]?.node_id
    || '',
  )
}, { immediate: true, deep: true })

watch(planSections, sections => {
  if (!sections.some(section => String(section.node_id || '') === selectedSectionId.value)) {
    selectedSectionId.value = String(sections[0]?.node_id || '')
  }
}, { deep: true })

watch(pendingCandidate, candidate => emit('ai-candidate-change', candidate), { immediate: true })
watch(aiBusy, busy => emit('ai-busy-change', busy))
watch(aiError, error => emit('ai-error', error ? toAppError(error, {
  title: tr('courseWorkbench.lessonDocument.aiFailed'),
  fallback: tr('courseWorkbench.lessonDocument.aiFailed'),
}).summary : ''))

defineExpose({
  requestAiCandidate,
  resolveAiCandidate,
  focusCandidate,
  editing,
  saving,
  aiBusy,
  qualityBlocked,
  qualityBlockMessage,
  beginEditing,
  cancelEditing,
  saveDraft,
  canUndo: editHistory.canUndo,
  canRedo: editHistory.canRedo,
  undoEdit: editHistory.undo,
  redoEdit: editHistory.redo,
})
</script>

<style scoped>
.lesson-document{position:relative;background:#fff}
.document-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}
.document-title{min-width:0;display:flex;align-items:center}.document-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}
.document-actions{flex:none;display:flex;align-items:center;gap:2px}.document-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:12px;font-weight:750;cursor:pointer}.document-actions button:hover{color:#3730a3;background:#f2f3fa}.document-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.document-actions button:disabled{opacity:.5;cursor:not-allowed}.document-actions .primary-action{margin-left:4px;border-color:#d7ddea;color:#3730a3;background:#fff}.document-actions .primary-action:hover{border-color:#c6cbe0;background:#f7f7ff}
.candidate-canvas-notice{display:flex;align-items:center;gap:10px;padding:11px 28px;border-bottom:1px solid #d9ddf5;color:#4338ca;background:#f5f5ff}.candidate-canvas-notice strong{font-size:11.5px}.lesson-document>:deep(.app-error-notice){margin:12px 28px 0}
.document-body{min-width:0;display:grid;padding:12px 28px 34px}.section-title{display:flex;align-items:center;gap:10px;padding:17px 0 2px}.section-title span{color:#6366f1;font-size:11px;font-weight:850}.section-title h4{margin:0;color:#172033;font-size:16px}.document-section{min-width:0;padding:22px 0;border-bottom:1px solid #e8ecf2}.document-section:last-child{border-bottom:0}.document-section h4{margin:0 0 12px;color:#263147;font-size:13px}.document-section p{margin:0;color:#536176;font-size:13px;line-height:1.7}.document-section ul,.document-section ol{display:grid;gap:7px;margin:0;padding-left:18px;color:#536176;font-size:13px;line-height:1.6}.document-section textarea,.flow-row input{width:100%;box-sizing:border-box;border:1px solid #cbd4e1;border-radius:7px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.55}.document-section textarea{min-height:74px;padding:9px 10px;resize:vertical}.document-section textarea:focus,.flow-row input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}
.lesson-identity{display:grid;grid-template-columns:1fr 1fr;gap:28px}.lesson-identity div{display:grid;gap:6px}.lesson-identity span{color:#7a8699;font-size:11px}.lesson-identity strong{color:#263147;font-size:13px}.objective-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.objective-grid>div{min-width:0}.objective-grid h5{margin:0 0 9px;color:#4a5568;font-size:12px}.objective-section p{font-size:13px}.focus-grid,.closing-grid{display:grid;grid-template-columns:1fr 1fr;gap:0}.focus-grid>div,.closing-grid>div{min-width:0;padding-right:26px}.focus-grid>div+div,.closing-grid>div+div{padding-right:0;padding-left:26px;border-left:1px solid #e8ecf2}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-heading span{color:#7a8699;font-size:11px}
.teaching-block-list{display:grid;gap:14px}.teaching-block{overflow:hidden;border:1px solid #dde3ec;border-radius:10px;background:#fff}.teaching-block>header{min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:8px 14px;border-bottom:1px solid #e5eaf1;background:#f7f9fc}.teaching-block>header>strong{color:#334155;font-size:12.5px}.block-duration{display:flex;align-items:center;gap:8px;color:#718096;font-size:11px}.block-duration input{width:64px;height:32px;padding:5px;border:1px solid #cbd4e1;border-radius:7px;text-align:center}.block-duration b{color:#475569;font-size:11px}.block-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0}.block-fields>label{min-width:0;display:grid;align-content:start;gap:7px;padding:14px;border-right:1px solid #e8ecf2;border-bottom:1px solid #e8ecf2}.block-fields>label:nth-child(2n){border-right:0}.block-fields>label.wide{grid-column:1/-1;border-right:0}.block-fields>label>span{color:#64748b;font-size:11px;font-weight:750}.block-fields textarea{min-height:76px}.block-fields p{font-size:12px;line-height:1.6}.block-fields ul{font-size:12px}.materials-record>h4{margin-bottom:18px}
.ai-change-target{position:relative}.is-ai-candidate .ai-change-target{margin-inline:-10px;padding-inline:10px;border-radius:9px;background:linear-gradient(90deg,rgba(238,242,255,.92),rgba(248,250,255,.42))}.ai-change-target::before{position:absolute;top:8px;bottom:8px;left:0;width:2px;border-radius:2px;background:#6366f1;content:""}.ai-change-marker{position:absolute;top:7px;right:9px;padding:3px 6px;border-radius:5px;color:#4338ca;background:#e0e7ff;font-size:9px;font-style:normal;font-weight:800}.flow-section.ai-change-target{padding-inline:10px}.focus-grid>div.ai-change-target,.closing-grid>div.ai-change-target{padding-top:12px;padding-bottom:12px}.focus-grid>div+div.ai-change-target,.closing-grid>div+div.ai-change-target{padding-left:36px}
.flow-table{width:100%;max-width:100%;box-sizing:border-box;overflow:hidden;border:1px solid #dde3ec;border-radius:8px}.flow-row{display:grid;grid-template-columns:64px minmax(120px,.82fr) minmax(170px,1.2fr) minmax(150px,1fr) minmax(150px,1fr);border-top:1px solid #e3e8f0}.flow-row:first-child{border-top:0}.flow-row>div,.flow-head>span{min-width:0;padding:12px 11px;border-left:1px solid #e3e8f0}.flow-row>div:first-child,.flow-head>span:first-child{border-left:0}.flow-head{color:#64748b;background:#f6f8fb;font-size:11px;font-weight:750}.flow-row p{font-size:12px;line-height:1.58}.flow-row ul{gap:5px;padding-left:15px;font-size:12px;line-height:1.5}.duration-cell{color:#475569;font-size:12px;text-align:center}.duration-cell input{height:34px;padding:6px;text-align:center}.phase-cell{display:grid;align-content:start;gap:7px}.phase-cell strong{color:#334155;font-size:12px}.phase-cell p{color:#7a8699;font-size:11px}.flow-row textarea{min-height:112px}.flow-empty{padding:28px;color:#7a8699;font-size:12px;text-align:center}
.document-empty{min-height:280px;display:grid;place-items:center;color:#7a8699;font-size:13px}.document-footer{min-height:64px;display:flex;align-items:center;justify-content:flex-end;gap:18px;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.document-footer button{min-height:38px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.document-footer button:hover{border-color:#4338ca;background:#4338ca}.document-footer button:disabled{opacity:.45;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1050px){.document-body{padding-inline:20px}.objective-grid{grid-template-columns:1fr}}
@media(max-width:760px){.document-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.document-actions{width:100%;justify-content:flex-end}.focus-grid,.closing-grid,.block-fields{grid-template-columns:1fr}.focus-grid>div,.closing-grid>div{padding-right:0}.focus-grid>div+div,.closing-grid>div+div{margin-top:20px;padding:20px 0 0;border-top:1px solid #e8ecf2;border-left:0}.block-fields>label{border-right:0}.document-footer{padding-inline:18px}}
.document-footer,.document-actions button:hover{background:var(--teacher-component-tint,#f7f7ff)}
</style>
