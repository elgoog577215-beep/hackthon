<template>
  <section class="lesson-document">
    <header class="document-header">
      <div class="document-title">
        <div class="document-kicker">
          <span>{{ tr('courseWorkbench.lessonDocument.title') }}</span>
          <i :data-state="documentState">{{ documentStateLabel }}</i>
        </div>
        <h3>{{ lesson.title }}</h3>
        <p>
          {{ sectionCountLabel }}
          <span aria-hidden="true">·</span>
          {{ totalMinutesLabel }}
        </p>
      </div>
      <div class="document-actions">
        <template v-if="pendingCandidate">
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
          <button type="button" :disabled="aiBusy" @click="aiOpen = !aiOpen">
            <Sparkles :size="15" />{{ tr('courseWorkbench.lessonDocument.aiImprove') }}
          </button>
          <button type="button" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.lessonDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <form v-if="aiOpen && !pendingCandidate && !editing" class="ai-command" @submit.prevent="createAiCandidate">
      <textarea
        v-model="aiInstruction"
        rows="2"
        :placeholder="tr('courseWorkbench.lessonDocument.aiPlaceholder')"
        :aria-label="tr('courseWorkbench.lessonDocument.aiImprove')"
      />
      <button class="primary-action" type="submit" :disabled="aiBusy || !aiInstruction.trim()">
        <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
        <Sparkles v-else :size="15" />
        {{ aiBusy ? tr('courseWorkbench.lessonDocument.aiGenerating') : tr('courseWorkbench.lessonDocument.generateAi') }}
      </button>
    </form>

    <p v-if="saveError || aiError || confirmError" class="document-error" role="alert">{{ saveError || aiError || confirmError }}</p>

    <nav v-if="planSections.length > 1" class="section-tabs" :aria-label="tr('courseWorkbench.lessonDocument.sectionNavigation')">
      <button
        v-for="(section, index) in planSections"
        :key="section.node_id || index"
        type="button"
        :class="{ active: selectedSectionId === section.node_id }"
        @click="selectedSectionId = section.node_id"
      >
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        {{ sectionTitle(section) }}
      </button>
    </nav>

    <article v-if="selectedSection" class="document-body">
      <header class="section-title">
        <span>{{ String(selectedSectionIndex + 1).padStart(2, '0') }}</span>
        <h4>{{ sectionTitle(selectedSection) }}</h4>
      </header>
      <section class="document-section objective-section">
        <h4>{{ tr('courseWorkbench.lessonDocument.objective') }}</h4>
        <textarea
          v-if="editing"
          v-model="selectedSection.learning_objective"
          rows="3"
          :aria-label="tr('courseWorkbench.lessonDocument.objective')"
        />
        <p v-else>{{ selectedSection.learning_objective || emptyValue }}</p>
      </section>

      <section class="document-section focus-grid">
        <div>
          <h4>{{ tr('courseWorkbench.lessonDocument.keyPoints') }}</h4>
          <textarea
            v-if="editing"
            :value="listText(selectedSection.key_points)"
            rows="3"
            :aria-label="tr('courseWorkbench.lessonDocument.keyPoints')"
            @input="updateList(selectedSection, 'key_points', $event)"
          />
          <ul v-else-if="stringList(selectedSection.key_points).length">
            <li v-for="item in stringList(selectedSection.key_points)" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ emptyValue }}</p>
        </div>
        <div>
          <h4>{{ tr('courseWorkbench.lessonDocument.difficulties') }}</h4>
          <textarea
            v-if="editing"
            :value="listText(selectedSection.key_difficulties)"
            rows="3"
            :aria-label="tr('courseWorkbench.lessonDocument.difficulties')"
            @input="updateList(selectedSection, 'key_difficulties', $event)"
          />
          <ul v-else-if="stringList(selectedSection.key_difficulties).length">
            <li v-for="item in stringList(selectedSection.key_difficulties)" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ emptyValue }}</p>
        </div>
      </section>

      <section class="document-section flow-section">
        <div class="section-heading">
          <h4>{{ tr('courseWorkbench.lessonDocument.flow') }}</h4>
          <span>{{ selectedSectionMinutes }} {{ tr('courseWorkbench.minutes') }}</span>
        </div>
        <div class="flow-table" role="table" :aria-label="tr('courseWorkbench.lessonDocument.flow')">
          <div class="flow-row flow-head" role="row">
            <span role="columnheader">{{ tr('courseWorkbench.lessonDocument.duration') }}</span>
            <span role="columnheader">{{ tr('courseWorkbench.lessonDocument.phase') }}</span>
            <span role="columnheader">{{ tr('courseWorkbench.lessonDocument.teacherActivity') }}</span>
            <span role="columnheader">{{ tr('courseWorkbench.lessonDocument.studentActivity') }}</span>
            <span role="columnheader">{{ tr('courseWorkbench.lessonDocument.check') }}</span>
          </div>
          <div
            v-for="(module, index) in teachingModules"
            :key="module.module_id || index"
            class="flow-row"
            role="row"
          >
            <div class="duration-cell" role="cell">
              <input
                v-if="editing"
                v-model.number="module.planned_minutes"
                type="number"
                min="0"
                max="300"
                :aria-label="tr('courseWorkbench.lessonDocument.duration')"
              />
              <span v-else>{{ normalizedMinutes(module.planned_minutes) || emptyValue }}</span>
            </div>
            <div class="phase-cell" role="cell">
              <strong>{{ moduleTitle(module, index) }}</strong>
              <textarea
                v-if="editing"
                v-model="module.teaching_purpose"
                rows="3"
                :aria-label="tr('courseWorkbench.lessonDocument.phasePurpose')"
              />
              <p v-else-if="module.teaching_purpose">{{ module.teaching_purpose }}</p>
            </div>
            <div role="cell">
              <textarea
                v-if="editing"
                v-model="module.teacher_activity"
                rows="5"
                :aria-label="tr('courseWorkbench.lessonDocument.teacherActivity')"
              />
              <p v-else>{{ module.teacher_activity || module.teaching_guidance || emptyValue }}</p>
            </div>
            <div role="cell">
              <textarea
                v-if="editing"
                v-model="module.student_activity"
                rows="5"
                :aria-label="tr('courseWorkbench.lessonDocument.studentActivity')"
              />
              <p v-else>{{ module.student_activity || emptyValue }}</p>
            </div>
            <div role="cell">
              <textarea
                v-if="editing && index === checkModuleIndex"
                :value="listText(selectedSection.in_class_checks)"
                rows="5"
                :aria-label="tr('courseWorkbench.lessonDocument.check')"
                @input="updateList(selectedSection, 'in_class_checks', $event)"
              />
              <ul v-else-if="index === checkModuleIndex && stringList(selectedSection.in_class_checks).length">
                <li v-for="item in stringList(selectedSection.in_class_checks)" :key="item">{{ item }}</li>
              </ul>
              <span v-else>{{ emptyValue }}</span>
            </div>
          </div>
          <div v-if="!teachingModules.length" class="flow-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>
        </div>
      </section>

      <section class="document-section closing-grid">
        <div>
          <h4>{{ tr('courseWorkbench.lessonDocument.homework') }}</h4>
          <textarea
            v-if="editing"
            :value="listText(selectedSection.homework)"
            rows="4"
            :aria-label="tr('courseWorkbench.lessonDocument.homework')"
            @input="updateList(selectedSection, 'homework', $event)"
          />
          <ol v-else-if="stringList(selectedSection.homework).length">
            <li v-for="item in stringList(selectedSection.homework)" :key="item">{{ item }}</li>
          </ol>
          <p v-else>{{ emptyValue }}</p>
        </div>
        <div>
          <h4>{{ tr('courseWorkbench.lessonDocument.notes') }}</h4>
          <textarea
            v-if="editing"
            :value="listText(selectedSection.teaching_notes)"
            rows="4"
            :aria-label="tr('courseWorkbench.lessonDocument.notes')"
            @input="updateList(selectedSection, 'teaching_notes', $event)"
          />
          <ul v-else-if="stringList(selectedSection.teaching_notes).length">
            <li v-for="item in stringList(selectedSection.teaching_notes)" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ emptyValue }}</p>
        </div>
      </section>
    </article>

    <div v-else class="document-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>

    <footer v-if="!pendingCandidate && !editing" class="document-footer">
      <span v-if="confirmed" class="document-saved"><Check :size="15" />{{ tr('courseWorkbench.lessonPlanConfirmed') }}</span>
      <span v-else />
      <button
        type="button"
        :disabled="confirming || qualityBlocked"
        :title="qualityBlocked ? qualityBlockMessage : ''"
        @click="continueWorkflow"
      >
        <LoaderCircle v-if="confirming" :size="15" class="spin" />
        <ArrowRight v-else :size="15" />
        {{ confirming
          ? tr('courseWorkbench.confirmingLessonPlan')
          : confirmed
            ? tr('courseWorkbench.lessonDocument.next')
            : tr('courseWorkbench.confirmLessonPlanAndContinue') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Check, LoaderCircle, Pencil, Sparkles, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import {
  useTeacherLessonAuthoringStore,
  type TeacherLessonPlanCandidate,
  type TeacherLessonProjection,
} from '../stores/teacherLessonAuthoring'

const props = withDefaults(defineProps<{
  courseId: string
  lesson: TeacherLessonProjection
  confirmed?: boolean
  confirming?: boolean
  confirmError?: string
}>(), {
  confirmed: false,
  confirming: false,
  confirmError: '',
})

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'next'): void
  (event: 'saved'): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const draftPlan = ref<Record<string, any> | null>(null)
const selectedSectionId = ref('')
const aiOpen = ref(false)
const aiInstruction = ref('')
const aiBusy = ref(false)
const aiError = ref('')
const pendingCandidate = ref<TeacherLessonPlanCandidate | null>(null)

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.lessonDocument.title': '标准教案',
  'courseWorkbench.lessonDocument.sectionCount': '{count} 个小节',
  'courseWorkbench.lessonDocument.totalMinutes': '{count} 分钟',
  'courseWorkbench.lessonDocument.edit': '编辑教案',
  'courseWorkbench.lessonDocument.editing': '编辑中',
  'courseWorkbench.lessonDocument.cancel': '取消',
  'courseWorkbench.lessonDocument.finishEditing': '完成编辑',
  'courseWorkbench.lessonDocument.saving': '正在保存…',
  'courseWorkbench.lessonDocument.saveFailed': '教案保存失败，请重试。',
  'courseWorkbench.lessonDocument.aiImprove': 'AI 优化',
  'courseWorkbench.lessonDocument.aiPlaceholder': '输入你想调整的内容…',
  'courseWorkbench.lessonDocument.generateAi': '生成方案',
  'courseWorkbench.lessonDocument.aiGenerating': '生成中…',
  'courseWorkbench.lessonDocument.aiCandidate': 'AI 方案',
  'courseWorkbench.lessonDocument.discardAi': '放弃',
  'courseWorkbench.lessonDocument.applyAi': '采用',
  'courseWorkbench.lessonDocument.applyingAi': '正在采用…',
  'courseWorkbench.lessonDocument.aiFailed': 'AI 优化失败，请重试。',
  'courseWorkbench.lessonDocument.next': '进入题库',
  'courseWorkbench.lessonDocument.sectionNavigation': '教案小节',
  'courseWorkbench.lessonDocument.objective': '教学目标',
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
  'courseWorkbench.lessonDocument.homework': '课后作业',
  'courseWorkbench.lessonDocument.notes': '教学备注',
  'courseWorkbench.lessonDocument.empty': '-',
  'courseWorkbench.confirmingLessonPlan': '正在确认…',
  'courseWorkbench.confirmLessonPlanAndContinue': '确认并进入题库',
  'courseWorkbench.lessonPlanConfirmed': '教案已确认',
  'courseWorkbench.lessonPlanPendingReview': '待确认',
  'courseWorkbench.lessonPlanPreparing': '教案内容正在整理，请稍后刷新。',
  'courseWorkbench.lessonSection': '教学小节',
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
const selectedSection = computed<any | null>(() => (
  planSections.value.find(section => String(section.node_id || '') === selectedSectionId.value)
  || planSections.value[0]
  || null
))
const selectedSectionIndex = computed(() => Math.max(0, planSections.value.indexOf(selectedSection.value)))
const teachingModules = computed<any[]>(() => Array.isArray(selectedSection.value?.teaching_modules)
  ? selectedSection.value.teaching_modules
  : [])
const checkModuleIndex = computed(() => {
  const preferred = teachingModules.value.findIndex(module => [
    'feedback_check',
    'assessment',
    'general_checklist',
    'summary_and_transfer',
  ].includes(String(module.module_id || '')))
  return preferred >= 0 ? preferred : teachingModules.value.length - 1
})
const selectedSectionMinutes = computed(() => teachingModules.value.reduce(
  (total, module) => total + normalizedMinutes(module.planned_minutes),
  0,
))
const totalMinutes = computed(() => planSections.value.reduce((total, section) => {
  const modules = Array.isArray(section.teaching_modules) ? section.teaching_modules : []
  const moduleMinutes = modules.reduce((sum: number, module: any) => sum + normalizedMinutes(module.planned_minutes), 0)
  return total + (moduleMinutes || normalizedMinutes(section.planned_minutes))
}, 0))
const sectionCountLabel = computed(() => tr('courseWorkbench.lessonDocument.sectionCount').replace('{count}', String(planSections.value.length)))
const totalMinutesLabel = computed(() => tr('courseWorkbench.lessonDocument.totalMinutes').replace('{count}', String(totalMinutes.value)))
const qualityBlocked = computed(() => workingRevision.value?.quality_report?.passed === false)
const qualityBlockMessage = computed(() => String(
  workingRevision.value?.quality_report?.blocking_issues?.[0]?.message || '',
))
const documentState = computed(() => pendingCandidate.value ? 'candidate' : editing.value ? 'editing' : props.confirmed ? 'confirmed' : 'draft')
const documentStateLabel = computed(() => pendingCandidate.value
  ? tr('courseWorkbench.lessonDocument.aiCandidate')
  : editing.value
    ? tr('courseWorkbench.lessonDocument.editing')
    : props.confirmed
      ? tr('courseWorkbench.lessonPlanConfirmed')
      : tr('courseWorkbench.lessonPlanPendingReview'))

function continueWorkflow() {
  if (props.confirmed) emit('next')
  else emit('confirm')
}
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

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item).trim()).filter(Boolean) : []
}

function listText(value: unknown): string {
  return stringList(value).join('\n')
}

function updateList(target: Record<string, any>, key: string, event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  target[key] = value.split('\n').map(item => item.trim()).filter(Boolean)
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

function beginEditing() {
  if (!workingRevision.value?.plan) return
  aiOpen.value = false
  draftPlan.value = clonePlan(workingRevision.value.plan)
  editing.value = true
  saveError.value = ''
}

async function createAiCandidate() {
  const instruction = aiInstruction.value.trim()
  if (!instruction || aiBusy.value || !workingRevision.value?.revision_id) return
  aiBusy.value = true
  aiError.value = ''
  try {
    pendingCandidate.value = await lessonStore.createAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      workingRevision.value.revision_id,
      instruction,
      selectedSectionId.value,
    )
    aiOpen.value = false
  } catch (error: any) {
    aiError.value = String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || error?.message
      || tr('courseWorkbench.lessonDocument.aiFailed'),
    )
  } finally {
    aiBusy.value = false
  }
}

async function resolveAiCandidate(accept: boolean) {
  if (!pendingCandidate.value || aiBusy.value) return
  aiBusy.value = true
  aiError.value = ''
  try {
    await lessonStore.resolveAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      pendingCandidate.value.candidate_id,
      accept,
    )
    pendingCandidate.value = null
    aiInstruction.value = ''
  } catch (error: any) {
    aiError.value = String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || error?.message
      || tr('courseWorkbench.lessonDocument.aiFailed'),
    )
  } finally {
    aiBusy.value = false
  }
}

function cancelEditing() {
  draftPlan.value = null
  editing.value = false
  saveError.value = ''
}

async function saveDraft() {
  if (!draftPlan.value || saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    await lessonStore.saveDraft(props.courseId, props.lesson.lesson_unit_id, draftPlan.value)
    draftPlan.value = null
    editing.value = false
    emit('saved')
  } catch (error: any) {
    saveError.value = String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || error?.message
      || tr('courseWorkbench.lessonDocument.saveFailed'),
    )
  } finally {
    saving.value = false
  }
}

watch(() => props.lesson.lesson_unit_id, () => {
  cancelEditing()
  pendingCandidate.value = null
  aiOpen.value = false
  aiInstruction.value = ''
  aiError.value = ''
  selectedSectionId.value = String(planSections.value[0]?.node_id || '')
}, { immediate: true })

watch(planSections, sections => {
  if (!sections.some(section => String(section.node_id || '') === selectedSectionId.value)) {
    selectedSectionId.value = String(sections[0]?.node_id || '')
  }
}, { deep: true })
</script>

<style scoped>
.lesson-document{background:#fff}
.document-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}
.document-title{min-width:0;display:grid;gap:5px}.document-kicker{display:flex;align-items:center;gap:9px;color:#6366f1;font-size:11px;font-weight:800}.document-kicker i{padding:3px 7px;border-radius:999px;color:#92400e;background:#fff7ed;font-style:normal;font-weight:750}.document-kicker i[data-state="confirmed"]{color:#047857;background:#ecfdf5}.document-kicker i[data-state="editing"],.document-kicker i[data-state="candidate"]{color:#4338ca;background:#eef2ff}.document-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}.document-title p{display:flex;align-items:center;gap:7px;margin:0;color:#7a8699;font-size:12px}
.document-actions{flex:none;display:flex;align-items:center;gap:2px}.document-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:12px;font-weight:750;cursor:pointer}.document-actions button:hover{color:#3730a3;background:#f2f3fa}.document-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.document-actions button:disabled{opacity:.5;cursor:not-allowed}.document-actions .primary-action{margin-left:4px;border-color:#d7ddea;color:#3730a3;background:#fff}.document-actions .primary-action:hover{border-color:#c6cbe0;background:#f7f7ff}
.ai-command{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;gap:10px;padding:12px 28px;border-bottom:1px solid #e8ecf2;background:#fbfcff}.ai-command textarea{min-height:58px;padding:9px 11px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.5;resize:vertical}.ai-command textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.ai-command button{min-width:108px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border:0;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.ai-command button:disabled{opacity:.5;cursor:not-allowed}.document-error{margin:0;padding:10px 28px;color:#b91c1c;background:#fff1f2;font-size:12px}.section-tabs{display:flex;gap:24px;overflow:auto;padding:0 28px;border-bottom:1px solid #e8ecf2}.section-tabs button{max-width:280px;min-height:48px;display:flex;align-items:center;gap:7px;padding:0;border:0;border-bottom:2px solid transparent;color:#64748b;background:transparent;font-size:12px;white-space:nowrap;cursor:pointer}.section-tabs button span{color:#94a3b8;font-size:10px;font-weight:800}.section-tabs button:hover{color:#3730a3}.section-tabs button.active{border-bottom-color:#5b57e8;color:#3730a3;font-weight:750}.section-tabs button.active span{color:#6366f1}
.document-body{display:grid;padding:12px 28px 34px}.section-title{display:flex;align-items:center;gap:10px;padding:17px 0 2px}.section-title span{color:#6366f1;font-size:11px;font-weight:850}.section-title h4{margin:0;color:#172033;font-size:16px}.document-section{padding:22px 0;border-bottom:1px solid #e8ecf2}.document-section:last-child{border-bottom:0}.document-section h4{margin:0 0 12px;color:#263147;font-size:13px}.document-section p{margin:0;color:#536176;font-size:13px;line-height:1.7}.document-section ul,.document-section ol{display:grid;gap:7px;margin:0;padding-left:18px;color:#536176;font-size:13px;line-height:1.6}.document-section textarea,.flow-row input{width:100%;box-sizing:border-box;border:1px solid #cbd4e1;border-radius:7px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.55}.document-section textarea{min-height:74px;padding:9px 10px;resize:vertical}.document-section textarea:focus,.flow-row input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}
.objective-section>p{max-width:820px;font-size:14px}.focus-grid,.closing-grid{display:grid;grid-template-columns:1fr 1fr;gap:0}.focus-grid>div,.closing-grid>div{min-width:0;padding-right:26px}.focus-grid>div+div,.closing-grid>div+div{padding-right:0;padding-left:26px;border-left:1px solid #e8ecf2}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-heading span{color:#7a8699;font-size:11px}
.flow-table{overflow:hidden;border:1px solid #dde3ec;border-radius:8px}.flow-row{display:grid;grid-template-columns:64px minmax(120px,.82fr) minmax(170px,1.2fr) minmax(150px,1fr) minmax(150px,1fr);border-top:1px solid #e3e8f0}.flow-row:first-child{border-top:0}.flow-row>div,.flow-head>span{min-width:0;padding:12px 11px;border-left:1px solid #e3e8f0}.flow-row>div:first-child,.flow-head>span:first-child{border-left:0}.flow-head{color:#64748b;background:#f6f8fb;font-size:11px;font-weight:750}.flow-row p{font-size:12px;line-height:1.58}.flow-row ul{gap:5px;padding-left:15px;font-size:12px;line-height:1.5}.duration-cell{color:#475569;font-size:12px;text-align:center}.duration-cell input{height:34px;padding:6px;text-align:center}.phase-cell{display:grid;align-content:start;gap:7px}.phase-cell strong{color:#334155;font-size:12px}.phase-cell p{color:#7a8699;font-size:11px}.flow-row textarea{min-height:112px}.flow-empty{padding:28px;color:#7a8699;font-size:12px;text-align:center}
.document-empty{min-height:280px;display:grid;place-items:center;color:#7a8699;font-size:13px}.document-footer{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.document-footer button{min-height:38px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.document-footer button:hover{border-color:#4338ca;background:#4338ca}.document-footer button:disabled{opacity:.45;cursor:not-allowed}.document-saved{display:flex;align-items:center;gap:7px;color:#047857;font-size:12px;font-weight:700}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1050px){.document-body{padding-inline:20px}.flow-table{overflow:auto}.flow-row{min-width:800px}}
@media(max-width:760px){.document-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.document-actions{width:100%;justify-content:flex-end}.ai-command{grid-template-columns:1fr;padding-inline:18px}.ai-command button{min-height:38px}.section-tabs{padding-inline:18px}.focus-grid,.closing-grid{grid-template-columns:1fr}.focus-grid>div,.closing-grid>div{padding-right:0}.focus-grid>div+div,.closing-grid>div+div{margin-top:20px;padding:20px 0 0;border-top:1px solid #e8ecf2;border-left:0}.document-footer{padding-inline:18px}}
</style>
