<template>
  <div class="course-view">
    <!-- 外层内容容器：与 ResourceView 的 .resource-content 一一对应，共用同一个 1400px 限宽 + 24px padding。 -->
    <div class="course-content">
    <!-- 课程信息栏（始终展开） -->
    <div class="course-info-bar">
      <div class="info-content">
        <!-- 第一行：返回 + 课程名 -->
        <div class="info-header">
          <button class="back-btn" @click="handleBack">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <h2 class="course-name">{{ courseLoading ? '加载中...' : courseName || '未找到课程' }}</h2>
        </div>

        <!-- 课时、简介、标签等（始终展示） -->
        <div class="info-detail">
          <div class="info-fields">
            <div class="info-field-row">
              <div class="info-field-group info-field-group--hours">
                <span class="info-field-label">课时</span>
                <button type="button" class="info-field-box editable" @click="handleEditHours">
                  <span class="info-field-value">{{ courseHours }} 课时</span>
                  <span class="info-field-hint">编辑</span>
                </button>
              </div>

              <div class="info-field-group info-field-group--tags">
                <span class="info-field-label">课程标签</span>
                <div class="info-tags-box">
                  <span
                    v-for="tag in courseTags"
                    :key="tag"
                    class="info-tag-chip"
                  >
                    {{ tag }}
                  </span>
                  <button type="button" class="info-tag-add" @click="handleAddTag">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M12 5V19M5 12H19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <span>添加标签</span>
                  </button>
                </div>
              </div>
            </div>

            <div class="info-field-group">
              <span class="info-field-label">课程简介</span>
              <button type="button" class="info-field-box editable info-field-box--multiline" @click="handleEditDescription">
                <span
                  class="info-field-value"
                  :class="{ 'is-placeholder': !courseDescriptionDisplay }"
                >{{ courseDescriptionDisplay || '点击添加课程简介' }}</span>
                <span class="info-field-hint">编辑</span>
              </button>
            </div>

            <!-- 课程展示扩展字段（只读，来自 extra_info） -->
            <div class="info-field-group">
              <span class="info-field-label">课程信息</span>
              <div class="info-extra-grid">
                <div
                  v-for="field in extraInfoFields"
                  :key="field.label"
                  class="info-extra-item"
                >
                  <span class="info-extra-label">
                    {{ field.label }}
                    <span v-if="field.sub" class="info-extra-sub">（{{ field.sub }}）</span>
                  </span>
                  <span class="info-extra-value">{{ field.value }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="operationError" class="operation-error">操作失败，请稍后重试</div>
        </div>
      </div>
    </div>

    <PromptInputModal
      v-model="showPromptModal"
      :title="promptModalTitle"
      :label="promptModalLabel"
      :initial-value="promptInitialValue"
      :multiline="promptMultiline"
      :input-type="promptInputType"
      :show-range="promptKind === 'hours'"
      :range-min="COURSE_HOURS_MIN"
      :range-max="COURSE_HOURS_MAX"
      :pending="operationPending"
      @cancel="closePromptModal"
      @submit="onPromptModalSubmit"
    />

    <!-- 内容区域：课程 → 大纲版本列表（唯一课程级入口） -->
    <div class="content-area">
      <div class="resources-section">
        <!-- 加载状态 -->
        <div v-if="resourcesLoading" class="resources-loading">
          <p>加载中...</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="resourcesError" class="resources-error">
          <p>加载失败，请稍后重试</p>
          <button @click="retryLoadCourse" class="retry-btn">重试</button>
        </div>

        <!-- 层级视图：大纲版本入口（课程 → 大纲 → 教案 → PPT/视频） -->
        <div v-else-if="currentCourse" class="outline-versions-panel">
          <div class="outline-versions-header">
            <div class="outline-versions-heading">
              <h3 class="section-title">大纲版本</h3>
              <p class="outline-versions-hint">课程 → 大纲 → 教案 → PPT/视频，逐级管理多版本资源</p>
            </div>
            <button type="button" class="toolbar-gen-btn primary" @click="handleCreateOutlineForCourse">
              + 新建大纲版本
            </button>
          </div>

          <div v-if="outlineVersions.length === 0" class="outline-versions-empty">
            暂无大纲版本，点击「新建大纲版本」开始构建课程资源层级
          </div>
          <div v-else class="outline-version-list">
            <div
              v-for="o in outlineVersions"
              :key="o.id"
              class="outline-version-row"
              role="button"
              tabindex="0"
              @click="openOutlineDetail(o.id)"
              @keydown.enter="openOutlineDetail(o.id)"
            >
              <span class="outline-version-badge">v{{ o.version_number ?? 1 }}</span>
              <div class="outline-version-texts">
                <span class="outline-version-name" :title="o.name">{{ o.name }}</span>
                <span class="outline-version-meta">
                  <span class="meta-chip">{{ o.word_count ? `${o.word_count} 字` : '暂无正文' }}</span>
                  <span class="meta-dot">·</span>
                  <span class="meta-chip">{{ planCountOf(o.id) }} 个教案版本</span>
                  <template v-if="formatOutlineDate(o.update_time)">
                    <span class="meta-dot">·</span>
                    <span class="meta-chip">更新于 {{ formatOutlineDate(o.update_time) }}</span>
                  </template>
                </span>
              </div>
              <div class="outline-version-actions" @click.stop>
                <button type="button" class="toolbar-gen-btn small" @click="handleViewResource(o.id)">编辑大纲</button>
                <button type="button" class="toolbar-gen-btn small primary" @click="openOutlineDetail(o.id)">
                  进入大纲
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div><!-- /.course-content -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import PromptInputModal from '../components/PromptInputModal.vue'
import { useUserStore } from '../stores/user'
import { queryCourse, operateCourse } from '../api/course'
import { listResources, queryResource } from '../api/resource'
import type { CourseListItem, ResourceResponse } from '../api/types'
import { OperationEnum } from '../api/types'
import {
  extractCourseIntroFromOutlineMarkdown,
  getPrefillCourseDescription,
  isPlaceholderCourseDescription,
  normalizeCourseDescriptionText,
} from '../lib/courseOutlineBridge'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 当前课程详情（由 Query Course 接口获取）
const currentCourse = ref<CourseListItem | null>(null)
const courseLoading = ref(false)
const courseError = ref<string | null>(null)

// 根据路由参数获取课程 ID（API 返回 string）
const courseId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : String(id)
})

const courseName = computed(() => currentCourse.value?.name ?? '')
const courseHours = computed(() => currentCourse.value?.lesson_count ?? 0)
const courseDescription = computed(() => currentCourse.value?.description ?? '')
/** API 仍为占位符时，用预填/大纲正文解析出的简介展示 */
const courseDescriptionOverride = ref<string | null>(null)

const courseDescriptionDisplay = computed(() => {
  const apiText = normalizeCourseDescriptionText(courseDescription.value)
  if (apiText) return apiText
  const override = normalizeCourseDescriptionText(courseDescriptionOverride.value)
  return override
})
/**
 * 课程展示扩展字段（只读）。来自 currentCourse.extra_info，空值统一显示「—」。
 * 比率字段补上百分号；学分原样展示。
 */
const EM_DASH = '—'
const extraInfoFields = computed(() => {
  const e = currentCourse.value?.extra_info ?? null
  const text = (v: unknown): string => {
    if (v === null || v === undefined || v === '') return EM_DASH
    return String(v)
  }
  const ratio = (v: unknown): string => {
    if (v === null || v === undefined || (v as any) === '') return EM_DASH
    return `${v}%`
  }
  return [
    { label: '授课对象年级', value: text(e?.grade) },
    { label: '课程类别', value: text(e?.category) },
    { label: '学分', value: text(e?.credits) },
    { label: '授课对象专业', value: text(e?.major) },
    { label: '教学安排', value: ratio(e?.offline_hours_ratio), sub: '线下学时占比' },
    { label: '考核方式', value: ratio(e?.offline_score_ratio), sub: '线下成绩占比' },
  ]
})

// 标签使用 API 的 labels，用 ref 以便后续编辑时可变
const courseTags = ref<string[]>([])
watch(
  () => currentCourse.value?.labels,
  (labels) => {
    courseTags.value = labels ? [...labels] : []
  },
  { immediate: true }
)

/** 课程级别的资源列表（通过 /resource/list?course_id 获取） */
const courseResourceList = ref<ResourceResponse[]>([])

/** 层级视图：课程下的大纲版本（根级，未挂父资源），按版本号倒序 */
const outlineVersions = computed(() =>
  (courseResourceList.value ?? [])
    .filter((r) => String(r.resource_type) === 'outline' && !r.parent_resource_id)
    .sort((a, b) => (b.version_number ?? 1) - (a.version_number ?? 1))
)

/** 大纲行的更新日期展示（YYYY-MM-DD） */
function formatOutlineDate(value?: string | null): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 某大纲版本下的教案版本数（从课程资源列表按 parent_resource_id 统计） */
function planCountOf(outlineId: string): number {
  return (courseResourceList.value ?? []).filter(
    (r) =>
      String(r.parent_resource_id ?? '') === String(outlineId) &&
      String(r.resource_type) === 'teaching_plan'
  ).length
}

function openOutlineDetail(outlineId: string) {
  router.push(`/course/${courseId.value}/outline/${outlineId}`)
}

// 资源区展示用的加载/错误状态（与课程加载一致）
const resourcesLoading = computed(() => courseLoading.value)
const resourcesError = computed(() => {
  if (courseError.value) return courseError.value
  if (!courseLoading.value && courseId.value && !currentCourse.value) {
    return '未找到该课程'
  }
  return null
})

// 加载请求令牌：快速切换课程时，旧请求的 await 回来后不得再写状态（避免串台）。
let loadToken = 0
/** 该 courseId 是否已不是当前路由课程（用于 await 后判断本次请求是否已过期） */
function isStaleCourse(id: string): boolean {
  return String(route.params.id) !== id
}

// 加载当前课程详情（Query Course 接口 + 课程资源列表）
async function backfillCourseDescriptionIfNeeded(courseId: string, description: string) {
  const normalized = normalizeCourseDescriptionText(description)
  if (!normalized || !currentCourse.value) return
  if (!isPlaceholderCourseDescription(currentCourse.value.description)) return
  if (isStaleCourse(courseId)) return
  try {
    await operateCourse({
      operation: OperationEnum.UPDATE,
      id: courseId,
      description: normalized,
    })
    currentCourse.value = { ...currentCourse.value, description: normalized }
    courseDescriptionOverride.value = null
  } catch (err) {
    console.warn('回填课程简介失败:', err)
    courseDescriptionOverride.value = normalized
  }
}

async function resolveCourseDescriptionFallback(courseId: string) {
  if (!currentCourse.value || !isPlaceholderCourseDescription(currentCourse.value.description)) {
    courseDescriptionOverride.value = null
    return
  }

  const fromPrefill = getPrefillCourseDescription(courseId)
  if (fromPrefill) {
    courseDescriptionOverride.value = fromPrefill
    await backfillCourseDescriptionIfNeeded(courseId, fromPrefill)
    return
  }

  const outlines = (courseResourceList.value ?? [])
    .filter((r) => String(r.resource_type) === 'outline' && !r.parent_resource_id)
    .sort((a, b) => (b.version_number ?? 1) - (a.version_number ?? 1))

  for (const outline of outlines) {
    try {
      const detail = await queryResource(outline.id)
      // await 期间课程可能已被切换，过期请求不得回写简介
      if (isStaleCourse(courseId)) return
      const intro = extractCourseIntroFromOutlineMarkdown(detail.content ?? '')
      if (intro) {
        courseDescriptionOverride.value = intro
        await backfillCourseDescriptionIfNeeded(courseId, intro)
        return
      }
    } catch (err) {
      console.warn('从大纲解析课程简介失败:', err)
    }
  }

  courseDescriptionOverride.value = null
}

async function loadCourseDetail() {
  const id = courseId.value
  if (!id) return
  const myToken = ++loadToken
  courseLoading.value = true
  courseError.value = null
  currentCourse.value = null
  courseResourceList.value = []
  courseDescriptionOverride.value = null
  try {
    const data = await queryCourse(id)
    if (myToken !== loadToken) return // 已有更晚的加载请求，丢弃本次结果
    currentCourse.value = data
    await loadCourseResources(id)
    if (myToken !== loadToken) return
    await resolveCourseDescriptionFallback(id)
  } catch (err) {
    if (myToken !== loadToken) return
    courseError.value =
      err instanceof Error ? err.message : '获取课程详情失败'
    console.error('获取课程详情失败:', err)
  } finally {
    if (myToken === loadToken) courseLoading.value = false
  }
}

/** 加载课程级资源列表（/resource/list?course_id&user_id） */
async function loadCourseResources(cid: string) {
  try {
    const params: { course_id: string; user_id?: string } = { course_id: cid }
    if (userStore.currentUser?.id) params.user_id = userStore.currentUser.id
    const list = await listResources(params)
    if (isStaleCourse(cid)) return // 课程已切换，丢弃过期资源列表
    courseResourceList.value = list
  } catch (err) {
    console.error('获取课程资源列表失败:', err)
    if (!isStaleCourse(cid)) courseResourceList.value = []
  }
}

// 重试加载（模板中按钮用）
function retryLoadCourse() {
  loadCourseDetail()
}

// 进入页面或课程 ID 变化时拉取课程详情
onMounted(() => {
  loadCourseDetail()
})
// 页面激活时刷新（从其他页面返回时）
onActivated(() => {
  if (courseId.value) {
    // 添加短暂延迟，确保从 ResourceView 返回时后端数据已更新
    setTimeout(() => {
      loadCourseDetail()
    }, 100)
  }
})
watch(courseId, (newId) => {
  if (newId) loadCourseDetail()
})

const handleBack = () => {
  router.push('/my-courses')
}

const operationPending = ref(false)
const operationError = ref<string | null>(null)

const COURSE_HOURS_MIN = 0
const COURSE_HOURS_MAX = 128

type PromptKind = 'hours' | 'description' | 'tag' | null
const showPromptModal = ref(false)
const promptKind = ref<PromptKind>(null)
const promptModalTitle = ref('')
const promptModalLabel = ref('')
const promptInitialValue = ref('')
const promptMultiline = ref(false)
const promptInputType = ref<'text' | 'number'>('text')

function closePromptModal() {
  showPromptModal.value = false
  promptKind.value = null
}

async function onPromptModalSubmit(raw: string) {
  if (!currentCourse.value || operationPending.value || !promptKind.value) return
  const kind = promptKind.value

  if (kind === 'hours') {
    const n = parseInt(raw, 10)
    if (Number.isNaN(n) || n < COURSE_HOURS_MIN || n > COURSE_HOURS_MAX) {
      operationError.value = `请输入 ${COURSE_HOURS_MIN}–${COURSE_HOURS_MAX} 之间的整数`
      return
    }
    operationError.value = null
    operationPending.value = true
    try {
      await operateCourse({
        operation: OperationEnum.UPDATE,
        id: courseId.value,
        lesson_count: n,
      })
      await loadCourseDetail()
      closePromptModal()
    } catch (err) {
      operationError.value = err instanceof Error ? err.message : '更新失败'
    } finally {
      operationPending.value = false
    }
    return
  }

  if (kind === 'description') {
    operationError.value = null
    operationPending.value = true
    try {
      await operateCourse({
        operation: OperationEnum.UPDATE,
        id: courseId.value,
        description: raw,
      })
      await loadCourseDetail()
      closePromptModal()
    } catch (err) {
      operationError.value = err instanceof Error ? err.message : '更新失败'
    } finally {
      operationPending.value = false
    }
    return
  }

  if (kind === 'tag') {
    const newTag = raw.trim()
    if (!newTag) {
      operationError.value = '请输入标签内容'
      return
    }
    if (courseTags.value.includes(newTag)) {
      operationError.value = '该标签已存在'
      return
    }
    const nextLabels = [...courseTags.value, newTag]
    operationError.value = null
    operationPending.value = true
    try {
      await operateCourse({
        operation: OperationEnum.UPDATE,
        id: courseId.value,
        labels: nextLabels,
      })
      courseTags.value = nextLabels
      if (currentCourse.value) {
        currentCourse.value = { ...currentCourse.value, labels: nextLabels }
      }
      closePromptModal()
    } catch (err) {
      operationError.value = err instanceof Error ? err.message : '添加标签失败'
    } finally {
      operationPending.value = false
    }
  }
}

function handleEditHours() {
  if (!currentCourse.value || operationPending.value) return
  promptKind.value = 'hours'
  promptModalTitle.value = '编辑课时'
  promptModalLabel.value = '课时数'
  promptInitialValue.value = String(currentCourse.value.lesson_count ?? 0)
  promptMultiline.value = false
  promptInputType.value = 'number'
  showPromptModal.value = true
}

function handleEditDescription() {
  if (!currentCourse.value || operationPending.value) return
  promptKind.value = 'description'
  promptModalTitle.value = '编辑课程简介'
  promptModalLabel.value = '课程简介'
  promptInitialValue.value = courseDescriptionDisplay.value || ''
  promptMultiline.value = true
  promptInputType.value = 'text'
  showPromptModal.value = true
}

function handleAddTag() {
  if (!currentCourse.value || operationPending.value) return
  promptKind.value = 'tag'
  promptModalTitle.value = '添加标签'
  promptModalLabel.value = '新标签名称'
  promptInitialValue.value = ''
  promptMultiline.value = false
  promptInputType.value = 'text'
  showPromptModal.value = true
}

const handleViewResource = (resourceId: string | number) => {
  if (courseId.value) {
    router.push({ path: `/resource/${resourceId}`, query: { from_course: courseId.value } })
  } else {
    router.push(`/resource/${resourceId}`)
  }
}

// 生成大纲：跳转至大纲表单大页面（含线上/线下比例等），不弹窗
const handleCreateOutlineForCourse = () => {
  if (!courseId.value) return
  router.push({ path: '/outline-form', query: { course_id: courseId.value } })
}
</script>

<style scoped>
.course-view {
  width: 100%;
  height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 与 ResourceView 的 .resource-content 对齐：单一限宽+内边距容器。 */
.course-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

/* 课程信息栏（可折叠，默认收起占位更小） */
.course-info-bar {
  background-color: rgba(255, 255, 255, 0.4);
  padding: 16px 20px;
  border-radius: 12px;
  margin-bottom: 12px;
  box-sizing: border-box;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-detail {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 4px;
}

.info-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.info-field-row {
  display: grid;
  grid-template-columns: minmax(140px, 200px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.info-field-group--hours {
  min-width: 0;
}

.info-field-group--tags {
  min-width: 0;
}

.info-field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.info-field-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.info-field-box {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  box-sizing: border-box;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font: inherit;
  text-align: left;
  color: #333;
  transition: border-color 0.2s, background-color 0.2s;
}

.info-field-box--multiline {
  align-items: flex-start;
}

.info-field-box.editable {
  cursor: pointer;
}

.info-field-box.editable:hover {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
}

.info-field-value {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.55;
  color: #333;
  word-break: break-word;
}

.info-field-value.is-placeholder {
  color: #999;
}

/* 课程展示扩展字段（只读） */
.info-extra-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px 14px;
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  background: #fafbfc;
  border: 1px solid #e0e0e0;
  border-radius: 16px;
}

.info-extra-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.info-extra-label {
  font-size: 12px;
  color: #999;
}

.info-extra-sub {
  color: #b3b3b3;
}

.info-extra-value {
  font-size: 14px;
  color: #333;
  word-break: break-word;
}

.info-field-hint {
  flex: none;
  font-size: 12px;
  color: #999;
  opacity: 0;
  transition: opacity 0.2s;
}

.info-field-box.editable:hover .info-field-hint,
.info-field-box.editable:focus-visible .info-field-hint {
  opacity: 1;
}

.info-tags-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  align-content: flex-start;
  gap: 8px;
  width: 100%;
  box-sizing: border-box;
  min-height: 42px;
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  transition: border-color 0.2s;
}

.info-tags-box:focus-within {
  border-color: #c5d9ff;
}

.info-tag-chip {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  max-width: 100%;
  padding: 4px 10px;
  background: rgba(197, 217, 255, 0.5);
  border-radius: 12px;
  font-size: 13px;
  color: #333;
  word-break: break-word;
}

.info-tag-add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 13px;
  color: #666;
  background: transparent;
  border: 1px dashed #d0d0d0;
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background-color 0.2s;
}

.info-tag-add:hover {
  border-color: #c5d9ff;
  color: #1a56db;
  background-color: #f8f9ff;
}

.back-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #333;
  transition: color 0.2s;
  border-radius: 4px;
}

.back-btn:hover {
  color: #C5D9FF;
}

.info-header .course-name {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.operation-error {
  margin-top: 12px;
  font-size: 13px;
  color: #d32f2f;
}

/* 内容区域：限宽 + padding 上提到 .course-content，这一层只负责占满剩余高度+允许内部滚动。 */
.content-area {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.resources-section {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

/* 层级视图：大纲版本面板——课程详情页的主入口，做成实体卡片并占据更大视觉权重 */
.outline-versions-panel {
  margin-bottom: 20px;
  padding: 24px 28px 26px;
  background-color: #fff;
  border: 1px solid #e9edf3;
  border-radius: 18px;
  box-shadow: 0 6px 24px rgba(31, 45, 80, 0.06);
  box-sizing: border-box;
}

.outline-versions-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.outline-versions-heading {
  min-width: 0;
  flex: 1;
}

.outline-versions-panel .section-title {
  font-size: 22px;
  font-weight: 700;
}

.outline-versions-hint {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: #6b7280;
}

.outline-versions-empty {
  padding: 40px 16px;
  text-align: center;
  font-size: 14px;
  color: #8a94a6;
  border: 1px dashed #dde3ee;
  border-radius: 14px;
}

.outline-version-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.outline-version-row {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 20px 24px;
  border: 1px solid #e6eaf2;
  border-radius: 16px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s, box-shadow 0.2s, transform 0.15s;
}

.outline-version-row:hover {
  border-color: #c5d9ff;
  background-color: #f8faff;
  box-shadow: 0 8px 22px rgba(59, 130, 246, 0.1);
  transform: translateY(-1px);
}

.outline-version-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(197, 217, 255, 0.5);
  color: #1e40af;
  font-size: 15px;
  font-weight: 700;
  flex: none;
}

.outline-version-texts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.outline-version-name {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.outline-version-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13.5px;
  color: #8a94a6;
}

.outline-version-meta .meta-dot {
  color: #c7cdd9;
}

.outline-version-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.outline-version-actions .toolbar-gen-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
  text-align: left;
}

.toolbar-gen-btn.small {
  padding: 6px 12px;
  font-size: 13px;
  border-radius: 20px;
}

/* 生成按钮——与 ResourceView 的 .action-btn 同款胶囊按钮（课程页全局复用）。 */
.course-view .toolbar-gen-btn {
  padding: 8px 16px;
  font-size: 14px;
  color: #333;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.course-view .toolbar-gen-btn:hover:not(:disabled) {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.course-view .toolbar-gen-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.course-view .toolbar-gen-btn.primary {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
  color: #1a56db;
}

.resources-loading,
.resources-error,
.resources-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  text-align: center;
  color: #999;
}

.resources-error p {
  color: #d32f2f;
  margin-bottom: 16px;
}

.retry-btn {
  padding: 8px 16px;
  background-color: #C5D9FF;
  border: none;
  border-radius: 4px;
  color: #333;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.retry-btn:hover {
  background-color: #a8c5ff;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .course-info-bar {
    padding: 12px 16px;
  }

  .info-header .course-name {
    font-size: 18px;
  }

  .info-field-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .course-content {
    padding: 12px;
  }
  .info-header .course-name {
    font-size: 16px;
  }
}
</style>
