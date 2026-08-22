import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamAgentRun } from './agent'

describe('streamAgentRun', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('parses SSE events split across response chunks', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: activity\ndata: {"type":"activity","message":"Search'))
        controller.enqueue(encoder.encode('ing..."}\n\nevent: text\ndata: {"type":"text","content":"Hello"}\n\n'))
        controller.enqueue(encoder.encode('event: done\ndata: {"type":"done","status":"completed"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))
    const events: unknown[] = []

    await streamAgentRun('workspace', 'question', (event) => events.push(event), new AbortController().signal)

    expect(events).toEqual([
      { type: 'activity', message: 'Searching...' },
      { type: 'text', content: 'Hello' },
      { type: 'done', status: 'completed' },
    ])
  })
})
