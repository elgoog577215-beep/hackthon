import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCompanionReminders } from '@/composables/useCompanionReminders'
import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'
import http from '@/utils/http'

vi.mock('@/utils/http', () => ({ default:{ post:vi.fn() } }))
const finding = { note_quote:'my wrong statement', source_quote:'course evidence', explanation:'Check this distinction.' }

describe('companion reminders', () => {
  let wrapper: ReturnType<typeof mount> | undefined
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    const course = useCourseStore()
    course.currentCourseId = 'c1'
    course.currentCourseVersionId = 'v1'
    course.nodes = [{ node_id:'n1' } as any]
    course.currentNode = course.nodes[0]!
    const notes = useNoteStore()
    notes.courseId = 'c1'
    notes.notes = [{ id:'note1', nodeId:'n1', revision:1, content:'my wrong statement', quote:'', highlightId:'', createdAt:1, color:'amber', sourceType:'user', syncState:'saved', recordType:'note', status:'active' }]
    vi.mocked(http.post).mockResolvedValue({ data:{ status:'checked', finding } })
  })
  afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.clearAllMocks() })
  function start(active = true) {
    let result!: ReturnType<typeof useCompanionReminders>
    wrapper = mount(defineComponent({ setup() { result = useCompanionReminders(ref(active)); return () => null } }))
    return result
  }
  async function settle() { await vi.advanceTimersByTimeAsync(1900); await flushPromises() }
  it('debounces saved revisions, shows evidence, dismisses without repeating and supports pausing', async () => {
    const result = start()
    expect(http.post).not.toHaveBeenCalled()
    await settle()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(result.reminder.value?.source).toBe('course evidence')
    result.dismiss()
    expect(result.reminder.value).toBeNull()
    result.enabled.value = false
    await settle()
    result.enabled.value = true
    await settle()
    expect(http.post).toHaveBeenCalledTimes(1)
    useNoteStore().notes[0]!.revision = 2
    await settle()
    expect(http.post).toHaveBeenCalledTimes(2)
  })
  it('honors a durable semantic note suppression even after its text or revision changes', async () => {
    let result!: ReturnType<typeof useCompanionReminders>
    const suppressed=ref(new Set(['note:note1']))
    wrapper=mount(defineComponent({setup(){result=useCompanionReminders(ref(true),{suppressed});return()=>null}}))
    await settle();expect(result.reminder.value).toBeNull();expect(http.post).not.toHaveBeenCalled()
    useNoteStore().notes[0]!.revision=2
    await settle();expect(http.post).not.toHaveBeenCalled()
  })
  it('does not check drafts, AI notes, or teacher preview', async () => {
    useNoteStore().notes[0]!.syncState = 'local_only'
    start()
    await settle()
    expect(http.post).not.toHaveBeenCalled()
    useNoteStore().notes[0]!.syncState = 'saved'
    useNoteStore().notes[0]!.sourceType = 'ai'
    await settle()
    expect(http.post).not.toHaveBeenCalled()
    wrapper?.unmount()
    useNoteStore().notes[0]!.sourceType = 'user'
    start(false)
    await settle()
    expect(http.post).not.toHaveBeenCalled()
  })
  it('drops a late result after switching courses', async () => {
    let resolve!: (value:any) => void
    vi.mocked(http.post).mockImplementation(() => new Promise(r => { resolve = r }))
    const result = start()
    await settle()
    useCourseStore().currentCourseId = 'c2'
    await flushPromises()
    resolve({ data:{ status:'checked', finding } })
    await flushPromises()
    expect(result.reminder.value).toBeNull()
  })
  it('links due review records without a model call', async () => {
    useNoteStore().notes[0]!.recordType = 'review_task'
    useNoteStore().notes[0]!.dueAt = new Date(Date.now()-1000).toISOString()
    const result = start()
    await settle()
    expect(result.reminder.value?.note.id).toBe('note1')
    expect(http.post).not.toHaveBeenCalled()
  })
})
