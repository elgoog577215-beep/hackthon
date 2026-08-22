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

    <main class="create-stage" />

    <CourseGenerationDialog
      v-model="generationDialogOpen"
      :busy="creating"
      :initial-audience="fixedAudience"
      :fixed-audience="fixedAudience"
      :initial-total-class-hours="32"
      :initial-lesson-duration-minutes="45"
      :initial-section-count="16"
      show-course-type
      course-space-mode
      :title="t('teacherCourseCreate.settingsTitle')"
      :submit-label="t('teacherCourseCreate.createSpaceAction')"
      @generate="createCourseWithSettings"
      @error="showError"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChevronRight } from 'lucide-vue-next'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'

const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const generationDialogOpen = ref(true)
const creating = ref(false)
const fixedAudience = computed(() => t('teacherCourseCreate.fixedAudience', '大学生'))

function backToCourses() {
  void router.push({ name: 'course-library', query: { view: 'courses' } })
}

function showError(message: string) {
  ElMessage.error(message)
}

function courseGoal(options: CourseGenerationOptions) {
  const intent = options.course_intent as Record<string, unknown> | undefined
  const candidates = [
    options.requirements,
    intent?.desired_outcome,
    intent?.expected_deliverable,
    intent?.desired_output,
  ]
  return String(candidates.find(value => typeof value === 'string' && value.trim()) || '')
}

async function createCourseWithSettings(payload: { subject: string; options: CourseGenerationOptions }) {
  if (creating.value) return
  creating.value = true
  const subject = payload.subject.trim()
  const brief = payload.options.teacher_course_brief
  try {
    const result = await courseStore.createTeacherCourseSpace({
      course_name: subject,
      academic_year: '',
      term: brief?.academic_term || '',
      course_code: '',
      course_goal: courseGoal(payload.options),
      default_location: '',
      generation_request: {
        subject,
        ...payload.options,
        teacher_authoring_mode: 'lesson_assets_v1',
      },
    })
    if (!result?.course_id) throw new Error(t('courseLibrary.createFailed', '课程创建失败'))
    await courseStore.fetchCourseList({ surface: 'teacher' })
    void router.push({
      name: 'course-workspace',
      params: { courseId: result.course_id, mode: 'setup' },
      query: { returnTo: '/courses?view=courses' },
    })
  } catch (error: any) {
    showError(String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed', '课程创建失败')))
  } finally {
    creating.value = false
  }
}

watch(generationDialogOpen, open => {
  if (!open && !creating.value) backToCourses()
})
</script>

<style scoped>
.course-create-page { min-height:100vh; overflow:hidden; color:var(--lz-text-primary); background:#f3f5f9; }
.product-bar { position:relative; z-index:1; height:58px; display:grid; grid-template-columns:210px minmax(0,1fr); align-items:center; border-bottom:1px solid var(--lz-border); background:#fff; }
.brand { height:100%; display:flex; align-items:center; gap:10px; padding:0 22px; border:0; border-right:1px solid var(--lz-border); color:var(--lz-text-primary); background:transparent; cursor:pointer; }
.brand img { width:27px; height:27px; }
.brand strong { font-size:17px; }
.product-bar nav { min-width:0; display:flex; align-items:center; gap:9px; padding:0 24px; color:var(--lz-text-muted); font-size:13px; }
.product-bar nav button { padding:0; border:0; color:inherit; background:transparent; cursor:pointer; }
.product-bar nav strong { color:var(--lz-text-primary); }
.create-stage { min-height:calc(100vh - 58px); background:#f3f5f9; }
@media (max-width:680px) {
  .product-bar { grid-template-columns:64px minmax(0,1fr); }
  .brand { justify-content:center; padding:0; }
  .brand strong { display:none; }
  .product-bar nav { padding-inline:14px; }
}
</style>
