<template>
  <div
    class="resource-view"
    :class="{
      'resource-view--ai-workspace': usesAiWorkspaceLayout,
      'resource-view--plan-bank-generate': isPlanOrBankGenerateMode,
    }"
  >
    <!-- 文件浏览页面内容 -->
    <div class="resource-content">
      <!-- 顶部操作栏 -->
      <div class="top-bar">
        <div class="left-section">
          <button class="back-btn" @click="handleBack">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <h2 class="file-name">{{ fileName }}</h2>
        </div>

        <div class="right-section">
          <button
            v-if="isReadOnlyFilePreview"
            class="action-btn action-btn--primary"
            type="button"
            :disabled="!currentResourceIdForDelete || savingCopy"
            @click="openSaveCopyModal"
          >
            {{ savingCopy ? '创建中...' : '创建可编辑副本' }}
          </button>
          <button
            v-else
            class="action-btn"
            @click="handleManualSave"
            :disabled="!hasContentToSave || savingProgress"
          >
            {{ savingProgress ? '保存中...' : '保存' }}
          </button>
          <div class="download-wrap">
            <button
              class="action-btn"
              :disabled="downloading || (isPptMode ? !pptxDownloadUrl : (!currentResourceIdForDelete || !isCompleted))"
              @click="toggleDownloadDropdown"
            >
              {{ downloading ? '下载中...' : '下载' }}
            </button>
            <div v-if="showDownloadDropdown" class="download-dropdown">
              <template v-if="isPptMode">
                <button type="button" class="download-option" @click="downloadPptx">下载为 PPT (.pptx)</button>
              </template>
              <template v-else>
                <button type="button" class="download-option" @click="handleDownloadAs('docx')">下载为 Word (.docx)</button>
                <button type="button" class="download-option" @click="handleDownloadAs('md')">下载为 Markdown (.md)</button>
              </template>
            </div>
          </div>
          <MoreOptionsMenu v-model:open="showMoreOptions">
            <button
              type="button"
              :disabled="!currentResourceIdForDelete || savingCopy"
              @click="openSaveCopyModal"
            >
              {{ savingCopy ? '保存中...' : (isReadOnlyFilePreview ? '创建可编辑副本' : '另存为副本') }}
            </button>
            <button
              type="button"
              :disabled="!currentResourceIdForDelete || renaming"
              @click="openRenameModal"
            >
              {{ renaming ? '重命名中...' : '重命名' }}
            </button>
            <button
              type="button"
              class="is-danger"
              :disabled="!currentResourceIdForDelete || deleting"
              @click="openDeleteResourceModal"
            >
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </MoreOptionsMenu>
        </div>
      </div>

      <!-- 资源层级步骤条：编辑大纲/教案/课件时，让课程 → 大纲 → 教案 → 课件流程贯穿编辑页，可逐级回跳 -->
      <!-- data-cscroll-skip：该栏不需要自定义滚动条，显式跳过包裹，避免被拉高 -->
      <div v-if="hierarchyContext" class="resource-hierarchy-bar" data-cscroll-skip>
        <HierarchyStepper
          :current="hierarchyContext.current"
          :course-id="hierarchyContext.courseId"
          :course-name="hierarchyContext.courseName"
          :outline-id="hierarchyContext.outlineId"
          :outline-name="hierarchyContext.outlineName"
          :plan-id="hierarchyContext.planId"
          :plan-name="hierarchyContext.planName"
          :ppt-name="hierarchyContext.pptName"
        />
      </div>

      <!-- 当前绑定 + 更换绑定（仅预览模式且非生成页） -->
      <div
        v-if="currentResourceIdForDelete && (!isGenerateMode || isPlanOrBankGenerateMode)"
        class="binding-bar"
      >
        <span class="binding-label">当前绑定：</span>
        <span class="binding-value">
          <template v-if="bindingCourseIdForLink">
            <router-link :to="`/course/${bindingCourseIdForLink}`" class="binding-link">{{ bindingDisplayText }}</router-link>
          </template>
          <template v-else>{{ bindingDisplayText }}</template>
        </span>
        <button type="button" class="action-btn binding-btn" @click="openRebindModal">更换绑定</button>
      </div>

      <!-- 文件预览区域 -->
      <div class="preview-container">
        <!-- 左侧：文件内容预览/编辑 -->
        <div class="preview-left">
          <div class="preview-content">
            <!-- 加载状态 -->
            <div v-if="loading" class="loading-placeholder">
              <p>加载中...</p>
            </div>

            <!-- 错误提示 -->
            <div v-else-if="error" class="error-placeholder">
              <p>加载失败，请稍后重试</p>
              <button @click="loadResource" class="retry-btn" v-if="!isGenerateMode">重试</button>
            </div>

            <div
              v-if="generateErrorMessage && isGenerateMode && !error"
              class="generate-error-banner"
              role="alert"
            >
              <p>{{ generateErrorMessage }}</p>
            </div>

            <!-- 只读文件预览提示 -->
            <div v-if="isReadOnlyFilePreview && !loading && !error" class="readonly-file-banner">
              <p>当前为只读文件预览。如需编辑，请创建可编辑副本后在 Markdown 编辑器中修改。</p>
              <button
                type="button"
                class="action-btn action-btn--primary"
                :disabled="!currentResourceIdForDelete || savingCopy"
                @click="openSaveCopyModal"
              >
                {{ savingCopy ? '创建中...' : '创建可编辑副本' }}
              </button>
            </div>

            <!-- 大纲/教案 4 步流水线阶段进度条（分析→生成→核查参考文献→优化定稿）；独立 v-if，不参与下方预览/编辑器互斥链 -->
            <div
              v-if="!isPptMode && isGenerateMode && generating && genStageMessage"
              class="gen-stage-banner"
              role="status"
            >
              <span class="gen-stage-spinner" aria-hidden="true"></span>
              <span class="gen-stage-text">{{ genStageMessage }}</span>
            </div>

            <!-- 文档预览：PDF/Word 文件预览（优先显示） -->
            <!-- 大纲生成以 Markdown 编辑器为主；仅教案/PPT 生成中才在左侧展示文件预览 -->
            <template v-if="pdfUrl && (isCompleted || (isGenerateMode && (isResourceContentGenerateMode)))">
              <iframe
                v-if="previewFileFormat === 'pdf'"
                :src="pdfUrl"
                class="doc-viewer"
                frameborder="0"
                title="PDF 预览"
              ></iframe>
              <div v-else-if="previewFileFormat === 'docx'" class="docx-preview-wrap">
                <iframe
                  :src="wordPreviewSrc"
                  class="doc-viewer"
                  frameborder="0"
                  title="Word 预览"
                ></iframe>
                <p class="docx-fallback-hint">若无法预览，请点击右上角「下载文件到本地」后查看。</p>
              </div>
              <iframe
                v-else
                :src="pdfUrl"
                class="doc-viewer"
                :title="previewFileFormat === 'html' ? 'PPT 预览' : '文档预览'"
                frameborder="0"
              ></iframe>
            </template>

            <!-- PPT 本地生成中：进度占位 -->
            <div v-else-if="isPptMode && generating" class="ppt-generating-panel">
              <div class="ppt-spinner" aria-hidden="true"></div>
              <p class="ppt-gen-title">正在本地生成 PPT…</p>
              <p class="ppt-gen-progress">{{ pptProgress || '请稍候' }}</p>
            </div>

            <!-- Markdown 编辑器（生成大纲模式）：可编辑 + 实时预览（生成中即使仍为空串也挂载，保证流式更新可见） -->
            <MdEditor
              v-else-if="isGenerateMode && !isResourceContentGenerateMode && (editableContent !== null || generating)"
              :key="outlineEditorKey"
              v-model="editableContent"
              class="md-editor-wrap"
              placeholder="AI生成的内容将显示在这里，您可以编辑..."
              :disabled="isCompleted"
              theme="light"
              preview-theme="github"
              language="zh-CN"
              :setting="generating ? { renderDelay: 0 } : {}"
            />

            <!-- Markdown 编辑器（生成教案/PPT 模式）：可编辑 + 实时预览（生成中即使仍为空串也挂载，保证流式更新可见） -->
            <MdEditor
              v-else-if="isGenerateMode && (isResourceContentGenerateMode) && (resourceContent !== null || generating)"
              v-model="resourceContent"
              class="md-editor-wrap"
              :placeholder="isPptMode ? 'AI生成的PPT内容将显示在这里...' : (isQuestionBankMode ? 'AI生成的题目内容将显示在这里...' : 'AI生成的教案内容将显示在这里...')"
              :disabled="isCompleted"
              theme="light"
              preview-theme="github"
              language="zh-CN"
              :setting="generating ? { renderDelay: 100 } : {}"
            />

            <!-- 预览模式 Markdown：可编辑源码，仅点击「另存当前进度」时才写回后端 -->
            <MdEditor
              v-else-if="isPreviewMarkdownMode"
              v-model="previewMarkdownContent"
              class="md-editor-wrap"
              :disabled="false"
              theme="light"
              preview-theme="github"
              language="zh-CN"
              :setting="generating ? { renderDelay: 100 } : {}"
            />

            <!-- AI 工作区左侧空状态（无预览/无正文时） -->
            <ResourceAiEmptyPanel
              v-else-if="showResourceAiEmptyPanel"
              :title="resourceAiEmptyPanelProps.title"
              :description="resourceAiEmptyPanelProps.description"
              :guide-text="resourceAiEmptyPanelProps.guideText"
              :icon="resourceAiEmptyPanelProps.icon"
            />
          </div>
        </div>

        <!-- 右侧：操作面板 -->
        <div class="preview-right" :class="{ 'preview-right--ai': showAiChatAside }">
          <ResourceAiChatAside
            v-if="showAiChatAside"
            ref="resourceAiChatRef"
            v-model:user-input="userInput"
            :placeholder="aiChatPlaceholder"
            :prompts="aiChatPrompts"
            :input-hints="aiChatInputHints"
            :generating="generating"
            :disabled="!canEditContent || generating"
            :send-disabled="aiChatSendDisabled"
            :show-picker="aiChatShowPicker"
            :picker-items="aiPickerItems"
            :picker-selected-id="aiChatShowPicker ? (isPptMode ? selectedPptBaseId : selectedOutlineId) : null"
            :picker-label="aiPickerLabel"
            :picker-placeholder="aiPickerPlaceholder"
            :picker-required="aiPickerRequired"
            :picker-loading="aiPickerLoading"
            :picker-empty-text="aiPickerEmptyText"
            :picker-allow-clear="isPptMode"
            @select-picker-item="onAiPickerSelect"
            @clear-picker="clearPptBase"
            @apply-prompt="applyAiChatPrompt"
            @attach="handleLink"
            @send="handleSend"
          />

          <!-- 文档转写预览：第二步再调用 AI 生成大纲 -->
          <div v-if="isOutlineDocPreviewStep" class="doc-preview-panel">
            <p class="doc-preview-hint">
              左侧为参考文档转写的 Markdown，请核对或修改。确认无误后点击下方按钮，将根据当前内容生成教学大纲。
            </p>
            <p v-if="outlineDocSession?.docName" class="doc-preview-source">
              参考文档：{{ outlineDocSession.docName }}
            </p>
            <button
              type="button"
              class="complete-btn doc-confirm-generate-btn"
              :disabled="generating || !editableContent.trim()"
              @click="() => confirmOutlineFromDocument()"
            >
              {{ generating ? '生成中...' : '确认并生成大纲' }}
            </button>
          </div>

          <!-- 完成按钮（文档转写预览步仅展示「确认并生成大纲」） -->
          <button
            v-if="isGenerateMode && !isOutlineDocPreviewStep"
            class="complete-btn"
            @click="handleComplete"
            :disabled="isCompleted || generating || (isPlanOrBankGenerateMode ? ((!pdfUrl && !resourceContent) || !selectedOutlineId) : (isPptMode ? (!pdfUrl && !resourceContent) : !editableContent.trim()))"
          >
            {{ generating ? '生成中...' : '完成' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 重命名弹窗 -->
    <div v-if="showRenameModal" class="modal-overlay">
      <div class="modal-content rename-modal">
        <div class="modal-header">
          <h3>重命名文件</h3>
          <button type="button" class="modal-close" @click="closeRenameModal" aria-label="关闭">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>文件名</label>
            <input v-model.trim="renameInput" type="text" class="form-input" placeholder="输入新文件名" @keydown.enter="confirmRename" />
          </div>
          <p v-if="renameError" class="rebind-error">操作失败，请稍后重试</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="closeRenameModal">取消</button>
          <button type="button" class="action-btn" :disabled="!renameInput || renaming" @click="confirmRename">
            {{ renaming ? '保存中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 更换绑定弹窗 -->
    <div v-if="showRebindModal" class="modal-overlay">
      <div class="modal-content rebind-modal">
        <div class="modal-header">
          <h3>更换绑定</h3>
          <button type="button" class="modal-close" @click="showRebindModal = false" aria-label="关闭">&times;</button>
        </div>
        <div class="modal-body">
          <p class="rebind-hint">选择要绑定到的课程和章节，仅绑课程不选章节则选「不绑定到具体章节」。</p>
          <div class="form-row">
            <label>课程</label>
            <select v-model="rebindCourseId" class="form-select" @change="onRebindCourseChange">
              <option value="">请选择课程</option>
              <option value="__none__">不绑定到任何课程（解除绑定，并脱离大纲/教案层级）</option>
              <option v-for="c in coursesForRebind" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>章节</label>
            <select v-model="rebindUnitId" class="form-select" :disabled="!rebindCourseId">
              <option value="">不绑定到具体章节</option>
              <option v-for="u in flattenedUnitsForRebind" :key="u.id" :value="u.id">{{ u.indent }}{{ u.name }}</option>
            </select>
          </div>
          <p v-if="rebindError" class="rebind-error">操作失败，请稍后重试</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="showRebindModal = false">取消</button>
          <button type="button" class="action-btn" :disabled="rebindCourseId === '' || rebindSubmitting" @click="confirmRebind">
            {{ rebindSubmitting ? '提交中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 另存为副本弹窗 -->
    <div v-if="showSaveCopyModal" class="modal-overlay">
      <div class="modal-content rename-modal">
        <div class="modal-header">
          <h3>{{ isReadOnlyFilePreview ? '创建可编辑副本' : '另存为副本' }}</h3>
          <button type="button" class="modal-close" @click="closeSaveCopyModal" aria-label="关闭">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>{{ isReadOnlyFilePreview ? '副本名称' : '副本名称' }}</label>
            <input
              v-model.trim="saveCopyName"
              type="text"
              class="form-input"
              :placeholder="isReadOnlyFilePreview ? '输入可编辑副本名称' : '输入副本名称'"
              @keydown.enter="confirmSaveCopy"
            />
          </div>
          <p v-if="saveCopyError" class="form-error">操作失败，请稍后重试</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="closeSaveCopyModal">取消</button>
          <button type="button" class="action-btn" :disabled="!saveCopyName || savingCopy" @click="confirmSaveCopy">
            {{ savingCopy ? '保存中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除资源确认（与「我的课程」删除弹窗同一组件） -->
    <DeleteConfirmModal
      v-model="showDeleteResourceModal"
      title="删除资源"
      entity-kind="资源"
      :entity-name="deleteResourceDisplayName"
      :pending="deleting"
      :error="!!deleteResourceError"
      :error-text="deleteResourceError || '操作失败，请稍后重试'"
      @cancel="closeDeleteResourceModal"
      @confirm="confirmDeleteResource"
    />

    <ConfirmDialogModal
      v-model="showUnsavedLeaveModal"
      variant="danger"
      title="离开页面"
      :message="UNSAVED_PROMPT_MESSAGE"
      confirm-label="仍要离开"
      cancel-label="留在此页"
      @cancel="cancelUnsavedLeave"
      @confirm="confirmUnsavedLeave"
    />

    <!-- 自动消失的提示（已自动保存 / 副本已创建） -->
    <Transition name="toast">
      <div v-if="toastMessage" class="toast-message">{{ toastMessage }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { buildTeachingPlanPromptSuggestions } from '../lib/teachingPlanPrompts'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import { useUserStore } from '../stores/user'
import MdEditor from 'md-editor-v3'
import {
  queryResource,
  generateResource,
  generateResourceStream,
  generateOutlineStream,
  operateResource,
  listResources,
  downloadResource,
  bindResource,
  getResourceFilePath,
  generatePptDeck,
} from '../api/resource'
import { listCourses, listUnitsByCourse, queryCourse } from '../api/course'
import type {
  ResourceResponse,
  ResourceGenerateParams,
  DownloadFormat,
  UnitListItem,
  CourseListItem,
  OutlineForm,
} from '../api/types'
import { stripMarkdownCodeFence } from '../utils/markdown'
import { OperationEnum, ResourceTypeEnum } from '../api/types'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import ConfirmDialogModal from '../components/ConfirmDialogModal.vue'
import MoreOptionsMenu from '../components/MoreOptionsMenu.vue'
import HierarchyStepper, { type HierarchyLevel } from '../components/HierarchyStepper.vue'
import ResourceAiEmptyPanel from '../components/resource-ai/ResourceAiEmptyPanel.vue'
import ResourceAiChatAside from '../components/resource-ai/ResourceAiChatAside.vue'
import type { ResourceAiPickerItem, ResourceAiInputHint } from '../components/resource-ai/ResourceAiChatAside.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 模式枚举
enum ViewMode {
  PREVIEW = 'preview', // 单纯预览
  GENERATE_OUTLINE = 'generate_outline', // 生成大纲
  GENERATE_TEACHING_PLAN = 'generate_teaching_plan', // 生成教案
  GENERATE_QUESTION_BANK = 'generate_question_bank', // 生成题目
  GENERATE_PPT = 'generate_ppt' // 生成PPT
}

const fileName = ref('教学大纲')
const showDropdown = ref(false)
const showDownloadDropdown = ref(false)
const showMoreOptions = ref(false)
const downloading = ref(false)
const selectedOption = ref('')
const selectedOutlineId = ref<string | null>(null) // 选中的大纲 ID（与 ResourceResponse.id 一致为 string）
const userInput = ref('')
const loading = ref(false)
const generating = ref(false)
/** 大纲/教案 4 步流水线当前阶段提示（分析→生成→核查→优化），由后端 loading 事件驱动 */
const genStageMessage = ref<string>('')
const error = ref<string | null>(null)
/** 大纲/教案等流式生成失败时的具体原因（与资源加载 error 区分） */
const generateErrorMessage = ref<string | null>(null)
const resourceData = ref<ResourceResponse | null>(null)
const resourceContent = ref<string | null>(null)
const editableContent = ref('')

/** 文档创建大纲：sessionStorage 中的参考文档与生成提示（第二步生成用） */
interface OutlineDocSessionPayload {
  sourceResourceId?: string
  sourceContent?: string
  prompt?: string
  docName?: string
}
const outlineDocSession = ref<OutlineDocSessionPayload | null>(null)

/** 当前预览/下载的文件 URL（PDF 或 Word 等） */
const pdfUrl = ref<string | null>(null)
/** 当前文件格式，用于区分预览方式：pdf 直接 iframe，docx 用 Office 在线预览，html 直接 iframe（PPT 可交互预览） */
const previewFileFormat = ref<'pdf' | 'docx' | 'html' | null>(null)
const isCompleted = ref(false)
// PPT 本地生成：可下载的 .pptx 地址、标题、进度文案
const pptxDownloadUrl = ref<string | null>(null)
const pptDeckTitle = ref<string>('')
const pptProgress = ref<string>('')
const resourceType = ref<ResourceTypeEnum | null>(null)
const outlineList = ref<ResourceResponse[]>([]) // 基础资源列表（教案用大纲，题目用教案）
/** 当前选中大纲的详情（含正文），用于生成教案预设提示 */
const selectedOutlineDetail = ref<ResourceResponse | null>(null)
const loadingReferenceDetail = ref(false)
const loadingOutlines = ref(false)

function classifyGenerateError(msg: string): string {
  const lower = msg.toLowerCase()
  if (/connection\s*(error|refused)|econnrefused|connect\s+timeout/i.test(lower)) {
    return '模型服务暂时不可用，请稍后再试。如持续出现，请联系管理员检查服务状态。'
  }
  if (/rate.?limit|too many requests|429/i.test(lower)) {
    return '当前使用人数较多，模型正在排队处理中，请稍等片刻后重试。'
  }
  if (/timeout|timed?\s*out|deadline/i.test(lower)) {
    return '模型响应超时，可能是当前负载较高。请缩短输入内容或稍后重试。'
  }
  return msg
}

function hasResourceTextContent(resource: ResourceResponse | null | undefined): boolean {
  if (!resource) return false
  const content = (resource as { content?: string | null }).content
  return !!String(content ?? '').trim()
}

function isEmptyReferenceSourceGenerateError(err: unknown): boolean {
  const msg = (err instanceof Error ? err.message : String(err ?? '')).trim()
  return msg.includes('教案内容不能为空') || msg.includes('教学大纲内容不能为空')
}

function usesTeachingPlanAsReference(): boolean {
  return isQuestionBankMode.value || isPreviewQuestionBank.value
}

function usesOutlineAsReference(): boolean {
  return isTeachingPlanMode.value || isPreviewTeachingPlan.value
}

function usesReferenceDetailPicker(): boolean {
  return usesTeachingPlanAsReference() || usesOutlineAsReference()
}

/** 已选参考资源（大纲/教案）但正文为空 */
const isSelectedReferenceSourceEmpty = computed(() => {
  if (!selectedOutlineId.value) return false
  if (!usesReferenceDetailPicker()) return false
  if (loadingReferenceDetail.value) return false
  if (!selectedOutlineDetail.value) return false
  if (selectedOutlineDetail.value.id !== selectedOutlineId.value) return false
  return !hasResourceTextContent(selectedOutlineDetail.value)
})
// PPT 模式：可选基础资源（大纲 + 教案）
const pptBaseList = ref<ResourceResponse[]>([])
const selectedPptBaseId = ref<string | null>(null)
const loadingPptBases = ref(false)
/** 当前用户 id（用于资源列表按用户过滤、创建/复制资源时绑定） */
const currentUserId = computed(() => userStore.currentUser?.id ?? null)
/** 当前编辑的资源 id（先创建资源再进入 AI 界面时由 query.id 传入，用于自动保存/完成时调 update） */
const currentResourceId = ref<string | null>(null)
/** 从课程/单元页跳转时传入，创建资源时绑定 */
const boundCourseId = ref<string | null>(null)
const boundUnitId = ref<string | null>(null)

/** 从路由 query 解析课程绑定（course_id 与 from_course 均可能携带） */
function readRouteCourseBinding(): string | null {
  const courseId = route.query.course_id as string | undefined
  const fromCourse = route.query.from_course as string | undefined
  const resolved = (courseId?.trim() || fromCourse?.trim() || '')
  return resolved || null
}

/** 完成后/返回时优先回到来源课程页 */
function resolveReturnCourseId(data?: unknown): string | null {
  const fromRoute = readRouteCourseBinding()
  if (fromRoute) return fromRoute
  if (boundCourseId.value) return boundCourseId.value
  return getRelatedIds(data ?? resourceData.value).courseId
}

function syncBoundCourseFromRouteAndResource(data?: unknown) {
  if (!boundCourseId.value) {
    boundCourseId.value = readRouteCourseBinding() ?? getRelatedIds(data ?? resourceData.value).courseId
  }
}
/** 用于删除的当前资源 id：预览页为 route.params.id，生成页为 currentResourceId（避免把 path 里的 generate 当 id） */
const currentResourceIdForDelete = computed(() => {
  const p = route.params.id as string | undefined
  if (p && p !== 'generate') return p
  return currentResourceId.value ?? null
})
const deleting = ref(false)
const showDeleteResourceModal = ref(false)
const deleteResourceError = ref<string | null>(null)

const deleteResourceDisplayName = computed(() => {
  const n = (resourceData.value?.name || fileName.value || '').trim()
  return n || '该资源'
})

function openDeleteResourceModal() {
  const id = currentResourceIdForDelete.value
  if (!id) return
  deleteResourceError.value = null
  showDeleteResourceModal.value = true
}

function closeDeleteResourceModal() {
  if (deleting.value) return
  showDeleteResourceModal.value = false
  deleteResourceError.value = null
}

async function confirmDeleteResource() {
  const id = currentResourceIdForDelete.value
  if (!id || deleting.value) return
  deleting.value = true
  deleteResourceError.value = null
  error.value = null
  try {
    await operateResource({
      operation: OperationEnum.DELETE,
      id,
    })
    showDeleteResourceModal.value = false
    router.push('/my-courses')
  } catch (err) {
    console.error('[Resource] 删除失败', err)
    deleteResourceError.value = err instanceof Error ? err.message : '删除失败'
    error.value = 'failed'
  } finally {
    deleting.value = false
  }
}

// Toast 提示（自动消失）
const toastMessage = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(message: string, durationMs = 2500) {
  if (toastTimer) clearTimeout(toastTimer)
  toastMessage.value = message
  toastTimer = setTimeout(() => {
    toastMessage.value = ''
    toastTimer = null
  }, durationMs)
}

// 另存为副本
const showSaveCopyModal = ref(false)
const saveCopyName = ref('')
const saveCopyError = ref('')
const savingCopy = ref(false)

/** 是否正在执行手动保存 */
const savingProgress = ref(false)

// 重命名
const showRenameModal = ref(false)
const renameInput = ref('')
const renameError = ref('')
const renaming = ref(false)

// 绑定展示与更换绑定（课程 id 用于跳转链接）
const bindingCourseName = ref<string | null>(null)
const bindingUnitName = ref<string | null>(null)
const bindingCourseIdForLink = ref<string | null>(null)
const showRebindModal = ref(false)
const rebindCourseId = ref('')
const rebindUnitId = ref('')
const coursesForRebind = ref<CourseListItem[]>([])
const unitsForRebind = ref<UnitListItem[]>([])
const rebindError = ref('')
const rebindSubmitting = ref(false)

const bindingDisplayText = computed(() => {
  if (bindingCourseName.value && bindingUnitName.value) return `${bindingCourseName.value} / ${bindingUnitName.value}`
  if (bindingCourseName.value) return bindingCourseName.value
  return '未绑定'
})

interface ResourceHierarchyContext {
  current: HierarchyLevel
  courseId: string
  courseName: string
  outlineId?: string
  outlineName?: string
  planId?: string
  planName?: string
  pptName?: string
}

/**
 * 当前编辑/生成的资源在「课程 → 大纲 → 教案 → 课件」层级中的位置。
 * 仅当能解析出归属课程（绑定课程 / 路由 from_course / 资源 related_course）时返回，
 * 否则为 null（独立资源不显示步骤条，沿用 /my-courses 返回逻辑）。
 */
const hierarchyContext = computed<ResourceHierarchyContext | null>(() => {
  const data = resourceData.value as any
  const courseId = boundCourseId.value || readRouteCourseBinding() || getRelatedIds(data).courseId
  if (!courseId) return null
  const rtData = data ? String(data.resource_type ?? '').toLowerCase() : ''
  const rtQuery = typeof route.query.resourceType === 'string' ? route.query.resourceType.toLowerCase() : ''
  const rt = rtData || rtQuery
  const selfId = data?.id ? String(data.id) : (currentResourceIdForDelete.value || '')
  const parentId = data?.parent_resource_id ? String(data.parent_resource_id) : null
  const qOutline = typeof route.query.outline_id === 'string' ? route.query.outline_id : null
  const cName = bindingCourseName.value || data?.related_course?.name || ''
  const parentName = (data?.parent_resource_name as string | undefined) || undefined
  if (rt === 'outline') {
    return { current: 'outline', courseId, courseName: cName, outlineId: selfId || undefined, outlineName: data?.name }
  }
  if (rt === 'teaching_plan') {
    return {
      current: 'plan',
      courseId,
      courseName: cName,
      outlineId: parentId || qOutline || undefined,
      outlineName: parentName,
      planId: selfId || undefined,
      planName: data?.name,
    }
  }
  if (rt === 'ppt') {
    return {
      current: 'ppt',
      courseId,
      courseName: cName,
      outlineId: qOutline || undefined,
      planId: parentId || undefined,
      planName: parentName,
      pptName: data?.name,
    }
  }
  return null
})

/** 编辑页「返回」目标：优先回到所编辑资源所在的层级详情页（大纲/教案），让 outline 流程贯穿编辑。 */
function resolveHierarchyBackTarget(): string | null {
  const h = hierarchyContext.value
  if (!h) return null
  if (h.current === 'outline' && h.outlineId) {
    return `/course/${h.courseId}/outline/${h.outlineId}`
  }
  if (h.current === 'plan' && h.outlineId && h.planId) {
    return `/course/${h.courseId}/outline/${h.outlineId}/plan/${h.planId}`
  }
  if (h.current === 'plan' && h.outlineId) {
    return `/course/${h.courseId}/outline/${h.outlineId}`
  }
  if (h.current === 'ppt' && h.outlineId && h.planId) {
    return `/course/${h.courseId}/outline/${h.outlineId}/plan/${h.planId}`
  }
  return null
}

/**
 * 教案「完成」后的跳转目标：回到该教案所属的大纲详情页（教案版本列表），
 * 而不是退回课程页。courseId 优先从 query.from_course / 绑定 / 资源解析，
 * outlineId 优先从 query.outline_id，其次资源的 parent_resource_id。
 * 任一缺失返回 null，由调用方安全回退到原有行为（回课程页）。
 */
function resolveTeachingPlanCompleteTarget(data?: unknown): string | null {
  const courseId = resolveReturnCourseId(data)
  if (!courseId) return null
  const raw: any = (data as any)?.data ?? data ?? resourceData.value
  const qOutline = typeof route.query.outline_id === 'string' ? route.query.outline_id.trim() : ''
  const parentId = raw?.parent_resource_id != null ? String(raw.parent_resource_id).trim() : ''
  const outlineId = qOutline || parentId
  if (!outlineId) return null
  return `/course/${courseId}/outline/${outlineId}`
}

/**
 * PPT「完成」后的跳转目标：回到该 PPT 所属的教案详情页（PPT 版本列表），
 * 而不是退回课程页。courseId 优先 query.from_course / 绑定 / 资源解析，
 * outlineId 优先 query.outline_id，planId 优先 query.plan_id，其次资源的
 * parent_resource_id（PPT 的父资源即教案）。
 * 任一缺失返回 null，由调用方安全回退到原有行为（回课程页）。
 */
function resolvePptCompleteTarget(data?: unknown): string | null {
  const courseId = resolveReturnCourseId(data)
  if (!courseId) return null
  const raw: any = (data as any)?.data ?? data ?? resourceData.value
  const qOutline = typeof route.query.outline_id === 'string' ? route.query.outline_id.trim() : ''
  if (!qOutline) return null
  const qPlan = typeof route.query.plan_id === 'string' ? route.query.plan_id.trim() : ''
  const parentId = raw?.parent_resource_id != null ? String(raw.parent_resource_id).trim() : ''
  const planId = qPlan || parentId
  if (!planId) return null
  return `/course/${courseId}/outline/${qOutline}/plan/${planId}`
}

// 弹窗内章节扁平列表（带缩进）
const flattenedUnitsForRebind = computed(() => {
  const list: { id: string; name: string; indent: string }[] = []
  function walk(nodes: UnitListItem[], depth: number) {
    for (const u of nodes) {
      list.push({ id: u.detail.id, name: u.detail.name, indent: '　'.repeat(depth) })
      if (u.children?.length) walk(u.children, depth + 1)
    }
  }
  walk(unitsForRebind.value, 0)
  return list
})

/** 从资源数据中读取课程/章节 id（兼容新接口 related_course 对象与扁平 related_course_id/related_unit_id） */
function getRelatedIds(data: any): { courseId: string | null; unitId: string | null } {
  const raw = data?.data ?? data
  if (!raw || typeof raw !== 'object') return { courseId: null, unitId: null }
  const courseId = raw.related_course_id ?? raw.related_course?.id ?? raw.relatedCourseId ?? null
  const unitId = raw.related_unit_id ?? raw.related_unit?.id ?? raw.relatedUnitId ?? null
  return {
    courseId: courseId != null && courseId !== '' ? String(courseId).trim() : null,
    unitId: unitId != null && unitId !== '' ? String(unitId).trim() : null,
  }
}

/** 从资源数据中读取展示用课程名、章节名（新接口直接返回 related_course_name / related_unit_name 或 related_course.name） */
function getBindingDisplayNames(data: any): { courseName: string | null; unitName: string | null; courseIdForLink: string | null } {
  const raw = data?.data ?? data
  if (!raw || typeof raw !== 'object') return { courseName: null, unitName: null, courseIdForLink: null }
  const courseName = raw.related_course_name ?? raw.related_course?.name ?? null
  const unitName = raw.related_unit_name ?? raw.related_unit?.name ?? null
  const courseIdForLink = raw.related_course_id ?? raw.related_course?.id ?? null
  return {
    courseName: courseName != null && courseName !== '' ? String(courseName).trim() : null,
    unitName: unitName != null && unitName !== '' ? String(unitName).trim() : null,
    courseIdForLink: courseIdForLink != null && courseIdForLink !== '' ? String(courseIdForLink).trim() : null,
  }
}

async function loadBindingNames() {
  const data = resourceData.value
  if (!data) return
  bindingCourseName.value = null
  bindingUnitName.value = null
  bindingCourseIdForLink.value = null
  // 新接口：直接使用返回的 related_course_name / related_unit_name 或 related_course.name
  const display = getBindingDisplayNames(data)
  if (display.courseName != null || display.unitName != null || display.courseIdForLink != null) {
    bindingCourseName.value = display.courseName ?? null
    bindingUnitName.value = display.unitName ?? null
    bindingCourseIdForLink.value = display.courseIdForLink ?? null
    return
  }
  // 兼容旧接口：仅有 id 时用接口解析课程名/章节名
  const { courseId, unitId } = getRelatedIds(data)
  if (!courseId) return
  bindingCourseIdForLink.value = courseId
  try {
    const course = await queryCourse(courseId)
    bindingCourseName.value = course.name
    if (unitId) {
      const units = await listUnitsByCourse(courseId)
      const find = (nodes: UnitListItem[]): UnitListItem | null => {
        for (const u of nodes) {
          if (u.detail.id === unitId) return u
          if (u.children?.length) {
            const t = find(u.children)
            if (t) return t
          }
        }
        return null
      }
      const unit = find(units)
      if (unit) bindingUnitName.value = unit.detail.name
    }
  } catch {
    bindingCourseName.value = '(获取失败)'
  }
}

/** 在树中查找单元（递归） */
function findUnitInTree(nodes: UnitListItem[], id: string): UnitListItem | null {
  for (const u of nodes) {
    if (u.detail.id === id) return u
    if (u.children?.length) {
      const found = findUnitInTree(u.children, id)
      if (found) return found
    }
  }
  return null
}

/**
 * 按绑定章节将教案资源重命名为「章节名 - 教案」（与从课程页进入生成教案后的重命名逻辑一致）
 * @param resourceId 资源 id
 * @param courseId 课程 id
 * @param unitId 章节 id
 * @returns 是否成功重命名
 */
async function renameTeachingPlanByUnit(
  resourceId: string,
  courseId: string,
  unitId: string
): Promise<boolean> {
  try {
    const units = await listUnitsByCourse(courseId)
    const unit = findUnitInTree(units, unitId)
    if (!unit) {
      console.warn('自动重命名教案：未找到章节', { courseId, unitId })
      return false
    }
    const newName = `${unit.detail.name} - 教案`
    await operateResource({
      operation: OperationEnum.UPDATE,
      id: resourceId,
      name: newName,
      resource_type: resourceType.value || ResourceTypeEnum.TeachingPlan,
    })
    return true
  } catch (err) {
    console.warn('自动重命名教案失败:', err)
    return false
  }
}

async function renameQuestionBankByUnit(
  resourceId: string,
  courseId: string,
  unitId: string
): Promise<boolean> {
  try {
    const units = await listUnitsByCourse(courseId)
    const unit = findUnitInTree(units, unitId)
    if (!unit) {
      console.warn('自动重命名题目资源：未找到章节', { courseId, unitId })
      return false
    }
    const newName = `${unit.detail.name} - 题目`
    await operateResource({
      operation: OperationEnum.UPDATE,
      id: resourceId,
      name: newName,
      resource_type: resourceType.value || ResourceTypeEnum.QuestionBank,
    })
    return true
  } catch (err) {
    console.warn('自动重命名题目资源失败:', err)
    return false
  }
}

function openRebindModal() {
  showRebindModal.value = true
  rebindError.value = ''
  const { courseId: curCourse, unitId: curUnit } = getRelatedIds(resourceData.value)
  rebindCourseId.value = curCourse ?? ''
  rebindUnitId.value = curUnit ?? ''
  unitsForRebind.value = []
  listCourses().then((data) => {
    coursesForRebind.value = data
    if (rebindCourseId.value && rebindCourseId.value !== '__none__') {
      listUnitsByCourse(rebindCourseId.value).then((u) => { unitsForRebind.value = u })
    }
  }).catch(() => { rebindError.value = '加载课程列表失败' })
}

function onRebindCourseChange() {
  rebindUnitId.value = ''
  unitsForRebind.value = []
  if (!rebindCourseId.value) return
  listUnitsByCourse(rebindCourseId.value).then((u) => { unitsForRebind.value = u }).catch(() => {})
}

async function confirmRebind() {
  const id = currentResourceIdForDelete.value
  if (!id) return
  const unbind = rebindCourseId.value === '__none__'
  const courseId = unbind ? null : (rebindCourseId.value || null)
  if (!unbind && !courseId) return
  rebindError.value = ''
  rebindSubmitting.value = true
  try {
    await bindResource({
      id,
      ...(unbind
        ? { unbind: true }
        : {
            related_course_id: courseId,
            related_unit_id: rebindUnitId.value ? rebindUnitId.value : null,
          }),
    })
    showRebindModal.value = false
    // 换绑后重新拉取资源，以拿到新接口返回的 related_course / related_unit_name 等
    const fresh = await queryResource(id)
    resourceData.value = fresh
    await loadBindingNames()
    // 若为教案且绑定到了具体章节，与课程页进入的教案生成逻辑一致：同步重命名为「章节名 - 教案」
    const isTeachingPlan =
      (fresh.resource_type === ResourceTypeEnum.TeachingPlan ||
       (typeof fresh.resource_type === 'string' && String(fresh.resource_type).toLowerCase() === 'teaching_plan'))
    if (isTeachingPlan && courseId && rebindUnitId.value) {
      const renamed = await renameTeachingPlanByUnit(id, courseId, rebindUnitId.value)
      if (renamed) {
        const updated = await queryResource(id)
        resourceData.value = updated
      }
    }
    const isQuestionBank =
      fresh.resource_type === ResourceTypeEnum.QuestionBank ||
      (typeof fresh.resource_type === 'string' && String(fresh.resource_type).toLowerCase() === 'question_bank')
    if (isQuestionBank && courseId && rebindUnitId.value) {
      const renamed = await renameQuestionBankByUnit(id, courseId, rebindUnitId.value)
      if (renamed) {
        const updated = await queryResource(id)
        resourceData.value = updated
      }
    }
  } catch (err) {
    rebindError.value = err instanceof Error ? err.message : '更新绑定失败'
  } finally {
    rebindSubmitting.value = false
  }
}

// 获取当前模式
const currentMode = computed(() => {
  if (route.path === '/resource/generate') {
    const mode = route.query.mode as string
    if (mode === 'teaching_plan') return ViewMode.GENERATE_TEACHING_PLAN
    if (mode === 'ppt') return ViewMode.GENERATE_PPT
    return ViewMode.GENERATE_OUTLINE
  }
  if (route.query.resourceType !== undefined && !isCompleted.value) {
    const type = route.query.resourceType as string
    if (type === ResourceTypeEnum.TeachingPlan) return ViewMode.GENERATE_TEACHING_PLAN
    if (type === ResourceTypeEnum.QuestionBank) return ViewMode.GENERATE_QUESTION_BANK
    if (type === ResourceTypeEnum.Ppt) return ViewMode.GENERATE_PPT
    return ViewMode.GENERATE_OUTLINE
  }
  return ViewMode.PREVIEW
})

// 判断是否为生成模式
const isGenerateMode = computed(() => {
  return currentMode.value !== ViewMode.PREVIEW
})

// 是否为生成教案模式
const isTeachingPlanMode = computed(() => {
  return currentMode.value === ViewMode.GENERATE_TEACHING_PLAN
})

const isQuestionBankMode = computed(() => {
  return currentMode.value === ViewMode.GENERATE_QUESTION_BANK
})

const resourceAiChatRef = ref<InstanceType<typeof ResourceAiChatAside> | null>(null)

const showResourceAiEmptyPanel = computed(() => {
  if (loading.value || error.value) return false
  if (pdfUrl.value && (isCompleted.value || (isGenerateMode.value && (isResourceContentGenerateMode.value)))) {
    return false
  }
  if (isGenerateMode.value && !isResourceContentGenerateMode.value && (editableContent.value !== null || generating.value)) {
    return false
  }
  if (
    isGenerateMode.value &&
    (isResourceContentGenerateMode.value) &&
    (resourceContent.value !== null || generating.value)
  ) {
    return false
  }
  if (isPreviewMarkdownMode.value) return false
  if (isPlanOrBankGenerateMode.value) {
    const content = resourceContent.value
    return content === null || !String(content).trim()
  }
  if (!isGenerateMode.value && resourceData.value && resourceContent.value === null) return true
  if (isGenerateMode.value) return true
  return !!resourceData.value
})

const resourceAiEmptyPanelProps = computed(() => {
  if (isSelectedReferenceSourceEmpty.value) {
    const refName = selectedOutlineDetail.value?.name?.trim()
    if (usesTeachingPlanAsReference()) {
      const planName = refName || '所选教案'
      return {
        title: '参考教案暂无内容',
        description: `「${planName}」尚未编写教学内容，无法据此生成题目。请先打开该教案完善正文，或在右侧更换其他参考教案。`,
        guideText: '请完善教案或更换参考教案',
        icon: 'edit_note',
      }
    }
    const outlineName = refName || '所选大纲'
    return {
      title: '参考大纲暂无内容',
      description: `「${outlineName}」尚未编写教学内容，无法据此生成教案。请先打开该大纲完善正文，或在右侧更换其他参考大纲。`,
      guideText: '请完善大纲或更换参考大纲',
      icon: 'menu_book',
    }
  }
  if (isTeachingPlanMode.value) {
    return {
      title: '准备好生成教案',
      description:
        '在右侧聊天框中输入您的要求，开始创建详细的教案。我们的 AI 将为您构建教学目标、活动设计等内容。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'edit_document',
    }
  }
  if (isQuestionBankMode.value) {
    return {
      title: '准备好生成题目',
      description: '在右侧选择参考教案并说明题型、难度与数量，AI 将为您生成习题内容。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'quiz',
    }
  }
  if (isPptMode.value) {
    return {
      title: '准备好生成 PPT',
      description: '在右侧选择可选基础资源并输入需求，AI 将为您生成课件内容。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'slideshow',
    }
  }
  if (isGenerateMode.value && !isResourceContentGenerateMode.value) {
    return {
      title: '准备好生成教学大纲',
      description: '在右侧输入课程信息与生成要求，AI 将为您构建结构化的教学大纲。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'menu_book',
    }
  }
  if (isPreviewQuestionBank.value) {
    return {
      title: '准备好生成题目',
      description: '在右侧选择参考教案并说明题型、难度与数量，AI 将为您生成习题内容。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'quiz',
    }
  }
  if (isPreviewTeachingPlan.value) {
    return {
      title: '准备好编写教案',
      description: '在右侧选择教学大纲并输入修改或续写需求，与 AI 协作完善教案内容。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'edit_document',
    }
  }
  if (isPreviewMarkdownType.value) {
    return {
      title: '准备好生成内容',
      description: '在右侧输入框中描述您的需求，AI 将为您生成首段内容或继续修改现有文稿。',
      guideText: '请在右侧输入框中开始输入',
      icon: 'edit_note',
    }
  }
  return {
    title: '暂无预览内容',
    description: '该资源暂无可预览的文件或正文。您仍可在右侧与 AI 交互，或从列表返回。',
    guideText: '',
    icon: 'description',
  }
})

const showAiChatAside = computed(() => showInputSection.value && !isOutlineDocPreviewStep.value)

const aiChatShowPicker = computed(() => shouldShowDropdown.value && showAiChatAside.value)

const aiPickerItems = computed((): ResourceAiPickerItem[] => {
  const list = isPptMode.value ? pptBaseList.value : outlineList.value
  return list.map((o) => ({ id: o.id, name: o.name }))
})

const aiPickerLabel = computed(() => selectedOption.value || '')

const aiPickerPlaceholder = computed(() => {
  if (isPptMode.value) return '选择基础资源（可选）'
  if (isQuestionBankMode.value || isPreviewQuestionBank.value) return '请选择参考教案以与AI进行交互'
  if (usesOutlinePicker.value) return '请选择参考资源以与AI进行交互'
  return '请选择……'
})

const aiPickerRequired = computed(
  () => usesOutlinePicker.value && !isPptMode.value && !isCompleted.value,
)

const aiPickerLoading = computed(() => (isPptMode.value ? loadingPptBases.value : loadingOutlines.value))

const aiPickerEmptyText = computed(() => {
  if (isPptMode.value) return '暂无大纲/教案'
  if (isQuestionBankMode.value || isPreviewQuestionBank.value) return '暂无教案'
  return '暂无大纲'
})

const aiChatPlaceholder = computed(() => {
  if (isPreviewMarkdownType.value) {
    return resourceContent.value
      ? '输入需求，与 AI 继续修改当前内容'
      : isPreviewQuestionBank.value
        ? '输入题目生成需求，如题型、难度、数量（必填）'
        : '输入需求，生成首段内容或与 AI 交互'
  }
  if (isTeachingPlanMode.value) return '请输入生成教案的章节与要求（必填）'
  if (isQuestionBankMode.value) return '请输入题型、难度与数量等要求（必填）'
  if (isPptMode.value) return '输入生成PPT的需求或说明，如：为第一章制作课件'
  return '输入你的需求，AI帮你生成/修改'
})

const aiChatPrompts = computed((): string[] => {
  if (isTeachingPlanMode.value) {
    return buildTeachingPlanPromptSuggestions(selectedOutlineDetail.value)
  }
  if (isQuestionBankMode.value) {
    return [
      '根据教案生成 10 道单选题，难度中等，附参考答案',
      '为本章设计 5 道简答题，考查核心概念',
      '生成 3 道编程实践题，含题目描述与评分要点',
    ]
  }
  if (isGenerateMode.value && !isResourceContentGenerateMode.value) {
    return [
      '为《数据结构》课程生成完整教学大纲',
      '设计一门 16 学时的机器学习入门课大纲',
      '根据已有讲义整理为章节化教学大纲',
    ]
  }
  if (isPreviewQuestionBank.value || isPreviewTeachingPlan.value) {
    return buildPreviewContextPrompts(resourceContent.value, isPreviewQuestionBank.value)
  }
  if (isPptMode.value) {
    return [
      '为第一章制作 15 页课件，含案例与小结',
      '生成项目答辩用的 PPT 大纲与讲稿要点',
    ]
  }
  if (isPreviewMarkdownType.value) {
    return [
      '润色全文语气，使其更适合课堂教学',
      '为当前章节补充小结与思考题',
    ]
  }
  return []
})

const aiChatInputHints = computed((): ResourceAiInputHint[] => {
  const hints: ResourceAiInputHint[] = []
  if (usesOutlinePicker.value && !isCompleted.value && !selectedOutlineId.value) {
    hints.push({ message: '请选择参考资源以与AI进行交互', error: true })
  } else if (isSelectedReferenceSourceEmpty.value) {
    hints.push({
      message: usesTeachingPlanAsReference()
        ? '所选教案暂无内容，请先完善教案或更换参考教案'
        : '所选大纲暂无内容，请先完善大纲或更换参考大纲',
      error: true,
    })
  } else if (isTeachingPlanMode.value && !isCompleted.value && selectedOutlineId.value && !userInput.value.trim()) {
    hints.push({ message: '请填写生成教案的章节（必填）', error: true })
  } else if (isQuestionBankMode.value && !isCompleted.value && selectedOutlineId.value && !userInput.value.trim()) {
    hints.push({ message: '请填写生成题目的要求（必填）', error: true })
  }
  return hints
})

const aiChatSendDisabled = computed(() => {
  if (generating.value) return true
  if (isSelectedReferenceSourceEmpty.value) return true
  if (isPlanOrBankGenerateMode.value) return !userInput.value.trim() || !!pdfUrl.value
  if (isPptMode.value) return !userInput.value.trim()
  if (isPreviewTeachingPlan.value || isPreviewQuestionBank.value) {
    return !selectedOutlineId.value || !userInput.value.trim()
  }
  if (isPreviewMarkdownType.value) return !userInput.value.trim()
  return !userInput.value.trim() && !editableContent.value.trim()
})

function buildPreviewContextPrompts(content: string | null, isQuestionBank: boolean): string[] {
  const headings: string[] = []
  if (content) {
    for (const line of content.split('\n')) {
      const m = line.match(/^#{1,3}\s+(.+)$/)
      if (!m?.[1]) continue
      const h = m[1].replace(/\*+/g, '').trim()
      if (h && h.length <= 40 && headings.length < 6) headings.push(h)
    }
  }

  if (isQuestionBank) {
    if (headings.length >= 2) {
      return [
        `针对「${headings[0]}」增加 5 道单选题`,
        `为「${headings[1]}」设计 3 道简答题`,
        '调整现有题目难度分布，增加高阶思维题',
      ]
    }
    return [
      '根据教案生成 10 道单选题，难度中等，附参考答案',
      '为本章设计 5 道简答题，考查核心概念',
      '生成 3 道编程实践题，含题目描述与评分要点',
    ]
  }

  if (headings.length >= 2) {
    return [
      `完善「${headings[0]}」部分的教学目标与重难点`,
      `为「${headings[1]}」增加课堂互动环节设计`,
      '补充课后作业与形成性评价方案',
    ]
  }
  return [
    '根据大纲补充本章教学目标与重点',
    '将现有内容改写为更清晰的 Markdown 结构',
    '增加课堂互动与练习环节',
  ]
}

function applyAiChatPrompt(text: string) {
  userInput.value = text
  void nextTick(() => {
    resourceAiChatRef.value?.focusInput()
  })
}

function onAiPickerSelect(item: ResourceAiPickerItem) {
  if (isPptMode.value) {
    const found = pptBaseList.value.find((o) => o.id === item.id)
    if (found) selectPptBase(found)
    return
  }
  const found = outlineList.value.find((o) => o.id === item.id)
  if (found) selectOutline(found)
}

// 是否为生成 PPT 模式
const isPptMode = computed(() => {
  return currentMode.value === ViewMode.GENERATE_PPT
})

/** 教案 / PPT / 题目：左侧用 resourceContent 的 Markdown 流式区 */
const isResourceContentGenerateMode = computed(
  () => isTeachingPlanMode.value || isPptMode.value || isQuestionBankMode.value,
)

/** 教案 / 题目：选基础资源 + 必填 prompt */
const isPlanOrBankGenerateMode = computed(
  () => isTeachingPlanMode.value || isQuestionBankMode.value,
)

/** 文档创建大纲第一步：仅预览/编辑 PDF 转写结果，不自动调用 AI */
const isOutlineDocPreviewStep = computed(() => {
  return (
    isGenerateMode.value &&
    !isResourceContentGenerateMode.value &&
    route.query.fromDoc === '1' &&
    route.query.docStep === 'preview'
  )
})

/** 大纲编辑器 remount key：文档预览 → 流式生成切换时强制刷新 MdEditor */
const outlineEditorKey = computed(
  () =>
    `${currentResourceId.value ?? 'new'}-${route.query.docStep ?? 'gen'}-${generating.value ? 'streaming' : 'idle'}`,
)

// 是否需要显示下拉菜单（生成教案选大纲 / 生成 PPT 选基础资源 / 预览教案选大纲 / 预览题目选教案）
const shouldShowDropdown = computed(() => {
  if ((isPlanOrBankGenerateMode.value || isPptMode.value) && !isCompleted.value) return true
  return isPreviewTeachingPlan.value || isPreviewQuestionBank.value
})

/** 预览模式下为只读上传文件（有 path，以 PDF/Word 等方式预览） */
const isReadOnlyFilePreview = computed(() => {
  return !isGenerateMode.value && !!pdfUrl.value && isCompleted.value
})

/** 预览模式下为 Markdown 类型资源（无 PDF/Word），含无内容的新建资源，可在此用 AI 生成首段内容 */
const isPreviewMarkdownType = computed(() => {
  return !isGenerateMode.value && !!resourceData.value && !pdfUrl.value
})

/** 预览模式下为 Markdown 类型且已有正文，可编辑源码并与 AI 继续交互 */
const isPreviewMarkdownMode = computed(() => {
  return isPreviewMarkdownType.value && resourceContent.value !== null
})

/** 预览模式下当前资源为教案类型，需显示并选择教学大纲 */
const isPreviewTeachingPlan = computed(() => {
  return !isGenerateMode.value && !!resourceData.value && String(resourceData.value.resource_type).toLowerCase() === 'teaching_plan'
})

/** 预览模式下当前资源为题库/题目类型，交互与教案一致（选大纲 + 需求说明） */
const isPreviewQuestionBank = computed(() => {
  return !isGenerateMode.value && !!resourceData.value && String(resourceData.value.resource_type).toLowerCase() === 'question_bank'
})

/** 需展示基础资源下拉并校验：生成教案选大纲 / 预览教案选大纲 / 预览题目选教案 */
const usesOutlinePicker = computed(() => {
  return (
    isPlanOrBankGenerateMode.value ||
    isPreviewTeachingPlan.value ||
    isPreviewQuestionBank.value
  )
})

/** 是否显示右侧输入区（生成模式 或 预览 Markdown 类型，含空资源；文档转写预览步隐藏） */
const showInputSection = computed(() => {
  if (isOutlineDocPreviewStep.value) return false
  return isGenerateMode.value || isPreviewMarkdownType.value
})

const usesAiWorkspaceLayout = computed(
  () => showAiChatAside.value || isOutlineDocPreviewStep.value || showResourceAiEmptyPanel.value,
)

/** 是否允许编辑/输入（生成模式未完成 或 预览 Markdown 类型，含空资源） */
const canEditContent = computed(() => {
  if (isGenerateMode.value) return !isCompleted.value
  return isPreviewMarkdownType.value
})

/** 是否有可保存的源码内容（用于「另存当前进度」按钮） */
const hasContentToSave = computed(() => {
  if (!currentResourceIdForDelete.value) return false
  if (isPreviewMarkdownMode.value) return resourceContent.value !== null
  // 生成大纲模式：editableContent 是纯 markdown
  if (isGenerateMode.value && !isResourceContentGenerateMode.value) return !!editableContent.value.trim()
  // 生成教案/PPT 模式：resourceContent 也是 markdown（当 result 不是文件路径/链接时）
  if (isGenerateMode.value && (isResourceContentGenerateMode.value)) return resourceContent.value !== null
  return false
})

/** 上次加载或保存时的内容，用于判断是否有未保存修改 */
const lastSavedContent = ref('')

/** 当前内容是否有未保存的修改（仅对可编辑的 Markdown 资源生效） */
const contentDirty = computed(() => {
  if (isPreviewMarkdownMode.value) return (resourceContent.value ?? '') !== lastSavedContent.value
  if (isGenerateMode.value && !isResourceContentGenerateMode.value) return editableContent.value.trim() !== lastSavedContent.value
  if (isGenerateMode.value && (isResourceContentGenerateMode.value)) return (resourceContent.value ?? '') !== lastSavedContent.value
  return false
})

/** 预览 Markdown 编辑用：始终为字符串，避免 MdEditor 收到 null */
const previewMarkdownContent = computed({
  get: () => resourceContent.value ?? '',
  set: (v: string) => { resourceContent.value = v },
})

/** Word 文档在线预览地址（Microsoft Office Viewer，要求文件 URL 公网可访问） */
const wordPreviewSrc = computed(() => {
  const url = pdfUrl.value
  if (!url) return ''
  return `https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(url)}`
})

// 加载资源数据（查看模式）
async function loadResource() {
  const resourceId = route.params.id
  if (!resourceId || typeof resourceId !== 'string') {
    return
  }
  // 避免在生成页误用：/resource/generate 可能被匹配为 /resource/:id 且 id='generate'
  if (resourceId === 'generate' || route.path === '/resource/generate') {
    return
  }

  loading.value = true
  error.value = null

  try {
    const data = await queryResource(resourceId)
    resourceData.value = data
    fileName.value = data.name

    // PPT：已落库的在线预览(html) 直接 iframe 预览，并提供 .pptx 下载
    const pptHtmlUrl = (data as { ppt_html_url?: string | null }).ppt_html_url
    if (pptHtmlUrl) {
      previewFileFormat.value = 'html'
      pdfUrl.value = resolveFileUrl(pptHtmlUrl)
      const pptxUrl = (data as { ppt_pptx_url?: string | null }).ppt_pptx_url
      pptxDownloadUrl.value = pptxUrl ? resolveFileUrl(pptxUrl) : null
      pptDeckTitle.value = data.name || ''
      resourceContent.value = null
      lastSavedContent.value = ''
      isCompleted.value = true
      await loadBindingNames()
      return
    }

    // 判断是否为可预览的文档（以 Word 为主，兼容 PDF）
    const fileType = (data as any).file_format?.toString().toLowerCase() || (typeof data.resource_type === 'string' ? data.resource_type.toLowerCase() : '') || ''
    const path = getResourceFilePath(data)
    const isPdf = fileType === 'pdf' || (path && path.toLowerCase().endsWith('.pdf'))
    const isWord = fileType === 'docx' || fileType === 'word' || fileType === 'doc' || (path && (path.toLowerCase().endsWith('.docx') || path.toLowerCase().endsWith('.doc')))
    if (path && (isPdf || isWord)) {
      previewFileFormat.value = isWord ? 'docx' : 'pdf'
      const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
      const prefix = baseUrl === '' ? '/api' : ''
      pdfUrl.value = `${baseUrl}${prefix}${path.startsWith('/') ? '' : '/'}${path}`
      resourceContent.value = null
      lastSavedContent.value = ''
    } else {
      previewFileFormat.value = null
      pdfUrl.value = null
      const rawContent = (data as any).content
      if (rawContent !== undefined && rawContent !== null) {
        const contentStr = rawContent ? stripMarkdownCodeFence(rawContent) : ''
        resourceContent.value = contentStr
        lastSavedContent.value = contentStr
      } else {
        resourceContent.value = null
        lastSavedContent.value = ''
      }
    }
    isCompleted.value = true
    await loadBindingNames()
    const loadedRt = String((data as any).resource_type).toLowerCase()
    if (loadedRt === 'teaching_plan' || loadedRt === 'question_bank') {
      await loadOutlineList()
    }
    // 定时自动保存已移除：改为 AI 流式完成后立即保存，用户编辑后 1 秒防抖保存
  } catch (err) {
    console.error('[Resource] 加载资源失败', err)
    error.value = 'failed'
    fileName.value = '资源加载失败'
  } finally {
    loading.value = false
  }
}

// 加载基础资源列表（用于生成教案选大纲、预览教案/题目选基础资源）
async function loadOutlineList() {
  const rt = resourceData.value ? String(resourceData.value.resource_type).toLowerCase() : ''
  const needPicker =
    isPlanOrBankGenerateMode.value ||
    (!!resourceData.value && (rt === 'teaching_plan' || rt === 'question_bank'))
  if (!needPicker) return

  const pickerType = rt === 'question_bank' ? ResourceTypeEnum.TeachingPlan : ResourceTypeEnum.Outline

  loadingOutlines.value = true
  try {
    // 题目生成的基础资源是教案，教案生成的基础资源是大纲
    const baseResourceType = rt === 'question_bank' ? ResourceTypeEnum.TeachingPlan : ResourceTypeEnum.Outline
    const data = await listResources({
      resource_type: pickerType,
    })
    outlineList.value = data
    // 预览（教案/题目）且 URL 带 outline_id 时预选（历史参数名，实际含义为 source_resource_id）
    const outlineIdFromQuery = route.query.outline_id
    if (outlineIdFromQuery && typeof outlineIdFromQuery === 'string') {
      const found = data.find((o) => o.id === outlineIdFromQuery || String(o.id) === outlineIdFromQuery)
      if (found) {
        selectedOutlineId.value = found.id
        selectedOption.value = found.name
        if (isPlanOrBankGenerateMode.value || isPreviewQuestionBank.value || isPreviewTeachingPlan.value) {
          await syncSelectedOutlineDetail()
        }
      }
    }
  } catch (err) {
    console.error(pickerType === ResourceTypeEnum.TeachingPlan ? '加载教案列表失败:' : '加载大纲列表失败:', err)
    outlineList.value = []
  } finally {
    loadingOutlines.value = false
  }
}

// 加载 PPT 可选基础资源列表（大纲 + 教案）
async function loadPptBaseList() {
  if (!isPptMode.value) return
  loadingPptBases.value = true
  try {
    const [outlines, plans] = await Promise.all([
      listResources({ resource_type: ResourceTypeEnum.Outline }),
      listResources({ resource_type: ResourceTypeEnum.TeachingPlan }),
    ])
    pptBaseList.value = [...outlines, ...plans]
  } catch (err) {
    console.error('加载PPT基础资源列表失败:', err)
    pptBaseList.value = []
  } finally {
    loadingPptBases.value = false
  }
}

function loadOutlineDocSession(outlineResourceId: string): OutlineDocSessionPayload | null {
  const docKey = `outline_doc_${outlineResourceId}`
  try {
    const raw = sessionStorage.getItem(docKey)
    if (!raw) return null
    return JSON.parse(raw) as OutlineDocSessionPayload
  } catch (e) {
    console.warn('读取 outline_doc 失败', e)
    return null
  }
}

function clearOutlineDocSession(outlineResourceId: string) {
  try {
    sessionStorage.removeItem(`outline_doc_${outlineResourceId}`)
  } catch (e) {
    console.warn('清除 outline_doc 失败', e)
  }
  outlineDocSession.value = null
}

// 初始化生成模式
async function initGenerateMode() {
  if (generating.value) return

  const content = route.query.content as string
  const paramId = route.params.id as string | undefined
  const queryId = route.query.id as string | undefined
  const id =
    (paramId && paramId !== 'generate' ? paramId : '') || (queryId && queryId !== 'generate' ? queryId : '') || ''
  const mode = currentMode.value
  const unitId = route.query.unit_id as string | undefined

  if (id) {
    currentResourceId.value = id
  }
  if (content) {
    const stripped = stripMarkdownCodeFence(content)
    editableContent.value = stripped
    lastSavedContent.value = ''
  } else {
    lastSavedContent.value = ''
  }
  boundCourseId.value = readRouteCourseBinding()
  boundUnitId.value = unitId && unitId !== '' ? unitId : null

  // 文档转写预览：加载资源正文，不触发 AI
  if (isOutlineDocPreviewStep.value && id) {
    outlineDocSession.value = loadOutlineDocSession(id)
    loading.value = true
    error.value = null
    pdfUrl.value = null
    previewFileFormat.value = null
    try {
      const data = await queryResource(id)
      resourceData.value = data
      fileName.value = data.name || '文档转写预览'
      const raw = (data.content ?? '').trim()
      const stripped = raw ? stripMarkdownCodeFence(raw) : ''
      editableContent.value = stripped
      lastSavedContent.value = stripped
    } catch (err) {
      error.value = 'failed'
      console.error('加载文档转写内容失败:', err)
    } finally {
      loading.value = false
    }
  } else {
    const streamOutline = route.query.stream === 'outline' && id
    if (streamOutline) {
      const fromDoc = route.query.fromDoc === '1'
      if (fromDoc) {
        const payload = loadOutlineDocSession(id)
        if (payload) {
          outlineDocSession.value = payload
          const transcript = (editableContent.value || payload.sourceContent || '').trim()
          if (transcript && id) {
            void confirmOutlineFromDocument({ skipRouteReplace: true, transcriptOverride: transcript })
          }
        }
      } else {
        const storageKey = `outline_form_${id}`
        let outlineForm: OutlineForm | null = null
        try {
          const raw = sessionStorage.getItem(storageKey)
          if (raw) {
            outlineForm = JSON.parse(raw) as OutlineForm
            sessionStorage.removeItem(storageKey)
          }
        } catch (e) {
          console.warn('读取 outline_form 失败', e)
        }
        if (outlineForm) {
          generating.value = true
          void startOutlineStream(outlineForm)
        }
      }
    }
  }

  // 根据模式设置资源类型和文件名
  if (mode === ViewMode.GENERATE_TEACHING_PLAN) {
    resourceType.value = ResourceTypeEnum.TeachingPlan
    if (id) {
      try {
        const data = await queryResource(id)
        resourceData.value = data
        fileName.value = data.name || '教案'
        const ids = getRelatedIds(data)
        if (!boundCourseId.value) boundCourseId.value = ids.courseId
        if (!unitId) boundUnitId.value = ids.unitId
        await loadBindingNames()
      } catch (err) {
        console.error('加载教案资源元数据失败:', err)
        if (!isOutlineDocPreviewStep.value) fileName.value = '教案'
      }
    } else if (!isOutlineDocPreviewStep.value) {
      fileName.value = '教案'
    }
    await loadOutlineList()
    if (currentResourceId.value) {
      await loadResourceForUpdate()
    }
  } else if (mode === ViewMode.GENERATE_QUESTION_BANK) {
    resourceType.value = ResourceTypeEnum.QuestionBank
    if (id) {
      try {
        const data = await queryResource(id)
        resourceData.value = data
        fileName.value = data.name || '题目'
        const ids = getRelatedIds(data)
        if (!boundCourseId.value) boundCourseId.value = ids.courseId
        if (!unitId) boundUnitId.value = ids.unitId
        await loadBindingNames()
      } catch (err) {
        console.error('加载题目资源元数据失败:', err)
        if (!isOutlineDocPreviewStep.value) fileName.value = '题目'
      }
    } else if (!isOutlineDocPreviewStep.value) {
      fileName.value = '题目'
    }
    await loadOutlineList()
    if (currentResourceId.value) {
      await loadResourceForUpdate()
    }
  } else if (mode === ViewMode.GENERATE_PPT) {
    resourceType.value = ResourceTypeEnum.Ppt
    fileName.value = 'PPT生成'
    loadPptBaseList()
    // 再次进入已生成的 PPT：读取已落库的产物地址，渲染 HTML 预览 + 提供下载，避免内容为空
    if (currentResourceId.value) {
      await loadPptResourceForUpdate()
    }
  } else {
    resourceType.value = ResourceTypeEnum.Outline
    if (!isOutlineDocPreviewStep.value) fileName.value = '教学大纲生成'
  }
}

function applyOutlineStreamDone(full: string) {
  const accumulated = stripMarkdownCodeFence(full || editableContent.value)
  if (accumulated) {
    editableContent.value = accumulated
  }
  generating.value = false
  genStageMessage.value = ''
  generateErrorMessage.value = null
  void autoSaveFromStream()
}

/**
 * 大纲流式生成（「从零生成」与「通过文档生成」共用，与 POST /ai/outline 对齐）
 */
async function runOutlineGenerateStream(opts: {
  outlineForm?: OutlineForm
  previousContent?: string
  /** 远程旧版 /ai/outline 仅认 resource_id，从库读 content */
  resourceId?: string
  prompt?: string | null
  errorLabel?: string
}) {
  const label = opts.errorLabel ?? '生成失败'
  const prev = (opts.previousContent ?? '').trim()
  const hasForm = opts.outlineForm != null
  const resourceId = (opts.resourceId ?? currentResourceId.value ?? '').trim()
  if (!hasForm && !prev && !resourceId) {
    generating.value = false
    generateErrorMessage.value = '表单数据不能为空'
    return
  }

  generateErrorMessage.value = null
  error.value = null
  pdfUrl.value = null
  previewFileFormat.value = null
  generating.value = true
  genStageMessage.value = '正在分析需求…'
  editableContent.value = ''

  await generateOutlineStream(
    {
      ...(hasForm ? { outline_form: opts.outlineForm } : {}),
      ...(prev ? { previous_content: prev } : {}),
      ...(resourceId ? { resource_id: resourceId } : {}),
      ...(opts.prompt != null && String(opts.prompt).trim()
        ? { prompt: String(opts.prompt).trim() }
        : {}),
    },
    {
      onChunk(delta) {
        if (delta) {
          // 最终稿开始流式写入：收起阶段进度条，呈现「进度 → 结果」
          if (genStageMessage.value) genStageMessage.value = ''
          editableContent.value += delta
        }
      },
      onStage(_stage, message) {
        if (message) genStageMessage.value = message
      },
      onDone(full) {
        applyOutlineStreamDone(full)
      },
      onError(err) {
        void handleStreamFailure(err, label)
      },
    },
  )
}

/** 退出文档预览路由态，与「从零生成」页 layout 一致（stream=outline，无 docStep） */
async function exitOutlineDocPreviewRoute(id: string) {
  const nextQuery: Record<string, string> = {
    id,
    resourceType: ResourceTypeEnum.Outline,
    fromDoc: '1',
    stream: 'outline',
  }
  const fromCourse = route.query.from_course
  if (typeof fromCourse === 'string' && fromCourse) {
    nextQuery.from_course = fromCourse
  }
  await router.replace({ path: '/resource/generate', query: nextQuery })
  await nextTick()
}

/** 文档预览确认后：保存转写正文，再流式生成（逻辑对齐从零生成的 runOutlineGenerateStream） */
async function confirmOutlineFromDocument(opts?: {
  skipRouteReplace?: boolean
  transcriptOverride?: string
}) {
  const id = currentResourceId.value
  if (!id) {
    generateErrorMessage.value = '缺少资源 id，无法生成'
    return
  }

  const session = outlineDocSession.value ?? loadOutlineDocSession(id)
  const transcript = (opts?.transcriptOverride ?? editableContent.value).trim()
  if (!transcript) {
    generateErrorMessage.value = '转写内容为空，请返回重新上传文档'
    return
  }

  try {
    await operateResource({
      operation: OperationEnum.UPDATE,
      id,
      content: transcript,
      resource_type: ResourceTypeEnum.Outline,
    })
    lastSavedContent.value = transcript

    const prompt =
      session?.prompt?.trim() ||
      '请根据参考文档内容，生成一份结构完整、可直接使用的教学大纲（Markdown 格式）。'

    if (!opts?.skipRouteReplace) {
      await exitOutlineDocPreviewRoute(id)
    }

    await runOutlineGenerateStream({
      previousContent: transcript,
      resourceId: id,
      prompt,
      errorLabel: '基于文档生成大纲失败',
    })

    if (!opts?.skipRouteReplace) {
      clearOutlineDocSession(id)
    }
  } catch (err) {
    generating.value = false
    void handleStreamFailure(err, '基于文档生成大纲失败')
  }
}

/** 流式生成失败：有已生成正文时保留编辑器，仅展示错误条 */
async function handleStreamFailure(err: unknown, label: string) {
  console.error(`[Resource] ${label}`, err)
  generating.value = false
  genStageMessage.value = ''

  if (usesReferenceDetailPicker() && isEmptyReferenceSourceGenerateError(err)) {
    generateErrorMessage.value = null
    error.value = null
    if (selectedOutlineId.value) {
      await syncSelectedOutlineDetail()
    }
    return
  }

  const rawMsg = err instanceof Error ? err.message : '生成失败'
  const msg = classifyGenerateError(rawMsg)
  generateErrorMessage.value = msg
  const outlineLike =
    isGenerateMode.value && !isResourceContentGenerateMode.value
  if (outlineLike && editableContent.value.trim()) {
    error.value = null
    return
  }
  if (isGenerateMode.value && (resourceContent.value?.trim() || pdfUrl.value)) {
    error.value = null
    return
  }
  error.value = 'failed'
}

/** 从零生成：sessionStorage 中的 outline_form 流式生成 */
async function startOutlineStream(outlineForm: OutlineForm) {
  await runOutlineGenerateStream({ outlineForm })
}

// 加载已有资源内容（用于生成模式下的 UPDATE 操作）
async function loadResourceForUpdate() {
  if (!currentResourceId.value) return
  try {
    const data = await queryResource(currentResourceId.value)
    const rawContent = (data as { content?: string }).content
    if (rawContent !== undefined && rawContent !== null) {
      const contentStr = rawContent ? stripMarkdownCodeFence(rawContent) : ''
      resourceContent.value = contentStr
      lastSavedContent.value = contentStr
    } else {
      resourceContent.value = null
      lastSavedContent.value = ''
    }
  } catch (err) {
    console.error('加载已有资源内容失败:', err)
  }
}

/**
 * 再次进入 PPT 生成页：从库读取已落库的产物地址（ppt_html_url / ppt_pptx_url），
 * 渲染 HTML 预览并提供下载。保持在生成态（不置 isCompleted），用户仍可重新生成。
 */
async function loadPptResourceForUpdate() {
  if (!currentResourceId.value) return
  try {
    const data = await queryResource(currentResourceId.value)
    resourceData.value = data
    if (data.name) fileName.value = data.name
    const htmlUrl = (data as { ppt_html_url?: string | null }).ppt_html_url
    if (htmlUrl) {
      pdfUrl.value = resolveFileUrl(htmlUrl)
      previewFileFormat.value = 'html'
      const pptxUrl = (data as { ppt_pptx_url?: string | null }).ppt_pptx_url
      pptxDownloadUrl.value = pptxUrl ? resolveFileUrl(pptxUrl) : null
      pptDeckTitle.value = data.name || ''
    }
  } catch (err) {
    console.error('加载已生成 PPT 失败:', err)
  }
}

// 发送请求（生成模式）
async function handleSend() {
  // 生成教案 / 预览教案 / 预览题目：均需先选基础资源（大纲或教案）
  if (usesOutlinePicker.value && !selectedOutlineId.value) {
    error.value =
      isQuestionBankMode.value || isPreviewQuestionBank.value
        ? '请选择参考教案以与AI进行交互'
        : '请选择参考资源以与AI进行交互'
    return
  }

  if (isTeachingPlanMode.value && !userInput.value.trim()) {
    error.value = '请填写生成哪一章哪一节的教案'
    return
  }
  if (isQuestionBankMode.value && !userInput.value.trim()) {
    error.value = '请填写题型、难度与数量等要求'
    return
  }
  if (usesReferenceDetailPicker() && selectedOutlineId.value) {
    if (
      !selectedOutlineDetail.value ||
      selectedOutlineDetail.value.id !== selectedOutlineId.value
    ) {
      await syncSelectedOutlineDetail()
    }
    if (isSelectedReferenceSourceEmpty.value) {
      generateErrorMessage.value = null
      error.value = null
      return
    }
  }
  // 生成 PPT 模式下，prompt 必填
  if (isPptMode.value && !userInput.value.trim()) {
    error.value = '请输入生成PPT的需求或说明'
    return
  }
  if (!editableContent.value.trim() && !userInput.value.trim() && !isPreviewMarkdownMode.value) {
    error.value = '请输入内容或提示词'
    return
  }
  if (isPreviewMarkdownType.value && !userInput.value.trim()) {
    error.value = '请输入需求，生成内容或与 AI 继续修改'
    return
  }

  generating.value = true
  genStageMessage.value = ''
  error.value = null

  // PPT 本地生成：走专用流式接口（产出可交互 HTML 预览 + 可下载 .pptx）
  if (isPptMode.value) {
    await runPptGeneration()
    return
  }

  // 流式写入前避免 resourceContent 长期为 null：MdEditor 条件含 !== null，不挂载则看不到增量
  if (usesOutlinePicker.value || isPreviewMarkdownType.value) {
    if (resourceContent.value === null) {
      resourceContent.value = ''
    }
  }

  try {
    let operation = OperationEnum.CREATE
    let previousContent: string | null = null

    // 预览模式 Markdown：无内容时用 CREATE 生成首段，有内容时用 UPDATE 修改
    if (isPreviewMarkdownType.value) {
      if (resourceContent.value !== null && resourceContent.value !== '') {
        operation = OperationEnum.UPDATE
        previousContent = resourceContent.value
      } else {
        operation = OperationEnum.CREATE
        previousContent = null
      }
    } else if (isPlanOrBankGenerateMode.value) {
      if (currentResourceId.value) {
        operation = OperationEnum.UPDATE
        previousContent = editableContent.value.trim() || resourceContent.value || null
      } else {
        operation = OperationEnum.CREATE
        previousContent = null
      }
    } else {
      // 大纲模式：有 editableContent 则 UPDATE，否则 CREATE
      // PPT 模式：无 currentResourceId 时均为 CREATE，若有已生成内容可传 previous_content 供再次生成
      if (isPptMode.value) {
        operation = OperationEnum.CREATE
        previousContent = resourceContent.value !== null && resourceContent.value !== '' ? resourceContent.value : null
      } else if (editableContent.value.trim()) {
        operation = OperationEnum.UPDATE
        previousContent = editableContent.value
      } else {
        operation = OperationEnum.CREATE
        previousContent = null
      }
    }

    const isOutlineGenerate =
      !isPreviewMarkdownType.value && !isResourceContentGenerateMode.value

    const params: ResourceGenerateParams = {
      operation,
      resource_type: isPreviewMarkdownType.value
        ? (resourceData.value?.resource_type as ResourceTypeEnum) ?? ResourceTypeEnum.Outline
        : (resourceType.value || ResourceTypeEnum.Outline),
      previous_content: previousContent,
      prompt: userInput.value.trim() || null,
      source_resource_id: usesOutlinePicker.value ? selectedOutlineId.value : (isPptMode.value ? selectedPptBaseId.value : null),
      outline_form: null,
    }
    /** 与 startOutlineStream 一致：流式阶段逐块追加，结束后再 stripMarkdownCodeFence(full) 定稿 */
    const applyResult = (result: string) => {
      if (usesOutlinePicker.value) {
        if (result.startsWith('http://') || result.startsWith('https://')) {
          pdfUrl.value = result
          previewFileFormat.value = result.toLowerCase().endsWith('.docx') ? 'docx' : 'pdf'
        } else if (result.startsWith('/')) {
          const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
          const prefix = baseUrl === '' ? '/api' : ''
          pdfUrl.value = `${baseUrl}${prefix}${result}`
          previewFileFormat.value = result.toLowerCase().endsWith('.docx') ? 'docx' : 'pdf'
        } else if (result) {
          resourceContent.value = stripMarkdownCodeFence(result)
        }
      } else if (isPptMode.value) {
        if (result.startsWith('http://') || result.startsWith('https://')) {
          pdfUrl.value = result
          previewFileFormat.value = result.toLowerCase().endsWith('.pptx') ? 'docx' : 'pdf'
        } else if (result.startsWith('/')) {
          const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
          const prefix = baseUrl === '' ? '/api' : ''
          pdfUrl.value = `${baseUrl}${prefix}${result}`
          previewFileFormat.value = result.toLowerCase().endsWith('.pptx') ? 'docx' : 'pdf'
        } else if (result) {
          resourceContent.value = stripMarkdownCodeFence(result)
        }
      } else if (isPreviewMarkdownType.value) {
        if (result) resourceContent.value = stripMarkdownCodeFence(result)
      } else {
        if (result) editableContent.value = stripMarkdownCodeFence(result)
      }
    }

    const streamCallbacks = {
      onChunk(delta: string) {
        // 最终稿开始流式写入：收起阶段进度条，呈现「进度 → 结果」
        if (genStageMessage.value) genStageMessage.value = ''
        if (usesOutlinePicker.value || isPptMode.value || isPreviewMarkdownType.value) {
          resourceContent.value = (resourceContent.value ?? '') + delta
        } else {
          editableContent.value += delta
        }
      },
      onStage(_stage: string, message: string) {
        if (message) genStageMessage.value = message
      },
      onDone(full: string) {
        if (isOutlineGenerate) {
          applyOutlineStreamDone(full)
        } else {
          applyResult(full)
          generating.value = false
          genStageMessage.value = ''
          void autoSaveFromStream()
        }
        userInput.value = ''
      },
      onError(err: Error) {
        void handleStreamFailure(err, '生成失败')
      },
    }

    if (isOutlineGenerate) {
      const prev = (previousContent ?? '').trim()
      if (!prev && !userInput.value.trim()) {
        generating.value = false
        error.value = '请输入内容或提示词'
        return
      }
      await generateOutlineStream(
        {
          ...(prev ? { previous_content: prev } : {}),
          ...(currentResourceId.value ? { resource_id: currentResourceId.value } : {}),
          ...(params.prompt ? { prompt: params.prompt } : {}),
        },
        streamCallbacks,
      )
    } else {
      await generateResourceStream(params, streamCallbacks)
    }
  } catch (err) {
    await handleStreamFailure(err, '生成失败')
  }
}

/** 把后端返回的相对路径（/static/... 或 /ai/...）拼成可访问的完整 URL */
function resolveFileUrl(p: string): string {
  if (!p) return ''
  if (p.startsWith('http://') || p.startsWith('https://')) return p
  const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
  const prefix = baseUrl === '' ? '/api' : ''
  return `${baseUrl}${prefix}${p.startsWith('/') ? '' : '/'}${p}`
}

/** PPT 本地生成：调用 /ai/ppt（SSE），完成后左侧 iframe 预览 HTML，并提供 .pptx 下载 */
async function runPptGeneration() {
  pptProgress.value = '正在准备生成…'
  pptxDownloadUrl.value = null
  pdfUrl.value = null
  await generatePptDeck(
    {
      source_resource_id: selectedPptBaseId.value || null,
      prompt: userInput.value.trim() || null,
      resource_id: currentResourceId.value || null,
      previous_content: resourceContent.value || null,
    },
    {
      onProgress(msg: string) {
        pptProgress.value = msg
      },
      onComplete(res) {
        pdfUrl.value = resolveFileUrl(res.html_url)
        previewFileFormat.value = 'html'
        pptxDownloadUrl.value = res.pptx_url ? resolveFileUrl(res.pptx_url) : null
        pptDeckTitle.value = res.title || ''
        generating.value = false
        pptProgress.value = ''
        userInput.value = ''
      },
      onError(err: Error) {
        pptProgress.value = ''
        void handleStreamFailure(err, '生成 PPT 失败')
      },
    },
  )
}

/** 下载本地生成的 .pptx（直接取静态文件，不走 markdown 转换） */
function downloadPptx() {
  if (!pptxDownloadUrl.value) return
  showDownloadDropdown.value = false
  const a = document.createElement('a')
  a.href = pptxDownloadUrl.value
  a.download = `${pptDeckTitle.value || fileName.value || 'PPT'}.pptx`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// 完成按钮：有 currentResourceId 时调 update 保存并跳转，否则创建新资源
async function handleComplete() {
  // 注意：currentMode 依赖 `!isCompleted`，下方一旦置 isCompleted=true，
  // 模式判断会退化为 PREVIEW，导致 isTeachingPlanMode/isPptMode 变 false，
  // 完成后的跳转目标就丢了（回退到课程页）。故在此先快照模式。
  const wasTeachingPlanMode = isTeachingPlanMode.value
  const wasPptMode = isPptMode.value
  if (isPlanOrBankGenerateMode.value) {
    if (!pdfUrl.value && !resourceContent.value) {
      error.value = isQuestionBankMode.value ? '请先生成题目' : '请先生成教案'
      return
    }
    if (!selectedOutlineId.value) {
      error.value = isQuestionBankMode.value
        ? '请选择参考教案以与AI进行交互'
        : '请选择参考资源以与AI进行交互'
      return
    }
  } else if (isPptMode.value) {
    if (!pdfUrl.value && !resourceContent.value) {
      error.value = '请先生成PPT'
      return
    }
  } else {
    if (!editableContent.value.trim()) {
      error.value = '内容不能为空'
      return
    }
  }

  generating.value = true
  error.value = null

  try {
    const rid = currentResourceId.value
    if (rid) {
      // 已有资源：后端存 markdown 源码，调 update 保存当前内容
      // 教案/PPT 模式：有 resourceContent 则保存，有 pdfUrl 则文件已生成不写 content
      const contentForUpdate = (isResourceContentGenerateMode.value)
        ? (resourceContent.value !== null && resourceContent.value !== '' ? resourceContent.value : undefined)
        : editableContent.value
      await operateResource({
        operation: OperationEnum.UPDATE,
        id: rid,
        content: contentForUpdate,
        resource_type: resourceType.value || ResourceTypeEnum.Outline,
      })
      if (contentForUpdate !== undefined) lastSavedContent.value = typeof contentForUpdate === 'string' ? contentForUpdate : ''
      const data = await queryResource(rid)
      resourceData.value = data
      isCompleted.value = true
      const filePathAfterUpdate = getResourceFilePath(data)
      if (filePathAfterUpdate) {
        const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
        const prefix = baseUrl === '' ? '/api' : ''
        pdfUrl.value = `${baseUrl}${prefix}${filePathAfterUpdate.startsWith('/') ? '' : '/'}${filePathAfterUpdate}`
        const fmt = (data.file_format || '').toLowerCase()
        previewFileFormat.value = fmt === 'docx' ? 'docx' : 'pdf'
      }

      if (isTeachingPlanMode.value && boundUnitId.value && boundCourseId.value) {
        const renamed = await renameTeachingPlanByUnit(rid, boundCourseId.value, boundUnitId.value)
        if (renamed) {
          const updatedData = await queryResource(rid)
          resourceData.value = updatedData
          data.name = updatedData.name
        }
      }
      if (isQuestionBankMode.value && boundUnitId.value && boundCourseId.value) {
        const renamed = await renameQuestionBankByUnit(rid, boundCourseId.value, boundUnitId.value)
        if (renamed) {
          const updatedData = await queryResource(rid)
          resourceData.value = updatedData
          data.name = updatedData.name
        }
      }

      // 如果从课程/单元页进入，完成后跳转回课程页；否则跳转到资源详情页
      // 教案完成后优先回到所属大纲详情页（教案版本列表），而非课程页
      // 添加短暂延迟，确保后端数据已更新
      syncBoundCourseFromRouteAndResource(data)
      const planTarget = wasTeachingPlanMode
        ? resolveTeachingPlanCompleteTarget(data)
        : (wasPptMode ? resolvePptCompleteTarget(data) : null)
      const returnCourseId = resolveReturnCourseId(data)
      if (planTarget) {
        await new Promise(resolve => setTimeout(resolve, 300))
        router.push(planTarget)
      } else if (returnCourseId) {
        // 等待一小段时间，确保后端数据已更新
        await new Promise(resolve => setTimeout(resolve, 300))
        router.push(`/course/${returnCourseId}`)
      } else {
        router.replace({ path: `/resource/${data.id}`, query: {} })
      }
      return
    }
    // 无资源 id（旧流程）：创建新资源（若从课程/单元页进入则绑定）
    // 教案/PPT 模式：有 resourceContent 则保存，有 pdfUrl 则文件已生成不写 content
    const contentForCreate = (isResourceContentGenerateMode.value)
      ? (resourceContent.value !== null && resourceContent.value !== '' ? resourceContent.value : null)
      : editableContent.value
    // 教案/题目把选中的基础资源（大纲/教案）作为父资源挂入层级链；课程/章节随 create 提交保证版本号作用域正确
    const rtForCreate = String(resourceType.value || ResourceTypeEnum.Outline).toLowerCase()
    const parentIdForCreate =
      (rtForCreate === 'teaching_plan' || rtForCreate === 'question_bank') && selectedOutlineId.value
        ? String(selectedOutlineId.value)
        : null
    const resultId = await operateResource({
      operation: OperationEnum.CREATE,
      name: fileName.value,
      content: contentForCreate,
      editable: true,
      related_user_id: userStore.currentUser?.id ?? undefined,
      resource_type: resourceType.value || ResourceTypeEnum.Outline,
      related_course_id: boundCourseId.value || null,
      related_unit_id: boundUnitId.value || null,
      parent_resource_id: parentIdForCreate,
    })
    if (!resultId) {
      throw new Error('创建成功但未返回资源 id')
    }
    // 教案/PPT 生成后若有 Markdown 内容，用 update 写回确保保存
    if ((isResourceContentGenerateMode.value) && resourceContent.value !== null && resourceContent.value !== '') {
      await operateResource({
        operation: OperationEnum.UPDATE,
        id: resultId,
        content: resourceContent.value,
        resource_type: resourceType.value || ResourceTypeEnum.Outline,
      })
    }
    const data = await queryResource(resultId)
    resourceData.value = data
    isCompleted.value = true
    const filePathAfterCreate = getResourceFilePath(data)
    if (filePathAfterCreate) {
      const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
      const prefix = baseUrl === '' ? '/api' : ''
      pdfUrl.value = `${baseUrl}${prefix}${filePathAfterCreate.startsWith('/') ? '' : '/'}${filePathAfterCreate}`
      const fmt = (data.file_format || '').toLowerCase()
      previewFileFormat.value = fmt === 'docx' ? 'docx' : 'pdf'
    }

    if (isTeachingPlanMode.value && boundUnitId.value && boundCourseId.value) {
      const renamed = await renameTeachingPlanByUnit(resultId, boundCourseId.value, boundUnitId.value)
      if (renamed) {
        const updatedData = await queryResource(resultId)
        resourceData.value = updatedData
        data.name = updatedData.name
      }
    }
    if (isQuestionBankMode.value && boundUnitId.value && boundCourseId.value) {
      const renamed = await renameQuestionBankByUnit(resultId, boundCourseId.value, boundUnitId.value)
      if (renamed) {
        const updatedData = await queryResource(resultId)
        resourceData.value = updatedData
        data.name = updatedData.name
      }
    }
    lastSavedContent.value = (isResourceContentGenerateMode.value) ? (resourceContent.value ?? '') : editableContent.value
    syncBoundCourseFromRouteAndResource(data)
    // 教案完成后优先回到所属大纲详情页（教案版本列表）；PPT 完成后优先回到所属教案详情页，均非课程页
    const planTarget = isTeachingPlanMode.value
      ? resolveTeachingPlanCompleteTarget(data)
      : (isPptMode.value ? resolvePptCompleteTarget(data) : null)
    const returnCourseId = resolveReturnCourseId(data)
    if (planTarget) {
      await new Promise(resolve => setTimeout(resolve, 300))
      router.push(planTarget)
    } else if (returnCourseId) {
      await new Promise(resolve => setTimeout(resolve, 300))
      router.push(`/course/${returnCourseId}`)
    } else {
      router.replace({ path: `/resource/${data.id}`, query: {} })
    }
  } catch (err) {
    console.error('[Resource] 操作资源失败', err)
    error.value = 'failed'
  } finally {
    generating.value = false
  }
}

/** 未保存离开时与浏览器 beforeunload 共用的提示文案 */
const UNSAVED_PROMPT_MESSAGE = '当前有未保存的修改，确定要离开吗？离开后修改将丢失。'

type PendingLeave = { kind: 'route'; to: RouteLocationNormalized } | { kind: 'back' }
const showUnsavedLeaveModal = ref(false)
const pendingLeave = ref<PendingLeave | null>(null)

/** 放弃「未保存」状态：把基线拉到当前内容，便于路由守卫放行（不调用保存接口） */
function syncLastSavedToCurrentForLeave() {
  if (isPreviewMarkdownMode.value) {
    lastSavedContent.value = resourceContent.value ?? ''
  } else if (isGenerateMode.value && !isResourceContentGenerateMode.value) {
    lastSavedContent.value = editableContent.value.trim()
  } else if (isGenerateMode.value && (isResourceContentGenerateMode.value)) {
    lastSavedContent.value = resourceContent.value ?? ''
  }
}

function doNavigateBackFromResource() {
  // 优先回到所编辑资源的层级详情页（大纲 / 教案），保持 outline 流程贯穿
  const hierarchyTarget = resolveHierarchyBackTarget()
  if (hierarchyTarget) {
    router.push(hierarchyTarget)
    return
  }
  const courseId = resolveReturnCourseId()
  if (courseId) {
    router.push(`/course/${courseId}`)
  } else {
    router.push('/my-courses')
  }
}

function confirmUnsavedLeave() {
  showUnsavedLeaveModal.value = false
  const p = pendingLeave.value
  pendingLeave.value = null
  syncLastSavedToCurrentForLeave()
  if (!p) return
  if (p.kind === 'route') {
    void router.push(p.to)
  } else {
    doNavigateBackFromResource()
  }
}

function cancelUnsavedLeave() {
  showUnsavedLeaveModal.value = false
  pendingLeave.value = null
}

function handleBack() {
  if (contentDirty.value) {
    pendingLeave.value = { kind: 'back' }
    showUnsavedLeaveModal.value = true
    return
  }
  doNavigateBackFromResource()
}

/** 获取当前可保存的正文（与 hasContentToSave 基本一致：预览 Markdown/生成大纲/生成教案-PPT 的 markdown） */
function getContentToSave(): string | null {
  if (isPreviewMarkdownMode.value) return resourceContent.value ?? ''
  if (isGenerateMode.value && !isResourceContentGenerateMode.value) return editableContent.value.trim() || null
  if (isGenerateMode.value && (isResourceContentGenerateMode.value)) return resourceContent.value ?? null
  return null
}

/** 执行保存到当前资源 */
async function performAutoSave(): Promise<boolean> {
  const id = currentResourceIdForDelete.value
  const content = getContentToSave()
  if (!id || content === null) return false
  try {
    await operateResource({
      operation: OperationEnum.UPDATE,
      id,
      content,
      resource_type: (resourceData.value?.resource_type as ResourceTypeEnum) ?? resourceType.value ?? undefined,
    })
    lastSavedContent.value = content
    return true
  } catch {
    return false
  }
}

/** 手动保存：将当前内容写回当前资源并提示 */
async function handleManualSave() {
  if (!hasContentToSave.value) return
  savingProgress.value = true
  error.value = null
  try {
    const ok = await performAutoSave()
    if (ok) showToast('已保存')
    else error.value = '保存失败'
  } catch (err) {
    console.error('[Resource] 保存失败', err)
    error.value = 'failed'
  } finally {
    savingProgress.value = false
  }
}

function openSaveCopyModal() {
  if (!currentResourceIdForDelete.value) return
  saveCopyName.value = isReadOnlyFilePreview.value
    ? `${fileName.value}-可编辑副本`
    : `${fileName.value}-副本`
  saveCopyError.value = ''
  showSaveCopyModal.value = true
}

function closeSaveCopyModal() {
  showSaveCopyModal.value = false
  saveCopyError.value = ''
}

async function confirmSaveCopy() {
  const name = saveCopyName.value.trim()
  if (!name) {
    saveCopyError.value = '请输入副本名称'
    return
  }
  const id = currentResourceIdForDelete.value
  if (!id) {
    saveCopyError.value = '无法获取当前资源'
    return
  }
  saveCopyError.value = ''
  savingCopy.value = true
  try {
    const newId = await operateResource({
      operation: OperationEnum.COPY,
      id,
      name,
      related_user_id: userStore.currentUser?.id ?? undefined,
    })
    closeSaveCopyModal()
    showToast(isReadOnlyFilePreview.value ? '可编辑副本已创建' : '副本已创建')
    if (newId) router.push(`/resource/${newId}`)
  } catch (err) {
    console.error('[Resource] 创建副本失败', err)
    saveCopyError.value = 'failed'
  } finally {
    savingCopy.value = false
  }
}

function openRenameModal() {
  if (!currentResourceIdForDelete.value) return
  renameInput.value = resourceData.value?.name ?? fileName.value ?? ''
  renameError.value = ''
  showRenameModal.value = true
}

function closeRenameModal() {
  showRenameModal.value = false
  renameError.value = ''
}

async function confirmRename() {
  const id = currentResourceIdForDelete.value
  if (!id) return
  const newName = renameInput.value.trim()
  if (!newName) {
    renameError.value = '请输入文件名'
    return
  }
  renameError.value = ''
  renaming.value = true
  try {
    await operateResource({
      operation: OperationEnum.UPDATE,
      id,
      name: newName,
      resource_type: (resourceData.value?.resource_type as ResourceTypeEnum) ?? undefined,
    })
    const updated = await queryResource(id)
    resourceData.value = updated
    fileName.value = updated.name
    closeRenameModal()
  } catch (err) {
    console.error('[Resource] 重命名失败', err)
    renameError.value = 'failed'
  } finally {
    renaming.value = false
  }
}

function toggleDownloadDropdown() {
  showMoreOptions.value = false
  showDownloadDropdown.value = !showDownloadDropdown.value
}

async function handleDownloadAs(format: DownloadFormat) {
  const id = currentResourceIdForDelete.value
  if (!id) return
  showDownloadDropdown.value = false
  downloading.value = true
  error.value = null
  try {
    const name = resourceData.value?.name || fileName.value || undefined
    await downloadResource(id, format, name)
  } catch (err) {
    console.error('[Resource] 下载失败', err)
    error.value = 'failed'
  } finally {
    downloading.value = false
  }
}

const toggleDropdown = () => {
  showDropdown.value = !showDropdown.value
}

const selectOption = (option: string) => {
  selectedOption.value = option
  showDropdown.value = false
}

async function syncSelectedOutlineDetail() {
  const id = selectedOutlineId.value
  const needsDetail =
    isPlanOrBankGenerateMode.value || isPreviewQuestionBank.value || isPreviewTeachingPlan.value
  if (!id || !needsDetail) {
    selectedOutlineDetail.value = null
    return
  }
  const cached = outlineList.value.find((o) => o.id === id) ?? null
  loadingReferenceDetail.value = true
  try {
    selectedOutlineDetail.value = await queryResource(id)
  } catch (err) {
    console.warn('[Resource] 加载参考资源详情失败', err)
    selectedOutlineDetail.value = cached
  } finally {
    loadingReferenceDetail.value = false
  }
}

// 选择大纲（生成教案模式）
const selectOutline = (outline: ResourceResponse) => {
  selectedOption.value = outline.name
  selectedOutlineId.value = outline.id
  showDropdown.value = false
  void syncSelectedOutlineDetail()
}

// 选择 PPT 基础资源（可选）
const selectPptBase = (item: ResourceResponse) => {
  selectedOption.value = item.name
  selectedPptBaseId.value = item.id
  showDropdown.value = false
}

// 清除 PPT 基础资源选择
const clearPptBase = () => {
  selectedOption.value = ''
  selectedPptBaseId.value = null
  showDropdown.value = false
}

const handleLink = () => {
  // TODO: 实现链接功能
}

/** 防抖自动保存：AI 流式完成后立即保存；用户停止编辑 1 秒后保存 */
const AUTO_SAVE_DEBOUNCE_MS = 1000
let editAutoSaveTimer: ReturnType<typeof setTimeout> | null = null
const isAutoSaving = ref(false)

function clearEditAutoSaveTimer() {
  if (editAutoSaveTimer) {
    clearTimeout(editAutoSaveTimer)
    editAutoSaveTimer = null
  }
}

async function autoSaveNow(source: 'stream' | 'edit'): Promise<void> {
  if (isAutoSaving.value) return
  if (!hasContentToSave.value) return

  clearEditAutoSaveTimer()
  isAutoSaving.value = true
  try {
    const ok = await performAutoSave()
    if (ok) showToast(source === 'stream' ? '已自动保存' : '已自动保存')
  } finally {
    isAutoSaving.value = false
  }
}

function autoSaveFromStream() {
  // 流式完成后：直接保存（不等 1 秒）
  void autoSaveNow('stream')
}

// 用户编辑 markdown 后：1 秒防抖自动保存
watch(editableContent, () => {
  if (!isGenerateMode.value || isResourceContentGenerateMode.value) return
  if (isCompleted.value) return
  if (generating.value) return
  if (isAutoSaving.value) return
  if (!contentDirty.value || !hasContentToSave.value) return

  clearEditAutoSaveTimer()
  editAutoSaveTimer = setTimeout(() => {
    void autoSaveNow('edit')
  }, AUTO_SAVE_DEBOUNCE_MS)
})

watch(resourceContent, () => {
  if (!isPreviewMarkdownMode.value && !(isGenerateMode.value && (isResourceContentGenerateMode.value))) return
  if (isCompleted.value) return
  if (generating.value) return
  if (isAutoSaving.value) return
  if (!contentDirty.value || !hasContentToSave.value) return

  clearEditAutoSaveTimer()
  editAutoSaveTimer = setTimeout(() => {
    void autoSaveNow('edit')
  }, AUTO_SAVE_DEBOUNCE_MS)
})

// 组件挂载时初始化（不再定时自动保存：改为流式完成/编辑防抖自动保存）
onMounted(() => {
  if (isGenerateMode.value) {
    void initGenerateMode()
  } else {
    loadResource()
  }
})

// 从列表点进不同资源时（预览模式）重新加载
watch(
  () => route.params.id,
  (newId, oldId) => {
    if (newId && newId !== 'generate' && newId !== oldId && !isGenerateMode.value) {
      loadResource()
    }
  }
)

// 未保存即离开时提示（应用内路由跳转）
onBeforeRouteLeave((to) => {
  if (!contentDirty.value) return true
  pendingLeave.value = { kind: 'route', to }
  showUnsavedLeaveModal.value = true
  return false
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (contentDirty.value) {
    e.preventDefault()
    e.returnValue = UNSAVED_PROMPT_MESSAGE
    return UNSAVED_PROMPT_MESSAGE
  }
}
watch(contentDirty, (dirty) => {
  if (dirty) {
    window.addEventListener('beforeunload', onBeforeUnload)
  } else {
    window.removeEventListener('beforeunload', onBeforeUnload)
  }
}, { immediate: true })

onUnmounted(() => {
  clearEditAutoSaveTimer()
  isAutoSaving.value = false
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (toastTimer) {
    clearTimeout(toastTimer)
    toastTimer = null
  }
})
</script>

<style scoped>
/* 整页高度固定为视口，禁止页面纵向滚动，仅编辑器内部滚动 */
.resource-view {
  width: 100%;
  height: calc(100vh - 64px);
  max-height: calc(100vh - 64px);
  overflow: hidden;
  background-color: transparent;
  display: flex;
  flex-direction: column;
}

.resource-view--ai-workspace {
  background: linear-gradient(135deg, #e0e8ff 0%, #f7f8f8 40%, #f7f8f8 60%, #e8f0fe 100%);
}

/* 教案/题目生成：透出全局背景，避免内容区与页面背景渐变割裂 */
.resource-view--plan-bank-generate,
.resource-view--plan-bank-generate .resource-content {
  background: transparent;
}

.resource-view--ai-workspace .preview-content {
  background: transparent;
  border: none;
  backdrop-filter: none;
}

.resource-view--ai-workspace .preview-container {
  overflow: visible;
}

.resource-view--ai-workspace .preview-right--ai {
  min-height: 0;
  overflow: hidden;
}

.resource-view--ai-workspace .preview-right--ai .complete-btn {
  width: 100%;
  flex-shrink: 0;
}

.resource-view--ai-workspace .doc-preview-panel {
  padding: 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.04),
    0 1px 2px rgba(0, 0, 0, 0.02);
}

.resource-view--ai-workspace .complete-btn {
  background: #4450b7;
  color: #fff;
  border-radius: 12px;
}

.resource-view--ai-workspace .complete-btn:hover:not(:disabled) {
  background: #3a46a8;
}

.resource-view--ai-workspace .complete-btn:disabled {
  background: #c5c9e8;
  color: #fff;
  opacity: 0.7;
}

.resource-content {
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

/* 顶部操作栏 */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 16px 24px;
  background-color: rgba(255, 255, 255, 0.4);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.resource-hierarchy-bar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding: 10px 20px;
  background-color: rgba(255, 255, 255, 0.55);
  border-radius: 12px;
  /* overflow-x:auto 会让 overflow-y 由 visible 计算成 auto（CSS 规范），
     从而被自定义滚动条插件误判为「纵向可滚动」并包一层会被拉高的 .cscroll-outer。
     显式 overflow-y:hidden 杜绝这一晋升，保留横向滚动即可。 */
  overflow-x: auto;
  overflow-y: hidden;
}

.binding-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding: 10px 24px;
  background-color: #f8f9ff;
  border-radius: 8px;
  font-size: 14px;
}
.binding-label {
  color: #666;
}
.binding-value {
  color: #333;
  flex: 1;
}
.binding-link {
  color: #1a73e8;
  text-decoration: none;
}
.binding-link:hover {
  text-decoration: underline;
}
.binding-btn {
  padding: 6px 14px;
  font-size: 13px;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal-overlay, 1200);
}
.rebind-modal.modal-content,
.rename-modal.modal-content {
  background: #fff;
  border-radius: 12px;
  width: min(440px, calc(100vw - 24px));
  min-width: 0;
  max-width: 90vw;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: #1a73e8;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}
.modal-header h3 {
  margin: 0;
  font-size: 18px;
}
.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: #666;
  padding: 0 4px;
}
.modal-close:hover {
  color: #333;
}
.modal-body {
  padding: 20px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}
.rebind-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: #666;
}
.form-row {
  margin-bottom: 14px;
}
.form-row label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: #333;
}
.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.rebind-error,
.form-error {
  margin: 12px 0 0;
  font-size: 13px;
  color: #c00;
}

/* 自动消失的 Toast 提示 */
.toast-message {
  position: fixed;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  background: rgba(0, 0, 0, 0.78);
  color: #fff;
  border-radius: 8px;
  font-size: 14px;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}

.action-btn.secondary {
  background: #e0e0e0;
  color: #333;
}
.action-btn.secondary:hover {
  background: #d0d0d0;
}

.left-section {
  display: flex;
  align-items: center;
  gap: 12px;
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

.file-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.right-section {
  display: flex;
  gap: 12px;
}

.action-btn {
  padding: 8px 16px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.action-btn--primary {
  background: #000;
  color: #fff;
  border-color: #000;
}

.action-btn--primary:hover:not(:disabled) {
  background: #333;
  border-color: #333;
}

.readonly-file-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #f5f7ff;
  border: 1px solid #d6e0ff;
  border-radius: 8px;
  font-size: 14px;
  color: #333;
}

.readonly-file-banner p {
  margin: 0;
  flex: 1;
  min-width: 200px;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.download-wrap {
  position: relative;
}

.download-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  min-width: 240px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  z-index: 10;
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
  background: #f5f5f5;
}

/* 预览容器：占满剩余高度，不超出视口，滚动发生在编辑器内部 */
.preview-container {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.preview-left {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.preview-content {
  background-color: #ffffff;
  border-radius: 12px;
  padding: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.preview-placeholder {
  color: #333;
  padding: 24px;
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.6;
  flex: 1;
  overflow-y: auto;
}

.preview-placeholder pre {
  margin: 0;
  font-family: inherit;
}

.preview-empty-hint {
  color: #666;
  margin: 0;
  white-space: pre-line;
}

/* 可编辑内容区域 */
.editable-content {
  width: 100%;
  height: 100%;
  min-height: 600px;
  padding: 24px;
  border: none;
  outline: none;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  resize: none;
  background-color: #ffffff;
  overflow-y: auto;
}

.editable-content:disabled {
  background-color: #f5f5f5;
  cursor: not-allowed;
}

/* Markdown 编辑器：占满预览区高度，仅编辑器内部内容区域滚动 */
.md-editor-wrap {
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.md-editor-wrap :deep(.md-editor) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* 编辑/预览分栏容器：与 md-editor-v3 默认一致，左右等分、各自滚动 */
.md-editor-wrap :deep(.md-editor-content) {
  flex: 1;
  flex-shrink: 0;
  min-height: 0;
  height: 0;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}
.md-editor-wrap :deep(.md-editor-input-wrapper),
.md-editor-wrap :deep(.md-editor-preview-wrapper) {
  flex: 1 1 0;
  min-width: 0;
}
.md-editor-wrap :deep(.md-editor-input-wrapper .cm-editor) {
  width: 100%;
  height: 100%;
}

/* 文档预览器（PDF / Word）：在限制高度的预览区内显示 */
.pdf-viewer,
.doc-viewer {
  width: 100%;
  flex: 1;
  min-height: 0;
  border: none;
  background-color: #f5f5f5;
}

.ppt-generating-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: #4b5563;
}
.ppt-generating-panel .ppt-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e3e6ee;
  border-top-color: #3d51e3;
  border-radius: 50%;
  animation: ppt-spin 0.8s linear infinite;
}
@keyframes ppt-spin {
  to { transform: rotate(360deg); }
}
.ppt-generating-panel .ppt-gen-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2430;
}
.ppt-generating-panel .ppt-gen-progress {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
}

.docx-preview-wrap {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.docx-preview-wrap .doc-viewer {
  flex: 1;
  min-height: 0;
}
.docx-fallback-hint {
  flex-shrink: 0;
  margin: 8px 0 0;
  padding: 0 8px;
  font-size: 12px;
  color: #666;
}

.loading-placeholder,
.error-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
  color: #999;
}

.error-placeholder p {
  color: #d32f2f;
  margin-bottom: 16px;
}

.generate-error-banner {
  flex-shrink: 0;
  margin: 12px 16px 0;
  padding: 10px 14px;
  border-radius: 8px;
  background: #fff3f3;
  border: 1px solid #ffcdd2;
}

.generate-error-banner p {
  margin: 0;
  font-size: 14px;
  color: #c62828;
  line-height: 1.5;
}

/* 大纲/教案 4 步流水线阶段进度条 */
.gen-stage-banner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 16px 0;
  padding: 10px 14px;
  border-radius: 8px;
  background: #eef1ff;
  border: 1px solid #d6ddff;
}
.gen-stage-banner .gen-stage-spinner {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border: 2px solid #c7d0f5;
  border-top-color: #3d51e3;
  border-radius: 50%;
  animation: ppt-spin 0.8s linear infinite;
}
.gen-stage-banner .gen-stage-text {
  font-size: 13px;
  color: #2f3a8c;
  line-height: 1.4;
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

/* 右侧操作面板 */
.preview-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.preview-right--ai {
  overflow: hidden;
}

.dropdown-section {
  margin-bottom: 8px;
}

.dropdown-wrapper {
  position: relative;
}

.dropdown-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s;
}

.dropdown-btn:hover {
  border-color: #C5D9FF;
}

.dropdown-btn.not-selected {
  border-color: #ff9800;
}

.dropdown-btn-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.dropdown-btn .dropdown-file-icon {
  flex-shrink: 0;
  color: #888;
}

.dropdown-btn svg {
  transition: transform 0.2s;
  flex-shrink: 0;
}

.dropdown-btn svg.rotate {
  transform: rotate(180deg);
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 8px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  overflow: hidden;
}

.dropdown-item {
  padding: 12px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: background-color 0.2s;
}

.dropdown-item:hover {
  background-color: #f5f5f5;
}

.dropdown-item.empty-item {
  color: #999;
  cursor: default;
}

.dropdown-item.empty-item:hover {
  background-color: transparent;
}

/* 输入区域 */
.input-section {
  flex: 1;
}

.input-container {
  position: relative;
  background-color: #ffffff;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #e0e0e0;
  min-height: 200px;
  display: flex;
  flex-direction: column;
}

.ai-input {
  width: 100%;
  flex: 1;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
  min-height: 120px;
}

.ai-input:focus {
  border-color: #C5D9FF;
}

.ai-input:disabled {
  background-color: #f5f5f5;
  cursor: not-allowed;
}

.ai-input.required:not(:disabled):not(:focus) {
  border-color: #ff9800;
}

.input-hints {
  margin-top: 4px;
}

.input-error {
  color: #d32f2f;
  font-size: 12px;
  padding-left: 4px;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(19, 88, 228, 0.65);
  transition: color 0.2s;
  border-radius: 4px;
}

.icon-btn:hover:not(:disabled) {
  color: rgba(19, 88, 228, 0.65);
  background-color: #f8f9ff;
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.doc-preview-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 8px;
}

.doc-preview-hint {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
}

.doc-preview-source {
  margin: 0;
  font-size: 13px;
  color: #888;
}

.doc-confirm-generate-btn {
  width: 100%;
}

/* 完成按钮 */
.complete-btn {
  padding: 12px 24px;
  background-color: #C5D9FF;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.complete-btn:hover:not(:disabled) {
  background-color: #a8c5ff;
}

.complete-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .preview-container {
    grid-template-columns: 1fr;
  }

  .preview-right {
    order: -1;
  }
}

@media (max-width: 768px) {
  .resource-content {
    padding: 16px;
  }

  .top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .right-section {
    width: 100%;
    justify-content: flex-end;
  }
}

@media (max-width: 640px) {
  /* 移动端：解除整页 100vh 锁定，改用自然流。
     桌面上 .resource-view 用 height:100vh + overflow:hidden 锁页面，
     让编辑器内部独自滚动；移动端这种锁定会让 .preview-container 的
     grid 行被拉伸，输入框和预览之间留出几百 px 的死白 */
  .resource-view {
    height: auto;
    max-height: none;
    overflow: visible;
  }
  .resource-content {
    padding: 12px;
    height: auto;
    overflow: visible;
  }
  .preview-container {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow: visible;
  }
  /* 保留输入区（右）在最上方的顺序；flex 容器下的 order 仍生效 */
  .preview-right {
    order: -1;
  }
  /* 预览区按自然高度展开，去掉桌面端 min-height: 600px 的硬性留白 */
  .editable-content {
    min-height: 320px;
  }
  .input-section {
    flex: none;
  }
  .input-container {
    min-height: 160px;
  }
  .right-section {
    flex-wrap: wrap;
    gap: 8px;
  }
  /* 预览区在窄屏改为按 60vh 限高，避免内嵌 iframe 撑满全屏 */
  .pdf-viewer,
  .doc-viewer {
    min-height: 60vh;
  }
}
</style>
