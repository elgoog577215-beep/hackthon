<template>
  <div class="plan-detail-view">
    <div class="plan-detail-content">
      <!-- 顶部：返回 + 层级步骤条 -->
      <div class="detail-topbar">
        <button class="back-btn" aria-label="返回大纲" @click="goBackToOutline">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <HierarchyStepper
          current="plan"
          :course-id="courseId"
          :course-name="courseName"
          :outline-id="outlineId"
          :outline-name="outlineName"
          :plan-id="planId"
          :plan-name="plan?.name"
        />
      </div>

      <div v-if="loading" class="detail-loading">加载中...</div>
      <div v-else-if="loadError" class="detail-error">
        <p>加载失败，请稍后重试</p>
        <button type="button" class="action-btn" @click="loadAll">重试</button>
      </div>

      <template v-else-if="plan">
        <!-- 教案信息头 -->
        <div class="detail-header-card">
          <div class="header-main">
            <span class="version-badge large">v{{ plan.version_number ?? 1 }}</span>
            <div class="header-texts">
              <h2 class="detail-title" :title="plan.name">{{ plan.name }}</h2>
              <div class="detail-meta">
                教案 · {{ plan.word_count || 0 }} 字 · 更新于 {{ formatTime(plan.update_time) }}
              </div>
            </div>
          </div>
        </div>

        <!-- PPT 版本（提到正文上方、可折叠：原本缩在最下面、需下拉才能看到）；
             「新建 PPT 版本」按钮放到标题栏右侧，大小与「课堂视频分析」一致 -->
        <CollapsibleSection title="PPT" :count="pptVersions.length">
          <template #actions>
            <button type="button" class="row-btn primary" :disabled="creatingPpt" @click="showPptMethodModal = true">
              {{ creatingPpt ? '创建中...' : '新建' }}
            </button>
          </template>

          <div v-if="pptVersions.length === 0" class="children-empty">
            <p>该教案下暂无 PPT 版本</p>
            <p class="children-empty-hint">点击右上方「新建 PPT 版本」，依据本教案生成课件</p>
          </div>

          <div v-else class="version-list">
            <div
              v-for="ppt in sortedPptVersionsDesc"
              :key="ppt.id"
              class="version-row"
              role="button"
              tabindex="0"
              @click="openResource(ppt.id, 'ppt')"
              @keydown.enter="openResource(ppt.id, 'ppt')"
            >
              <span class="version-badge red">{{ pptSeqMap[ppt.id] ?? 1 }}</span>
              <div class="version-texts">
                <span class="version-name" :title="ppt.name">{{ ppt.name }}</span>
                <span class="version-meta">PPT · 更新于 {{ formatTime(ppt.update_time) }}</span>
              </div>
              <div class="version-actions" @click.stop>
                <button type="button" class="row-btn danger" @click="askDeleteChild(ppt)">删除</button>
                <button type="button" class="row-btn primary" @click="openResource(ppt.id, 'ppt')">
                  进入课件
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </CollapsibleSection>

        <!-- 绑定的课堂视频（提到正文上方、可折叠；操作按钮放在标题栏右侧） -->
        <CollapsibleSection title="课堂视频分析" :count="boundVideos.length">
          <template #actions>
            <button type="button" class="row-btn" @click="openBindVideoModal">绑定已有视频</button>
            <button type="button" class="row-btn primary" @click="openUploadVideoModal">+ 上传并分析</button>
          </template>

          <div v-if="boundVideos.length === 0" class="children-empty">
            <p>暂未绑定课堂视频</p>
            <p class="children-empty-hint">
              点击「上传并分析」上传课堂实录直接发起分析，或「绑定已有视频」关联已分析的录像，分析结果将与本教案版本关联
            </p>
          </div>

          <div v-else class="video-grid">
            <div v-for="video in boundVideos" :key="video.id" class="video-card">
              <div class="video-cover">
                <img v-if="video.cover" :src="resolveVideoMediaUrl(video.cover)" alt="" loading="lazy" />
                <div v-else class="video-cover-fallback">视频</div>
                <span class="video-status" :class="`is-${video.status}`">{{ videoStatusLabel(video.status) }}</span>
              </div>
              <div class="video-info">
                <span class="video-name" :title="video.name">{{ video.name }}</span>
                <div class="video-actions">
                  <button
                    v-if="String(video.status) === 'success'"
                    type="button"
                    class="row-btn primary"
                    @click="viewVideoReport(video.id)"
                  >
                    查看分析报告
                  </button>
                  <button v-else type="button" class="row-btn" @click="goVideoModule">前往分析</button>
                  <button type="button" class="row-btn danger" :disabled="videoActionPending" @click="unbindVideo(video.id)">
                    解绑
                  </button>
                </div>
              </div>
            </div>
          </div>
        </CollapsibleSection>

        <!-- 教案正文预览（移到资源下方：资源前置，正文作为主体内容置于其后） -->
        <div class="children-section content-section">
          <div class="section-title-row">
            <h3 class="section-title">教案正文</h3>
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
              <button type="button" class="row-btn primary" @click="editPlan">编辑正文</button>
            </div>
          </div>
          <div v-if="planHtml" class="markdown-body" v-html="planHtml"></div>
          <div v-else class="content-empty">
            <p>该教案尚未生成正文</p>
            <p class="content-empty-hint">点击上方「查看 / 编辑正文」开始撰写或用 AI 生成教案内容</p>
          </div>
        </div>
      </template>
    </div>

    <!-- 生成 PPT 方式选择：本地生成 / 远程生成 -->
    <PptGenerateMethodModal
      :visible="showPptMethodModal"
      :pending="creatingPpt"
      @close="showPptMethodModal = false"
      @select="handlePptMethodSelect"
    />

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

    <!-- 绑定已有视频弹窗 -->
    <div v-if="showBindVideoModal" class="modal-overlay">
      <div class="modal-content bind-video-modal">
        <div class="modal-header">
          <h3>绑定已有视频到本教案</h3>
          <button type="button" class="modal-close" aria-label="关闭" @click="closeBindVideoModal">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="bindVideoLoading" class="bind-loading">加载视频列表中...</div>
          <div v-else class="bind-video-list">
            <div
              v-for="v in bindableVideos"
              :key="v.id"
              class="bind-video-item"
              :class="{ selected: selectedVideoIdToBind === v.id }"
              @click="selectedVideoIdToBind = v.id"
            >
              <span class="bind-video-name" :title="v.name">{{ v.name }}</span>
              <span class="bind-video-status">{{ videoStatusLabel(v.status) }}</span>
            </div>
            <div v-if="bindableVideos.length === 0" class="bind-empty">
              暂无可绑定的视频，请先在「视频分析」模块上传或导入
            </div>
          </div>
          <p v-if="bindVideoError" class="form-error">操作失败，请稍后重试</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="closeBindVideoModal">取消</button>
          <button
            type="button"
            class="action-btn"
            :disabled="!selectedVideoIdToBind || videoActionPending"
            @click="confirmBindVideo"
          >
            {{ videoActionPending ? '绑定中...' : '确定绑定' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 上传并分析弹窗：上传课堂视频 → 自动绑定到本教案 → 发起分析 -->
    <div v-if="showUploadVideoModal" class="modal-overlay">
      <div class="modal-content bind-video-modal">
        <div class="modal-header">
          <h3>上传课堂视频并分析</h3>
          <button type="button" class="modal-close" aria-label="关闭" :disabled="uploadSubmitting" @click="closeUploadVideoModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="upload-field">
            <label class="upload-label">视频名称</label>
            <input
              v-model="uploadVideoName"
              type="text"
              class="upload-input"
              placeholder="请输入视频名称"
              :disabled="uploadSubmitting"
            />
          </div>
          <div class="upload-field">
            <label class="upload-label">视频文件</label>
            <input
              type="file"
              accept="video/*"
              class="upload-input"
              :disabled="uploadSubmitting"
              @change="onUploadFileChange"
            />
          </div>
          <div v-if="uploadSubmitting" class="upload-progress">
            <div class="upload-progress-bar">
              <div class="upload-progress-fill" :style="{ width: `${uploadPercent}%` }"></div>
            </div>
            <p class="upload-progress-text">{{ uploadStageText }}</p>
          </div>
          <p v-if="uploadError" class="form-error">{{ uploadError }}</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" :disabled="uploadSubmitting" @click="closeUploadVideoModal">取消</button>
          <button
            type="button"
            class="action-btn"
            :disabled="!uploadFile || !uploadVideoName.trim() || uploadSubmitting"
            @click="confirmUploadVideo"
          >
            {{ uploadSubmitting ? '处理中...' : '上传并分析' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import HierarchyStepper from '../components/HierarchyStepper.vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import CollapsibleSection from '../components/CollapsibleSection.vue'
import PptGenerateMethodModal, { type PptGenerateMethod } from '../components/PptGenerateMethodModal.vue'
import { queryResource, listResources, operateResource, downloadResource } from '../api/resource'
import { queryCourse } from '../api/course'
import { renderMarkdown } from '../utils/markdown'
import { listVideos, bindVideo, submitVideo, startVideoAnalysis, resolveVideoMediaUrl, type VideoSummary } from '../api/video'
import { OperationEnum, ResourceTypeEnum, type DownloadFormat, type ResourceResponse } from '../api/types'
import { createPptResource } from '../lib/pptFlow'
import { openChaoxingPptCoursewareDemo } from '../utils/chaoxingPpt'
import { useUserStore } from '../stores/user'

const props = defineProps<{
  courseId: string
  outlineId: string
  planId: string
}>()

const router = useRouter()
const userStore = useUserStore()

const plan = ref<ResourceResponse | null>(null)
const children = ref<ResourceResponse[]>([])
const boundVideos = ref<VideoSummary[]>([])
const loading = ref(true)
const loadError = ref(false)

const fallbackCourseName = ref('')
const fallbackOutlineName = ref('')
const courseName = computed(() => plan.value?.related_course?.name || fallbackCourseName.value || '')
const outlineName = computed(
  () => (plan.value?.parent_resource_name as string | undefined) || fallbackOutlineName.value || ''
)

/** 教案正文 Markdown 渲染（无正文时为空字符串，模板降级到空状态） */
const planHtml = computed(() => {
  const content = (plan.value?.content ?? '').trim()
  return content ? renderMarkdown(content) : ''
})

const pptVersions = computed(() =>
  children.value.filter((r) => String(r.resource_type) === ResourceTypeEnum.Ppt)
)

/**
 * PPT 版本按「创建时间升序」排序（最早在前 → 最新在后），
 * create_time 相同再用 version_number 升序兜底。
 * 列表展示与序号徽标统一用这个数组，保证「顺序」与「序号」一致。
 */
const sortedPptVersions = computed(() =>
  [...pptVersions.value].sort(
    (a, b) =>
      new Date(a.create_time ?? 0).getTime() - new Date(b.create_time ?? 0).getTime() ||
      (a.version_number ?? 0) - (b.version_number ?? 0)
  )
)

/** PPT 列表展示用：创建时间降序（最新在顶 → 最早在底），与教案区一致；徽标序号仍按升序(最早=1)。 */
const sortedPptVersionsDesc = computed(() => [...sortedPptVersions.value].reverse())

/**
 * PPT 版本「创建顺序序号」映射：最早 = 1，依次到 N。
 */
const pptSeqMap = computed<Record<string, number>>(() => {
  const map: Record<string, number> = {}
  sortedPptVersions.value.forEach((item, idx) => {
    map[item.id] = idx + 1
  })
  return map
})

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function videoStatusLabel(status: unknown): string {
  const s = String(status ?? '')
  if (s === 'success') return '分析完成'
  if (s === 'waiting') return '分析中'
  if (s === 'failed') return '分析失败'
  return '未分析'
}

async function loadAll() {
  loading.value = true
  loadError.value = false
  try {
    const [detail, childList, videos] = await Promise.all([
      queryResource(props.planId),
      listResources({ parent_resource_id: props.planId }),
      listVideos({ resource_id: props.planId }),
    ])
    plan.value = detail
    children.value = childList
    boundVideos.value = videos
    // related_course / parent_resource_name 缺失时回查，避免步骤条「课程 / 大纲」无名
    if (!detail.related_course?.name && props.courseId) {
      try {
        const course = await queryCourse(props.courseId)
        fallbackCourseName.value = course?.name ?? ''
      } catch {
        /* 忽略 */
      }
    }
    if (!detail.parent_resource_name && props.outlineId) {
      try {
        const outlineDetail = await queryResource(props.outlineId)
        fallbackOutlineName.value = outlineDetail?.name ?? ''
      } catch {
        /* 忽略 */
      }
    }
  } catch (err) {
    console.error('[PlanDetail] 加载失败', err)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function goBackToOutline() {
  router.push(`/course/${props.courseId}/outline/${props.outlineId}`)
}

function editPlan() {
  router.push({ path: `/resource/${props.planId}`, query: { from_course: props.courseId, outline_id: props.outlineId } })
}

function openResource(id: string, resourceType?: string) {
  const query: Record<string, string> = { from_course: props.courseId, outline_id: props.outlineId }
  if (resourceType) query.resourceType = resourceType
  router.push({ path: `/resource/${id}`, query })
}

// 下载教案正文（浏览模式直接下载，无需进入编辑页；格式 docx/md，与大纲页一致）
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
    await downloadResource(props.planId, format, plan.value?.name)
  } catch (err) {
    console.error('[PlanDetail] 下载教案失败', err)
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

// ---------- 新建 PPT 版本 ----------
const showPptMethodModal = ref(false)
const creatingPpt = ref(false)

async function handlePptMethodSelect(method: PptGenerateMethod) {
  if (method === 'chaoxing') {
    showPptMethodModal.value = false
    openChaoxingPptCoursewareDemo()
    return
  }
  if (creatingPpt.value || !plan.value) return
  creatingPpt.value = true
  try {
    const id = await createPptResource({
      name: `${plan.value.name} - PPT`,
      relatedUserId: userStore.currentUser?.id,
      courseId: props.courseId,
      parentResourceId: props.planId,
    })
    showPptMethodModal.value = false
    await router.push({
      path: `/resource/${id}`,
      query: { resourceType: ResourceTypeEnum.Ppt, from_course: props.courseId, outline_id: props.outlineId, plan_id: props.planId },
    })
  } catch (err) {
    console.error('[PlanDetail] 创建 PPT 失败', err)
  } finally {
    creatingPpt.value = false
  }
}

// ---------- 删除子资源 ----------
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

// ---------- 视频绑定 ----------
const showBindVideoModal = ref(false)
const bindVideoLoading = ref(false)
const bindVideoError = ref(false)
const allVideos = ref<VideoSummary[]>([])
const selectedVideoIdToBind = ref<string | null>(null)
const videoActionPending = ref(false)

const bindableVideos = computed(() =>
  allVideos.value.filter((v) => v.related_resource_id !== props.planId)
)

async function openBindVideoModal() {
  showBindVideoModal.value = true
  bindVideoError.value = false
  selectedVideoIdToBind.value = null
  bindVideoLoading.value = true
  try {
    allVideos.value = await listVideos()
  } catch (err) {
    console.error('[PlanDetail] 加载视频列表失败', err)
    bindVideoError.value = true
  } finally {
    bindVideoLoading.value = false
  }
}

function closeBindVideoModal() {
  showBindVideoModal.value = false
  selectedVideoIdToBind.value = null
}

async function confirmBindVideo() {
  if (!selectedVideoIdToBind.value || videoActionPending.value) return
  videoActionPending.value = true
  bindVideoError.value = false
  try {
    await bindVideo({
      id: selectedVideoIdToBind.value,
      related_resource_id: props.planId,
      related_course_id: props.courseId,
    })
    closeBindVideoModal()
    boundVideos.value = await listVideos({ resource_id: props.planId })
  } catch (err) {
    console.error('[PlanDetail] 绑定视频失败', err)
    bindVideoError.value = true
  } finally {
    videoActionPending.value = false
  }
}

async function unbindVideo(videoId: string) {
  if (videoActionPending.value) return
  videoActionPending.value = true
  try {
    await bindVideo({ id: videoId, unbind: true })
    boundVideos.value = await listVideos({ resource_id: props.planId })
  } catch (err) {
    console.error('[PlanDetail] 解绑视频失败', err)
  } finally {
    videoActionPending.value = false
  }
}

function viewVideoReport(videoId: string) {
  router.push(`/resource-analysis/report-new/${encodeURIComponent(videoId)}`)
}

function goVideoModule() {
  router.push('/resource-analysis')
}

// ---------- 上传并分析（上传 → 绑定到本教案 → 发起分析） ----------
const showUploadVideoModal = ref(false)
const uploadVideoName = ref('')
const uploadFile = ref<File | null>(null)
const uploadSubmitting = ref(false)
const uploadError = ref<string | null>(null)
const uploadPercent = ref(0)
const uploadStage = ref<'idle' | 'uploading' | 'binding' | 'analyzing'>('idle')

const uploadStageText = computed(() => {
  if (uploadStage.value === 'uploading') return `上传中… ${uploadPercent.value}%`
  if (uploadStage.value === 'binding') return '上传完成，正在绑定到本教案…'
  if (uploadStage.value === 'analyzing') return '正在发起分析…'
  return ''
})

function openUploadVideoModal() {
  showUploadVideoModal.value = true
  uploadError.value = null
  uploadVideoName.value = ''
  uploadFile.value = null
  uploadPercent.value = 0
  uploadStage.value = 'idle'
}

function closeUploadVideoModal() {
  if (uploadSubmitting.value) return
  showUploadVideoModal.value = false
  uploadFile.value = null
  uploadVideoName.value = ''
}

function onUploadFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  uploadFile.value = file
  // 未填写名称时，用文件名（去扩展名）兜底
  if (file && !uploadVideoName.value.trim()) {
    uploadVideoName.value = file.name.replace(/\.[^.]+$/, '')
  }
}

async function confirmUploadVideo() {
  const file = uploadFile.value
  const name = uploadVideoName.value.trim()
  if (!file || !name || uploadSubmitting.value) return
  uploadSubmitting.value = true
  uploadError.value = null
  uploadPercent.value = 0
  uploadStage.value = 'uploading'
  try {
    // 1) 上传（init → 分片 → finish → 落库）
    const { taskId } = await submitVideo({
      file,
      videoName: name,
      onUploadProgress: ({ uploadedChunks, totalChunks }) => {
        uploadPercent.value = totalChunks
          ? Math.round((uploadedChunks / totalChunks) * 100)
          : 0
      },
    })
    // 2) 绑定到本教案（related_course_id 由后端按资源自动同步，这里显式带上更稳）
    uploadStage.value = 'binding'
    await bindVideo({
      id: taskId,
      related_resource_id: props.planId,
      related_course_id: props.courseId,
    })
    // 3) 发起分析（默认云端）
    uploadStage.value = 'analyzing'
    try {
      await startVideoAnalysis(taskId, 'cloud')
    } catch (err) {
      // 分析发起失败不回滚已上传/已绑定的视频；提示用户可在卡片上「前往分析」重试
      console.error('[PlanDetail] 发起视频分析失败', err)
    }
    showUploadVideoModal.value = false
    uploadFile.value = null
    uploadVideoName.value = ''
    boundVideos.value = await listVideos({ resource_id: props.planId })
  } catch (err) {
    console.error('[PlanDetail] 上传视频失败', err)
    uploadError.value = err instanceof Error ? err.message : '上传失败，请稍后重试'
  } finally {
    uploadSubmitting.value = false
    uploadStage.value = 'idle'
  }
}

onMounted(() => {
  loadAll()
  document.addEventListener('click', onDocumentClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
watch(() => [props.courseId, props.outlineId, props.planId], loadAll)
</script>

<style src="../styles/version-row.css"></style>
<style scoped>
.plan-detail-view {
  min-height: calc(100vh - var(--app-nav-height, 64px));
  background: #f7f8fa;
}

.plan-detail-content {
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

.action-btn.secondary {
  background: #fff;
  color: #3b82f6;
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

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.section-title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
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

.row-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ---------- 视频卡片 ---------- */
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.video-card {
  border: 1px solid #e9edf3;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

.video-cover {
  position: relative;
  aspect-ratio: 16 / 9;
  background: #f1f3f8;
}

.video-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.video-cover-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9aa3b2;
  font-size: 13px;
}

.video-status {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: #f3f4f6;
  color: #4b5563;
}

.video-status.is-success {
  background: #ecfdf5;
  color: #059669;
}

.video-status.is-waiting {
  background: #fffbeb;
  color: #d97706;
}

.video-status.is-failed {
  background: #fef2f2;
  color: #dc2626;
}

.video-info {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.video-name {
  font-size: 14px;
  font-weight: 500;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-actions {
  display: flex;
  gap: 8px;
}

/* ---------- 绑定视频弹窗 ---------- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content.bind-video-modal {
  width: 520px;
  max-width: calc(100vw - 48px);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #eef1f6;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
}

.modal-close {
  border: none;
  background: none;
  font-size: 22px;
  line-height: 1;
  color: #9aa3b2;
  cursor: pointer;
}

.modal-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}

.bind-loading,
.bind-empty {
  padding: 24px 0;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.bind-video-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bind-video-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid #e9edf3;
  border-radius: 10px;
  cursor: pointer;
}

.bind-video-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.bind-video-name {
  font-size: 14px;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bind-video-status {
  font-size: 12px;
  color: #8a94a6;
  flex: none;
}

.form-error {
  margin-top: 10px;
  color: #dc2626;
  font-size: 13px;
}

/* ---------- 上传并分析 ---------- */
.upload-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.upload-label {
  font-size: 13px;
  font-weight: 500;
  color: #4b5563;
}

.upload-input {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 12px;
  border: 1px solid #e3e7ef;
  border-radius: 8px;
  font-size: 14px;
  color: #111827;
  background: #fff;
}

.upload-input:focus {
  outline: none;
  border-color: #3b82f6;
}

.upload-input:disabled {
  background: #f8f9fb;
  cursor: not-allowed;
}

.upload-progress {
  margin-top: 4px;
}

.upload-progress-bar {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #eef1f6;
  overflow: hidden;
}

.upload-progress-fill {
  height: 100%;
  background: #3b82f6;
  border-radius: 999px;
  transition: width 0.2s ease;
}

.upload-progress-text {
  margin: 8px 0 0;
  font-size: 13px;
  color: #6b7280;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid #eef1f6;
}

/* 正文预览 */
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
