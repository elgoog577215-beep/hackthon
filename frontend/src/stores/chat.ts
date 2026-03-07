/**
 * 聊天 Store - 聊天历史、AI 问答状态
 * 从 course.ts 抽取的聊天相关状态和简单方法。
 *
 * 注意：askQuestion 等重方法因深度依赖 courseStore 状态（currentNode, courseTree, nodes, notes），
 * 在 10.7 精简 course.ts 时再迁移。当前仅抽取状态和简单 action。
 */
import { defineStore } from 'pinia'
import type { ChatMessage, AIContent, Annotation } from './types'

export const useChatStore = defineStore('chat', {
  state: () => ({
    chatHistory: [] as ChatMessage[],
    chatLoading: false,
    chatAbortController: null as AbortController | null,
    pendingChatInput: '' as string,
    activeAnnotation: null as Annotation | null,
  }),
  actions: {
    addMessage(type: 'user' | 'ai', content: string | AIContent) {
      this.chatHistory.push({ type, content })
    },

    cancelChat() {
      if (this.chatAbortController) {
        this.chatAbortController.abort()
      }
    },

    clearChat() {
      this.chatHistory = []
      this.activeAnnotation = null
    },

    setPendingChatInput(text: string) {
      this.pendingChatInput = text
    },
  },
})
