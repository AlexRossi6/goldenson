import { apiRequest, apiUrl } from './client'

export type AgentSource = {
  kind: 'page' | 'block' | 'file'
  title: string
  snippet: string
  page_id: string | null
  block_id: string | null
  file_id: string | null
  score: number
}

export type AgentProposal = {
  tool_call_id: string
  tool_name: string
  permission: 'WRITE' | 'DESTRUCTIVE'
  arguments: Record<string, unknown>
  expected_effect: string
}

export type AgentEvent =
  | { type: 'run'; run_id: string }
  | { type: 'activity'; message: string }
  | { type: 'sources'; sources: AgentSource[] }
  | { type: 'text'; content: string }
  | { type: 'proposal'; proposal: AgentProposal }
  | { type: 'error'; message: string }
  | { type: 'done'; status: string }

function parseEvent(block: string): AgentEvent | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  if (!data) return null
  return JSON.parse(data) as AgentEvent
}

export async function streamAgentRun(
  workspaceId: string,
  message: string,
  onEvent: (event: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/workspaces/${workspaceId}/agent/runs`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error('The local agent could not start.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseEvent(block)
      if (event) onEvent(event)
    }
    if (done) break
  }
  const finalEvent = parseEvent(buffer)
  if (finalEvent) onEvent(finalEvent)
}

export async function decideAgentProposal(
  workspaceId: string,
  toolCallId: string,
  approved: boolean,
): Promise<{ status: string }> {
  return apiRequest(`/workspaces/${workspaceId}/agent/tool-calls/${toolCallId}/decision`, {
    method: 'POST',
    body: JSON.stringify({ approved }),
  })
}

export async function cancelAgentRun(runId: string): Promise<void> {
  await apiRequest(`/agent/runs/${runId}/cancel`, { method: 'POST' })
}
