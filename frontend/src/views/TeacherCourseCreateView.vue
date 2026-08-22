<template>
  <section class="course-create-page">
    <header class="product-bar">
      <button type="button" class="brand" @click="backToCourses">
        <img src="/qizhi-favicon.svg" alt="" />
        <strong>启智</strong>
      </button>
      <nav :aria-label="t('teacherWorkbench.breadcrumb', '当前位置')">
        <button type="button" @click="backToCourses">{{ t('teacherWorkbench.courseWorkbench', '课程工作台') }}</button>
        <ChevronRight :size="14" />
        <strong>{{ t('teacherCourseCreate.title', '新建课程') }}</strong>
      </nav>
    </header>

    <main class="create-main">
      <form class="course-form" @submit.prevent="createCourse">
        <header class="form-heading">
          <div>
            <h1>{{ t('teacherCourseCreate.title', '新建课程') }}</h1>
            <p>{{ t('teacherCourseCreate.simpleHelp', '填写课程名称即可创建，其他信息可稍后补充。') }}</p>
          </div>
        </header>

        <section class="identity-section">
          <label class="field field--name" for="course-name">
            <span>{{ t('teacherCourseCreate.courseName', '课程名称') }} <b aria-hidden="true">*</b></span>
            <input id="course-name" v-model.trim="form.courseName" required maxlength="200" autofocus :placeholder="t('teacherCourseCreate.courseNamePlaceholder', '例如：设计思维与创新设计')" />
          </label>
        </section>

        <details class="course-details">
          <summary>
            <span>{{ t('teacherCourseCreate.basicInfo', '课程基本信息') }}</span>
            <small>{{ t('teacherCourseCreate.optional', '选填') }}</small>
          </summary>
          <div class="details-grid">
            <label class="field" for="target-grade"><span>{{ t('teacherCourseCreate.targetGrade', '授课对象年级') }}</span><select id="target-grade" v-model="form.targetGrade"><option value="">{{ t('teacherCourseCreate.notSet', '暂不设置') }}</option><option value="本科生">{{ t('teacherCourseCreate.undergraduate', '本科生') }}</option><option value="研究生">{{ t('teacherCourseCreate.postgraduate', '研究生') }}</option></select></label>
            <label class="field" for="course-category"><span>{{ t('teacherCourseCreate.courseCategory', '课程类别') }}</span><select id="course-category" v-model="form.courseCategory"><option value="">{{ t('teacherCourseCreate.notSet', '暂不设置') }}</option><option value="通识必修课">{{ t('teacherCourseCreate.generalRequired', '通识必修课') }}</option><option value="专业必修课">{{ t('teacherCourseCreate.majorRequired', '专业必修课') }}</option><option value="专业选修课">{{ t('teacherCourseCreate.majorElective', '专业选修课') }}</option></select></label>
            <label class="field" for="target-major"><span>{{ t('teacherCourseCreate.targetMajor', '授课对象专业') }}</span><input id="target-major" v-model.trim="form.targetMajor" maxlength="200" /></label>
            <label class="field" for="course-code"><span>{{ t('teacherCourseCreate.courseCode', '课程代码（可后补）') }}</span><input id="course-code" v-model.trim="form.courseCode" maxlength="64" /></label>
            <label class="field" for="credits"><span>{{ t('teacherCourseCreate.credits', '学分') }}</span><input id="credits" v-model.number="form.credits" type="number" min="0" max="100" step="0.5" /></label>
            <label class="field" for="total-hours"><span>{{ t('teacherCourseCreate.totalHours', '总学时') }}</span><input id="total-hours" v-model.number="form.totalHours" type="number" min="1" max="1000" step="1" /></label>
            <label class="field" for="academic-year"><span>{{ t('teacherCourseCreate.academicYear', '学年') }}</span><input id="academic-year" v-model.trim="form.academicYear" maxlength="30" placeholder="2026-2027" /></label>
            <label class="field" for="term"><span>{{ t('teacherCourseCreate.term', '学期') }}</span><select id="term" v-model="form.term"><option value="">{{ t('teacherCourseCreate.notSet', '暂不设置') }}</option><option value="秋冬">{{ t('teacherCourseCreate.autumnWinter', '秋冬') }}</option><option value="春夏">{{ t('teacherCourseCreate.springSummer', '春夏') }}</option></select></label>
            <label class="field field--wide" for="assessment-method"><span>{{ t('teacherCourseCreate.assessmentMethod', '考核方式') }}</span><input id="assessment-method" v-model.trim="form.assessmentMethod" maxlength="500" :placeholder="t('teacherCourseCreate.assessmentPlaceholder', '例如：过程考核 40% + 课程项目 60%')" /></label>
            <label class="field field--wide" for="course-intro"><span>{{ t('teacherCourseCreate.courseIntro', '课程介绍') }}</span><textarea id="course-intro" v-model.trim="form.courseIntro" rows="3" maxlength="3000" /></label>
            <label class="field field--wide" for="teaching-goals"><span>{{ t('teacherCourseCreate.teachingGoals', '教学目标') }}</span><textarea id="teaching-goals" v-model.trim="form.teachingGoals" rows="3" maxlength="3000" :placeholder="t('teacherCourseCreate.goalPlaceholder', '学生完成课程后能够……')" /></label>
          </div>
        </details>

        <footer class="form-footer">
          <label class="outline-option">
            <input v-model="form.generateOutline" type="checkbox" />
            <span><strong>{{ t('teacherCourseCreate.generateOutline', '创建后生成课程大纲') }}</strong><small>{{ t('teacherCourseCreate.generateOutlineHelp', '进入工作台后可看到实时生成过程') }}</small></span>
          </label>
          <div class="form-actions">
            <button type="button" @click="backToCourses">{{ t('common.cancel', '取消') }}</button>
            <button class="primary" type="submit" :disabled="creating || !form.courseName">
              <LoaderCircle v-if="creating" :size="16" class="spin" />
              {{ form.generateOutline ? t('teacherCourseCreate.createAndGenerate', '创建课程并生成大纲') : t('teacherCourseCreate.createCourse', '创建课程') }}
            </button>
          </div>
        </footer>
      </form>
    </main>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChevronRight, LoaderCircle } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'

const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const creating = ref(false)
const form = reactive({
  courseName: '', targetGrade: '本科生', courseCategory: '', targetMajor: '', courseCode: '',
  credits: undefined as number | undefined, totalHours: 32 as number | undefined,
  academicYear: '', term: '', assessmentMethod: '', courseIntro: '', teachingGoals: '', generateOutline: false,
})

function backToCourses() { void router.push({ name: 'course-library', query: { view: 'courses' } }) }

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
    ElMessage.error(String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed', '课程创建失败')))
  } finally { creating.value = false }
}
</script>

<style scoped>
.course-create-page{min-height:100vh;color:var(--lz-text-primary);background:#f3f5f9}.product-bar{height:58px;display:grid;grid-template-columns:210px minmax(0,1fr);align-items:center;border-bottom:1px solid var(--lz-border);background:#fff}.brand{height:100%;display:flex;align-items:center;gap:10px;padding:0 22px;border:0;border-right:1px solid var(--lz-border);color:var(--lz-text-primary);background:transparent;cursor:pointer}.brand img{width:27px;height:27px}.brand strong{font-size:17px}.product-bar nav{min-width:0;display:flex;align-items:center;gap:9px;padding:0 24px;color:var(--lz-text-muted);font-size:13px}.product-bar nav button{padding:0;border:0;color:inherit;background:transparent;cursor:pointer}.product-bar nav strong{color:var(--lz-text-primary)}.create-main{display:flex;justify-content:center;padding:48px 24px 80px}.course-form{width:min(760px,100%);overflow:hidden;border:1px solid #e2e7ef;border-radius:16px;background:#fff;box-shadow:0 18px 45px rgba(30,41,59,.08)}.form-heading{padding:30px 34px 22px;border-bottom:1px solid #edf1f6}.form-heading h1{margin:0;color:#172033;font-size:26px;letter-spacing:-.02em}.form-heading p{margin:8px 0 0;color:#64748b;font-size:14px}.identity-section{padding:28px 34px}.field{display:grid;gap:8px;min-width:0}.field>span{color:#334155;font-size:13px;font-weight:700}.field b{color:#dc2626}.field input,.field select,.field textarea{width:100%;min-height:44px;padding:10px 12px;border:1px solid #cfd7e3;border-radius:9px;outline:0;color:#172033;background:#fff;font:inherit;font-size:14px}.field textarea{resize:vertical;line-height:1.6}.field input:focus,.field select:focus,.field textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.field--name input{min-height:50px;font-size:16px}.course-details{border-top:1px solid #edf1f6}.course-details summary{min-height:58px;display:flex;align-items:center;gap:9px;padding:0 34px;color:#334155;font-size:14px;font-weight:750;cursor:pointer}.course-details summary small{padding:3px 7px;border-radius:5px;color:#64748b;background:#f1f5f9;font-size:11px;font-weight:650}.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px 18px;padding:4px 34px 30px}.field--wide{grid-column:1/-1}.form-footer{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 34px;border-top:1px solid #e8edf4;background:#fbfcfe}.outline-option{display:flex;align-items:flex-start;gap:10px;cursor:pointer}.outline-option input{width:17px;height:17px;margin-top:2px;accent-color:#5b57e8}.outline-option span{display:grid;gap:3px}.outline-option strong{color:#334155;font-size:13px}.outline-option small{color:#64748b;font-size:12px}.form-actions{display:flex;gap:9px}.form-actions button{min-height:42px;padding:0 16px;border:1px solid #d7dde7;border-radius:9px;color:#475569;background:#fff;font-size:13px;font-weight:700;cursor:pointer}.form-actions button.primary{min-width:132px;border-color:#514bdc;color:#fff;background:#514bdc;box-shadow:0 7px 18px rgba(81,75,220,.18)}.form-actions button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:680px){.product-bar{grid-template-columns:64px minmax(0,1fr)}.brand{justify-content:center;padding:0}.brand strong{display:none}.product-bar nav{padding-inline:14px}.create-main{padding:18px 12px 40px}.course-form{border-radius:12px}.form-heading,.identity-section{padding-inline:20px}.details-grid{grid-template-columns:1fr;padding-inline:20px}.field--wide{grid-column:auto}.course-details summary{padding-inline:20px}.form-footer{align-items:stretch;flex-direction:column;padding:18px 20px}.form-actions{display:grid;grid-template-columns:auto 1fr}.form-actions button.primary{min-width:0}}
</style>
