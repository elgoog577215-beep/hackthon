<template>
  <div class="admin-feedbacks-view">
    <div class="admin-toolbar">
      <h2 class="admin-page-title">用户反馈</h2>
      <div class="admin-toolbar-actions">
        <select v-model="ratingType" class="filter-select">
          <option :value="null">全部评价</option>
          <option value="positive">好评（4-5★）</option>
          <option value="neutral">中评（3★）</option>
          <option value="negative">差评（1-2★）</option>
        </select>
        <input
          v-model.number="minLength"
          type="number"
          class="filter-input"
          placeholder="最短字数"
          min="0"
        />
        <button type="button" class="btn-secondary" @click="loadFeedbacks" :disabled="loading">查询</button>
        <button type="button" class="btn-primary" @click="onExport" :disabled="exporting">
          {{ exporting ? '导出中...' : '导出 Excel' }}
        </button>
      </div>
    </div>

    <div class="feedback-table-wrap">
      <table class="feedback-table" v-if="feedbacks.length > 0">
        <thead>
          <tr>
            <th>姓名</th>
            <th>学工号</th>
            <th>学院</th>
            <th class="col-star">星级</th>
            <th>评价文案</th>
            <th class="col-image">附件</th>
            <th>提交时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in feedbacks" :key="f.id">
            <td>{{ f.user_name || '—' }}</td>
            <td>{{ f.user_zju_id || '—' }}</td>
            <td>{{ f.user_department || '—' }}</td>
            <td class="col-star">
              <span class="star-cell">{{ '★'.repeat(f.star) }}{{ '☆'.repeat(5 - f.star) }}</span>
            </td>
            <td class="col-content">
              <div class="content-cell" :title="f.content">{{ f.content }}</div>
            </td>
            <td class="col-image">
              <div
                v-if="(f.image_paths?.length ?? 0) > 0"
                class="attachment-thumbs"
                role="button"
                tabindex="0"
                :aria-label="`查看 ${f.image_paths!.length} 个附件`"
                @click="openLightbox(f.image_paths!, 0)"
                @keyup.enter="openLightbox(f.image_paths!, 0)"
              >
                <span
                  v-for="(p, i) in f.image_paths!.slice(0, 3)"
                  :key="i"
                  class="attachment-thumb"
                  :class="`attachment-thumb-${attachmentKind(p)}`"
                  :title="attachmentFilename(p)"
                >
                  <img
                    v-if="attachmentKind(p) === 'image'"
                    :src="attachmentUrl(p)"
                    alt=""
                    loading="lazy"
                  />
                  <template v-else-if="attachmentKind(p) === 'video'">▶</template>
                  <template v-else>📄</template>
                </span>
                <span v-if="f.image_paths!.length > 3" class="attachment-more">
                  +{{ f.image_paths!.length - 3 }}
                </span>
              </div>
              <span v-else class="image-empty">—</span>
            </td>
            <td>{{ f.create_time }}</td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty-state">加载中...</div>
      <div v-else-if="error" class="empty-state error">{{ error }}</div>
      <div v-else class="empty-state">暂无反馈数据</div>
    </div>

    <AttachmentLightbox
      v-model="lightboxOpen"
      :attachments="lightboxAttachments"
      :initial-index="lightboxIndex"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AttachmentLightbox from '../../components/AttachmentLightbox.vue'
import { buildApiFullUrl } from '../../api/request'
import {
  exportAdminFeedbacks,
  fetchAdminFeedbacks,
  triggerBlobDownload,
} from '../../api/admin'
import type { AdminFeedbackDetail } from '../../api/types'

type Rating = 'positive' | 'neutral' | 'negative' | null

const feedbacks = ref<AdminFeedbackDetail[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const ratingType = ref<Rating>(null)
const minLength = ref<number | null>(null)
const exporting = ref(false)

async function loadFeedbacks() {
  loading.value = true
  error.value = null
  try {
    feedbacks.value = await fetchAdminFeedbacks({
      rating_type: ratingType.value,
      min_length: minLength.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

const lightboxOpen = ref(false)
const lightboxAttachments = ref<string[]>([])
const lightboxIndex = ref(0)

function openLightbox(paths: string[], index: number) {
  lightboxAttachments.value = paths
  lightboxIndex.value = index
  lightboxOpen.value = true
}

function attachmentFilename(path: string): string {
  const seg = (path ?? '').split(/[\\/]/).pop() ?? path
  return (seg ?? '').split('?')[0] ?? ''
}

function attachmentKind(path: string): 'image' | 'video' | 'other' {
  const ext = attachmentFilename(path).split('.').pop()?.toLowerCase() ?? ''
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image'
  if (['mp4', 'webm', 'mov', 'm4v', 'ogv'].includes(ext)) return 'video'
  return 'other'
}

function attachmentUrl(rawPath: string): string {
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

async function onExport() {
  exporting.value = true
  try {
    const blob = await exportAdminFeedbacks({
      rating_type: ratingType.value,
      min_length: minLength.value,
    })
    const date = new Date().toISOString().slice(0, 10)
    triggerBlobDownload(blob, `用户反馈_${date}.xlsx`)
  } catch (e) {
    console.error('[Admin] 导出反馈失败', e)
    alert(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  loadFeedbacks()
})
</script>

<style scoped>
.admin-feedbacks-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.admin-page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1a2540;
}

.admin-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-select,
.filter-input {
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #d8deea;
  font-size: 14px;
  color: #1a2540;
  background: #fff;
}

.filter-input {
  width: 120px;
}

.filter-select:focus,
.filter-input:focus {
  outline: none;
  border-color: #4467d9;
}

.btn-primary,
.btn-secondary {
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 14px;
  border: none;
  cursor: pointer;
}

.btn-primary {
  background: #2f4aa6;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #243a85;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f0f4fb;
  color: #1f3c8b;
}

.btn-secondary:hover:not(:disabled) {
  background: #dde6f8;
}

.feedback-table-wrap {
  background: #fff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
  overflow-x: auto;
}

.feedback-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}

.feedback-table thead th {
  background: #f5f7fb;
  color: #4b5670;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  white-space: nowrap;
}

.feedback-table tbody td {
  padding: 12px;
  color: #1a2540;
  border-bottom: 1px solid #f0f3f9;
  vertical-align: middle;
}

.col-star {
  width: 110px;
}

.star-cell {
  color: #d99700;
  letter-spacing: 1px;
  font-size: 14px;
}

.col-content {
  max-width: 360px;
}

.content-cell {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #4b5670;
  white-space: pre-line;
}

.col-image {
  width: 180px;
}

.attachment-thumbs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 6px;
}

.attachment-thumbs:hover {
  background: #f0f4fb;
}

.attachment-thumbs:focus-visible {
  outline: 2px solid #4467d9;
  outline-offset: 1px;
}

.attachment-thumb {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: #e7eeff;
  color: #1f3c8b;
  font-size: 16px;
  overflow: hidden;
  border: 1px solid #d3def8;
}

.attachment-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.attachment-thumb-video {
  background: #1a2540;
  color: #fff;
}

.attachment-thumb-other {
  background: #f0f3f9;
  color: #4b5670;
}

.attachment-more {
  display: inline-block;
  padding: 4px 8px;
  background: #f0f4fb;
  color: #4b5670;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.image-empty {
  color: #8a93a6;
}

.empty-state {
  padding: 48px 16px;
  text-align: center;
  color: #8a93a6;
  font-size: 14px;
}

.empty-state.error {
  color: #c62828;
}
</style>
