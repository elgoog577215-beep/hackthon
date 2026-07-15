import { describe, expect, it, vi } from 'vitest'
import { consumePresentationEventStream } from '@/services/presentations'
import type { PresentationEvent } from '@/types/presentation'

const event = (sequence: number): PresentationEvent => ({
  schema_version: 'presentation-event/v1',
  event_type: 'progress',
  deck_id: 'deck-1',
  generation_id: 'generation-1',
  event_seq: sequence,
  outline_revision: 1,
  revision_id: null,
  emitted_at: '2026-07-15T00:00:00Z',
  payload: { completed: sequence, total: 2 },
})

describe('presentation event stream', () => {
  it('跨网络分块解析有序 SSE，不丢失尾部事件', async () => {
    const encoder = new TextEncoder()
    const first = `id: generation-1:1\ndata: ${JSON.stringify(event(1))}\n\n`
    const second = `id: generation-1:2\ndata: ${JSON.stringify(event(2))}\n\n`
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(first.slice(0, 31)))
        controller.enqueue(encoder.encode(first.slice(31) + second))
        controller.close()
      },
    }), { status: 200, headers: { 'content-type': 'text/event-stream' } })
    const received = vi.fn()

    await consumePresentationEventStream(response, received)

    expect(received.mock.calls.map(call => call[0].event_seq)).toEqual([1, 2])
  })

  it('把非 2xx 响应的结构化错误返回给工作台', async () => {
    const response = new Response(JSON.stringify({ detail: { code: 'generation_conflict', message: '已有课件正在生成' } }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    })

    await expect(consumePresentationEventStream(response, vi.fn())).rejects.toThrow('已有课件正在生成')
  })
})
