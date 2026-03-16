/**
 * 草稿 Store - 测验答题时的文字草稿和图画草稿
 * 临时数据，不持久化到 localStorage。提交测验后错题草稿转移到 reviewStore，其余丢弃。
 */
import { defineStore } from 'pinia'

export const useDraftStore = defineStore('draft', {
  state: () => ({
    textDrafts: {} as Record<number, string>,
    drawingDrafts: {} as Record<number, string>, // dataURL
  }),
  actions: {
    setTextDraft(index: number, content: string) {
      this.textDrafts[index] = content
    },
    getTextDraft(index: number): string {
      return this.textDrafts[index] || ''
    },
    setDrawingDraft(index: number, dataURL: string) {
      this.drawingDrafts[index] = dataURL
    },
    getDrawingDraft(index: number): string {
      return this.drawingDrafts[index] || ''
    },
    clearAll() {
      this.textDrafts = {}
      this.drawingDrafts = {}
    },
  },
})
