<template>
  <main class="course-change-route">
    <Teleport to="#app-header-route-context">
      <div class="change-route-context">
        <button type="button" :aria-label="t('courseEvolution.workspace.backToCourse', '返回课程工作台')" @click="returnToCourse"><ArrowLeft :size="17" /></button>
        <span><GitBranchPlus :size="17" /></span>
        <div><small>{{ courseTitle || t('courseEvolution.workspace.currentCourse', '当前课程') }}</small><h1>{{ t('courseEvolution.workspace.title', '全课联动修改') }}</h1></div>
      </div>
    </Teleport>
    <Teleport to="#app-header-route-actions">
      <button class="change-route-refresh" type="button" :aria-label="t('courseEvolution.workspace.refresh', '重新读取课程资产')" @click="refreshWorkspace"><RefreshCw :size="16" />{{ t('courseEvolution.workspace.refreshShort', '刷新状态') }}</button>
    </Teleport>
    <CourseEvolutionWorkspace
      ref="workspaceRef"
      :model-value="true"
      standalone
      :course-id="courseId"
      :course-title="courseTitle"
      :focus-plan-id="planId"
      @update:model-value="returnToCourse"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, GitBranchPlus, RefreshCw } from 'lucide-vue-next'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'

const props = withDefaults(defineProps<{ courseId?: string; planId?: string }>(), {
  courseId: '',
  planId: '',
})
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const workspaceRef = ref<{ reloadWorkspace: () => Promise<void> } | null>(null)

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const planId = computed(() => String(props.planId || route.params.planId || ''))
const courseTitle = computed(() => (
  courseStore.courseList.find(item => item.course_id === courseId.value)?.course_name
  || courseStore.currentCourse?.course_name
  || ''
))

function returnToCourse() {
  void router.push({
    name: 'course-workspace',
    params: { courseId: courseId.value, mode: 'build' },
  })
}

function refreshWorkspace() {
  void workspaceRef.value?.reloadWorkspace()
}

onMounted(() => {
  if (!courseStore.courseList.length) {
    void courseStore.fetchCourseList({ surface: 'teacher' })
  }
})
</script>

<style scoped>
.course-change-route {
  min-height: 0;
  height: 100%;
  overflow: hidden;
  background: #f5f7fb;
}
.change-route-context{min-width:0;display:flex;align-items:center;gap:9px}.change-route-context>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:9px;color:#596579;background:transparent;cursor:pointer}.change-route-context>button:hover{color:#4e46d4;background:#efeeff}.change-route-context>span{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;color:#fff;background:#5b54e8}.change-route-context>div{min-width:0;display:grid;gap:1px}.change-route-context small{overflow:hidden;color:#667085;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.change-route-context h1{margin:0;color:#172033;font-size:15px;letter-spacing:-.015em}.change-route-refresh{min-height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:1px solid #d8dde6;border-radius:9px;color:#4f5d70;background:#fff;font-size:11px;font-weight:700;cursor:pointer}.change-route-refresh:hover{border-color:#c8c5f7;color:#4e46ce;background:#f8f7ff}
</style>
