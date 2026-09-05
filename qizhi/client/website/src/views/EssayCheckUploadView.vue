<template>
  <div class="essay-check-upload-view">
    <div class="toolbar">
      <div class="toolbar-left">
        <router-link to="/essay-check" class="back-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回列表</span>
        </router-link>
        <h2 class="page-title">{{ isUploading || isComplete ? '批量上传论文' : '上传论文' }}</h2>
      </div>
    </div>

    <div class="content-area">
      <!-- 选择阶段 -->
      <div v-if="!isUploading && !isComplete" class="form-area">
        <div class="form-panel">
          <div class="form-row">
            <label>选择论文PDF文件 <span class="required">*</span></label>
            <div class="file-row">
              <input
                ref="fileInputRef"
                type="file"
                accept=".pdf"
                multiple
                class="file-input-hidden"
                @change="onFileChange"
              />
              <button type="button" class="file-trigger-btn" @click="triggerFileSelect">
                {{ fileItems.length > 0 ? '重新选择' : '选择PDF文件' }}
              </button>
              <span v-if="fileItems.length > 0" class="file-name">{{ fileItems.length }} 个文件</span>
            </div>
            <p class="form-hint">支持 PDF 格式，可多选，每个文件最多 200 页</p>
          </div>

          <!-- 文件列表预览 -->
          <div v-if="fileItems.length > 0" class="file-list-preview">
            <div class="preview-title">已选择文件：</div>
            <div
              v-for="(item, idx) in fileItems"
              :key="idx"
              class="preview-item"
            >
              <span class="preview-index">{{ idx + 1 }}</span>
              <span class="preview-name" :title="item.name">{{ item.name }}</span>
              <span class="preview-size">{{ formatFileSize(item.size) }}</span>
              <button type="button" class="preview-remove" @click="removeFile(idx)" title="移除">x</button>
            </div>
          </div>

          <p v-if="submitError" class="form-error">{{ submitError }}</p>

          <div class="form-actions">
            <router-link to="/essay-check" class="action-btn secondary">返回</router-link>
            <button
              type="button"
              class="action-btn primary"
              :disabled="!canSubmit"
              @click="handleSubmit"
            >
              开始上传 ({{ fileItems.length }} 个文件)
            </button>
          </div>
        </div>
      </div>

      <!-- 上传中阶段 -->
      <div v-if="isUploading" class="upload-area">
        <!-- 总进度 -->
        <div class="summary-card">
          <h3>上传进度</h3>
          <div class="total-progress">
            <div class="total-progress-bar">
              <div class="total-progress-inner" :style="{ width: `${totalProgress}%` }"></div>
            </div>
            <span class="total-progress-text">{{ completedCount }} / {{ fileItems.length }} 已完成</span>
          </div>
        </div>

        <!-- 文件卡片列表 -->
        <div class="file-cards">
          <div
            v-for="(item, idx) in fileItems"
            :key="idx"
            class="file-card"
            :class="'status-' + item.status"
          >
            <div class="file-card-header">
              <span class="file-card-index">{{ idx + 1 }}</span>
              <span class="file-card-name" :title="item.name">{{ item.name }}</span>
              <span class="file-card-status-tag" :class="'tag-' + item.status">
                {{ statusLabel(item.status) }}
              </span>
            </div>
            <div v-if="item.status === 'uploading'" class="file-card-progress">
              <div class="file-card-progress-bar">
                <div class="file-card-progress-inner" :style="{ width: `${item.progress}%` }"></div>
              </div>
              <span class="file-card-progress-text">{{ item.progress }}%</span>
            </div>
            <div v-if="item.status === 'failed'" class="file-card-error">
              {{ item.error }}
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="upload-actions">
          <button
            type="button"
            class="action-btn danger"
            @click="handleCancel"
          >
            取消上传
          </button>
        </div>
      </div>

      <!-- 完成阶段 -->
      <div v-if="isComplete" class="complete-area">
        <div class="summary-card complete-card">
          <div class="complete-icon">
            <svg v-if="failedCount === 0" width="48" height="48" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#67c23a" stroke-width="2"/>
              <path d="M8 12l3 3 5-5" stroke="#67c23a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg v-else-if="successCount === 0" width="48" height="48" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#f56c6c" stroke-width="2"/>
              <path d="M15 9l-6 6M9 9l6 6" stroke="#f56c6c" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <svg v-else width="48" height="48" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#e6a23c" stroke-width="2"/>
              <path d="M12 8v4M12 16h.01" stroke="#e6a23c" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3>上传完成</h3>
          <div class="complete-stats">
            <span class="stat stat-success">成功 {{ successCount }} 个</span>
            <span v-if="failedCount > 0" class="stat stat-fail">失败 {{ failedCount }} 个</span>
          </div>

          <!-- 失败文件详情 -->
          <div v-if="failedCount > 0" class="failed-list">
            <h4>失败文件：</h4>
            <div
              v-for="(item, idx) in failedItems"
              :key="idx"
              class="failed-item"
            >
              <span class="failed-name">{{ item.name }}</span>
              <span class="failed-reason">{{ item.error }}</span>
            </div>
          </div>
        </div>

        <div class="complete-actions">
          <router-link to="/essay-check" class="action-btn primary">返回列表</router-link>
          <button type="button" class="action-btn secondary" @click="handleReset">继续上传</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { uploadEssay } from '../api/essayCheck'

interface FileItem {
  file: File
  name: string
  size: number
  status: 'waiting' | 'uploading' | 'uploaded' | 'failed'
  taskId: string | null
  error: string | null
  progress: number
}

const router = useRouter()
const fileItems = ref<FileItem[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const submitError = ref('')
const isUploading = ref(false)
const isComplete = ref(false)
const isCancelled = ref(false)

const canSubmit = computed(() => fileItems.value.length > 0)
const completedCount = computed(() => fileItems.value.filter((f: FileItem) => f.status === 'uploaded' || f.status === 'failed').length)
const successCount = computed(() => fileItems.value.filter((f: FileItem) => f.status === 'uploaded').length)
const failedCount = computed(() => fileItems.value.filter((f: FileItem) => f.status === 'failed').length)
const failedItems = computed(() => fileItems.value.filter((f: FileItem) => f.status === 'failed'))
const totalProgress = computed(() => {
  if (fileItems.value.length === 0) return 0
  return Math.round((completedCount.value / fileItems.value.length) * 100)
})

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    waiting: '等待中',
    uploading: '上传中',
    uploaded: '已上传',
    failed: '失败',
  }
  return map[status] ?? status
}

function triggerFileSelect() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length === 0) return

  fileItems.value = files.map(f => ({
    file: f,
    name: f.name,
    size: f.size,
    status: 'waiting' as const,
    taskId: null,
    error: null,
    progress: 0,
  }))
  submitError.value = ''
}

function removeFile(idx: number) {
  fileItems.value.splice(idx, 1)
  if (fileItems.value.length === 0 && fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

async function handleSubmit() {
  if (fileItems.value.length === 0) return

  isUploading.value = true
  isComplete.value = false
  submitError.value = ''
  isCancelled.value = false

  for (let i = 0; i < fileItems.value.length; i++) {
    if (isCancelled.value) {
      // 取消后，将剩余 waiting 状态标记为 failed
      for (let j = i; j < fileItems.value.length; j++) {
        const remaining = fileItems.value[j]!
        if (remaining.status === 'waiting') {
          remaining.status = 'failed'
          remaining.error = '已取消'
        }
      }
      break
    }

    const item = fileItems.value[i]!
    item.status = 'uploading'
    item.progress = 0

    // 模拟上传进度
    const progressInterval = setInterval(() => {
      if (item.progress < 90) {
        item.progress += 1
      }
    }, 200)

    try {
      const resp = await uploadEssay(item.file)
      clearInterval(progressInterval)
      item.progress = 100
      item.status = 'uploaded'
      item.taskId = resp.data
    } catch (e: unknown) {
      clearInterval(progressInterval)
      item.status = 'failed'
      item.error = e instanceof Error ? e.message : '上传失败'
      item.progress = 0
    }
  }

  isUploading.value = false
  isComplete.value = true
}

function handleCancel() {
  isCancelled.value = true
}

function handleReset() {
  fileItems.value = []
  isComplete.value = false
  isUploading.value = false
  submitError.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}
</script>

<style scoped>
.essay-check-upload-view {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
}

.toolbar {
  background-color: transparent;
  padding: 16px 24px;
  padding-left: 102px;
  display: flex;
  align-items: center;
  box-shadow: none;
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: #333;
  font-size: 14px;
  text-decoration: none;
  transition: color 0.2s;
  border-radius: 4px;
}
.back-btn:hover { color: #C5D9FF; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.content-area { flex: 1; padding: 24px; overflow-y: auto; }

/* 选择阶段 */
.form-area { max-width: 600px; margin: 0 auto; }
.form-panel {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.form-row { margin-bottom: 20px; }
.form-row label { display: block; font-size: 14px; font-weight: 500; color: #333; margin-bottom: 8px; }
.required { color: #c62828; }
.file-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.file-input-hidden { display: none; }
.file-trigger-btn {
  padding: 8px 16px;
  background: #C5D9FF;
  color: #333;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
.file-trigger-btn:hover { background: #b0caff; }
.file-name { font-size: 14px; color: #666; }
.form-hint { font-size: 12px; color: #999; margin: 8px 0 0 0; }
.form-error { color: #c62828; font-size: 14px; margin: 0 0 12px 0; }
.form-actions { display: flex; gap: 12px; margin-top: 24px; }

/* 文件预览 */
.file-list-preview {
  margin-top: 16px;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px 16px;
}
.preview-title {
  font-size: 13px;
  font-weight: 500;
  color: #666;
  margin-bottom: 8px;
}
.preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}
.preview-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #C5D9FF;
  color: #333;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.preview-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}
.preview-size { color: #999; flex-shrink: 0; }
.preview-remove {
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: #999;
  cursor: pointer;
  font-size: 14px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.preview-remove:hover { background: #fdecea; color: #c0392b; }

/* 上传中阶段 */
.upload-area {
  max-width: 600px;
  margin: 0 auto;
}
.summary-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 20px;
}
.summary-card h3 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 16px 0;
}
.total-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}
.total-progress-bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: #f0f0f0;
  overflow: hidden;
}
.total-progress-inner {
  height: 100%;
  background: linear-gradient(90deg, #C5D9FF, #8ab4ff);
  transition: width 0.3s ease;
  border-radius: 999px;
}
.total-progress-text {
  font-size: 13px;
  font-weight: 500;
  color: #666;
  white-space: nowrap;
}

/* 文件卡片 */
.file-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
.file-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  border-left: 4px solid #e0e0e0;
}
.file-card.status-uploading { border-left-color: #409eff; }
.file-card.status-uploaded { border-left-color: #67c23a; }
.file-card.status-failed { border-left-color: #f56c6c; }

.file-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.file-card-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f0f0f0;
  color: #666;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.file-card.status-uploading .file-card-index { background: #e6f0ff; color: #409eff; }
.file-card.status-uploaded .file-card-index { background: #e8f5e9; color: #67c23a; }
.file-card.status-failed .file-card-index { background: #fdecea; color: #f56c6c; }

.file-card-name {
  flex: 1;
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-card-status-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.tag-waiting { background: #f0f0f0; color: #999; }
.tag-uploading { background: #e6f0ff; color: #409eff; }
.tag-uploaded { background: #e8f5e9; color: #67c23a; }
.tag-failed { background: #fdecea; color: #f56c6c; }

.file-card-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.file-card-progress-bar {
  flex: 1;
  height: 4px;
  border-radius: 999px;
  background: #f0f0f0;
  overflow: hidden;
}
.file-card-progress-inner {
  height: 100%;
  background: #409eff;
  transition: width 0.2s ease;
  border-radius: 999px;
}
.file-card-progress-text {
  font-size: 12px;
  color: #999;
  min-width: 36px;
  text-align: right;
}
.file-card-error {
  margin-top: 6px;
  font-size: 12px;
  color: #f56c6c;
}

.upload-actions {
  display: flex;
  justify-content: center;
}

/* 完成阶段 */
.complete-area {
  max-width: 600px;
  margin: 0 auto;
}
.complete-card {
  text-align: center;
}
.complete-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}
.complete-stats {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
}
.stat {
  font-size: 14px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 6px;
}
.stat-success { background: #e8f5e9; color: #67c23a; }
.stat-fail { background: #fdecea; color: #f56c6c; }

.failed-list {
  margin-top: 20px;
  text-align: left;
  background: #fdf6ec;
  border-radius: 8px;
  padding: 12px 16px;
}
.failed-list h4 {
  font-size: 14px;
  color: #e6a23c;
  margin: 0 0 8px 0;
}
.failed-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-top: 1px solid #f0e0c0;
  font-size: 13px;
}
.failed-item:first-child { border-top: none; padding-top: 0; }
.failed-name { color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.failed-reason { color: #f56c6c; font-size: 12px; flex-shrink: 0; margin-left: 12px; }

.complete-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
}

/* 通用按钮 */
.action-btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.action-btn.secondary { background: #eee; color: #333; }
.action-btn.primary { background: #C5D9FF; color: #333; }
.action-btn.primary:disabled { opacity: 0.6; cursor: not-allowed; }
.action-btn.danger { background: #fdecea; color: #c0392b; }
.action-btn.danger:hover { background: #f8d0cc; }

@media (max-width: 768px) {
  .toolbar { padding-left: 24px; }
}
</style>
