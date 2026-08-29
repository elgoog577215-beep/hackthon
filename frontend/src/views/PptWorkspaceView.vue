<template>
  <section
    ref="workspaceRoot"
    class="ppt-workspace-view"
    :class="{ 'is-ai-open': aiVisible }"
    :style="{ '--ppt-ai-width': `${pptAiPaneWidth}px` }"
  >
    <div v-if="initializing || (!slideRepresentation && store.building && !store.liveSlides.length)" class="ppt-workspace-state">
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <h1>{{ courseTitle }}</h1>
      <p v-if="!store.building">{{ t('pptWorkspace.loading', '正在读取同源课件与页面结构') }}</p>
      <SlideDeckBuildProgress
        v-if="store.building"
        :progress="store.buildProgress"
        :stage="store.buildStage"
        :step-index="store.buildDisplayStep"
        :detail="store.buildDetail"
        :progress-v2="store.slideBuildProgressV2"
        :estimated-slide-count="store.buildEstimatedSlideCount"
        variant="initial"
      />
      <b v-else>···</b>
      <div v-if="store.buildTaskId" class="ppt-workspace-state__task-actions">
        <button v-if="store.building" type="button" @click="pauseBuild">暂停</button>
        <button type="button" @click="cancelBuild">取消</button>
      </div>
    </div>

    <div v-else-if="documentLoadError" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <h1>{{ courseTitle }}</h1>
      <p>{{ documentLoadError }}</p>
    </div>

    <PptManuscriptWorkflow
      v-else-if="showManuscriptWorkflow && pptManuscriptState"
      :title="courseTitle"
      :state="pptManuscriptState"
      :busy="store.building"
      :confirming="pptManuscriptConfirming"
      :error="pptManuscriptConfirmError || buildErrorLabel"
      :failure="effectiveBuildFailure"
      @back="closeManuscriptWorkflow"
      @generate-manuscript="openGenerator(false)"
      @regenerate-manuscript="openGenerator(true)"
      @confirm-manuscript="confirmPptManuscript"
      @generate-ppt="generatePptFromConfirmedManuscript"
    />

    <div v-else-if="documentEnvelope?.source_format !== 'legacy_projection' && !slideRepresentation && !store.liveSlides.length" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <h1>{{ courseTitle }}</h1>
      <small
        class="ppt-workspace-state__engine"
        data-testid="ppt-engine-status"
        :data-engine-status="slideEngineStatus"
      >{{ slideEngineStatusLabel }}</small>
      <p v-if="buildErrorLabel">{{ buildErrorLabel }}</p>
      <p v-if="logicUpgradeError" class="ppt-workspace-state__logic-error">{{ logicUpgradeError }}</p>
      <button
        v-if="slideEngineStatus === 'blocked'"
        type="button"
        class="ppt-workspace-state__upgrade-logic"
        :disabled="logicUpgrading"
        @click="upgradeCourseLogic"
      >
        <Sparkles :size="17" />{{ logicUpgrading ? '正在补全课程逻辑…' : '补全课程逻辑' }}
      </button>
      <button v-else type="button" class="ppt-workspace-state__build" :disabled="store.building" @click="startOrResumeBuild">
        <Sparkles :size="17" />{{ store.buildPaused ? '从保存点继续' : t('pptWorkspace.build', '选择模式与风格') }}
      </button>
    </div>

    <div v-else-if="documentEnvelope?.source_format === 'legacy_projection'" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <h1>{{ t('pptWorkspace.legacyMigrationTitle', '旧课程需要先升级') }}</h1>
      <p>{{ t('pptWorkspace.legacyMigrationDescription', '升级后会使用统一课程源生成 PPT，不会直接基于旧投影视图构建。') }}</p>
      <p v-if="migrationMessage">{{ migrationMessage }}</p>
      <button type="button" class="ppt-workspace-state__build ppt-workspace-state__migrate" :disabled="migrating" @click="migrateCourse">
        <Sparkles :size="17" />{{ migrating ? t('pptWorkspace.migrating', '正在升级课程…') : t('pptWorkspace.migrateAndBuild', '升级课程后生成PPT') }}
      </button>
    </div>

    <template v-else>
      <SlideDeckWorkbench
        class="ppt-workspace-view__deck"
        standalone
        :course-id="courseId"
        :representation-id="slideRepresentation?.representation_id || ''"
        :deck-title="content?.title || courseTitle"
        :slides="displaySlides"
        :stale-unit-ids="slideRepresentation?.stale_unit_ids || []"
        :building="store.building"
        :progress="store.buildProgress"
        :stage="store.buildStage"
        :build-step-index="store.buildDisplayStep"
        :build-detail="store.buildDetail"
        :build-progress-v2="store.slideBuildProgressV2"
        :estimated-slide-count="store.buildEstimatedSlideCount"
        :error="store.buildError"
        :build-failure="effectiveBuildFailure"
        :build-resumable="store.buildPaused"
        :logic-upgrading="logicUpgrading"
        :logic-upgrade-error="logicUpgradeError"
        :quality="displayQuality"
        :preview-source="store.slidePreviewSource"
        :mode="selectedMode"
        :theme="selectedTheme"
        :theme-overrides="content?.template_theme_overrides || {}"
        :template-pack="activeTemplatePack"
        :variants="slideVariants"
        :bundle-parts="activeBundleParts"
        :active-bundle-part-id="slideRepresentation?.representation_id || ''"
        :engine-status="slideEngineStatus"
        :target-schema="store.slideTargetSchema || String(store.registry?.slide_deck_target_schema || '')"
        :candidate-schema="store.slideCandidateSchema || String(content?.schema_version || '')"
        :published-schema="store.slidePublishedSchema || String(content?.schema_version || '')"
        :candidate-status="store.slideCandidateStatus || String(content?.candidate_status || '')"
        :planning-status="content?.planning_status || null"
        :ppt-manuscript="content?.ppt_manuscript || null"
        :storyboard="content?.storyboard || null"
        :manuscript-status="pptManuscriptState?.status || ''"
        :manuscript-confirming="pptManuscriptConfirming"
        :manuscript-confirmation-required="isTeacherSurface && Boolean(content?.ppt_manuscript)"
        :manuscript-confirm-error="pptManuscriptConfirmError"
        @back="backToCourse"
        @rebuild="rebuild"
        @configure="openGenerator(false)"
        @upgrade-course-logic="upgradeCourseLogic"
        @variant-change="selectVariant"
        @bundle-part-change="selectBundlePart"
        @open-materials="openMaterials"
        @ask-ai="openAiForSlide"
        @open-course="openSameSourceCourse"
        @confirm-manuscript="confirmPptManuscript"
        @review-manuscript="openManuscriptWorkflow"
      />

      <TeachingRepresentationsOverlay
        :visible="materialsVisible"
        :course-id="courseId"
        active-type="outline"
        overview-mode
        @close="closeMaterials"
        @course="backToCourse"
        @ppt="closeMaterials"
      />

      <div
        v-if="aiVisible && isTeacherSurface"
        class="ppt-workspace-view__ai-resizer"
        :class="{ 'is-resizing': pptAiResizing }"
        role="separator"
        tabindex="0"
        aria-orientation="vertical"
        :aria-label="t('pptWorkspace.resizeAi', '调整 AI 助手宽度')"
        :aria-valuemin="PPT_AI_MIN_WIDTH"
        :aria-valuemax="pptAiMaxWidth"
        :aria-valuenow="pptAiPaneWidth"
        @pointerdown="startPptAiResize"
        @keydown="resizePptAiWithKeyboard"
      ><GripVertical :size="14" /></div>

      <Transition name="ppt-ai">
        <TeacherLessonAiWorkspace
          v-if="aiVisible && isTeacherSurface"
          class="ppt-workspace-view__ai"
          domain="ppt"
          :scope-title="pptAiScopeTitle"
          :scope-detail="pptAiScopeDetail"
          :reference-count="pptAiReferences.length"
          :reference-labels="pptAiReferenceLabels"
          :messages="pptAiMessages"
          :phase="pptAiPhase"
          :busy="pptAiBusy"
          :candidate-pending="Boolean(pptAiCandidate)"
          :candidate-fields="pptAiCandidateFields"
          :candidate-impacts="pptAiCandidate ? [t('pptWorkspace.aiCurrentPageOnly', '仅当前页'), t('pptWorkspace.aiSourceSafe', '课程源不变')] : []"
          :quick-actions="pptAiQuickActions"
          :placeholder="t('pptWorkspace.aiPlaceholder', '描述这一页想怎么改…')"
          :can-retry="Boolean(pptAiLastInstruction)"
          @close="closePptAi"
          @open-sources="openMaterials"
          @send="requestPptAiCandidate"
          @clarify="requestPptAiCandidate"
          @retry="retryPptAiCandidate"
          @accept="resolvePptAiCandidate(true)"
          @reject="resolvePptAiCandidate(false)"
          @focus-candidate="focusPptAiCandidate"
          @open-course-plan="openPptCoursePlan"
        />
      </Transition>

      <Transition name="ppt-ai">
        <SideAIPanel
          v-if="aiVisible && !isTeacherSurface"
          class="ppt-workspace-view__ai"
          :visible="aiVisible"
          :quote-text="aiQuote"
          :quote-node-id="aiNodeId"
          :quote-anchor="aiAnchor"
          :prefill="aiPrefill"
          entrypoint="global"
          mode="teacher"
          identity-scope="teacher"
          @close="aiVisible = false"
        />
      </Transition>
    </template>

    <SlideDeckGeneratorDialog
      :open="generatorOpen"
      :mode="selectedMode"
      :theme="selectedTheme"
      :web-image-retrieval="selectedWebImageRetrieval"
      :busy="store.building"
      :closable="Boolean(slideRepresentation || pptManuscriptState)"
      :manuscript-first="isTeacherSurface"
      :fragment-count="estimatedFragmentCount"
      :duration-minutes="lessonDurationMinutes"
      :personal-templates="templatePacksStore.personal"
      :personal-templates-enabled="templateStore.personalTemplatesEnabled"
      @close="closeGenerator"
      @confirm="generateVariant"
      @create-template="openTemplateCreator"
    />
    <PptTemplateCreatorDialog
      :open="templateCreatorOpen"
      @close="closeTemplateCreator"
      @published="handleTemplatePublished"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, GripVertical, Presentation, Sparkles } from 'lucide-vue-next'
import SideAIPanel from '../components/SideAIPanel.vue'
import TeacherLessonAiWorkspace, { type TeacherAiQuickAction } from '../components/TeacherLessonAiWorkspace.vue'
import SlideDeckBuildProgress from '../components/SlideDeckBuildProgress.vue'
import SlideDeckWorkbench from '../components/SlideDeckWorkbench.vue'
import SlideDeckGeneratorDialog from '../components/SlideDeckGeneratorDialog.vue'
import PptManuscriptWorkflow from '../components/PptManuscriptWorkflow.vue'
import PptTemplateCreatorDialog from '../components/PptTemplateCreatorDialog.vue'
import TeachingRepresentationsOverlay from '../components/TeachingRepresentationsOverlay.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useCourseEvolutionStore } from '../stores/courseEvolution'
import { usePptTemplatePacksStore, type PersonalPptTemplatePack } from '../stores/pptTemplatePacks'
import {
  normalizedBuildFailure,
  useTeachingRepresentationsStore,
} from '../stores/teachingRepresentations'
import type {
  SlideDeckMode,
  SlideDeckTheme,
  TeachingRepresentation,
  TeachingRepresentationBuildFailure,
} from '../stores/teachingRepresentations'
import type { CourseDocumentEnvelope } from '../stores/types'
import type { PptSameSourceHighlightState } from '../utils/ppt-same-source'
import { adaptSlideDeckV6ForWeb } from '../utils/slide-deck-v6-adapter'
import {
  buildTeacherCourseChangeInstruction,
  buildTeacherProductionAiInstruction,
  projectTeacherCoursePlan,
  routeTeacherProductionRequest,
  teacherProductionAiBusy,
  transitionTeacherProductionAiPhase,
  type TeacherProductionAiMessage,
  type TeacherProductionAiPhase,
  type TeacherProductionAiScope,
  type TeacherCoursePlanProjection,
} from '../composables/useTeacherProductionAiCollaboration'
import http, { teacherIdentityHeaders } from '../utils/http'
import { postGenerationStream } from '../shared/generation-stream'
import { createUuid } from '../utils/client-id'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const courseEvolutionStore = useCourseEvolutionStore()
const templatePacksStore = usePptTemplatePacksStore()
const store = useTeachingRepresentationsStore()
const templateStore = templatePacksStore
const workspaceRoot = ref<HTMLElement | null>(null)
const initializing = ref(true)
const aiVisible = ref(false)
const materialsVisible = ref(false)
const aiQuote = ref('')
const aiNodeId = ref('')
const aiAnchor = ref<Record<string, unknown> | undefined>(undefined)
const aiPrefill = ref('')
const documentEnvelope = ref<CourseDocumentEnvelope | null>(null)
const migrating = ref(false)
const migrationMessage = ref('')
const logicUpgrading = ref(false)
const logicUpgradeError = ref('')
const documentLoadError = ref('')
const generatorOpen = ref(false)
const templateCreatorOpen = ref(false)
const forceGeneratorBuild = ref(false)
const selectedMode = ref<SlideDeckMode>('teaching')
const selectedTheme = ref<V3Theme>('academic-editorial')
const selectedWebImageRetrieval = ref(false)
const selectedTemplatePackId = ref('')
const selectedTemplatePackVersion = ref<number | undefined>(undefined)
let workspaceAttempt = 0

interface TeacherV6AiCandidate {
  candidate_id: string
  representation_id: string
  page_id: string
  base_spec_id: string
  base_spec_revision: string
  candidate_page: Record<string, any>
  changed_fields: string[]
  status: string
}

const PPT_AI_WIDTH_KEY = 'teacher-ppt-workspace:ai-pane-width'
const PPT_AI_MIN_WIDTH = 360
const PPT_AI_MAX_WIDTH = 680
const PPT_CANVAS_MIN_WIDTH = 620
const pptAiPaneWidth = ref(460)
const pptAiResizing = ref(false)
const pptAiCandidate = ref<TeacherV6AiCandidate | null>(null)
const pptAiPageId = ref('')
const pptAiMessages = ref<TeacherProductionAiMessage[]>([])
const pptAiPhase = ref<TeacherProductionAiPhase>('ready')
const pptAiLastInstruction = ref('')
const pptAiCoursePlanRequestId = ref('')
const pptManuscriptState = ref<{
  generation_branch: 'manuscript_first' | 'original_ppt_review'
  revision: string
  status: 'not_generated' | 'draft' | 'confirmed'
  source_state: string
  confirmable: boolean
  can_generate_ppt: boolean
  task_id?: string
  mode?: SlideDeckMode
  theme?: V3Theme
  template_id?: string
  template_version?: string
  template_digest?: string
  template_pack_id?: string
  generated_representation_id?: string
  manuscript?: Record<string, any> | null
} | null>(null)
const pptManuscriptConfirming = ref(false)
const pptManuscriptConfirmError = ref('')
const manuscriptWorkflowForced = ref(false)
let pptAiCandidateAttempt = 0
let pptAiMessageSequence = 0

type V3Theme = Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>

const courseId = computed(() => String(route.params.courseId || ''))
const teacherLessonId = computed(() => String(route.query?.lesson || route.query?.node || ''))
const isTeacherSurface = computed(() => (
  Boolean(teacherLessonId.value)
  || route.meta?.courseSurface === 'teacher'
))
const courseTitle = computed(() => (
  store.selectedSpec?.payload?.content?.title
  || courseStore.currentCourse?.course_name
  || documentEnvelope.value?.document?.title
  || documentEnvelope.value?.course_name
  || t('pptWorkspace.untitledCourse', '课程演示')
))
const targetSlideRepresentations = computed(() => (
  store.representations.filter(item => (
    item.representation_type === 'slide_deck'
    && representationMatchesTargetEngine(item)
  ))
))
const slideVariants = computed(() => (
  targetSlideRepresentations.value.filter(item => item.variant_key)
))
const activeVariantKey = computed(() => (
  selectedTemplatePackId.value && selectedTemplatePackVersion.value
    ? `${selectedMode.value}:${selectedTheme.value}:template:${selectedTemplatePackId.value}@${selectedTemplatePackVersion.value}`
    : `${selectedMode.value}:${selectedTheme.value}`
))
const activeBundleRepresentations = computed(() => (
  slideVariants.value.filter(item => (
    baseVariantKey(item.variant_key) === activeVariantKey.value
    && String(item.variant_key || '').includes(':part:')
  ))
))
const activeBundleParts = computed(() => (
  activeBundleRepresentations.value
    .map(item => ({
      representationId: item.representation_id,
      label: `第 ${bundlePartIndex(item.variant_key)} 册`,
    }))
    .sort((left, right) => (
      Number(left.label.match(/\d+/)?.[0] || 0)
      - Number(right.label.match(/\d+/)?.[0] || 0)
    ))
))
const slideRepresentation = computed(() => (
  targetSlideRepresentations.value.find(
    item => item.representation_id === store.selectedId,
  )
  || slideVariants.value.find(item => item.variant_key === activeVariantKey.value)
  || targetSlideRepresentations.value[0]
  || null
))
const showManuscriptWorkflow = computed(() => {
  if (!isTeacherSurface.value || !pptManuscriptState.value) return false
  if (manuscriptWorkflowForced.value) return true
  if (pptManuscriptState.value.generation_branch === 'original_ppt_review') return true
  if (!slideRepresentation.value) return true
  if (pptManuscriptState.value.status === 'not_generated') return false
  return (
    !pptManuscriptState.value.generated_representation_id
    || pptManuscriptState.value.generated_representation_id
      !== slideRepresentation.value.representation_id
  )
})

function openManuscriptWorkflow() {
  manuscriptWorkflowForced.value = true
}

function closeManuscriptWorkflow() {
  if (manuscriptWorkflowForced.value && slideRepresentation.value) {
    manuscriptWorkflowForced.value = false
    return
  }
  backToCourse()
}
const content = computed(() => store.selectedSpec?.payload?.content || null)
const pptAiPage = computed<Record<string, any> | null>(() => {
  const pages = Array.isArray(content.value?.pages) ? content.value.pages : []
  return pages.find((page: Record<string, any>) => String(page.page_id || '') === pptAiPageId.value)
    || pages[0]
    || null
})
const pptAiScopeTitle = computed(() => (
  pptAiPage.value?.title
  || t('pptWorkspace.aiCurrentPage', '当前页面')
))
const pptAiScopeDetail = computed(() => {
  const ordinal = Number(pptAiPage.value?.page_ordinal ?? 0) + 1
  return t('pptWorkspace.aiPageNumber', '第 {number} 页').replace('{number}', String(ordinal))
})
const pptAiReferences = computed<Array<{
  id: string
  label: string
  role: 'primary' | 'reference'
}>>(() => (
  (pptAiPage.value?.source_block_ids || []).map((id: string, index: number) => ({
    id: String(id),
    label: `${t('pptWorkspace.aiSource', '课程源')} ${index + 1}`,
    role: index === 0 ? 'primary' as const : 'reference' as const,
  }))
))
const pptAiReferenceLabels = computed(() => pptAiReferences.value.map(item => item.label))
const pptAiBusy = computed(() => teacherProductionAiBusy(pptAiPhase.value))
const pptAiCandidateFields = computed(() => {
  const labels: Record<string, string> = {
    title: t('pptWorkspace.aiFieldTitle', '标题'),
    subtitle: t('pptWorkspace.aiFieldSubtitle', '副标题'),
    key_message: t('pptWorkspace.aiFieldKeyMessage', '关键内容'),
  }
  return (pptAiCandidate.value?.changed_fields || []).map(field => labels[field] || field)
})
const pptAiQuickActions = computed<TeacherAiQuickAction[]>(() => [
  { id: 'title', label: t('pptWorkspace.aiQuickTitle', '聚焦标题'), prompt: '压缩当前页标题，让课堂上一眼能抓住重点。', icon: 'target' },
  { id: 'message', label: t('pptWorkspace.aiQuickMessage', '强化重点'), prompt: '强化当前页的关键内容，保持原意不变。', icon: 'focus' },
  { id: 'compress', label: t('pptWorkspace.aiQuickCompress', '精简表达'), prompt: '精简当前页表达，保留完整的教学信息。', icon: 'compress' },
  { id: 'classroom', label: t('pptWorkspace.aiQuickClassroom', '课堂化'), prompt: '把当前页改成更适合教师现场讲解的表达。', icon: 'voice' },
  { id: 'transition', label: t('pptWorkspace.aiQuickTransition', '补足衔接'), prompt: '补足当前页与本讲内容的衔接，不新增知识事实。', icon: 'transition' },
  { id: 'objective', label: t('pptWorkspace.aiQuickObjective', '对齐目标'), prompt: '让当前页表达更直接服务本讲教学目标。', icon: 'check' },
])
const activeTemplateAssetUrls = ref<Record<string, string>>({})
const activeTemplatePackSnapshot = computed(() => {
  const contentPack = content.value?.template_pack
  const selectedPack = templateStore.personal.find(item => (
    item.pack_id === selectedTemplatePackId.value
    && (item.version || item.latest_version) === selectedTemplatePackVersion.value
  ))
  if (selectedTemplatePackId.value) {
    const contentMatches = contentPack?.pack_id === selectedTemplatePackId.value
      && Number(contentPack?.version || 0) === Number(selectedTemplatePackVersion.value || 0)
    return contentMatches ? contentPack : selectedPack || null
  }
  return contentPack || null
})
const activeTemplatePack = computed(() => (
  activeTemplatePackSnapshot.value
    ? {
        ...activeTemplatePackSnapshot.value,
        asset_urls: activeTemplateAssetUrls.value,
      }
    : null
))
let templateAssetAttempt = 0

watch(activeTemplatePackSnapshot, async snapshot => {
  const attempt = ++templateAssetAttempt
  activeTemplateAssetUrls.value = {}
  if (!snapshot?.pack_id || !Array.isArray(snapshot.assets)) return
  const version = Number(snapshot.version || snapshot.latest_version || 0) || undefined
  const imageAssets = snapshot.assets.filter((asset: any) => (
    String(asset.mime_type || '').startsWith('image/')
    && ['logo', 'style_reference'].includes(String(asset.role || ''))
  ))
  const settled = await Promise.allSettled(imageAssets.map(async (asset: any) => ({
    role: String(asset.role),
    url: await templateStore.assetUrl(
      String(snapshot.pack_id),
      String(asset.asset_id),
      version,
    ),
  })))
  if (attempt !== templateAssetAttempt) return
  const urls: Record<string, string> = {}
  let referenceIndex = 0
  for (const result of settled) {
    if (result.status !== 'fulfilled') continue
    const key = result.value.role === 'logo'
      ? 'logo'
      : `style_reference_${++referenceIndex}`
    urls[key] = result.value.url
  }
  activeTemplateAssetUrls.value = urls
})
const slideEngineStatus = computed<
  'slide_deck_v6' | 'slide_deck_v5' | 'slide_deck_v4' | 'slide_deck_v3' | 'blocked' | 'unknown'
>(() => {
  const target = String(store.registry?.slide_deck_target_schema || '')
  if (['slide_deck_v6', 'slide_deck_v5', 'slide_deck_v4', 'slide_deck_v3', 'blocked'].includes(target)) {
    return target as 'slide_deck_v6' | 'slide_deck_v5' | 'slide_deck_v4' | 'slide_deck_v3' | 'blocked'
  }
  const publishedSchema = String(content.value?.schema_version || '')
  if (
    publishedSchema === 'slide_deck_v6'
    || publishedSchema === 'slide_deck_v5'
    || publishedSchema === 'slide_deck_v4'
    || publishedSchema === 'slide_deck_v3'
  ) {
    return publishedSchema
  }
  return 'unknown'
})
const slideEngineStatusLabel = computed(() => ({
  slide_deck_v6: '将使用课程忠实型故事、视觉与最新模板合同 V6 生成',
  slide_deck_v5: '将使用课程叙事与语义版式 V5 生成',
  slide_deck_v4: '将使用新版课程逻辑 V4 生成',
  slide_deck_v3: '当前使用兼容模式 V3',
  blocked: '课程逻辑产物未就绪，暂不能生成 PPT',
  unknown: '正在确认 PPT 生成引擎',
}[slideEngineStatus.value]))

function representationMatchesTargetEngine(item: TeachingRepresentation) {
  const target = String(store.registry?.slide_deck_target_schema || '')
  if (
    target !== 'slide_deck_v6'
    && target !== 'slide_deck_v5'
    && target !== 'slide_deck_v4'
    && target !== 'slide_deck_v3'
  ) return true
  const registrySpec = (store.registry?.specs || []).find(
    (spec: Record<string, any>) => spec.spec_id === item.spec_id,
  )
  const selectedSpec = (
    store.selectedSpec?.spec_id === item.spec_id
      ? store.selectedSpec
      : null
  )
  const schema = String(
    registrySpec?.payload?.content?.schema_version
    || selectedSpec?.payload?.content?.schema_version
    || '',
  )
  return schema === target
}
const displayContent = computed(() => {
  const source = content.value
  const candidate = pptAiCandidate.value
  if (!source || !candidate || source.schema_version !== 'slide_deck_v6') return source
  const preview = JSON.parse(JSON.stringify(source))
  const page = (preview.pages || []).find(
    (item: Record<string, any>) => String(item.page_id || '') === candidate.page_id,
  )
  if (!page) return source
  const candidatePage = candidate.candidate_page || {}
  for (const field of candidate.changed_fields || []) {
    if (field === 'title') {
      page.title = candidatePage.title
      continue
    }
    const regionId = String(candidatePage[`${field}_region_id`] || '')
    const region = (page.regions || []).find(
      (item: Record<string, any>) => String(item.region_id || '') === regionId,
    )
    if (region) region.content = candidatePage[field]
  }
  return preview
})
const displaySlides = computed(() => (
  store.liveSlides.length && store.slidePreviewSource === 'draft'
    ? store.liveSlides
    : displayContent.value?.schema_version === 'slide_deck_v6'
      ? adaptSlideDeckV6ForWeb(displayContent.value)
      : (displayContent.value?.slides || [])
))
const estimatedFragmentCount = computed(() => (
  Number(content.value?.fragment_manifest?.length)
  || (documentEnvelope.value?.document?.blocks || []).length
))
const lessonDurationMinutes = computed(() => {
  const blocks = documentEnvelope.value?.document?.blocks || []
  const total = blocks.reduce((sum: number, block: Record<string, any>) => (
    sum + Math.max(0, Number(block?.metadata?.planned_minutes || 0))
  ), 0)
  return total || 45
})
const displayQuality = computed(() => (
  store.buildError && store.draftSlideQuality
    ? store.draftSlideQuality
    : store.slideQuality
))
const registryCourseLogicFailure = computed<TeachingRepresentationBuildFailure | null>(() => {
  const detail = store.registry?.slide_deck_v4_blocker_details?.[0]
  if (detail) return normalizedBuildFailure(detail)
  const legacy = store.registry?.slide_deck_v4_blockers?.[0]
  if (legacy) return normalizedBuildFailure(legacy)
  if (slideEngineStatus.value === 'blocked') {
    return normalizedBuildFailure({ code: 'course_teaching_plan_not_ready' })
  }
  return null
})
const effectiveBuildFailure = computed(() => (
  store.buildFailure || registryCourseLogicFailure.value
))
const buildErrorLabel = computed(() => (
  effectiveBuildFailure.value?.action === 'upgrade_course_logic'
    ? effectiveBuildFailure.value.message
    : store.buildError === 'deck_split_required'
    ? '课程内容过多，预计超过 300 页。请按章节拆分课程后再生成 PPT。'
    : store.buildError === 'layout_capacity_failed'
      ? '课程内容排版失败，系统未发布不完整课件。请重试；若仍失败，请拆分过长的代码、公式或列表。'
    : store.buildError === 'quality_gate_failed'
      ? t('pptWorkspace.qualityBlocked', '课件未通过课堂可用性检查，系统没有发布问题版本。请调整课程内容后重试。')
      : store.buildError
))
async function loadWorkspace() {
  const id = courseId.value
  if (!id) return
  store.setTeacherLessonScope(teacherLessonId.value)
  if (isTeacherSurface.value && !teacherLessonId.value) {
    documentLoadError.value = '请先从课程生产页选择一讲，再进入 PPT 工作台。'
    initializing.value = false
    return
  }
  const attempt = ++workspaceAttempt
  initializing.value = true
  documentEnvelope.value = null
  pptManuscriptState.value = null
  migrating.value = false
  migrationMessage.value = ''
  logicUpgrading.value = false
  logicUpgradeError.value = ''
  documentLoadError.value = ''
  try {
    const documentPromise = loadDocumentEnvelope(id, attempt)
    const registryPromise = store.ensure(id, {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })
    const manuscriptPromise = isTeacherSurface.value
      ? loadPptManuscriptState(id, attempt)
      : Promise.resolve(null)
    const [envelope] = await Promise.all([
      documentPromise,
      registryPromise,
      manuscriptPromise,
    ])
    if (!envelope || !isCurrentAttempt(id, attempt) || envelope.source_format !== 'canonical') return
    if (store.courseId === id && !store.representations.length) {
      await store.recoverDurableBuild(id)
    }
    if (!isCurrentAttempt(id, attempt)) return
    const preferred = preferredVariantRepresentation()
      || slideVariants.value[0]
      || targetSlideRepresentations.value[0]
    if (preferred) {
      applyVariantSelection(preferred)
      await store.select(preferred.representation_id)
    } else if (
      !isTeacherSurface.value
      &&
      !store.liveSlides.length
      && slideEngineStatus.value !== 'blocked'
    ) {
      generatorOpen.value = true
    }
  } catch {
    if (isCurrentAttempt(id, attempt)) {
      documentLoadError.value = t('pptWorkspace.documentLoadFailed', '加载课程源失败，请重试')
    }
  } finally {
    if (isCurrentAttempt(id, attempt)) initializing.value = false
  }
}

async function loadPptManuscriptState(id: string, attempt: number) {
  if (!teacherLessonId.value) return null
  const response = await http.get(
    `/api/teacher/courses/${id}/lessons/${teacherLessonId.value}/ppt-v6/manuscript`,
  )
  if (!isCurrentAttempt(id, attempt)) return null
  pptManuscriptState.value = response.data?.ppt_manuscript_state || null
  const state = pptManuscriptState.value
  if (state?.mode) selectedMode.value = state.mode
  if (state?.theme) selectedTheme.value = state.theme
  selectedTemplatePackId.value = state?.template_pack_id || ''
  selectedTemplatePackVersion.value = state?.template_version
    ? Number(state.template_version)
    : undefined
  return pptManuscriptState.value
}

function isCurrentAttempt(id: string, attempt: number) {
  return courseId.value === id && workspaceAttempt === attempt
}

async function loadDocumentEnvelope(id: string, attempt: number) {
  const endpoint = isTeacherSurface.value
    ? `/api/teacher/courses/${id}/lessons/${teacherLessonId.value}/ppt-v6/source`
    : `/api/courses/${id}/document`
  const response = await http.get<CourseDocumentEnvelope>(endpoint)
  const envelope = response.data
  if (!envelope?.document || !isCurrentAttempt(id, attempt)) return null
  courseStore.applyCourseDocumentEnvelope(envelope)
  documentEnvelope.value = envelope
  return envelope
}

async function migrateCourse() {
  const id = courseId.value
  const envelope = documentEnvelope.value
  const attempt = workspaceAttempt
  if (!id || !envelope || envelope.source_format !== 'legacy_projection' || migrating.value) return

  migrating.value = true
  migrationMessage.value = ''
  try {
    const response = await http.post<CourseDocumentEnvelope>(`/api/courses/${id}/document/migrate`, {
      confirm: true,
      source_checksum: envelope.migration.source_checksum,
    })
    if (!response.data?.document || !isCurrentAttempt(id, attempt)) return
    courseStore.applyCourseDocumentEnvelope(response.data)
    documentEnvelope.value = response.data
    if (response.data.source_format !== 'canonical') return
    store.deferMissingSlideBuild = true
    try {
      await store.ensure(id, { loadSelectedSpec: false })
    } finally {
      store.deferMissingSlideBuild = false
    }
    if (!isCurrentAttempt(id, attempt)) return
    const preferred = preferredVariantRepresentation()
      || slideVariants.value[0]
      || targetSlideRepresentations.value[0]
    if (preferred) {
      applyVariantSelection(preferred)
      await store.select(preferred.representation_id)
    } else if (
      !store.liveSlides.length
      && slideEngineStatus.value !== 'blocked'
    ) {
      generatorOpen.value = true
    }
  } catch (error: any) {
    if (error?.response?.status !== 409 || !isCurrentAttempt(id, attempt)) return
    const refreshed = await loadDocumentEnvelope(id, attempt)
    if (refreshed && isCurrentAttempt(id, attempt)) {
      migrationMessage.value = t('pptWorkspace.migrationPreviewRefreshed', '课程源已变化，迁移预览已刷新，请确认后重试')
    }
  } finally {
    if (isCurrentAttempt(id, attempt)) migrating.value = false
  }
}

async function upgradeCourseLogic() {
  const id = courseId.value
  const attempt = workspaceAttempt
  if (
    !id
    || logicUpgrading.value
    || slideEngineStatus.value !== 'blocked'
  ) return

  logicUpgrading.value = true
  logicUpgradeError.value = ''
  try {
    await store.upgradeCourseLogic(id)
    if (!isCurrentAttempt(id, attempt)) return
    const targetSchema = String(
      store.registry?.slide_deck_target_schema || '',
    )
    if (['slide_deck_v6', 'slide_deck_v5', 'slide_deck_v4'].includes(targetSchema)) {
      generatorOpen.value = true
      return
    }
    logicUpgradeError.value = '课程逻辑补全后仍未通过检查，请检查课程知识点与教学目标。'
  } catch (error: any) {
    if (!isCurrentAttempt(id, attempt)) return
    logicUpgradeError.value = String(
      error?.response?.data?.detail?.message
      || '课程逻辑补全失败，请稍后重试。',
    )
  } finally {
    if (isCurrentAttempt(id, attempt)) logicUpgrading.value = false
  }
}

async function rebuild() {
  if (!courseId.value || store.building) return
  if (slideEngineStatus.value === 'blocked') {
    logicUpgradeError.value = effectiveBuildFailure.value?.message || '当前课程逻辑尚未就绪。'
    return
  }
  try {
    if (store.buildPaused) await store.resumeBuild()
    else await store.buildSlideDeckVariant(courseId.value, {
      mode: selectedMode.value,
      theme: selectedTheme.value,
      forceRebuild: true,
      webImageRetrieval: {
        enabled: selectedWebImageRetrieval.value,
        mode: 'wide_safe',
      },
      templatePackId: selectedTemplatePackId.value || undefined,
      templatePackVersion: selectedTemplatePackVersion.value,
    })
  } catch {
    return
  }
  if (slideRepresentation.value) await store.select(slideRepresentation.value.representation_id)
}

async function startOrResumeBuild() {
  if (store.buildPaused) {
    await store.resumeBuild()
    return
  }
  openGenerator(false)
}

function openGenerator(forceRebuild: boolean) {
  if (slideEngineStatus.value === 'blocked') return
  if (!templateStore.loading && !templateStore.builtIn.length) {
    void templateStore.load()
  }
  forceGeneratorBuild.value = forceRebuild
  generatorOpen.value = true
}

function openTemplateCreator() {
  generatorOpen.value = false
  templateCreatorOpen.value = true
}

function closeTemplateCreator() {
  templateCreatorOpen.value = false
  if (!store.building) generatorOpen.value = true
}

async function handleTemplatePublished(template: PersonalPptTemplatePack) {
  await templateStore.load()
  selectedTemplatePackId.value = template.pack_id
  selectedTemplatePackVersion.value = template.version || template.latest_version
}

function closeGenerator() {
  generatorOpen.value = false
  const current = store.selectedRepresentation
  if (current?.variant_key) {
    applyVariantSelection(current)
  } else {
    selectedMode.value = 'teaching'
    selectedTheme.value = 'academic-editorial'
  }
}

async function generateVariant(value: {
  mode: SlideDeckMode
  theme: V3Theme
  webImageRetrieval: { enabled: boolean; mode: 'wide_safe' }
  templatePackId?: string
  templatePackVersion?: number
}) {
  if (!courseId.value || store.building) return
  if (slideEngineStatus.value === 'blocked') {
    generatorOpen.value = false
    logicUpgradeError.value = effectiveBuildFailure.value?.message || '当前课程逻辑尚未就绪。'
    return
  }
  selectedMode.value = value.mode
  selectedTheme.value = value.theme
  selectedWebImageRetrieval.value = value.webImageRetrieval.enabled
  selectedTemplatePackId.value = value.templatePackId || ''
  selectedTemplatePackVersion.value = value.templatePackVersion
  generatorOpen.value = false
  try {
    const manuscriptOnly = isTeacherSurface.value
    const completed = await store.buildSlideDeckVariant(courseId.value, {
      mode: value.mode,
      theme: value.theme,
      engineVersion: slideEngineStatus.value === 'slide_deck_v6' ? 'v6' : undefined,
      templatePackId: value.templatePackId,
      templatePackVersion: value.templatePackVersion,
      forceRebuild: forceGeneratorBuild.value,
      manuscriptOnly,
      webImageRetrieval: value.webImageRetrieval,
    })
    if (manuscriptOnly && completed?.ppt_manuscript_state) {
      pptManuscriptState.value = completed.ppt_manuscript_state as any
      pptManuscriptConfirmError.value = ''
      return
    }
  } catch {
    return
  } finally {
    forceGeneratorBuild.value = false
  }
  const variant = preferredVariantRepresentation()
  if (variant) await store.select(variant.representation_id)
}

async function selectVariant(value: { mode: SlideDeckMode; theme: V3Theme }) {
  selectedMode.value = value.mode
  selectedTheme.value = value.theme
  const cached = preferredVariantRepresentation()
  if (cached) {
    await store.select(cached.representation_id)
    return
  }
  if (slideEngineStatus.value === 'blocked') {
    logicUpgradeError.value = effectiveBuildFailure.value?.message || '当前课程逻辑尚未就绪。'
    return
  }
  forceGeneratorBuild.value = false
  generatorOpen.value = true
}

function applyVariantSelection(representation: TeachingRepresentation) {
  const [mode = '', theme = ''] = String(representation.variant_key || '').split(':')
  if (['full', 'teaching', 'concise'].includes(mode)) selectedMode.value = mode as SlideDeckMode
  if (['qizhi-classroom', 'academic-editorial', 'grid-notebook', 'modern-geometric', 'dark-tech'].includes(theme)) {
    selectedTheme.value = theme as V3Theme
  }
  const template = String(representation.variant_key || '').match(/:template:([^:@]+)@(\d+)/)
  selectedTemplatePackId.value = template?.[1] || ''
  selectedTemplatePackVersion.value = template?.[2] ? Number(template[2]) : undefined
}

function baseVariantKey(variantKey?: string) {
  return String(variantKey || '').split(':part:')[0]
}

function bundlePartIndex(variantKey?: string) {
  return Number(String(variantKey || '').split(':part:')[1] || 1)
}

function preferredVariantRepresentation() {
  return (
    slideVariants.value.find(item => item.variant_key === activeVariantKey.value)
    || activeBundleRepresentations.value
      .slice()
      .sort((left, right) => (
        bundlePartIndex(left.variant_key) - bundlePartIndex(right.variant_key)
      ))[0]
  )
}

async function selectBundlePart(representationId: string) {
  const part = activeBundleRepresentations.value.find(
    item => item.representation_id === representationId,
  )
  if (part) await store.select(part.representation_id)
}

async function pauseBuild() {
  await store.pauseBuild().catch(() => undefined)
}

async function cancelBuild() {
  await store.cancelBuild().catch(() => undefined)
}

function backToCourse() {
  const returnTo = String(route.query.returnTo || '')
  if (returnTo.startsWith('/') && !returnTo.startsWith('//')) {
    void router.push(returnTo)
    return
  }
  void router.push(isTeacherSurface.value
    ? { name: 'teacher-course-production', params: { courseId: courseId.value }, query: { stage: 'ppt' } }
    : { name: 'learning', params: { courseId: courseId.value } })
}

function openMaterials() {
  materialsVisible.value = true
}

async function closeMaterials() {
  materialsVisible.value = false
  if (slideRepresentation.value) {
    await store.select(slideRepresentation.value.representation_id)
  }
}

function openSameSourceCourse(state: PptSameSourceHighlightState) {
  if (isTeacherSurface.value) {
    void router.push({
      name: 'teacher-course-production',
      params: { courseId: state.courseId },
      query: { stage: 'teaching', lesson: teacherLessonId.value, section: state.sectionId },
    })
    return
  }
  void router.push({
    name: 'learning',
    params: { courseId: state.courseId, nodeId: state.sectionId },
  })
}

function applyPptAiEvent(type: Parameters<typeof transitionTeacherProductionAiPhase>[1]['type']) {
  pptAiPhase.value = transitionTeacherProductionAiPhase(pptAiPhase.value, { type } as any)
}

function addPptAiMessage(
  role: TeacherProductionAiMessage['role'],
  kind: TeacherProductionAiMessage['kind'],
  text: string,
  metadata: Partial<Pick<TeacherProductionAiMessage, 'planId' | 'planStatus' | 'impacts'>> = {},
) {
  pptAiMessages.value.push({
    id: `ppt-ai-${Date.now()}-${++pptAiMessageSequence}`,
    role,
    kind,
    text,
    ...metadata,
  })
}

async function loadPptAiCandidate() {
  if (!isTeacherSurface.value || !courseId.value || !teacherLessonId.value || !store.selectedId) {
    pptAiCandidate.value = null
    return
  }
  const representationId = store.selectedId
  const attempt = ++pptAiCandidateAttempt
  try {
    const response = await http.get(
      `/api/teacher/courses/${courseId.value}/lessons/${teacherLessonId.value}/ppt-v6/${representationId}/spec`,
    )
    if (attempt !== pptAiCandidateAttempt || store.selectedId !== representationId) return
    const candidate = (response.data.ai_candidate || null) as TeacherV6AiCandidate | null
    const previousCandidateId = pptAiCandidate.value?.candidate_id
    pptAiCandidate.value = candidate
    if (!candidate) return
    pptAiPageId.value = candidate.page_id
    aiVisible.value = true
    if (previousCandidateId !== candidate.candidate_id) {
      pptAiMessages.value = []
      addPptAiMessage('assistant', 'candidate', t('pptWorkspace.aiCandidateRestored', '已恢复待确认修改。'))
    }
    applyPptAiEvent('CANDIDATE_RESTORED')
  } catch {
    if (attempt === pptAiCandidateAttempt) {
      pptAiCandidate.value = null
    }
  }
}

async function confirmPptManuscript() {
  const state = pptManuscriptState.value
  if (
    !isTeacherSurface.value
    || !courseId.value
    || !teacherLessonId.value
    || !state?.revision
    || !state.confirmable
    || state.status === 'confirmed'
    || pptManuscriptConfirming.value
  ) return
  pptManuscriptConfirming.value = true
  pptManuscriptConfirmError.value = ''
  try {
    const response = await http.post(
      `/api/teacher/courses/${courseId.value}/lessons/${teacherLessonId.value}/ppt-v6/manuscript/confirm`,
      { manuscript_revision: state.revision },
    )
    pptManuscriptState.value = response.data.ppt_manuscript_state
  } catch (error: any) {
    pptManuscriptConfirmError.value = String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || t('pptWorkspace.manuscriptConfirmFailed', '确认失败，请刷新后重试。'),
    )
  } finally {
    pptManuscriptConfirming.value = false
  }
}

async function generatePptFromConfirmedManuscript() {
  const state = pptManuscriptState.value
  if (
    !state?.can_generate_ppt
    || store.building
    || !courseId.value
  ) return
  pptManuscriptConfirmError.value = ''
  try {
    await store.buildSlideDeckVariant(courseId.value, {
      mode: state.mode || selectedMode.value,
      theme: state.theme || selectedTheme.value,
      engineVersion: 'v6',
    })
    await loadPptManuscriptState(courseId.value, workspaceAttempt)
    const representation = preferredVariantRepresentation()
      || targetSlideRepresentations.value[0]
    if (representation) await store.select(representation.representation_id)
    manuscriptWorkflowForced.value = false
  } catch {
    return
  }
}

function pptAiErrorMessage(error: any) {
  return String(
    error?.response?.data?.detail?.message
    || error?.response?.data?.detail
    || error?.message
    || t('pptWorkspace.aiFailed', 'AI 修改失败，请重试。'),
  )
}

function currentPptAiScope(page = pptAiPage.value): TeacherProductionAiScope {
  return {
    domain: 'ppt',
    courseTitle: courseTitle.value,
    primaryTitle: String(page?.title || pptAiScopeTitle.value),
    secondaryTitle: pptAiScopeDetail.value,
    referenceCount: pptAiReferences.value.length,
    references: pptAiReferences.value,
  }
}

function pptCoursePlanImpacts(projection: TeacherCoursePlanProjection): string[] {
  const labels: Record<string, string> = {
    outline: t('courseWorkbench.aiCollaboration.assetOutline', '大纲'),
    course_content: t('courseWorkbench.aiCollaboration.assetCourseContent', '课程内容'),
    lesson_plan: t('courseWorkbench.aiCollaboration.assetLessonPlan', '教案'),
    script: t('courseWorkbench.aiCollaboration.assetScript', '讲稿'),
    ppt: 'PPT',
    question_bank: t('courseWorkbench.aiCollaboration.assetQuestionBank', '题库'),
  }
  const assets = projection.assetTypes.map(assetType => labels[assetType] || assetType)
  return [
    projection.affectedUnitCount
      ? t('courseWorkbench.aiCollaboration.affectedUnits', '{count} 个受影响单元').replace('{count}', String(projection.affectedUnitCount))
      : '',
    projection.structuralOperationCount
      ? t('courseWorkbench.aiCollaboration.structuralOperations', '{count} 项结构调整').replace('{count}', String(projection.structuralOperationCount))
      : '',
    assets.length ? assets.join('、') : '',
  ].filter(Boolean)
}

async function createPptCourseChangePlan() {
  const requestId = pptAiCoursePlanRequestId.value || `teacher-ppt-${createUuid()}`
  pptAiCoursePlanRequestId.value = requestId
  applyPptAiEvent('GENERATE')
  try {
    const payload = await courseEvolutionStore.createCoursePlan({
      courseId: courseId.value,
      requestId,
      instruction: buildTeacherCourseChangeInstruction(pptAiMessages.value, currentPptAiScope()),
    })
    const plans = (payload?.course_evolution_plans || payload?.change_sets || []) as Array<Record<string, any>>
    const plan = plans.find(item => String(item.impact_summary?.request_id || '') === requestId)
    const projection = plan ? projectTeacherCoursePlan(plan) : null
    if (!projection) throw new Error('course_change_plan_missing')
    addPptAiMessage(
      'assistant',
      'course_plan',
      projection.blockingQuestionCount
        ? t('courseWorkbench.aiCollaboration.coursePlanNeedsDetailSummary', '我已整理修改范围，但有 {count} 个问题需要你补充。正式课程尚未改变。').replace('{count}', String(projection.blockingQuestionCount))
        : t('courseWorkbench.aiCollaboration.coursePlanSummary', '我已把要求整理成整课修改方案。请先核对影响范围，再决定生成并应用哪些修改。'),
      {
        planId: projection.planId,
        planStatus: projection.status,
        impacts: pptCoursePlanImpacts(projection),
      },
    )
    applyPptAiEvent('COURSE_PLAN_READY')
  } catch (error: any) {
    applyPptAiEvent('FAIL')
    addPptAiMessage('assistant', 'error', pptAiErrorMessage(error))
  }
}

async function requestPptAiCandidate(value: string, options: { retry?: boolean } = {}) {
  const instruction = String(value || '').trim()
  const page = pptAiPage.value
  const spec = store.selectedSpec
  const representationId = store.selectedId
  if (!instruction || !page || !spec || !representationId || pptAiBusy.value) return
  pptAiLastInstruction.value = instruction
  if (!options.retry) addPptAiMessage('user', 'text', instruction)
  const requestRoute = routeTeacherProductionRequest('ppt', instruction)
  if (requestRoute.capability === 'clarify_request') {
    applyPptAiEvent('ASK_CLARIFICATION')
    addPptAiMessage('assistant', 'text', t('pptWorkspace.aiClarify', '请指定标题、副标题或关键内容。'))
    return
  }
  if (requestRoute.capability === 'plan_course_change') {
    if (!options.retry) pptAiCoursePlanRequestId.value = ''
    await createPptCourseChangePlan()
    return
  }
  applyPptAiEvent('GENERATE')
  try {
    const prompt = buildTeacherProductionAiInstruction(pptAiMessages.value, currentPptAiScope(page))
    const data = await postGenerationStream<{ candidate: TeacherV6AiCandidate }>(
      `/api/teacher/courses/${courseId.value}/lessons/${teacherLessonId.value}/ppt-v6/${representationId}/ai-candidates`,
      {
        page_id: String(page.page_id || ''),
        instruction: prompt,
        base_spec_id: spec.spec_id,
        base_spec_revision: spec.revision,
      },
      { headers: teacherIdentityHeaders() },
    )
    pptAiCandidate.value = data.candidate
    pptAiPageId.value = pptAiCandidate.value.page_id
    applyPptAiEvent('CANDIDATE_READY')
    addPptAiMessage('assistant', 'candidate', t('pptWorkspace.aiCandidateReady', '修改已显示在左侧。'))
  } catch (error: any) {
    applyPptAiEvent('FAIL')
    addPptAiMessage('assistant', 'error', pptAiErrorMessage(error))
  }
}

async function retryPptAiCandidate() {
  if (pptAiLastInstruction.value) await requestPptAiCandidate(pptAiLastInstruction.value, { retry: true })
}

function openPptCoursePlan(planId: string) {
  if (!planId) return
  void router.push({
    name: 'course-audit-updates',
    params: { courseId: courseId.value, planId },
    query: {
      view: 'changes',
      returnTo: route.fullPath,
      returnLabel: t('courseAuditUpdates.returnPpt', '返回 PPT'),
    },
  })
}

async function resolvePptAiCandidate(accept: boolean) {
  const candidate = pptAiCandidate.value
  if (!candidate || pptAiBusy.value) return
  applyPptAiEvent(accept ? 'ACCEPT' : 'REJECT')
  try {
    const response = await http.post(
      `/api/teacher/courses/${courseId.value}/lessons/${teacherLessonId.value}/ppt-v6/${candidate.representation_id}/ai-candidates/${candidate.candidate_id}/resolve`,
      { accept },
    )
    if (accept && response.data.registry) store.registry = response.data.registry
    if (accept && response.data.spec) store.selectedSpec = response.data.spec
    pptAiCandidate.value = null
    applyPptAiEvent('RESOLVED')
    addPptAiMessage(
      'assistant',
      'receipt',
      accept
        ? t('pptWorkspace.aiAccepted', '已形成新的 PPT 修订。')
        : t('pptWorkspace.aiRejected', '已放弃这次修改。'),
    )
  } catch (error: any) {
    applyPptAiEvent('FAIL')
    addPptAiMessage('assistant', 'error', pptAiErrorMessage(error))
  }
}

function focusPptAiCandidate() {
  if (!pptAiCandidate.value) return
  pptAiPageId.value = pptAiCandidate.value.page_id
}

function closePptAi() {
  aiVisible.value = false
}

function clampPptAiWidth(value: number) {
  return Math.round(Math.min(pptAiMaxWidth.value, Math.max(PPT_AI_MIN_WIDTH, value)))
}

const pptAiMaxWidth = computed(() => {
  const width = workspaceRoot.value?.clientWidth || window.innerWidth
  return Math.max(PPT_AI_MIN_WIDTH, Math.min(PPT_AI_MAX_WIDTH, width - PPT_CANVAS_MIN_WIDTH))
})

function persistPptAiWidth() {
  localStorage.setItem(PPT_AI_WIDTH_KEY, String(pptAiPaneWidth.value))
}

function stopPptAiResize() {
  pptAiResizing.value = false
  window.removeEventListener('pointermove', movePptAiResize)
  window.removeEventListener('pointerup', stopPptAiResize)
  persistPptAiWidth()
}

function movePptAiResize(event: PointerEvent) {
  const rect = workspaceRoot.value?.getBoundingClientRect()
  if (!rect) return
  pptAiPaneWidth.value = clampPptAiWidth(rect.right - event.clientX)
}

function startPptAiResize(event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  pptAiResizing.value = true
  window.addEventListener('pointermove', movePptAiResize)
  window.addEventListener('pointerup', stopPptAiResize, { once: true })
}

function resizePptAiWithKeyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  pptAiPaneWidth.value = clampPptAiWidth(
    pptAiPaneWidth.value + (event.key === 'ArrowLeft' ? 24 : -24),
  )
  persistPptAiWidth()
}

function openAiForSlide(payload: { text: string; nodeId: string; anchor: Record<string, unknown>; prefill: string }) {
  aiQuote.value = payload.text
  aiNodeId.value = payload.nodeId
  aiAnchor.value = payload.anchor
  aiPrefill.value = payload.prefill
  pptAiPageId.value = String(payload.anchor?.slide_unit_id || '')
  aiVisible.value = true
  if (isTeacherSurface.value && !pptAiCandidate.value) {
    pptAiPhase.value = 'ready'
  }
}

watch([courseId, teacherLessonId], loadWorkspace)
watch(
  () => [store.selectedId, store.selectedSpec?.revision],
  () => { void loadPptAiCandidate() },
)
onMounted(() => {
  const savedWidth = Number(localStorage.getItem(PPT_AI_WIDTH_KEY) || 0)
  if (Number.isFinite(savedWidth) && savedWidth > 0) pptAiPaneWidth.value = clampPptAiWidth(savedWidth)
  void loadWorkspace()
})
onUnmounted(() => {
  stopPptAiResize()
  pptAiCandidateAttempt += 1
  store.setTeacherLessonScope('')
  templateAssetAttempt += 1
  templateStore.releaseAllAssets()
})
</script>

<style scoped>
.ppt-workspace-view { position:relative; width:100%; height:100%; display:flex; min-width:0; min-height:0; overflow:hidden; border-radius:var(--lz-radius-surface); background:#e9edf3; }
.ppt-workspace-view__deck { min-width:0; flex:1 1 auto; }
.ppt-workspace-view__ai-resizer{position:relative;z-index:4;width:8px;flex:0 0 8px;display:grid;place-items:center;border:0;border-left:1px solid #e0e5ed;color:transparent;background:#f8f9fb;cursor:col-resize;outline:0}.ppt-workspace-view__ai-resizer::before{content:"";position:absolute;inset:0 -4px}.ppt-workspace-view__ai-resizer:hover,.ppt-workspace-view__ai-resizer.is-resizing,.ppt-workspace-view__ai-resizer:focus-visible{color:#716ce1;background:#eeefff}.ppt-workspace-view__ai-resizer:focus-visible{box-shadow:inset 2px 0 #716ce1}.ppt-workspace-view.is-ai-open:has(.ppt-workspace-view__ai-resizer.is-resizing){user-select:none;cursor:col-resize}
.ppt-workspace-view__ai { width:var(--ppt-ai-width); flex:0 0 var(--ppt-ai-width); border-left:0; background:#fff; }
.ppt-workspace-state {
  position:relative;
  width:100%;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:28px;
  text-align:center;
  color:#1a2533;
  background:
    radial-gradient(circle at 20% 18%,rgba(37,86,216,.11),transparent 26%),
    radial-gradient(circle at 80% 78%,rgba(8,127,116,.1),transparent 24%),
    #f5f7fa;
}
.ppt-workspace-state__mark { width:76px; height:76px; display:grid; place-items:center; margin-bottom:22px; border:1px solid #b9c9ed; border-radius:22px; color:#2556d8; background:#fff; box-shadow:0 18px 46px rgba(37,65,114,.13); }
.ppt-workspace-state > small { color:#2556d8; font-size:11px; font-weight:800; letter-spacing:.16em; }
.ppt-workspace-state h1 { max-width:760px; margin:12px 0 0; font-family:"Songti SC","STSong","Noto Serif CJK SC",serif; font-size:clamp(28px,4vw,52px); line-height:1.15; }
.ppt-workspace-state p { max-width:620px; margin:16px 0 0; color:#667085; font-size:14px; line-height:1.7; }
.ppt-workspace-state > b { margin-top:10px; color:#6f7c8d; font:700 11px/1 "Aptos Mono","SFMono-Regular",monospace; }
.ppt-workspace-state__task-actions { display:flex; gap:8px; margin-top:14px; }
.ppt-workspace-state__task-actions button { min-height:34px; padding:0 14px; border:1px solid #cbd5e1; border-radius:9px; color:#334155; background:#fff; cursor:pointer; }
.ppt-workspace-state__back { position:absolute; top:22px; left:22px; width:40px; height:40px; display:grid; place-items:center; border:1px solid #d4dae4; border-radius:10px; color:#526174; background:#fff; cursor:pointer; }
.ppt-workspace-state__build { min-height:42px; display:inline-flex; align-items:center; gap:8px; margin-top:26px; padding:0 18px; border:0; border-radius:10px; color:#fff; background:#2556d8; box-shadow:0 10px 24px rgba(37,86,216,.24); font-size:13px; font-weight:700; cursor:pointer; }
.ppt-workspace-state__build:disabled { cursor:not-allowed; opacity:.5; box-shadow:none; }
.ppt-workspace-state__upgrade-logic { min-height:42px; display:inline-flex; align-items:center; gap:8px; margin-top:22px; padding:0 18px; border:0; border-radius:10px; color:#fff; background:#2556d8; box-shadow:0 10px 24px rgba(37,86,216,.24); font-size:13px; font-weight:700; cursor:pointer; }
.ppt-workspace-state__upgrade-logic:disabled { cursor:wait; opacity:.65; box-shadow:none; }
.ppt-workspace-state__logic-error { color:#a12828 !important; }
.ppt-workspace-state__engine { display:inline-flex; align-items:center; min-height:28px; padding:0 10px; border:1px solid #bfd1ff; border-radius:999px; color:#2449a8; background:#edf3ff; font-size:11px; font-weight:800; }
.ppt-workspace-state__engine[data-engine-status="slide_deck_v3"] { border-color:#ecd09c; color:#85520a; background:#fff7e6; }
.ppt-workspace-state__engine[data-engine-status="blocked"] { border-color:#efb6b6; color:#a12828; background:#fff0f0; }
.ppt-ai-enter-active,.ppt-ai-leave-active { transition:transform .22s ease,opacity .22s ease; }
.ppt-ai-enter-from,.ppt-ai-leave-to { opacity:0; transform:translateX(20px); }
@media (max-width:860px) {
  .ppt-workspace-view__ai-resizer{display:none}
  .ppt-workspace-view__ai { position:absolute; inset:0 0 0 auto; z-index:20; width:min(420px,92vw); box-shadow:-18px 0 44px rgba(20,31,52,.18); }
}
@media (max-width:600px) {
  .ppt-workspace-view { border-radius:0; }
}
</style>
