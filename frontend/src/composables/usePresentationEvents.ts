import { onScopeDispose, ref } from 'vue'
import { presentationService } from '@/services/presentations'
import { usePresentationStore } from '@/stores/presentation'

export function usePresentationEvents() {
  const store = usePresentationStore()
  const reconnecting = ref(false)
  let controller: AbortController | null = null

  async function reconnect(): Promise<void> {
    const deckId = store.deck?.deck_id
    const generationId = store.activeGenerationId || store.deck?.active_generation_id
    if (!deckId || !generationId || reconnecting.value) return
    controller?.abort()
    controller = new AbortController()
    reconnecting.value = true
    try {
      await presentationService.replay(
        deckId,
        generationId,
        store.lastSequence,
        store.consumeEvent,
        controller.signal,
      )
    } catch (cause) {
      if ((cause as { name?: string })?.name !== 'AbortError') {
        await store.loadDeck(deckId)
      }
    } finally {
      reconnecting.value = false
      controller = null
    }
  }

  function stop(): void {
    controller?.abort()
    controller = null
    reconnecting.value = false
  }

  onScopeDispose(stop)

  return { reconnecting, reconnect, stop }
}
