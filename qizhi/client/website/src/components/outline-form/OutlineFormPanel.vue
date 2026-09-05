<template>
  <div class="outline-form-panel">
  <ConfirmDialogModal
    v-model="uploadAlertVisible"
    variant="info"
    :title="uploadAlertTitle"
    :message="uploadAlertMessage"
    single-button
    confirm-label="知道了"
    @confirm="closeUploadAlert"
    @cancel="closeUploadAlert"
  />
    <!-- 白色圆角矩形容器 -->
    <div
      class="form-container"
      @dragenter.prevent="onDocumentDragEnter"
      @dragover.prevent="onDocumentDragOver"
      @dragleave.prevent="onDocumentDragLeave"
      @drop.prevent="onDocumentDrop"
    >
      <Transition name="upload-drop-fade">
        <div
          v-if="creationMode === 'document' && dragOverActive && !uploadPending"
          class="upload-drop-overlay"
          aria-hidden="true"
        >
          <div class="upload-drop-inner">
            <svg
              class="upload-drop-icon"
              width="56"
              height="56"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M12 16V4m0 0l-4 4m4-4l4 4"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
              />
            </svg>
            <p class="upload-drop-text">将文件释放至此处以上传</p>
          </div>
        </div>
      </Transition>
      <!-- 顶部固定区域 -->
      <div class="form-header">
        <button class="back-btn" @click="handleBack">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <h2 class="form-title">{{ pageTitle }}</h2>
        <div
          class="creation-mode-switch"
          role="tablist"
          aria-label="创建方式"
        >
          <button
            type="button"
            class="creation-mode-option"
            :class="{ active: creationMode === 'scratch' }"
            role="tab"
            :aria-selected="creationMode === 'scratch'"
            @click="creationMode = 'scratch'"
          >
            从零开始创建
          </button>
          <button
            type="button"
            class="creation-mode-option"
            :class="{ active: creationMode === 'document' }"
            role="tab"
            :aria-selected="creationMode === 'document'"
            @click="creationMode = 'document'"
          >
            通过文档创建
          </button>
        </div>
      </div>

      <!-- 可滚动表单内容区域 -->
      <div class="form-scroll-area">
        <!-- 通过文档创建 -->
        <div v-if="creationMode === 'document'" class="form-body document-mode-body">

          <input
            ref="localUploadInputRef"
            type="file"
            class="local-upload-input"
            accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.webp,.bmp,.svg,.mp4,.webm,.mov,.mkv,.avi,.m4v"
            @change="onLocalUploadFileChange"
          />
          <button
            type="button"
            class="document-upload-zone"
            :class="{ 'is-uploading': uploadPending }"
            :disabled="uploadPending"
            @click="triggerLocalUpload"
          >
            <span v-if="uploadPending" class="document-upload-spinner" aria-hidden="true"></span>
            <svg
              v-else
              class="document-upload-icon"
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M12 16V4m0 0l-4 4m4-4l4 4"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
              />
            </svg>
            <span class="document-upload-title">
              {{ uploadPending ? '上传中…' : '点击或拖拽上传本地文件' }}
            </span>
            <span class="document-upload-sub">支持常见文档、图片与视频格式</span>
          </button>

          <div
            v-if="selectedDocumentSummary && !uploadPending"
            class="document-selected-banner"
          >
            已选择：{{ selectedDocumentSummary.name }}
          </div>

          <p class="document-mode-divider">或从已有资源中选择</p>

          <div v-if="loadingDocuments" class="document-mode-status">加载文档列表…</div>
          <div
            v-else-if="documentResources.length === 0 && !selectedDocumentSummary"
            class="document-mode-status"
          >
            暂无已有资源，请上传本地文件后使用
          </div>
          <ul v-else-if="documentResources.length > 0" class="document-resource-list">
            <li
              v-for="item in documentResources"
              :key="item.id"
              class="document-resource-item"
              :class="{ selected: selectedDocumentId === item.id }"
              @click="selectDocumentResource(item.id)"
            >
              <span class="document-resource-name">{{ item.name }}</span>
              <span class="document-resource-meta">{{ documentResourceMeta(item) }}</span>
            </li>
          </ul>
        </div>

        <!-- 从零开始创建（原有表单） -->
        <div v-else class="form-body">
          <p v-if="isCourseCreateFlow" class="course-create-hint">
            仅需填写课程名称即可快速创建；填写完整大纲必填项后，可通过右下角「创建课程并生成大纲」同时进入 AI 生成流程。
          </p>

          <div v-if="isCourseCreateFlow" class="form-row form-row--labels">
            <div class="form-field form-field--full">
              <label class="field-label">课程标签</label>
              <div class="course-labels-input">
                <span v-for="(tag, index) in courseLabels" :key="tag" class="course-label-chip">
                  {{ tag }}
                  <button type="button" class="course-label-remove" @click="removeCourseLabel(index)">×</button>
                </span>
                <div class="course-label-text-wrap">
                  <input
                    v-model="newCourseLabel"
                    type="text"
                    class="course-label-text"
                    placeholder="输入标签后回车"
                    @keydown.enter.prevent="addCourseLabel"
                    @blur="addCourseLabel"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- 第一行：课程名称、授课对象年级、课程类别 -->
          <div class="form-row">
            <div class="form-field">
              <label class="field-label">课程名称 <span class="required">*</span></label>
              <input
                type="text"
                class="field-input"
                v-model="formData.courseName"
                placeholder="请输入课程名称"
              />
            </div>
            <div class="form-field">
              <label class="field-label">授课对象年级 <span class="required">*</span></label>
              <div class="dropdown-wrapper">
                <button
                  type="button"
                  class="dropdown-btn"
                  @click="toggleDropdown('grade')"
                  @blur="onGradeBlur"
                >
                  <span>{{ formData.grade || '请选择' }}</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
                <div v-if="activeDropdown === 'grade'" class="dropdown-menu">
                  <div class="dropdown-item" @click="selectOption('grade', '本科生')">本科生</div>
                  <div class="dropdown-item" @click="selectOption('grade', '硕士研究生')">硕士研究生</div>
                  <div class="dropdown-item" @click="selectOption('grade', '博士生')">博士生</div>
                </div>
              </div>
            </div>
            <div class="form-field">
              <label class="field-label">课程类别 <span class="required">*</span></label>
              <div class="dropdown-wrapper">
                <button
                  type="button"
                  class="dropdown-btn"
                  @click="toggleDropdown('courseCategory')"
                  @blur="onCourseCategoryBlur"
                >
                  <span>{{ courseCategoryPlaceholder }}</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
                <div v-if="activeDropdown === 'courseCategory'" class="dropdown-menu">
                  <div
                    v-for="opt in courseCategoryOptions"
                    :key="opt"
                    class="dropdown-item"
                    @click="selectOption('courseCategory', opt)"
                  >
                    {{ opt }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 第二行：3个输入域 -->
          <div class="form-row">
            <div class="form-field form-field--with-range">
              <label class="field-label">学分 <span class="required">*</span></label>
              <input
                type="number"
                min="0"
                :max="CREDITS_SLIDER_MAX"
                step="0.5"
                class="field-input"
                v-model="formData.credits"
                placeholder="请输入学分"
                @blur="clampCreditsNonNegative"
              />
              <div class="range-control">
                <input
                  type="range"
                  class="range-slider"
                  :min="0"
                  :max="CREDITS_SLIDER_MAX"
                  step="0.5"
                  :value="creditsRangeValue"
                  :style="{ '--range-ratio': creditsRangeRatio }"
                  aria-label="学分滑动调节"
                  @input="onCreditsRangeInput"
                />
                <div class="range-ticks">
                  <span>0</span>
                  <span>{{ CREDITS_SLIDER_MAX }}</span>
                </div>
              </div>
            </div>
            <div class="form-field form-field--with-range">
              <label class="field-label">学时 <span class="required">*</span></label>
              <input
                type="number"
                min="0"
                :max="HOURS_SLIDER_MAX"
                step="1"
                class="field-input"
                v-model="formData.hours"
                placeholder="请输入学时"
                @blur="clampHoursNonNegative"
              />
              <div class="range-control">
                <input
                  type="range"
                  class="range-slider"
                  :min="0"
                  :max="HOURS_SLIDER_MAX"
                  step="1"
                  :value="hoursRangeValue"
                  :style="{ '--range-ratio': hoursRangeRatio }"
                  aria-label="学时滑动调节"
                  @input="onHoursRangeInput"
                />
                <div class="range-ticks">
                  <span>0</span>
                  <span>{{ HOURS_SLIDER_MAX }}</span>
                </div>
              </div>
            </div>
            <div class="form-field">
              <label class="field-label">授课对象专业 <span class="required">*</span></label>
              <input
                type="text"
                class="field-input"
                v-model="formData.major"
                placeholder="请输入专业"
              />
            </div>
          </div>

          <!-- 教学安排与考核方式：各仅填一项占比（%），另一项由 100 减去得出；授课方式据此隐式推导 -->
          <div class="form-row">
            <div class="form-group">
              <label class="group-label">教学安排 <span class="required">*</span></label>
              <div class="group-field form-field--with-range">
                <label class="field-label">线下学时占比（%）</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  class="field-input"
                  :class="{ 'field-input-error': !offlineHoursValid && formData.offlineHoursRatio !== '' }"
                  v-model="formData.offlineHoursRatio"
                  placeholder="0-100 整数"
                  @blur="clampOfflineHours"
                />
                <div class="range-control">
                  <input
                    type="range"
                    class="range-slider"
                    :min="0"
                    :max="RATIO_SLIDER_MAX"
                    step="1"
                    :value="offlineHoursRangeValue"
                    :style="{ '--range-ratio': offlineHoursRangeRatio }"
                    aria-label="线下学时占比滑动调节"
                    @input="onOfflineHoursRangeInput"
                  />
                  <div class="range-ticks">
                    <span>0</span>
                    <span>{{ RATIO_SLIDER_MAX }}</span>
                  </div>
                </div>
                <p v-if="offlineHoursValid && parsedOfflineHours !== null" class="ratio-hint">线上学时占比：{{ onlineHoursDisplay }}%</p>
                <p v-else-if="formData.offlineHoursRatio !== '' && !offlineHoursValid" class="ratio-error">请输入 0-100 的整数</p>
              </div>
            </div>

            <div class="form-group">
              <label class="group-label">考核方式 <span class="required">*</span></label>
              <div class="group-field form-field--with-range">
                <label class="field-label">线下成绩占比（%）</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  class="field-input"
                  :class="{ 'field-input-error': !offlineScoreValid && formData.offlineScoreRatio !== '' }"
                  v-model="formData.offlineScoreRatio"
                  placeholder="0-100 整数"
                  @blur="clampOfflineScore"
                />
                <div class="range-control">
                  <input
                    type="range"
                    class="range-slider"
                    :min="0"
                    :max="RATIO_SLIDER_MAX"
                    step="1"
                    :value="offlineScoreRangeValue"
                    :style="{ '--range-ratio': offlineScoreRangeRatio }"
                    aria-label="线下成绩占比滑动调节"
                    @input="onOfflineScoreRangeInput"
                  />
                  <div class="range-ticks">
                    <span>0</span>
                    <span>{{ RATIO_SLIDER_MAX }}</span>
                  </div>
                </div>
                <p v-if="offlineScoreValid && parsedOfflineScore !== null" class="ratio-hint">线上成绩占比：{{ onlineScoreDisplay }}%</p>
                <p v-else-if="formData.offlineScoreRatio !== '' && !offlineScoreValid" class="ratio-error">请输入 0-100 的整数</p>
              </div>
            </div>
          </div>

          <!-- 多行文本输入域（一行一个） -->
          <div class="form-row-single">
            <div class="form-field-full">
              <label class="field-label">预修要求</label>
              <textarea
                class="field-textarea"
                v-model="formData.prerequisites"
                placeholder="请输入预修要求"
                rows="4"
              ></textarea>
            </div>
          </div>

          <div class="form-row-single">
            <div class="form-field-full course-desc-builder">
              <div class="course-desc-header">
                <label class="field-label">课程介绍 <span class="required">*</span></label>
                <span class="course-desc-hint">点选卡片与关键词，智能组合生成</span>
              </div>

              <div class="course-desc-section">
                <span class="course-desc-section-label">课程定位</span>
                <div class="course-desc-theme-grid">
                  <button
                    v-for="theme in DESCRIPTION_THEMES"
                    :key="theme.id"
                    type="button"
                    class="course-desc-theme-card"
                    :class="{ 'is-active': selectedDescriptionThemeId === theme.id }"
                    @click="selectDescriptionTheme(theme.id)"
                  >
                    <span class="theme-card-icon" aria-hidden="true">{{ theme.icon }}</span>
                    <span class="theme-card-title">{{ theme.title }}</span>
                    <span class="theme-card-sub">{{ theme.subtitle }}</span>
                  </button>
                </div>
              </div>

              <div class="course-desc-section">
                <span class="course-desc-section-label">教学特色</span>
                <div class="course-desc-chip-row">
                  <button
                    v-for="chip in TEACHING_STYLE_CHIPS"
                    :key="chip.id"
                    type="button"
                    class="course-desc-chip"
                    :class="{ 'is-active': selectedTeachingStyleIds.includes(chip.id) }"
                    @click="toggleTeachingStyle(chip.id)"
                  >
                    {{ chip.label }}
                  </button>
                </div>
              </div>

              <div class="course-desc-section">
                <span class="course-desc-section-label">能力培养</span>
                <div class="course-desc-chip-row">
                  <button
                    v-for="chip in ABILITY_CHIPS"
                    :key="chip.id"
                    type="button"
                    class="course-desc-chip"
                    :class="{ 'is-active': selectedAbilityIds.includes(chip.id) }"
                    @click="toggleAbilityChip(chip.id)"
                  >
                    {{ chip.label }}
                  </button>
                </div>
              </div>

              <div class="course-desc-preview">
                <div class="course-desc-preview-head">
                  <span class="course-desc-preview-badge">AI 预览</span>
                  <button
                    v-if="descriptionPrefilledExternal"
                    type="button"
                    class="course-desc-rebuild-btn"
                    @click="rebuildDescriptionFromBuilder"
                  >
                    重新组合
                  </button>
                </div>
                <p class="course-desc-preview-text">{{ composedCourseDescription || '请选择课程定位，并可补充教学特色与能力关键词' }}</p>
              </div>

              <details class="course-desc-custom" @toggle="onCustomNoteDetailsToggle">
                <summary>补充一句（可选）</summary>
                <textarea
                  ref="descriptionCustomNoteEl"
                  class="field-input course-desc-custom-input"
                  v-model="descriptionCustomNote"
                  rows="1"
                  placeholder="例如：适合零基础学生选修"
                  maxlength="120"
                  @input="resizeCustomNoteInput"
                />
              </details>
            </div>
          </div>

          <div class="form-row-single">
            <div class="form-field-full">
              <label class="field-label">教学目标</label>
              <textarea
                class="field-textarea"
                v-model="formData.teachingObjectives"
                placeholder="请输入教学目标"
                rows="4"
              ></textarea>
            </div>
          </div>

          <div class="form-row-single">
            <div class="form-field-full">
              <label class="field-label">思政内容</label>
              <textarea
                class="field-textarea"
                v-model="formData.ideologicalPolitical"
                placeholder="请输入思政内容"
                rows="4"
              ></textarea>
            </div>
          </div>

          <div class="form-row-single">
            <div class="form-field-full">
              <div class="chapter-structure-header">
                <label class="field-label chapter-structure-title">章节结构</label>
                <button class="chapter-add-root-btn" type="button" @click="addRootChapter">
                  + 添加章节
                </button>
              </div>

              <div class="chapter-structure-frame">
                <div v-if="chapterTree.length === 0" class="chapter-empty">
                  暂无章节（选填），如需填写请点击“添加章节”
                </div>
                <div v-else class="chapter-tree">
                  <ChapterNode
                    v-for="node in chapterTree"
                    :key="node.id"
                    :node="node"
                    :depth="0"
                    :activeMenuId="activeChapterMenuId"
                    :maxDepth="3"
                    @toggle="toggleNode"
                    @openMenu="openChapterMenu"
                    @closeMenu="closeChapterMenu"
                    @addChild="addChildChapter"
                    @delete="deleteChapter"
                    @updateTitle="updateChapterTitle"
                    @updateDesc="updateChapterDesc"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部固定区域 -->
      <div class="form-footer">
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
        <div class="form-footer-actions">
          <template v-if="isCourseCreateFlow && creationMode === 'scratch'">
            <button
              type="button"
              class="confirm-btn"
              :disabled="loading || uploadPending"
              @click="handleQuickCourseCreate"
            >
              {{ loading ? '处理中...' : '快速新建课程' }}
            </button>
            <button
              type="button"
              class="confirm-btn confirm-btn--primary"
              :disabled="loading || uploadPending"
              @click="handleFullCourseCreateWithOutline"
            >
              {{ loading ? '处理中...' : '创建课程并生成大纲' }}
            </button>
          </template>
          <button
            v-else
            type="button"
            class="confirm-btn"
            :class="{ 'confirm-btn--primary': isCourseCreateFlow && creationMode === 'document' }"
            :disabled="loading || uploadPending || (creationMode === 'document' && !selectedDocumentId)"
            @click="handleConfirm"
          >
            {{ confirmButtonLabel }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { queryCourse, operateCourse } from '../../api/course'
import {
  applyPrefillSnapshot,
  buildPrefillSnapshot,
  loadCourseOutlinePrefill,
  saveCourseOutlinePrefill,
  normalizeCourseDescriptionText,
} from '../../lib/courseOutlineBridge'
import { useUserStore } from '../../stores/user'
import {
  operateResource,
  listResources,
  queryResource,
  getResourceFilePath,
  uploadResourceFile,
  resolveReadonlyResourceMarkdown,
} from '../../api/resource'
import { isExtensionAllowed } from '../../api/attachment'
import type { CourseExtraInfo, OutlineForm, ResourceResponse } from '../../api/types'
import { OperationEnum, ResourceTypeEnum } from '../../api/types'
import ChapterNode, { type ChapterNodeModel, type ChapterKind } from '../ChapterNode.vue'
import ConfirmDialogModal from '../ConfirmDialogModal.vue'

export type OutlineFormFlow = 'resource' | 'course-create' | 'course-bound'

const props = withDefaults(
  defineProps<{
    /** resource：我的资源新建大纲；course-create：我的课程新建课程；course-bound：课程详情生成大纲 */
    flow?: OutlineFormFlow
    /** 绑定课程 id（course-bound 时由父级传入） */
    boundCourseId?: string | null
  }>(),
  {
    flow: 'resource',
    boundCourseId: null,
  }
)

const router = useRouter()
const userStore = useUserStore()

const boundCourseId = toRef(props, 'boundCourseId')

/** 新建课程流程（我的课程入口） */
const isCourseCreateFlow = computed(() => props.flow === 'course-create')

const pageTitle = computed(() => (isCourseCreateFlow.value ? '新建课程' : '大纲生成'))

const confirmButtonLabel = computed(() => {
  if (loading.value) return '处理中...'
  if (creationMode.value === 'document') {
    return isCourseCreateFlow.value ? '创建课程并生成大纲' : '下一步'
  }
  return '确认'
})

const courseLabels = ref<string[]>([])
const newCourseLabel = ref('')

function addCourseLabel() {
  const label = newCourseLabel.value.trim()
  if (label && !courseLabels.value.includes(label)) {
    courseLabels.value.push(label)
  }
  newCourseLabel.value = ''
}

function removeCourseLabel(index: number) {
  courseLabels.value.splice(index, 1)
}

type CreationMode = 'scratch' | 'document'

const creationMode = ref<CreationMode>('scratch')
const activeDropdown = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const loadingDocuments = ref(false)
const documentResources = ref<ResourceResponse[]>([])
const selectedDocumentId = ref<string | null>(null)
/** 本地上传后拉取的详情（列表接口可能尚未包含该条） */
const pinnedDocumentDetail = ref<ResourceResponse | null>(null)

const selectedDocumentSummary = computed(() => {
  const id = selectedDocumentId.value
  if (!id) return null
  const inList = documentResources.value.find((r) => r.id === id)
  if (inList) return inList
  if (pinnedDocumentDetail.value?.id === id) return pinnedDocumentDetail.value
  return null
})
const localUploadInputRef = ref<HTMLInputElement | null>(null)
const uploadPending = ref(false)
const dragDepth = ref(0)
const dragOverActive = computed(() => dragDepth.value > 0)
const uploadAlertVisible = ref(false)
const uploadAlertTitle = ref('提示')
const uploadAlertMessage = ref('')

function uid(prefix = 'node') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

const CREDITS_SLIDER_MAX = 10
const HOURS_SLIDER_MAX = 128
const RATIO_SLIDER_MAX = 100

const formData = ref({
  courseName: '示例课程',
  courseCategory: '通识必修课',
  credits: '2',
  hours: '32',
  major: '不限专业',
  grade: '本科生',
  teachingMethod: '混合',
  offlineHoursRatio: '50',
  offlineScoreRatio: '50',
  prerequisites: '无特殊要求',
  courseDescription:
    '本课程系统介绍相关领域的基本理论、方法与实践，培养学生分析与综合应用能力。',
  teachingObjectives:
    '学生能够掌握本课程核心概念与基本技能，具备进一步学习与应用的基础。',
  ideologicalPolitical: '结合课程教学内容，融入社会主义核心价值观与立德树人要求。',
})

/** 课程介绍：定位卡片 */
const DESCRIPTION_THEMES = [
  {
    id: 'theory-practice',
    icon: '📘',
    title: '理论+实践',
    subtitle: '夯实基础、知行合一',
    sentence: '本课程系统介绍相关领域的基本理论、方法与实践',
    matchKey: '基本理论、方法与实践',
  },
  {
    id: 'theory-intro',
    icon: '📖',
    title: '理论导论',
    subtitle: '概念框架与知识体系',
    sentence: '本课程系统梳理相关领域的核心概念与理论框架',
    matchKey: '核心概念与理论框架',
  },
  {
    id: 'applied',
    icon: '🔧',
    title: '应用导向',
    subtitle: '问题导向、学以致用',
    sentence: '本课程以典型问题为导向，强调理论联系实际的应用能力培养',
    matchKey: '理论联系实际',
  },
  {
    id: 'frontier',
    icon: '🚀',
    title: '前沿交叉',
    subtitle: '拓展视野、激发创新',
    sentence: '本课程聚焦学科前沿与交叉议题，拓展学生的学术视野与创新思维',
    matchKey: '学科前沿与交叉',
  },
  {
    id: 'literacy',
    icon: '🌐',
    title: '素养提升',
    subtitle: '知识能力与品格并重',
    sentence: '本课程立足综合素质培养，兼顾知识、能力与价值观念的协调发展',
    matchKey: '综合素质培养',
  },
] as const

/** 课程介绍：教学特色关键词 */
const TEACHING_STYLE_CHIPS = [
  { id: 'case', label: '案例教学', phrase: '案例教学' },
  { id: 'project', label: '项目驱动', phrase: '项目驱动' },
  { id: 'seminar', label: '研讨互动', phrase: '研讨互动' },
  { id: 'flipped', label: '翻转课堂', phrase: '翻转课堂' },
  { id: 'lab', label: '实验实训', phrase: '实验实训' },
] as const

/** 课程介绍：能力培养关键词 */
const ABILITY_CHIPS = [
  { id: 'analysis', label: '分析应用', phrase: '分析与综合应用' },
  { id: 'critical', label: '批判思维', phrase: '批判性思维' },
  { id: 'teamwork', label: '团队协作', phrase: '团队协作' },
  { id: 'writing', label: '学术写作', phrase: '学术写作' },
  { id: 'hands-on', label: '动手实践', phrase: '动手实践' },
  { id: 'data', label: '数据素养', phrase: '数据素养' },
  { id: 'innovation', label: '创新设计', phrase: '创新设计' },
  { id: 'communication', label: '沟通表达', phrase: '沟通表达' },
] as const

const selectedDescriptionThemeId = ref<string>('theory-practice')
const selectedTeachingStyleIds = ref<string[]>([])
const selectedAbilityIds = ref<string[]>(['analysis'])
const descriptionCustomNote = ref('')
const descriptionCustomNoteEl = ref<HTMLTextAreaElement | null>(null)

function resizeCustomNoteInput() {
  const el = descriptionCustomNoteEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function onCustomNoteDetailsToggle() {
  nextTick(resizeCustomNoteInput)
}

const descriptionPrefilledExternal = ref(false)
const descriptionSyncLock = ref(false)

function clearExternalDescriptionMode() {
  descriptionPrefilledExternal.value = false
}

function buildCourseDescriptionText(): string {
  const theme = DESCRIPTION_THEMES.find((t) => t.id === selectedDescriptionThemeId.value)
  if (!theme) return ''

  const parts: string[] = [theme.sentence]

  const teaching = selectedTeachingStyleIds.value
    .map((id) => TEACHING_STYLE_CHIPS.find((c) => c.id === id)?.phrase)
    .filter(Boolean) as string[]
  if (teaching.length) parts.push(`课程采用${teaching.join('、')}等教学方式`)

  const abilities = selectedAbilityIds.value
    .map((id) => ABILITY_CHIPS.find((c) => c.id === id)?.phrase)
    .filter(Boolean) as string[]
  if (abilities.length) parts.push(`着力培养学生的${abilities.join('、')}能力`)

  const custom = descriptionCustomNote.value.trim()
  if (custom) parts.push(custom)

  let text = parts.join('，')
  if (text && !text.endsWith('。')) text += '。'
  return text
}

const composedCourseDescription = computed(() => {
  const built = buildCourseDescriptionText()
  if (descriptionPrefilledExternal.value) {
    const external = normalizeCourseDescriptionText(formData.value.courseDescription)
    return external || built
  }
  return built
})

function ensureDefaultDescriptionBuilderState() {
  if (!selectedDescriptionThemeId.value) {
    selectedDescriptionThemeId.value = 'theory-practice'
  }
  if (selectedAbilityIds.value.length === 0) {
    selectedAbilityIds.value = ['analysis']
  }
}

/** 预填或重置后，保证外部文案模式与组合器状态一致，并同步 formData */
function reconcileCourseDescriptionState() {
  const normalized = normalizeCourseDescriptionText(formData.value.courseDescription)
  if (descriptionPrefilledExternal.value && !normalized) {
    descriptionPrefilledExternal.value = false
  }
  ensureDefaultDescriptionBuilderState()
  if (!descriptionPrefilledExternal.value) {
    const built = buildCourseDescriptionText()
    if (built) {
      descriptionSyncLock.value = true
      formData.value.courseDescription = built
      descriptionSyncLock.value = false
    }
  }
}

function selectDescriptionTheme(id: string) {
  clearExternalDescriptionMode()
  selectedDescriptionThemeId.value = id
}

function toggleTeachingStyle(id: string) {
  clearExternalDescriptionMode()
  const list = selectedTeachingStyleIds.value
  const idx = list.indexOf(id)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(id)
}

function toggleAbilityChip(id: string) {
  clearExternalDescriptionMode()
  const list = selectedAbilityIds.value
  const idx = list.indexOf(id)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(id)
}

/** 尝试从已有文案反推选中的卡片/关键词 */
function parseDescriptionIntoBuilder(text: string): boolean {
  const raw = text.trim()
  if (!raw) return false

  let matched = false
  const theme = DESCRIPTION_THEMES.find((t) => raw.includes(t.matchKey) || raw.includes(t.sentence))
  if (theme) {
    selectedDescriptionThemeId.value = theme.id
    matched = true
  }

  selectedTeachingStyleIds.value = TEACHING_STYLE_CHIPS.filter((c) => raw.includes(c.phrase)).map((c) => c.id)
  if (selectedTeachingStyleIds.value.length) matched = true

  selectedAbilityIds.value = ABILITY_CHIPS.filter((c) => raw.includes(c.phrase)).map((c) => c.id)
  if (selectedAbilityIds.value.length) matched = true

  descriptionCustomNote.value = ''
  return matched
}

function rebuildDescriptionFromBuilder() {
  const text = formData.value.courseDescription
  descriptionPrefilledExternal.value = false
  parseDescriptionIntoBuilder(text)
  if (!selectedDescriptionThemeId.value) {
    selectedDescriptionThemeId.value = 'theory-practice'
  }
  formData.value.courseDescription = buildCourseDescriptionText()
}

watch(
  composedCourseDescription,
  (text) => {
    if (descriptionSyncLock.value) return
    if (
      descriptionPrefilledExternal.value &&
      normalizeCourseDescriptionText(formData.value.courseDescription)
    ) {
      return
    }
    formData.value.courseDescription = text
  },
  { immediate: true }
)

watch(descriptionCustomNote, () => {
  if (!descriptionSyncLock.value) clearExternalDescriptionMode()
  nextTick(resizeCustomNoteInput)
})

function documentResourceMeta(item: ResourceResponse): string {
  const path = getResourceFilePath(item)
  if (path) return '只读文件'
  if (item.content?.trim()) return '可编辑内容'
  if ((item.word_count ?? 0) > 0) return '含正文'
  return '打开后加载详情'
}

async function ensureUserForDocuments() {
  if (!userStore.currentUser) {
    await userStore.fetchCurrentUser()
  }
}

function selectDocumentResource(id: string) {
  selectedDocumentId.value = id
  if (pinnedDocumentDetail.value?.id !== id) {
    pinnedDocumentDetail.value = null
  }
}

async function loadDocumentResources() {
  await ensureUserForDocuments()
  loadingDocuments.value = true
  try {
    const userId = userStore.currentUser?.id
    const list = await listResources(userId ? { user_id: userId } : {})
    // 列表接口不含 path/content，展示全部资源供选择，确认时再 query 详情
    documentResources.value = list
    const selectedId = selectedDocumentId.value
    if (
      selectedId &&
      !documentResources.value.some((r) => r.id === selectedId) &&
      pinnedDocumentDetail.value?.id !== selectedId
    ) {
      selectedDocumentId.value = null
      pinnedDocumentDetail.value = null
    }
  } catch (e) {
    console.error('[OutlineForm] 加载文档列表失败', e)
    documentResources.value = []
  } finally {
    loadingDocuments.value = false
  }
}

function resetDragDepth() {
  dragDepth.value = 0
}

function showUploadAlert(title: string, message: string) {
  uploadAlertTitle.value = title
  uploadAlertMessage.value = message
  uploadAlertVisible.value = true
}

function closeUploadAlert() {
  uploadAlertVisible.value = false
}

function isFileDragEvent(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  if (!types) return false
  return Array.from(types).includes('Files')
}

function onDocumentDragEnter(event: DragEvent) {
  if (creationMode.value !== 'document' || !isFileDragEvent(event) || uploadPending.value) return
  dragDepth.value += 1
}

function onDocumentDragOver(event: DragEvent) {
  if (creationMode.value !== 'document' || !isFileDragEvent(event) || uploadPending.value) return
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

function onDocumentDragLeave(event: DragEvent) {
  if (creationMode.value !== 'document' || !isFileDragEvent(event)) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
}

async function onDocumentDrop(event: DragEvent) {
  dragDepth.value = 0
  if (creationMode.value !== 'document' || uploadPending.value) return
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  await uploadLocalFile(file)
}

function triggerLocalUpload() {
  if (uploadPending.value) return
  localUploadInputRef.value?.click()
}

async function onLocalUploadFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await uploadLocalFile(file)
}

async function uploadLocalFile(file: File) {
  if (uploadPending.value) return
  if (!isExtensionAllowed(file)) {
    showUploadAlert(
      '无法上传',
      '不支持该文件格式，请上传常见文档、图片或视频文件。',
    )
    return
  }
  uploadPending.value = true
  error.value = null
  try {
    await ensureUserForDocuments()
    const resourceId = await uploadResourceFile(file, {
      resourceType: ResourceTypeEnum.Outline,
      relatedUserId: userStore.currentUser?.id,
    })
    let detail: ResourceResponse | null = null
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        detail = await queryResource(resourceId)
        break
      } catch (queryErr) {
        if (attempt === 0) {
          await new Promise((resolve) => setTimeout(resolve, 350))
          continue
        }
        console.warn('[OutlineForm] 上传后查询资源详情失败，使用最小信息继续', queryErr)
        detail = {
          id: resourceId,
          name: file.name,
          resource_type: ResourceTypeEnum.Outline,
          word_count: 0,
          editable: true,
          create_time: new Date().toISOString(),
          update_time: new Date().toISOString(),
        }
      }
    }
    if (!detail) {
      throw new Error('上传成功但无法获取资源信息，请刷新后重试')
    }
    pinnedDocumentDetail.value = detail
    selectedDocumentId.value = detail.id
    const existingIdx = documentResources.value.findIndex((r) => r.id === detail.id)
    if (existingIdx >= 0) {
      documentResources.value[existingIdx] = { ...documentResources.value[existingIdx], ...detail }
    } else {
      documentResources.value = [detail, ...documentResources.value]
    }
    await loadDocumentResources()
    selectedDocumentId.value = detail.id
    if (!documentResources.value.some((r) => r.id === detail.id)) {
      documentResources.value = [detail, ...documentResources.value]
    }
  } catch (err) {
    console.error('[OutlineForm] 本地上传失败', err)
    showUploadAlert(
      '上传失败',
      err instanceof Error ? err.message : '上传失败，请稍后重试。',
    )
  } finally {
    uploadPending.value = false
  }
}

watch(creationMode, (mode) => {
  error.value = null
  if (mode === 'document') {
    void loadDocumentResources()
  } else {
    resetDragDepth()
  }
})

onMounted(() => {
  nextTick(resizeCustomNoteInput)
  window.addEventListener('dragend', resetDragDepth)
})

onBeforeUnmount(() => {
  window.removeEventListener('dragend', resetDragDepth)
})

const chapterTree = ref<ChapterNodeModel[]>([])

const activeChapterMenuId = ref<string | null>(null)

function addRootChapter() {
  chapterTree.value.push({
    id: uid('chapter'),
    kind: 'chapter',
    title: '',
    description: '',
    collapsed: false,
    children: [],
  })
}

function findNodeAndParent(
  nodes: ChapterNodeModel[],
  id: string,
  parent: ChapterNodeModel | null = null
  ,
  depth = 0
): { node: ChapterNodeModel; parent: ChapterNodeModel | null; depth: number } | null {
  for (const n of nodes) {
    if (n.id === id) return { node: n, parent, depth }
    const hit = findNodeAndParent(n.children, id, n, depth + 1)
    if (hit) return hit
  }
  return null
}

function toggleNode(id: string) {
  const hit = findNodeAndParent(chapterTree.value, id)
  if (!hit) return
  hit.node.collapsed = !hit.node.collapsed
}

function openChapterMenu(id: string) {
  activeChapterMenuId.value = id
}
function closeChapterMenu() {
  activeChapterMenuId.value = null
}

function addChildChapter(parentId: string) {
  const hit = findNodeAndParent(chapterTree.value, parentId)
  if (!hit) return
  // 限制最大 3 层：章(0) - 节(1) - 节(2)
  if (hit.depth >= 2) {
    error.value = '章节最多支持 3 层（章-节-节）'
    activeChapterMenuId.value = null
    return
  }
  hit.node.collapsed = false
  hit.node.children.push({
    id: uid('section'),
    kind: 'section',
    title: '',
    description: '',
    collapsed: false,
    children: [],
  })
  activeChapterMenuId.value = null
}

function deleteChapter(id: string) {
  const hit = findNodeAndParent(chapterTree.value, id)
  if (!hit) return
  const { parent } = hit
  if (!parent) {
    chapterTree.value = chapterTree.value.filter((n) => n.id !== id)
  } else {
    parent.children = parent.children.filter((n) => n.id !== id)
  }
  if (activeChapterMenuId.value === id) activeChapterMenuId.value = null
}

function updateChapterTitle(id: string, title: string) {
  const hit = findNodeAndParent(chapterTree.value, id)
  if (!hit) return
  hit.node.title = title
}
function updateChapterDesc(id: string, desc: string) {
  const hit = findNodeAndParent(chapterTree.value, id)
  if (!hit) return
  hit.node.description = desc
}

function hasEmptyChapterTitle(nodes: ChapterNodeModel[]): boolean {
  for (const n of nodes) {
    if (!String(n.title ?? '').trim()) return true
    if (n.children?.length && hasEmptyChapterTitle(n.children)) return true
  }
  return false
}

/** 当从课程页进入（带 course_id）时，拉取课程信息并预填表单中的课程名称、学时、课程介绍 */
async function prefillFromCourse(courseId: string) {
  try {
    const course = await queryCourse(courseId)
    formData.value.courseName = course.name ?? ''
    formData.value.hours = course.lesson_count != null ? String(course.lesson_count) : ''
    if (course.labels?.length) courseLabels.value = [...course.labels]
    const desc = normalizeCourseDescriptionText(course.description)
    descriptionSyncLock.value = true
    if (desc) {
      formData.value.courseDescription = desc
      const parsed = parseDescriptionIntoBuilder(desc)
      descriptionPrefilledExternal.value = !parsed
    } else {
      descriptionPrefilledExternal.value = false
      ensureDefaultDescriptionBuilderState()
    }
    descriptionSyncLock.value = false

    const stored = loadCourseOutlinePrefill(courseId)
    if (stored) {
      applyPrefillSnapshot(stored, formData, chapterTree, courseLabels)
      const storedDesc = normalizeCourseDescriptionText(stored.courseDescription)
      if (storedDesc) {
        descriptionSyncLock.value = true
        formData.value.courseDescription = storedDesc
        const parsed = parseDescriptionIntoBuilder(storedDesc)
        descriptionPrefilledExternal.value = !parsed
        descriptionSyncLock.value = false
      }
    }

    reconcileCourseDescriptionState()
  } catch (e) {
    console.warn('预填课程信息失败:', e)
    reconcileCourseDescriptionState()
  }
}

function initFormForCourseCreate() {
  formData.value = {
    courseName: '',
    courseCategory: '通识必修课',
    credits: '',
    hours: '',
    major: '',
    grade: '本科生',
    teachingMethod: '混合',
    offlineHoursRatio: '50',
    offlineScoreRatio: '50',
    prerequisites: '',
    courseDescription: '',
    teachingObjectives: '',
    ideologicalPolitical: '',
  }
  courseLabels.value = []
  chapterTree.value = []
  descriptionPrefilledExternal.value = false
  selectedDescriptionThemeId.value = 'theory-practice'
  selectedTeachingStyleIds.value = []
  selectedAbilityIds.value = ['analysis']
  descriptionCustomNote.value = ''
  reconcileCourseDescriptionState()
}

function parseLessonCountFromForm(): number | undefined {
  const hoursStr = String(formData.value.hours).trim()
  if (!hoursStr) return undefined
  const n = Math.round(parseFloat(hoursStr))
  if (Number.isNaN(n) || n < 0) return undefined
  return Math.min(HOURS_SLIDER_MAX, n)
}

/**
 * 从表单组装课程展示扩展信息（extra_info，snake_case 与后端契约一致）。
 * 数字字段空值/NaN 兜底为 undefined，字符串字段 trim 后为空则 undefined。
 */
function buildCourseExtraInfo(): CourseExtraInfo {
  const f = formData.value
  const num = (v: unknown, parser: (s: string) => number): number | undefined => {
    const s = String(v ?? '').trim()
    if (!s) return undefined
    const n = parser(s)
    return Number.isNaN(n) ? undefined : n
  }
  const str = (v: unknown): string | undefined => {
    const s = String(v ?? '').trim()
    return s || undefined
  }
  return {
    grade: str(f.grade),
    category: str(f.courseCategory),
    credits: num(f.credits, parseFloat),
    major: str(f.major),
    offline_hours_ratio: num(f.offlineHoursRatio, (s) => parseInt(s, 10)),
    offline_score_ratio: num(f.offlineScoreRatio, (s) => parseInt(s, 10)),
  }
}

async function createCourseFromForm(): Promise<string> {
  const name = formData.value.courseName.trim()
  if (!name) throw new Error('请输入课程名称')
  const courseId = await operateCourse({
    operation: OperationEnum.CREATE,
    name,
    manager_ids: userStore.currentUser?.id ? [userStore.currentUser.id] : undefined,
    lesson_count: parseLessonCountFromForm(),
    description: normalizeCourseDescriptionText(formData.value.courseDescription) || undefined,
    labels: courseLabels.value.length ? courseLabels.value : undefined,
    extra_info: buildCourseExtraInfo(),
  })
  if (!courseId) throw new Error('创建课程失败')
  saveCourseOutlinePrefill(
    courseId,
    buildPrefillSnapshot(formData.value, chapterTree.value, courseLabels.value)
  )
  return courseId
}

/** 将大纲表单中的课程元数据写回后端，供课程详情页展示与后续进入时保留 */
async function syncBoundCourseFromForm(courseId: string): Promise<void> {
  const name = formData.value.courseName.trim()
  let description = normalizeCourseDescriptionText(formData.value.courseDescription)
  if (!description) {
    description = normalizeCourseDescriptionText(buildCourseDescriptionText())
  }
  await operateCourse({
    operation: OperationEnum.UPDATE,
    id: courseId,
    ...(name ? { name } : {}),
    ...(description ? { description } : {}),
    lesson_count: parseLessonCountFromForm(),
    labels: [...courseLabels.value],
    extra_info: buildCourseExtraInfo(),
  })
}

async function handleQuickCourseCreate() {
  if (!formData.value.courseName.trim()) {
    error.value = '请输入课程名称'
    return
  }
  loading.value = true
  error.value = null
  try {
    const courseId = await createCourseFromForm()
    router.push(`/course/${courseId}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建课程失败'
  } finally {
    loading.value = false
  }
}

watch(
  boundCourseId,
  (id) => {
    if (id) prefillFromCourse(id)
  },
  { immediate: true }
)

watch(
  isCourseCreateFlow,
  (active) => {
    if (active) {
      creationMode.value = 'scratch'
      initFormForCourseCreate()
    }
  },
  { immediate: true }
)

/** 本科生课程类别 */
const UNDERGRADUATE_CATEGORIES = ['通识必修课', '通识选修课', '专业基础课程', '专业课程']
/** 研究生课程类别（硕士/博士共用） */
const GRADUATE_CATEGORIES = ['专业选修课', '专业学位课']
const ALL_COURSE_CATEGORIES = [...UNDERGRADUATE_CATEGORIES, ...GRADUATE_CATEGORIES]

/** 切换年级后，若原课程类别不适用则回落到该年级默认类别 */
const DEFAULT_CATEGORY_BY_GRADE: Record<string, string> = {
  本科生: '通识必修课',
  硕士研究生: '专业选修课',
  博士生: '专业选修课',
}

function defaultCategoryForGrade(grade: string): string {
  const preset = DEFAULT_CATEGORY_BY_GRADE[grade]
  if (preset) return preset
  const options = categoriesForGrade(grade)
  return options[0] ?? ''
}

function categoriesForGrade(grade: string): string[] {
  if (grade === '本科生') return UNDERGRADUATE_CATEGORIES
  if (grade === '硕士研究生' || grade === '博士生') return GRADUATE_CATEGORIES
  return ALL_COURSE_CATEGORIES
}

function inferGradeFromCategory(category: string): string {
  if (UNDERGRADUATE_CATEGORIES.includes(category)) return '本科生'
  if (GRADUATE_CATEGORIES.includes(category)) {
    const g = formData.value.grade.trim()
    if (g === '博士生' || g === '硕士研究生') return g
    return '硕士研究生'
  }
  return ''
}

/** 未选年级时展示全部类别；已选年级时收窄列表 */
const courseCategoryOptions = computed(() => {
  const grade = formData.value.grade.trim()
  if (!grade) return ALL_COURSE_CATEGORIES
  return categoriesForGrade(grade)
})

/** 课程类别下拉框占位文案 */
const courseCategoryPlaceholder = computed(() => {
  if (!formData.value.courseCategory.trim()) return '请选择'
  return formData.value.courseCategory
})

/** 年级 / 课程类别失焦时双向匹配（不限制填写顺序） */
function syncGradeAndCategoryMatch() {
  const grade = formData.value.grade.trim()
  const category = formData.value.courseCategory.trim()

  if (category) {
    const inferred = inferGradeFromCategory(category)
    if (inferred) {
      const allowed = categoriesForGrade(inferred)
      if (!grade || !allowed.includes(category)) {
        formData.value.grade = inferred
      }
    }
  }

  const gradeAfter = formData.value.grade.trim()
  if (gradeAfter) {
    const allowed = categoriesForGrade(gradeAfter)
    const current = formData.value.courseCategory.trim()
    if (!current || !allowed.includes(current)) {
      formData.value.courseCategory = defaultCategoryForGrade(gradeAfter)
    }
  }
}

function onGradeBlur() {
  syncGradeAndCategoryMatch()
}

function onCourseCategoryBlur() {
  syncGradeAndCategoryMatch()
}

/** 根据课程类别自动得到课程性质（只读展示与提交用） */
const COURSE_CATEGORY_TO_NATURE: Record<string, string> = {
  通识必修课: '必修课',
  通识选修课: '选修课',
  专业基础课程: '必修课',
  专业课程: '必修课',
  专业选修课: '选修课',
  专业学位课: '必修课',
}
const courseNatureFromCategory = computed(() => {
  const cat = formData.value.courseCategory.trim()
  return cat ? (COURSE_CATEGORY_TO_NATURE[cat] ?? '') : ''
})

/** 解析线下学时占比，合法为 [0,100] 的整数，否则 null */
const parsedOfflineHours = computed(() => {
  const s = String(formData.value.offlineHoursRatio).trim()
  if (s === '') return null
  const n = parseInt(s, 10)
  if (Number.isNaN(n) || n < 0 || n > 100) return null
  return n
})
/** 解析线下成绩占比，合法为 [0,100] 的整数，否则 null */
const parsedOfflineScore = computed(() => {
  const s = String(formData.value.offlineScoreRatio).trim()
  if (s === '') return null
  const n = parseInt(s, 10)
  if (Number.isNaN(n) || n < 0 || n > 100) return null
  return n
})
const offlineHoursValid = computed(() => parsedOfflineHours.value !== null || formData.value.offlineHoursRatio === '')
const offlineScoreValid = computed(() => parsedOfflineScore.value !== null || formData.value.offlineScoreRatio === '')
const onlineHoursDisplay = computed(() => parsedOfflineHours.value !== null ? 100 - parsedOfflineHours.value : '')
const onlineScoreDisplay = computed(() => parsedOfflineScore.value !== null ? 100 - parsedOfflineScore.value : '')

/** 根据教学安排、考核方式隐式推导授课方式（不展示下拉） */
const inferredTeachingMethod = computed(() => {
  const hours = parsedOfflineHours.value
  const score = parsedOfflineScore.value
  if (hours === null || score === null) return ''
  if (hours === 0 && score === 0) return '线上'
  if (hours === 100 && score === 100) return '线下'
  return '混合'
})

watch(
  inferredTeachingMethod,
  (method) => {
    if (method) formData.value.teachingMethod = method
  },
  { immediate: true },
)

function parseCreditsNumber(): number | null {
  const s = String(formData.value.credits).trim()
  if (s === '') return null
  const n = parseFloat(s)
  return Number.isNaN(n) ? null : n
}

function parseHoursNumber(): number | null {
  const s = String(formData.value.hours).trim()
  if (s === '') return null
  const n = parseFloat(s)
  return Number.isNaN(n) ? null : n
}

const creditsRangeValue = computed(() => {
  const n = parseCreditsNumber()
  if (n === null) return 0
  return Math.min(CREDITS_SLIDER_MAX, Math.max(0, n))
})

const hoursRangeValue = computed(() => {
  const n = parseHoursNumber()
  if (n === null) return 0
  return Math.min(HOURS_SLIDER_MAX, Math.max(0, Math.round(n)))
})

const creditsRangeRatio = computed(() =>
  CREDITS_SLIDER_MAX > 0 ? creditsRangeValue.value / CREDITS_SLIDER_MAX : 0,
)

const hoursRangeRatio = computed(() =>
  HOURS_SLIDER_MAX > 0 ? hoursRangeValue.value / HOURS_SLIDER_MAX : 0,
)

function onCreditsRangeInput(e: Event) {
  formData.value.credits = String((e.target as HTMLInputElement).value)
}


const offlineHoursRangeValue = computed(() => {
  const n = parsedOfflineHours.value
  return n === null ? 0 : n
})

const offlineScoreRangeValue = computed(() => {
  const n = parsedOfflineScore.value
  return n === null ? 0 : n
})

const offlineHoursRangeRatio = computed(() =>
  RATIO_SLIDER_MAX > 0 ? offlineHoursRangeValue.value / RATIO_SLIDER_MAX : 0,
)

const offlineScoreRangeRatio = computed(() =>
  RATIO_SLIDER_MAX > 0 ? offlineScoreRangeValue.value / RATIO_SLIDER_MAX : 0,
)

function onOfflineHoursRangeInput(e: Event) {
  formData.value.offlineHoursRatio = String((e.target as HTMLInputElement).value)
}

function onOfflineScoreRangeInput(e: Event) {
  formData.value.offlineScoreRatio = String((e.target as HTMLInputElement).value)
}

function onHoursRangeInput(e: Event) {
  formData.value.hours = String((e.target as HTMLInputElement).value)
}

/** 学分：失焦时去掉负数与非法值（须为非负数） */
function clampCreditsNonNegative() {
  const s = String(formData.value.credits).trim()
  if (s === '') return
  const n = parseFloat(s)
  if (Number.isNaN(n) || n < 0) {
    formData.value.credits = '0'
  } else {
    formData.value.credits = String(Math.min(CREDITS_SLIDER_MAX, n))
  }
}

/** 学时：失焦时去掉负数与非法值（须为非负数） */
function clampHoursNonNegative() {
  const s = String(formData.value.hours).trim()
  if (s === '') return
  const n = parseFloat(s)
  if (Number.isNaN(n) || n < 0) {
    formData.value.hours = '0'
  } else {
    formData.value.hours = String(Math.min(HOURS_SLIDER_MAX, Math.round(n)))
  }
}

function clampOfflineHours() {
  const s = String(formData.value.offlineHoursRatio).trim()
  if (s === '') return
  const n = parseInt(s, 10)
  if (Number.isNaN(n) || n < 0 || n > 100) {
    formData.value.offlineHoursRatio = ''
  } else {
    formData.value.offlineHoursRatio = String(n)
  }
}
function clampOfflineScore() {
  const s = String(formData.value.offlineScoreRatio).trim()
  if (s === '') return
  const n = parseInt(s, 10)
  if (Number.isNaN(n) || n < 0 || n > 100) {
    formData.value.offlineScoreRatio = ''
  } else {
    formData.value.offlineScoreRatio = String(n)
  }
}

const handleBack = () => {
  if (props.flow === 'course-create') {
    router.push('/my-courses')
    return
  }
  const courseId = boundCourseId.value?.trim()
  if (courseId) {
    router.push(`/course/${courseId}`)
  } else {
    router.push('/my-courses')
  }
}

const toggleDropdown = (field: string) => {
  if (activeDropdown.value === field) {
    activeDropdown.value = null
  } else {
    activeDropdown.value = field
  }
}

const selectOption = (field: keyof typeof formData.value, value: string) => {
  formData.value[field] = value
  activeDropdown.value = null
  if (field === 'grade' || field === 'courseCategory') {
    syncGradeAndCategoryMatch()
  }
}

/** 必填校验：按表单项顺序检查，返回首个错误文案，全部通过返回 null */
function validateRequired(): string | null {
  const d = formData.value
  if (!d.courseName.trim()) return '请输入课程名称'
  if (!d.grade.trim()) return '请选择授课对象年级'
  if (!d.courseCategory.trim()) return '请选择课程类别'
  const creditsStr = String(d.credits).trim()
  if (!creditsStr) return '请输入学分'
  const creditsNum = parseFloat(creditsStr)
  if (Number.isNaN(creditsNum) || creditsNum < 0) return '请输入非负的学分'
  const hoursStr = String(d.hours).trim()
  if (!hoursStr) return '请输入学时'
  const hoursNum = parseFloat(hoursStr)
  if (Number.isNaN(hoursNum) || hoursNum < 0) return '请输入非负的学时'
  if (!d.major.trim()) return '请输入授课对象专业'
  if (parsedOfflineHours.value === null) return '请填写线下学时占比（0-100 的整数）'
  if (parsedOfflineScore.value === null) return '请填写线下成绩占比（0-100 的整数）'
  if (!d.courseDescription.trim()) {
    if (!descriptionPrefilledExternal.value && !selectedDescriptionThemeId.value) return '请选择课程定位'
    return '请完成课程介绍'
  }
  // 章节结构为选填：不做必填校验；若用户填写了章节，则要求标题不为空
  if (chapterTree.value.length && hasEmptyChapterTitle(chapterTree.value)) return '请完善章节标题'
  return null
}

/** 文档模式第一步：转写 PDF 后在编辑器中预览/修改，不调用 AI */
async function handleConfirmFromDocument() {
  if (!selectedDocumentId.value) {
    error.value = '请选择一份文档'
    return
  }

  loading.value = true
  error.value = null

  try {
    const docId = selectedDocumentId.value
    let source: ResourceResponse
    if (pinnedDocumentDetail.value?.id === docId) {
      source = pinnedDocumentDetail.value
    } else {
      source = await queryResource(docId)
      pinnedDocumentDetail.value = source
    }

    const transcript = await resolveReadonlyResourceMarkdown(docId)
    if (!transcript) {
      error.value = '无法读取参考文档内容，请重新上传或更换文档后重试'
      return
    }

    let targetCourseId = boundCourseId.value
    if (!targetCourseId && isCourseCreateFlow.value) {
      if (!formData.value.courseName.trim()) {
        formData.value.courseName = (source.name || '新课程').trim()
      }
      targetCourseId = await createCourseFromForm()
    }

    const resourceName = ((source.name || '参考文档').trim() + ' 教学大纲').trim()
    const outlineResourceId = await operateResource({
      operation: OperationEnum.CREATE,
      name: resourceName,
      resource_type: ResourceTypeEnum.Outline,
      editable: true,
      ...(targetCourseId ? { related_course_id: targetCourseId } : {}),
    })
    if (!outlineResourceId) {
      throw new Error('创建资源失败，未返回资源 id')
    }

    await operateResource({
      operation: OperationEnum.UPDATE,
      id: outlineResourceId,
      content: transcript,
      resource_type: ResourceTypeEnum.Outline,
    })

    if (targetCourseId) {
      await syncBoundCourseFromForm(targetCourseId)
      saveCourseOutlinePrefill(
        targetCourseId,
        buildPrefillSnapshot(formData.value, chapterTree.value, courseLabels.value)
      )
    }

    const docKey = `outline_doc_${outlineResourceId}`
    const prompt = `请根据参考文档「${source.name}」的内容，生成一份结构完整、可直接使用的教学大纲（Markdown 格式）。`
    try {
      sessionStorage.setItem(
        docKey,
        JSON.stringify({
          sourceResourceId: docId,
          sourceContent: transcript,
          prompt,
          docName: source.name,
        }),
      )
    } catch (e) {
      console.warn('sessionStorage.setItem failed', e)
      error.value = '无法保存文档数据，请重试'
      return
    }

    const query: Record<string, string> = {
      id: outlineResourceId,
      resourceType: ResourceTypeEnum.Outline,
      fromDoc: '1',
      docStep: 'preview',
    }
    if (targetCourseId) query.from_course = targetCourseId
    router.push({ path: '/resource/generate', query })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '处理文档失败'
    console.error('文档转写预览失败:', err)
  } finally {
    loading.value = false
  }
}

async function handleFullCourseCreateWithOutline() {
  await submitOutlineForm({ createCourseIfNeeded: isCourseCreateFlow.value })
}

const handleConfirm = async () => {
  if (creationMode.value === 'document') {
    await handleConfirmFromDocument()
    return
  }

  await submitOutlineForm({ createCourseIfNeeded: false })
}

async function submitOutlineForm(options: { createCourseIfNeeded: boolean }) {
  const err = validateRequired()
  if (err) {
    error.value = err
    return
  }

  loading.value = true
  error.value = null

  try {
    let targetCourseId = boundCourseId.value
    if (!targetCourseId && options.createCourseIfNeeded) {
      targetCourseId = await createCourseFromForm()
    }

    const outlineForm: OutlineForm = {
      course_name: formData.value.courseName || '',
      course_nature: courseNatureFromCategory.value || '',
      course_category: formData.value.courseCategory || '',
      course_introduction: formData.value.courseDescription || '',
      credits: Math.max(0, Math.round(formData.value.credits ? parseFloat(formData.value.credits) : 0)),
      hours: Math.max(0, Math.round(formData.value.hours ? parseFloat(formData.value.hours) : 0)),
      target_major: formData.value.major || '',
      target_grade: formData.value.grade || '',
      teaching_method: inferredTeachingMethod.value || formData.value.teachingMethod || '',
      offline_hours_ratio: formData.value.offlineHoursRatio !== '' ? parseInt(String(formData.value.offlineHoursRatio), 10) || 0 : 0,
      offline_score_ratio: formData.value.offlineScoreRatio !== '' ? parseInt(String(formData.value.offlineScoreRatio), 10) || 0 : 0,
      prerequisites: formData.value.prerequisites || '',
      teaching_objectives: formData.value.teachingObjectives || '',
      ideological_political: formData.value.ideologicalPolitical || '',
      chapter_structure: chapterTree.value,
    }

    // 1. 创建资源（课程随 create 提交，保证大纲版本号在课程作用域内计算），后端返回资源 id
    const resourceName = (formData.value.courseName || '教学大纲').trim() + ' 教学大纲'
    const resourceId = await operateResource({
      operation: OperationEnum.CREATE,
      name: resourceName,
      resource_type: ResourceTypeEnum.Outline,
      editable: true,
      related_user_id: userStore.currentUser?.id ?? undefined,
      related_course_id: targetCourseId || null,
    })
    if (!resourceId) {
      throw new Error('创建资源失败，未返回资源 id')
    }
    if (targetCourseId) {
      await syncBoundCourseFromForm(targetCourseId)
      saveCourseOutlinePrefill(
        targetCourseId,
        buildPrefillSnapshot(formData.value, chapterTree.value, courseLabels.value)
      )
    }

    // 2. 将 outline_form 存入 sessionStorage，跳转生成页由生成页流式拉取并展示
    const storageKey = `outline_form_${resourceId}`
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(outlineForm))
    } catch (e) {
      console.warn('sessionStorage.setItem failed', e)
      error.value = '无法保存表单数据，请重试'
      return
    }
    const query: Record<string, string> = {
      id: resourceId,
      resourceType: ResourceTypeEnum.Outline,
      stream: 'outline',
    }
    if (targetCourseId) query.from_course = targetCourseId
    router.push({ path: '/resource/generate', query })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '生成资源失败'
    console.error('生成资源失败:', err)
  } finally {
    loading.value = false
  }
}

// 点击外部关闭下拉框
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.dropdown-wrapper')) activeDropdown.value = null
  if (!target.closest('.chapter-menu-wrapper')) activeChapterMenuId.value = null
}

// 监听点击事件
if (typeof window !== 'undefined') {
  window.addEventListener('click', handleClickOutside)
}
</script>

<style scoped>
.outline-form-panel {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.form-container {
  background-color: rgba(255, 255, 255, 0.8);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  height: calc(100vh - 64px - 48px);
  overflow: hidden;
  position: relative;
}

.upload-drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  border: 2px dashed rgba(61, 81, 227, 0.55);
  border-radius: 12px;
  box-sizing: border-box;
  pointer-events: none;
}

.upload-drop-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px;
  text-align: center;
}

.upload-drop-icon {
  color: #3d51e3;
  flex-shrink: 0;
}

.upload-drop-text {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
  line-height: 1.4;
}

.upload-drop-fade-enter-active,
.upload-drop-fade-leave-active {
  transition: opacity 0.18s ease;
}

.upload-drop-fade-enter-from,
.upload-drop-fade-leave-to {
  opacity: 0;
}

/* 顶部固定区域 */
.form-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid #e0e0e0;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.creation-mode-switch {
  display: inline-flex;
  margin-left: auto;
  padding: 3px;
  background: #f0f0f0;
  border-radius: 10px;
  gap: 2px;
}

.creation-mode-option {
  border: none;
  background: transparent;
  color: #666;
  font-size: 13px;
  line-height: 1.2;
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s;
  white-space: nowrap;
}

.creation-mode-option.active {
  background: #fff;
  color: #111;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.course-create-hint {
  margin: 0 0 16px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: #555;
  background: #f5f8ff;
  border: 1px solid #d8e4ff;
  border-radius: 10px;
}

.form-row--labels {
  margin-bottom: 8px;
}

.course-labels-input {
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

.course-labels-input:focus-within {
  border-color: #c5d9ff;
}

.course-label-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  max-width: 100%;
  padding: 4px 10px;
  background: rgba(197, 217, 255, 0.5);
  border-radius: 12px;
  font-size: 13px;
  color: #333;
  word-break: break-word;
}

.course-label-remove {
  border: none;
  background: transparent;
  color: #666;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
  flex-shrink: 0;
}

.course-label-remove:hover {
  color: #d32f2f;
}

.course-label-text-wrap {
  flex: 1 1 120px;
  min-width: 120px;
  display: flex;
  align-items: center;
}

.course-label-text {
  width: 100%;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  padding: 4px 0;
  font-size: 14px;
  line-height: 1.4;
  color: #333;
}

.course-label-text::placeholder {
  color: #999;
}

.document-mode-body {
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
  text-align: center;
}

.document-mode-hint {
  margin: 0 auto 24px;
  max-width: 560px;
  font-size: 14px;
  line-height: 1.7;
  color: #666;
  text-align: center;
}

.local-upload-input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.document-upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  max-width: 480px;
  margin: 0 auto 28px;
  padding: 32px 24px;
  border: 2px dashed #c8d4f0;
  border-radius: 12px;
  background: #fafbff;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  font: inherit;
  color: inherit;
}

.document-upload-zone:hover:not(:disabled) {
  border-color: #3d51e3;
  background: #f0f4ff;
}

.document-upload-zone:disabled {
  cursor: not-allowed;
  opacity: 0.85;
}

.document-upload-zone.is-uploading {
  border-color: #a8b8e8;
}

.document-upload-icon {
  color: #3d51e3;
}

.document-upload-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e6f5;
  border-top-color: #3d51e3;
  border-radius: 50%;
  animation: document-upload-spin 0.75s linear infinite;
}

@keyframes document-upload-spin {
  to {
    transform: rotate(360deg);
  }
}

.document-upload-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.document-upload-sub {
  font-size: 13px;
  color: #888;
}

.document-mode-divider {
  margin: 0 0 16px;
  font-size: 13px;
  color: #999;
  text-align: center;
}

.document-selected-banner {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  font-size: 14px;
  line-height: 1.5;
}

.document-mode-status {
  padding: 20px 16px;
  text-align: center;
  color: #888;
  font-size: 14px;
}

.document-resource-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.document-resource-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.document-resource-item:hover {
  border-color: #c5d9ff;
  background: #fafbff;
}

.document-resource-item.selected {
  border-color: #1358e4;
  background: #f0f5ff;
}

.document-resource-name {
  font-size: 15px;
  color: #222;
  font-weight: 500;
}

.document-resource-meta {
  font-size: 12px;
  color: #888;
  flex-shrink: 0;
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

.form-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

/* 可滚动表单内容区域（滚动条见全局 customScrollbar 插件） */
.form-scroll-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.form-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 表单行样式 */
.form-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

/* 与下方三列行共用同一网格，课程标签跨列至「课程类别」右边界 */
.form-row.form-row--labels .form-field--full {
  grid-column: 1 / -1;
  width: 100%;
  min-width: 0;
}

.form-row-single {
  display: flex;
  width: 100%;
}

/* 表单字段样式 */
.form-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-field-full {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.field-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.field-label .required,
.group-label .required {
  color: #d32f2f;
}

.field-input {
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  outline: none;
  transition: border-color 0.2s;
}

.field-input:focus {
  border-color: #C5D9FF;
}

.field-input::placeholder {
  color: #999;
}

.field-input-error {
  border-color: #d32f2f;
}
.field-input-error:focus {
  border-color: #d32f2f;
}

.field-readonly {
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 999px;
  font-size: 14px;
  color: #666;
  background-color: #f5f5f5;
  min-height: 20px;
}

.ratio-hint {
  margin: 4px 0 0;
  font-size: 13px;
  color: #666;
}
.ratio-error {
  margin: 4px 0 0;
  font-size: 13px;
  color: #d32f2f;
}

.field-textarea {
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
}

.field-textarea:focus {
  border-color: #C5D9FF;
}

.field-textarea::placeholder {
  color: #999;
}

/* 课程介绍：卡片 + 关键词组合 */
.course-desc-builder {
  gap: 14px;
}

.course-desc-header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.course-desc-hint {
  font-size: 12px;
  color: #86aaf2;
  letter-spacing: 0.02em;
}

.course-desc-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.course-desc-section-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  letter-spacing: 0.04em;
}

.course-desc-theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 10px;
}

.course-desc-theme-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid rgba(19, 88, 228, 0.12);
  border-radius: 16px;
  background: linear-gradient(145deg, #ffffff 0%, #f7faff 100%);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
}

.course-desc-theme-card:hover {
  border-color: rgba(134, 170, 242, 0.65);
  box-shadow: 0 4px 14px rgba(19, 88, 228, 0.08);
}

.course-desc-theme-card.is-active {
  border-color: #1358e4;
  background: linear-gradient(145deg, #f0f5ff 0%, #e8f0ff 100%);
  box-shadow: 0 6px 18px rgba(19, 88, 228, 0.14);
}

.theme-card-icon {
  font-size: 18px;
  line-height: 1;
}

.theme-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.theme-card-sub {
  font-size: 11px;
  color: #888;
  line-height: 1.35;
}

.course-desc-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.course-desc-chip {
  padding: 6px 14px;
  border: 1px solid #e8ecf4;
  border-radius: 999px;
  background: #fff;
  font-size: 13px;
  color: #555;
  cursor: pointer;
  transition: all 0.18s ease;
}

.course-desc-chip:hover {
  border-color: #c5d9ff;
  color: #1358e4;
}

.course-desc-chip.is-active {
  border-color: #86aaf2;
  background: linear-gradient(135deg, #86aaf2 0%, #1358e4 100%);
  color: #fff;
  box-shadow: 0 2px 10px rgba(19, 88, 228, 0.22);
}

.course-desc-preview {
  padding: 14px 16px;
  border-radius: 20px;
  border: 1px solid rgba(197, 217, 255, 0.9);
  background: linear-gradient(135deg, rgba(240, 245, 255, 0.95) 0%, rgba(255, 255, 255, 0.98) 55%, rgba(232, 240, 255, 0.6) 100%);
  position: relative;
  overflow: hidden;
}

.course-desc-preview::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 100% 0%, rgba(134, 170, 242, 0.15), transparent 45%);
  pointer-events: none;
}

.course-desc-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  position: relative;
  z-index: 1;
}

.course-desc-preview-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #1358e4;
  background: rgba(19, 88, 228, 0.08);
  letter-spacing: 0.06em;
}

.course-desc-rebuild-btn {
  padding: 4px 12px;
  border: none;
  border-radius: 999px;
  font-size: 12px;
  color: #1358e4;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  transition: background 0.2s;
}

.course-desc-rebuild-btn:hover {
  background: #fff;
}

.course-desc-preview-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: #333;
  position: relative;
  z-index: 1;
}

.course-desc-custom {
  font-size: 13px;
  color: #666;
}

.course-desc-custom summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
}

.course-desc-custom summary::-webkit-details-marker {
  display: none;
}

.course-desc-custom summary::before {
  content: '＋ ';
  color: #86aaf2;
  font-weight: 600;
}

.course-desc-custom[open] summary::before {
  content: '－ ';
}

.course-desc-custom-input {
  margin-top: 8px;
  width: 100%;
  box-sizing: border-box;
  min-height: 42px;
  line-height: 1.5;
  resize: none;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-family: inherit;
}

/* 下拉框样式 */
.dropdown-wrapper {
  position: relative;
}

.dropdown-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 999px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s;
  text-align: left;
}

.dropdown-btn:hover {
  border-color: #C5D9FF;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
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

.dropdown-item.disabled {
  color: #999;
  cursor: default;
  pointer-events: none;
}

/* 组合输入区域 */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  flex: 1;
}

.group-label {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.group-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 章节结构 */
.chapter-structure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chapter-structure-title {
  margin: 0;
}

.chapter-add-root-btn {
  padding: 8px 14px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 999px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}

.chapter-add-root-btn:hover {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.chapter-structure-frame {
  margin-top: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.55);
}

.chapter-empty {
  font-size: 14px;
  color: #666;
  padding: 10px 2px;
}

.chapter-tree {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chapter-card {
  background: #ffffff;
  border: 1px solid #eaeaea;
  border-radius: 12px;
  padding: 12px;
}

.chapter-card-top {
  display: grid;
  grid-template-columns: 28px auto 1fr 36px;
  gap: 10px;
  align-items: center;
}

.chapter-collapse-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: #333;
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s;
}

.chapter-collapse-btn:hover {
  background: #f5f7ff;
}

.chapter-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  user-select: none;
  white-space: nowrap;
}

.pill-blue {
  color: #1358E4;
  background: rgba(19, 88, 228, 0.12);
  border: 1px solid rgba(19, 88, 228, 0.25);
}

.pill-green {
  color: #1B8A5A;
  background: rgba(27, 138, 90, 0.12);
  border: 1px solid rgba(27, 138, 90, 0.25);
}

.chapter-title-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 999px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.chapter-title-input:focus {
  border-color: #C5D9FF;
}

.chapter-title-input::placeholder {
  color: #999;
}

.chapter-menu-wrapper {
  position: relative;
  display: flex;
  justify-content: flex-end;
}

.chapter-menu-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #e0e0e0;
  background: #ffffff;
  border-radius: 10px;
  cursor: pointer;
  color: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.chapter-menu-btn:hover {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.chapter-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 170px;
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow: hidden;
  z-index: 1000;
}

.chapter-menu-item {
  padding: 12px 14px;
  font-size: 14px;
  color: #111;
  cursor: pointer;
  transition: background-color 0.2s;
}

.chapter-menu-item:hover {
  background: #f5f5f5;
}

.chapter-menu-item.danger {
  color: #d32f2f;
}

.chapter-desc-input {
  margin-top: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e6e6e6;
  border-radius: 12px;
  font-size: 14px;
  color: #333;
  outline: none;
  resize: vertical;
  font-family: inherit;
  background: #f7f8fb;
  transition: border-color 0.2s;
}

.chapter-desc-input:focus {
  border-color: #C5D9FF;
}

.chapter-desc-input::placeholder {
  color: #8b8f98;
}

.chapter-children {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 底部固定区域 */
.form-footer {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.form-footer-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
}

.error-message {
  color: #d32f2f;
  font-size: 14px;
  text-align: right;
}

.confirm-btn {
  padding: 10px 32px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}

.confirm-btn:hover:not(:disabled) {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}

.confirm-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.confirm-btn--primary {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
  color: #1a56db;
}

.confirm-btn--primary:hover:not(:disabled) {
  border-color: #a8c5ff;
  background-color: #eef3ff;
}

/* 响应式设计 */
@media (max-width: 968px) {
  .form-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .form-group {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .outline-form-panel {
    padding: 12px;
  }
  .form-container {
    height: calc(100vh - 56px - 24px);
    border-radius: 10px;
  }
  .form-header {
    padding: 14px 16px;
  }
  .form-scroll-area {
    padding: 16px;
  }
  .form-row {
    grid-template-columns: 1fr;
    gap: 14px;
  }
  .form-title {
    font-size: 18px;
  }
}

@media (max-width: 480px) {
  .form-container {
    height: calc(100vh - 56px - 16px);
  }
}
</style>
