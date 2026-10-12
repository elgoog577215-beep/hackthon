import { computed, ref, watch, type Ref } from 'vue'

/** Browser-only presentation state; never a chat message or learning record. */
export function useCompanionWelcome(ready: Readonly<Ref<boolean>>, identity: Readonly<Ref<string>>) {
  const open = ref(false)
  const dismissed = new Set<string>()
  const storageKey = computed(() => `lingzhi-companion-welcome:v1:${encodeURIComponent(identity.value)}`)
  const visible = computed(() => open.value && ready.value)

  watch([ready, identity], ([available, user]) => {
    open.value = false
    if (!available || !user || dismissed.has(user)) return
    try { if (localStorage.getItem(storageKey.value) === 'done') return } catch { /* Session still works without storage. */ }
    open.value = true
  }, { immediate: true })

  function dismiss() {
    open.value = false
    if (!identity.value) return
    dismissed.add(identity.value)
    try { localStorage.setItem(storageKey.value, 'done') } catch { /* Do not interrupt learning. */ }
  }
  return { visible, dismiss }
}
