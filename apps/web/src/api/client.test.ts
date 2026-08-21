import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from './client'
import { ApiClientError } from '../types/api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiRequest', () => {
  it('returns parsed JSON for successful responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [{ id: 'w1' }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiRequest<{ items: Array<{ id: string }> }>('/workspaces')

    expect(result.items[0].id).toBe('w1')
    expect(fetchMock).toHaveBeenCalledWith('/api/workspaces', expect.any(Object))
  })

  it('returns null for 204 responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiRequest<null>('/pages/123', { method: 'DELETE' })

    expect(result).toBeNull()
  })

  it('throws ApiClientError for typed error responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'NOT_FOUND',
            message: 'Page not found',
            details: { page_id: 'p-1' },
          },
        }),
        {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const error = await apiRequest('/pages/p-1').catch((caught) => caught)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error).toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: 'Page not found',
    })
  })
})
