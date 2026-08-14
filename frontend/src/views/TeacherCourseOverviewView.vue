<template>
  <section class="teacher-overview-page">
    <header class="product-bar">
      <button type="button" class="brand" @click="router.push('/courses')">
        <img src="/qizhi-favicon.svg" alt="" />
        <strong>启智</strong>
      </button>
      <nav :aria-label="t('teacherWorkbench.breadcrumb', '当前位置')">
        <button type="button" @click="router.push('/courses')">{{ t('teacherWorkbench.courseWorkbench', '课程工作台') }}</button>
        <ChevronRight :size="14" />
        <strong>{{ courseTitle }}</strong>
      </nav>
      <div class="product-actions">
        <button type="button" @click="openStudentPreview"><Eye :size="16" />{{ t('teacherWorkbench.studentPreview', '预览学生版') }}</button>
        <button type="button" :aria-label="t('common.refresh', '刷新')" :title="t('common.refresh', '刷新')" @click="refresh">
          <RefreshCw :size="17" :class="{ spin: loading }" />
        </button>
      </div>
    </header>

    <div class="page-shell">
      <TeacherCourseSidebar
        :course-id="courseId"
        :title="courseTitle"
        :meta="courseMeta"
        active="overview"
        :attention-count="attentionCount"
      />

      <main class="overview-main">
        <div class="status-bar" role="status">
          <strong>{{ courseTitle }}</strong>
          <span>{{ taskStatusLabel }}</span>
          <span>{{ t('teacherOverview.lessons', '课次') }} {{ lessonCount }}</span>
          <span>{{ t('teacherOverview.calendarScheduled', '已排期') }} {{ scheduledCount }}</span>
          <span>{{ t('teacherOverview.pending', '待处理') }} {{ attentionCount }}</span>
          <span class="spacer"></span>
          <button type="button" class="next-action" @click="openRecommended">{{ recommendedActionLabel }}<ArrowRight :size="15" /></button>
        </div>

        <div v-if="loading" class="page-state"><LoaderCircle class="spin" :size="22" />{{ t('teacherOverview.loading', '正在读取课程工作台') }}</div>
        <div v-else-if="loadError" class="page-state is-error" role="alert">
          <TriangleAlert :size="22" /><strong>{{ t('teacherOverview.loadFailed', '课程工作台读取失败') }}</strong><span>{{ loadError }}</span><button type="button" @click="refresh">{{ t('common.retry', '重试') }}</button>
        </div>

        <div v-else class="overview-body">
          <section class="next-class" aria-labelledby="next-class-title">
            <header>
              <div><small>{{ t('teacherOverview.nextClass', '下一次授课') }}</small><h1 id="next-class-title">{{ nextSession?.content_summary || t('teacherOverview.unscheduledTitle', '尚未安排下一次授课') }}</h1></div>
              <button type="button" class="quiet-button" @click="openCalendar">{{ t('teacherOverview.openCalendar', '打开教学日历') }}<ArrowRight :size="15" /></button>
            </header>
            <div v-if="nextSession" class="next-class-line">
              <span><CalendarClock :size="15" />{{ formatSessionDate(nextSession.date) }} {{ sessionTime(nextSession) }}</span>
              <span><MapPin :size="15" />{{ nextSession.location || t('teacherOverview.locationUnset', '地点未定') }}</span>
              <span><UserRound :size="15" />{{ nextSession.teacher_name || t('teacherOverview.teacherUnset', '教师未定') }}</span>
              <span v-if="nextSession.group_code"><UsersRound :size="15" />{{ nextSession.group_code }}</span>
            </div>
            <p v-else>{{ t('teacherOverview.unscheduledBody', '可以先确认教学大纲，再从大纲生成课次候选；也可以直接手动新增课次。') }}</p>
          </section>

          <section class="asset-progress" aria-labelledby="asset-progress-title">
            <header><h2 id="asset-progress-title">{{ t('teacherOverview.assetProgress', '课程资产进度') }}</h2><span>{{ t('teacherOverview.saveNotPublish', '保存不等于确认，确认不等于发布') }}</span></header>
            <div class="asset-table" role="table">
              <button type="button" role="row" @click="openOutline">
                <span role="cell"><BookOpenText :size="17" /><strong>{{ t('teacherWorkbench.nav.outline', '教学大纲') }}</strong></span>
                <span role="cell" :data-state="outlineState">{{ outlineStatus }}</span>
                <span role="cell">{{ outlineAction }}</span><ArrowRight :size="16" />
              </button>
              <button type="button" role="row" @click="openCalendar">
                <span role="cell"><CalendarDays :size="17" /><strong>{{ t('teacherWorkbench.nav.calendar', '教学日历') }}</strong></span>
                <span role="cell" :data-state="calendarState">{{ calendarStatus }}</span>
                <span role="cell">{{ scheduledCount }}/{{ calendarStore.calendar?.sessions.length || 0 }} {{ t('teacherOverview.scheduledUnit', '已排期') }}</span><ArrowRight :size="16" />
              </button>
              <button type="button" role="row" @click="openProduction('teaching')">
                <span role="cell"><NotebookTabs :size="17" /><strong>{{ t('teacherOverview.teachingPlans', '分讲教案') }}</strong></span>
                <span role="cell" :data-state="teachingState">{{ teachingStatus }}</span>
                <span role="cell">{{ teachingReadyCount }}/{{ lessonCount }} {{ t('teacherOverview.readyUnit', '已有内容') }}</span><ArrowRight :size="16" />
              </button>
              <button type="button" role="row" @click="openProduction('ppt')">
                <span role="cell"><Presentation :size="17" /><strong>PPT</strong></span>
                <span role="cell" :data-state="pptState">{{ pptStatus }}</span>
                <span role="cell">{{ pptDetail }}</span><ArrowRight :size="16" />
              </button>
              <button type="button" role="row" @click="openRelease">
                <span role="cell"><Send :size="17" /><strong>{{ t('teacherWorkbench.nav.release', '发布管理') }}</strong></span>
                <span role="cell" :data-state="isPublished ? 'ready' : 'pending'">{{ isPublished ? t('teacherOverview.published', '已有学生版') : t('teacherOverview.notPublished', '尚未发布') }}</span>
                <span role="cell">{{ isPublished ? t('teacherOverview.snapshotReady', '可查看冻结快照') : t('teacherOverview.releaseSelectVersions', '发布时选择精确版本') }}</span><ArrowRight :size="16" />
              </button>
            </div>
          </section>

          <section class="attention-list" aria-labelledby="attention-title">
            <header><h2 id="attention-title">{{ t('teacherOverview.attention', '需要处理') }}</h2><span>{{ attentionItems.length }}</span></header>
            <button v-for="item in attentionItems" :key="item.key" type="button" @click="item.action">
              <TriangleAlert v-if="item.tone === 'danger'" :size="16" />
              <CircleAlert v-else :size="16" />
              <span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span>
              <ArrowRight :size="16" />
            </button>
            <div v-if="!attentionItems.length" class="all-clear"><CheckCircle2 :size="17" />{{ t('teacherOverview.allClear', '当前没有需要立即处理的异常') }}</div>
          </section>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight, BookOpenText, CalendarClock, CalendarDays, CheckCircle2, ChevronRight,
  CircleAlert, Eye, LoaderCircle, MapPin, NotebookTabs, Presentation, RefreshCw,
  Send, TriangleAlert, UserRound, UsersRound,
} from 'lucide-vue-next'
import TeacherCourseSidebar from '../components/TeacherCourseSidebar.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeachingCalendarStore, type ClassSession } from '../stores/teachingCalendar'
import type { GuidedGenerationStepKey, Node } from '../stores/types'
import { lessonUnitHasContent, projectLessonUnits } from '../utils/lesson-units'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const calendarStore = useTeachingCalendarStore()
const loading = ref(false)
const loadError = ref('')

const courseId = computed(() => String(route.params.courseId || ''))
const task = computed(() => generationStore.tasks.get(courseId.value))
const summary = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value))
const courseTitle = computed(() => courseStore.currentCourse?.course_name || summary.value?.course_name || task.value?.courseName || t('teacherOverview.untitled', '未命名课程'))
const isPublished = computed(() => Boolean(summary.value?.is_published))
const courseMeta = computed(() => calendarStore.calendar?.academic_year || calendarStore.calendar?.term
  ? [calendarStore.calendar?.academic_year, calendarStore.calendar?.term].filter(Boolean).join(' ')
  : isPublished.value ? t('teacherOverview.formalCourse', '正式课程') : t('teacherOverview.draftCourse', '课程草稿'))
const lessons = computed<Node[]>(() => projectLessonUnits(courseStore.nodes))
const lessonCount = computed(() => lessons.value.length)
const teachingReadyCount = computed(() => lessons.value.filter(node => lessonUnitHasContent(courseStore.nodes, node)).length)
const scheduledSessions = computed(() => (calendarStore.calendar?.sessions || []).filter(item => item.date && item.start_time && item.end_time && item.status !== 'cancelled'))
const scheduledCount = computed(() => scheduledSessions.value.length)
const nextSession = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return [...scheduledSessions.value].filter(item => String(item.date) >= today).sort((a, b) => String(a.date).localeCompare(String(b.date)) || String(a.start_time || '').localeCompare(String(b.start_time || '')))[0] || null
})
const reviewStep = computed(() => String(task.value?.guidedWorkflow?.review_step || ''))
const failedLessonCount = computed(() => task.value?.failedNodes?.length || 0)
const attentionCount = computed(() => attentionItems.value.length)
const taskStatusLabel = computed(() => ({ pending: t('teacherOverview.task.pending', '等待开始'), running: t('teacherOverview.task.running', '生成中'), paused: t('teacherOverview.task.paused', '已暂停'), waiting_for_review: t('teacherOverview.task.review', '等待教师确认'), completed: t('teacherOverview.task.completed', '生成完成'), completed_with_warnings: t('teacherOverview.task.warning', '生成完成，有建议'), error: t('teacherOverview.task.error', '生成失败'), conflict: t('teacherOverview.task.conflict', '版本冲突'), idle: t('teacherOverview.task.idle', '未开始') }[task.value?.status || 'idle']))

const outlineState = computed(() => isPublished.value || confirmedStep('outline') ? 'ready' : reviewStep.value === 'outline' ? 'attention' : 'pending')
const outlineStatus = computed(() => outlineState.value === 'ready' ? t('teacherOverview.confirmed', '已确认') : outlineState.value === 'attention' ? t('teacherOverview.awaitingConfirmation', '等待确认') : t('teacherOverview.inProgress', '生成中'))
const outlineAction = computed(() => outlineState.value === 'attention' ? t('teacherOverview.reviewOutline', '审阅并确认大纲') : t('teacherOverview.openOutline', '查看大纲版本'))
const calendarState = computed(() => scheduledCount.value ? 'ready' : calendarStore.calendar?.sessions.length ? 'attention' : 'pending')
const calendarStatus = computed(() => scheduledCount.value ? t('teacherOverview.scheduled', '已排期') : calendarStore.calendar?.sessions.length ? t('teacherOverview.needsScheduling', '待补日期') : t('teacherOverview.notCreated', '尚未建立'))
const teachingState = computed(() => failedLessonCount.value ? 'danger' : teachingReadyCount.value ? 'ready' : outlineState.value === 'ready' ? 'attention' : 'locked')
const teachingStatus = computed(() => failedLessonCount.value ? t('teacherOverview.hasFailures', '存在失败') : teachingReadyCount.value ? t('teacherOverview.hasDrafts', '已有教案') : outlineState.value === 'ready' ? t('teacherOverview.canStart', '可以开始') : t('teacherOverview.waitingOutline', '等待大纲确认'))
const pptState = computed(() => isPublished.value ? 'ready' : teachingReadyCount.value ? 'attention' : 'locked')
const pptStatus = computed(() => isPublished.value ? t('teacherOverview.canProduce', '可以制作') : teachingReadyCount.value ? t('teacherOverview.sourcePreparing', '来源准备中') : t('teacherOverview.waitingTeaching', '等待教案'))
const pptDetail = computed(() => isPublished.value ? t('teacherOverview.openPptWorkbench', '进入现有 PPT 工作台') : t('teacherOverview.pptCanonicalSource', '当前接口要求正式课程源'))

const recommendedRoute = computed(() => {
  if (reviewStep.value === 'outline') return { name: 'teacher-course-outline' }
  if (failedLessonCount.value || task.value?.status === 'paused' || task.value?.status === 'error') return { name: 'teacher-course-production' }
  if (!calendarStore.calendar?.sessions.length) return { name: 'teacher-course-calendar' }
  if (reviewStep.value === 'teaching' || teachingReadyCount.value < lessonCount.value) return { name: 'teacher-course-production', query: { stage: 'teaching' } }
  return { name: 'teacher-course-production' }
})
const recommendedActionLabel = computed(() => reviewStep.value === 'outline'
  ? t('teacherOverview.next.reviewOutline', '下一步：确认教学大纲')
  : failedLessonCount.value || task.value?.status === 'paused' || task.value?.status === 'error'
    ? t('teacherOverview.next.recover', '下一步：处理生成异常')
    : !calendarStore.calendar?.sessions.length
      ? t('teacherOverview.next.calendar', '下一步：建立教学日历')
      : teachingReadyCount.value < lessonCount.value
        ? t('teacherOverview.next.teaching', '下一步：继续分讲教案')
        : t('teacherOverview.next.production', '继续课程生产'))

const attentionItems = computed(() => {
  const items: Array<{ key: string; title: string; detail: string; tone: 'warning' | 'danger'; action: () => void }> = []
  if (task.value?.error || task.value?.errorUserMessage) items.push({ key: 'task-error', title: t('teacherOverview.issue.generationFailed', '课程生成存在失败'), detail: String(task.value.errorUserMessage || task.value.error), tone: 'danger', action: () => openProduction() })
  if (reviewStep.value) items.push({ key: `review-${reviewStep.value}`, title: t('teacherOverview.issue.waitingReview', '有产物等待教师确认'), detail: stepLabel(reviewStep.value), tone: 'warning', action: () => reviewStep.value === 'outline' ? openOutline() : openProduction('teaching') })
  if (failedLessonCount.value) items.push({ key: 'failed-lessons', title: t('teacherOverview.issue.failedLessons', '部分讲次生成失败'), detail: t('teacherOverview.issue.failedLessonCount', '{count} 个讲次需要重试或检查').replace('{count}', String(failedLessonCount.value)), tone: 'danger', action: () => openProduction('teaching') })
  if (!calendarStore.calendar?.sessions.length) items.push({ key: 'calendar-empty', title: t('teacherOverview.issue.calendarEmpty', '教学日历尚未建立'), detail: t('teacherOverview.issue.calendarEmptyDetail', '可从已确认大纲生成课次候选，也可手动新增。'), tone: 'warning', action: openCalendar })
  return items
})

function confirmedStep(key: GuidedGenerationStepKey) { return task.value?.guidedWorkflow?.steps?.some(item => item.key === key && item.status === 'confirmed') || false }
function stepLabel(key: string) { return ({ outline: t('teacherWorkbench.nav.outline', '教学大纲'), teaching: t('teacherOverview.teachingPlans', '分讲教案'), content: t('teacherOverview.courseContent', '课程内容'), release: t('teacherWorkbench.nav.release', '发布管理') } as Record<string, string>)[key] || key }
function formatSessionDate(value?: string | null) { if (!value) return ''; const date = new Date(`${value}T12:00:00`); return new Intl.DateTimeFormat(document.documentElement.lang === 'en' ? 'en-US' : 'zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(date) }
function sessionTime(session: ClassSession) { return [session.start_time, session.end_time].filter(Boolean).join('–') || t('teacherOverview.timeUnset', '时间未定') }
function openRecommended() { void router.push({ ...recommendedRoute.value, params: { courseId: courseId.value } }) }
function openOutline() { void router.push({ name: 'teacher-course-outline', params: { courseId: courseId.value } }) }
function openCalendar() { void router.push({ name: 'teacher-course-calendar', params: { courseId: courseId.value } }) }
function openProduction(stage?: 'teaching' | 'ppt') { void router.push({ name: 'teacher-course-production', params: { courseId: courseId.value }, query: stage ? { stage } : undefined }) }
function openRelease() { void router.push({ name: 'teacher-course-release', params: { courseId: courseId.value } }) }
function openStudentPreview() { void router.push({ name: 'learning', params: { courseId: courseId.value } }) }

async function load() {
  if (!courseId.value || loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    generationStore.restoreGenerationState()
    generationStore.initWebSocket()
    await courseStore.fetchCourseList()
    await Promise.all([courseStore.loadCourse(courseId.value), calendarStore.loadCourse(courseId.value)])
    generationStore.observeCourse(courseId.value)
  } catch (error: any) {
    loadError.value = String(error?.response?.data?.detail || error?.message || t('teacherOverview.unknownError', '未知错误'))
  } finally { loading.value = false }
}
async function refresh() { await load() }

watch(courseId, async (next, previous) => {
  if (previous) generationStore.unobserveCourse(previous)
  calendarStore.resetCourse()
  if (next) await load()
}, { immediate: true })
onBeforeUnmount(() => { if (courseId.value) generationStore.unobserveCourse(courseId.value) })
</script>

<style scoped>
.teacher-overview-page { min-height:100vh; height:100vh; overflow:hidden; color:var(--lz-text-primary); background:var(--lz-canvas); }
button { font:inherit; }
.product-bar { height:52px; display:grid; grid-template-columns:188px minmax(0,1fr) auto; align-items:center; border-bottom:1px solid var(--lz-border); background:var(--lz-surface); }
.brand { height:100%; display:flex; align-items:center; gap:10px; padding:0 20px; border:0; border-right:1px solid var(--lz-border); color:var(--lz-text-primary); background:transparent; cursor:pointer; }.brand img{width:25px;height:25px}.brand strong{font-size:17px}
.product-bar nav { min-width:0; display:flex; align-items:center; gap:8px; padding:0 24px; color:var(--lz-text-muted); font-size:12px; }.product-bar nav button{max-width:220px;overflow:hidden;padding:0;border:0;color:inherit;background:transparent;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.product-bar nav strong{overflow:hidden;color:var(--lz-text-primary);text-overflow:ellipsis;white-space:nowrap}
.product-actions{display:flex;align-items:center;gap:6px;padding-right:14px}.product-actions button{height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}
.page-shell{height:calc(100vh - 52px);display:grid;grid-template-columns:188px minmax(0,1fr)}.overview-main{min-width:0;min-height:0;display:grid;grid-template-rows:42px minmax(0,1fr)}
.status-bar{min-width:0;display:flex;align-items:center;padding:0 14px;border-bottom:1px solid var(--lz-border);background:var(--lz-surface);font-size:11px;white-space:nowrap}.status-bar>strong,.status-bar>span{padding:0 11px;border-right:1px solid var(--lz-border)}.status-bar>strong{padding-left:0}.status-bar .spacer{flex:1;border:0}.next-action{height:29px;display:inline-flex;align-items:center;gap:5px;padding:0 10px;border:0;border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);cursor:pointer;font-weight:700}
.page-state{height:100%;display:grid;place-content:center;justify-items:center;gap:9px;color:var(--lz-text-muted);font-size:11px}.page-state.is-error{color:var(--lz-danger)}.page-state button{height:32px;padding:0 12px;border:1px solid var(--lz-border);border-radius:7px;background:var(--lz-surface);cursor:pointer}
.overview-body{min-width:0;min-height:0;overflow:auto;padding:18px clamp(18px,3vw,38px) 36px;background:var(--lz-surface)}
.next-class,.asset-progress,.attention-list{max-width:1180px;margin:0 auto;border-bottom:1px solid var(--lz-border)}.next-class{padding:2px 0 18px}.next-class>header,.asset-progress>header,.attention-list>header{display:flex;align-items:center;justify-content:space-between;gap:18px}.next-class small{color:var(--lz-brand);font-size:10px;font-weight:800}.next-class h1{margin:4px 0 0;font-size:21px;line-height:1.3}.quiet-button{height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.next-class-line{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:13px;color:var(--lz-text-secondary);font-size:11px}.next-class-line span{display:inline-flex;align-items:center;gap:6px}.next-class p{margin:11px 0 0;color:var(--lz-text-muted);font-size:11px}
.asset-progress{padding:17px 0}.asset-progress h2,.attention-list h2{margin:0;font-size:14px}.asset-progress header>span{color:var(--lz-text-muted);font-size:10px}.asset-table{margin-top:10px;border-top:1px solid var(--lz-border)}.asset-table>button{width:100%;min-height:47px;display:grid;grid-template-columns:minmax(180px,1.2fr) 120px minmax(180px,1fr) 22px;align-items:center;gap:12px;padding:0 6px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.asset-table>button:hover{background:var(--lz-brand-soft)}.asset-table [role="cell"]:first-child{display:flex;align-items:center;gap:9px;color:var(--lz-text-primary)}.asset-table [role="cell"]:nth-child(2){width:max-content;padding:3px 7px;border-radius:7px;color:var(--lz-text-muted);background:var(--lz-fill);font-size:9px}.asset-table [data-state="ready"]{color:var(--lz-success)!important;background:var(--lz-success-soft)!important}.asset-table [data-state="attention"]{color:var(--lz-warning)!important;background:var(--lz-warning-soft)!important}.asset-table [data-state="danger"]{color:var(--lz-danger)!important;background:var(--lz-danger-soft)!important}.asset-table [role="cell"]:nth-child(3){font-size:10px}
.attention-list{padding:17px 0;border-bottom:0}.attention-list>header>span{min-width:20px;padding:2px 6px;border-radius:9px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:9px;text-align:center}.attention-list>button{width:100%;min-height:48px;display:grid;grid-template-columns:22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:7px 6px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-warning);background:transparent;text-align:left;cursor:pointer}.attention-list>button:hover{background:var(--lz-warning-soft)}.attention-list>button>span{display:grid;gap:3px}.attention-list strong{color:var(--lz-text-primary);font-size:11px}.attention-list small{color:var(--lz-text-muted);font-size:10px}.all-clear{display:flex;align-items:center;gap:7px;padding:16px 6px;color:var(--lz-success);font-size:11px}
.spin{animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:900px){.product-bar{grid-template-columns:150px minmax(0,1fr) auto}.brand{padding:0 15px}.page-shell{grid-template-columns:64px minmax(0,1fr)}.status-bar>span:nth-of-type(n+3){display:none}.asset-table>button{grid-template-columns:minmax(160px,1fr) 100px minmax(130px,1fr) 18px}}
@media(max-width:680px){.teacher-overview-page{height:auto;min-height:100vh;overflow:auto}.product-bar{grid-template-columns:64px minmax(0,1fr) auto}.brand strong,.product-bar nav button,.product-bar nav svg,.product-actions button:first-child{display:none}.product-bar nav{padding:0 10px}.page-shell{height:auto;display:block}.overview-main{min-height:calc(100vh - 97px);grid-template-rows:38px minmax(0,1fr)}.status-bar>span{display:none}.overview-body{padding:14px 12px 28px}.next-class>header{align-items:flex-start}.next-class h1{font-size:17px}.asset-progress header>span{display:none}.asset-table>button{grid-template-columns:minmax(120px,1fr) auto 18px;gap:7px}.asset-table [role="cell"]:nth-child(3){display:none}}
</style>
