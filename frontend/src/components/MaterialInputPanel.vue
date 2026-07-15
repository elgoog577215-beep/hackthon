<template>
  <section class="material-panel" :aria-label="t('courseGeneration.materials.label', '参考资料')">
    <div class="material-panel__header">
      <div class="material-panel__title">
        <span class="material-panel__icon">
          <Upload :size="14" />
        </span>
        <div>
          <label>{{ t('courseGeneration.materials.label', '参考资料') }}</label>
          <p>{{ t('courseGeneration.materials.subtitle', '上传教材、讲义或题目，让生成内容有据可循') }}</p>
        </div>
      </div>
      <span v-if="modelValue.length" class="material-panel__count">
        {{ t('courseGeneration.materials.fileCount', '{count} 份资料').replace('{count}', String(modelValue.length)) }}
      </span>
    </div>

    <div
      class="material-dropzone"
      :class="{ 'material-dropzone--active': dragging, 'material-dropzone--disabled': disabled }"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="handleDrop"
    >
      <div class="material-dropzone__copy">
        <span class="material-dropzone__mark"><FolderUp :size="19" /></span>
        <div>
          <strong>{{ t('courseGeneration.materials.dropTitle', '拖入文件，或从电脑中选择') }}</strong>
          <span>{{ t('courseGeneration.materials.supportHint', '支持 PDF、Office、Markdown 与常见文本格式，单个文件不超过 50 MB') }}</span>
        </div>
      </div>
      <div class="material-dropzone__actions">
        <button
          type="button"
          class="material-button material-button--secondary"
          :title="t('courseGeneration.materials.addText', '添加文本资料')"
          :aria-label="t('courseGeneration.materials.addText', '添加文本资料')"
          :disabled="disabled"
          @click="addTextMaterial"
        >
          <FilePlus2 :size="15" />
          <span>{{ t('courseGeneration.materials.addText', '添加文本资料') }}</span>
        </button>
        <label
          class="material-button material-button--primary"
          :class="{ 'pointer-events-none opacity-50': disabled }"
          :title="t('courseGeneration.materials.chooseFiles', '选择文件')"
          :aria-label="t('courseGeneration.materials.chooseFiles', '选择文件')"
        >
          <FolderUp :size="15" />
          <span>{{ t('courseGeneration.materials.chooseFiles', '选择文件') }}</span>
          <input
            class="sr-only"
            type="file"
            multiple
            accept=".pdf,.docx,.pptx,.xlsx,.md,.markdown,.txt,.csv,.json,.py,.js,.ts,.html,.css"
            @change="handleFiles"
          />
        </label>
      </div>
    </div>

    <div
      v-if="modelValue.length === 0"
      class="material-empty"
    >
      <FileText :size="18" />
      <span>{{ t('courseGeneration.materials.emptyHelp', '资料会先上传并解析，再作为课程证据使用。') }}</span>
    </div>

    <div v-else class="material-list">
      <article
        v-for="material in modelValue"
        :key="material.local_id"
        class="material-card"
        :class="`material-card--${material.upload_status}`"
      >
      <div class="material-card__top">
        <div class="material-card__file-icon">
          <FileText :size="15" />
        </div>
        <div class="material-card__identity">
          <el-input
            v-model="material.filename"
            size="small"
            :disabled="material.upload_status === 'uploading' || material.upload_status === 'uploaded'"
            :placeholder="t('courseGeneration.materials.namePlaceholder', '资料名称')"
          />
          <div class="material-card__meta">
            <span class="material-status" :class="statusClass(material.upload_status)">
              <span class="material-status__dot" />
              {{ statusLabel(material.upload_status) }}
            </span>
            <span v-if="material.file?.size" class="material-card__size">{{ formatFileSize(material.file.size) }}</span>
            <span v-if="material.parse_status" class="material-card__parse">{{ parseStatusLabel(material.parse_status) }}</span>
          </div>
        </div>
        <div class="material-card__actions">
        <button
          v-if="material.upload_status === 'error'"
          type="button"
          class="material-icon-button material-icon-button--retry"
          :title="t('courseGeneration.materials.retry', '重试上传')"
          @click="uploadDraft(material.local_id)"
        >
          <RefreshCw :size="14" />
        </button>
        <button
          type="button"
          class="material-icon-button material-icon-button--remove"
          :title="t('courseGeneration.materials.remove', '移除资料')"
          :disabled="material.upload_status === 'uploading'"
          @click="removeMaterial(material.local_id)"
        >
          <Trash2 :size="14" />
        </button>
        </div>
      </div>

      <div v-if="material.upload_error" class="material-error" role="alert">
        {{ material.upload_error }}
      </div>

      <div class="material-card__settings">
        <label><span>{{ t('courseGeneration.materials.field.purpose', '用途') }}</span><el-select v-model="material.purpose" size="small" @change="applyPurposeDefaults(material)">
          <el-option :label="t('courseGeneration.materials.usage.contentSource', '正文依据')" value="content_source" />
          <el-option :label="t('courseGeneration.materials.usage.styleReference', '讲法参考')" value="style_reference" />
          <el-option :label="t('courseGeneration.materials.usage.questionSource', '题目来源')" value="question_source" />
          <el-option :label="t('courseGeneration.materials.usage.supplement', '补充材料')" value="supplement" />
          <el-option :label="t('courseGeneration.materials.usage.weakContext', '弱背景')" value="weak_context" />
        </el-select></label>
        <label><span>{{ t('courseGeneration.materials.field.priority', '优先级') }}</span><el-select v-model="material.priority" size="small" @change="applyPriorityDefaults(material)">
          <el-option :label="t('courseGeneration.materials.importance.core', '核心资料')" value="core" />
          <el-option :label="t('courseGeneration.materials.importance.supporting', '辅助资料')" value="supporting" />
          <el-option :label="t('courseGeneration.materials.importance.weak', '弱参考')" value="weak" />
        </el-select></label>
        <label><span>{{ t('courseGeneration.materials.field.authority', '权威性') }}</span><el-select v-model="material.authority" size="small">
          <el-option :label="t('courseGeneration.materials.authority.primary', '主要依据')" value="primary" />
          <el-option :label="t('courseGeneration.materials.authority.secondary', '次要依据')" value="secondary" />
          <el-option :label="t('courseGeneration.materials.authority.contextOnly', '仅作背景')" value="context_only" />
        </el-select></label>
        <label><span>{{ t('courseGeneration.materials.field.policy', '使用策略') }}</span><el-select v-model="material.usage_policy" size="small">
          <el-option :label="t('courseGeneration.materials.policy.mustUse', '必须使用')" value="must_use" />
          <el-option :label="t('courseGeneration.materials.policy.prefer', '优先使用')" value="prefer" />
          <el-option :label="t('courseGeneration.materials.policy.optional', '可选使用')" value="optional" />
          <el-option :label="t('courseGeneration.materials.policy.styleOnly', '仅参考讲法')" value="style_only" />
        </el-select></label>
      </div>

      <el-input
        v-model="material.user_description"
        type="textarea"
        :rows="2"
        resize="none"
        :placeholder="t('courseGeneration.materials.descriptionPlaceholder', '资料来源与使用说明')"
      />
      <el-input
        v-if="material.file_type === 'md' && !material.file"
        v-model="material.manual_content"
        type="textarea"
        :rows="3"
        resize="none"
        :placeholder="t('courseGeneration.materials.contentPlaceholder', '粘贴资料正文')"
      />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { FilePlus2, FileText, FolderUp, RefreshCw, Trash2, Upload } from 'lucide-vue-next'
import http from '@/utils/http'
import { t } from '@/shared/i18n'
import { formatFileSize, materialUploadErrorMessage, validateMaterialFile } from '@/shared/material-upload'
import type { CourseMaterialBindingInput, CourseMaterialDraft } from '@/shared/prompt-config'

const props = withDefaults(defineProps<{
  modelValue: CourseMaterialDraft[]
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: CourseMaterialDraft[]]
}>()

const dragging = ref(false)
const updateDraft = (localId: string, patch: Partial<CourseMaterialDraft>) => {
  emit('update:modelValue', props.modelValue.map(item => (
    item.local_id === localId ? { ...item, ...patch } : item
  )))
}

const newDraft = (filename: string, file?: File): CourseMaterialDraft => ({
  local_id: crypto.randomUUID(),
  filename,
  file_type: (filename.split('.').pop() || 'md').toLowerCase(),
  file,
  manual_content: '',
  purpose: 'content_source',
  priority: 'core',
  authority: 'primary',
  usage_policy: 'must_use',
  user_description: '',
  source_label: '',
  upload_status: 'pending',
})

const handleFiles = async (event: Event) => {
  const input = event.target as HTMLInputElement
  await addFiles(Array.from(input.files || []))
  input.value = ''
}

const addFiles = async (files: File[]) => {
  const existing = new Set(props.modelValue.map(item => `${item.filename}:${item.file?.size || 0}`))
  const additions = files.map(file => {
    const draft = newDraft(file.name, file)
    const validationError = validateMaterialFile(file, {
      unsupported: extension => t('courseGeneration.materials.unsupportedType', `不支持的文件类型：${extension}`).replace('{extension}', extension),
      tooLarge: maxMb => t('courseGeneration.materials.tooLarge', `文件过大，单个文件最大支持 ${maxMb} MB`).replace('{max}', String(maxMb)),
      empty: t('courseGeneration.materials.emptyFile', '文件为空，请选择包含内容的文件'),
    })
    if (existing.has(`${file.name}:${file.size}`)) {
      draft.upload_status = 'error'
      draft.upload_error = t('courseGeneration.materials.duplicateFile', '这份文件已在列表中')
    } else if (validationError) {
      draft.upload_status = 'error'
      draft.upload_error = validationError
    }
    existing.add(`${file.name}:${file.size}`)
    return draft
  })
  emit('update:modelValue', [...props.modelValue, ...additions])
  await nextTick()
  await Promise.allSettled(additions.filter(item => item.upload_status !== 'error').map(item => uploadDraft(item.local_id)))
}

const handleDrop = async (event: DragEvent) => {
  dragging.value = false
  if (props.disabled) return
  await addFiles(Array.from(event.dataTransfer?.files || []))
}

const addTextMaterial = () => {
  emit('update:modelValue', [...props.modelValue, newDraft(t('courseGeneration.materials.manualName', '手工资料.md'))])
}

const fileForDraft = (draft: CourseMaterialDraft): File | null => {
  if (draft.file) return draft.file
  if (!draft.manual_content?.trim()) return null
  const filename = draft.filename.trim() || t('courseGeneration.materials.manualName', '手工资料.md')
  return new File([draft.manual_content], filename.endsWith('.md') ? filename : `${filename}.md`, {
    type: 'text/markdown',
  })
}

const uploadDraft = async (localId: string) => {
  const draft = props.modelValue.find(item => item.local_id === localId)
  if (!draft || draft.asset_id) return
  const file = fileForDraft(draft)
  if (!file) return
  updateDraft(localId, { upload_status: 'uploading', upload_error: '' })
  await nextTick()
  const data = new FormData()
  data.append('file', file)
  data.append('upload_batch_id', `course-draft-${Date.now()}`)
  try {
    const response = await http.post('/api/materials', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    updateDraft(localId, {
      asset_id: response.data.asset_id,
      filename: response.data.filename || draft.filename,
      parse_status: response.data.status,
      upload_status: 'uploaded',
      upload_error: '',
    })
  } catch (error: any) {
    updateDraft(localId, {
      upload_status: 'error',
      upload_error: materialUploadErrorMessage(error, t('courseGeneration.materials.uploadFailed', '上传失败')),
    })
  }
}

const removeMaterial = async (localId: string) => {
  const draft = props.modelValue.find(item => item.local_id === localId)
  emit('update:modelValue', props.modelValue.filter(item => item.local_id !== localId))
  if (draft?.asset_id) {
    try {
      await http.delete(`/api/materials/${draft.asset_id}`)
    } catch {
      // A bound asset remains available to its course.
    }
  }
}

const applyPurposeDefaults = (draft: CourseMaterialDraft) => {
  if (draft.purpose === 'style_reference') {
    updateDraft(draft.local_id, { authority: 'context_only', usage_policy: 'style_only' })
  } else if (draft.purpose === 'weak_context') {
    updateDraft(draft.local_id, { authority: 'context_only', usage_policy: 'optional' })
  } else {
    applyPriorityDefaults(draft)
  }
}

const applyPriorityDefaults = (draft: CourseMaterialDraft) => {
  if (draft.purpose === 'style_reference' || draft.purpose === 'weak_context') return
  updateDraft(draft.local_id, {
    authority: draft.priority === 'core' ? 'primary' : 'secondary',
    usage_policy: draft.priority === 'core' ? 'must_use' : draft.priority === 'supporting' ? 'prefer' : 'optional',
  })
}

const ensureUploaded = async (): Promise<CourseMaterialBindingInput[]> => {
  for (const draft of props.modelValue) {
    if (!draft.asset_id) await uploadDraft(draft.local_id)
    await nextTick()
  }
  await nextTick()
  const latest = props.modelValue
  const failed = latest.find(item => item.upload_status === 'error' || !item.asset_id)
  if (failed) throw new Error(failed.upload_error || t('courseGeneration.materials.contentRequired', '资料内容为空或尚未上传'))
  return latest.map(item => ({
    asset_id: item.asset_id!,
    purpose: item.purpose,
    priority: item.priority,
    authority: item.authority,
    usage_policy: item.usage_policy,
    user_description: item.user_description?.trim() || '',
    source_label: item.source_label?.trim() || '',
  }))
}

const statusLabel = (status: CourseMaterialDraft['upload_status']) => t(
  `courseGeneration.materials.status.${status}`,
  ({ pending: '等待上传', uploading: '上传中', uploaded: '已上传', error: '上传失败' } as const)[status],
)

const parseStatusLabel = (status: string) => t(
  `courseGeneration.materials.parseStatus.${status}`,
  ({ parsed: '解析完成', degraded: '降级解析', failed: '解析失败', metadata_only: '仅识别元数据' } as Record<string, string>)[status] || '解析状态未知',
)

const statusClass = (status: CourseMaterialDraft['upload_status']) => ({
  pending: 'status-pending',
  uploading: 'status-uploading',
  uploaded: 'status-uploaded',
  error: 'status-error',
}[status])

defineExpose({ ensureUploaded })
</script>

<style scoped>
.material-panel { display: grid; gap: 12px; }
.material-panel__header, .material-panel__title, .material-dropzone, .material-dropzone__copy, .material-dropzone__actions, .material-card__top, .material-card__meta, .material-card__actions { display: flex; align-items: center; }
.material-panel__header { justify-content: space-between; gap: 16px; }
.material-panel__title { gap: 10px; min-width: 0; }
.material-panel__icon { width: 30px; height: 30px; display: grid; flex: 0 0 auto; place-items: center; border: 1px solid #c7d2fe; border-radius: 9px; color: #4f46e5; background: linear-gradient(145deg, #eef2ff, #fff); box-shadow: 0 4px 12px rgba(79,70,229,.08); }
.material-panel__title label { display: block; color: #334155; font-size: 13px; font-weight: 750; }
.material-panel__title p { margin: 2px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.4; }
.material-panel__count { flex: 0 0 auto; padding: 4px 8px; border-radius: 999px; color: #4f46e5; background: #eef2ff; font-size: 10px; font-weight: 700; }
.material-dropzone { justify-content: space-between; gap: 18px; min-height: 78px; padding: 14px 16px; border: 1px dashed #cbd5e1; border-radius: 13px; background: linear-gradient(135deg, rgba(248,250,252,.95), rgba(238,242,255,.6)); transition: .18s ease; }
.material-dropzone:hover, .material-dropzone--active { border-color: #818cf8; background: #eef2ff; box-shadow: inset 0 0 0 1px rgba(99,102,241,.08); }
.material-dropzone--disabled { opacity: .55; pointer-events: none; }
.material-dropzone__copy { min-width: 0; gap: 11px; }
.material-dropzone__mark { width: 38px; height: 38px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 11px; color: #6366f1; background: #fff; box-shadow: 0 5px 15px rgba(15,23,42,.07); }
.material-dropzone__copy strong, .material-dropzone__copy span { display: block; }
.material-dropzone__copy strong { color: #475569; font-size: 12px; }
.material-dropzone__copy span { margin-top: 3px; color: #94a3b8; font-size: 10px; line-height: 1.45; }
.material-dropzone__actions { flex: 0 0 auto; gap: 8px; }
.material-button { height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 11px; border-radius: 9px; font-size: 11px; font-weight: 700; cursor: pointer; transition: .16s ease; }
.material-button:disabled { cursor: not-allowed; opacity: .5; }
.material-button--secondary { border: 1px solid #e2e8f0; color: #64748b; background: #fff; }
.material-button--secondary:hover { border-color: #c7d2fe; color: #4f46e5; }
.material-button--primary { border: 1px solid #4f46e5; color: #fff; background: linear-gradient(135deg, #6366f1, #4f46e5); box-shadow: 0 5px 12px rgba(79,70,229,.18); }
.material-empty { min-height: 48px; display: flex; align-items: center; justify-content: center; gap: 8px; color: #94a3b8; font-size: 11px; }
.material-list { display: grid; gap: 10px; }
.material-card { position: relative; display: grid; gap: 11px; padding: 13px; overflow: hidden; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; box-shadow: 0 3px 12px rgba(15,23,42,.035); }
.material-card::before { content: ''; position: absolute; inset: 0 auto 0 0; width: 3px; background: #cbd5e1; }
.material-card--uploading::before { background: #6366f1; }
.material-card--uploaded::before { background: #10b981; }
.material-card--error::before { background: #ef4444; }
.material-card__top { gap: 10px; }
.material-card__file-icon { width: 34px; height: 34px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 9px; color: #64748b; background: #f1f5f9; }
.material-card__identity { min-width: 0; flex: 1; }
.material-card__meta { min-height: 18px; gap: 8px; margin-top: 3px; color: #94a3b8; font-size: 10px; }
.material-status { display: inline-flex; align-items: center; gap: 5px; font-weight: 700; }
.material-status__dot { width: 5px; height: 5px; border-radius: 999px; background: currentColor; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 12%, transparent); }
.status-pending { color: #94a3b8; }.status-uploading { color: #4f46e5; }.status-uploaded { color: #059669; }.status-error { color: #dc2626; }
.material-card__actions { gap: 3px; }
.material-icon-button { width: 30px; height: 30px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }
.material-icon-button--retry { color: #d97706; }.material-icon-button--retry:hover { background: #fffbeb; }
.material-icon-button--remove { color: #f87171; }.material-icon-button--remove:hover { color: #ef4444; background: #fef2f2; }
.material-error { padding: 8px 10px; border: 1px solid #fecaca; border-radius: 8px; color: #b91c1c; background: #fef2f2; font-size: 10px; line-height: 1.5; }
.material-card__settings { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.material-card__settings label { min-width: 0; }
.material-card__settings label > span { display: block; margin: 0 0 4px 2px; color: #94a3b8; font-size: 9px; font-weight: 700; }
.material-card__settings :deep(.el-select) { width: 100%; }
.material-card :deep(.el-input__wrapper), .material-card :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px #e2e8f0 inset; }
.material-card :deep(.el-input__wrapper:hover), .material-card :deep(.el-textarea__inner:hover) { box-shadow: 0 0 0 1px #c7d2fe inset; }
@media (max-width: 720px) {
  .material-dropzone { align-items: stretch; flex-direction: column; }
  .material-dropzone__actions { width: 100%; }
  .material-button { flex: 1; }
  .material-card__settings { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 480px) {
  .material-panel__title p { display: none; }
  .material-dropzone__copy span { max-width: 240px; }
  .material-dropzone__actions { flex-direction: column; }
  .material-button { width: 100%; }
}
</style>
