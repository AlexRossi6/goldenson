import { afterEach, describe, expect, it, vi } from 'vitest'

import { installLocalModel, installLocalRuntime } from './localAi'

describe('installLocalModel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('parses progress events split across response chunks', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: downloading\ndata: {"state":"downloading","model_id":"llama3.2:3b","progress":0.'))
        controller.enqueue(encoder.encode('5,"downloaded_bytes":100,"total_bytes":200,"message":null}\n\n'))
        controller.enqueue(encoder.encode('event: ready\ndata: {"state":"ready","model_id":"llama3.2:3b","progress":1,"downloaded_bytes":200,"total_bytes":200,"message":null}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))
    const events: unknown[] = []

    await installLocalModel(
      'llama3.2:3b',
      (event) => events.push(event),
      new AbortController().signal,
    )

    expect(events).toEqual([
      {
        state: 'downloading',
        model_id: 'llama3.2:3b',
        progress: 0.5,
        downloaded_bytes: 100,
        total_bytes: 200,
        message: null,
      },
      {
        state: 'ready',
        model_id: 'llama3.2:3b',
        progress: 1,
        downloaded_bytes: 200,
        total_bytes: 200,
        message: null,
      },
    ])
  })
})

describe('installLocalRuntime', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('parses fragmented runtime progress and surfaces installer failures', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: downloading\ndata: {"state":"downloading","progress":0.'))
        controller.enqueue(encoder.encode('5,"downloaded_bytes":50,"total_bytes":100,"message":"Downloading Ollama..."}\n\n'))
        controller.enqueue(encoder.encode('event: failed\ndata: {"state":"failed","progress":null,"downloaded_bytes":null,"total_bytes":null,"message":"Signature verification failed"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))
    const events: unknown[] = []

    await expect(installLocalRuntime(
      (event) => events.push(event),
      new AbortController().signal,
    )).rejects.toThrow('Signature verification failed')
    expect(events).toHaveLength(2)
  })
})
