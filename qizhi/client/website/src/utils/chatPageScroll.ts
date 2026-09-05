/** 智能对话页消息区滚动：供 App 全局「返回顶部」在 /chat 路由下调用 */

export type ChatMessagesScrollOptions = { smooth?: boolean }

type ScrollToTopFn = (options?: ChatMessagesScrollOptions) => void

let scrollMessagesToTop: ScrollToTopFn | null = null

export function registerChatMessagesScrollToTop(fn: ScrollToTopFn) {
  scrollMessagesToTop = fn
}

export function unregisterChatMessagesScrollToTop() {
  scrollMessagesToTop = null
}

export function chatMessagesScrollToTop(options?: ChatMessagesScrollOptions) {
  scrollMessagesToTop?.(options)
}
