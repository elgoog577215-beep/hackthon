<template>
  <Teleport to="body">
    <div
      v-if="modelValue && attachments.length > 0"
      class="al-overlay"
      role="dialog"
      aria-modal="true"
      @click.self="close"
      @keydown.esc="close"
      tabindex="0"
      ref="overlayRef"
    >
      <button type="button" class="al-close" aria-label="关闭" @click="close">×</button>

      <button
        v-if="attachments.length > 1"
        type="button"
        class="al-nav al-nav-prev"
        aria-label="上一个"
        :disabled="currentIndex <= 0"
        @click="goPrev"
      >
        ‹
      </button>

      <div class="al-stage" @click.self="close">
        <img
          v-if="currentKind === 'image'"
          :src="currentUrl"
          :alt="currentFilename"
          class="al-media"
        />
        <video
          v-else-if="currentKind === 'video'"
          :src="currentUrl"
          class="al-media"
          controls
          preload="metadata"
        />
        <div v-else class="al-file">
          <div class="al-file-icon">📄</div>
          <div class="al-file-name">{{ currentFilename }}</div>
          <div class="al-file-hint">该文件类型无法预览，请下载查看</div>
        </div>
      </div>

      <button
        v-if="attachments.length > 1"
        type="button"
        class="al-nav al-nav-next"
        aria-label="下一个"
        :disabled="currentIndex >= attachments.length - 1"
        @click="goNext"
      >
        ›
      </button>

      <div class="al-toolbar">
        <span class="al-counter" v-if="attachments.length > 1">
          {{ currentIndex + 1 }} / {{ attachments.length }}
        </span>
        <a
          :href="currentUrl"
          :download="currentFilename"
          class="al-download"
          target="_blank"
          rel="noopener noreferrer"
        >
          下载
        </a>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { buildApiFullUrl } from '../api/request'

type AttachmentKind = 'image' | 'video' | 'other'

const props = defineProps<{
  modelValue: boolean
  attachments: string[]
  initialIndex?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const overlayRef = ref<HTMLElement | null>(null)
const currentIndex = ref(0)

watch(
  () => [props.modelValue, props.initialIndex] as const,
  ([open, idx]) => {
    if (open) {
      const safeIdx = typeof idx === 'number' ? idx : 0
      currentIndex.value = Math.max(0, Math.min(safeIdx, props.attachments.length - 1))
      nextTick(() => overlayRef.value?.focus())
    }
  },
  { immediate: true },
)

const currentPath = computed(() => props.attachments[currentIndex.value] ?? '')
const currentUrl = computed(() => resolveAttachmentUrl(currentPath.value))
const currentFilename = computed(() => extractFilename(currentPath.value))
const currentKind = computed<AttachmentKind>(() => detectKind(currentPath.value))

function close() {
  emit('update:modelValue', false)
}

function goPrev() {
  if (currentIndex.value > 0) currentIndex.value -= 1
}

function goNext() {
  if (currentIndex.value < props.attachments.length - 1) currentIndex.value += 1
}

function resolveAttachmentUrl(rawPath: string): string {
  const raw = (rawPath ?? '').trim()
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) return raw
  let normalized = raw
  if (!normalized.startsWith('/static/')) {
    const idx = normalized.indexOf('uploads/')
    if (idx >= 0) normalized = `/static/${normalized.slice(idx + 'uploads/'.length)}`
    else if (!normalized.startsWith('/')) normalized = `/${normalized}`
  }
  return buildApiFullUrl(normalized)
}

function extractFilename(path: string): string {
  const raw = (path ?? '').trim()
  if (!raw) return ''
  const seg = raw.split(/[\\/]/).pop() ?? raw
  return seg.split('?')[0] ?? seg
}

function detectKind(path: string): AttachmentKind {
  const ext = extractFilename(path).split('.').pop()?.toLowerCase() ?? ''
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image'
  if (['mp4', 'webm', 'mov', 'm4v', 'ogv'].includes(ext)) return 'video'
  return 'other'
}
</script>

<style scoped>
.al-overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 14, 30, 0.85);
  z-index: 1200;
  display: grid;
  grid-template-columns: 64px 1fr 64px;
  grid-template-rows: 1fr auto;
  align-items: center;
  justify-items: center;
  outline: none;
}

.al-close {
  position: absolute;
  top: 16px;
  right: 20px;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.al-close:hover {
  background: rgba(255, 255, 255, 0.24);
}

.al-stage {
  grid-column: 2;
  grid-row: 1;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  box-sizing: border-box;
}

.al-media {
  max-width: 100%;
  max-height: calc(100vh - 140px);
  border-radius: 8px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
  background: #000;
}

.al-file {
  background: rgba(255, 255, 255, 0.95);
  color: #1a2540;
  padding: 36px 48px;
  border-radius: 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  min-width: 280px;
}

.al-file-icon {
  font-size: 48px;
}

.al-file-name {
  font-size: 16px;
  font-weight: 600;
  word-break: break-all;
}

.al-file-hint {
  font-size: 13px;
  color: #6b7080;
}

.al-nav {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: none;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  font-size: 26px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.al-nav:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.al-nav:not(:disabled):hover {
  background: rgba(255, 255, 255, 0.28);
}

.al-nav-prev {
  grid-column: 1;
  grid-row: 1;
}

.al-nav-next {
  grid-column: 3;
  grid-row: 1;
}

.al-toolbar {
  grid-column: 1 / -1;
  grid-row: 2;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
  color: #fff;
}

.al-counter {
  font-size: 13px;
  letter-spacing: 0.5px;
  opacity: 0.8;
}

.al-download {
  padding: 8px 18px;
  background: #2f4aa6;
  color: #fff;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
}

.al-download:hover {
  background: #243a85;
}
</style>
