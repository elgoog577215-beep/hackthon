<template>
  <Teleport to="body">
    <dialog
      ref="dialogRef"
      class="course-create-dialog"
      :aria-labelledby="titleId"
      @cancel.prevent="closeCourseCreate"
      @keydown.esc.prevent.stop="closeCourseCreate"
    >
      <form class="course-form" @submit.prevent="createCourse">
        <header class="form-heading">
          <div>
            <h2 :id="titleId">{{ t('teacherCourseCreate.title') }}</h2>
            <p>{{ t('teacherCourseCreate.simpleHelp') }}</p>
          </div>
          <button type="button" :aria-label="t('common.close')" @click="closeCourseCreate">
            <X :size="18" />
          </button>
        </header>

        <div class="form-scroll">
          <section class="identity-section">
            <label class="field field--name" for="course-name">
              <span>{{ t('teacherCourseCreate.courseName') }}{{ t('teacherCourseCreate.chineseNameSuffix') }} <b aria-hidden="true">*</b></span>
              <input id="course-name" v-model.trim="form.courseName" required maxlength="200" autofocus :placeholder="t('teacherCourseCreate.courseNamePlaceholder')" />
            </label>
            <label class="field" for="course-english-name"><span>{{ t('teacherCourseCreate.englishName') }}</span><input id="course-english-name" v-model.trim="form.englishName" maxlength="200" /></label>
          </section>

          <section class="course-details" :aria-labelledby="basicInfoId">
            <header class="details-heading">
              <strong :id="basicInfoId">{{ t('teacherCourseCreate.basicInfo') }}</strong>
              <small>{{ t('teacherCourseCreate.requiredHint') }}</small>
            </header>
            <div class="details-grid">
              <label class="field" for="target-grade"><span>{{ t('teacherCourseCreate.targetGrade') }} <b>*</b></span><select id="target-grade" v-model="form.targetGrade" required><option v-for="option in targetAudienceOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label class="field" for="course-category"><span>{{ t('teacherCourseCreate.courseCategory') }} <b>*</b></span><select id="course-category" v-model="form.courseCategory" required><option value="" disabled>{{ t('teacherCourseCreate.selectPlaceholder') }}</option><option v-for="option in courseCategoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label class="field" for="course-code"><span>{{ t('teacherCourseCreate.courseCode') }}</span><input id="course-code" v-model.trim="form.courseCode" maxlength="64" /></label>
              <label class="field" for="credits"><span>{{ t('teacherCourseCreate.credits') }} <b>*</b></span><input id="credits" v-model.number="form.credits" required type="number" min="0.5" max="100" step="0.5" /></label>
              <label class="field" for="weekly-hours"><span>{{ t('teacherCourseCreate.weeklyHours') }} <b>*</b></span><input id="weekly-hours" v-model.number="form.weeklyHours" required type="number" min="0.5" max="100" step="0.5" /></label>
              <label class="field field--wide" for="prerequisites"><span>{{ t('teacherCourseCreate.prerequisiteCourses') }}</span><input id="prerequisites" v-model.trim="form.prerequisiteCourses" maxlength="1000" :placeholder="t('teacherCourseCreate.prerequisitePlaceholder')" /></label>
              <label class="field" for="academic-year"><span>{{ t('teacherCourseCreate.academicYear') }}</span><input id="academic-year" v-model.trim="form.academicYear" maxlength="30" placeholder="2026-2027" /></label>
              <label class="field" for="term"><span>{{ t('teacherCourseCreate.term') }}</span><select id="term" v-model="form.term"><option value="">{{ t('teacherCourseCreate.notSet') }}</option><option value="秋冬">{{ t('teacherCourseCreate.autumnWinter') }}</option><option value="春夏">{{ t('teacherCourseCreate.springSummer') }}</option></select></label>
              <label class="field" for="weekday"><span>{{ t('teacherCourseCreate.weekday') }}</span><select id="weekday" v-model="form.weekday"><option value="">{{ t('teacherCourseCreate.notSet') }}</option><option v-for="option in weekdayOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label class="field" for="periods"><span>{{ t('teacherCourseCreate.periods') }}</span><input id="periods" v-model.trim="form.periods" maxlength="100" :placeholder="t('teacherCourseCreate.periodsPlaceholder')" /></label>
              <label class="field field--wide" for="location"><span>{{ t('teacherCourseCreate.classLocation') }}</span><input id="location" v-model.trim="form.defaultLocation" maxlength="200" /></label>
            </div>
          </section>
        </div>

        <footer class="form-footer">
          <div class="form-actions">
            <button type="button" @click="closeCourseCreate">{{ t('common.cancel') }}</button>
            <button class="primary" type="submit" :disabled="creating || !form.courseName || !form.courseCategory || !form.targetGrade || !form.credits || !form.weeklyHours">
              <LoaderCircle v-if="creating" :size="16" class="spin" />
              {{ t('teacherCourseCreate.createCourse') }}
            </button>
          </div>
        </footer>
      </form>
    </dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { LoaderCircle, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'

const emit = defineEmits<{ (event: 'close'): void }>()
const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const dialogRef = ref<HTMLDialogElement | null>(null)
const creating = ref(false)
const titleId = 'teacher-course-create-title'
const basicInfoId = 'teacher-course-create-basic-info'
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
const weekdayOptions = computed(() => [
  { value: '周一', label: t('teacherCourseCreate.weekdays.monday') },
  { value: '周二', label: t('teacherCourseCreate.weekdays.tuesday') },
  { value: '周三', label: t('teacherCourseCreate.weekdays.wednesday') },
  { value: '周四', label: t('teacherCourseCreate.weekdays.thursday') },
  { value: '周五', label: t('teacherCourseCreate.weekdays.friday') },
  { value: '周六', label: t('teacherCourseCreate.weekdays.saturday') },
  { value: '周日', label: t('teacherCourseCreate.weekdays.sunday') },
])
const form = reactive({
  courseName: '', englishName: '', targetGrade: '本科生', courseCategory: '', courseCode: '',
  credits: 2, weeklyHours: 2, totalHours: 32,
  prerequisiteCourses: '', academicYear: '', term: '', weekday: '', periods: '', defaultLocation: '',
})

function closeCourseCreate() {
  if (creating.value) return
  if (dialogRef.value?.open) dialogRef.value.close()
  emit('close')
}

async function createCourse() {
  if (creating.value || !form.courseName.trim()) return
  creating.value = true
  const totalHours = Number(form.totalHours || 32)
  try {
    const result = await courseStore.createTeacherCourseSpace({
      course_name: form.courseName, english_name: form.englishName, academic_year: form.academicYear, term: form.term,
      course_code: form.courseCode, target_grade: form.targetGrade,
      course_category: form.courseCategory, credits: Number(form.credits), weekly_hours: Number(form.weeklyHours),
      total_hours: form.totalHours, prerequisite_courses: form.prerequisiteCourses,
      weekday: form.weekday, periods: form.periods, default_location: form.defaultLocation,
      generation_request: {
        subject: form.courseName, target_audience: form.targetGrade || '大学生', difficulty: 'intermediate',
        learning_purpose: 'systematic',
        course_teaching_type: 'comprehensive',
        pedagogy_mode: 'auto',
        course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: form.courseName },
        requirements: '',
        production_mode: 'manual', teacher_course_brief: {
          schema_version: 'teacher_course_brief_v1', academic_term: [form.academicYear, form.term].filter(Boolean).join(' '),
          target_audience: form.targetGrade || '大学生', total_class_hours: totalHours,
          lesson_duration_minutes: 45,
          additional_requirements: '',
        }, teacher_authoring_mode: 'lesson_assets_v1',
      },
    })
    await courseStore.fetchCourseList({ surface: 'teacher' })
    await router.push({
      name: 'course-workspace',
      params: { courseId: result.course_id, mode: 'setup' },
      query: { returnTo: '/courses?view=courses', prepare: '1' },
    })
  } catch (error: any) {
    ElMessage.error(String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed')))
  } finally { creating.value = false }
}

onMounted(() => dialogRef.value?.showModal())
onBeforeUnmount(() => { if (dialogRef.value?.open) dialogRef.value.close() })
</script>

<style scoped>
.course-create-dialog{width:min(900px,calc(100vw - 32px));max-width:none;height:min(780px,calc(100dvh - 40px));max-height:none;margin:auto;padding:0;overflow:hidden;border:1px solid #dfe5ee;border-radius:16px;color:var(--lz-text-primary);background:#fff;box-shadow:0 28px 72px rgba(15,23,42,.24);animation:course-create-dialog-in .24s cubic-bezier(.16,1,.3,1)}
.course-create-dialog::backdrop{background:rgba(15,23,42,.42);animation:course-create-backdrop-in .18s ease-out}
@keyframes course-create-dialog-in{from{opacity:0;transform:translateY(10px) scale(.992)}to{opacity:1;transform:none}}
@keyframes course-create-backdrop-in{from{background:rgba(15,23,42,0)}to{background:rgba(15,23,42,.42)}}
.course-form{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:#fff}
.form-heading{min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 30px;border-bottom:1px solid #e8edf4}
.form-heading>div{min-width:0;display:grid;gap:6px}.form-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.02em}.form-heading p{margin:0;color:#64748b;font-size:13px}
.form-heading>button{width:36px;height:36px;flex:none;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.form-heading>button:hover{color:#334155;background:#f1f5f9}.form-heading>button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.form-scroll{min-height:0;overflow:auto;overscroll-behavior:contain}
.identity-section{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:24px 30px 26px}.identity-section .field--name{grid-column:1/-1}
.field{min-width:0;display:grid;gap:7px}.field>span{color:#334155;font-size:13px;font-weight:700}.field b{color:#dc2626}
.field input,.field select,.field textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.field textarea{resize:vertical;line-height:1.6}.field input:focus,.field select:focus,.field textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.field--name input{min-height:48px;font-size:15px}
.course-details{border-top:1px solid #e8edf4}.details-heading{min-height:56px;display:flex;align-items:center;gap:9px;padding:0 30px}.details-heading strong{color:#334155;font-size:14px}.details-heading small{padding:3px 7px;border-radius:5px;color:#64748b;background:#f1f5f9;font-size:11px;font-weight:650}
.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:0 30px 30px}.field--wide{grid-column:1/-1}
.form-footer{min-height:76px;display:flex;align-items:center;justify-content:flex-end;gap:20px;padding:14px 30px;border-top:1px solid #e8edf4;background:#fbfcfe}.form-actions{display:flex;gap:9px}.form-actions button{min-height:40px;padding:0 15px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:13px;font-weight:700;cursor:pointer}.form-actions button.primary{min-width:132px;border-color:#514bdc;color:#fff;background:#514bdc;box-shadow:0 7px 18px rgba(81,75,220,.18)}.form-actions button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:680px){.course-create-dialog{width:calc(100vw - 16px);height:calc(100dvh - 16px);border-radius:12px}.form-heading{min-height:82px;padding:18px 20px}.form-heading h2{font-size:21px}.identity-section{grid-template-columns:1fr;padding:20px}.identity-section .field--name{grid-column:auto}.details-heading{padding-inline:20px}.details-grid{grid-template-columns:1fr;padding:0 20px 24px}.field--wide{grid-column:auto}.form-footer{min-height:0;align-items:stretch;flex-direction:column;padding:14px 20px}.form-actions{display:grid;grid-template-columns:auto 1fr}.form-actions button.primary{min-width:0}}
@media(prefers-reduced-motion:reduce){.course-create-dialog,.course-create-dialog::backdrop,.spin{animation:none}}
</style>
