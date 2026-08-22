import { apiRequest, apiUrl } from './client'

export type InstallationState =
  | 'available'
  | 'checking'
  | 'downloading'
  | 'installing'
  | 'ready'
  | 'failed'
  | 'cancelled'

export type RuntimeStatus = {
  installed: boolean
  reachable: boolean
  usable: boolean
  version: string | null
  error: string | null
}

export type LocalModelStatus = {
  id: string
  name: string
  size_bytes: number
  installed_size_bytes: number | null
  required_disk_bytes: number
  role: string
  state: InstallationState
  selected: boolean
  recommended: boolean
  progress: number | null
  downloaded_bytes: number | null
  total_bytes: number | null
  error: string | null
}

export type LocalAIStatus = {
  runtime: RuntimeStatus
  selected_model: string | null
  models: LocalModelStatus[]
  disk_free_bytes: number | null
}

export type InstallProgressEvent = {
  state: InstallationState
  model_id: string
  progress: number | null
  downloaded_bytes: number | null
  total_bytes: number | null
  message: string | null
}

export type RuntimeInstallProgressEvent = {
  state: 'downloading' | 'verifying' | 'installing' | 'ready' | 'failed'
  progress: number | null
  downloaded_bytes: number | null
  total_bytes: number | null
  message: string
}

function parseProgressEvent(block: string): InstallProgressEvent | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  return data ? JSON.parse(data) as InstallProgressEvent : null
}

export function getLocalAIStatus(): Promise<LocalAIStatus> {
  return apiRequest('/local-ai/status')
}

export function startLocalRuntime(): Promise<RuntimeStatus> {
  return apiRequest('/local-ai/runtime/start', { method: 'POST' })
}

export async function installLocalRuntime(
  onProgress: (event: RuntimeInstallProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl('/local-ai/runtime/install'), {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error('Ollama installation could not start.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let failure: RuntimeInstallProgressEvent | null = null
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const data = block
        .split(/\r?\n/)
        .find((line) => line.startsWith('data:'))
        ?.slice(5).trimStart()
      if (data) {
        const event = JSON.parse(data) as RuntimeInstallProgressEvent
        onProgress(event)
        if (event.state === 'failed') failure = event
      }
    }
    if (done) break
  }
  if (failure) throw new Error(failure.message)
}

export function selectLocalModel(modelId: string): Promise<LocalAIStatus> {
  return apiRequest('/local-ai/models/select', {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId }),
  })
}

export function removeLocalModel(modelId: string): Promise<LocalAIStatus> {
  return apiRequest(`/local-ai/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' })
}

export function cancelModelInstallation(modelId: string): Promise<void> {
  return apiRequest(`/local-ai/models/${encodeURIComponent(modelId)}/cancel`, { method: 'POST' })
}

export async function installLocalModel(
  modelId: string,
  onProgress: (event: InstallProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/local-ai/models/${encodeURIComponent(modelId)}/install`), {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error('Model installation could not start.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseProgressEvent(block)
      if (event) onProgress(event)
    }
    if (done) break
  }
  const event = parseProgressEvent(buffer)
  if (event) onProgress(event)
}
