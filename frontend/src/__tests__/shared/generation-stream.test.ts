import { describe, expect, it, vi } from 'vitest'

import { parseSseBlock, postGenerationStream } from '@/shared/generation-stream'

describe('generation stream transport', () => {
  it('parses one SSE block without exposing protocol fields as content', () => {
    expect(parseSseBlock('event: heartbeat\ndata: {"stage":"writing"}\n\n')).toEqual({
      event: 'heartbeat',
      data: { stage: 'writing' },
    })
  })

  it('reports progress and releases only the completed structured result', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: started\ndata: {"status":"running","message":"已收到"}\n\n'
          + 'event: heartbeat\ndata: {"status":"running","message":"正在生成"}\n\n',
        ))
        controller.enqueue(encoder.encode(
          'event: complete\ndata: {"status":"completed","result":{"candidate_id":"c1"}}\n\n',
        ))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))
    const progress = vi.fn()

    await expect(postGenerationStream<{ candidate_id: string }>(
      '/api/generate',
      { instruction: '优化' },
      { onProgress: progress },
    )).resolves.toEqual({ candidate_id: 'c1' })
    expect(progress).toHaveBeenCalledTimes(3)
  })

  it('turns a streamed terminal failure into one typed error', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'event: error\ndata: {"code":"candidate_invalid","message":"候选结果不完整","http_status":422}\n\n',
        ))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))

    await expect(postGenerationStream('/api/generate', {})).rejects.toMatchObject({
      code: 'candidate_invalid',
      httpStatus: 422,
    })
  })
})
