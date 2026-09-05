<template>
  <div class="outline-detail-view">
    <div class="outline-detail-content">
      <!-- 顶部：返回 + 层级步骤条 -->
      <div class="detail-topbar">
        <button class="back-btn" aria-label="返回课程" @click="goBackToCourse">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <HierarchyStepper
          current="outline"
          :course-id="courseId"
          :course-name="courseName"
          :outline-id="outlineId"
          :outline-name="outline?.name"
        />
      </div>

      <div v-if="loading" class="detail-loading">加载中...</div>
      <div v-else-if="loadError" class="detail-error">
        <p>加载失败，请稍后重试</p>
        <button type="button" class="action-btn" @click="loadAll">重试</button>
      </div>

      <template v-else-if="outline">
        <!-- 大纲信息头 -->
        <div class="detail-header-card">
          <div class="header-main">
            <span class="version-badge large">v{{ outline.version_number ?? 1 }}</span>
            <div class="header-texts">
              <h2 class="detail-title" :title="outline.name">{{ outline.name }}</h2>
              <div class="detail-meta">
                教学大纲 · {{ outline.word_count || 0 }} 字 · 更新于 {{ formatTime(outline.update_time) }}
              </div>
            </div>
          </div>
        </div>

        <!-- 教案版本（整区可折叠、默认展开）：按创建时间降序展示（最新在顶 → 最早在底），
             徽标仍是创建顺序序号（最早=1、最新=N）。复用 CollapsibleSection，与 PPT 区结构一致。 -->
        <CollapsibleSection title="教案" :count="planVersions.length" :default-open="true">
          <template #actions>
            <button
              type="button"
              class="row-btn primary"
              :disabled="creatingPlan"
              @click="createPlanVersion"
            >
              {{ creatingPlan ? '创建中...' : '新建' }}
            </button>
          </template>

          <div v-if="planVersions.length === 0" class="children-empty">
            <p>该大纲下暂无教案版本</p>
            <p class="children-empty-hint">点击右上方「新建」，依据本大纲生成教案</p>
          </div>

          <div v-else class="version-list">
            <div
              v-for="plan in sortedPlanVersionsDesc"
              :key="plan.id"
              class="version-row"
              role="button"
              tabindex="0"
              @click="openPlan(plan.id)"
              @keydown.enter="openPlan(plan.id)"
            >
              <span class="version-badge">{{ planSeqMap[plan.id] ?? 1 }}</span>
              <div class="version-texts">
                <span class="version-name" :title="plan.name">{{ plan.name }}</span>
                <span class="version-meta">
                  {{ plan.word_count || 0 }} 字 · 更新于 {{ formatTime(plan.update_time) }}
                  <template v-if="plan.child_count"> · {{ plan.child_count }} 个子资源</template>
                </span>
              </div>
              <div class="version-actions" @click.stop>
                <button type="button" class="row-btn danger" @click="askDeleteChild(plan)">删除</button>
                <button type="button" class="row-btn primary" @click="openPlan(plan.id)">
                  进入教案
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </CollapsibleSection>

        <!-- 大纲正文预览 -->
        <div class="children-section content-section">
          <div class="section-title-row">
            <h3 class="section-title">大纲正文</h3>
            <div class="section-title-actions">
              <div ref="downloadWrapRef" class="download-wrap">
                <button
                  type="button"
                  class="row-btn"
                  :disabled="downloading"
                  @click="toggleDownloadDropdown"
                >
                  {{ downloading ? '下载中...' : '下载' }}
                </button>
                <div v-if="showDownloadDropdown" class="download-dropdown">
                  <button type="button" class="download-option" @click="handleDownloadAs('docx')">下载为 Word (.docx)</button>
                  <button type="button" class="download-option" @click="handleDownloadAs('md')">下载为 Markdown (.md)</button>
                </div>
              </div>
              <button type="button" class="row-btn primary" @click="editOutline">编辑正文</button>
            </div>
          </div>
          <div v-if="outlineHtml" class="markdown-body" v-html="outlineHtml"></div>
          <div v-else class="content-empty">
            <p>该大纲尚未生成正文</p>
            <p class="content-empty-hint">点击右上方「编辑正文」开始撰写或用 AI 生成大纲内容</p>
          </div>
        </div>
      </template>
    </div>

    <DeleteConfirmModal
      v-model="showDeleteModal"
      title="删除资源"
      entity-kind="资源"
      :entity-name="deleteTarget?.name || ''"
      :pending="deletePending"
      :error="!!deleteError"
      :error-text="deleteError || '操作失败，请稍后重试'"
      @cancel="closeDeleteModal"
      @confirm="confirmDeleteChild"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import HierarchyStepper from '../components/HierarchyStepper.vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import CollapsibleSection from '../components/CollapsibleSection.vue'
import { queryResource, listResources, operateResource, downloadResource } from '../api/resource'
import { queryCourse } from '../api/course'
import { OperationEnum, ResourceTypeEnum, type DownloadFormat, type ResourceResponse } from '../api/types'
import { createTeachingPlanFromOutline, buildTeachingPlanFromOutlineQuery } from '../lib/teachingPlanFlow'
import { renderMarkdown } from '../utils/markdown'
import { useUserStore } from '../stores/user'

const props = defineProps<{
  courseId: string
  outlineId: string
}>()

const router = useRouter()
const userStore = useUserStore()

const outline = ref<ResourceResponse | null>(null)
const children = ref<ResourceResponse[]>([])
const loading = ref(true)
const loadError = ref(false)
const creatingPlan = ref(false)

const fallbackCourseName = ref('')
const courseName = computed(() => outline.value?.related_course?.name || fallbackCourseName.value || '')

/** 大纲正文 Markdown 渲染（无正文时为空字符串，模板降级到空状态） */
const outlineHtml = computed(() => {
  const content = (outline.value?.content ?? '').trim()
  return content ? renderMarkdown(content) : ''
})

const planVersions = computed(() =>
  children.value.filter((r) => String(r.resource_type) === ResourceTypeEnum.TeachingPlan)
)

/**
 * 教案版本按「创建时间升序」排序（最早在前 → 最新在后），
 * create_time 相同再用 version_number 升序兜底。
 * 列表展示与序号徽标统一用这个数组，保证「展示顺序」与「序号」一致。
 */
const sortedPlanVersions = computed(() =>
  [...planVersions.value].sort(
    (a, b) =>
      new Date(a.create_time ?? 0).getTime() - new Date(b.create_time ?? 0).getTime() ||
      (a.version_number ?? 0) - (b.version_number ?? 0)
  )
)

/** 教案版本「创建顺序序号」映射：最早 = 1，依次到 N。 */
const planSeqMap = computed<Record<string, number>>(() => {
  const map: Record<string, number> = {}
  sortedPlanVersions.value.forEach((item, idx) => {
    map[item.id] = idx + 1
  })
  return map
})

/** 列表展示用「创建时间降序」数组（最新在顶 → 最早在底）；徽标序号仍用 planSeqMap（按升序算）。 */
const sortedPlanVersionsDesc = computed(() => [...sortedPlanVersions.value].reverse())

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadAll() {
  loading.value = true
  loadError.value = false
  try {
    const [detail, childList] = await Promise.all([
      queryResource(props.outlineId),
      listResources({ parent_resource_id: props.outlineId }),
    ])
    outline.value = detail
    children.value = childList
    // 大纲未绑定 related_course 时，用路由 courseId 回查课程名，避免步骤条「课程」无名
    if (!detail.related_course?.name && props.courseId) {
      try {
        const course = await queryCourse(props.courseId)
        fallbackCourseName.value = course?.name ?? ''
      } catch {
        /* 课程不可见/不存在时忽略，步骤条退化为无名「课程」 */
      }
    }
  } catch (err) {
    console.error('[OutlineDetail] 加载失败', err)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function goBackToCourse() {
  router.push(`/course/${props.courseId}`)
}

function editOutline() {
  router.push({ path: `/resource/${props.outlineId}`, query: { from_course: props.courseId } })
}

// 下载大纲（浏览模式直接下载，无需进入编辑页；格式与编辑页一致 docx/md）
const downloading = ref(false)
const showDownloadDropdown = ref(false)
const downloadWrapRef = ref<HTMLElement | null>(null)

function toggleDownloadDropdown() {
  showDownloadDropdown.value = !showDownloadDropdown.value
}

async function handleDownloadAs(format: DownloadFormat) {
  if (downloading.value) return
  showDownloadDropdown.value = false
  downloading.value = true
  try {
    await downloadResource(props.outlineId, format, outline.value?.name)
  } catch (err) {
    console.error('[OutlineDetail] 下载大纲失败', err)
  } finally {
    downloading.value = false
  }
}

function onDocumentClick(e: MouseEvent) {
  if (!showDownloadDropdown.value) return
  if (downloadWrapRef.value && !downloadWrapRef.value.contains(e.target as Node)) {
    showDownloadDropdown.value = false
  }
}

function openPlan(planId: string) {
  router.push(`/course/${props.courseId}/outline/${props.outlineId}/plan/${planId}`)
}

async function createPlanVersion() {
  if (!outline.value || creatingPlan.value) return
  creatingPlan.value = true
  try {
    const { id } = await createTeachingPlanFromOutline(outline.value, {
      relatedUserId: userStore.currentUser?.id,
      courseId: props.courseId,
    })
    await router.push({
      path: `/resource/${id}`,
      query: buildTeachingPlanFromOutlineQuery(props.outlineId, props.courseId),
    })
  } catch (err) {
    console.error('[OutlineDetail] 新建教案版本失败', err)
  } finally {
    creatingPlan.value = false
  }
}

// 删除子资源
const showDeleteModal = ref(false)
const deleteTarget = ref<ResourceResponse | null>(null)
const deletePending = ref(false)
const deleteError = ref<string | null>(null)

function askDeleteChild(resource: ResourceResponse) {
  deleteTarget.value = resource
  deleteError.value = null
  showDeleteModal.value = true
}

function closeDeleteModal() {
  showDeleteModal.value = false
  deleteTarget.value = null
  deleteError.value = null
}

async function confirmDeleteChild() {
  if (!deleteTarget.value || deletePending.value) return
  deletePending.value = true
  deleteError.value = null
  try {
    await operateResource({ operation: OperationEnum.DELETE, id: deleteTarget.value.id })
    closeDeleteModal()
    await loadAll()
  } catch (err) {
    deleteError.value = err instanceof Error ? err.message : '删除失败'
  } finally {
    deletePending.value = false
  }
}

onMounted(() => {
  loadAll()
  document.addEventListener('click', onDocumentClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
watch(() => [props.courseId, props.outlineId], loadAll)
</script>

<style src="../styles/version-row.css"></style>
<style scoped>
.outline-detail-view {
  min-height: calc(100vh - var(--app-nav-height, 64px));
  background: #f7f8fa;
}

.outline-detail-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-topbar {
  display: flex;
  align-items: center;
  gap: 14px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #e3e7ef;
  background: #fff;
  color: #4b5563;
  cursor: pointer;
  flex: none;
}

.back-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}

.detail-loading,
.detail-error {
  padding: 60px 0;
  text-align: center;
  color: #6b7280;
}

.detail-header-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e9edf3;
  border-radius: 14px;
  padding: 20px 24px;
}

.header-main {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.header-texts {
  min-width: 0;
}

.detail-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-meta {
  margin-top: 4px;
  font-size: 13px;
  color: #8a94a6;
}

.download-wrap {
  position: relative;
}

.download-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 6px;
  min-width: 200px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.12);
  z-index: 20;
  overflow: hidden;
}

.download-option {
  display: block;
  width: 100%;
  padding: 10px 16px;
  text-align: left;
  font-size: 14px;
  color: #333;
  background: none;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.download-option:hover {
  background: #f5f7fb;
  color: #3b82f6;
}

.action-btn {
  padding: 8px 18px;
  border-radius: 10px;
  border: 1px solid #3b82f6;
  background: #3b82f6;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn:hover:not(:disabled) {
  filter: brightness(0.96);
}

.children-section {
  background: #fff;
  border: 1px solid #e9edf3;
  border-radius: 14px;
  padding: 18px 24px 22px;
}

.section-title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.children-empty {
  padding: 36px 0;
  text-align: center;
  color: #6b7280;
}

.children-empty-hint {
  margin-top: 6px;
  font-size: 13px;
  color: #9aa3b2;
}

/* 正文预览卡片 */
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-title-row .section-title {
  margin: 0;
}

.section-title-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.content-empty {
  padding: 32px 0;
  text-align: center;
  color: #6b7280;
}

.content-empty-hint {
  margin-top: 6px;
  font-size: 13px;
  color: #9aa3b2;
}

/* Markdown 正文（renderMarkdown 输出，v-html 注入） */
.markdown-body {
  font-size: 15px;
  line-height: 1.75;
  color: #1f2937;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 1.2em 0 0.5em;
  font-weight: 700;
  line-height: 1.3;
  color: #111827;
}

.markdown-body :deep(h1) { font-size: 1.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; }
.markdown-body :deep(h3) { font-size: 1.12em; }
.markdown-body :deep(h4) { font-size: 1em; }

.markdown-body :deep(p) { margin: 0.6em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.6em 0; padding-left: 1.5em; }
.markdown-body :deep(li) { margin: 0.25em 0; }

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  font-size: 0.95em;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) { background: #f8fafc; font-weight: 600; }

.markdown-body :deep(code) {
  background: #f3f4f6;
  border-radius: 4px;
  padding: 2px 5px;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) { background: transparent; padding: 0; color: inherit; }

.markdown-body :deep(blockquote) {
  margin: 0.8em 0;
  padding: 4px 14px;
  border-left: 3px solid #c5d9ff;
  color: #4b5563;
  background: #f8faff;
  border-radius: 0 8px 8px 0;
}
</style>
