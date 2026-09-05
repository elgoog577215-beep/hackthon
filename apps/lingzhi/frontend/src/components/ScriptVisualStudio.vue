<template>
  <section class="script-visual-studio">
    <figure
      v-for="item in acceptedItems"
      :key="item.representation_id"
      class="script-visual-inline"
      :data-type="item.representation_type"
    >
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
        <div v-else class="script-image-state">
          <LoaderCircle :size="18" class="spin" />
          <span>{{ tr('assetLoading', '正在读取图片…', 'Loading image…') }}</span>
        </div>
      </div>
      <figcaption>{{ acceptedCaption(item) }}</figcaption>
    </figure>

    <div class="script-visual-tools">
      <div class="script-visual-create">
        <p v-if="recommendationReason && !acceptedItems.length">{{ recommendationReason }}</p>
        <nav :aria-label="tr('createLabel', '插入图解或图片', 'Insert a diagram or illustration')">
          <button
            v-for="option in visualOptions"
            :key="option.type"
            type="button"
            :class="{ recommended: recommendation?.recommended_types.includes(option.type) }"
            :disabled="Boolean(loading || busyType || resolvingId)"
            @click="generate(option.type)"
          >
            <LoaderCircle v-if="busyType === option.type" :size="15" class="spin" />
            <component :is="option.icon" v-else :size="15" />
            {{ visualActionLabel(option.type) }}
          </button>
        </nav>
      </div>

      <p v-if="errorMessage" class="script-visual-error" role="alert">{{ errorMessage }}</p>
      <p v-else-if="loading && !blockItems.length" class="script-visual-loading">
        <LoaderCircle :size="15" class="spin" />{{ tr('loading', '正在读取视觉表达…', 'Loading visual explanations…') }}
      </p>

      <article
        v-for="item in reviewItems"
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
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, reactive, ref, watch } from 'vue'
import {
  Check,
  Image as ImageIcon,
  ImageOff,
  LoaderCircle,
  Network,
  PlaySquare,
  RotateCcw,
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
const busyType = ref<ScriptVisualType | ''>('')
const resolvingId = ref('')
const localError = ref('')
const imageUrls = reactive<Record<string, string>>({})

function tr(key: string, zh: string, en: string) {
  return t(`courseWorkbench.scriptVisual.${key}`, activeLocale.value === 'en' ? en : zh)
}

const visualOptions = computed(() => [
  { type: 'diagram' as const, icon: markRaw(Network) },
  { type: 'image' as const, icon: markRaw(ImageIcon) },
  { type: 'animation' as const, icon: markRaw(PlaySquare) },
].filter(option => (view.value?.available_types || ['diagram', 'image']).includes(option.type)))
const view = computed(() => store.view(props.courseId, props.lessonUnitId))
const loading = computed(() => Boolean(store.loading[`${props.courseId}\u0000${props.lessonUnitId}`]))
const errorMessage = computed(() => localError.value || store.errors[`${props.courseId}\u0000${props.lessonUnitId}`] || '')
const blockItems = computed(() => (view.value?.items || []).filter(item => item.source.block_id === props.blockId))
const recommendation = computed(() => view.value?.recommendations.find(item => item.block_id === props.blockId))
const recommendationReason = computed(() => {
  const reasonCode = recommendation.value?.reason_code
  if (reasonCode === 'process_or_change') {
    return tr('reasonProcess', '这一段包含公式、概念或过程关系，适合用结构图解讲清。', 'This block contains formulas, concepts, or process relationships that fit a structured diagram.')
  }
  if (reasonCode === 'concept_or_relation') {
    return tr('reasonConcept', '这一段包含概念或关系，适合压缩成结构图。', 'This block contains concepts or relationships that fit a compact diagram.')
  }
  if (reasonCode === 'dense_content') {
    return tr('reasonDense', '这一段信息较密，可用视觉表达降低口头解释负担。', 'This block is information-dense; a visual can reduce the explanation load.')
  }
  if (reasonCode === 'ai_illustration_scene') {
    return tr('reasonImageScene', '这一段包含人物或场景，可适当加入 AI 插图帮助联想。', 'This block contains a person or scene that may benefit from an AI illustration.')
  }
  if (reasonCode === 'relation_and_scene') {
    return tr('reasonRelationScene', '这一段既有知识关系，也有适合形象化呈现的人物或场景。', 'This block contains both knowledge relationships and a scene worth visualizing.')
  }
  return recommendation.value?.reason || ''
})
const displayItems = computed(() => {
  const result: ScriptVisualItem[] = []
  ;(view.value?.available_types || ['diagram', 'image']).forEach(type => {
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
const acceptedItems = computed(() => displayItems.value.filter(item => item.status === 'accepted'))
const reviewItems = computed(() => displayItems.value.filter(item => item.status !== 'accepted'))

function acceptedCaption(item: ScriptVisualItem) {
  const title = String(item.content?.title || props.blockTitle)
  if (item.representation_type === 'image') {
    const provenance = String(item.content?.provenance_label || tr('aiGenerated', 'AI 生成插图', 'AI-generated illustration'))
    return `${provenance} · ${title}`
  }
  return title
}

function visualActionLabel(type: ScriptVisualType) {
  const replacing = acceptedItems.value.some(item => item.representation_type === type)
  if (type === 'diagram') {
    return replacing
      ? tr('updateDiagram', '更新图解', 'Update diagram')
      : tr('insertDiagram', '插入图解', 'Insert diagram')
  }
  if (type === 'image') {
    return replacing
      ? tr('updateImage', '更新 AI 插图', 'Update AI illustration')
      : tr('insertImage', '插入 AI 插图', 'Insert AI illustration')
  }
  return replacing
    ? tr('updateAnimation', '更新动画', 'Update animation')
    : tr('insertAnimation', '插入动画', 'Insert animation')
}

function typeLabel(type: ScriptVisualType) {
  return ({
    diagram: tr('diagramLabel', '结构图解', 'Diagram'),
    image: tr('imageLabel', 'AI 插图', 'AI illustration'),
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
</script>

<style scoped>
.script-visual-studio{display:grid;gap:12px;margin-top:20px}.script-visual-inline{display:grid;gap:7px;margin:0}.script-visual-inline figcaption{color:#667287;font-size:13px;line-height:1.5}.script-visual-tools{display:grid;gap:10px}.script-visual-create{display:grid;gap:7px}.script-visual-create p{margin:0;color:#667287;font-size:14px;line-height:1.5}.script-visual-create nav{display:flex;gap:7px;flex-wrap:wrap}.script-visual-create button,.script-visual-item footer button{min-height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:1px solid #d4dbe8;border-radius:7px;color:#4e5c72;background:#fff;font:inherit;font-size:14px;font-weight:700;cursor:pointer}.script-visual-create button.recommended{border-color:#b9b9ea;color:#3f3a9b;background:#f8f8ff}.script-visual-create button:hover:not(:disabled),.script-visual-item footer button:hover:not(:disabled){border-color:#9d9ce0;color:#3730a3}.script-visual-create button:focus-visible,.script-visual-item footer button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.script-visual-create button:disabled,.script-visual-item footer button:disabled{opacity:.45;cursor:not-allowed}.script-visual-item{display:grid;gap:12px;padding:14px;border:1px solid #e1e6ef;border-radius:10px;background:#fcfdff}.script-visual-item[data-status='candidate']{border-color:#cfd0ef;background:#fbfbff}.script-visual-item[data-status='stale']{border-style:dashed;background:#fafafa}.script-visual-item>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.script-visual-item>header strong{color:#263147;font-size:15px}.script-visual-item>header span{color:#6b778b;font-size:13px}.script-visual-item footer{display:flex;align-items:center;justify-content:flex-end;gap:7px}.script-visual-item footer button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.script-visual-item footer.stale-actions{justify-content:space-between}.stale-actions span{color:#777f8d;font-size:13px}.script-image-preview{display:grid;gap:10px}.script-image-preview img{width:100%;max-height:420px;object-fit:contain;border-radius:8px;background:#f3f5f9}.script-image-state{min-height:128px;display:grid;place-items:center;align-content:center;gap:6px;padding:16px;border:1px dashed #d8dde8;border-radius:8px;color:#697589;background:#fff;text-align:center}.script-image-state strong{color:#37445a;font-size:15px}.script-image-state span{font-size:13px}.script-image-prompt summary{color:#59677c;font-size:13px;cursor:pointer}.script-image-prompt p{margin:7px 0 0;padding:9px;border-radius:6px;color:#586579;background:#f4f6fa;font-size:13px;line-height:1.55}.script-visual-error,.script-visual-loading{margin:0;padding:10px 12px;border-radius:7px;font-size:14px}.script-visual-error{color:#9a3e30;background:#fff3f1}.script-visual-loading{display:flex;align-items:center;gap:7px;color:#5b6382;background:#f7f7ff}.spin{animation:script-visual-spin 1s linear infinite}@keyframes script-visual-spin{to{transform:rotate(360deg)}}
</style>
