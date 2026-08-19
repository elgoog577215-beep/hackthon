<template>
  <section class="course-workspace-view glass-panel-elevated">
    <header class="workspace-heading">
      <div class="workspace-identity">
        <RouterLink :to="{ name: 'course-library' }" :aria-label="t('unifiedCourseWorkspace.back', '返回课程库')">
          <ArrowLeft :size="17" />
        </RouterLink>
        <div>
          <span>{{ t('unifiedCourseWorkspace.label', '课程工作区') }}</span>
          <strong>{{ courseTitle }}</strong>
        </div>
      </div>
      <CourseModeTabs :active="activeMode" :course-id="courseId" />
      <div class="workspace-state" :data-state="courseState.tone">
        <i aria-hidden="true"></i>
        <span>{{ courseState.label }}</span>
      </div>
    </header>

    <nav class="workspace-subtabs" :aria-label="sectionNavigationLabel">
      <button
        v-for="item in sections"
        :key="item.key"
        type="button"
        :class="{ 'is-active': activeSection === item.key }"
        :aria-current="activeSection === item.key ? 'page' : undefined"
        :data-testid="`course-section-${item.key}`"
        @click="selectSection(item.key)"
      >
        <component :is="item.icon" :size="16" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <main class="workspace-content" :class="`is-${activeSection}`">
      <div v-if="loading" class="workspace-feedback" role="status">
        <LoaderCircle class="spin" :size="22" />
        <strong>{{ t('unifiedCourseWorkspace.loading', '正在读取课程') }}</strong>
        <span>{{ t('unifiedCourseWorkspace.loadingHelp', '先打开当前模块，其余工具会在需要时加载。') }}</span>
      </div>
      <div v-else-if="loadError" class="workspace-feedback is-error" role="alert">
        <TriangleAlert :size="22" />
        <strong>{{ t('unifiedCourseWorkspace.loadFailed', '课程读取失败') }}</strong>
        <span>{{ loadError }}</span>
        <button type="button" @click="loadCourse(true)">{{ t('common.retry', '重试') }}</button>
      </div>

      <template v-else>
        <section v-show="activePanel === 'setup:basic'" class="basic-panel">
          <header>
            <div>
              <span>{{ t('unifiedCourseWorkspace.basic.eyebrow', '基本课程信息') }}</span>
              <h1>{{ courseTitle }}</h1>
              <p>{{ t('unifiedCourseWorkspace.basic.help', '这里说明这门课当前连接了哪些正式内容。资料、课程设计与排课分别在上方继续维护。') }}</p>
            </div>
            <button type="button" class="primary-action" @click="selectSection('files')">
              <FolderOpen :size="16" />{{ t('unifiedCourseWorkspace.basic.prepareFiles', '整理课程资料') }}
            </button>
          </header>
          <dl class="course-facts">
            <div><dt>{{ t('unifiedCourseWorkspace.basic.status', '课程状态') }}</dt><dd>{{ courseState.label }}</dd></div>
            <div><dt>{{ t('unifiedCourseWorkspace.basic.structure', '课程结构') }}</dt><dd>{{ courseStore.nodes.length }} {{ t('unifiedCourseWorkspace.basic.nodes', '个教学节点') }}</dd></div>
            <div><dt>{{ t('unifiedCourseWorkspace.basic.plan', '课程设计') }}</dt><dd>{{ teachingPlanLabel }}</dd></div>
            <div><dt>{{ t('unifiedCourseWorkspace.basic.revision', '正文修订') }}</dt><dd>{{ courseStore.currentDocumentRevision || t('unifiedCourseWorkspace.basic.notPublished', '尚未发布') }}</dd></div>
          </dl>
          <section class="workflow-note">
            <strong>{{ t('unifiedCourseWorkspace.basic.orderTitle', '建议顺序') }}</strong>
            <p>{{ t('unifiedCourseWorkspace.basic.orderHelp', '先整理资料与课程设计，再确认大纲和逐讲备课；需要上课时切到正式课程。每一步都可单独保存和返回。') }}</p>
            <div>
              <button type="button" @click="selectSection('design')">{{ t('unifiedCourseWorkspace.sections.design', '课程设计') }}<ArrowRight :size="14" /></button>
              <button type="button" @click="openBuild('outline')">{{ t('unifiedCourseWorkspace.sections.outline', '大纲') }}<ArrowRight :size="14" /></button>
            </div>
          </section>
        </section>

        <TeacherCourseSpaceView
          v-if="visitedPanels.has('setup:files')"
          v-show="activePanel === 'setup:files'"
          :key="`files:${courseId}`"
          embedded
          :course-id="courseId"
          :course-title="courseTitle"
        />

        <div
          v-if="visitedPanels.has('setup:design')"
          v-show="activePanel === 'setup:design'"
          class="plan-panel"
        >
          <GenerationLessonPlan
            :plan="courseStore.currentTeachingPlan"
            :nodes="courseStore.nodes"
            :active-node-id="courseStore.currentNode?.node_id"
            :course-id="courseId"
            visible-scope="overall"
            @select="selectNode"
            @open-outline-editor="openBuild('outline')"
            @applied="reloadCurrentCourse"
          />
        </div>

        <TeacherCourseCalendarView
          v-if="visitedPanels.has('setup:calendar')"
          v-show="activePanel === 'setup:calendar'"
          :key="`calendar:${courseId}`"
          embedded
        />

        <div
          v-if="visitedPanels.has('build:outline')"
          v-show="activePanel === 'build:outline'"
          class="outline-panel"
        >
          <CourseOutlineReview
            :course-id="courseId"
            :course-name="courseTitle"
            :nodes="courseStore.nodes"
            :task="generationTask"
            @confirmed="reloadCurrentCourse"
          />
        </div>

        <div
          v-if="visitedPanels.has('build:lesson')"
          v-show="activePanel === 'build:lesson'"
          class="plan-panel"
        >
          <GenerationLessonPlan
            :plan="courseStore.currentTeachingPlan"
            :nodes="courseStore.nodes"
            :active-node-id="courseStore.currentNode?.node_id"
            :course-id="courseId"
            prefer-section-view
            visible-scope="sections"
            @select="selectNode"
            @open-outline-editor="openBuild('outline')"
            @applied="reloadCurrentCourse"
          />
        </div>

        <section
          v-if="visitedPanels.has('build:practice')"
          v-show="activePanel === 'build:practice'"
          class="handoff-panel"
        >
          <ClipboardCheck :size="25" />
          <span>{{ t('unifiedCourseWorkspace.practice.eyebrow', '沿用正式练习资产') }}</span>
          <h2>{{ t('unifiedCourseWorkspace.practice.title', '在正式课程中检查和试做练习') }}</h2>
          <p>{{ t('unifiedCourseWorkspace.practice.help', '练习继续读取同一题目资产、作答记录和质量状态。这里不建立一份教师专用题库。') }}</p>
          <button type="button" class="primary-action" @click="openFormal('practice')">
            {{ t('unifiedCourseWorkspace.practice.open', '打开正式课程练习') }}<ArrowRight :size="16" />
          </button>
        </section>

        <section
          v-if="visitedPanels.has('build:ppt')"
          v-show="activePanel === 'build:ppt'"
          class="handoff-panel"
        >
          <Presentation :size="25" />
          <span>{{ t('unifiedCourseWorkspace.ppt.eyebrow', '沿用原 PPT 工作台') }}</span>
          <h2>{{ t('unifiedCourseWorkspace.ppt.title', '从同一课程设计生成和维护课件') }}</h2>
          <p>{{ t('unifiedCourseWorkspace.ppt.help', '课件继续绑定课程、知识、目标和来源修订。预览、页级编辑、演示与导出都在原工作台完成。') }}</p>
          <button type="button" class="primary-action" @click="openPpt">
            {{ t('unifiedCourseWorkspace.ppt.open', '进入 PPT 工作台') }}<ArrowRight :size="16" />
          </button>
        </section>
      </template>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ArrowRight, BookOpenCheck, CalendarDays, ClipboardCheck, FileText,
  FolderOpen, Info, ListTree, LoaderCircle, Presentation, TriangleAlert,
} from 'lucide-vue-next'
import CourseModeTabs, { type CourseMode } from '../components/CourseModeTabs.vue'
import CourseOutlineReview from '../components/CourseOutlineReview.vue'
import GenerationLessonPlan from '../components/GenerationLessonPlan.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import TeacherCourseCalendarView from './TeacherCourseCalendarView.vue'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import type { Node } from '../stores/types'
import { t } from '../shared/i18n'

type SetupSection = 'basic' | 'files' | 'design' | 'calendar'
type BuildSection = 'outline' | 'lesson' | 'practice' | 'ppt'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const loading = ref(false)
const loadError = ref('')
const loadedCourseId = ref('')
const visitedPanels = reactive(new Set<string>())

const courseId = computed(() => String(route.params.courseId || ''))
const activeMode = computed<CourseMode>(() => route.params.mode === 'build' ? 'build' : 'setup')
const setupSections = computed(() => [
  { key: 'basic' as const, label: t('unifiedCourseWorkspace.sections.basic', '基本信息'), icon: Info },
  { key: 'files' as const, label: t('unifiedCourseWorkspace.sections.files', '资料'), icon: FolderOpen },
  { key: 'design' as const, label: t('unifiedCourseWorkspace.sections.design', '课程设计'), icon: BookOpenCheck },
  { key: 'calendar' as const, label: t('unifiedCourseWorkspace.sections.calendar', '教学日历'), icon: CalendarDays },
])
const buildSections = computed(() => [
  { key: 'outline' as const, label: t('unifiedCourseWorkspace.sections.outline', '大纲'), icon: ListTree },
  { key: 'lesson' as const, label: t('unifiedCourseWorkspace.sections.lesson', '讲次备课'), icon: FileText },
  { key: 'practice' as const, label: t('unifiedCourseWorkspace.sections.practice', '练习'), icon: ClipboardCheck },
  { key: 'ppt' as const, label: 'PPT', icon: Presentation },
])
const sections = computed(() => activeMode.value === 'setup' ? setupSections.value : buildSections.value)
const activeSection = computed<SetupSection | BuildSection>(() => {
  const requested = String(route.query.section || '')
  const allowed = sections.value.map(item => item.key as string)
  return (allowed.includes(requested) ? requested : allowed[0]) as SetupSection | BuildSection
})
const activePanel = computed(() => `${activeMode.value}:${activeSection.value}`)
const sectionNavigationLabel = computed(() => activeMode.value === 'setup'
  ? t('unifiedCourseWorkspace.setupNavigation', '课程设置模块')
  : t('unifiedCourseWorkspace.buildNavigation', '备课制作模块'))
const courseTitle = computed(() => (
  courseStore.currentCourse?.course_name
  || generationTask.value?.courseName
  || t('unifiedCourseWorkspace.untitled', '未命名课程')
))
const generationTask = computed(() => generationStore.tasks.get(courseId.value))
const courseState = computed(() => {
  const task = generationTask.value
  if (task && ['running', 'pending'].includes(task.status)) return { tone: 'working', label: t('unifiedCourseWorkspace.state.generating', '正在生成') }
  if (task && ['waiting_for_review', 'paused', 'conflict', 'error', 'completed_with_warnings'].includes(task.status)) return { tone: 'attention', label: t('unifiedCourseWorkspace.state.attention', '需要处理') }
  if (courseStore.currentCourse?.is_published || courseStore.currentDocumentRevision) return { tone: 'ready', label: t('unifiedCourseWorkspace.state.ready', '正式课程可用') }
  return { tone: 'draft', label: t('unifiedCourseWorkspace.state.draft', '课程草稿') }
})
const teachingPlanLabel = computed(() => {
  const plan = courseStore.currentTeachingPlan
  if (!plan) return t('unifiedCourseWorkspace.basic.planMissing', '尚未形成')
  if (plan.status === 'completed') return t('unifiedCourseWorkspace.basic.planReady', '已形成，可继续修订')
  return t('unifiedCourseWorkspace.basic.planWorking', '正在形成')
})

watch(activePanel, panel => visitedPanels.add(panel), { immediate: true })
watch(courseId, () => {
  visitedPanels.clear()
  visitedPanels.add(activePanel.value)
  void loadCourse()
}, { immediate: true })

async function loadCourse(force = false) {
  if (!courseId.value || loading.value) return
  if (!force && loadedCourseId.value === courseId.value && courseStore.currentCourseId === courseId.value) return
  loading.value = true
  loadError.value = ''
  try {
    const results = await Promise.allSettled([
      courseStore.fetchCourseList(),
      courseStore.loadCourse(courseId.value, { includeLearningRecords: false, silentError: true }),
    ])
    if (results[1].status === 'rejected' || courseStore.currentCourseId !== courseId.value) {
      throw results[1].status === 'rejected' ? results[1].reason : new Error(t('unifiedCourseWorkspace.loadFailed', '课程读取失败'))
    }
    loadedCourseId.value = courseId.value
    const initialNode = courseStore.nodes.find(node => node.node_level === 2) || courseStore.nodes[0]
    if (!courseStore.currentNode && initialNode) courseStore.selectNode(initialNode)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : t('unifiedCourseWorkspace.loadFailedHelp', '请检查服务后重试。')
  } finally {
    loading.value = false
  }
}

function reloadCurrentCourse() { void loadCourse(true) }
function selectNode(node: Node) { courseStore.selectNode(node) }
function selectSection(section: SetupSection | BuildSection) {
  void router.push({
    name: 'course-workspace',
    params: { courseId: courseId.value, mode: activeMode.value },
    query: { ...route.query, section },
  })
}
function openBuild(section: BuildSection) {
  void router.push({ name: 'course-workspace', params: { courseId: courseId.value, mode: 'build' }, query: { section } })
}
function openFormal(workspace?: 'practice') {
  void router.push({ name: 'learning', params: { courseId: courseId.value }, query: workspace ? { workspace } : undefined })
}
function openPpt() { void router.push({ name: 'ppt-workspace', params: { courseId: courseId.value }, query: { returnTo: route.fullPath } }) }
</script>

<style scoped>
.course-workspace-view {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 72px 48px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, .88);
  border-radius: var(--lz-radius-surface);
  background: var(--lz-surface);
}
.workspace-heading {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(460px, 720px) minmax(150px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--lz-border);
  background: rgba(255, 255, 255, .96);
}
.workspace-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }
.workspace-identity > a { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; border-radius: 9px; color: var(--lz-text-secondary); text-decoration: none; }
.workspace-identity > a:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.workspace-identity > a:focus-visible { outline: 3px solid rgba(99, 102, 241, .24); outline-offset: 2px; }
.workspace-identity > div { min-width: 0; display: grid; gap: 3px; }
.workspace-identity span { color: var(--lz-text-muted); font-size: 9px; }
.workspace-identity strong { overflow: hidden; color: var(--lz-text-strong); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.workspace-state { justify-self: end; display: flex; align-items: center; gap: 7px; color: var(--lz-text-secondary); font-size: 10px; font-weight: 700; }
.workspace-state i { width: 7px; height: 7px; border-radius: 50%; background: var(--lz-text-muted); }
.workspace-state[data-state="ready"] i { background: var(--lz-success); }
.workspace-state[data-state="working"] i { background: var(--lz-brand); box-shadow: 0 0 0 4px var(--lz-brand-soft); }
.workspace-state[data-state="attention"] i { background: var(--lz-warning); }
.workspace-subtabs { display: flex; align-items: end; gap: 4px; padding: 0 18px; border-bottom: 1px solid var(--lz-border); background: var(--lz-surface); overflow-x: auto; }
.workspace-subtabs button { height: 47px; display: inline-flex; align-items: center; gap: 7px; padding: 0 15px; border: 0; border-bottom: 2px solid transparent; color: var(--lz-text-muted); background: transparent; font-size: 11px; font-weight: 700; white-space: nowrap; cursor: pointer; }
.workspace-subtabs button:hover { color: var(--lz-text-strong); background: var(--lz-fill); }
.workspace-subtabs button:focus-visible { outline: 3px solid rgba(99, 102, 241, .24); outline-offset: -4px; }
.workspace-subtabs button.is-active { color: var(--lz-brand-strong); border-bottom-color: var(--lz-brand); }
.workspace-content { min-width: 0; min-height: 0; overflow: auto; background: var(--lz-canvas); }
.workspace-content.is-files,
.workspace-content.is-calendar { overflow: hidden; }
.workspace-feedback { height: 100%; display: grid; place-content: center; justify-items: center; gap: 8px; color: var(--lz-text-muted); text-align: center; }
.workspace-feedback strong { color: var(--lz-text-strong); font-size: 14px; }
.workspace-feedback span { max-width: 420px; font-size: 10px; line-height: 1.6; }
.workspace-feedback button { height: 32px; margin-top: 5px; padding: 0 14px; border: 1px solid var(--lz-brand-border); border-radius: 8px; color: var(--lz-brand-strong); background: var(--lz-surface); cursor: pointer; }
.workspace-feedback.is-error > svg { color: var(--lz-danger); }
.spin { animation: workspace-spin .9s linear infinite; }
.basic-panel { width: min(920px, calc(100% - 48px)); margin: 0 auto; padding: 44px 0 56px; }
.basic-panel > header { display: flex; align-items: end; justify-content: space-between; gap: 28px; padding-bottom: 24px; border-bottom: 1px solid var(--lz-border); }
.basic-panel > header > div { min-width: 0; }
.basic-panel > header span,
.handoff-panel > span { color: var(--lz-brand-strong); font-size: 10px; font-weight: 800; }
.basic-panel h1 { margin: 6px 0 8px; color: var(--lz-text-strong); font-size: clamp(24px, 3vw, 38px); letter-spacing: -.025em; }
.basic-panel p,
.handoff-panel p { max-width: 68ch; margin: 0; color: var(--lz-text-secondary); font-size: 12px; line-height: 1.75; }
.primary-action { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 14px; border: 1px solid var(--lz-brand); border-radius: 9px; color: #fff; background: var(--lz-brand); font-size: 11px; font-weight: 700; white-space: nowrap; cursor: pointer; }
.primary-action:hover { background: var(--lz-brand-strong); }
.primary-action:focus-visible { outline: 3px solid rgba(99, 102, 241, .25); outline-offset: 2px; }
.course-facts { margin: 0; }
.course-facts > div { min-height: 58px; display: grid; grid-template-columns: minmax(120px, 190px) minmax(0, 1fr); align-items: center; gap: 20px; border-bottom: 1px solid var(--lz-border); }
.course-facts dt { color: var(--lz-text-muted); font-size: 10px; font-weight: 700; }
.course-facts dd { margin: 0; overflow-wrap: anywhere; color: var(--lz-text-strong); font-size: 12px; }
.workflow-note { margin-top: 28px; padding: 20px 0 0; }
.workflow-note > strong { color: var(--lz-text-strong); font-size: 13px; }
.workflow-note p { margin: 7px 0 14px; }
.workflow-note > div { display: flex; gap: 8px; }
.workflow-note button { min-height: 32px; display: inline-flex; align-items: center; gap: 6px; padding: 0 11px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: var(--lz-surface); font-size: 10px; cursor: pointer; }
.plan-panel,
.outline-panel { min-height: 100%; padding: 18px; }
.plan-panel > :deep(.generation-lesson-plan),
.outline-panel > :deep(.outline-review) { min-height: calc(100% - 2px); }
.handoff-panel { width: min(680px, calc(100% - 40px)); min-height: 100%; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; margin: 0 auto; padding: 48px 0; }
.handoff-panel > svg { margin-bottom: 18px; color: var(--lz-brand); }
.handoff-panel h2 { margin: 7px 0 10px; color: var(--lz-text-strong); font-size: 24px; letter-spacing: -.02em; }
.handoff-panel .primary-action { margin-top: 20px; }
@keyframes workspace-spin { to { transform: rotate(360deg); } }
@media (max-width: 1100px) {
  .workspace-heading { grid-template-columns: minmax(150px, .8fr) minmax(420px, 1.4fr) auto; gap: 10px; }
  .workspace-state span { display: none; }
}
@media (max-width: 767px) {
  .course-workspace-view { height: auto; min-height: 100%; grid-template-rows: auto 44px minmax(0, 1fr); border: 0; border-radius: 0; }
  .workspace-heading { grid-template-columns: minmax(0, 1fr); gap: 9px; padding: 10px; }
  .workspace-identity { order: 1; }
  .workspace-heading > :deep(.course-mode-tabs) { order: 2; }
  .workspace-state { position: absolute; top: 17px; right: 14px; }
  .workspace-subtabs { padding: 0 6px; }
  .workspace-subtabs button { height: 43px; padding: 0 10px; }
  .workspace-subtabs button svg { display: none; }
  .workspace-content.is-files,
  .workspace-content.is-calendar { overflow: auto; }
  .basic-panel { width: calc(100% - 28px); padding: 28px 0 40px; }
  .basic-panel > header { display: grid; align-items: start; }
  .course-facts > div { grid-template-columns: 100px minmax(0, 1fr); }
  .plan-panel,
  .outline-panel { padding: 8px; }
  .handoff-panel h2 { font-size: 20px; }
}
@media (prefers-reduced-motion: reduce) {
  .spin { animation: none; }
}
</style>
