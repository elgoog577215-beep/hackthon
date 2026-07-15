import { createPinia, setActivePinia } from 'pinia'
import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePresentationEvents } from '@/composables/usePresentationEvents'
import { presentationService } from '@/services/presentations'
import { usePresentationStore } from '@/stores/presentation'
import type { PresentationDeck, PresentationEvent, PresentationRevision } from '@/types/presentation'

const deck: PresentationDeck = {
  schema_version: 1,
  deck_id: 'deck-1',
  course_id: 'course-1',
  title: '课件',
  source_ref: {
    course_id: 'course-1', source_format: 'canonical', version_id: 'cv1', document_revision: 'cdr1',
    blueprint_revision_id: '', asset_bundle_revision_id: '', source_snapshot_id: 'source-1',
    source_snapshot_sha256: `sha256:${'a'.repeat(64)}`,
  },
  scope: { type: 'chapter', section_ids: ['chapter-1'] },
  purpose: 'teaching',
  template_id: 'lingzhi-classroom',
  status: 'generating',
  active_revision_id: null,
  active_generation_id: 'generation-1',
  latest_quality_report_id: null,
  latest_artifact_id: null,
  created_at: '',
  updated_at: '',
}

const completedRevision: PresentationRevision = {
  revision_id: 'revision-1', parent_revision_id: null, deck_id: 'deck-1', reason: 'initial_generation',
  created_at: '', created_by: 'system', source_snapshot_id: 'source-1', slide_order: [], slides: [],
}

const event = (sequence: number, eventType: PresentationEvent['event_type']): PresentationEvent => ({
  schema_version: 'presentation-event/v1', event_type: eventType, deck_id: 'deck-1', generation_id: 'generation-1',
  event_seq: sequence, outline_revision: 1, revision_id: eventType === 'generation_complete' ? 'revision-1' : null,
  emitted_at: '', payload: eventType === 'generation_complete'
    ? { revision: completedRevision, revision_checksum: 'checksum-1' }
    : { completed: 4, total: 8 },
})

describe('usePresentationEvents', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('刷新后从 working 的 generation/sequence 续接到 terminal，不重复旧事件', async () => {
    const store = usePresentationStore()
    store.deck = deck
    store.activeGenerationId = 'generation-1'
    store.lastSequence = 3
    store.generating = true
    const replay = vi.spyOn(presentationService, 'replay').mockImplementation(async (_deckId, _generationId, _after, onEvent) => {
      await onEvent(event(4, 'progress'))
      await onEvent(event(5, 'generation_complete'))
    })
    const scope = effectScope()
    const events = scope.run(() => usePresentationEvents())!

    await events.reconnect()

    expect(replay).toHaveBeenCalledWith('deck-1', 'generation-1', 3, store.consumeEvent, expect.any(AbortSignal))
    expect(store.lastSequence).toBe(5)
    expect(store.revision?.revision_id).toBe('revision-1')
    expect(store.generating).toBe(false)
    expect(store.activeGenerationId).toBeNull()
    scope.stop()
  })
})
