<template>
  <section class="script-visual-studio" :data-open="open ? 'true' : 'false'">
    <button
      type="button"
      class="script-visual-toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      <Shapes :size="16" />
      <span>{{ tr('title', '视觉表达', 'Visual explanation') }}</span>
      <small v-if="acceptedCount">{{ tr('acceptedCount', `已采用 ${acceptedCount} 个`, `${acceptedCount} accepted`) }}</small>
      <small v-else-if="recommendation?.recommended_types.length">{{ tr('recommended', '建议补充', 'Suggested') }}</small>
      <ChevronDown :size="15" aria-hidden="true" />
    </button>

    <div v-if="open" class="script-visual-panel">
      <div class="script-visual-create">
        <p v-if="recommendationReason">{{ recommendationReason }}</p>
        <nav :aria-label="tr('createLabel', '选择视觉表达类型', 'Choose a visual type')">
          <button
            v-for="option in visualOptions"
            :key="option.type"
            type="button"
            :class="{ recommended: recommendation?.recommended_types.includes(option.type) }"
            :disabled="Boolean(busyType || resolvingId)"
            @click="generate(option.type)"
          >
            <LoaderCircle v-if="busyType === option.type" :size="15" class="spin" />
            <component :is="option.icon" v-else :size="15" />
            {{ option.label }}
          </button>
        </nav>
      </div>

      <p v-if="errorMessage" class="script-visual-error" role="alert">{{ errorMessage }}</p>
      <p v-else-if="loading && !blockItems.length" class="script-visual-loading">
        <LoaderCircle :size="15" class="spin" />{{ tr('loading', '正在读取视觉表达…', 'Loading visual explanations…') }}
      </p>

      <article
        v-for="item in displayItems"
        :key="item.representation_id"
        class="script-visual-item"
        :data-status="item.status"
        :data-type="item.representation_type"
      >
        <header>
          <strong>{{ typeLabel(item.representation_type) }}</strong>
          <span>{{ statusLabel(item) }}</span>
        </header>

        <DiagramSpecRenderer
          v-if="item.representation_type === 'diagram'"
          :unit="item.content?.units?.[0]"
          :title="String(item.content?.title || blockTitle)"
        />
        <StructuredScenePlayer
          v-else-if="item.representation_type === 'animation'"
          :scene="item.content"
        />
        <div v-else class="script-image-preview" :data-generation-status="item.content?.generation_status">
          <img
            v-if="imageUrls[item.representation_id]"
            :src="imageUrls[item.representation_id]"
            :alt="String(item.content?.title || blockTitle)"
          />
          <div v-else-if="item.content?.generation_status === 'provider_unavailable'" class="script-image-state">
            <ImageOff :size="21" />
            <strong>{{ tr('providerUnavailable', '图片服务未配置', 'Image service is not configured') }}</strong>
            <span>{{ tr('promptSaved', '生成提示词已经保存，配置服务后可以直接重试。', 'The prompt is saved. Retry after configuring the service.') }}</span>
          </div>
          <div v-else-if="item.content?.generation_status === 'provider_failed'" class="script-image-state">
            <TriangleAlert :size="21" />
            <strong>{{ tr('providerFailed', '图片生成没有完成', 'Image generation did not finish') }}</strong>
            <span>{{ tr('retryHint', '讲义不受影响，可以稍后重新生成。', 'The script is unaffected. You can retry later.') }}</span>
          </div>
          <div v-else class="script-image-state">
            <LoaderCircle :size="18" class="spin" />
            <span>{{ tr('assetLoading', '正在读取图片…', 'Loading image…') }}</span>
          </div>
          <details v-if="item.content?.prompt" class="script-image-prompt">
            <summary>{{ tr('prompt', '查看已保存提示词', 'View saved prompt') }}</summary>
            <p>{{ item.content.prompt }}</p>
          </details>
        </div>

        <footer v-if="item.status === 'candidate'">
          <template v-if="canAccept(item)">
            <button type="button" :disabled="Boolean(resolvingId)" @click="resolve(item, false)">
              <X :size="14" />{{ tr('discard', '放弃', 'Discard') }}
            </button>
            <button class="primary" type="button" :disabled="Boolean(resolvingId)" @click="resolve(item, true)">
              <LoaderCircle v-if="resolvingId === item.representation_id" :size="14" class="spin" />
              <Check v-else :size="14" />{{ tr('accept', '采用', 'Accept') }}
            </button>
          </template>
          <template v-else>
            <button type="button" :disabled="Boolean(busyType || resolvingId)" @click="resolve(item, false)">
              <X :size="14" />{{ tr('discard', '放弃', 'Discard') }}
            </button>
            <button class="primary" type="button" :disabled="Boolean(busyType || resolvingId)" @click="generate(item.representation_type)">
              <RotateCcw :size="14" />{{ tr('retry', '重新生成', 'Retry') }}
            </button>
          </template>
        </footer>
        <footer v-else-if="item.status === 'stale'" class="stale-actions">
          <span>{{ tr('staleDetail', '讲义已经变化，这个表达只保留作历史参考。', 'The script changed; this visual is kept only for reference.') }}</span>
          <button type="button" :disabled="Boolean(busyType || resolvingId)" @click="generate(item.representation_type)">
            <RotateCcw :size="14" />{{ tr('regenerate', '按当前讲义重生成', 'Regenerate from current script') }}
          </button>
        </footer>
        <p v-else-if="item.status === 'accepted'" class="accepted-note">
          <Check :size="14" />{{ tr('acceptedReuse', '已进入共享表达集，可供讲义、PPT 和学生端复用。', 'Added to the shared set for script, PPT, and learner reuse.') }}
        </p>
      </article>

      <p v-if="!loading && !displayItems.length && !errorMessage" class="script-visual-empty">
        {{ tr('empty', '选择一种方式，为这段讲义生成可审阅的视觉表达。', 'Choose a format to create a reviewable visual explanation.') }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, reactive, ref, watch } from 'vue'
import {
  Check,
  ChevronDown,
  Image as ImageIcon,
  ImageOff,
  LoaderCircle,
  Network,
  PlaySquare,
  RotateCcw,
  Shapes,
  TriangleAlert,
  X,
} from 'lucide-vue-next'
import DiagramSpecRenderer from './DiagramSpecRenderer.vue'
import StructuredScenePlayer from './StructuredScenePlayer.vue'
import { activeLocale, t } from '../shared/i18n'
import {
  type ScriptVisualItem,
  type ScriptVisualType,
  useTeacherScriptVisualStore,
} from '../stores/teacherScriptVisuals'

const props = defineProps<{
  courseId: string
  lessonUnitId: string
  scriptRevisionId: string
  sectionNodeId: string
  blockId: string
  blockTitle: string
}>()

const store = useTeacherScriptVisualStore()
const open = ref(false)
const busyType = ref<ScriptVisualType | ''>('')
const resolvingId = ref('')
const localError = ref('')
const imageUrls = reactive<Record<string, string>>({})

function tr(key: string, zh: string, en: string) {
  return t(`courseWorkbench.scriptVisual.${key}`, activeLocale.value === 'en' ? en : zh)
}

const visualOptions = computed(() => [
  { type: 'diagram' as const, label: tr('diagram', '生成图解', 'Generate diagram'), icon: markRaw(Network) },
  { type: 'image' as const, label: tr('image', '生成插图', 'Generate illustration'), icon: markRaw(ImageIcon) },
  { type: 'animation' as const, label: tr('animation', '生成动画', 'Generate animation'), icon: markRaw(PlaySquare) },
])
const view = computed(() => store.view(props.courseId, props.lessonUnitId))
const loading = computed(() => Boolean(store.loading[`${props.courseId}\u0000${props.lessonUnitId}`]))
const errorMessage = computed(() => localError.value || store.errors[`${props.courseId}\u0000${props.lessonUnitId}`] || '')
const blockItems = computed(() => (view.value?.items || []).filter(item => item.source.block_id === props.blockId))
const recommendation = computed(() => view.value?.recommendations.find(item => item.block_id === props.blockId))
const recommendationReason = computed(() => {
  const reasonCode = recommendation.value?.reason_code
  if (reasonCode === 'process_or_change') {
    return tr('reasonProcess', '这一段包含过程或变化关系，逐步呈现更容易讲清。', 'This block describes a process or change; a step-by-step view will make it easier to explain.')
  }
  if (reasonCode === 'concept_or_relation') {
    return tr('reasonConcept', '这一段包含概念或关系，适合压缩成结构图。', 'This block contains concepts or relationships that fit a compact diagram.')
  }
  if (reasonCode === 'dense_content') {
    return tr('reasonDense', '这一段信息较密，可用视觉表达降低口头解释负担。', 'This block is information-dense; a visual can reduce the explanation load.')
  }
  return recommendation.value?.reason || ''
})
const acceptedCount = computed(() => blockItems.value.filter(item => item.status === 'accepted').length)
const displayItems = computed(() => {
  const result: ScriptVisualItem[] = []
  ;(['diagram', 'image', 'animation'] as ScriptVisualType[]).forEach(type => {
    const typed = blockItems.value
      .filter(item => item.representation_type === type)
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    const candidate = typed.find(item => item.status === 'candidate')
    const accepted = typed.find(item => item.status === 'accepted')
    const stale = typed.find(item => item.status === 'stale')
    if (accepted) result.push(accepted)
    if (candidate) result.push(candidate)
    if (!accepted && !candidate && stale) result.push(stale)
  })
  return result
})

function typeLabel(type: ScriptVisualType) {
  return ({
    diagram: tr('diagramLabel', '结构图解', 'Diagram'),
    image: tr('imageLabel', '教学插图', 'Illustration'),
    animation: tr('animationLabel', '代码动画', 'Code animation'),
  })[type]
}

function statusLabel(item: ScriptVisualItem) {
  if (item.status === 'accepted') return tr('accepted', '已采用', 'Accepted')
  if (item.status === 'stale') return tr('stale', '来源已变化', 'Source changed')
  if (item.representation_type === 'image' && item.content?.generation_status === 'provider_unavailable') {
    return tr('waitingService', '等待图片服务', 'Waiting for image service')
  }
  if (item.representation_type === 'image' && item.content?.generation_status === 'provider_failed') {
    return tr('generationFailed', '生成失败', 'Generation failed')
  }
  return tr('candidate', '待审阅', 'Review')
}

function canAccept(item: ScriptVisualItem) {
  return item.representation_type !== 'image'
    || (item.content?.generation_status === 'ready' && item.artifact_ids.length > 0)
}

async function refresh(force = false) {
  localError.value = ''
  try {
    await store.load(props.courseId, props.lessonUnitId, force)
  } catch {
    // The store keeps the user-facing scoped error.
  }
}

async function generate(type: ScriptVisualType) {
  if (busyType.value || resolvingId.value) return
  busyType.value = type
  localError.value = ''
  try {
    const item = await store.create(
      props.courseId,
      props.lessonUnitId,
      props.scriptRevisionId,
      props.sectionNodeId,
      props.blockId,
      type,
    )
    open.value = true
    await loadImage(item)
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    localError.value = String(detail?.message || detail || error?.message || tr('generateFailed', '视觉表达生成失败，请重试。', 'Could not generate the visual. Try again.'))
  } finally {
    busyType.value = ''
  }
}

async function resolve(item: ScriptVisualItem, accept: boolean) {
  if (resolvingId.value) return
  resolvingId.value = item.representation_id
  localError.value = ''
  try {
    await store.resolve(
      props.courseId,
      props.lessonUnitId,
      props.scriptRevisionId,
      item.representation_id,
      accept,
    )
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    localError.value = String(detail?.message || detail || error?.message || tr('resolveFailed', '候选处理失败，请重试。', 'Could not resolve the candidate. Try again.'))
  } finally {
    resolvingId.value = ''
  }
}

async function loadImage(item: ScriptVisualItem) {
  if (item.representation_type !== 'image' || !item.artifact_ids.length) return
  try {
    imageUrls[item.representation_id] = await store.imageUrl(props.courseId, item)
  } catch {
    localError.value = tr('assetFailed', '图片读取失败，可以重新生成或稍后重试。', 'Could not load the image. Retry later or regenerate it.')
  }
}

watch(displayItems, items => { items.forEach(item => { void loadImage(item) }) }, { immediate: true })
watch(open, value => { if (value && !view.value) void refresh() })
watch(() => props.scriptRevisionId, () => { if (view.value) void refresh(true) })
</script>

<style scoped>
.script-visual-studio{margin-top:16px;border-top:1px solid #edf0f5}.script-visual-toggle{width:100%;min-height:42px;display:flex;align-items:center;gap:8px;padding:8px 0;border:0;color:#58667b;background:transparent;font:inherit;font-size:14px;font-weight:720;text-align:left;cursor:pointer}.script-visual-toggle:hover{color:#3730a3}.script-visual-toggle:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-visual-toggle small{margin-left:auto;color:#7c8798;font-size:13px;font-weight:600}.script-visual-toggle>svg:last-child{transition:transform .18s ease}.script-visual-studio[data-open='true'] .script-visual-toggle>svg:last-child{transform:rotate(180deg)}.script-visual-panel{display:grid;gap:14px;padding:2px 0 12px}.script-visual-create{display:grid;gap:8px}.script-visual-create p{margin:0;color:#667287;font-size:14px;line-height:1.5}.script-visual-create nav{display:flex;gap:7px;flex-wrap:wrap}.script-visual-create button,.script-visual-item footer button{min-height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:1px solid #d4dbe8;border-radius:7px;color:#4e5c72;background:#fff;font:inherit;font-size:14px;font-weight:700;cursor:pointer}.script-visual-create button.recommended{border-color:#b9b9ea;color:#3f3a9b;background:#f8f8ff}.script-visual-create button:hover:not(:disabled),.script-visual-item footer button:hover:not(:disabled){border-color:#9d9ce0;color:#3730a3}.script-visual-create button:focus-visible,.script-visual-item footer button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-visual-create button:disabled,.script-visual-item footer button:disabled{opacity:.45;cursor:not-allowed}.script-visual-item{display:grid;gap:12px;padding:14px;border:1px solid #e1e6ef;border-radius:10px;background:#fcfdff}.script-visual-item[data-status='candidate']{border-color:#cfd0ef;background:#fbfbff}.script-visual-item[data-status='stale']{border-style:dashed;background:#fafafa}.script-visual-item>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.script-visual-item>header strong{color:#263147;font-size:15px}.script-visual-item>header span{color:#6b778b;font-size:13px}.script-visual-item footer{display:flex;align-items:center;justify-content:flex-end;gap:7px}.script-visual-item footer button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.script-visual-item footer.stale-actions{justify-content:space-between}.stale-actions span{color:#777f8d;font-size:13px}.accepted-note{display:flex;align-items:center;gap:6px;margin:0;color:#3b6c50;font-size:13px}.script-image-preview{display:grid;gap:10px}.script-image-preview img{width:100%;max-height:420px;object-fit:contain;border-radius:8px;background:#f3f5f9}.script-image-state{min-height:128px;display:grid;place-items:center;align-content:center;gap:6px;padding:16px;border:1px dashed #d8dde8;border-radius:8px;color:#697589;background:#fff;text-align:center}.script-image-state strong{color:#37445a;font-size:15px}.script-image-state span{font-size:13px}.script-image-prompt summary{color:#59677c;font-size:13px;cursor:pointer}.script-image-prompt p{margin:7px 0 0;padding:9px;border-radius:6px;color:#586579;background:#f4f6fa;font-size:13px;line-height:1.55}.script-visual-error,.script-visual-loading,.script-visual-empty{margin:0;padding:10px 12px;border-radius:7px;font-size:14px}.script-visual-error{color:#9a3e30;background:#fff3f1}.script-visual-loading{display:flex;align-items:center;gap:7px;color:#5b6382;background:#f7f7ff}.script-visual-empty{color:#6c788b;background:#f7f8fa}.spin{animation:script-visual-spin 1s linear infinite}@keyframes script-visual-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.script-visual-toggle>svg:last-child{transition:none}}
</style>
