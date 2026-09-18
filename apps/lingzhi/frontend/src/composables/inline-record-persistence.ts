import type { Note } from '../stores/types'
import { useNoteStore } from '../stores/notes'

// Serialize edits and deletion of the same record, using the server revision
// returned by the previous write instead of the editor's older note object.
export function createInlineRecordPersistence(store: ReturnType<typeof useNoteStore>) {
  const pending = new Map<string, Promise<unknown>>()
  function enqueue<T>(id: string, action: () => Promise<T>): Promise<T> {
    const previous = pending.get(id)
    const operation = previous ? previous.catch(() => undefined).then(action) : action()
    pending.set(id, operation)
    const cleanup = () => { if (pending.get(id) === operation) pending.delete(id) }
    void operation.then(cleanup, cleanup)
    return operation
  }
  return {
    isPending: (id: string) => pending.has(id),
    save(note: Note, content: string) {
      note.content = content
      return enqueue(note.id, async () => {
        const current = store.notes.find(item => item.id === note.id) || note
        return current.revision
          ? store.updateNote(note.id, content)
          : store.createNote({ ...current, content })
      })
    },
    remove(note: Note) {
      return enqueue(note.id, () => store.deleteNote(note.id))
    },
  }
}
