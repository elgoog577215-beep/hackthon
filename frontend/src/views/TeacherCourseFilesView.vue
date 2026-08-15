<template>
  <section class="teacher-files-page">
    <header class="product-bar">
      <button type="button" class="brand" @click="router.push({ name: 'teacher-course-library' })"><img src="/qizhi-favicon.svg" alt="" /><strong>启智</strong></button>
      <nav aria-label="当前位置">
      <button type="button" @click="router.push({ name: 'teacher-course-library' })">课程工作台</button><ChevronRight :size="14" /><button type="button" @click="router.push({ name: 'teacher-course-overview', params: { courseId } })">{{ courseTitle }}</button><ChevronRight :size="14" /><strong>课程文件</strong>
      </nav>
      <div class="product-actions">
        <button type="button" @click="openStudentPreview"><Eye :size="16" />预览学生版</button>
        <button type="button" aria-label="刷新" title="刷新" @click="load"><RefreshCw :size="17" :class="{ spin: loading }" /></button>
      </div>
    </header>

    <div class="page-shell">
      <TeacherCourseSidebar :course-id="courseId" :title="courseTitle" :meta="courseMeta" active="files" />
      <main class="files-main">
        <div class="status-bar" role="status"><strong>{{ courseTitle }}</strong><span>课程文件</span><span>真实存储</span><span>支持整文件夹导入</span><span class="spacer"></span><span>文件组织不改变课程生成版本</span></div>
        <div v-if="loading" class="page-state">正在读取课程文件空间</div>
        <TeacherCourseSpaceView v-else embedded :course-id="courseId" :course-title="courseTitle" />
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronRight, Eye, RefreshCw } from 'lucide-vue-next'
import TeacherCourseSidebar from '../components/TeacherCourseSidebar.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'

const route = useRoute()
const router = useRouter()
const { course: courseStore } = useTeacherCourseRuntime()
const loading = ref(false)
const courseId = computed(() => String(route.params.courseId || ''))
const summary = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value))
const courseTitle = computed(() => courseStore.currentCourse?.course_name || summary.value?.course_name || '未命名课程')
const courseMeta = computed(() => summary.value?.is_published ? '正式课程' : '课程草稿')

async function load() {
  if (!courseId.value || loading.value) return
  loading.value = true
  try {
    await courseStore.fetchCourseList()
    await courseStore.loadCourse(courseId.value)
  } finally { loading.value = false }
}
function openStudentPreview() { void router.push({ name: 'learning', params: { courseId: courseId.value } }) }
watch(courseId, () => { void load() }, { immediate: true })
</script>

<style scoped>
.teacher-files-page{min-height:100vh;height:100vh;overflow:hidden;color:var(--lz-text-primary);background:var(--lz-canvas)}button{font:inherit}.product-bar{height:52px;display:grid;grid-template-columns:188px minmax(0,1fr) auto;align-items:center;border-bottom:1px solid var(--lz-border);background:var(--lz-surface)}.brand{height:100%;display:flex;align-items:center;gap:10px;padding:0 20px;border:0;border-right:1px solid var(--lz-border);color:var(--lz-text-primary);background:transparent;cursor:pointer}.brand img{width:25px;height:25px}.brand strong{font-size:17px}.product-bar nav{min-width:0;display:flex;align-items:center;gap:8px;padding:0 20px;color:var(--lz-text-muted);font-size:12px}.product-bar nav button{max-width:220px;overflow:hidden;padding:0;border:0;color:inherit;background:transparent;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.product-bar nav strong{color:var(--lz-text-primary)}.product-actions{display:flex;gap:6px;padding-right:14px}.product-actions button{height:32px;display:inline-flex;align-items:center;gap:6px;padding:0 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.page-shell{height:calc(100vh - 52px);display:grid;grid-template-columns:188px minmax(0,1fr)}.files-main{min-width:0;min-height:0;display:grid;grid-template-rows:42px minmax(0,1fr)}.status-bar{min-width:0;display:flex;align-items:center;padding:0 14px;border-bottom:1px solid var(--lz-border);background:var(--lz-surface);font-size:11px;white-space:nowrap}.status-bar>strong,.status-bar>span{padding:0 10px;border-right:1px solid var(--lz-border)}.status-bar>strong{padding-left:0}.status-bar .spacer{flex:1;border:0}.page-state{height:100%;display:grid;place-items:center;color:var(--lz-text-muted);font-size:11px}.spin{animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:900px){.product-bar{grid-template-columns:64px minmax(0,1fr) auto}.brand{justify-content:center;padding:0}.brand strong{display:none}.page-shell{grid-template-columns:64px minmax(0,1fr)}.status-bar>span:nth-of-type(n+3){display:none}}
@media(max-width:680px){.teacher-files-page{height:auto;min-height:100vh;overflow:auto}.product-bar nav button,.product-bar nav svg,.product-actions button:first-child{display:none}.page-shell{height:auto;display:block}.files-main{min-height:calc(100vh - 96px);grid-template-rows:38px minmax(0,1fr)}.status-bar>span{display:none}}
</style>
