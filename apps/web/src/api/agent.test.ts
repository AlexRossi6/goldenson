import { afterEach, describe, expect, it, vi } from 'vitest'

import { decideAgentProposal, reconnectAgentRun, streamAgentRun } from './agent'

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

  it('streams continuation events after an approval decision', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'event: activity\ndata: {"type":"activity","message":"Approved, continuing..."}\n\n' +
          'event: text\ndata: {"type":"text","content":"Finished"}\n\n',
        ))
        controller.close()
      },
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const events: unknown[] = []

    await decideAgentProposal(
      'workspace',
      'tool-call',
      true,
      (event) => events.push(event),
      new AbortController().signal,
    )

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/workspaces/workspace/agent/tool-calls/tool-call/decision'),
      expect.objectContaining({ body: '{"approved":true}', method: 'POST' }),
    )
    expect(events).toEqual([
      { type: 'activity', message: 'Approved, continuing...' },
      { type: 'text', content: 'Finished' },
    ])
  })

  it('reconnects to a persisted run event stream', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'event: done\ndata: {"type":"done","status":"waiting_for_approval"}\n\n',
        ))
        controller.close()
      },
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const events: unknown[] = []

    await reconnectAgentRun(
      'workspace',
      'run-1',
      (event) => events.push(event),
      new AbortController().signal,
    )

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/workspaces/workspace/agent/runs/run-1/events'),
      expect.objectContaining({ headers: { Accept: 'text/event-stream' } }),
    )
    expect(events).toEqual([{ type: 'done', status: 'waiting_for_approval' }])
  })
})
