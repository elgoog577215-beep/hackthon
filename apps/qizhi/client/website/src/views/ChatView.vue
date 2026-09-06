<template>
  <div class="chat-view core-app-page core-app-page--chat">
    <div class="chat-layout">
      <!-- 侧边栏：会话列表 -->
      <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-header">
          <h2 v-if="!sidebarCollapsed" class="sidebar-brand">对话列表</h2>
          <button
            type="button"
            class="sidebar-toggle-btn"
            :aria-label="sidebarCollapsed ? '展开对话列表' : '收起对话列表'"
            :title="sidebarCollapsed ? '展开对话列表' : '收起对话列表'"
            @click="toggleSidebar"
          >
            <svg
              v-if="sidebarCollapsed"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
              <path d="M9 4v16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M13.5 10l2.5 2-2.5 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg
              v-else
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
              <path d="M9 4v16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M14.5 14l-2.5-2 2.5-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <template v-if="!sidebarCollapsed">
        <button type="button" class="btn-new-chat" @click="handleNewChat">
          <span class="btn-new-icon">+</span>
          <span>新建对话</span>
        </button>
        <div class="session-list">
            <div
              v-for="item in sidebarSessions"
              :key="item.id ?? `new-${item.key}`"
              class="session-item"
              :class="{ active: (item.id === null && currentSessionId === null) || (item.id !== null && currentSessionId === item.id) }"
              @click="selectSession(item)"
            >
              <span class="session-title">{{ item.title }}</span>
              <!-- 三点菜单按钮 -->
              <div v-if="item.id" class="session-menu-wrapper">
                <button
                  type="button"
                  class="session-menu-btn"
                  title="更多操作"
                  @click.stop="toggleMenu(item.id)"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="12" cy="6" r="2" />
                    <circle cx="12" cy="12" r="2" />
                    <circle cx="12" cy="18" r="2" />
                  </svg>
                </button>
                <!-- 下拉菜单 -->
                <div v-if="openMenuId === item.id" class="session-menu-dropdown">
                  <button
                    type="button"
                    class="session-menu-item delete"
                    @click.stop="handleDeleteSession(item.id)"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"/>
                    </svg>
                    <span>删除会话</span>
                  </button>
                </div>
              </div>
            </div>
            <div v-if="sidebarSessions.length === 0 && !loadingList" class="session-empty">
              暂无会话，点击「新建对话」开始
            </div>
            <div v-if="loadingList" class="session-loading">加载中…</div>
        </div>
        </template>
      </aside>

      <!-- 移动端抽屉打开时的半透明遮罩，点击关闭抽屉 -->
      <Transition name="sidebar-backdrop">
        <div
          v-if="!sidebarCollapsed"
          class="sidebar-backdrop"
          aria-hidden="true"
          @click="toggleSidebar"
        ></div>
      </Transition>

      <!-- 主区域：当前会话消息 + 输入 -->
      <div class="chat-body">
        <button
          v-if="sidebarCollapsed"
          type="button"
          class="mobile-sidebar-open"
          aria-label="打开会话列表"
          title="历史会话"
          @click="toggleSidebar"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
            <path d="M9 4v16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            <path d="M13.5 10l2.5 2-2.5 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div class="chat-main">
        <div ref="messagesEndRef" class="messages-wrap">
          <div v-if="messages.length === 0" class="welcome">
            <div class="welcome-title-wrap">
              <img
                class="welcome-star welcome-star--tl"
                :src="starShape1Url"
                alt=""
                aria-hidden="true"
              />
              <p class="welcome-title">启智 Mentor AI</p>
              <img
                class="welcome-star welcome-star--tr"
                :src="starShape2Url"
                alt=""
                aria-hidden="true"
              />
            </div>
            <p class="welcome-desc">智能对话，让你的教学工作更轻松</p>
          </div>
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-row"
            :class="msg.role"
          >
            <div class="message-bubble">
              <MessageBubble
                :role="msg.role"
                :content="msg.content"
                :attachments="msg.attachments"
              />
            </div>
          </div>
          <div v-if="typing" class="message-row assistant">
            <div class="message-bubble typing" :class="{ 'typing-with-hint': progressStatus || currentPlan }">
              <div v-if="currentPlan" class="typing-plan">
                <div class="typing-plan-label">📋 执行计划</div>
                <div class="typing-plan-content message-markdown" v-html="renderMarkdown(currentPlan)"></div>
              </div>
              <p v-if="progressStatus" class="typing-hint">{{ progressStatus }}</p>
              <div class="typing-dots-row">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
              </div>
            </div>
          </div>
        </div>

        <div class="input-area">
          <!-- 附件列表（发送前预览） -->
          <div v-if="attachments.length > 0" class="attachments-preview">
            <div
              v-for="att in attachments"
              :key="att.id"
              class="attachment-item"
              :class="{
                'is-uploading': att.status === 'uploading',
                'is-error': att.status === 'error',
              }"
            >
              <span class="attachment-badge">
                <span v-if="att.status === 'uploading'" class="attachment-spinner" aria-hidden="true"></span>
                <span v-else class="attachment-ext">{{ fileExtLabel(att.name) }}</span>
              </span>
              <span class="attachment-info">
                <span class="attachment-name" :title="att.name">{{ att.name }}</span>
                <span class="attachment-sub">
                  <template v-if="att.status === 'error'">{{ att.error || '上传失败' }}</template>
                  <template v-else-if="att.status === 'uploading'">上传中…</template>
                  <template v-else>{{ formatFileSize(att.size) }}</template>
                </span>
              </span>
              <button
                type="button"
                class="attachment-remove"
                :title="att.status === 'uploading' ? '上传中，无法移除' : '移除附件'"
                :disabled="att.status === 'uploading'"
                @click="removeAttachment(att.id)"
                aria-label="移除附件"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M3 3L9 9M9 3L3 9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
          </div>

          <div class="input-inner">
            <input
              ref="fileInputRef"
              type="file"
              style="display: none"
              :accept="CHAT_ATTACH_ACCEPT"
              multiple
              @change="handleFileSelect"
            />
            <textarea
              ref="textareaRef"
              v-model="inputText"
              class="input-textarea"
              placeholder="输入消息，与 AI 对话...（Enter 发送，Shift+Enter 换行）"
              @keydown="onInputKeydown"
            />
            <div class="input-actions">
              <button
                type="button"
                class="attach-btn"
                :disabled="sending"
                title="添加附件"
                @click="triggerFileSelect"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
              <button
                type="button"
                class="send-btn"
                :disabled="sending || (!inputText.trim() && attachments.length === 0)"
                @click="handleSend"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>

    <DeleteConfirmModal
      v-model="showDeleteSessionModal"
      title="删除会话"
      entity-kind="会话"
      :entity-name="deleteSessionEntityName"
      :pending="deleteSessionPending"
      @cancel="closeDeleteSessionModal"
      @confirm="confirmDeleteSession"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import {
  listSessions,
  getSession,
  deleteSession,
  uploadAttachment,
  type SessionSummary,
  type SessionDetail,
  type SessionHistoryMessage,
  type SessionMessage,
  type ChatAttachment,
} from '../api/chat'
import { COMMON_ATTACHMENT_EXTENSIONS, isExtensionAllowed } from '../api/attachment'
import { useChatStore, type ChatMessage } from '../stores/chat'
import {
  registerChatMessagesScrollToTop,
  unregisterChatMessagesScrollToTop,
} from '../utils/chatPageScroll'
import MessageBubble from '../components/MessageBubble.vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import { renderMarkdown } from '../utils/markdown'
import starShape1Url from '../../image_materials/star_shape1.png'
import starShape2Url from '../../image_materials/star_shape2.png'

/** 侧边栏一项：来自接口或本地「新会话」占位 */
interface SidebarItem {
  id: string | null
  title: string
  create_time?: string
  /** 仅 id 为 null 时用，用于 key */
  key?: string
}

// 会话状态搬到 Pinia store，让流式生成不被组件卸载/会话切换打断
const chatStore = useChatStore()
const {
  currentMessages: messages,
  isCurrentStreaming: sending,
  isCurrentTyping: typing,
  currentProgressStatus: progressStatus,
  currentPlan,
  currentSessionId,
} = storeToRefs(chatStore)

const inputText = ref('')
const error = ref('')
const messagesEndRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

/** 会话列表（来自后端） */
const sessionList = ref<SessionSummary[]>([])
/** 本地「新会话」占位：未发过消息时存在，发过或切换走则剔除 */
const newSessionPlaceholder = ref<SidebarItem | null>(null)
const loadingList = ref(false)

/** 附件列表 */
const attachments = ref<ChatAttachment[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

/** 当前打开菜单的会话 ID */
const openMenuId = ref<string | null>(null)

const showDeleteSessionModal = ref(false)
const sessionIdPendingDelete = ref<string | null>(null)
const sessionTitlePendingDelete = ref('')
const deleteSessionPending = ref(false)
const deleteSessionEntityName = computed(() => sessionTitlePendingDelete.value.trim() || '该会话')

/** 收起会话列表侧边栏（仅用于样式展示） */
// 桌面端默认打开；移动端（<=640px）默认收起，避免抽屉一开始就盖住主区。
const sidebarCollapsed = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 640px)').matches)

/** 与 COMMON_ATTACHMENT_EXTENSIONS 一致，并补充 MIME 便于系统文件选择器筛选 */
const CHAT_ATTACH_ACCEPT = [...COMMON_ATTACHMENT_EXTENSIONS, 'image/*', 'video/*'].join(',')
const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500MB

/** 侧边栏展示的会话列表 = 接口列表 + 若有则加一个「新会话」占位 */
const sidebarSessions = computed<SidebarItem[]>(() => {
  const list: SidebarItem[] = sessionList.value.map((s) => ({
    id: s.id,
    title: s.title || '未命名对话',
    create_time: s.create_time,
  }))
  if (newSessionPlaceholder.value) {
    list.unshift(newSessionPlaceholder.value)
  }
  return list
})

function genId() {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 滚动到底部。
 * @param smooth 是否带过渡动画；默认 false。
 *   流式增量会高频触发滚动，带 smooth 会把 50+ 个平滑动画排队，造成卡顿。
 *   仅在用户主动操作（发送消息、切换会话）时给平滑动画。
 */
function scrollToBottom(smooth = false) {
  nextTick(() => {
    const el = messagesEndRef.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

/** 滚动消息列表到顶部（供全局「返回顶部」按钮调用） */
function scrollMessagesToTop(smooth = false) {
  nextTick(() => {
    const el = messagesEndRef.value
    if (!el) return
    el.scrollTo({ top: 0, left: 0, behavior: smooth ? 'smooth' : 'auto' })
  })
}

/**
 * 用户离底部足够近时才视为「跟随最新消息」，此时流式增量到达继续滚到底部；
 * 一旦用户手动往上翻阅，就不再把视口强行拉回底部，避免打断阅读。
 */
const FOLLOW_BOTTOM_THRESHOLD_PX = 80
function isNearBottom(): boolean {
  const el = messagesEndRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= FOLLOW_BOTTOM_THRESHOLD_PX
}

/**
 * 把高频到达的流式增量合并到下一帧再滚动，避免一秒内触发几十次 scrollTo。
 * rAF 天然按浏览器刷新节奏限频（~16ms）。
 */
let followScrollRafId: number | null = null
function followScroll() {
  if (followScrollRafId != null) return
  followScrollRafId = requestAnimationFrame(() => {
    followScrollRafId = null
    if (isNearBottom()) scrollToBottom(false)
  })
}

function messageContent(msg: SessionMessage): string {
  const c = msg.content
  // 处理字符串
  if (typeof c === 'string') return c
  // 处理数组（如 ['你好', '！', '有什么可以帮助你的吗？']）
  if (Array.isArray(c)) return c.join('')
  // 处理 CardResponse 对象
  if (c && typeof c === 'object' && 'content' in c) return String((c as { content?: string }).content ?? '')
  return ''
}


/** 加载会话列表 */
async function loadSessionList() {
  loadingList.value = true
  error.value = ''
  try {
    sessionList.value = await listSessions()
  } catch (e) {
    console.error('[Chat] 加载会话列表失败', e)
    error.value = ''
  } finally {
    loadingList.value = false
  }
}

/** 选中某一项：若为「新会话」占位则清空消息；若有 id 则拉取会话详情 */
function selectSession(item: SidebarItem) {
  // 离开当前会话前，如果当前是空的新会话，则清除它
  clearNewPlaceholderIfEmpty()

  if (item.id === null) {
    currentSessionId.value = null
    return
  }
  currentSessionId.value = item.id
  // 拉取历史前不清空 store 中的消息：如果该会话正在流式生成，setMessages 会跳过覆盖，
  // 保证用户回到这条会话时能看到当前已生成的内容。
  getSession(item.id)
    .then((detail) => {
      const historyMsgs = detail.messages ?? []
      if (currentSessionId.value !== detail.id) return
      const mapped = (historyMsgs || []).map((m: SessionHistoryMessage) => ({
        id: genId(),
        role: m.role as ChatMessage['role'],
        content: typeof m.content === 'string' ? m.content : String(m.content ?? ''),
      }))
      chatStore.setMessages(detail.id, mapped)
      scrollToBottom(true)
    })
    .catch((e) => {
      const msg = e instanceof Error ? e.message : '加载会话失败'
      // 上线环境不在页面直接展示报错，保留 console 便于排查
      error.value = ''
      // 摘要（含会话 id 与错误信息），便于排查
      const summary = [
        '[智能对话] 获取会话详情失败',
        `会话 id: ${item.id}`,
        `错误: ${msg}`,
      ].join('\n')
      console.error(summary)
    })
}

/** 新会话：若当前已是新会话且从未发过消息，无需操作；否则增加占位并选中 */
function handleNewChat() {
  // 已处于空白新会话界面时，不在左侧新增占位项
  if (currentSessionId.value === null && messages.value.length === 0 && !newSessionPlaceholder.value) {
    return
  }
  if (newSessionPlaceholder.value) {
    currentSessionId.value = null
    chatStore.clearNewChat()
    return
  }
  newSessionPlaceholder.value = {
    id: null,
    title: '新会话',
    key: `new-${Date.now()}`,
  }
  currentSessionId.value = null
  chatStore.clearNewChat()
}

/** 若当前选中的是「新会话」且一条消息都没发，离开时剔除占位（不请求后端） */
function clearNewPlaceholderIfEmpty() {
  if (!newSessionPlaceholder.value) return
  if (currentSessionId.value !== null) return
  if (messages.value.length > 0) return
  newSessionPlaceholder.value = null
}

/** 切换菜单显示状态 */
function toggleMenu(id: string) {
  openMenuId.value = openMenuId.value === id ? null : id
}

/** 关闭菜单 */
function closeMenu() {
  openMenuId.value = null
}

function toggleSidebar() {
  // 收起时关闭会话菜单下拉，避免遮挡
  openMenuId.value = null
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function closeDeleteSessionModal() {
  if (deleteSessionPending.value) return
  showDeleteSessionModal.value = false
  sessionIdPendingDelete.value = null
  sessionTitlePendingDelete.value = ''
}

/** 删除会话：先打开确认弹窗 */
function handleDeleteSession(id: string) {
  if (!id) return
  closeMenu()
  const session = sessionList.value.find((s) => s.id === id)
  sessionIdPendingDelete.value = id
  sessionTitlePendingDelete.value = session?.title?.trim() || '未命名对话'
  showDeleteSessionModal.value = true
}

async function confirmDeleteSession() {
  const id = sessionIdPendingDelete.value
  if (!id || deleteSessionPending.value) return
  deleteSessionPending.value = true
  try {
    await deleteSession(id)
    showDeleteSessionModal.value = false
    sessionIdPendingDelete.value = null
    sessionTitlePendingDelete.value = ''
    sessionList.value = sessionList.value.filter((s) => s.id !== id)
    chatStore.dropSession(id)
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      chatStore.clearNewChat()
      if (!newSessionPlaceholder.value) {
        newSessionPlaceholder.value = {
          id: null,
          title: '新会话',
          key: `new-${Date.now()}`,
        }
      }
    }
  } catch (e) {
    console.error('[Chat] 删除会话失败', e)
    error.value = ''
  } finally {
    deleteSessionPending.value = false
  }
}

/** 触发文件选择 */
function triggerFileSelect() {
  fileInputRef.value?.click()
}

/** 处理文件选择 */
async function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return

  for (const file of Array.from(files)) {
    await addAttachment(file)
  }

  // 清空 input，允许重复选择同一文件
  input.value = ''
}

/** 添加附件 */
async function addAttachment(file: File) {
  if (!isExtensionAllowed(file)) {
    error.value = '不支持的文件类型，请上传图片、视频或常见文档格式'
    return
  }
  if (file.size > MAX_FILE_SIZE) {
    error.value = '单个附件不能超过 500MB'
    return
  }

  const attachment: ChatAttachment = {
    id: genId(),
    name: file.name,
    size: file.size,
    status: 'uploading',
  }
  attachments.value.push(attachment)

  try {
    const path = await uploadAttachment(file)
    const idx = attachments.value.findIndex((a) => a.id === attachment.id)
    if (idx !== -1) {
      attachments.value[idx] = { ...attachments.value[idx]!, status: 'done', path }
    }
  } catch (e) {
    const idx = attachments.value.findIndex((a) => a.id === attachment.id)
    if (idx !== -1) {
      attachments.value[idx] = {
        ...attachments.value[idx]!,
        status: 'error',
        error: e instanceof Error ? e.message : '上传失败',
      }
    }
  }
}

/** 移除附件 */
function removeAttachment(id: string) {
  attachments.value = attachments.value.filter((a) => a.id !== id)
}

/** 格式化文件大小 */
function formatFileSize(size: number): string {
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(1) + ' MB'
}

/** 文件扩展名大写（最多 4 个字符），用作附件卡片上的小徽标 */
function fileExtLabel(name: string): string {
  const dot = name.lastIndexOf('.')
  if (dot < 0 || dot === name.length - 1) return 'FILE'
  const ext = name.slice(dot + 1).toUpperCase()
  return ext.length > 4 ? ext.slice(0, 4) : ext
}

async function handleSend() {
  const text = inputText.value.trim()
  if ((!text && attachments.value.length === 0) || sending.value) return
  error.value = ''
  inputText.value = ''

  // 构建消息内容（包含附件信息）
  const doneAttachments = attachments.value.filter((a) => a.status === 'done')
  let messageContent = text
  if (doneAttachments.length > 0) {
    const fileNames = doneAttachments.map((a) => `[${a.name}]`).join(' ')
    messageContent = text ? `${text}\n\n${fileNames}` : fileNames
  }

  // 清空附件
  const filePaths = doneAttachments.map((a) => a.path!).filter(Boolean)
  attachments.value = []

  const sessionIdToSend = currentSessionId.value

  // 把流式请求交给 store：即使此时用户切到别的路由或会话，
  // 增量依旧会写入对应会话的 state，回到那条会话时可直接看到当前进度。
  chatStore.sendMessage({
    sessionId: sessionIdToSend,
    query: messageContent,
    filePaths,
    // 附件元数据（name/size）带到用户消息上，MessageBubble 据此渲染附件卡片，
    // 避免仅依赖 content 中「[文件名]」的回退解析。
    attachments: doneAttachments.length > 0
      ? doneAttachments.map((a) => ({ name: a.name, size: a.size }))
      : undefined,
    onSessionIdReceived(newId) {
      if (newSessionPlaceholder.value) {
        newSessionPlaceholder.value = null
      }
      // 重新加载会话列表，确保拿到后端生成的正确标题
      loadSessionList()
    },
    onError(err) {
      console.error('[Chat] 发送消息失败', err)
      error.value = ''
    },
  })
  // 首条用户消息已经入栈，立即滚到底部（用户主动操作，可以带平滑动画）；
  // 后续流式增量由 watch(messages) 里的 followScroll() 在 rAF 内合并滚动。
  scrollToBottom(true)
}

/**
 * 流式增量到达时合并跟随滚动。
 * - 用浅依赖（messages 长度 + 末条内容长度）代替 deep watch，避免每次增量都对整个数组做深度对比。
 * - followScroll() 内部用 requestAnimationFrame 合并高频触发。
 */
watch(
  () => {
    const arr = messages.value
    const last = arr.length > 0 ? arr[arr.length - 1] : null
    return [arr.length, last?.content.length ?? 0]
  },
  () => followScroll()
)

/** 切换会话时，若从「新会话」切走且未发过消息，剔除占位 */
watch(currentSessionId, (id, oldId) => {
  if (oldId === null && id !== null) clearNewPlaceholderIfEmpty()
})

function onInputKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter') return
  if (e.shiftKey) {
    // Shift+Enter：换行，使用浏览器默认行为
    return
  }
  e.preventDefault()
  handleSend()
}

onMounted(() => {
  registerChatMessagesScrollToTop((opts) => scrollMessagesToTop(opts?.smooth ?? true))
  loadSessionList()
  // 点击外部关闭菜单
  document.addEventListener('click', closeMenu)
})

onUnmounted(() => {
  unregisterChatMessagesScrollToTop()
  document.removeEventListener('click', closeMenu)
})
</script>

<style scoped>
/* 页面壳层与顶栏/内容区边距见 assets/core-page-layout.css（.core-app-page--chat） */

.chat-view.core-app-page {
  display: flex;
  flex-direction: column;
}

.chat-view.core-app-page--chat .chat-layout {
  padding-top: var(--toolbar-top-gap);
}

.chat-layout {
  display: flex;
  align-items: stretch;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
  flex: 1 1 auto;
}

.sidebar {
  --sidebar-width: 272px;
  width: var(--sidebar-width);
  flex-shrink: 0;
  align-self: stretch;
  box-sizing: border-box;
  padding: 16px;
  background: rgba(255, 255, 255, 0.3);
  border: 1px solid #e0e0e0;
  border-radius: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
  transition:
    width 0.28s cubic-bezier(0.4, 0, 0.2, 1),
    padding 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.collapsed {
  --sidebar-width: 52px;
  width: var(--sidebar-width);
  padding: 12px 8px;
  gap: 0;
  align-items: center;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  width: 100%;
  min-width: 0;
}

.sidebar.collapsed .sidebar-header {
  justify-content: center;
}

.sidebar-brand {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
  color: #111;
  line-height: 1.35;
  text-align: left;
}

.sidebar-toggle-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #111;
  cursor: pointer;
  transition: background-color 0.2s, opacity 0.2s;
}

.sidebar-toggle-btn:hover {
  background: rgba(0, 0, 0, 0.04);
}

.sidebar-toggle-btn:active {
  background: rgba(0, 0, 0, 0.08);
}

.session-list-heading {
  margin: 0;
  font-size: 14px;
  font-weight: 400;
  color: #757575;
  line-height: 1.4;
  text-align: left;
  flex-shrink: 0;
}

/* 新建对话按钮——与其它页面的 .action-btn 同款白底胶囊 */
.btn-new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: 8px 16px;
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-new-chat:hover {
  border-color: #C5D9FF;
  background: #f8f9ff;
}

.btn-new-icon {
  font-size: 16px;
  line-height: 1;
  color: #5B8DEE;
}

.session-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: background 0.2s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.55);
}

.session-item.active {
  background: #f8f9ff;
  color: #1a73e8;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 会话菜单 */
.session-menu-wrapper {
  position: relative;
  flex-shrink: 0;
}

.session-menu-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #666;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, background-color 0.2s;
}

.session-item:hover .session-menu-btn {
  opacity: 1;
}

.session-menu-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}

.session-item.active .session-menu-btn {
  color: #1a73e8;
}

.session-menu-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  min-width: 120px;
  overflow: hidden;
}

.session-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: transparent;
  border: none;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.2s;
}

.session-menu-item:hover {
  background: #f5f5f5;
}

.session-menu-item.delete {
  color: #d32f2f;
}

.session-menu-item.delete:hover {
  background: #ffebee;
}

.session-empty,
.session-loading {
  padding: 12px 0;
  font-size: 13px;
  color: #999;
  text-align: center;
}

.chat-body {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  justify-content: center;
  align-items: stretch;
  overflow: hidden;
  position: relative;
}

.chat-main {
  width: 100%;
  max-width: 900px;
  min-height: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-wrap {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 24px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.welcome {
  text-align: center;
  padding: 48px 24px;
  /* 消息为空时独占 messages-wrap（flex column），用 auto 外边距把文案在垂直方向上
     顶上的空白 / 底部空白平分，实现视觉居中；text-align: center 负责水平居中。
     在此基础上略微上移（ChatGPT 风格的欢迎页位置），避免文字压得过低。 */
  margin: auto 0;
  transform: translateY(-40px);
}

.welcome-title-wrap {
  position: relative;
  display: inline-block;
  max-width: 100%;
  margin: 0 0 14px 0;
  padding: 18px 44px 0;
  box-sizing: border-box;
}

.welcome-title {
  font-size: 42px;
  font-weight: 700;
  color: #001081;
  margin: 0;
  line-height: 1.35;
}

.welcome-star {
  position: absolute;
  pointer-events: none;
  user-select: none;
  object-fit: contain;
}

.welcome-star--tl {
  top: 0;
  left: 0;
  height: 32px;
  width: auto;
  transform: translate(-28%, -18%);
}

.welcome-star--tr {
  top: 0;
  right: 0;
  height: 28px;
  width: auto;
  transform: translate(22%, -12%);
}

.welcome-desc {
  font-size: 25px;
  font-weight: 700;
  color: #001081;
  margin: 0;
  line-height: 1.5;
}

.message-row {
  display: flex;
  width: 100%;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 85%;
  padding: 14px 18px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-row.user .message-bubble {
  background-color: #C5D9FF;
  color: #333;
  border-bottom-right-radius: 4px;
}

.message-row.assistant .message-bubble {
  background-color: #fff;
  color: #333;
  border: 1px solid #e0e0e0;
  border-bottom-left-radius: 4px;
}

.message-bubble.typing {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 16px 20px;
}

.message-bubble.typing.typing-with-hint {
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.typing-plan {
  margin: 0 0 10px;
  padding: 10px 14px;
  background: #f5f5f5;
  border-radius: 8px;
  border-left: 3px solid #9e9e9e;
  max-width: 100%;
}
.typing-plan-label {
  font-size: 12px;
  font-weight: 600;
  color: #757575;
  margin-bottom: 6px;
  letter-spacing: 0.5px;
}
.typing-plan-content {
  font-size: 13px;
  line-height: 1.6;
  color: #666;
}
.typing-plan-content.message-markdown {
  white-space: normal;
}
.typing-plan-content.message-markdown :deep(ol),
.typing-plan-content.message-markdown :deep(ul) {
  margin: 4px 0;
  padding-left: 1.25em;
}
.typing-plan-content.message-markdown :deep(li) {
  margin: 3px 0;
  line-height: 1.5;
}
.typing-plan-content.message-markdown :deep(p) {
  margin: 4px 0;
}
.typing-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #5c5c5c;
  white-space: pre-wrap;
  word-break: break-word;
  max-width: 100%;
}

.typing-dots-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #999;
  animation: typing-bounce 1.4s ease-in-out infinite both;
}

.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1.1); opacity: 1; }
}

.input-area {
  flex-shrink: 0;
  padding-top: 12px;
}

.attachments-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding: 0 4px;
}

.attachment-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  max-width: 280px;
  padding: 6px 8px 6px 6px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.attachment-item.is-uploading {
  border-color: #bcd0ff;
  background: #f6f9ff;
}

.attachment-item.is-error {
  border-color: #f4c3c3;
  background: #fff5f5;
}

.attachment-badge {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #5B8DEE;
  color: #fff;
}
.attachment-item.is-uploading .attachment-badge {
  background: #bcd0ff;
  color: #5B8DEE;
}
.attachment-item.is-error .attachment-badge {
  background: #d32f2f;
}

.attachment-ext {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.attachment-spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-top-color: transparent;
  animation: attachment-spin 0.8s linear infinite;
}
@keyframes attachment-spin {
  to { transform: rotate(360deg); }
}

.attachment-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}

.attachment-name {
  font-size: 13px;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.attachment-sub {
  margin-top: 2px;
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.attachment-item.is-error .attachment-sub {
  color: #d32f2f;
}

.attachment-remove {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: #999;
  cursor: pointer;
  padding: 0;
  margin-left: 2px;
  transition: background-color 0.15s, color 0.15s;
}

.attachment-remove:hover:not(:disabled) {
  background: #f0f0f0;
  color: #333;
}

.attachment-remove:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.attach-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: #666;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.attach-btn:hover:not(:disabled) {
  background: #f0f0f0;
  color: #333;
}

.attach-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-inner {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  height: 150px;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 24px;
  padding: 14px 16px 12px;
  transition: border-color 0.2s;
}

.input-inner:focus-within {
  border-color: #C5D9FF;
  box-shadow: 0 0 0 2px rgba(197, 217, 255, 0.3);
}

.input-textarea {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  overflow-y: auto;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  background: transparent;
  padding: 5px;
  display: block;
  box-sizing: border-box;
}

.input-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.input-textarea::placeholder {
  font-family: inherit;
  font-size: inherit;
  color: #999;
}

.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1358e4;
  color: #fff;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: background-color 0.2s, opacity 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: #0f4bc4;
}

.send-btn:disabled {
  background: #a8c4f5;
  cursor: not-allowed;
}

.input-error {
  font-size: 13px;
  color: #d32f2f;
  margin: 8px 0 0 0;
}

/* 移动端遮罩淡入淡出 */
.sidebar-backdrop-enter-active,
.sidebar-backdrop-leave-active {
  transition: opacity 0.25s ease;
}

.sidebar-backdrop-enter-from,
.sidebar-backdrop-leave-to {
  opacity: 0;
}

/* 桌面端默认隐藏移动端遮罩与移动端打开按钮 */
.sidebar-backdrop {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .sidebar-backdrop-enter-active,
  .sidebar-backdrop-leave-active {
    transition: none !important;
  }
}
.mobile-sidebar-open {
  display: none;
}

/* ========== 移动端适配 ========== */
@media (max-width: 768px) {
  .message-bubble {
    max-width: 92% !important;
  }
}

@media (max-width: 640px) {
  /* 抽屉打开时的遮罩 */
  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 56px 0 0 0;
    background: rgba(0, 0, 0, 0.32);
    z-index: 35;
  }

  /* 侧边栏改为 off-canvas 抽屉：默认隐藏在屏幕左外侧，sidebarCollapsed 控制显隐 */
  .sidebar {
    position: fixed;
    top: 56px;
    left: 0;
    bottom: 0;
    width: min(300px, 82vw);
    z-index: 40;
    background: rgba(255, 255, 255, 0.96);
    box-sizing: border-box;
    border: 1px solid #e0e0e0;
    border-radius: 0 10px 10px 0;
    box-shadow: 4px 0 16px rgba(0, 0, 0, 0.12);
    transform: translateX(0);
    /* 移动端用滑入滑出；宽度不参与过渡，避免与 transform 冲突 */
    transition:
      transform 0.28s cubic-bezier(0.4, 0, 0.2, 1),
      box-shadow 0.28s ease;
  }

  .sidebar.collapsed {
    --sidebar-width: min(300px, 82vw);
    width: min(300px, 82vw);
    padding: 16px;
    gap: 16px;
    align-items: stretch;
    transform: translateX(-105%);
    pointer-events: none;
    box-shadow: none;
  }

  .sidebar.collapsed .sidebar-header {
    justify-content: space-between;
  }
  /* 移动端：侧栏收起时，在对话区左上角打开会话列表 */
  .chat-body .mobile-sidebar-open {
    display: inline-flex;
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 5;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    margin: 0;
    padding: 0;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.92);
    color: #333;
    cursor: pointer;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }
  .chat-body .mobile-sidebar-open:hover {
    background: #fff;
  }
  /* 三点菜单按钮在触屏端常显（不再 :hover 才显示） */
  .session-menu-btn {
    opacity: 1;
  }
  .chat-body {
    position: relative;
  }

  .chat-main {
    max-width: 100%;
  }
  .messages-wrap {
    padding: 16px 4px 12px;
    gap: 16px;
  }
}

@media (max-width: 500px) {
  .welcome {
    padding: 32px 16px;
  }

  .welcome-title-wrap {
    padding: 14px 32px 0;
  }

  .welcome-title {
    font-size: 40px;
  }

  .welcome-desc {
    font-size: 22px;
  }

  .welcome-star--tl {
    height: 52px;
  }

  .welcome-star--tr {
    height: 46px;
  }
}
</style>
