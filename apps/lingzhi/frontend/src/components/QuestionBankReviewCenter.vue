<template>
  <Teleport to="body" :disabled="embedded">
    <div
      v-if="modelValue"
      class="review-center-layer"
      :class="{ 'review-center-layer--embedded': embedded }"
      @keydown.esc="handleEscape"
    >
      <button
        v-if="!embedded"
        type="button"
        class="review-center-backdrop"
        :aria-label="t('common.cancel', '关闭')"
        @click="close"
      />
      <section
        ref="panelRef"
        class="review-center"
        :class="{ 'review-center--embedded': embedded }"
        :role="embedded ? 'region' : 'dialog'"
        :aria-modal="embedded ? undefined : true"
        :aria-labelledby="embedded ? undefined : titleId"
        :aria-label="embedded ? t('questionBank.centerTitle', '课程题库质量管理') : undefined"
        tabindex="-1"
      >
        <header v-if="!embedded" class="review-center__header">
          <div>
            <span><ShieldCheck :size="17" /></span>
            <div>
              <h2 :id="titleId">{{ t('questionBank.centerTitle', '课程题库质量管理') }}</h2>
            </div>
          </div>
          <div class="review-center__header-actions">
            <button
              type="button"
              class="icon-button"
              :title="t('questionBank.refreshCourses', '刷新课程')"
              :disabled="refreshing"
              @click="refresh"
            >
              <RefreshCw :size="17" :class="{ spin: refreshing }" />
            </button>
            <button
              type="button"
              class="icon-button"
              :title="t('common.cancel', '关闭')"
              @click="close"
            >
              <X :size="18" />
            </button>
          </div>
        </header>

        <div class="review-center__body" :class="{ 'review-center__body--single': embedded && courseId }">
          <aside v-if="!embedded || !courseId" class="review-course-list" :aria-label="t('questionBank.courseList', '课程列表')">
            <label class="review-course-search">
              <Search :size="15" />
              <input
                v-model="query"
                type="search"
                :placeholder="t('questionBank.searchCourse', '搜索课程')"
              />
            </label>
            <div class="review-course-count">
              {{ filteredCourses.length }} {{ t('courseLibrary.courseUnit', '门课程') }}
            </div>
            <div v-if="refreshing && !courses.length" class="review-course-empty">
              <LoaderCircle :size="20" class="spin" />
              <span>{{ t('courseLibrary.loading', '正在读取课程') }}</span>
            </div>
            <div v-else-if="!filteredCourses.length" class="review-course-empty">
              <Inbox :size="22" />
              <strong>{{ t('questionBank.noCourses', '没有可管理的课程') }}</strong>
            </div>
            <div v-else class="review-course-rows">
              <button
                v-for="course in filteredCourses"
                :key="course.course_id"
                type="button"
                class="review-course-row"
                :class="{ active: selectedCourseId === course.course_id }"
                :data-testid="`question-bank-course-${course.course_id}`"
                @click="selectCourse(course.course_id)"
              >
                <span class="review-course-row__icon">
                  <BookOpenText :size="16" />
                </span>
                <span class="review-course-row__copy">
                  <strong>{{ course.course_name }}</strong>
                  <small>
                    {{ course.node_count || 0 }} {{ t('courseLibrary.nodes', '个学习节点') }}
                  </small>
                </span>
                <ChevronRight :size="15" />
              </button>
            </div>
          </aside>

          <main class="review-center__detail">
            <div v-if="selectedCourse" class="review-center__scroll">
              <header class="selected-course-heading">
                <div>
                  <h3>{{ selectedCourse.course_name }}</h3>
                </div>
                <small>{{ selectedCourse.node_count || 0 }} {{ t('courseLibrary.nodes', '个学习节点') }}</small>
              </header>
              <QuestionBankReviewPanel
                :key="selectedCourse.course_id"
                :course-id="selectedCourse.course_id"
                :initial-node-ids="initialQuestionNodeIds"
                :initial-scope-label="initialQuestionScopeLabel"
              />
            </div>
            <div v-else class="review-center__empty">
              <ShieldCheck :size="30" />
              <strong>{{ t('questionBank.selectCourse', '请选择一门课程浏览题库') }}</strong>
            </div>
          </main>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  BookOpenText,
  ChevronRight,
  Inbox,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-vue-next'
import QuestionBankReviewPanel from '@/components/QuestionBankReviewPanel.vue'
import { useCourseStore } from '@/stores/course'
import { t } from '@/shared/i18n'

const props = withDefaults(defineProps<{
  modelValue: boolean
  courseId?: string
  embedded?: boolean
  initialQuestionNodeIds?: string[]
  initialQuestionScopeLabel?: string
}>(), {
  courseId: '',
  embedded: false,
  initialQuestionNodeIds: () => [],
  initialQuestionScopeLabel: '',
})
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const courseStore = useCourseStore()
const titleId = `question-bank-review-${Math.random().toString(36).slice(2)}`
const panelRef = ref<HTMLElement | null>(null)
const selectedCourseId = ref('')
const query = ref('')
const refreshing = ref(false)

const courses = computed(() => courseStore.courseList)
const filteredCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return courses.value
  return courses.value.filter(course => (
    course.course_name.toLocaleLowerCase().includes(keyword)
  ))
})
const selectedCourse = computed(() => (
  courses.value.find(course => course.course_id === selectedCourseId.value)
  || null
))

watch(() => props.modelValue, async open => {
  if (!open) return
  await refresh()
  selectInitialCourse()
  await nextTick()
  if (!props.embedded) panelRef.value?.focus()
}, { immediate: true })

watch(() => props.courseId, value => {
  if (value && courses.value.some(course => course.course_id === value)) {
    selectedCourseId.value = value
  }
})

watch(courses, () => {
  if (!selectedCourse.value) selectInitialCourse()
})

function close() {
  emit('update:modelValue', false)
}

function handleEscape() {
  if (!props.embedded) close()
}

function selectCourse(courseId: string) {
  selectedCourseId.value = courseId
}

function selectInitialCourse() {
  const requested = String(props.courseId || '')
  selectedCourseId.value = (
    courses.value.some(course => course.course_id === requested)
      ? requested
      : selectedCourseId.value && courses.value.some(
        course => course.course_id === selectedCourseId.value,
      )
        ? selectedCourseId.value
        : courses.value[0]?.course_id || ''
  )
}

async function refresh() {
  refreshing.value = true
  try {
    await courseStore.fetchCourseList({ surface: 'teacher' })
  } finally {
    refreshing.value = false
  }
}
</script>

<style scoped>
.review-center-layer { position:fixed; inset:0; z-index:530; display:grid; place-items:center; padding:20px; }
.review-center-layer--embedded { position:relative; inset:auto; z-index:auto; width:100%; height:100%; display:block; padding:0; }
.review-center-backdrop { position:absolute; inset:0; width:100%; height:100%; border:0; background:rgba(30,41,59,.36); backdrop-filter:blur(5px); cursor:default; }
.review-center { position:relative; width:min(1180px,100%); height:min(820px,calc(100vh - 40px)); display:grid; grid-template-rows:62px minmax(0,1fr); overflow:hidden; border:1px solid rgba(255,255,255,.92); border-radius:var(--lz-radius-surface); color:var(--lz-text); background:rgba(255,255,255,.98); box-shadow:var(--lz-shadow-overlay); outline:none; }
.review-center--embedded { width:100%; height:100%; grid-template-rows:minmax(0,1fr); border:0; border-radius:0; box-shadow:none; }
.review-center__header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 14px 0 20px; border-bottom:1px solid var(--lz-border); }
.review-center__header>div:first-child { min-width:0; display:flex; align-items:center; gap:10px; }
.review-center__header>div:first-child>span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.review-center__header p { margin:0 0 1px; color:var(--lz-text-muted); font-size:12px; font-weight:700; }
.review-center__header h2 { margin:0; color:var(--lz-text-strong); font-size:16px; }
.review-center__header-actions { display:flex; gap:4px; }
.icon-button { width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:8px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.icon-button:hover,.icon-button:focus-visible { color:var(--lz-brand-strong); background:var(--lz-brand-soft); outline:none; }
.review-center__body { min-height:0; display:grid; grid-template-columns:280px minmax(0,1fr); }
.review-center__body--single { grid-template-columns:minmax(0,1fr); }
.review-course-list { min-height:0; display:flex; flex-direction:column; padding:12px 10px; border-right:1px solid var(--lz-border); background:var(--lz-surface-muted); }
.review-course-search { display:flex; align-items:center; gap:8px; padding:0 10px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-muted); background:#fff; }
.review-course-search input { min-width:0; flex:1; height:36px; border:0; outline:0; color:var(--lz-text); background:transparent; }
.review-course-count { padding:9px 5px 7px; color:var(--lz-text-muted); font-size:12px; }
.review-course-rows { min-height:0; display:grid; align-content:start; gap:5px; overflow:auto; }
.review-course-row { width:100%; display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:center; gap:8px; min-height:54px; padding:8px; border:1px solid transparent; border-radius:9px; color:var(--lz-text); background:transparent; text-align:left; cursor:pointer; }
.review-course-row:hover,.review-course-row:focus-visible { background:#fff; outline:none; }
.review-course-row.active { border-color:rgba(99,102,241,.24); background:var(--lz-brand-soft); }
.review-course-row__icon { width:28px; height:28px; display:grid; place-items:center; border-radius:7px; color:var(--lz-brand-strong); background:#fff; }
.review-course-row__copy { min-width:0; display:grid; gap:3px; }
.review-course-row__copy strong { overflow:hidden; color:var(--lz-text-strong); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.review-course-row__copy small { overflow:hidden; color:var(--lz-text-muted); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.review-course-empty,.review-center__empty { min-height:180px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--lz-text-muted); text-align:center; }
.review-course-empty strong,.review-center__empty strong { color:var(--lz-text-strong); font-size:13px; }
.review-center__detail { min-width:0; min-height:0; background:#f8fafc; }
.review-center__scroll {
  height:100%;
  overflow-x:hidden;
  overflow-y:scroll;
  overscroll-behavior:contain;
  scrollbar-color:#94a3b8 #e2e8f0;
  scrollbar-gutter:stable;
  scrollbar-width:auto;
  padding:16px 18px 18px;
}
.review-center__scroll::-webkit-scrollbar { width:12px; }
.review-center__scroll::-webkit-scrollbar-track { border-radius:999px; background:#e2e8f0; }
.review-center__scroll::-webkit-scrollbar-thumb { min-height:48px; border:3px solid #e2e8f0; border-radius:999px; background:#94a3b8; }
.review-center__scroll::-webkit-scrollbar-thumb:hover { background:#64748b; }
.selected-course-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:9px; padding:0 2px; }
.selected-course-heading span,.selected-course-heading small { color:var(--lz-text-muted); font-size:12px; }
.selected-course-heading h3 { margin:0; overflow:hidden; color:var(--lz-text-strong); font-size:16px; text-overflow:ellipsis; white-space:nowrap; }
.spin { animation:review-center-spin .9s linear infinite; }
@keyframes review-center-spin { to { transform:rotate(360deg); } }
@media (max-width:760px) {
  .review-center-layer { align-items:end; padding:0; }
  .review-center { width:100%; height:calc(100vh - 40px); border-radius:14px 14px 0 0; }
  .review-center--embedded { height:100%; border-radius:0; }
  .review-center__body { grid-template-columns:1fr; grid-template-rows:112px minmax(0,1fr); }
  .review-center__body--single { grid-template-rows:minmax(0,1fr); }
  .review-course-list { display:grid; grid-template-columns:minmax(0,1fr) auto; grid-template-rows:36px minmax(0,1fr); gap:6px 8px; padding:8px 10px; border-right:0; border-bottom:1px solid var(--lz-border); }
  .review-course-count { align-self:center; padding:0; }
  .review-course-rows { grid-column:1 / -1; display:flex; gap:6px; overflow-x:auto; overflow-y:hidden; scroll-snap-type:x proximity; }
  .review-course-row { flex:0 0 min(232px,calc(100vw - 64px)); min-height:52px; gap:7px; padding:6px 8px; scroll-snap-align:start; }
  .review-course-row__icon { width:28px; height:28px; }
  .review-course-row__copy strong { font-size:12px; }
  .review-course-row__copy small { font-size:12px; }
  .review-center__scroll { padding:12px; }
  .selected-course-heading { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:7px; margin-bottom:8px; }
  .selected-course-heading > div { min-width:0; display:contents; }
  .selected-course-heading span { white-space:nowrap; }
  .selected-course-heading h3 { min-width:0; margin:0; overflow:hidden; font-size:14px; text-overflow:ellipsis; white-space:nowrap; }
  .selected-course-heading small { padding:3px 6px; border-radius:999px; background:var(--lz-surface-muted); white-space:nowrap; }
}
</style>
