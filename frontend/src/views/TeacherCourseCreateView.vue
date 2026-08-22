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
              <span>{{ t('teacherCourseCreate.courseName') }} <b aria-hidden="true">*</b></span>
              <input id="course-name" v-model.trim="form.courseName" required maxlength="200" autofocus :placeholder="t('teacherCourseCreate.courseNamePlaceholder')" />
            </label>
          </section>

          <section class="course-details" :aria-labelledby="basicInfoId">
            <header class="details-heading">
              <strong :id="basicInfoId">{{ t('teacherCourseCreate.basicInfo') }}</strong>
              <small>{{ t('teacherCourseCreate.optional') }}</small>
            </header>
            <div class="details-grid">
              <label class="field" for="target-grade"><span>{{ t('teacherCourseCreate.targetGrade') }}</span><select id="target-grade" v-model="form.targetGrade"><option value="">{{ t('teacherCourseCreate.notSet') }}</option><option value="本科生">{{ t('teacherCourseCreate.undergraduate') }}</option><option value="研究生">{{ t('teacherCourseCreate.postgraduate') }}</option></select></label>
              <label class="field" for="course-category"><span>{{ t('teacherCourseCreate.courseCategory') }}</span><select id="course-category" v-model="form.courseCategory"><option value="">{{ t('teacherCourseCreate.notSet') }}</option><option value="通识必修课">{{ t('teacherCourseCreate.generalRequired') }}</option><option value="专业必修课">{{ t('teacherCourseCreate.majorRequired') }}</option><option value="专业选修课">{{ t('teacherCourseCreate.majorElective') }}</option></select></label>
              <label class="field" for="target-major"><span>{{ t('teacherCourseCreate.targetMajor') }}</span><input id="target-major" v-model.trim="form.targetMajor" maxlength="200" /></label>
              <label class="field" for="course-code"><span>{{ t('teacherCourseCreate.courseCode') }}</span><input id="course-code" v-model.trim="form.courseCode" maxlength="64" /></label>
              <label class="field" for="credits"><span>{{ t('teacherCourseCreate.credits') }}</span><input id="credits" v-model.number="form.credits" type="number" min="0" max="100" step="0.5" /></label>
              <label class="field" for="total-hours"><span>{{ t('teacherCourseCreate.totalHours') }}</span><input id="total-hours" v-model.number="form.totalHours" type="number" min="1" max="1000" step="1" /></label>
              <label class="field" for="academic-year"><span>{{ t('teacherCourseCreate.academicYear') }}</span><input id="academic-year" v-model.trim="form.academicYear" maxlength="30" placeholder="2026-2027" /></label>
              <label class="field" for="term"><span>{{ t('teacherCourseCreate.term') }}</span><select id="term" v-model="form.term"><option value="">{{ t('teacherCourseCreate.notSet') }}</option><option value="秋冬">{{ t('teacherCourseCreate.autumnWinter') }}</option><option value="春夏">{{ t('teacherCourseCreate.springSummer') }}</option></select></label>
              <label class="field field--wide" for="assessment-method"><span>{{ t('teacherCourseCreate.assessmentMethod') }}</span><input id="assessment-method" v-model.trim="form.assessmentMethod" maxlength="500" :placeholder="t('teacherCourseCreate.assessmentPlaceholder')" /></label>
              <label class="field field--wide" for="course-intro"><span>{{ t('teacherCourseCreate.courseIntro') }}</span><textarea id="course-intro" v-model.trim="form.courseIntro" rows="3" maxlength="3000" /></label>
              <label class="field field--wide" for="teaching-goals"><span>{{ t('teacherCourseCreate.teachingGoals') }}</span><textarea id="teaching-goals" v-model.trim="form.teachingGoals" rows="3" maxlength="3000" :placeholder="t('teacherCourseCreate.goalPlaceholder')" /></label>
            </div>
          </section>
        </div>

        <footer class="form-footer">
          <label class="outline-option">
            <input v-model="form.generateOutline" type="checkbox" />
            <span><strong>{{ t('teacherCourseCreate.generateOutline') }}</strong><small>{{ t('teacherCourseCreate.generateOutlineHelp') }}</small></span>
          </label>
          <div class="form-actions">
            <button type="button" @click="closeCourseCreate">{{ t('common.cancel') }}</button>
            <button class="primary" type="submit" :disabled="creating || !form.courseName">
              <LoaderCircle v-if="creating" :size="16" class="spin" />
              {{ form.generateOutline ? t('teacherCourseCreate.createAndGenerate') : t('teacherCourseCreate.createCourse') }}
            </button>
          </div>
        </footer>
      </form>
    </dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
const form = reactive({
  courseName: '', targetGrade: '本科生', courseCategory: '', targetMajor: '', courseCode: '',
  credits: undefined as number | undefined, totalHours: 32 as number | undefined,
  academicYear: '', term: '', assessmentMethod: '', courseIntro: '', teachingGoals: '', generateOutline: false,
})

function closeCourseCreate() {
  if (creating.value) return
  if (dialogRef.value?.open) dialogRef.value.close()
  emit('close')
}

async function createCourse() {
  if (creating.value || !form.courseName.trim()) return
  creating.value = true
  const learningGoal = form.teachingGoals || form.courseIntro || form.courseName
  const totalHours = Number(form.totalHours || 32)
  try {
    const result = await courseStore.createTeacherCourseSpace({
      course_name: form.courseName, academic_year: form.academicYear, term: form.term,
      course_code: form.courseCode, course_goal: form.teachingGoals, target_grade: form.targetGrade,
      course_category: form.courseCategory, target_major: form.targetMajor, credits: form.credits,
      total_hours: form.totalHours, assessment_method: form.assessmentMethod, course_intro: form.courseIntro,
      teaching_goals: form.teachingGoals,
      generation_request: {
        subject: form.courseName, target_audience: form.targetGrade || '大学生', difficulty: 'intermediate',
        composition_style: 'balanced', course_type: 'systematic',
        course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: learningGoal },
        requirements: [form.courseIntro, form.assessmentMethod].filter(Boolean).join('\n'),
        production_mode: 'manual', teacher_course_brief: {
          schema_version: 'teacher_course_brief_v1', academic_term: [form.academicYear, form.term].filter(Boolean).join(' '),
          target_audience: form.targetGrade || '大学生', total_class_hours: totalHours,
          lesson_duration_minutes: 45, teaching_context: 'classroom', section_count: Math.max(1, Math.round(totalHours / 2)),
          additional_requirements: form.assessmentMethod,
        }, teacher_authoring_mode: 'lesson_assets_v1',
      },
    })
    await courseStore.fetchCourseList({ surface: 'teacher' })
    await router.push({ name: 'course-workspace', params: { courseId: result.course_id, mode: 'setup' }, query: { returnTo: '/courses?view=courses', ...(form.generateOutline ? { generate: 'outline' } : {}) } })
  } catch (error: any) {
    ElMessage.error(String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed')))
  } finally { creating.value = false }
}

onMounted(() => dialogRef.value?.showModal())
onBeforeUnmount(() => { if (dialogRef.value?.open) dialogRef.value.close() })
</script>

<style scoped>
.course-create-dialog{width:min(900px,calc(100vw - 32px));max-width:none;height:min(780px,calc(100dvh - 40px));max-height:none;margin:auto;padding:0;overflow:hidden;border:1px solid #dfe5ee;border-radius:16px;color:var(--lz-text-primary);background:#fff;box-shadow:0 28px 72px rgba(15,23,42,.24)}
.course-create-dialog::backdrop{background:rgba(15,23,42,.42)}
.course-form{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:#fff}
.form-heading{min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 30px;border-bottom:1px solid #e8edf4}
.form-heading>div{min-width:0;display:grid;gap:6px}.form-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.02em}.form-heading p{margin:0;color:#64748b;font-size:13px}
.form-heading>button{width:36px;height:36px;flex:none;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.form-heading>button:hover{color:#334155;background:#f1f5f9}.form-heading>button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.form-scroll{min-height:0;overflow:auto;overscroll-behavior:contain}
.identity-section{padding:24px 30px 26px}
.field{min-width:0;display:grid;gap:7px}.field>span{color:#334155;font-size:13px;font-weight:700}.field b{color:#dc2626}
.field input,.field select,.field textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.field textarea{resize:vertical;line-height:1.6}.field input:focus,.field select:focus,.field textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.field--name input{min-height:48px;font-size:15px}
.course-details{border-top:1px solid #e8edf4}.details-heading{min-height:56px;display:flex;align-items:center;gap:9px;padding:0 30px}.details-heading strong{color:#334155;font-size:14px}.details-heading small{padding:3px 7px;border-radius:5px;color:#64748b;background:#f1f5f9;font-size:11px;font-weight:650}
.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:0 30px 30px}.field--wide{grid-column:1/-1}
.form-footer{min-height:76px;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 30px;border-top:1px solid #e8edf4;background:#fbfcfe}.outline-option{display:flex;align-items:flex-start;gap:10px;cursor:pointer}.outline-option input{width:17px;height:17px;margin-top:2px;accent-color:#5b57e8}.outline-option span{display:grid;gap:3px}.outline-option strong{color:#334155;font-size:13px}.outline-option small{color:#64748b;font-size:12px}.form-actions{display:flex;gap:9px}.form-actions button{min-height:40px;padding:0 15px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:13px;font-weight:700;cursor:pointer}.form-actions button.primary{min-width:132px;border-color:#514bdc;color:#fff;background:#514bdc;box-shadow:0 7px 18px rgba(81,75,220,.18)}.form-actions button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:680px){.course-create-dialog{width:calc(100vw - 16px);height:calc(100dvh - 16px);border-radius:12px}.form-heading{min-height:82px;padding:18px 20px}.form-heading h2{font-size:21px}.identity-section{padding:20px}.details-heading{padding-inline:20px}.details-grid{grid-template-columns:1fr;padding:0 20px 24px}.field--wide{grid-column:auto}.form-footer{min-height:0;align-items:stretch;flex-direction:column;padding:14px 20px}.form-actions{display:grid;grid-template-columns:auto 1fr}.form-actions button.primary{min-width:0}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
