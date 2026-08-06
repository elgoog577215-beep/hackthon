<template>
  <section class="ppt-workspace-view">
    <div v-if="initializing || (!slideRepresentation && store.building && !store.liveSlides.length)" class="ppt-workspace-state">
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <small>{{ t('pptWorkspace.eyebrow', 'PPT 工作台') }}</small>
      <h1>{{ courseTitle }}</h1>
      <p>{{ store.building ? stageLabel : t('pptWorkspace.loading', '正在读取同源课件与页面结构') }}</p>
      <div class="ppt-workspace-state__progress"><i :style="{ width: `${store.buildProgress}%` }"></i></div>
      <b>{{ store.building ? `${store.buildProgress}%` : '···' }}</b>
      <div v-if="store.buildTaskId" class="ppt-workspace-state__task-actions">
        <button v-if="store.building" type="button" @click="pauseBuild">暂停</button>
        <button type="button" @click="cancelBuild">取消</button>
      </div>
    </div>

    <div v-else-if="documentLoadError" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <small>{{ t('pptWorkspace.eyebrow', 'PPT 工作台') }}</small>
      <h1>{{ courseTitle }}</h1>
      <p>{{ documentLoadError }}</p>
    </div>

    <div v-else-if="documentEnvelope?.source_format !== 'legacy_projection' && !slideRepresentation && !store.liveSlides.length" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <small>{{ t('pptWorkspace.emptyEyebrow', '课堂课件尚未生成') }}</small>
      <h1>{{ courseTitle }}</h1>
      <small
        class="ppt-workspace-state__engine"
        data-testid="ppt-engine-status"
        :data-engine-status="slideEngineStatus"
      >{{ slideEngineStatusLabel }}</small>
      <p>{{ buildErrorLabel || t('pptWorkspace.emptyDescription', '从课程目标、正文、知识点与理解检查编译一套可直接上课的 PPT。') }}</p>
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
      <button v-else type="button" class="ppt-workspace-state__build" :disabled="store.building" @click="openGenerator(false)">
        <Sparkles :size="17" />{{ store.buildPaused ? '从保存点继续' : t('pptWorkspace.build', '选择模式与风格') }}
      </button>
    </div>

    <div v-else-if="documentEnvelope?.source_format === 'legacy_projection'" class="ppt-workspace-state is-empty">
      <button type="button" class="ppt-workspace-state__back" @click="backToCourse"><ArrowLeft :size="18" /></button>
      <div class="ppt-workspace-state__mark"><Presentation :size="34" /></div>
      <small>{{ t('pptWorkspace.legacyMigrationEyebrow', '课程源升级') }}</small>
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
        :error="store.buildError"
        :build-failure="effectiveBuildFailure"
        :logic-upgrading="logicUpgrading"
        :logic-upgrade-error="logicUpgradeError"
        :quality="displayQuality"
        :preview-source="store.slidePreviewSource"
        :mode="selectedMode"
        :theme="selectedTheme"
        :variants="slideVariants"
        :bundle-parts="activeBundleParts"
        :active-bundle-part-id="slideRepresentation?.representation_id || ''"
        :engine-status="slideEngineStatus"
        @back="backToCourse"
        @rebuild="rebuild"
        @configure="openGenerator(false)"
        @upgrade-course-logic="upgradeCourseLogic"
        @variant-change="selectVariant"
        @bundle-part-change="selectBundlePart"
        @open-materials="openMaterials"
        @ask-ai="openAiForSlide"
        @open-course="openSameSourceCourse"
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

      <Transition name="ppt-ai">
        <SideAIPanel
          v-if="aiVisible"
          class="ppt-workspace-view__ai"
          :visible="aiVisible"
          :quote-text="aiQuote"
          :quote-node-id="aiNodeId"
          :quote-anchor="aiAnchor"
          :prefill="aiPrefill"
          entrypoint="global"
          @close="aiVisible = false"
        />
      </Transition>
    </template>

    <SlideDeckGeneratorDialog
      :open="generatorOpen"
      :mode="selectedMode"
      :theme="selectedTheme"
      :busy="store.building"
      :closable="Boolean(slideRepresentation)"
      :fragment-count="estimatedFragmentCount"
      @close="closeGenerator"
      @confirm="generateVariant"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Presentation, Sparkles } from 'lucide-vue-next'
import SideAIPanel from '../components/SideAIPanel.vue'
import SlideDeckWorkbench from '../components/SlideDeckWorkbench.vue'
import SlideDeckGeneratorDialog from '../components/SlideDeckGeneratorDialog.vue'
import TeachingRepresentationsOverlay from '../components/TeachingRepresentationsOverlay.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
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
import http from '../utils/http'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const store = useTeachingRepresentationsStore()
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
const forceGeneratorBuild = ref(false)
const selectedMode = ref<SlideDeckMode>('teaching')
const selectedTheme = ref<V3Theme>('qizhi-classroom')
let workspaceAttempt = 0

type V3Theme = Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>

const courseId = computed(() => String(route.params.courseId || ''))
const courseTitle = computed(() => (
  store.selectedSpec?.payload?.content?.title
  || courseStore.currentCourse?.course_name
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
const activeVariantKey = computed(() => `${selectedMode.value}:${selectedTheme.value}`)
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
const content = computed(() => store.selectedSpec?.payload?.content || null)
const slideEngineStatus = computed<
  'slide_deck_v5' | 'slide_deck_v4' | 'slide_deck_v3' | 'blocked' | 'unknown'
>(() => {
  const target = String(store.registry?.slide_deck_target_schema || '')
  if (['slide_deck_v5', 'slide_deck_v4', 'slide_deck_v3', 'blocked'].includes(target)) {
    return target as 'slide_deck_v5' | 'slide_deck_v4' | 'slide_deck_v3' | 'blocked'
  }
  const publishedSchema = String(content.value?.schema_version || '')
  if (
    publishedSchema === 'slide_deck_v5'
    || publishedSchema === 'slide_deck_v4'
    || publishedSchema === 'slide_deck_v3'
  ) {
    return publishedSchema
  }
  return 'unknown'
})
const slideEngineStatusLabel = computed(() => ({
  slide_deck_v5: '将使用课程叙事与语义版式 V5 生成',
  slide_deck_v4: '将使用新版课程逻辑 V4 生成',
  slide_deck_v3: '当前使用兼容模式 V3',
  blocked: '课程逻辑产物未就绪，暂不能生成 PPT',
  unknown: '正在确认 PPT 生成引擎',
}[slideEngineStatus.value]))

function representationMatchesTargetEngine(item: TeachingRepresentation) {
  const target = String(store.registry?.slide_deck_target_schema || '')
  if (
    target !== 'slide_deck_v5'
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
const displaySlides = computed(() => (
  store.liveSlides.length && store.slidePreviewSource === 'draft'
    ? store.liveSlides
    : (content.value?.slides || [])
))
const estimatedFragmentCount = computed(() => (
  Number(content.value?.fragment_manifest?.length)
  || (documentEnvelope.value?.document?.blocks || []).length * 3
))
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
const stageLabel = computed(() => ({
  fragmenting: '正在切分并校验课程原文',
  planning: t('teachingRepresentations.slides.stages.planning', '正在准备课程结构'),
  story_plan: '正在读取课程逻辑',
  chapter_plan: '正在编排章节叙事',
  episode_progress: '正在生成教学场景',
  layout_plan: '正在匹配语义版式',
  slide_plan: t('teachingRepresentations.slides.stages.slidePlan', '正在规划整套页面'),
  visual_plan: '正在规划课件视觉',
  asset_compilation: '正在编译课件素材',
  slide_build: t('teachingRepresentations.slides.stages.slideBuild', '正在逐页生成教学内容'),
  reviewing: '正在审核页面分配',
  quality: t('teachingRepresentations.slides.stages.quality', '正在检查课堂可用性'),
  render_review: '正在渲染复核成品',
  semantic_repair: '正在修复内容完整性与分页',
  image_search: '正在检索并核验教学图片',
  render_repair: '正在修复导出版式问题',
  repair_progress: '正在定向修复问题页面',
  quality_fallback: t('pptWorkspace.qualityFallbackStage', 'AI 草稿未通过检查，正在切换稳定生成方案'),
  bundle_plan: '正在按章节拆分课件',
  bundle_part_build: '正在逐册生成课件',
  paused: '已暂停，可从保存点继续',
  resuming: '正在从保存点继续',
  build_blocked: '生成已停止',
  cancelled: '生成已取消',
  complete: t('teachingRepresentations.slides.stages.complete', '生成完成'),
}[store.buildStage] || t('teachingRepresentations.slides.stages.building', '正在生成课件')))

async function loadWorkspace() {
  const id = courseId.value
  if (!id) return
  const attempt = ++workspaceAttempt
  initializing.value = true
  documentEnvelope.value = null
  migrating.value = false
  migrationMessage.value = ''
  logicUpgrading.value = false
  logicUpgradeError.value = ''
  documentLoadError.value = ''
  try {
    const envelope = await loadDocumentEnvelope(id, attempt)
    if (!envelope || !isCurrentAttempt(id, attempt) || envelope.source_format !== 'canonical') return
    store.deferMissingSlideBuild = true
    try {
      await store.ensure(id)
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
  } catch {
    if (isCurrentAttempt(id, attempt)) {
      documentLoadError.value = t('pptWorkspace.documentLoadFailed', '加载课程源失败，请重试')
    }
  } finally {
    if (isCurrentAttempt(id, attempt)) initializing.value = false
  }
}

function isCurrentAttempt(id: string, attempt: number) {
  return courseId.value === id && workspaceAttempt === attempt
}

async function loadDocumentEnvelope(id: string, attempt: number) {
  const response = await http.get<CourseDocumentEnvelope>(`/api/courses/${id}/document`)
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
      await store.ensure(id)
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
    if (targetSchema === 'slide_deck_v5' || targetSchema === 'slide_deck_v4') {
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
    })
  } catch {
    return
  }
  if (slideRepresentation.value) await store.select(slideRepresentation.value.representation_id)
}

function openGenerator(forceRebuild: boolean) {
  if (slideEngineStatus.value === 'blocked') return
  forceGeneratorBuild.value = forceRebuild
  generatorOpen.value = true
}

function closeGenerator() {
  generatorOpen.value = false
  const current = store.selectedRepresentation
  if (current?.variant_key) {
    applyVariantSelection(current)
  } else {
    selectedMode.value = 'teaching'
    selectedTheme.value = 'qizhi-classroom'
  }
}

async function generateVariant(value: { mode: SlideDeckMode; theme: V3Theme }) {
  if (!courseId.value || store.building) return
  if (slideEngineStatus.value === 'blocked') {
    generatorOpen.value = false
    logicUpgradeError.value = effectiveBuildFailure.value?.message || '当前课程逻辑尚未就绪。'
    return
  }
  selectedMode.value = value.mode
  selectedTheme.value = value.theme
  generatorOpen.value = false
  try {
    await store.buildSlideDeckVariant(courseId.value, {
      mode: value.mode,
      theme: value.theme,
      forceRebuild: forceGeneratorBuild.value,
    })
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
  void router.push({ name: 'learning', params: { courseId: courseId.value } })
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
  void router.push({
    name: 'learning',
    params: { courseId: state.courseId, nodeId: state.sectionId },
  })
}

function openAiForSlide(payload: { text: string; nodeId: string; anchor: Record<string, unknown>; prefill: string }) {
  aiQuote.value = payload.text
  aiNodeId.value = payload.nodeId
  aiAnchor.value = payload.anchor
  aiPrefill.value = payload.prefill
  aiVisible.value = true
}

watch(courseId, loadWorkspace)
onMounted(loadWorkspace)
</script>

<style scoped>
.ppt-workspace-view { position:fixed; inset:0; z-index:70; display:flex; min-width:0; min-height:0; overflow:hidden; background:#e9edf3; }
.ppt-workspace-view__deck { min-width:0; flex:1 1 auto; }
.ppt-workspace-view__ai { width:min(380px,34vw); flex:0 0 min(380px,34vw); border-left:1px solid #d5dce6; background:#fff; }
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
.ppt-workspace-state__progress { width:min(360px,70vw); height:5px; overflow:hidden; margin-top:26px; border-radius:99px; background:#dfe5ee; }
.ppt-workspace-state__progress i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#2556d8,#087f74); transition:width .25s ease; }
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
  .ppt-workspace-view__ai { position:absolute; inset:0 0 0 auto; z-index:20; width:min(420px,92vw); box-shadow:-18px 0 44px rgba(20,31,52,.18); }
}
</style>
