import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import type { Note } from '../stores/types'
import { activeLocale, t } from '../shared/i18n'
import http from '../utils/http'

export interface CompanionReminder {
  id: string
  note: Note
  title: string
  message: string
  source?: string
  quote?: string
}
interface ReviewResult {
  status: string
  finding: { note_quote: string; source_quote: string; explanation: string } | null
}

/** Checks only saved personal notes. Requests never enter the conversation or mastery stores. */
export function useCompanionReminders(active: Readonly<Ref<boolean>>, policy?: {suppressed:Readonly<Ref<Set<string>>>; dismiss?:(key:string,mode:'not_now'|'never')=>void}) {
  const course = useCourseStore()
  const notes = useNoteStore()
  const enabled = ref(true)
  const findings = ref(new Map<string, ReviewResult['finding']>())
  const dismissed = ref(new Set<string>())
  const checked = new Set<string>()
  const now = ref(Date.now())
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let generation = 0
  const key = (note: Note) => `${course.currentCourseId}:${course.currentCourseVersionId}:${activeLocale.value}:${note.id}:${note.revision}:${note.content}`
  const eligible = computed(() => notes.courseId === course.currentCourseId ? notes.notes.filter(note =>
    note.status !== 'archived' && note.status !== 'resolved' && note.status !== 'completed'
    && note.sourceType !== 'ai' && note.sourceType !== 'format' && note.sourceType !== 'wrong'
    && !policy?.suppressed.value.has(`note:${note.id}`)
    && (!note.migrationStatus || note.migrationStatus === 'current')
    && course.nodes.some(node => node.node_id === note.nodeId)) : [])
  const reminder = computed<CompanionReminder | null>(() => {
    if (!active.value || !enabled.value) return null
    for (const note of eligible.value) {
      const id = `review:${key(note)}`
      const finding = findings.value.get(key(note))
      if (finding && !dismissed.value.has(id)) return { id, note, title:t('companionReminder.checkTitle'), message:finding.explanation, source:finding.source_quote, quote:finding.note_quote }
    }
    for (const note of eligible.value) {
      const due = note.recordType === 'review_task' && note.dueAt && Date.parse(note.dueAt) <= now.value
      const issue = note.recordType === 'issue' && note.nodeId === course.currentNode?.node_id
      if (!due && !issue) continue
      const id = `${due ? 'due' : 'issue'}:${key(note)}`
      if (!dismissed.value.has(id)) return { id, note, title:t(due ? 'companionReminder.dueTitle' : 'companionReminder.issueTitle'), message:note.content || note.quote || t('companionReminder.openHint') }
    }
    return null
  })
  function dismiss(mode:'not_now'|'never'='not_now') { if (reminder.value) { const current=reminder.value; dismissed.value = new Set([...dismissed.value, current.id]); policy?.dismiss?.(`note:${current.note.id}`,mode) } }
  function schedule() {
    const token = ++generation
    clearTimeout(timer)
    controller?.abort()
    if (!active.value || !enabled.value || document.visibilityState === 'hidden') return
    timer = setTimeout(async () => {
      const pending = eligible.value.filter(note => (!note.recordType || note.recordType === 'note')
        && note.syncState === 'saved' && note.revision && note.content.trim().length >= 5
        && note.content.length <= 6000 && !checked.has(key(note)))
      // Prefer the currently edited lecture; serialize calls to avoid a request per keystroke.
      pending.sort((a,b) => Number(b.nodeId === course.currentNode?.node_id) - Number(a.nodeId === course.currentNode?.node_id))
      for (const note of pending.slice(0, 3)) {
        if (token !== generation) return
        const id = key(note)
        checked.add(id)
        controller = new AbortController()
        try {
          const { data } = await http.post<ReviewResult>(`/api/courses/${encodeURIComponent(course.currentCourseId)}/learning-records/${encodeURIComponent(note.id)}/companion-review`, {
            expected_revision:note.revision, course_version_id:course.currentCourseVersionId || '', language:activeLocale.value,
          }, { signal:controller.signal, timeout:35000 })
          if (token !== generation) { checked.delete(id); return }
          if (data.status === 'checked') findings.value = new Map(findings.value).set(id, data.finding)
        } catch {
          if (token !== generation) { checked.delete(id); return }
          // No repeated background retries and no fabricated "all correct" result.
        }
      }
    }, 1800)
  }
  watch(() => [active.value, enabled.value, course.currentCourseId, course.currentCourseVersionId, course.currentNode?.node_id, activeLocale.value, eligible.value.map(note => `${key(note)}:${note.syncState}`).join('|')], schedule, { immediate:true })
  watch(() => [course.currentCourseId, course.currentCourseVersionId], () => { findings.value = new Map(); dismissed.value = new Set(); checked.clear() }, { flush:'sync' })
  const clock = setInterval(() => { now.value = Date.now() }, 60000)
  document.addEventListener('visibilitychange', schedule)
  onUnmounted(() => { ++generation; clearTimeout(timer); clearInterval(clock); controller?.abort(); document.removeEventListener('visibilitychange', schedule) })
  return { reminder, enabled, dismiss }
}
