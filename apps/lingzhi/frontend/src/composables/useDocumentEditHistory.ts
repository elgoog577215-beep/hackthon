import { computed, ref, shallowRef } from 'vue'

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

export function useDocumentEditHistory<T>(applySnapshot: (value: T) => void, limit = 100) {
  const snapshots = shallowRef<T[]>([])
  const index = ref(-1)

  const canUndo = computed(() => index.value > 0)
  const canRedo = computed(() => index.value >= 0 && index.value < snapshots.value.length - 1)

  function reset(value: T) {
    snapshots.value = [clone(value)]
    index.value = 0
  }

  function record(value: T) {
    const next = clone(value)
    const current = snapshots.value[index.value]
    if (current && JSON.stringify(current) === JSON.stringify(next)) return
    const retained = snapshots.value.slice(0, index.value + 1)
    retained.push(next)
    snapshots.value = retained.slice(-limit)
    index.value = snapshots.value.length - 1
  }

  function undo() {
    if (!canUndo.value) return false
    index.value -= 1
    applySnapshot(clone(snapshots.value[index.value]!))
    return true
  }

  function redo() {
    if (!canRedo.value) return false
    index.value += 1
    applySnapshot(clone(snapshots.value[index.value]!))
    return true
  }

  function clear() {
    snapshots.value = []
    index.value = -1
  }

  return { canUndo, canRedo, reset, record, undo, redo, clear }
}
