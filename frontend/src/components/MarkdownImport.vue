<template>
  <el-dialog
    v-model="visible"
    title="导入 Markdown"
    width="480px"
    destroy-on-close
    append-to-body
  >
    <div v-loading="uploading" class="import-body">
      <!-- Hidden file input -->
      <input
        ref="fileInputRef"
        type="file"
        accept=".md,.txt"
        class="hidden-input"
        @change="onFileChange"
      />

      <!-- Trigger button -->
      <div class="file-select-area">
        <el-button @click="triggerFileInput">选择文件</el-button>
        <span v-if="selectedFile" class="file-info">
          {{ selectedFile.name }} ({{ formatSize(selectedFile.size) }})
        </span>
        <span v-else class="file-placeholder">未选择文件</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedFile || uploading"
        @click="confirmUpload"
      >
        上传
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import { useCourseStore } from '@/stores/course'

const router = useRouter()
const courseStore = useCourseStore()

const visible = ref(false)
const uploading = ref(false)
const selectedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function open() {
  selectedFile.value = null
  uploading.value = false
  visible.value = true
}

function cancel() {
  visible.value = false
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function confirmUpload() {
  if (!selectedFile.value) return

  uploading.value = true
  try {
    const result = await courseStore.importMarkdown(selectedFile.value)
    visible.value = false
    router.push({ name: 'course', params: { courseId: result.course_id } })
  } catch (error: unknown) {
    const detail =
      (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? '上传失败，请重试'
    ElNotification.error({ title: '导入失败', message: detail })
  } finally {
    selectedFile.value = null
    uploading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.hidden-input {
  display: none;
}

.import-body {
  padding: 8px 0;
}

.file-select-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.file-info {
  font-size: 14px;
  color: #303133;
  word-break: break-all;
}

.file-placeholder {
  font-size: 14px;
  color: #909399;
}
</style>
