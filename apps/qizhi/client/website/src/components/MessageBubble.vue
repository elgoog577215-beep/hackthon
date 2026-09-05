<template>
  <template v-if="role === 'user'">
    <div v-if="displayText" class="message-content">{{ displayText }}</div>
    <div
      v-if="renderedAttachments.length > 0"
      class="attachment-list"
      :class="{ 'attachment-list--solo': !displayText }"
    >
      <div
        v-for="(att, idx) in renderedAttachments"
        :key="idx"
        class="attachment-card"
      >
        <span class="attachment-badge" :class="attachmentBadgeClass(att.name)">
          <span class="attachment-ext">{{ fileExtLabel(att.name) }}</span>
        </span>
        <span class="attachment-info">
          <span class="attachment-name" :title="att.name">{{ att.name }}</span>
          <span class="attachment-sub">
            {{ att.size != null ? formatSize(att.size) : attachmentKindLabel(att.name) }}
          </span>
        </span>
      </div>
    </div>
  </template>
  <div v-else class="assistant-message">
    <div
      class="message-content message-markdown"
      v-html="renderedHtml"
      @click="onMarkdownClick"
    ></div>
    <div class="message-actions">
      <button
        type="button"
        class="message-action-btn message-action-btn--copy"
        aria-label="复制"
        title="复制"
        @click="copyAssistantReply"
      ></button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 单条消息内容渲染。
 *
 * 为什么拆成独立组件：
 * - `renderedHtml` 是个 `computed`，只依赖当前这条消息的 `content`。
 *   流式增量到达时，只有「正在被写入」的那条消息的 `content` 变化，
 *   Vue 只会重算它的 computed；其它历史消息的 HTML 直接命中缓存，
 *   不再重跑 marked + DOMPurify + KaTeX 这一整套解析。
 * - 之前在 ChatView 里用 `v-html="renderMarkdown(msg.content)"` 直接调用函数，
 *   一次流式增量会让所有助手消息都重新解析一遍，消息越多越卡。
 *
 * 用户消息的附件：
 * - 新发送的消息会带结构化 `attachments` (name/size)，直接渲染为卡片。
 * - 从后端加载的历史消息没有结构化附件，走「尾部 `[xxx] [yyy]` 回退解析」。
 */
import { computed } from 'vue'

import { getMarkdownCodeBlockText, renderMarkdown } from '../utils/markdown'
import type { ChatAttachmentMeta } from '../stores/chat'

interface Props {
  role: 'assistant' | 'user'
  content: string
  attachments?: ChatAttachmentMeta[]
}

const props = defineProps<Props>()

const renderedHtml = computed(() =>
  props.role === 'assistant' ? renderMarkdown(props.content) : ''
)

/**
 * 从用户消息末尾把 `[xxx] [yyy]` 这样的附件回退标记剥出来。
 * 仅当最后一行完全由若干 `[...]` 组成（中间用空格分隔）才视为附件行，避免把用户正文里的
 * 方括号误识别为附件。
 */
const TRAILING_ATTACH_LINE = /^(?:\[[^\[\]\n]+\])(?:\s+\[[^\[\]\n]+\])*\s*$/
const TRAILING_ATTACH_TOKEN = /\[([^\[\]\n]+)\]/g

interface ParsedFallback {
  cleanText: string
  attachments: ChatAttachmentMeta[]
}
function parseFallbackAttachments(content: string): ParsedFallback {
  if (!content) return { cleanText: '', attachments: [] }
  const lines = content.split('\n')
  let lastNonEmpty = lines.length - 1
  while (lastNonEmpty >= 0 && lines[lastNonEmpty]!.trim() === '') lastNonEmpty--
  if (lastNonEmpty < 0) return { cleanText: content, attachments: [] }
  const lastLine = lines[lastNonEmpty]!.trim()
  if (!TRAILING_ATTACH_LINE.test(lastLine)) return { cleanText: content, attachments: [] }
  const names: string[] = []
  let m: RegExpExecArray | null
  const re = new RegExp(TRAILING_ATTACH_TOKEN.source, 'g')
  while ((m = re.exec(lastLine)) !== null) names.push(m[1]!.trim())
  if (names.length === 0) return { cleanText: content, attachments: [] }
  // 去掉附件行以及它前面用于分隔的空行
  let keepUntil = lastNonEmpty - 1
  while (keepUntil >= 0 && lines[keepUntil]!.trim() === '') keepUntil--
  const cleanText = lines.slice(0, keepUntil + 1).join('\n')
  return { cleanText, attachments: names.map((name) => ({ name })) }
}

/** 实际渲染时展示的主体文本 */
const displayText = computed<string>(() => {
  if (props.role !== 'user') return ''
  // 有结构化附件：直接用原文（发送端已保留 `[文件名]` 以兼容后端，但我们在 UI 层把它们剥掉）
  if (props.attachments && props.attachments.length > 0) {
    return parseFallbackAttachments(props.content).cleanText
  }
  return parseFallbackAttachments(props.content).cleanText
})

/** 实际渲染的附件列表：优先用结构化元数据，否则回退解析 content */
const renderedAttachments = computed<ChatAttachmentMeta[]>(() => {
  if (props.role !== 'user') return []
  if (props.attachments && props.attachments.length > 0) return props.attachments
  return parseFallbackAttachments(props.content).attachments
})

/** 文件扩展名大写（最多 4 个字符）作为 badge 文案；无扩展时显示 FILE */
function fileExt(name: string): string {
  const dot = name.lastIndexOf('.')
  if (dot < 0 || dot === name.length - 1) return ''
  return name.slice(dot + 1).toLowerCase()
}

function fileExtLabel(name: string): string {
  const ext = fileExt(name).toUpperCase()
  if (!ext) return 'FILE'
  return ext.length > 4 ? ext.slice(0, 4) : ext
}

type AttachmentBadgeTone = 'image' | 'video' | 'pdf' | 'doc' | 'sheet' | 'archive' | 'default'

function attachmentBadgeClass(name: string): `is-${AttachmentBadgeTone}` {
  const ext = fileExt(name)
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'heic'].includes(ext)) return 'is-image'
  if (['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'].includes(ext)) return 'is-video'
  if (ext === 'pdf') return 'is-pdf'
  if (['doc', 'docx', 'txt', 'md', 'rtf', 'ppt', 'pptx'].includes(ext)) return 'is-doc'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'is-sheet'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return 'is-archive'
  return 'is-default'
}

function attachmentKindLabel(name: string): string {
  const tone = attachmentBadgeClass(name).slice(3)
  const labels: Record<string, string> = {
    image: '图片',
    video: '视频',
    pdf: 'PDF 文档',
    doc: '文档',
    sheet: '表格',
    archive: '压缩包',
    default: '附件',
  }
  return labels[tone] ?? labels.default!
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function copyTextToClipboard(text: string): Promise<boolean> {
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fallback */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

async function copyAssistantReply(event: MouseEvent) {
  const btn = event.currentTarget
  if (!(btn instanceof HTMLButtonElement)) return
  const text = props.content?.trim() ?? ''
  const ok = await copyTextToClipboard(text)
  const prevTitle = btn.getAttribute('title') ?? '复制'
  btn.setAttribute('title', ok ? '已复制' : '复制失败')
  btn.classList.toggle('is-copied', ok)
  window.setTimeout(() => {
    btn.setAttribute('title', prevTitle)
    btn.classList.remove('is-copied')
  }, 1500)
}

function onMarkdownClick(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  const btn = target.closest('.md-code-block__copy')
  if (!(btn instanceof HTMLButtonElement)) return
  event.preventDefault()
  event.stopPropagation()
  const block = btn.closest('.md-code-block')
  if (!(block instanceof HTMLElement)) return
  void (async () => {
    const text = getMarkdownCodeBlockText(block)
    const ok = await copyTextToClipboard(text)
    const prevTitle = btn.getAttribute('title') ?? '复制代码'
    btn.setAttribute('title', ok ? '已复制' : '复制失败')
    btn.classList.toggle('is-copied', ok)
    window.setTimeout(() => {
      btn.setAttribute('title', prevTitle)
      btn.classList.remove('is-copied')
    }, 1500)
  })()
}
</script>

<style scoped>
/* `.message-content` 的基础排版（字号/换行）由父级 `.message-bubble` 继承，
   此处只处理 markdown 模式下要关闭父级 `pre-wrap`、避免双倍换行的覆盖。 */
.assistant-message {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.message-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 8px;
  padding-top: 4px;
}

.message-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #8b949e;
  cursor: pointer;
}

.message-action-btn::before {
  content: '';
  width: 16px;
  height: 16px;
  background-color: currentColor;
  -webkit-mask: no-repeat center / contain;
  mask: no-repeat center / contain;
}

.message-action-btn:hover {
  color: #57606a;
  background: rgba(27, 31, 35, 0.06);
}

.message-action-btn.is-copied {
  color: #1a7f37;
}

.message-action-btn--copy::before {
  -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Crect x='9' y='9' width='13' height='13' rx='2' stroke='black' stroke-width='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' stroke='black' stroke-width='2'/%3E%3C/svg%3E");
  mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Crect x='9' y='9' width='13' height='13' rx='2' stroke='black' stroke-width='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' stroke='black' stroke-width='2'/%3E%3C/svg%3E");
}

.message-action-btn--copy.is-copied::before {
  -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M20 6L9 17l-5-5' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M20 6L9 17l-5-5' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}

.message-content.message-markdown {
  white-space: normal;
}

/* ---------- 用户消息里的附件卡片（与输入区预览风格一致） ---------- */
.attachment-list {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  margin-top: 10px;
  width: 100%;
}

.attachment-list--solo {
  margin-top: 0;
}

.message-content + .attachment-list {
  margin-top: 12px;
}

.attachment-card {
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(300px, 100%);
  max-width: 100%;
  padding: 8px 12px 8px 8px;
  background: #fff;
  border: 1px solid rgba(0, 16, 129, 0.1);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 16, 129, 0.06);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.attachment-card:hover {
  border-color: rgba(19, 88, 228, 0.28);
  box-shadow: 0 4px 14px rgba(19, 88, 228, 0.12);
  transform: translateY(-1px);
}

.attachment-badge {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #5b8dee;
  color: #fff;
  box-shadow: inset 0 -1px 0 rgba(0, 0, 0, 0.08);
}

.attachment-badge.is-image {
  background: linear-gradient(145deg, #3db88a, #2a9d6f);
}

.attachment-badge.is-video {
  background: linear-gradient(145deg, #8b6ce8, #6b4fd4);
}

.attachment-badge.is-pdf {
  background: linear-gradient(145deg, #e85d5d, #c73e3e);
}

.attachment-badge.is-doc {
  background: linear-gradient(145deg, #5b8dee, #3d6fd4);
}

.attachment-badge.is-sheet {
  background: linear-gradient(145deg, #45b87a, #2d9a5f);
}

.attachment-badge.is-archive {
  background: linear-gradient(145deg, #f0a030, #d4881c);
}

.attachment-ext {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.35px;
  line-height: 1;
  text-align: center;
  padding: 0 2px;
}

.attachment-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
  line-height: 1.35;
}

.attachment-name {
  font-size: 13px;
  font-weight: 500;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attachment-sub {
  margin-top: 3px;
  font-size: 11px;
  color: #757575;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Markdown/LaTeX 渲染内容：紧凑排版 */
.message-content.message-markdown :deep(strong),
.message-content.message-markdown :deep(b) {
  /* 全局 * { font-weight: normal } 会压过默认粗体；700 在中文字体上比 600 更易区分 */
  font-weight: 700;
  font-synthesis: weight;
}

.message-content.message-markdown :deep(em),
.message-content.message-markdown :deep(i) {
  font-style: italic;
}

.message-content.message-markdown :deep(p) {
  margin: 4px 0;
  line-height: 1.5;
}
.message-content.message-markdown :deep(p):first-child {
  margin-top: 0;
}
.message-content.message-markdown :deep(p):last-child {
  margin-bottom: 0;
}
/* 标题样式 */
.message-content.message-markdown :deep(h1),
.message-content.message-markdown :deep(h2),
.message-content.message-markdown :deep(h3),
.message-content.message-markdown :deep(h4),
.message-content.message-markdown :deep(h5),
.message-content.message-markdown :deep(h6) {
  margin: 12px 0 8px;
  font-weight: 600;
  line-height: 1.3;
}
.message-content.message-markdown :deep(h1) { font-size: 1.4em; }
.message-content.message-markdown :deep(h2) { font-size: 1.25em; }
.message-content.message-markdown :deep(h3) { font-size: 1.15em; }
.message-content.message-markdown :deep(h4) { font-size: 1.05em; }
.message-content.message-markdown :deep(h5),
.message-content.message-markdown :deep(h6) { font-size: 1em; }

.message-content.message-markdown :deep(ul),
.message-content.message-markdown :deep(ol) {
  margin: 4px 0;
  padding-left: 1.25em;
}
.message-content.message-markdown :deep(li) {
  margin: 2px 0;
  line-height: 1.5;
}
.message-content.message-markdown :deep(.md-code-block) {
  position: relative;
  margin: 8px 0;
  border-radius: 10px;
  background: #f6f8fa;
  overflow: hidden;
}
.message-content.message-markdown :deep(.md-code-block__toolbar) {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  min-height: 32px;
  padding: 4px 6px;
  border-bottom: 1px solid rgba(27, 31, 35, 0.08);
  background: rgba(27, 31, 35, 0.04);
}
.message-content.message-markdown :deep(.md-code-block__copy) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #57606a;
  cursor: pointer;
}
.message-content.message-markdown :deep(.md-code-block__copy)::before {
  content: '';
  width: 16px;
  height: 16px;
  background-color: currentColor;
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Crect x='9' y='9' width='13' height='13' rx='2' stroke='black' stroke-width='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' stroke='black' stroke-width='2'/%3E%3C/svg%3E") no-repeat center / contain;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Crect x='9' y='9' width='13' height='13' rx='2' stroke='black' stroke-width='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' stroke='black' stroke-width='2'/%3E%3C/svg%3E") no-repeat center / contain;
}
.message-content.message-markdown :deep(.md-code-block__copy:hover) {
  background: rgba(27, 31, 35, 0.08);
  color: #24292f;
}
.message-content.message-markdown :deep(.md-code-block__copy.is-copied) {
  color: #1a7f37;
}
.message-content.message-markdown :deep(.md-code-block__copy.is-copied)::before {
  -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M20 6L9 17l-5-5' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M20 6L9 17l-5-5' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}
.message-content.message-markdown :deep(.md-code-block pre) {
  margin: 0;
  padding: 10px 12px;
  border-radius: 0;
  background: transparent;
  overflow: auto;
  font-size: 0.9em;
  font-family: var(--font-family-code);
}
.message-content.message-markdown :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(27, 31, 35, 0.08);
  font-size: 0.9em;
  font-family: var(--font-family-code);
}
.message-content.message-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
  font-size: 0.95em;
}
.message-content.message-markdown :deep(.katex-display) {
  margin: 8px 0;
  overflow-x: auto;
  overflow-y: hidden;
}
/* 引用块样式 */
.message-content.message-markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid #5B8DEE;
  background: #f8f9fa;
  border-radius: 0 6px 6px 0;
  color: #555;
}
.message-content.message-markdown :deep(blockquote p) {
  margin: 2px 0;
}
/* 链接样式 */
.message-content.message-markdown :deep(a) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(26, 115, 232, 0.25);
  background: rgba(26, 115, 232, 0.08);
  color: #1a73e8;
  text-decoration: none;
  font-weight: 500;
  line-height: 1.2;
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.message-content.message-markdown :deep(a:hover) {
  background: rgba(26, 115, 232, 0.12);
  border-color: rgba(26, 115, 232, 0.35);
  text-decoration: none;
}
.message-content.message-markdown :deep(a:active) {
  transform: translateY(0.5px);
}
.message-content.message-markdown :deep(a)::before {
  content: '';
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  display: inline-block;
  background-color: currentColor;
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M10.59 13.41a1.996 1.996 0 0 0 2.82 0l3.54-3.54a2 2 0 0 0-2.83-2.83l-1.76 1.76a1 1 0 1 1-1.41-1.41l1.76-1.76a4 4 0 0 1 5.66 5.66l-3.54 3.54a4 4 0 0 1-5.66 0 1 1 0 0 1 1.42-1.42Zm2.82-2.82a1.996 1.996 0 0 0-2.82 0l-3.54 3.54a2 2 0 0 0 2.83 2.83l1.76-1.76a1 1 0 1 1 1.41 1.41l-1.76 1.76a4 4 0 0 1-5.66-5.66l3.54-3.54a4 4 0 0 1 5.66 0 1 1 0 0 1-1.42 1.42Z'/%3E%3C/svg%3E") no-repeat center / contain;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M10.59 13.41a1.996 1.996 0 0 0 2.82 0l3.54-3.54a2 2 0 0 0-2.83-2.83l-1.76 1.76a1 1 0 1 1-1.41-1.41l1.76-1.76a4 4 0 0 1 5.66 5.66l-3.54 3.54a4 4 0 0 1-5.66 0 1 1 0 0 1 1.42-1.42Zm2.82-2.82a1.996 1.996 0 0 0-2.82 0l-3.54 3.54a2 2 0 0 0 2.83 2.83l1.76-1.76a1 1 0 1 1 1.41 1.41l-1.76 1.76a4 4 0 0 1-5.66-5.66l3.54-3.54a4 4 0 0 1 5.66 0 1 1 0 0 1-1.42 1.42Z'/%3E%3C/svg%3E") no-repeat center / contain;
}
.message-content.message-markdown :deep(a) :deep(*) {
  max-width: 100%;
}
/* 表格样式 */
.message-content.message-markdown :deep(table) {
  margin: 8px 0;
  border-collapse: collapse;
  width: 100%;
  font-size: 0.95em;
}
.message-content.message-markdown :deep(th),
.message-content.message-markdown :deep(td) {
  padding: 6px 10px;
  border: 1px solid #e0e0e0;
  text-align: left;
}
.message-content.message-markdown :deep(th) {
  background: #f6f8fa;
  font-weight: 600;
}
.message-content.message-markdown :deep(tr:nth-child(even)) {
  background: #fafafa;
}
/* 水平分割线 */
.message-content.message-markdown :deep(hr) {
  margin: 12px 0;
  border: none;
  border-top: 1px solid #e0e0e0;
}
/* 任务列表 */
.message-content.message-markdown :deep(input[type="checkbox"]) {
  margin-right: 6px;
  vertical-align: middle;
}
</style>
