<template>
  <Teleport to="body">
    <div v-if="modelValue" class="baseline-dialog-layer" @keydown.esc="close">
      <button class="baseline-dialog-backdrop" type="button" :aria-label="t('common.close')" @click="close" />
      <section class="baseline-dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
        <header>
          <span class="baseline-dialog__mark"><SlidersHorizontal :size="17" /></span>
          <div>
            <h2 :id="titleId">{{ t('courseFiles.workbench.baselineEditorTitle') }}</h2>
            <p>{{ t('courseFiles.workbench.baselineEditorHelp') }}</p>
          </div>
          <button class="icon-button" type="button" :aria-label="t('common.close')" :disabled="busy" @click="close"><X :size="18" /></button>
        </header>

        <form class="baseline-dialog__body" @submit.prevent="submit">
          <div v-if="aiDraft" class="ai-draft-notice" role="status">
            <Sparkles :size="16" />
            <span>{{ t('courseFiles.workbench.aiDraftNotice') }}</span>
          </div>

          <fieldset class="form-section">
            <legend>{{ t('courseFiles.workbench.courseType') }}</legend>
            <div class="course-type-options">
              <button
                v-for="item in courseTypeOptions"
                :key="item.value"
                type="button"
                :class="{ active: form.courseType === item.value }"
                :aria-pressed="form.courseType === item.value"
                :disabled="busy"
                @click="form.courseType = item.value"
              >
                <component :is="item.icon" :size="17" />
                <span><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></span>
              </button>
            </div>
          </fieldset>

          <section class="form-section intent-fields">
            <template v-if="form.courseType === 'systematic'">
              <label for="baseline-learning-goal">{{ t('courseFiles.workbench.learningGoal') }}</label>
              <textarea id="baseline-learning-goal" v-model="form.systematicGoal" required maxlength="2000" :disabled="busy" :placeholder="t('teacherCourseCreate.goalPlaceholder')" />
            </template>
            <template v-else-if="form.courseType === 'project'">
              <label for="baseline-project-goal">{{ t('courseGeneration.project.goalLabel') }}</label>
              <textarea id="baseline-project-goal" v-model="form.projectGoal" required maxlength="3000" :disabled="busy" :placeholder="t('courseGeneration.project.goalPlaceholder')" />
              <label for="baseline-project-deliverable">{{ t('courseGeneration.project.deliverableLabel') }}</label>
              <textarea id="baseline-project-deliverable" v-model="form.expectedDeliverable" required maxlength="3000" :disabled="busy" :placeholder="t('courseGeneration.project.deliverablePlaceholder')" />
            </template>
            <template v-else-if="form.courseType === 'inquiry'">
              <label for="baseline-core-question">{{ t('courseGeneration.inquiry.questionLabel') }}</label>
              <textarea id="baseline-core-question" v-model="form.coreQuestion" required maxlength="3000" :disabled="busy" :placeholder="t('courseGeneration.inquiry.questionPlaceholder')" />
              <label for="baseline-desired-output">{{ t('courseGeneration.inquiry.outputLabel') }}</label>
              <textarea id="baseline-desired-output" v-model="form.desiredOutput" required maxlength="3000" :disabled="busy" :placeholder="t('courseGeneration.inquiry.outputPlaceholder')" />
            </template>
            <template v-else>
              <div class="two-column-fields">
                <label for="baseline-exam-name"><span>{{ t('courseGeneration.exam.nameLabel') }}</span><input id="baseline-exam-name" v-model="form.examName" required maxlength="1000" :disabled="busy" :placeholder="t('courseGeneration.exam.namePlaceholder')" /></label>
                <label for="baseline-exam-date"><span>{{ t('courseGeneration.exam.dateLabel') }}</span><input id="baseline-exam-date" v-model="form.examDate" required type="date" :disabled="busy" /></label>
              </div>
              <label for="baseline-exam-scope">{{ t('courseGeneration.exam.scopeLabel') }}</label>
              <textarea id="baseline-exam-scope" v-model="form.examScope" required maxlength="5000" :disabled="busy" :placeholder="t('courseGeneration.exam.scopePlaceholder')" />
            </template>
          </section>

          <section class="form-section settings-grid">
            <fieldset>
              <legend>{{ t('courseFiles.workbench.difficulty') }}</legend>
              <div class="segmented-options segmented-options--three">
                <button v-for="item in difficultyOptions" :key="item.value" type="button" :class="{ active: form.difficulty === item.value }" :aria-pressed="form.difficulty === item.value" :disabled="busy" @click="form.difficulty = item.value">{{ item.label }}</button>
              </div>
            </fieldset>
            <label for="baseline-pedagogy"><span>{{ t('courseFiles.workbench.knowledgeStructure') }}</span><select id="baseline-pedagogy" v-model="form.pedagogyMode" :disabled="busy"><option v-for="item in pedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          </section>

          <section class="form-section settings-grid">
            <fieldset>
              <legend>{{ t('courseFiles.workbench.courseScale') }}</legend>
              <div class="two-column-fields">
                <label for="baseline-total-hours"><span>{{ t('teacherCourseCreate.totalHours') }}</span><input id="baseline-total-hours" v-model.number="form.totalClassHours" required type="number" min="1" max="1000" step="1" :disabled="busy" /></label>
                <label for="baseline-section-count"><span>{{ t('teacherCourseCreate.expectedSessions') }}</span><input id="baseline-section-count" v-model.number="form.sectionCount" required type="number" min="1" max="1000" step="1" :disabled="busy" /></label>
              </div>
            </fieldset>
            <fieldset>
              <legend>{{ t('courseFiles.workbench.productionMode') }}</legend>
              <div class="segmented-options">
                <button type="button" :class="{ active: form.productionMode === 'manual' }" :aria-pressed="form.productionMode === 'manual'" :disabled="busy" @click="form.productionMode = 'manual'">{{ t('teacherCourseCreate.productionModeManual') }}</button>
                <button type="button" :class="{ active: form.productionMode === 'automatic' }" :aria-pressed="form.productionMode === 'automatic'" :disabled="busy" @click="form.productionMode = 'automatic'">{{ t('teacherCourseCreate.productionModeAutomatic') }}</button>
              </div>
            </fieldset>
          </section>
        </form>

        <footer>
          <button class="secondary-button" type="button" :disabled="busy" @click="emit('discussAi')"><Sparkles :size="15" />{{ t('courseFiles.workbench.discussWithAi') }}</button>
          <span />
          <button class="secondary-button" type="button" :disabled="busy" @click="close">{{ t('common.cancel') }}</button>
          <button class="primary-button" type="button" :disabled="!canSubmit" @click="submit"><LoaderCircle v-if="busy" class="spin" :size="15" />{{ busy ? t('courseFiles.workbench.baselineSaving') : t('courseFiles.workbench.baselineSave') }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { BookOpen, Hammer, LoaderCircle, MessageCircleQuestion, SlidersHorizontal, Sparkles, Timer, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { PEDAGOGY_MODE_OPTIONS, type CourseGenerationOptions, type CourseType, type DifficultyLevel, type PedagogyModeSelection } from '../shared/prompt-config'

const props = withDefaults(defineProps<{
  modelValue: boolean
  busy?: boolean
  initialOptions?: CourseGenerationOptions & { subject?: string }
  contextKey?: string
  aiDraft?: boolean
}>(), { busy: false, initialOptions: () => ({}), contextKey: '', aiDraft: false })
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: { subject: string; options: CourseGenerationOptions }]
  discussAi: []
}>()
const titleId = `course-baseline-title-${Math.random().toString(36).slice(2)}`
const form = reactive({
  courseType: 'systematic' as CourseType,
  systematicGoal: '',
  projectGoal: '',
  expectedDeliverable: '',
  coreQuestion: '',
  desiredOutput: '',
  examName: '',
  examDate: '',
  examScope: '',
  difficulty: 'intermediate' as DifficultyLevel,
  pedagogyMode: 'auto' as PedagogyModeSelection,
  totalClassHours: 16,
  sectionCount: 8,
  productionMode: 'manual' as 'manual' | 'automatic',
})

const courseTypeOptions = computed(() => ([
  { value: 'systematic' as const, icon: BookOpen, label: t('courseGeneration.courseTypes.systematic.label'), detail: t('courseGeneration.courseTypes.systematic.detail') },
  { value: 'project' as const, icon: Hammer, label: t('courseGeneration.courseTypes.project.label'), detail: t('courseGeneration.courseTypes.project.detail') },
  { value: 'inquiry' as const, icon: MessageCircleQuestion, label: t('courseGeneration.courseTypes.inquiry.label'), detail: t('courseGeneration.courseTypes.inquiry.detail') },
  { value: 'exam' as const, icon: Timer, label: t('courseGeneration.courseTypes.exam.label'), detail: t('courseGeneration.courseTypes.exam.detail') },
]))
const difficultyOptions = computed(() => (['beginner', 'intermediate', 'advanced'] as const).map(value => ({ value, label: t(`courseGeneration.difficulty.${value}.label`) })))
const pedagogyOptions = computed(() => PEDAGOGY_MODE_OPTIONS.map(item => ({ value: item.value, label: t(item.labelKey) })))
const intentComplete = computed(() => ({
  systematic: Boolean(form.systematicGoal.trim()),
  project: Boolean(form.projectGoal.trim() && form.expectedDeliverable.trim()),
  inquiry: Boolean(form.coreQuestion.trim() && form.desiredOutput.trim()),
  exam: Boolean(form.examName.trim() && form.examDate && form.examScope.trim()),
})[form.courseType])
const canSubmit = computed(() => !props.busy && intentComplete.value
  && Number.isInteger(form.totalClassHours) && form.totalClassHours >= 1 && form.totalClassHours <= 1000
  && Number.isInteger(form.sectionCount) && form.sectionCount >= 1 && form.sectionCount <= 1000)

function hydrate() {
  const options = props.initialOptions || {}
  const intent = options.course_intent as Record<string, any> | undefined
  const brief = options.teacher_course_brief
  form.courseType = (['systematic', 'project', 'inquiry', 'exam'].includes(String(options.course_type)) ? options.course_type : intent?.type || 'systematic') as CourseType
  form.systematicGoal = String(intent?.type === 'systematic' ? intent.learning_goal || intent.desired_outcome || '' : '')
  form.projectGoal = String(intent?.type === 'project' ? intent.project_goal || '' : '')
  form.expectedDeliverable = String(intent?.type === 'project' ? intent.expected_deliverable || '' : '')
  form.coreQuestion = String(intent?.type === 'inquiry' ? intent.core_question || '' : '')
  form.desiredOutput = String(intent?.type === 'inquiry' ? intent.desired_output || '' : '')
  form.examName = String(intent?.type === 'exam' ? intent.exam_name || '' : '')
  form.examDate = String(intent?.type === 'exam' ? intent.exam_date || '' : '')
  form.examScope = String(intent?.type === 'exam' ? intent.exam_scope || '' : '')
  form.difficulty = (['beginner', 'intermediate', 'advanced'].includes(String(options.difficulty)) ? options.difficulty : 'intermediate') as DifficultyLevel
  form.pedagogyMode = (options.pedagogy_mode || 'auto') as PedagogyModeSelection
  form.totalClassHours = Number(brief?.total_class_hours || 16)
  form.sectionCount = Number(brief?.section_count || 8)
  form.productionMode = options.production_mode === 'automatic' ? 'automatic' : 'manual'
}

function close() {
  if (!props.busy) emit('update:modelValue', false)
}

function submit() {
  if (!canSubmit.value) return
  const current = props.initialOptions || {}
  const currentBrief = current.teacher_course_brief
  const audience = currentBrief?.target_audience || current.target_audience || t('courseGeneration.teacherBrief.defaultAudience')
  const subject = String(current.subject || '').trim()
  const courseIntent = form.courseType === 'project'
    ? { schema_version: 'course_intent_v1' as const, type: 'project' as const, project_goal: form.projectGoal.trim(), expected_deliverable: form.expectedDeliverable.trim(), prior_experience: current.course_intent?.type === 'project' ? current.course_intent.prior_experience || '' : '', current_uncertainty: current.course_intent?.type === 'project' ? current.course_intent.current_uncertainty || '' : '', project_constraints: current.course_intent?.type === 'project' ? current.course_intent.project_constraints || '' : '' }
    : form.courseType === 'inquiry'
      ? { schema_version: 'course_intent_v1' as const, type: 'inquiry' as const, core_question: form.coreQuestion.trim(), desired_output: form.desiredOutput.trim(), existing_understanding: current.course_intent?.type === 'inquiry' ? current.course_intent.existing_understanding || '' : '', evidence_scope: current.course_intent?.type === 'inquiry' ? current.course_intent.evidence_scope || '' : '' }
      : form.courseType === 'exam'
        ? { schema_version: 'course_intent_v1' as const, type: 'exam' as const, exam_name: form.examName.trim(), exam_date: form.examDate, exam_scope: form.examScope.trim(), current_preparation: current.course_intent?.type === 'exam' ? current.course_intent.current_preparation || '' : '' }
        : { schema_version: 'course_intent_v1' as const, type: 'systematic' as const, learning_goal: form.systematicGoal.trim(), desired_outcome: current.course_intent?.type === 'systematic' ? current.course_intent.desired_outcome || '' : '', existing_foundation: current.course_intent?.type === 'systematic' ? current.course_intent.existing_foundation || '' : '' }
  const nextSubject = form.courseType === 'project' ? form.projectGoal.trim()
    : form.courseType === 'inquiry' ? form.coreQuestion.trim()
      : form.courseType === 'exam' ? form.examName.trim()
        : subject || form.systematicGoal.trim()
  emit('save', {
    subject: nextSubject,
    options: {
      ...current,
      difficulty: form.difficulty,
      course_type: form.courseType,
      course_intent: courseIntent,
      composition_style: ({ systematic: 'balanced', project: 'project_driven', inquiry: 'inquiry_driven', exam: 'example_driven' } as const)[form.courseType],
      course_purpose: form.courseType === 'exam' ? 'exam_sprint' : 'systematic',
      pedagogy_mode: form.pedagogyMode,
      production_mode: form.productionMode,
      target_audience: audience,
      teacher_course_brief: {
        ...(currentBrief || {}),
        schema_version: 'teacher_course_brief_v1',
        target_audience: audience,
        total_class_hours: form.totalClassHours,
        lesson_duration_minutes: currentBrief?.lesson_duration_minutes || 45,
        teaching_context: currentBrief?.teaching_context || 'classroom',
        section_count: form.sectionCount,
      },
    },
  })
}

watch(() => [props.modelValue, props.contextKey], ([open]) => { if (open) hydrate() }, { immediate: true })
</script>

<style scoped>
.baseline-dialog-layer{position:fixed;inset:0;z-index:530;display:grid;place-items:center;padding:24px}.baseline-dialog-backdrop{position:absolute;inset:0;border:0;background:rgba(30,41,59,.38)}.baseline-dialog{position:relative;width:min(900px,100%);max-height:calc(100dvh - 48px);display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;border:1px solid var(--lz-border);border-radius:16px;color:var(--lz-text);background:#fff;box-shadow:0 24px 72px rgba(15,23,42,.24)}.baseline-dialog>header{min-height:68px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:0 18px;border-bottom:1px solid #edf0f5}.baseline-dialog__mark{width:38px;height:38px;display:grid;place-items:center;border-radius:12px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.baseline-dialog h2{margin:0;color:#29256f;font-size:20px}.baseline-dialog header p{margin:3px 0 0;color:var(--lz-text-muted);font-size:12px}.icon-button{width:36px;height:36px;display:grid;place-items:center;border:0;border-radius:9px;color:var(--lz-text-secondary);background:transparent;cursor:pointer}.icon-button:hover{background:var(--lz-surface-muted)}.baseline-dialog__body{min-height:0;overflow:auto;padding:0 28px}.form-section{min-width:0;margin:0;padding:18px 0;border:0;border-bottom:1px solid #edf0f5}.form-section>legend,.form-section>label,.settings-grid legend,.settings-grid label>span{display:block;margin-bottom:10px;color:var(--lz-text);font-size:12px;font-weight:800}.course-type-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.course-type-options button{min-width:0;min-height:78px;display:flex;align-items:flex-start;gap:9px;padding:12px;border:1px solid var(--lz-border);border-radius:10px;color:var(--lz-text-secondary);background:#fff;text-align:left;cursor:pointer}.course-type-options button.active,.segmented-options button.active{border-color:var(--lz-brand);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-type-options svg{flex:none;margin-top:1px}.course-type-options span{min-width:0;display:grid;gap:4px}.course-type-options strong{font-size:12px}.course-type-options small{color:var(--lz-text-muted);font-size:12px;line-height:1.45}.intent-fields{display:grid;gap:10px}.intent-fields>label{margin:0}.intent-fields textarea{min-height:78px}.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px}.settings-grid fieldset{min-width:0;margin:0;padding:0;border:0}.segmented-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.segmented-options--three{grid-template-columns:repeat(3,minmax(0,1fr))}.segmented-options button{min-height:42px;padding:7px 9px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:#fff;font-size:12px;font-weight:700;cursor:pointer}.two-column-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.two-column-fields label{display:grid;gap:8px;color:var(--lz-text);font-size:12px;font-weight:750}.two-column-fields label span{margin:0}.baseline-dialog input,.baseline-dialog select,.baseline-dialog textarea{width:100%;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-strong);background:#fff;outline:none}.baseline-dialog input,.baseline-dialog select{height:42px;padding:0 11px}.baseline-dialog textarea{padding:10px 12px;resize:vertical;font-size:12px;line-height:1.55}.baseline-dialog input:focus,.baseline-dialog select:focus,.baseline-dialog textarea:focus{border-color:var(--lz-brand);box-shadow:0 0 0 3px rgba(99,102,241,.1)}.ai-draft-notice{display:flex;align-items:flex-start;gap:9px;margin-top:18px;padding:11px 12px;border:1px solid rgba(99,102,241,.2);border-radius:10px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:12px;line-height:1.55}.ai-draft-notice svg{flex:none;margin-top:1px}.baseline-dialog>footer{min-height:64px;display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:8px;padding:10px 18px;border-top:1px solid #edf0f5;background:#fbfcff}.primary-button,.secondary-button{min-height:40px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border-radius:8px;font-size:12px;font-weight:750;cursor:pointer}.primary-button{border:1px solid var(--lz-brand-strong);color:#fff;background:var(--lz-brand-strong)}.secondary-button{border:1px solid var(--lz-border);color:var(--lz-text-secondary);background:#fff}.primary-button:disabled,.secondary-button:disabled,.course-type-options button:disabled,.segmented-options button:disabled{cursor:not-allowed;opacity:.55}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.baseline-dialog-layer{align-items:end;padding:0}.baseline-dialog{max-height:calc(100dvh - 20px);border-radius:18px 18px 0 0}.baseline-dialog>header{padding:0 14px}.baseline-dialog h2{font-size:18px}.baseline-dialog header p{display:none}.baseline-dialog__body{padding:0 16px}.course-type-options{grid-template-columns:repeat(2,minmax(0,1fr))}.course-type-options button{min-height:64px}.course-type-options small{display:none}.settings-grid{grid-template-columns:1fr;gap:18px}.baseline-dialog>footer{grid-template-columns:1fr 1fr;padding:10px 16px 14px}.baseline-dialog>footer>span{display:none}.baseline-dialog>footer button{width:100%}.baseline-dialog>footer .secondary-button:first-child{grid-column:1/-1}}
</style>
