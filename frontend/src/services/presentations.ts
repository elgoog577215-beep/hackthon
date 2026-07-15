import type {
  PresentationArtifact,
  PresentationDeck,
  PresentationEvent,
  PresentationProposal,
  PresentationQualityIssue,
  PresentationRenderMeasurement,
  PresentationRevision,
  PresentationScope,
  PresentationTemplateId,
} from '@/types/presentation'
import http, { learnerIdentityHeaders, withApiBase } from '@/utils/http'

export interface PresentationDeckSnapshot {
  deck: PresentationDeck
  revision: PresentationRevision | null
  revision_checksum: string | null
  working?: {
    generation_id: string
    event_seq: number
    outline_revision: number
    slide_order: string[]
    slides: PresentationRevision['slides']
  } | null
  quality?: {
    report_id?: string
    status: 'passed' | 'blocked' | 'advisory'
    issues: PresentationQualityIssue[]
  } | null
  artifact?: PresentationArtifact | null
}

export interface CreatePresentationInput {
  request_id: string
  title: string
  scope: PresentationScope
  purpose: 'teaching' | 'self_study'
  template_id: PresentationTemplateId
  page_budget: number
  extra_requirements: string
}

export interface GeneratePresentationInput {
  request_id: string
  expected_revision_id: string | null
  page_budget?: number
  extra_requirements?: string
}

export interface PresentationChatInput {
  request_id: string
  expected_revision_id: string
  scope: 'slide' | 'deck'
  slide_ids: string[]
  prompt: string
}

const toDetail = (value: unknown): string => {
  if (!value || typeof value !== 'object') return ''
  const payload = value as Record<string, unknown>
  const detail = payload.detail || payload.message || payload.error
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const structured = detail as Record<string, unknown>
    return String(structured.message || structured.code || '')
  }
  return ''
}

export function resolveInitialPresentationScope(sectionId: unknown): 'chapter' | 'course' {
  return typeof sectionId === 'string' && sectionId.trim() ? 'chapter' : 'course'
}

const parseSseBlock = (block: string): { id: string; data: string } | null => {
  const lines = block.split(/\r?\n/)
  let id = ''
  const data: string[] = []
  for (const line of lines) {
    if (line.startsWith('id:')) id = line.slice(3).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  return data.length ? { id, data: data.join('\n') } : null
}

export async function consumePresentationEventStream(
  response: Response,
  onEvent: (event: PresentationEvent) => unknown | Promise<unknown>,
): Promise<void> {
  if (!response.ok) {
    let detail = `课件请求失败（${response.status}）`
    try {
      detail = toDetail(await response.json()) || detail
    } catch {
      // Keep the status-based message when the server returned no JSON body.
    }
    throw new Error(detail)
  }
  if (!response.body) throw new Error('课件事件流不可用')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const parsed = parseSseBlock(block)
      if (!parsed) continue
      const event = JSON.parse(parsed.data) as PresentationEvent
      await onEvent(event)
    }
    if (done) break
  }
  const tail = parseSseBlock(buffer)
  if (tail) await onEvent(JSON.parse(tail.data) as PresentationEvent)
}

export const presentationService = {
  async create(courseId: string, input: CreatePresentationInput): Promise<PresentationDeckSnapshot> {
    const response = await http.post(`/api/courses/${encodeURIComponent(courseId)}/presentations`, input)
    return response.data as PresentationDeckSnapshot
  },

  async list(courseId: string): Promise<PresentationDeck[]> {
    const response = await http.get(`/api/courses/${encodeURIComponent(courseId)}/presentations`, { silentError: true })
    const data = response.data as PresentationDeck[] | { decks?: PresentationDeck[] }
    return Array.isArray(data) ? data : data.decks || []
  },

  async get(deckId: string): Promise<PresentationDeckSnapshot> {
    const response = await http.get(`/api/presentations/${encodeURIComponent(deckId)}`, { silentError: true })
    return response.data as PresentationDeckSnapshot
  },

  async generate(
    deckId: string,
    input: GeneratePresentationInput,
    onEvent: (event: PresentationEvent) => unknown | Promise<unknown>,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(withApiBase(`/api/presentations/${encodeURIComponent(deckId)}/generate`), {
      method: 'POST',
      headers: learnerIdentityHeaders({ Accept: 'text/event-stream', 'Content-Type': 'application/json' }),
      body: JSON.stringify(input),
      signal,
    })
    await consumePresentationEventStream(response, onEvent)
  },

  async replay(
    deckId: string,
    generationId: string,
    afterSequence: number,
    onEvent: (event: PresentationEvent) => unknown | Promise<unknown>,
    signal?: AbortSignal,
  ): Promise<void> {
    const query = new URLSearchParams({ generation_id: generationId, after_seq: String(afterSequence) })
    const response = await fetch(withApiBase(`/api/presentations/${encodeURIComponent(deckId)}/events?${query}`), {
      headers: learnerIdentityHeaders({ Accept: 'text/event-stream' }),
      signal,
    })
    await consumePresentationEventStream(response, onEvent)
  },

  async propose(deckId: string, input: PresentationChatInput): Promise<PresentationProposal> {
    const response = await http.post(`/api/presentations/${encodeURIComponent(deckId)}/chat`, input)
    return (response.data?.proposal || response.data) as PresentationProposal
  },

  async applyProposal(
    deckId: string,
    proposalId: string,
    input: { expected_revision_id: string; command_id: string },
  ): Promise<PresentationDeckSnapshot> {
    const response = await http.post(
      `/api/presentations/${encodeURIComponent(deckId)}/patches/${encodeURIComponent(proposalId)}/apply`,
      input,
    )
    return response.data as PresentationDeckSnapshot
  },

  async restore(
    deckId: string,
    revisionId: string,
    input: { expected_revision_id: string; command_id: string },
  ): Promise<PresentationDeckSnapshot> {
    const response = await http.post(
      `/api/presentations/${encodeURIComponent(deckId)}/revisions/${encodeURIComponent(revisionId)}/restore`,
      input,
    )
    return response.data as PresentationDeckSnapshot
  },

  async finalize(
    deckId: string,
    input: { expected_revision_id: string; command_id: string; render_measurement: PresentationRenderMeasurement },
  ): Promise<PresentationDeckSnapshot> {
    const response = await http.post(`/api/presentations/${encodeURIComponent(deckId)}/finalize`, input)
    return response.data as PresentationDeckSnapshot
  },

  artifactUrl(artifactId: string, format: 'html' | 'pptx'): string {
    return withApiBase(`/api/presentation-artifacts/${encodeURIComponent(artifactId)}/${format}`)
  },
}
