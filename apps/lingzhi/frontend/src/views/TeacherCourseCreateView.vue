<template>
  <Teleport to="body">
    <dialog ref="dialogRef" class="course-create-dialog" :aria-labelledby="titleId" @cancel.prevent="closeCourseCreate" @keydown.esc.prevent.stop="closeCourseCreate">
      <form class="course-form" @submit.prevent="createCourse">
        <header class="form-heading">
          <div><h2 :id="titleId">{{ t('teacherCourseCreate.title') }}</h2><p>{{ t('courseCreationFlow.help') }}</p></div>
          <button type="button" :aria-label="t('common.close')" :disabled="creating" @click="closeCourseCreate"><X :size="18" /></button>
        </header>
        <ol class="creation-steps" :aria-label="t('courseCreationFlow.stepsLabel')">
          <li v-for="(label, index) in stepLabels" :key="index" :class="{ active: step === index, complete: step > index }" :aria-current="step === index ? 'step' : undefined"><span>{{ index + 1 }}</span><strong>{{ label }}</strong></li>
        </ol>
        <fieldset class="form-scroll" :disabled="creating || Boolean(createdCourseId)">
          <p v-if="creationError" class="creation-error" role="alert">{{ creationError }}</p>
          <section v-if="step === 0" class="creation-section">
            <header><h3>{{ t('courseCreationFlow.goalTitle') }}</h3><p>{{ t('courseCreationFlow.goalHelp') }}</p></header>
            <div class="details-grid">
              <label class="field field--wide" for="course-name"><span>{{ t('teacherCourseCreate.courseName') }} <b>*</b></span><input id="course-name" v-model.trim="form.courseName" required maxlength="200" autofocus :placeholder="t('teacherCourseCreate.courseNamePlaceholder')" /></label>
              <label class="field" for="target-grade"><span>{{ t('teacherCourseCreate.targetGrade') }} <b>*</b></span><select id="target-grade" v-model="form.targetGrade" required><option v-for="option in targetAudienceOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label class="field" for="course-category"><span>{{ t('teacherCourseCreate.courseCategory') }} <b>*</b></span><select id="course-category" v-model="form.courseCategory" required><option value="" disabled>{{ t('teacherCourseCreate.selectPlaceholder') }}</option><option v-for="option in courseCategoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label class="field field--wide" for="course-goal"><span>{{ t('courseCreationFlow.learningGoal') }} <b>*</b></span><textarea id="course-goal" v-model.trim="form.learningGoal" rows="3" maxlength="4000" required :placeholder="t('courseCreationFlow.goalPlaceholder')" /></label>
              <label class="field" for="course-subject-type"><span>{{ t('courseWorkbench.form.subjectType') }}</span><select id="course-subject-type" v-model="form.subjectType"><option v-for="option in subjectTypeOptions" :key="option.value" :value="option.value">{{ t(option.labelKey) }}</option></select></label>
              <label class="field" for="prerequisites"><span>{{ t('teacherCourseCreate.prerequisiteCourses') }}</span><input id="prerequisites" v-model.trim="form.prerequisiteCourses" maxlength="1000" :placeholder="t('teacherCourseCreate.prerequisitePlaceholder')" /></label>
              <label class="field field--wide" for="course-requirements"><span>{{ t('courseWorkbench.form.requirements') }}</span><textarea id="course-requirements" v-model.trim="form.requirements" rows="2" maxlength="4000" :placeholder="t('courseWorkbench.form.requirementsPlaceholder')" /></label>
            </div>
          </section>
          <section v-else-if="step === 1" class="creation-section">
            <header><h3>{{ t('courseCreationFlow.scheduleTitle') }}</h3><p>{{ t('courseCreationFlow.scheduleHelp') }}</p></header>
            <div class="details-grid">
              <label class="field" for="planned-lecture-count"><span>{{ t('teacherCourseCreate.plannedLectures') }} <b>*</b></span><input id="planned-lecture-count" v-model.number="form.plannedLectureCount" type="number" min="1" max="1000" required /></label>
              <label class="field" for="total-hours"><span>{{ t('courseWorkbench.form.totalHours') }} <b>*</b></span><input id="total-hours" v-model.number="form.totalHours" type="number" min="1" max="1000" required /></label>
              <label class="field" for="academic-year"><span>{{ t('teacherCourseCreate.academicYear') }}</span><input id="academic-year" v-model.trim="form.academicYear" maxlength="30" /></label>
              <label class="field" for="term"><span>{{ t('teacherCourseCreate.term') }} <b>*</b></span><select id="term" v-model="form.term" required><option value="春夏">{{ t('teacherCourseCreate.springSummer') }}</option><option value="秋冬">{{ t('teacherCourseCreate.autumnWinter') }}</option><option value="春">{{ t('teacherCourseCreate.spring') }}</option><option value="夏">{{ t('teacherCourseCreate.summer') }}</option><option value="秋">{{ t('teacherCourseCreate.autumn') }}</option><option value="冬">{{ t('teacherCourseCreate.winter') }}</option><option value="暑期课">{{ t('teacherCourseCreate.summerCourse') }}</option><option value="寒期课">{{ t('teacherCourseCreate.winterCourse') }}</option></select></label>
            </div>
            <div class="creation-relation"><BookOpenText :size="20" /><div><strong>{{ t('courseCreationFlow.hierarchy') }}</strong><p>{{ t('courseCreationFlow.hierarchyHelp') }}</p></div></div>
            <details class="schedule-details"><summary>{{ t('courseCreationFlow.scheduleOptional') }}</summary><div class="details-grid">
              <label class="field" for="course-english-name"><span>{{ t('teacherCourseCreate.englishName') }}</span><input id="course-english-name" v-model.trim="form.englishName" maxlength="200" /></label>
              <label class="field" for="course-code"><span>{{ t('teacherCourseCreate.courseCode') }}</span><input id="course-code" v-model.trim="form.courseCode" maxlength="64" /></label>
              <label class="field" for="credits"><span>{{ t('teacherCourseCreate.credits') }}</span><input id="credits" v-model.number="form.credits" type="number" min="0.5" max="100" step="0.5" /></label>
              <label class="field" for="weekly-hours"><span>{{ t('teacherCourseCreate.weeklyHours') }}</span><input id="weekly-hours" v-model.number="form.weeklyHours" type="number" min="0.5" max="100" step="0.5" /></label>
              <div class="week-range-setting field--wide"><div><span>{{ t('teacherCourseCreate.activeWeeks') }}</span><strong>{{ teachingWeekSummary }}</strong></div><button v-if="automaticWeekRange" type="button" @click="toggleWeekRangeMode">{{ form.weekRangeMode === 'custom' ? t('teacherCourseCreate.useAcademicCalendar') : t('teacherCourseCreate.customizeWeeks') }}</button></div>
              <template v-if="form.weekRangeMode === 'custom'"><label class="field" for="active-week-start"><span>{{ t('teacherCourseCreate.activeWeekStart') }}</span><input id="active-week-start" v-model.number="form.activeWeekStart" type="number" min="1" max="30" /></label><label class="field" for="active-week-end"><span>{{ t('teacherCourseCreate.activeWeekEnd') }}</span><input id="active-week-end" v-model.number="form.activeWeekEnd" type="number" min="1" max="30" /></label></template>
              <ZjuCourseScheduleGrid v-model="form.scheduleSlots" />
              <p class="schedule-suggestion field--wide">{{ scheduleSuggestionText }} <button v-if="suggestedLectureCount && suggestedLectureCount !== form.plannedLectureCount" class="apply-suggestion" type="button" @click="form.plannedLectureCount = suggestedLectureCount">{{ t('teacherCourseCreate.applyLectureSuggestion') }}</button></p>
              <label class="field field--wide" for="location"><span>{{ t('teacherCourseCreate.classLocation') }}</span><input id="location" v-model.trim="form.defaultLocation" maxlength="200" /></label>
            </div></details>
          </section>
          <section v-else class="creation-section">
            <header><h3>{{ t('courseCreationFlow.sourceTitle') }}</h3><p>{{ t('courseCreationFlow.sourceHelp') }}</p></header>
            <div class="source-options"><button v-for="option in sourceOptions" :key="option.value" type="button" :aria-pressed="form.startMode === option.value" :class="{ selected: form.startMode === option.value }" @click="form.startMode = option.value"><component :is="option.icon" :size="26" /><strong>{{ option.label }}</strong><span>{{ option.help }}</span><Check v-if="form.startMode === option.value" :size="18" class="source-check" /></button></div>
            <dl class="creation-summary"><div><dt>{{ t('teacherCourseCreate.courseName') }}</dt><dd>{{ form.courseName }}</dd></div><div><dt>{{ t('courseCreationFlow.learningGoal') }}</dt><dd>{{ form.learningGoal }}</dd></div><div><dt>{{ t('courseCreationFlow.scheduleTitle') }}</dt><dd>{{ t('courseCreationFlow.summaryHours').replace('{lectures}', String(form.plannedLectureCount)).replace('{hours}', String(form.totalHours)) }}</dd></div></dl>
            <p class="creation-next"><ArrowRight :size="18" />{{ t(form.startMode === 'materials' ? 'courseCreationFlow.nextMaterials' : 'courseCreationFlow.nextBlank') }}</p>
          </section>
        </fieldset>
        <footer class="form-footer"><span>{{ t('courseCreationFlow.noAutoGeneration') }}</span><div class="form-actions"><button type="button" :disabled="creating" @click="createdCourseId || !step ? closeCourseCreate() : step--">{{ createdCourseId ? t('courseFiles.backToCourses') : step ? t('common.back') : t('common.cancel') }}</button><button v-if="step < 2" type="button" class="primary" @click="nextStep">{{ t('courseCreationFlow.next') }}<ArrowRight :size="16" /></button><button v-else type="submit" class="primary" :disabled="creating || !creationReady"><LoaderCircle v-if="creating" :size="16" class="spin" />{{ creating ? t('courseCreationFlow.creating') : createdCourseId ? t('courseCreationFlow.openSavedCourse') : t('courseCreationFlow.createAndPrepare') }}</button></div></footer>
      </form>
    </dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, BookOpenText, Check, FilePlus2, FolderInput, LoaderCircle, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { PEDAGOGY_MODE_OPTIONS, type PedagogyModeSelection } from '../shared/prompt-config'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import ZjuCourseScheduleGrid, { type CourseScheduleSlot } from '../components/ZjuCourseScheduleGrid.vue'
import { zjuTeachingWeekRange, type WeekRangeMode } from '../utils/zju-academic-calendar'

const emit = defineEmits<{ (event: 'close'): void }>()
const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const dialogRef = ref<HTMLDialogElement | null>(null)
const creating = ref(false)
const createdCourseId = ref('')
const titleId = 'teacher-course-create-title'
const step = ref(0)
const creationError = ref('')
const stepLabels = computed(() => [t('courseCreationFlow.steps.goal'), t('courseCreationFlow.steps.schedule'), t('courseCreationFlow.steps.source')])
const subjectTypeOptions = PEDAGOGY_MODE_OPTIONS
const sourceOptions = computed(() => [
  { value: 'blank' as const, label: t('courseFiles.preparation.blankMode'), help: t('courseCreationFlow.blankHelp'), icon: FilePlus2 },
  { value: 'materials' as const, label: t('courseFiles.preparation.existingMode'), help: t('courseCreationFlow.materialsHelp'), icon: FolderInput },
])
const creationReady = computed(() => Boolean(form.courseName.trim() && form.learningGoal.trim() && form.courseCategory && form.targetGrade && form.term && Number(form.plannedLectureCount) >= 1 && Number(form.totalHours) >= 1 && form.activeWeekEnd >= form.activeWeekStart))
function nextStep() {
  if (!dialogRef.value?.querySelector<HTMLFormElement>('form')?.reportValidity()) return
  step.value = Math.min(2, step.value + 1)
}
const now = new Date()
const academicStartYear = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
const targetAudienceOptions = computed(() => [
  { value: '本科生', label: t('teacherCourseCreate.undergraduate') },
  { value: '研究生', label: t('teacherCourseCreate.postgraduate') },
  { value: '本研混合', label: t('teacherCourseCreate.audienceMixed') },
  { value: '继续教育', label: t('teacherCourseCreate.continuingEducation') },
])
const courseCategoryOptions = computed(() => [
  { value: '通识必修课', label: t('teacherCourseCreate.generalRequired') },
  { value: '通识选修课', label: t('teacherCourseCreate.generalElective') },
  { value: '专业基础课', label: t('teacherCourseCreate.majorFoundation') },
  { value: '专业必修课', label: t('teacherCourseCreate.majorRequired') },
  { value: '专业选修课', label: t('teacherCourseCreate.majorElective') },
  { value: '实践课', label: t('teacherCourseCreate.practicalCourse') },
])
const form = reactive({
  courseName: '', englishName: '', targetGrade: '本科生', courseCategory: '', courseCode: '',
  credits: 2, weeklyHours: 2, totalHours: 32,
  prerequisiteCourses: '', academicYear: `${academicStartYear}-${academicStartYear + 1}`, term: now.getMonth() >= 7 ? '秋冬' : '春夏', defaultLocation: '',
  learningGoal: '', requirements: '', subjectType: 'auto' as PedagogyModeSelection, startMode: 'blank' as 'blank' | 'materials',
  activeWeekStart: 1, activeWeekEnd: 16, weekRangeMode: 'academic_calendar' as WeekRangeMode,
  scheduleSlots: [] as CourseScheduleSlot[], plannedLectureCount: 6,
})

const automaticWeekRange = computed(() => zjuTeachingWeekRange(form.term))
const teachingWeekSummary = computed(() => {
  if (!form.term) return t('teacherCourseCreate.selectTermForWeeks', '选择学期后自动确定')
  if (form.weekRangeMode === 'academic_calendar' && automaticWeekRange.value) {
    return t('teacherCourseCreate.academicCalendarWeeks', '按浙大校历：第 {start}–{end} 教学周')
      .replace('{start}', String(automaticWeekRange.value.start))
      .replace('{end}', String(automaticWeekRange.value.end))
  }
  return t('teacherCourseCreate.customWeeksValue', '自定义：第 {start}–{end} 周')
    .replace('{start}', String(form.activeWeekStart))
    .replace('{end}', String(form.activeWeekEnd))
})

function applyAutomaticWeekRange() {
  const range = automaticWeekRange.value
  if (!range) return false
  form.weekRangeMode = 'academic_calendar'
  form.activeWeekStart = range.start
  form.activeWeekEnd = range.end
  return true
}

function toggleWeekRangeMode() {
  if (form.weekRangeMode === 'custom') {
    applyAutomaticWeekRange()
  } else {
    form.weekRangeMode = 'custom'
  }
}

const weeklySessionCount = computed(() => {
  const byDay = new Map<number, number[]>()
  for (const slot of form.scheduleSlots) byDay.set(slot.weekday, [...(byDay.get(slot.weekday) || []), slot.period])
  let count = 0
  for (const periods of byDay.values()) {
    periods.sort((a, b) => a - b)
    periods.forEach((period, index) => { if (index === 0 || period !== periods[index - 1]! + 1) count += 1 })
  }
  return count
})
const suggestedLectureCount = computed(() => weeklySessionCount.value * Math.max(0, form.activeWeekEnd - form.activeWeekStart + 1))
const scheduleSuggestionText = computed(() => suggestedLectureCount.value
  ? t('teacherCourseCreate.lectureSuggestion', '按已选课表建议 {count} 讲；可按实际教学安排修改').replace('{count}', String(suggestedLectureCount.value))
  : t('teacherCourseCreate.lectureSuggestionEmpty', '选择课表后会给出建议，最终讲数仍由老师确定'))
watch(() => [form.scheduleSlots.length, form.activeWeekStart, form.activeWeekEnd], () => {
  if (!form.scheduleSlots.length) return
  form.weeklyHours = form.scheduleSlots.length
  form.totalHours = form.scheduleSlots.length * Math.max(0, form.activeWeekEnd - form.activeWeekStart + 1)
})
watch(() => form.term, () => {
  if (!applyAutomaticWeekRange()) form.weekRangeMode = 'custom'
})
watch(() => [form.weeklyHours, form.activeWeekStart, form.activeWeekEnd], () => {
  if (form.scheduleSlots.length) return
  form.totalHours = Number(form.weeklyHours) * Math.max(0, form.activeWeekEnd - form.activeWeekStart + 1)
})

function closeCourseCreate() {
  if (creating.value) return
  if (dialogRef.value?.open) dialogRef.value.close()
  emit('close')
}

async function createCourse() {
  if (
    creating.value
    || !creationReady.value
    || !form.term
    || form.activeWeekEnd < form.activeWeekStart
    || Number(form.plannedLectureCount) < 1
  ) return
  creating.value = true
  creationError.value = ''
  const totalHours = Number(form.totalHours || 32)
  try {
    if (!createdCourseId.value) {
    const result = await courseStore.createTeacherCourseSpace({
      course_name: form.courseName, english_name: form.englishName, academic_year: form.academicYear, term: form.term,
      course_code: form.courseCode, target_grade: form.targetGrade,
      course_category: form.courseCategory, credits: Number(form.credits), weekly_hours: Number(form.weeklyHours),
      total_hours: form.totalHours, prerequisite_courses: form.prerequisiteCourses,
      active_week_start: form.activeWeekStart, active_week_end: form.activeWeekEnd,
      week_range_mode: form.weekRangeMode,
      schedule_slots: form.scheduleSlots, planned_lecture_count: Number(form.plannedLectureCount),
      default_location: form.defaultLocation,
      generation_request: {
        subject: form.courseName, target_audience: form.targetGrade || '大学生', difficulty: 'intermediate',
        learning_purpose: 'systematic',
        course_teaching_type: 'comprehensive',
        pedagogy_mode: form.subjectType,
        course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: form.learningGoal },
        requirements: form.requirements,
        production_mode: 'manual', teacher_course_brief: {
          schema_version: 'teacher_course_brief_v1', academic_term: [form.academicYear, form.term].filter(Boolean).join(' '),
          target_audience: form.targetGrade || '大学生', total_class_hours: totalHours,
          lesson_duration_minutes: 45,
          course_period_minutes: 45,
          lecture_count: Number(form.plannedLectureCount),
          additional_requirements: form.requirements,
        }, teacher_authoring_mode: 'lesson_assets_v1',
      },
    })
    createdCourseId.value = result.course_id
    }
    await courseStore.fetchCourseList({ surface: 'teacher' }).catch(() => undefined)
    await router.push({
      name: 'course-workspace',
      params: { courseId: createdCourseId.value, mode: 'setup' },
      query: { returnTo: '/courses?view=courses', prepare: form.startMode, stage: 'foundation' },
    })
  } catch (error: any) {
    creationError.value = createdCourseId.value ? t('courseCreationFlow.savedEntryFailed') : String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed'))
  } finally { creating.value = false }
}

onMounted(() => { applyAutomaticWeekRange(); dialogRef.value?.showModal() })
onBeforeUnmount(() => { if (dialogRef.value?.open) dialogRef.value.close() })
</script>

<style scoped>
.course-create-dialog{width:min(900px,calc(100vw - 32px));max-width:none;height:min(780px,calc(100dvh - 40px));max-height:none;margin:auto;padding:0;overflow:hidden;border:1px solid #dfe5ee;border-radius:16px;color:var(--lz-text-primary);background:#fff;box-shadow:0 28px 72px rgba(15,23,42,.24);animation:course-create-dialog-in .24s cubic-bezier(.16,1,.3,1)}
.course-create-dialog::backdrop{background:rgba(15,23,42,.42);animation:course-create-backdrop-in .18s ease-out}
@keyframes course-create-dialog-in{from{opacity:0;transform:translateY(10px) scale(.992)}to{opacity:1;transform:none}}
@keyframes course-create-backdrop-in{from{background:rgba(15,23,42,0)}to{background:rgba(15,23,42,.42)}}
.course-form{height:100%;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;background:#fff}
.form-heading{min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 30px;border-bottom:1px solid #e8edf4}
.form-heading>div{min-width:0;display:grid;gap:6px}.form-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.02em}.form-heading p{margin:0;color:#64748b;font-size:15px}
.form-heading>button{width:36px;height:36px;flex:none;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.form-heading>button:hover{color:#334155;background:#f1f5f9}.form-heading>button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.form-scroll{min-height:0;overflow:auto;overscroll-behavior:contain}
.identity-section{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:24px 30px 26px}.identity-section .field--name{grid-column:1/-1}
.field{min-width:0;display:grid;gap:7px}.field>span{color:#334155;font-size:15px;font-weight:700}.field b{color:#dc2626}
.field input,.field select,.field textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:15px}.field textarea{resize:vertical;line-height:1.6}.field input:focus,.field select:focus,.field textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.field--name input{min-height:48px;font-size:15px}
.course-details{border-top:1px solid #e8edf4}.details-heading{min-height:56px;display:flex;align-items:center;gap:9px;padding:0 30px}.details-heading strong{color:#334155;font-size:15px}.details-heading small{padding:3px 7px;border-radius:5px;color:#64748b;background:#f1f5f9;font-size:11px;font-weight:650}
.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:0 30px 30px}.field--wide{grid-column:1/-1}
.lecture-plan{display:flex;align-items:end;justify-content:space-between;gap:24px;padding:14px 16px;border:1px solid #e3e8f0;border-radius:10px;background:#f8fafc}.lecture-plan>div{display:grid;gap:5px}.lecture-plan strong{color:#334155;font-size:15px}.lecture-plan>div span{color:#64748b;font-size:12px}.lecture-plan .field{width:150px;flex:none}.apply-suggestion{justify-self:start;padding:2px 0;border:0;color:#514bdc;background:transparent;font:inherit;font-size:12px;font-weight:750;cursor:pointer}.apply-suggestion:focus-visible{outline:2px solid #514bdc;outline-offset:3px;border-radius:3px}
.week-range-setting{min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:9px 0;border-bottom:1px solid #e8edf4}.week-range-setting>div{display:grid;gap:4px}.week-range-setting span{color:#64748b;font-size:11px}.week-range-setting strong{color:#334155;font-size:15px}.week-range-setting button{padding:4px 0;border:0;color:#514bdc;background:transparent;font:inherit;font-size:12px;font-weight:750;cursor:pointer}.week-range-setting button:focus-visible{outline:2px solid #514bdc;outline-offset:3px;border-radius:3px}
.form-footer{min-height:76px;display:flex;align-items:center;justify-content:flex-end;gap:20px;padding:14px 30px;border-top:1px solid #e8edf4;background:#fbfcfe}.form-actions{display:flex;gap:9px}.form-actions button{min-height:40px;padding:0 15px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:15px;font-weight:700;cursor:pointer}.form-actions button.primary{min-width:132px;border-color:#514bdc;color:#fff;background:#514bdc;box-shadow:0 7px 18px rgba(81,75,220,.18)}.form-actions button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:680px){.course-create-dialog{width:calc(100vw - 16px);height:calc(100dvh - 16px);border-radius:12px}.form-heading{min-height:82px;padding:18px 20px}.form-heading h2{font-size:21px}.identity-section{grid-template-columns:1fr;padding:20px}.identity-section .field--name{grid-column:auto}.details-heading{padding-inline:20px}.details-grid{grid-template-columns:1fr;padding:0 20px 24px}.field--wide{grid-column:auto}.lecture-plan{align-items:stretch;flex-direction:column}.lecture-plan .field{width:100%}.form-footer{min-height:0;align-items:stretch;flex-direction:column;padding:14px 20px}.form-actions{display:grid;grid-template-columns:auto 1fr}.form-actions button.primary{min-width:0}}
@media(prefers-reduced-motion:reduce){.course-create-dialog,.course-create-dialog::backdrop,.spin{animation:none}}
</style>

<style scoped>
.form-scroll{margin:0;border:0;padding:24px 30px;min-width:0}.creation-steps{display:flex;gap:18px;list-style:none;margin:0;padding:18px 30px;border-bottom:1px solid #e8edf4;background:#fafaff}.creation-steps li{flex:1;display:flex;align-items:center;gap:9px;color:#79859a;font-size:15px}.creation-steps li>span{width:27px;height:27px;display:grid;place-items:center;border-radius:50%;background:#edf0f5;font-weight:700}.creation-steps li.active,.creation-steps li.complete{color:#5a4bc6}.creation-steps li.active>span{background:#6551c7;color:#fff}.creation-steps li.complete>span{background:#ebe7fa}.creation-section{display:grid;gap:22px}.creation-section>header{display:grid;gap:7px}.creation-section h3{margin:0;font-size:20px;color:#202a40}.creation-section>header p,.creation-relation p{margin:0;color:#738096;font-size:15px;line-height:1.6}.creation-section textarea{width:100%;resize:vertical;min-height:72px;padding:11px;border:1px solid #dce1ed;border-radius:9px;font:inherit;font-size:15px;line-height:1.65;outline:0}.creation-section textarea:focus{border-color:#6551c7;box-shadow:0 0 0 3px #6551c714}.creation-relation{display:flex;gap:12px;padding:17px;border:1px solid #e4e0f3;border-radius:12px;background:#f8f6ff;color:#6352b6}.creation-relation svg{flex:none;margin-top:3px}.creation-relation strong{display:block;margin-bottom:6px;font-size:15px}.schedule-details{border-top:1px solid #e6eaf1;padding-top:16px}.schedule-details summary{cursor:pointer;font-size:15px;font-weight:700;color:#55617a}.schedule-details .details-grid{padding-top:22px}.schedule-suggestion{font-size:15px;line-height:1.6;color:#728097}.source-options{display:grid;grid-template-columns:1fr 1fr;gap:16px}.source-options>button{position:relative;display:grid;align-content:start;gap:12px;min-height:175px;padding:22px;text-align:left;border:1px solid #dce1ed;border-radius:12px;background:#fff;font:inherit;font-size:15px;cursor:pointer}.source-options>button.selected{border-color:#7964d8;background:#f9f7ff;box-shadow:0 0 0 2px #7964d81a}.source-options>button>svg{color:#6551c7}.source-options strong{font-size:18px;color:#29344a}.source-options span{color:#748096;line-height:1.6}.source-check{position:absolute;right:17px;top:17px}.creation-summary{display:grid;gap:14px;margin:0;padding:18px 20px;border:1px solid #e7eaf0;border-radius:12px}.creation-summary>div{display:grid;grid-template-columns:100px minmax(0,1fr);gap:14px;font-size:15px;line-height:1.6}.creation-summary dt{color:#778398}.creation-summary dd{margin:0;color:#334155;overflow-wrap:anywhere}.creation-next{display:flex;align-items:start;gap:10px;margin:0;color:#6652b4;font-size:15px;line-height:1.6}.creation-next svg{flex:none;margin-top:3px}.creation-error{padding:14px;border-radius:8px;color:#a33248;background:#fff1f3;font-size:15px}.form-footer{justify-content:space-between;gap:16px}.form-footer>span{max-width:50%;color:#7b8698;font-size:15px;line-height:1.6}.creation-section button:focus-visible{outline:3px solid #b9a8ee;outline-offset:3px}
</style>
