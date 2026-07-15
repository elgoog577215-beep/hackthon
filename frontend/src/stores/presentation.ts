import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  presentationService,
  type CreatePresentationInput,
  type PresentationDeckSnapshot,
} from '@/services/presentations'
import type {
  PresentationArtifact,
  PresentationDeck,
  PresentationEvent,
  PresentationProposal,
  PresentationQualityIssue,
  PresentationRenderMeasurement,
  PresentationRevision,
  PresentationSlide,
  PresentationStudioPhase,
} from '@/types/presentation'

interface PresentationQualitySummary {
  report_id?: string
  status: 'passed' | 'blocked' | 'advisory'
  issues: PresentationQualityIssue[]
}

type IncomingPresentationSlide = Partial<PresentationSlide> & Pick<PresentationSlide, 'slide_id'>

const requestId = (prefix: string): string => {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

const errorMessage = (error: unknown, fallback: string): string => {
  const status = (error as { response?: { status?: number } })?.response?.status
  const body = (error as { response?: { data?: { detail?: unknown; message?: unknown } } })?.response?.data
  const rawDetail = body?.detail || body?.message
  if (typeof rawDetail === 'string' && rawDetail) return rawDetail
  if (rawDetail && typeof rawDetail === 'object') {
    const structured = rawDetail as { message?: unknown; code?: unknown }
    if (structured.message) return String(structured.message)
    if (structured.code) return String(structured.code)
  }
  if (status === 404) return '课件服务暂未就绪，请稍后重试'
  if (!(error as { response?: unknown })?.response && error instanceof Error) return '无法连接课件服务，已保留当前页面状态'
  if (error instanceof Error && error.message) return error.message
  return fallback
}

const qualityFromError = (error: unknown): PresentationQualitySummary | null => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (!detail || typeof detail !== 'object') return null
  const candidate = (detail as { details?: unknown }).details
  if (!candidate || typeof candidate !== 'object') return null
  const report = candidate as { report_id?: unknown; status?: unknown; issues?: unknown }
  if (!['passed', 'blocked', 'advisory'].includes(String(report.status))) return null
  return {
    report_id: report.report_id ? String(report.report_id) : undefined,
    status: String(report.status) as PresentationQualitySummary['status'],
    issues: Array.isArray(report.issues) ? report.issues as PresentationQualityIssue[] : [],
  }
}

const deckFromSnapshot = (snapshot: PresentationDeckSnapshot): PresentationDeck => (
  snapshot.deck || snapshot as unknown as PresentationDeck
)

export const usePresentationStore = defineStore('presentation', () => {
  const courseId = ref('')
  const decks = ref<PresentationDeck[]>([])
  const deck = ref<PresentationDeck | null>(null)
  const revision = ref<PresentationRevision | null>(null)
  const revisionChecksum = ref<string | null>(null)
  const slides = ref<PresentationSlide[]>([])
  const slideOrder = ref<string[]>([])
  const selectedSlideId = ref<string | null>(null)
  const proposal = ref<PresentationProposal | null>(null)
  const quality = ref<PresentationQualitySummary | null>(null)
  const artifact = ref<PresentationArtifact | null>(null)
  const activeGenerationId = ref<string | null>(null)
  const lastSequence = ref(0)
  const outlineRevision = ref(0)
  const eventGap = ref(false)
  const generationProgress = ref({ completed: 0, total: 0, message: '' })
  const renderMeasurement = ref<PresentationRenderMeasurement | null>(null)
  const loading = ref(false)
  const generating = ref(false)
  const proposing = ref(false)
  const applying = ref(false)
  const finalizing = ref(false)
  const error = ref<string | null>(null)
  let streamController: AbortController | null = null
  let gapRefresh: Promise<void> | null = null

  const selectedSlide = computed(() => (
    slides.value.find(item => item.slide_id === selectedSlideId.value) || null
  ))
  const orderedSlides = computed(() => {
    const byId = new Map(slides.value.map(item => [item.slide_id, item]))
    return slideOrder.value.map(id => byId.get(id)).filter((item): item is PresentationSlide => Boolean(item))
  })
  const phase = computed<PresentationStudioPhase>(() => {
    if (!deck.value) return loading.value ? 'booting' : 'configuring'
    if (generating.value || deck.value.status === 'generating') return 'generating'
    if (finalizing.value || deck.value.status === 'exporting') return 'finalizing'
    if (deck.value.status === 'quality_blocked' || quality.value?.status === 'blocked') return 'quality_blocked'
    if (artifact.value && !artifact.value.stale && deck.value.active_revision_id === artifact.value.revision_id) return 'export_ready'
    if (!revision.value) return 'configuring'
    return 'editing'
  })
  const canDownload = computed(() => Boolean(
    artifact.value
    && !artifact.value.stale
    && artifact.value.revision_id === deck.value?.active_revision_id
    && quality.value?.status !== 'blocked',
  ))
  const measurementReady = computed(() => Boolean(
    revision.value
    && revisionChecksum.value
    && renderMeasurement.value
    && renderMeasurement.value.revision_id === revision.value.revision_id
    && renderMeasurement.value.revision_checksum === revisionChecksum.value
    && typeof renderMeasurement.value.overflow === 'boolean'
    && typeof renderMeasurement.value.collision === 'boolean'
    && Number.isInteger(renderMeasurement.value.slide_count)
    && renderMeasurement.value.slide_count === slides.value.length,
  ))

  function mergeSlide(next: IncomingPresentationSlide) {
    const index = slides.value.findIndex(item => item.slide_id === next.slide_id)
    const previous = index >= 0 ? slides.value[index] : undefined
    const normalized: PresentationSlide = {
      slide_id: next.slide_id,
      position: next.position ?? previous?.position ?? Math.max(0, slideOrder.value.indexOf(next.slide_id)),
      layout_id: next.layout_id ?? previous?.layout_id ?? 'L04',
      status: next.status ?? previous?.status ?? 'planned',
      title: next.title ?? previous?.title ?? '',
      subtitle: next.subtitle ?? previous?.subtitle ?? '',
      key_message: next.key_message ?? previous?.key_message ?? '',
      blocks: Array.isArray(next.blocks) ? next.blocks : previous?.blocks ?? [],
      speaker_notes: next.speaker_notes ?? previous?.speaker_notes ?? '',
      source_refs: next.source_refs ?? previous?.source_refs ?? {
        section_ids: [], block_ids: [], block_revision_ids: [], objective_ids: [], asset_ids: [],
      },
      quality: next.quality ?? previous?.quality ?? { issues: [], capacity: {} },
    }
    if (index >= 0) slides.value[index] = normalized
    else slides.value.push(normalized)
    if (!slideOrder.value.includes(next.slide_id)) slideOrder.value.push(next.slide_id)
    if (!selectedSlideId.value && normalized.status === 'ready') selectedSlideId.value = next.slide_id
  }

  function applySnapshot(snapshot: PresentationDeckSnapshot) {
    const nextDeck = deckFromSnapshot(snapshot)
    const nextRevision = snapshot.revision || null
    const nextChecksum = snapshot.revision_checksum || null
    if (
      revision.value?.revision_id !== nextRevision?.revision_id
      || revisionChecksum.value !== nextChecksum
    ) {
      renderMeasurement.value = null
    }
    deck.value = nextDeck
    revision.value = nextRevision
    revisionChecksum.value = nextChecksum
    quality.value = snapshot.quality || null
    artifact.value = snapshot.artifact || null
    activeGenerationId.value = snapshot.working?.generation_id || nextDeck.active_generation_id
    if (snapshot.working) {
      slides.value = [...snapshot.working.slides]
      slideOrder.value = [...snapshot.working.slide_order]
      lastSequence.value = snapshot.working.event_seq
      outlineRevision.value = snapshot.working.outline_revision
    } else if (snapshot.revision) {
      slides.value = [...snapshot.revision.slides]
      slideOrder.value = [...snapshot.revision.slide_order]
      lastSequence.value = 0
      outlineRevision.value = 0
    } else {
      slides.value = []
      slideOrder.value = []
    }
    if (!slideOrder.value.includes(selectedSlideId.value || '')) {
      selectedSlideId.value = slides.value.find(item => item.status === 'ready')?.slide_id || slideOrder.value[0] || null
    }
    eventGap.value = false
  }

  async function listDecks(targetCourseId: string) {
    courseId.value = targetCourseId
    loading.value = true
    error.value = null
    try {
      decks.value = await presentationService.list(targetCourseId)
      return decks.value
    } catch (cause) {
      error.value = errorMessage(cause, '课件列表读取失败')
      return []
    } finally {
      loading.value = false
    }
  }

  async function loadDeck(deckId: string) {
    loading.value = true
    error.value = null
    try {
      const snapshot = await presentationService.get(deckId)
      applySnapshot(snapshot)
      courseId.value = snapshot.deck.course_id
      generating.value = snapshot.deck.status === 'generating'
      return snapshot
    } catch (cause) {
      error.value = errorMessage(cause, '课件草稿读取失败')
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function createDeck(targetCourseId: string, input: Omit<CreatePresentationInput, 'request_id'>) {
    loading.value = true
    error.value = null
    try {
      const snapshot = await presentationService.create(targetCourseId, {
        ...input,
        request_id: requestId('create-deck'),
      })
      applySnapshot(snapshot)
      courseId.value = targetCourseId
      return snapshot.deck
    } catch (cause) {
      error.value = errorMessage(cause, '课件草稿创建失败')
      throw cause
    } finally {
      loading.value = false
    }
  }

  function refreshAfterGap(): Promise<void> {
    if (!deck.value) return Promise.resolve()
    if (!gapRefresh) {
      gapRefresh = loadDeck(deck.value.deck_id)
        .then(() => undefined)
        .finally(() => { gapRefresh = null })
    }
    return gapRefresh
  }

  async function consumeEvent(event: PresentationEvent): Promise<boolean> {
    if (!deck.value || event.deck_id !== deck.value.deck_id) return false
    if (activeGenerationId.value && event.generation_id !== activeGenerationId.value) return false
    if (!activeGenerationId.value) activeGenerationId.value = event.generation_id
    if (event.event_seq <= lastSequence.value) return false
    if (lastSequence.value > 0 && event.event_seq !== lastSequence.value + 1) {
      eventGap.value = true
      await refreshAfterGap()
      return false
    }

    lastSequence.value = event.event_seq
    outlineRevision.value = event.outline_revision
    if (event.event_type === 'deck_outline') {
      const order = Array.isArray(event.payload.slide_order) ? event.payload.slide_order.map(String) : []
      const planned = Array.isArray(event.payload.slides) ? event.payload.slides as IncomingPresentationSlide[] : []
      if (order.length) slideOrder.value = order
      for (const item of planned) mergeSlide(item)
    } else if (event.event_type === 'slide_upsert' || event.event_type === 'slide_patch') {
      const candidate = (event.payload.slide || event.payload) as unknown as IncomingPresentationSlide
      if (candidate?.slide_id) mergeSlide(candidate)
    } else if (event.event_type === 'progress') {
      generationProgress.value = {
        completed: Number(event.payload.completed || 0),
        total: Number(event.payload.total || 0),
        message: String(event.payload.message || ''),
      }
    } else if (event.event_type === 'quality_report') {
      const report = (event.payload.report || event.payload) as unknown as PresentationQualitySummary
      quality.value = report
    } else if (event.event_type === 'generation_complete') {
      const nextRevision = event.payload.revision as PresentationRevision | undefined
      const nextChecksum = typeof event.payload.revision_checksum === 'string'
        ? event.payload.revision_checksum
        : null
      if (nextRevision) {
        if (
          revision.value?.revision_id !== nextRevision.revision_id
          || revisionChecksum.value !== nextChecksum
        ) {
          renderMeasurement.value = null
        }
        revision.value = nextRevision
        revisionChecksum.value = nextChecksum
        slides.value = [...nextRevision.slides]
        slideOrder.value = [...nextRevision.slide_order]
      }
      deck.value = {
        ...deck.value,
        status: quality.value?.status === 'blocked' ? 'quality_blocked' : 'editing',
        active_revision_id: event.revision_id || nextRevision?.revision_id || deck.value.active_revision_id,
        active_generation_id: null,
      }
      activeGenerationId.value = null
      generating.value = false
    } else if (event.event_type === 'export_ready') {
      artifact.value = (event.payload.artifact || event.payload) as unknown as PresentationArtifact
      deck.value = { ...deck.value, status: 'exported', latest_artifact_id: artifact.value.artifact_id }
    } else if (event.event_type === 'error') {
      error.value = String(event.payload.message || event.payload.error || '课件生成失败')
      generating.value = false
      deck.value = { ...deck.value, status: revision.value ? 'editing' : 'failed' }
    }
    return true
  }

  async function generate(input: { page_budget: number; extra_requirements: string }) {
    if (!deck.value || generating.value) return
    streamController?.abort()
    streamController = new AbortController()
    generating.value = true
    error.value = null
    lastSequence.value = 0
    eventGap.value = false
    activeGenerationId.value = null
    renderMeasurement.value = null
    deck.value = { ...deck.value, status: 'generating' }
    try {
      await presentationService.generate(deck.value.deck_id, {
        request_id: requestId('generate-deck'),
        expected_revision_id: deck.value.active_revision_id,
        ...input,
      }, consumeEvent, streamController.signal)
    } catch (cause) {
      if ((cause as { name?: string })?.name !== 'AbortError') {
        error.value = errorMessage(cause, '课件生成失败')
        deck.value = { ...deck.value, status: revision.value ? 'editing' : 'failed' }
      }
    } finally {
      generating.value = false
      streamController = null
    }
  }

  async function requestProposal(prompt: string) {
    if (!deck.value || !revision.value || proposing.value) return null
    const target = selectedSlide.value?.status === 'ready' ? selectedSlide.value.slide_id : null
    proposing.value = true
    error.value = null
    try {
      proposal.value = await presentationService.propose(deck.value.deck_id, {
        request_id: requestId('deck-chat'),
        expected_revision_id: revision.value.revision_id,
        scope: target ? 'slide' : 'deck',
        slide_ids: target ? [target] : [],
        prompt,
      })
      return proposal.value
    } catch (cause) {
      error.value = errorMessage(cause, '课件修改建议生成失败')
      return null
    } finally {
      proposing.value = false
    }
  }

  async function applyProposal() {
    if (!deck.value || !revision.value || !proposal.value || applying.value) return
    const activeProposal = proposal.value
    applying.value = true
    error.value = null
    try {
      const snapshot = await presentationService.applyProposal(deck.value.deck_id, activeProposal.proposal_id, {
        expected_revision_id: revision.value.revision_id,
        command_id: requestId('apply-proposal'),
      })
      applySnapshot(snapshot)
      proposal.value = null
      if (artifact.value) artifact.value = { ...artifact.value, stale: true }
    } catch (cause) {
      const status = (cause as { response?: { status?: number } })?.response?.status
      if (status === 409) proposal.value = { ...activeProposal, status: 'stale' }
      error.value = status === 409 ? '课件版本已变化，请重新生成修改建议' : errorMessage(cause, '应用修改失败')
    } finally {
      applying.value = false
    }
  }

  async function undo() {
    if (!deck.value || !revision.value?.parent_revision_id || applying.value) return
    applying.value = true
    error.value = null
    try {
      const snapshot = await presentationService.restore(deck.value.deck_id, revision.value.parent_revision_id, {
        expected_revision_id: revision.value.revision_id,
        command_id: requestId('restore-revision'),
      })
      applySnapshot(snapshot)
      proposal.value = null
      if (artifact.value) artifact.value = { ...artifact.value, stale: true }
    } catch (cause) {
      error.value = errorMessage(cause, '撤销课件修改失败')
    } finally {
      applying.value = false
    }
  }

  async function finalize() {
    if (!deck.value || !revision.value || finalizing.value) return
    const currentMeasurement = renderMeasurement.value
    if (!measurementReady.value || !currentMeasurement) {
      error.value = '预览仍在检查当前课件版本，请等待排版测量完成后，再点击“完成课件”'
      return
    }
    finalizing.value = true
    error.value = null
    deck.value = { ...deck.value, status: 'exporting' }
    try {
      const snapshot = await presentationService.finalize(deck.value.deck_id, {
        expected_revision_id: revision.value.revision_id,
        command_id: requestId('finalize-deck'),
        render_measurement: currentMeasurement,
      })
      applySnapshot(snapshot)
    } catch (cause) {
      const blockedReport = qualityFromError(cause)
      if (blockedReport) quality.value = blockedReport
      error.value = errorMessage(cause, '课件完成检查失败')
      deck.value = { ...deck.value, status: blockedReport?.status === 'blocked' ? 'quality_blocked' : 'editing' }
    } finally {
      finalizing.value = false
    }
  }

  function setRenderMeasurement(value: PresentationRenderMeasurement) {
    if (
      !revision.value
      || !revisionChecksum.value
      || value.revision_id !== revision.value.revision_id
      || value.revision_checksum !== revisionChecksum.value
    ) return
    renderMeasurement.value = value
    if (error.value?.startsWith('预览仍在检查')) error.value = null
  }

  function cancelProposal() {
    proposal.value = null
  }

  function reset() {
    streamController?.abort()
    streamController = null
    courseId.value = ''
    decks.value = []
    deck.value = null
    revision.value = null
    revisionChecksum.value = null
    slides.value = []
    slideOrder.value = []
    selectedSlideId.value = null
    proposal.value = null
    quality.value = null
    artifact.value = null
    activeGenerationId.value = null
    lastSequence.value = 0
    outlineRevision.value = 0
    eventGap.value = false
    renderMeasurement.value = null
    error.value = null
  }

  return {
    courseId, decks, deck, revision, revisionChecksum, slides, slideOrder, orderedSlides, selectedSlideId, selectedSlide,
    proposal, quality, artifact, activeGenerationId, lastSequence, outlineRevision, eventGap,
    generationProgress, renderMeasurement, loading, generating, proposing, applying, finalizing, error,
    phase, canDownload, measurementReady, listDecks, loadDeck, createDeck, consumeEvent, generate, requestProposal,
    applyProposal, undo, finalize, setRenderMeasurement, cancelProposal, reset,
  }
})
