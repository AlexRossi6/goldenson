import { ApiClientError, type ApiErrorShape } from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

function isErrorShape(input: unknown): input is ApiErrorShape {
  if (!input || typeof input !== 'object') {
    return false
  }
  const value = input as { error?: unknown }
  if (!value.error || typeof value.error !== 'object') {
    return false
  }
  const errorValue = value.error as { code?: unknown; message?: unknown; details?: unknown }
  return (
    typeof errorValue.code === 'string' &&
    typeof errorValue.message === 'string' &&
    !!errorValue.details &&
    typeof errorValue.details === 'object'
  )
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null
  }

  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return response.json()
  }

  return response.text()
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body instanceof FormData
    ? { ...(init?.headers ?? {}) }
    : { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  const body = await parseBody(response)

  if (!response.ok) {
    if (isErrorShape(body)) {
      throw new ApiClientError(response.status, body.error.code, body.error.message, body.error.details)
    }

    throw new ApiClientError(response.status, 'HTTP_ERROR', 'Request failed.', {
      response: body,
      statusText: response.statusText,
    })
  }

  return body as T
}
