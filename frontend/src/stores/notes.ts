/**
 * 笔记 Store - 笔记管理
 * 从 course.ts 抽取的笔记相关状态和方法。
 */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import type { Note, Annotation } from './types'
import { useCourseStore } from './course'

// 复用 course.ts 中的工具函数
const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_').trim()
const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
}

export const useNoteStore = defineStore('notes', {
  state: () => ({
    notes: [] as Note[],
    focusNoteId: null as string | null,
  }),
  getters: {
    getNotesByNodeId: (state) => (nodeId: string) => state.notes.filter(n => n.nodeId === nodeId),
  },
  actions: {
    addNote(note: Note) {
      this.notes.push(note)
    },

    async createNote(note: Note) {
      this.addNote(note)
      try {
        const anno: Partial<Annotation> = {
          anno_id: note.id,
          node_id: note.nodeId,
          question: note.sourceType === 'ai' ? 'AI Assistant Note' : 'User Note',
          answer: note.content,
          anno_summary: note.summary || (note.content.length > 50 ? note.content.slice(0, 50) + '...' : note.content),
          quote: note.quote,
          source_type: note.sourceType || 'user'
        }
        if (anno.source_type !== 'format') {
          await http.post(`/api/annotations`, anno)
          ElMessage.success('笔记已保存')
        }
      } catch (e) {
        console.error('Failed to persist note', e)
        ElMessage.error('保存失败')
      }
    },

    async updateNote(id: string, content: string) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.content = content
        try {
          await http.put(`/api/annotations/${id}`, { content })
        } catch (e) {
          console.error('Failed to update note persistence', e)
          ElMessage.warning('笔记保存失败，请重试')
        }
      }
    },

    async deleteNote(id: string) {
      const index = this.notes.findIndex(n => n.id === id)
      if (index !== -1) {
        this.notes.splice(index, 1)
        try {
          await http.delete(`/api/annotations/${id}`)
        } catch (e) {
          console.error('Failed to delete note persistence', e)
        }
      }
    },

    // ========== Tag & Category Management ==========
    async updateNoteTags(id: string, tags: string[]) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.tags = tags
        try {
          await http.put(`/api/annotations/${id}/tags`, { tags })
        } catch (e) {
          console.error('Failed to update note tags', e)
        }
      }
    },

    async updateNoteCategory(id: string, category: string) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.category = category
        try {
          await http.put(`/api/annotations/${id}/category`, { category })
        } catch (e) {
          console.error('Failed to update note category', e)
        }
      }
    },

    async updateNotePriority(id: string, priority: 'low' | 'medium' | 'high') {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.priority = priority
        try {
          await http.put(`/api/annotations/${id}/priority`, { priority })
        } catch (e) {
          console.error('Failed to update note priority', e)
        }
      }
    },

    getAllTags(): string[] {
      const tagSet = new Set<string>()
      this.notes.forEach(note => {
        note.tags?.forEach(tag => tagSet.add(tag))
      })
      return Array.from(tagSet).sort()
    },

    getAllCategories(): string[] {
      const categorySet = new Set<string>()
      this.notes.forEach(note => {
        if (note.category) categorySet.add(note.category)
      })
      return Array.from(categorySet).sort()
    },

    getNotesByTag(tag: string): Note[] {
      return this.notes.filter(note => note.tags?.includes(tag))
    },

    getNotesByCategory(category: string): Note[] {
      return this.notes.filter(note => note.category === category)
    },

    getNotesByPriority(priority: 'low' | 'medium' | 'high'): Note[] {
      return this.notes.filter(note => note.priority === priority)
    },

    scrollToNote(noteId: string) {
      this.focusNoteId = null
      setTimeout(() => {
        this.focusNoteId = noteId
      }, 10)
    },

    // ========== Export Functions ==========
    exportNotesToMarkdown(): string {
      const notes = this.notes
      if (notes.length === 0) {
        return '# 学习笔记\n\n暂无笔记内容。'
      }

      let markdown = '# 学习笔记导出\n\n'
      markdown += `导出时间：${dayjs().format('YYYY-MM-DD HH:mm:ss')}\n\n`
      markdown += `---\n\n`

      const groupedNotes = {
        user: notes.filter(n => n.sourceType === 'user' || !n.sourceType),
        ai: notes.filter(n => n.sourceType === 'ai'),
        wrong: notes.filter(n => n.sourceType === 'wrong'),
        format: notes.filter(n => n.sourceType === 'format')
      }

      if (groupedNotes.wrong.length > 0) {
        markdown += '## 📝 错题记录\n\n'
        groupedNotes.wrong.forEach((note, idx) => {
          markdown += `### 错题 ${idx + 1}\n\n`
          markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
          if (note.quote) {
            markdown += `**题目**：\n> ${note.quote}\n\n`
          }
          markdown += `${note.content}\n\n`
          markdown += `---\n\n`
        })
      }

      if (groupedNotes.ai.length > 0) {
        markdown += '## 💬 AI 问答记录\n\n'
        groupedNotes.ai.forEach((note, idx) => {
          markdown += `### 问答 ${idx + 1}\n\n`
          markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
          if (note.quote) {
            markdown += `**引用**：\n> ${note.quote}\n\n`
          }
          markdown += `${note.content}\n\n`
          markdown += `---\n\n`
        })
      }

      if (groupedNotes.user.length > 0) {
        markdown += '## ✏️ 个人笔记\n\n'
        groupedNotes.user.forEach((note, idx) => {
          markdown += `### 笔记 ${idx + 1}\n\n`
          markdown += `**时间**：${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
          if (note.quote) {
            markdown += `**引用**：\n> ${note.quote}\n\n`
          }
          markdown += `${note.content}\n\n`
          markdown += `---\n\n`
        })
      }

      return markdown
    },

    exportNotesToJSON(): string {
      const exportData = {
        exportTime: dayjs().format('YYYY-MM-DD HH:mm:ss'),
        totalNotes: this.notes.length,
        notes: this.notes.map(note => ({
          ...note,
          createdAtFormatted: dayjs(note.createdAt).format('YYYY-MM-DD HH:mm:ss')
        }))
      }
      return JSON.stringify(exportData, null, 2)
    },

    downloadNotes(format: 'markdown' | 'json' = 'markdown') {
      const content = format === 'markdown' ? this.exportNotesToMarkdown() : this.exportNotesToJSON()
      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
      const filename = `学习笔记_${dayjs().format('YYYYMMDD')}.${format === 'markdown' ? 'md' : 'json'}`
      downloadBlob(blob, filename)
    },

    /**
     * 导出筛选后的笔记为 Markdown，按节点分组。
     * 需要从 courseStore 获取节点信息。
     */
    exportNotesMarkdown(notes: Note[], options: { filterLabel: string, query?: string }) {
      if (!notes || notes.length === 0) {
        ElMessage.warning('当前没有可导出的笔记')
        return
      }
      // Lazy import to avoid circular dependency
      const courseStore = useCourseStore()

      const courseName = courseStore.courseList.find((c: { course_id: string; course_name: string }) => c.course_id === courseStore.currentCourseId)?.course_name || 'My Notes'
      let md = `# ${courseName}\n\n`
      md += `> 导出时间：${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
      md += `> 类型：${options.filterLabel}\n\n`
      if (options.query) {
        md += `> 搜索：${options.query}\n\n`
      }
      md += `> 条目数：${notes.length}\n\n---\n\n`

      const linearNodes = courseStore.getLinearNodes(courseStore.courseTree)
      const nodeOrder = new Map<string, number>(linearNodes.map((n: { node_id: string }, i: number) => [n.node_id, i]))
      const nodeNameMap = new Map(linearNodes.map((n: { node_id: string; node_name: string }) => [n.node_id, n.node_name]))

      notes.sort((a, b) => {
        const orderA = nodeOrder.get(a.nodeId) ?? -1
        const orderB = nodeOrder.get(b.nodeId) ?? -1
        if (orderA !== orderB) return orderA - orderB
        return a.createdAt - b.createdAt
      })

      const groupedNotes = new Map<string, Note[]>()
      notes.forEach(note => {
        const nodeId = note.nodeId
        if (!groupedNotes.has(nodeId)) groupedNotes.set(nodeId, [])
        groupedNotes.get(nodeId)?.push(note)
      })

      groupedNotes.forEach((noteItems, nodeId) => {
        md += `## ${nodeNameMap.get(nodeId) || '未知章节'}\n\n`
        noteItems.forEach(note => {
          if (note.quote) {
            md += `> ${note.quote}\n\n`
          }
          md += `${note.content}\n\n`
          const typeLabel = note.sourceType === 'ai' ? 'AI 助手' : '笔记'
          md += `> — *${typeLabel} · ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}*\n\n---\n\n`
        })
      })

      const filename = `${sanitizeFileName(courseName)}_${options.filterLabel}_${dayjs().format('YYYYMMDD_HHmmss')}.md`
      downloadBlob(new Blob([md], { type: 'text/markdown' }), filename)
      ElMessage.success('Markdown 导出成功')
    },
  },
})
