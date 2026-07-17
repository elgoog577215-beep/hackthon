/**
 * 笔记 Store - 笔记管理
 * 从 course.ts 抽取的笔记相关状态和方法。
 */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import type { LearningRecord, LearningRecordType, Note } from './types'
import { useCourseStore } from './course'
import { useLearningProgressStore } from './learningProgress'
import logger from '../utils/logger'

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

const refreshLearningRuntime = async (courseId: string, nodeId?: string) => {
  if (!courseId) return
  await useLearningProgressStore().loadRuntime(courseId, nodeId).catch(error => {
    logger.warn('Learning runtime refresh deferred', error)
  })
}

const recordDraftPrefix = 'learning_record_draft_v1:'
const recordDraftKey = (courseId: string, recordId: string) => `${recordDraftPrefix}${courseId}:${recordId}`
const persistRecordDraft = (courseId: string, note: Note) => {
  localStorage.setItem(recordDraftKey(courseId, note.id), JSON.stringify({ note, saved_at: new Date().toISOString() }))
}
const clearRecordDraft = (courseId: string, recordId: string) => localStorage.removeItem(recordDraftKey(courseId, recordId))
const restoreRecordDrafts = (courseId: string): Note[] => {
  const prefix = `${recordDraftPrefix}${courseId}:`
  const drafts: Note[] = []
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index)
    if (!key?.startsWith(prefix)) continue
    try {
      const note = JSON.parse(localStorage.getItem(key) || 'null')?.note as Note | undefined
      if (note?.id) drafts.push({ ...note, syncState: 'local_only' })
    } catch {
      localStorage.removeItem(key)
    }
  }
  return drafts
}

const recordToNote = (record: LearningRecord): Note => ({
  id: record.record_id,
  nodeId: record.node_id,
  highlightId: `hl-${record.record_id}`,
  quote: record.quote || '',
  content: record.content || '',
  summary: record.title || '',
  title: record.title || '',
  color: record.record_type === 'issue' ? 'red' : record.record_type === 'review_task' ? 'orange' : record.record_type === 'bookmark' ? 'blue' : 'amber',
  createdAt: Date.parse(record.created_at) || Date.now(),
  sourceType: record.origin?.startsWith('assistant') || record.origin === 'legacy_ai_annotation' ? 'ai' : 'user',
  tags: record.tags || [],
  category: record.category || '',
  priority: record.priority || 'medium',
  recordType: record.record_type,
  status: record.status,
  revision: record.revision,
  origin: record.origin,
  dueAt: record.due_at,
  migrationStatus: record.migration_status,
  anchor: record.anchor,
  metadata: record.metadata,
  syncState: 'saved',
})

export const useNoteStore = defineStore('notes', {
  state: () => ({
    notes: [] as Note[],
    focusNoteId: null as string | null,
    courseId: '',
    loading: false,
  }),
  getters: {
    getNotesByNodeId: (state) => (nodeId: string) => state.notes.filter(n => n.nodeId === nodeId),
  },
  actions: {
    addNote(note: Note) {
      this.notes.push(note)
    },

    async loadCourseRecords(courseId: string) {
      if (!courseId) return []
      this.loading = true
      this.courseId = courseId
      try {
        const migrationKey = `learning_records_legacy_migrated_v1:${courseId}`
        if (!localStorage.getItem(migrationKey)) {
          await http.post(`/api/courses/${courseId}/learning-records/migrate-legacy-annotations`)
          localStorage.setItem(migrationKey, new Date().toISOString())
        }
        const res = await http.get(`/api/courses/${courseId}/learning-records`)
        const serverNotes: Note[] = (res.data?.records || [])
          .filter((record: LearningRecord) => record.status !== 'archived')
          .map(recordToNote)
        const drafts = restoreRecordDrafts(courseId)
        const byId = new Map(serverNotes.map((note: Note) => [note.id, note]))
        for (const draft of drafts) byId.set(draft.id, { ...(byId.get(draft.id) || {}), ...draft })
        this.notes = [...byId.values()]
        return this.notes
      } catch (error) {
        logger.error('Failed to load learning records', error)
        return []
      } finally {
        this.loading = false
      }
    },

    async createNote(note: Note) {
      if (note.sourceType === 'format') {
        this.addNote(note)
        return note
      }
      const courseStore = useCourseStore()
      const courseId = this.courseId || courseStore.currentCourseId
      if (!courseId) return null
      const existingIndex = this.notes.findIndex(item => item.id === note.id)
      const optimistic = { ...note, syncState: 'saving' as const }
      if (existingIndex >= 0) this.notes[existingIndex] = optimistic
      else this.notes.push(optimistic)
      persistRecordDraft(courseId, optimistic)
      try {
        const res = await http.post(`/api/courses/${courseId}/learning-records`, {
          record_id: note.id,
          record_type: note.recordType || 'note',
          status: note.status,
          node_id: note.nodeId,
          node_name: courseStore.nodes.find(node => node.node_id === note.nodeId)?.node_name || '',
          quote: note.quote || '',
          title: note.title || note.summary || '',
          content: note.content || '',
          origin: note.origin || (note.sourceType === 'ai' ? 'assistant_saved' : 'user'),
          priority: note.priority || 'medium',
          tags: note.tags || [],
          category: note.category || '',
          due_at: note.dueAt,
          anchor: note.anchor,
          metadata: note.metadata,
        })
        const saved = recordToNote(res.data)
        const index = this.notes.findIndex(item => item.id === saved.id)
        if (index >= 0) this.notes[index] = saved
        else this.notes.push(saved)
        clearRecordDraft(courseId, saved.id)
        await refreshLearningRuntime(courseId, saved.nodeId)
        ElMessage.success(saved.recordType === 'note' ? '笔记已保存' : '已加入稍后处理')
        return saved
      } catch (e) {
        logger.error('Failed to persist learning record', e)
        const index = this.notes.findIndex(item => item.id === note.id)
        if (index >= 0) this.notes[index] = { ...this.notes[index]!, syncState: 'local_only' }
        ElMessage.error('保存失败')
        return null
      }
    },

    async createLater(recordType: Exclude<LearningRecordType, 'note'>, payload: {
      nodeId: string
      quote: string
      content?: string
      title?: string
      anchor?: Record<string, unknown>
    }) {
      return this.createNote({
        id: `record-${crypto.randomUUID()}`,
        nodeId: payload.nodeId,
        highlightId: '',
        quote: payload.quote,
        content: payload.content || payload.quote,
        title: payload.title,
        color: recordType === 'issue' ? 'red' : recordType === 'review_task' ? 'orange' : 'blue',
        createdAt: Date.now(),
        sourceType: 'user',
        recordType,
        status: recordType === 'issue' ? 'open' : recordType === 'review_task' ? 'pending' : 'active',
        priority: recordType === 'bookmark' ? 'low' : 'medium',
        anchor: payload.anchor,
      })
    },

    async updateRecordStatus(id: string, status: string) {
      const note = this.notes.find(item => item.id === id)
      if (!note?.revision || note.sourceType === 'format') return null
      try {
        const res = await http.patch(`/api/courses/${this.courseId}/learning-records/${id}`, {
          expected_revision: note.revision,
          status,
        })
        const updated = recordToNote(res.data)
        const index = this.notes.findIndex(item => item.id === id)
        if (index >= 0) this.notes[index] = updated
        await refreshLearningRuntime(this.courseId, updated.nodeId)
        return updated
      } catch (e) {
        logger.error('Failed to update learning record status', e)
        ElMessage.error('状态更新失败')
        return null
      }
    },

    async updateNote(id: string, content: string) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        if (note.sourceType === 'format') {
          note.content = content
          return note
        }
        note.content = content
        note.syncState = 'saving'
        persistRecordDraft(this.courseId, note)
        try {
          const res = await http.patch(`/api/courses/${this.courseId}/learning-records/${id}`, {
            expected_revision: note.revision,
            content,
          })
          Object.assign(note, recordToNote(res.data))
          clearRecordDraft(this.courseId, id)
          await refreshLearningRuntime(this.courseId, note.nodeId)
          return note
        } catch (e) {
          logger.error('Failed to update note persistence', e)
          note.syncState = 'local_only'
          ElMessage.warning('笔记保存失败，请重试')
          return null
        }
      }
      return null
    },

    async retryNote(id: string) {
      const note = this.notes.find(item => item.id === id)
      if (!note) return null
      return note.revision ? this.updateNote(id, note.content) : this.createNote(note)
    },

    async upsertAnchoredAiNote(payload: {
      nodeId: string
      quote: string
      content: string
      anchor?: Record<string, unknown>
      conversationId: string
      messageId: string
      prompt?: string
      action?: string
      title?: string
      summary?: string
    }) {
      const stableSource = `${payload.nodeId}|${payload.quote}|${JSON.stringify(payload.anchor?.text_position || {})}`
      let hash = 2166136261
      for (let index = 0; index < stableSource.length; index += 1) {
        hash ^= stableSource.charCodeAt(index)
        hash = Math.imul(hash, 16777619)
      }
      const recordId = `ai-qa-${(hash >>> 0).toString(16)}`
      const metadata = {
        ai_conversation_id: payload.conversationId,
        ai_message_ids: [payload.messageId],
        record_subtype: 'anchored_ai_qa',
        ai_prompt: payload.prompt || '',
        inline_ai_action: payload.action || 'ask',
      }
      const current = this.notes.find(item => item.id === recordId)
      if (!current?.revision) {
        const created = await this.createNote({
          id: recordId,
          nodeId: payload.nodeId,
          highlightId: `hl-${recordId}`,
          quote: payload.quote,
          title: payload.title || payload.summary || 'AI 问答',
          summary: payload.summary || payload.title || 'AI 问答',
          content: payload.content,
          color: 'purple',
          createdAt: Date.now(),
          sourceType: 'ai',
          recordType: 'note',
          status: 'active',
          origin: 'assistant_inline_qa',
          priority: 'medium',
          anchor: payload.anchor,
          metadata,
        })
        return created || this.notes.find(item => item.id === recordId) || null
      }
      current.content = payload.content
      current.title = payload.title || current.title
      current.summary = payload.summary || payload.title || current.summary
      current.metadata = {
        ...(current.metadata || {}),
        ...metadata,
        ai_message_ids: [
          ...new Set([...(Array.isArray(current.metadata?.ai_message_ids) ? current.metadata.ai_message_ids : []), payload.messageId]),
        ],
      }
      current.syncState = 'saving'
      persistRecordDraft(this.courseId, current)
      try {
        const response = await http.patch(`/api/courses/${this.courseId}/learning-records/${recordId}`, {
          expected_revision: current.revision,
          title: current.title || current.summary || '',
          content: current.content,
          anchor: payload.anchor,
          metadata: current.metadata,
        })
        Object.assign(current, recordToNote(response.data))
        clearRecordDraft(this.courseId, recordId)
        await refreshLearningRuntime(this.courseId, payload.nodeId)
        return current
      } catch (error) {
        logger.error('Failed to upsert anchored AI note', error)
        current.syncState = 'local_only'
        return current
      }
    },

    async deleteNote(id: string) {
      const index = this.notes.findIndex(n => n.id === id)
      if (index !== -1) {
        const note = this.notes[index]
        if (!note) return
        if (!note.revision) {
          this.notes.splice(index, 1)
          clearRecordDraft(this.courseId || useCourseStore().currentCourseId, id)
          return
        }
        if (note.sourceType === 'format') {
          this.notes.splice(index, 1)
          clearRecordDraft(this.courseId, id)
          return
        }
        try {
          await http.post(`/api/courses/${this.courseId}/learning-records/${id}/archive`, {
            expected_revision: note.revision,
          })
          this.notes.splice(index, 1)
          await refreshLearningRuntime(this.courseId, note.nodeId)
        } catch (e) {
          logger.error('Failed to delete note persistence', e)
        }
      }
    },

    // ========== Tag & Category Management ==========
    async updateNoteTags(id: string, tags: string[]) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.tags = tags
        try {
          const res = await http.patch(`/api/courses/${this.courseId}/learning-records/${id}`, {
            expected_revision: note.revision,
            tags,
          })
          Object.assign(note, recordToNote(res.data))
          await refreshLearningRuntime(this.courseId, note.nodeId)
        } catch (e) {
          logger.error('Failed to update note tags', e)
        }
      }
    },

    async updateNoteCategory(id: string, category: string) {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.category = category
        try {
          const res = await http.patch(`/api/courses/${this.courseId}/learning-records/${id}`, {
            expected_revision: note.revision,
            category,
          })
          Object.assign(note, recordToNote(res.data))
          await refreshLearningRuntime(this.courseId, note.nodeId)
        } catch (e) {
          logger.error('Failed to update note category', e)
        }
      }
    },

    async updateNotePriority(id: string, priority: 'low' | 'medium' | 'high') {
      const note = this.notes.find(n => n.id === id)
      if (note) {
        note.priority = priority
        try {
          const res = await http.patch(`/api/courses/${this.courseId}/learning-records/${id}`, {
            expected_revision: note.revision,
            priority,
          })
          Object.assign(note, recordToNote(res.data))
          await refreshLearningRuntime(this.courseId, note.nodeId)
        } catch (e) {
          logger.error('Failed to update note priority', e)
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
