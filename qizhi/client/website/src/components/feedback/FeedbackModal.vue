<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="feedback-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-modal-title"
      @click.self="close"
    >
      <div class="feedback-dialog">
        <button type="button" class="feedback-close" aria-label="关闭" @click="close">
          <svg width="25" height="25" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </button>

        <div class="feedback-inner">
          <h2 id="feedback-modal-title" class="feedback-main-title">用户评价与反馈</h2>
          <div class="feedback-title-line" />

          <div class="feedback-form-block">
            <div class="feedback-section-title">评分</div>
            <div
              ref="starsTrackRef"
              class="feedback-stars"
              role="slider"
              aria-label="评分，1 至 5 星"
              aria-valuemin="0"
              aria-valuemax="5"
              :aria-valuenow="star"
              :aria-valuetext="star ? `${star} 星` : '未选择'"
              tabindex="0"
              @click="onStarsTrackClick"
              @keydown="onStarsTrackKeydown"
            >
              <span v-for="n in 5" :key="n" class="feedback-star-cell" aria-hidden="true">
                <span class="feedback-star" :class="{ on: n <= star }">★</span>
              </span>
            </div>
            <p v-if="starError" class="feedback-field-error">{{ starError }}</p>

            <div class="feedback-section-title feedback-section-title-spaced">反馈与建议</div>
            <textarea
              ref="textareaRef"
              v-model="content"
              class="feedback-textarea"
              rows="8"
              maxlength="2047"
              placeholder="在此输入您宝贵的反馈与建议……"
            />
            <p v-if="contentError" class="feedback-field-error">{{ contentError }}</p>

            <div class="feedback-section-title feedback-section-title-spaced">附件（可选）</div>
            <p class="feedback-attach-hint">
              最多 {{ maxAttachments }} 个
            </p>
            <input
              ref="fileInputRef"
              type="file"
              class="feedback-file-input"
              :accept="FEEDBACK_ATTACH_ACCEPT"
              multiple
              @change="onAttachmentFilesSelected"
            />
            <button
              type="button"
              class="feedback-attach-btn"
              :disabled="submitting || attachments.length >= maxAttachments"
              @click="triggerAttachmentPick"
            >
              选择附件
            </button>
            <div v-if="attachments.length" class="feedback-thumb-grid">
              <div v-for="(item, idx) in attachments" :key="item.id" class="feedback-thumb-wrap">
                <img v-if="item.kind === 'image'" class="feedback-thumb" :src="item.previewUrl" alt="" />
                <video
                  v-else-if="item.kind === 'video'"
                  class="feedback-thumb feedback-thumb-video"
                  :src="item.previewUrl"
                  muted
                  playsinline
                  preload="metadata"
                />
                <div v-else class="feedback-thumb feedback-file-thumb" :title="item.file.name">
                  <span class="feedback-file-label">文件</span>
                  <span class="feedback-file-name">{{ shortenFileName(item.file.name) }}</span>
                </div>
                <button
                  type="button"
                  class="feedback-thumb-remove"
                  :disabled="submitting"
                  aria-label="移除附件"
                  @click="removeAttachment(idx)"
                >
                  ×
                </button>
              </div>
            </div>
            <p v-if="attachmentError" class="feedback-field-error">{{ attachmentError }}</p>

            <button type="button" class="feedback-submit" :disabled="submitting" @click="handleSubmit">
              {{ submitting ? '提交中…' : '确认并提交' }}
            </button>
            <p v-if="message" class="feedback-message" :class="{ err: messageIsError }">{{ message }}</p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import {
  uploadAttachment,
  COMMON_ATTACHMENT_EXTENSIONS,
  isExtensionAllowed,
} from '../../api/attachment'
import { submitFeedback } from '../../api/feedback'

const maxAttachments = 5

const FEEDBACK_ATTACH_ACCEPT = [...COMMON_ATTACHMENT_EXTENSIONS, 'image/*', 'video/*'].join(',')

type FeedbackAttachKind = 'image' | 'video' | 'file'

type FeedbackAttachmentItem = {
  id: string
  file: File
  /** 图片/视频预览用 object URL；纯文件为空字符串 */
  previewUrl: string
  kind: FeedbackAttachKind
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const star = ref(0)
const content = ref('')
const submitting = ref(false)
const message = ref('')
const messageIsError = ref(false)
const starError = ref('')
const contentError = ref('')
const attachmentError = ref('')
const attachments = ref<FeedbackAttachmentItem[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const starsTrackRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function close() {
  emit('update:modelValue', false)
}

function revokeAttachmentPreviewUrls() {
  for (const im of attachments.value) {
    if (!im.previewUrl) continue
    try {
      URL.revokeObjectURL(im.previewUrl)
    } catch {
      //
    }
  }
}

function resetForm() {
  revokeAttachmentPreviewUrls()
  attachments.value = []
  star.value = 0
  content.value = ''
  message.value = ''
  messageIsError.value = false
  starError.value = ''
  contentError.value = ''
  attachmentError.value = ''
  submitting.value = false
}

let removeEscListener: (() => void) | null = null

watch(
  () => props.modelValue,
  (open) => {
    if (removeEscListener) {
      removeEscListener()
      removeEscListener = null
    }
    if (open) {
      resetForm()
      document.body.style.overflow = 'hidden'
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') close()
      }
      window.addEventListener('keydown', onKey)
      removeEscListener = () => window.removeEventListener('keydown', onKey)
    } else {
      document.body.style.overflow = ''
      resetForm()
    }
  },
)

onUnmounted(() => {
  if (removeEscListener) removeEscListener()
  document.body.style.overflow = ''
  revokeAttachmentPreviewUrls()
  attachments.value = []
})

/** 按整条轨道从左到右分段取星，避免逐星点击错位或“跳选”观感 */
function onStarsTrackClick(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const w = rect.width
  if (w <= 0) return
  const x = e.clientX - rect.left
  const segment = w / 5
  let idx = Math.floor(x / segment)
  if (idx < 0) idx = 0
  if (idx > 4) idx = 4
  star.value = idx + 1
}

/** 键盘仅每次 ±1（或 Home/End 到端点），保证分值始终为连续星级 */
function onStarsTrackKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
    e.preventDefault()
    star.value = Math.min(5, (star.value || 0) + 1)
    return
  }
  if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
    e.preventDefault()
    star.value = Math.max(0, star.value - 1)
    return
  }
  if (e.key === 'Home') {
    e.preventDefault()
    star.value = 1
    return
  }
  if (e.key === 'End') {
    e.preventDefault()
    star.value = 5
  }
}

function triggerAttachmentPick() {
  attachmentError.value = ''
  fileInputRef.value?.click()
}

function shortenFileName(name: string, max = 12): string {
  if (name.length <= max) return name
  return `${name.slice(0, max - 1)}…`
}

function onAttachmentFilesSelected(e: Event) {
  attachmentError.value = ''
  const input = e.target as HTMLInputElement
  const list = input.files
  if (!list?.length) return

  let skipped = 0
  for (const file of Array.from(list)) {
    if (attachments.value.length >= maxAttachments) {
      attachmentError.value = `最多只能上传 ${maxAttachments} 个附件`
      break
    }
    if (!isExtensionAllowed(file)) {
      skipped += 1
      continue
    }
    const kind: FeedbackAttachKind = file.type.startsWith('image/')
      ? 'image'
      : file.type.startsWith('video/')
        ? 'video'
        : 'file'
    const previewUrl =
      kind === 'image' || kind === 'video' ? URL.createObjectURL(file) : ''
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`
    attachments.value.push({
      id,
      file,
      previewUrl,
      kind,
    })
  }
  if (skipped > 0 && !attachmentError.value) {
    attachmentError.value = `已跳过 ${skipped} 个不在允许列表内的文件`
  }
  input.value = ''
}

function removeAttachment(index: number) {
  const [removed] = attachments.value.splice(index, 1)
  if (removed?.previewUrl) {
    try {
      URL.revokeObjectURL(removed.previewUrl)
    } catch {
      //
    }
  }
}

async function handleSubmit() {
  message.value = ''
  messageIsError.value = false
  starError.value = ''
  contentError.value = ''
  attachmentError.value = ''

  const s = Number(star.value)
  const c = content.value.trim()
  const starOk = Number.isFinite(s) && s >= 1 && s <= 5
  const contentOk = c.length > 0

  if (!starOk) starError.value = '请先选择评分（1–5 星）'
  if (!contentOk) contentError.value = '请填写反馈与建议后再提交'

  if (!starOk || !contentOk) {
    if (!starOk) starsTrackRef.value?.focus()
    else textareaRef.value?.focus()
    return
  }

  submitting.value = true
  try {
    const imagePaths: string[] = []
    for (const im of attachments.value) {
      imagePaths.push(await uploadAttachment(im.file))
    }
    await submitFeedback({
      star: s,
      content: c,
      image_paths: imagePaths.length > 0 ? imagePaths : undefined,
    })
    messageIsError.value = false
    message.value = '提交成功，感谢您的反馈'
    setTimeout(() => {
      close()
    }, 800)
  } catch (e) {
    messageIsError.value = true
    message.value = e instanceof Error ? e.message : '提交失败'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.feedback-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  box-sizing: border-box;
  background: rgba(30, 30, 30, 0.22);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.feedback-dialog {
  position: relative;
  box-sizing: border-box;
  width: min(536px, calc(100vw - 24px));
  max-width: calc(100vw - 24px);
  height: 650px;
  max-height: calc(100vh - 32px - env(safe-area-inset-bottom, 0px));
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.feedback-close {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  width: 50px;
  height: 50px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #555;
  cursor: pointer;
}

.feedback-close:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #222;
}

.feedback-inner {
  box-sizing: border-box;
  height: 100%;
  padding: 28px 36px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow-x: hidden;
  overflow-y: auto;
}

.feedback-main-title {
  margin: 0 0 14px;
  font-size: 18px;
  font-weight: 600;
  color: #222;
  text-align: center;
  width: 100%;
}

.feedback-title-line {
  width: 100%;
  height: 1px;
  background: rgba(117, 117, 117, 1.00);
  flex-shrink: 0;
  margin-bottom: 22px;
}

.feedback-form-block {
  width: 100%;
  max-width: 432px;
  margin: 0 auto;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.feedback-section-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 700;
  color: #222;
  text-align: left;
}

.feedback-section-title-spaced {
  margin-top: 20px;
}

.feedback-stars {
  direction: ltr;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
  padding: 6px 0;
  border-radius: 10px;
  cursor: pointer;
  outline: none;
}

.feedback-stars:focus-visible {
  box-shadow: 0 0 0 2px rgba(19, 88, 228, 0.35);
}

.feedback-star-cell {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.feedback-star {
  font-size: 36px;
  line-height: 1;
  color: #d9d9d9;
  user-select: none;
  transition: color 0.15s ease;
}

.feedback-star.on {
  color: #1358e4;
}

.feedback-textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 160px;
  padding: 10px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  background: #fff;
  font-size: 14px;
  color: #333;
  resize: vertical;
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.feedback-textarea::placeholder {
  color: #999;
}

.feedback-textarea:focus {
  border-color: #c5d9ff;
}

.feedback-field-error {
  margin: 8px 0 0;
  font-size: 12px;
  color: #b71c1c;
  text-align: left;
}

.feedback-attach-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: #666;
  text-align: left;
}

.feedback-file-input {
  display: none;
}

.feedback-attach-btn {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  background: #fff;
  font-size: 14px;
  font-weight: 500;
  color: #333;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.feedback-attach-btn:hover:not(:disabled) {
  border-color: #c5d9ff;
  background: #fafafa;
}

.feedback-attach-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.feedback-thumb-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.feedback-thumb-wrap {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.feedback-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.feedback-thumb-video {
  background: #111;
}

.feedback-file-thumb {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 4px;
  box-sizing: border-box;
  background: #f4f4f4;
  font-size: 10px;
  line-height: 1.2;
  color: #444;
  text-align: center;
}

.feedback-file-label {
  font-weight: 600;
  font-size: 11px;
  color: #1358e4;
}

.feedback-file-name {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feedback-thumb-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.feedback-thumb-remove:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.72);
}

.feedback-submit {
  box-sizing: border-box;
  width: 100%;
  margin-top: 16px;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: #c5d9ff;
  color: #000;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.feedback-submit:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.feedback-submit:not(:disabled):hover {
  filter: brightness(0.97);
}

.feedback-message {
  margin: 12px 0 0;
  font-size: 13px;
  color: #1b5e20;
  text-align: left;
}

.feedback-message.err {
  color: #b71c1c;
}

/* 移动端：抹掉桌面端的内边距与控件尺寸 */
@media (max-width: 480px) {
  .feedback-dialog {
    height: auto;
    max-height: calc(100vh - 24px - env(safe-area-inset-bottom, 0px));
    border-radius: 14px;
  }
  .feedback-inner {
    padding: 20px 16px 20px;
  }
  .feedback-close {
    top: 8px;
    right: 8px;
    width: 40px;
    height: 40px;
  }
  .feedback-main-title {
    font-size: 16px;
  }
}
</style>
