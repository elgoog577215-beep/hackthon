<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="local-video-modal-overlay"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <Transition name="upload-drop-fade">
        <div
          v-if="dragOverActive && !submitting"
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
            <p class="upload-drop-text">将视频释放至此处以上传</p>
          </div>
        </div>
      </Transition>

      <div
        class="local-video-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="local-video-modal-title"
        @click.stop
      >
        <div class="modal-header">
          <h3 id="local-video-modal-title">本地视频分析</h3>
          <button
            type="button"
            class="modal-close"
            :aria-label="submitting ? '取消上传并关闭' : '关闭'"
            @click="requestClose"
          >
            &times;
          </button>
        </div>

        <div class="modal-body">
          <input
            ref="videoFileInputRef"
            type="file"
            accept="video/*,.mp4,.webm,.mov,.mkv,.avi,.m4v"
            class="file-input-hidden"
            @change="onVideoFileChange"
          />

          <div class="form-row">
            <label>选择视频文件 <span class="required">*</span></label>
            <button
              type="button"
              class="video-upload-zone"
              :class="{ 'has-file': !!videoFile, 'is-uploading': submitting }"
              :disabled="submitting"
              @click="triggerVideoFileSelect"
            >
              <span v-if="submitting" class="video-upload-spinner" aria-hidden="true"></span>
              <svg
                v-else
                class="video-upload-icon"
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
              <span class="video-upload-title">
                {{
                  submitting
                    ? '上传中…'
                    : videoFile
                      ? '重新选择视频'
                      : '点击或拖拽上传本地视频'
                }}
              </span>
              <span v-if="videoFile && !submitting" class="video-upload-file">
                {{ videoFile.name }}（{{ formatFileSize(videoFile.size) }}）
              </span>
              <span v-else-if="!submitting" class="video-upload-sub">支持 MP4、WebM、MOV 等常见格式</span>
            </button>
          </div>

          <div class="form-row">
            <label>视频名称 <span class="required">*</span></label>
            <input
              v-model.trim="videoName"
              type="text"
              class="form-input"
              placeholder="请输入视频名称"
              :disabled="submitting"
            />
          </div>

          <div v-if="uploadingVideo" class="upload-progress">
            <div class="upload-progress-bar">
              <div class="upload-progress-inner" :style="{ width: `${uploadPercent}%` }"></div>
            </div>
            <p class="upload-progress-text">正在上传视频 {{ uploadPercent }}%</p>
          </div>

          <p v-if="submitError" class="form-error">{{ submitError }}</p>
        </div>

        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="requestClose">
            {{ submitting ? '取消上传' : '取消' }}
          </button>
          <button
            type="button"
            class="action-btn primary"
            :disabled="!canSubmit || submitting"
            @click="handleSubmit"
          >
            {{ submitting ? '上传中...' : '上传并预览' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { submitVideo, registerUploadedVideoTask } from '../api/video'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submitted', taskId: string): void
}>()

const videoFile = ref<File | null>(null)
const videoFileInputRef = ref<HTMLInputElement | null>(null)
const videoName = ref('')
const submitting = ref(false)
const submitError = ref('')
const uploadPercent = ref(0)
const uploadingVideo = ref(false)
/** 进行中上传的中断控制器；取消/关闭时 abort 以停止分片上传 */
let uploadController: AbortController | null = null

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}
const dragDepth = ref(0)
const dragOverActive = computed(() => dragDepth.value > 0)

const canSubmit = computed(() => !!(videoFile.value && videoName.value.trim()))

function resetForm() {
  videoFile.value = null
  videoName.value = ''
  submitError.value = ''
  uploadPercent.value = 0
  uploadingVideo.value = false
  if (videoFileInputRef.value) videoFileInputRef.value.value = ''
}

function resetDragDepth() {
  dragDepth.value = 0
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isVideoFile(file: File): boolean {
  if (file.type.startsWith('video/')) return true
  return /\.(mp4|webm|mov|mkv|avi|m4v)$/i.test(file.name)
}

function isFileDragEvent(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  if (!types) return false
  return Array.from(types).includes('Files')
}

function onDragEnter(event: DragEvent) {
  if (!props.visible || !isFileDragEvent(event) || submitting.value) return
  dragDepth.value += 1
}

function onDragOver(event: DragEvent) {
  if (!props.visible || !isFileDragEvent(event) || submitting.value) return
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function onDragLeave(event: DragEvent) {
  if (!props.visible || !isFileDragEvent(event)) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
}

async function onDrop(event: DragEvent) {
  dragDepth.value = 0
  if (!props.visible || submitting.value) return
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  applyVideoFile(file)
}

function applyVideoFile(file: File) {
  if (!isVideoFile(file)) {
    submitError.value = '请选择视频文件（如 MP4、WebM、MOV 等）'
    return
  }
  submitError.value = ''
  videoFile.value = file
  if (!videoName.value.trim()) {
    videoName.value = file.name.replace(/\.[^.]+$/, '')
  }
}

function triggerVideoFileSelect() {
  if (submitting.value) return
  videoFileInputRef.value?.click()
}

function onVideoFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  applyVideoFile(file)
}

/** 关闭入口：上传进行中则中断上传后再关闭，否则直接关闭 */
function requestClose() {
  if (submitting.value) {
    cancelUpload()
    return
  }
  emit('close')
}

/** 中断进行中的上传并关闭弹窗（已上传分片由后端作为临时文件留存，不影响后续重传） */
function cancelUpload() {
  uploadController?.abort()
  emit('close')
}

async function handleSubmit() {
  if (!canSubmit.value || submitting.value) return
  const controller = new AbortController()
  uploadController = controller
  submitting.value = true
  submitError.value = ''
  uploadPercent.value = 0
  uploadingVideo.value = true
  try {
    const result = await submitVideo({
      file: videoFile.value!,
      videoName: videoName.value.trim(),
      signal: controller.signal,
      onUploadProgress: ({ uploadedChunks, totalChunks }) => {
        uploadPercent.value = Math.round((uploadedChunks / totalChunks) * 100)
      },
    })
    // 取消与「最后一个请求恰好完成」存在竞态：abort 只能中断在途请求，若 create 已返回则 submitVideo 仍会成功。
    // 此处以组件为准复检取消意图，避免用户已点取消却仍被登记任务并跳转到报告页。
    if (controller.signal.aborted || uploadController !== controller) return
    registerUploadedVideoTask({
      taskId: result.taskId,
      videoName: videoName.value.trim(),
      coverPath: result.coverPath,
    })
    emit('submitted', result.taskId)
    emit('close')
  } catch (e) {
    // 用户主动取消（abort）不算失败，弹窗已在 cancelUpload 中关闭，无需提示
    if (isAbortError(e)) return
    console.error('[LocalVideoAnalysisModal] 提交视频失败', e)
    submitError.value = e instanceof Error ? e.message : '上传失败，请稍后重试'
  } finally {
    if (uploadController === controller) uploadController = null
    submitting.value = false
    uploadingVideo.value = false
  }
}

watch(
  () => props.visible,
  (open) => {
    if (!open) {
      // 兜底：若弹窗被外部关闭时仍在上传，一并中断，避免后台请求悬挂
      uploadController?.abort()
      resetForm()
      resetDragDepth()
    }
  }
)

onMounted(() => {
  window.addEventListener('dragend', resetDragDepth)
})

onBeforeUnmount(() => {
  window.removeEventListener('dragend', resetDragDepth)
})
</script>

<style scoped>
.local-video-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal-overlay, 1200);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  box-sizing: border-box;
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.upload-drop-overlay {
  position: fixed;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  border: 2px dashed rgba(61, 81, 227, 0.55);
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

.local-video-modal {
  position: relative;
  z-index: 2;
  background: #fff;
  border-radius: 12px;
  width: min(480px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111;
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

.modal-close:hover:not(:disabled) {
  color: #333;
}

.modal-close:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
  flex-shrink: 0;
}

.form-row {
  margin-bottom: 16px;
}

.form-row label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #c62828;
}

.file-input-hidden {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.video-upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 28px 20px;
  border: 2px dashed #c8d4f0;
  border-radius: 12px;
  background: #fafbff;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  font: inherit;
  color: inherit;
  box-sizing: border-box;
}

.video-upload-zone:hover:not(:disabled) {
  border-color: #3d51e3;
  background: #f0f4ff;
}

.video-upload-zone.has-file {
  border-color: #a8b8e8;
}

.video-upload-zone:disabled {
  cursor: not-allowed;
  opacity: 0.9;
}

.video-upload-icon {
  color: #3d51e3;
}

.video-upload-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e6f5;
  border-top-color: #3d51e3;
  border-radius: 50%;
  animation: video-upload-spin 0.75s linear infinite;
}

@keyframes video-upload-spin {
  to {
    transform: rotate(360deg);
  }
}

.video-upload-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.video-upload-file,
.video-upload-sub {
  font-size: 13px;
  color: #666;
  text-align: center;
  word-break: break-all;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: #3d51e3;
}

.form-input:disabled {
  background: #f5f5f5;
}

.upload-progress {
  margin: 4px 0 8px;
}

.upload-progress-bar {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: #f0f0f0;
  overflow: hidden;
  margin-bottom: 4px;
}

.upload-progress-inner {
  height: 100%;
  background: #3d51e3;
  transition: width 0.2s ease;
}

.upload-progress-text {
  font-size: 12px;
  color: #666;
  margin: 0;
}

.form-error {
  margin: 0;
  font-size: 13px;
  color: #c62828;
}

.action-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #e0e0e0;
  background: #fff;
  color: #333;
}

.action-btn:hover:not(:disabled) {
  border-color: #c5d9ff;
  background: #f8f9ff;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.secondary {
  background: #f5f5f5;
}

.action-btn.primary {
  background: #000;
  border-color: #000;
  color: #fff;
}

.action-btn.primary:hover:not(:disabled) {
  background: #333;
  border-color: #333;
}
</style>
