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
      <p>{{ buildErrorLabel || t('pptWorkspace.emptyDescription', '从课程目标、正文、知识点与理解检查编译一套可直接上课的 PPT。') }}</p>
      <button type="button" class="ppt-workspace-state__build" :disabled="store.building" @click="rebuild">
        <Sparkles :size="17" />{{ store.buildPaused ? '从保存点继续' : t('pptWorkspace.build', '生成完整课件') }}
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
        :quality="store.slideQuality"
        :preview-source="store.slidePreviewSource"
        @back="backToCourse"
        @rebuild="rebuild"
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
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Presentation, Sparkles } from 'lucide-vue-next'
import SideAIPanel from '../components/SideAIPanel.vue'
import SlideDeckWorkbench from '../components/SlideDeckWorkbench.vue'
import TeachingRepresentationsOverlay from '../components/TeachingRepresentationsOverlay.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useTeachingRepresentationsStore } from '../stores/teachingRepresentations'
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
const documentLoadError = ref('')
let workspaceAttempt = 0

const courseId = computed(() => String(route.params.courseId || ''))
const courseTitle = computed(() => (
  store.selectedSpec?.payload?.content?.title
  || courseStore.currentCourse?.course_name
  || t('pptWorkspace.untitledCourse', '课程演示')
))
const slideRepresentation = computed(() => (
  store.representations.find(item => item.representation_type === 'slide_deck') || null
))
const content = computed(() => store.selectedSpec?.payload?.content || null)
const displaySlides = computed(() => (
  store.liveSlides.length && store.slidePreviewSource === 'draft'
    ? store.liveSlides
    : (content.value?.slides || [])
))
const buildErrorLabel = computed(() => (
  store.buildError === 'quality_gate_failed'
    ? t('pptWorkspace.qualityBlocked', '课件未通过课堂可用性检查，系统没有发布问题版本。请调整课程内容后重试。')
    : store.buildError
))
const stageLabel = computed(() => ({
  planning: t('teachingRepresentations.slides.stages.planning', '正在准备课程结构'),
  slide_plan: t('teachingRepresentations.slides.stages.slidePlan', '正在规划整套页面'),
  slide_build: t('teachingRepresentations.slides.stages.slideBuild', '正在逐页生成教学内容'),
  quality: t('teachingRepresentations.slides.stages.quality', '正在检查课堂可用性'),
  paused: '已暂停，可从保存点继续',
  resuming: '正在从保存点继续',
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
  documentLoadError.value = ''
  try {
    const envelope = await loadDocumentEnvelope(id, attempt)
    if (!envelope || !isCurrentAttempt(id, attempt) || envelope.source_format !== 'canonical') return
    await store.ensure(id)
    if (!isCurrentAttempt(id, attempt)) return
    if (slideRepresentation.value) await store.select(slideRepresentation.value.representation_id)
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
    await store.ensure(id)
    if (!isCurrentAttempt(id, attempt)) return
    if (slideRepresentation.value) await store.select(slideRepresentation.value.representation_id)
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

async function rebuild() {
  if (!courseId.value || store.building) return
  if (store.buildPaused) await store.resumeBuild().catch(() => undefined)
  else await store.buildProgressive(courseId.value).catch(() => undefined)
  if (slideRepresentation.value) await store.select(slideRepresentation.value.representation_id)
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
.ppt-ai-enter-active,.ppt-ai-leave-active { transition:transform .22s ease,opacity .22s ease; }
.ppt-ai-enter-from,.ppt-ai-leave-to { opacity:0; transform:translateX(20px); }
@media (max-width:860px) {
  .ppt-workspace-view__ai { position:absolute; inset:0 0 0 auto; z-index:20; width:min(420px,92vw); box-shadow:-18px 0 44px rgba(20,31,52,.18); }
}
</style>
