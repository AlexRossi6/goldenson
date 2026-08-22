import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AssistantPanel } from './AssistantPanel'

const apiMocks = vi.hoisted(() => ({
  streamAgentRun: vi.fn(),
  decideAgentProposal: vi.fn(),
  cancelAgentRun: vi.fn(),
}))

vi.mock('../../api/agent', () => apiMocks)

const localAIMocks = vi.hoisted(() => ({
  getLocalAIStatus: vi.fn(),
  startLocalRuntime: vi.fn(),
  selectLocalModel: vi.fn(),
  removeLocalModel: vi.fn(),
  cancelModelInstallation: vi.fn(),
  installLocalModel: vi.fn(),
}))

vi.mock('../../api/localAi', () => localAIMocks)

describe('AssistantPanel', () => {
  beforeEach(() => {
    localAIMocks.getLocalAIStatus.mockResolvedValue({
      runtime: { installed: true, reachable: true, usable: true, version: '1.0', error: null },
      selected_model: 'llama3.2:3b',
      disk_free_bytes: 20_000_000_000,
      models: [{
        id: 'llama3.2:3b',
        name: 'Llama 3.2 3B',
        size_bytes: 2_000_000_000,
        installed_size_bytes: 2_000_000_000,
        required_disk_bytes: 3_000_000_000,
        role: 'Fast general assistant',
        state: 'ready',
        selected: true,
        recommended: true,
        progress: null,
        downloaded_bytes: null,
        total_bytes: null,
        error: null,
      }],
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows streamed activity, answer text, and navigable sources', async () => {
    const user = userEvent.setup()
    const onSelectPage = vi.fn()
    apiMocks.streamAgentRun.mockImplementation(async (_workspaceId, _message, onEvent) => {
      onEvent({ type: 'run', run_id: 'run-1' })
      onEvent({ type: 'activity', message: 'Searching your workspace...' })
      onEvent({
        type: 'sources',
        sources: [{
          kind: 'page',
          title: 'Local AI',
          snippet: 'Ollama notes',
          page_id: 'page-1',
          block_id: null,
          file_id: null,
          score: 1,
        }],
      })
      onEvent({ type: 'text', content: 'You are comparing ' })
      onEvent({ type: 'text', content: 'Ollama and llama.cpp.' })
      onEvent({ type: 'done', status: 'completed' })
    })
    render(<AssistantPanel workspaceId="workspace-1" onSelectPage={onSelectPage} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'What am I working on?')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('Searching your workspace...')).toBeInTheDocument()
    expect(screen.getByText('You are comparing Ollama and llama.cpp.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Local AI' }))
    expect(onSelectPage).toHaveBeenCalledWith('page-1')
  })

  it('shows a proposed change and sends approval explicitly', async () => {
    const user = userEvent.setup()
    apiMocks.streamAgentRun.mockImplementation(async (_workspaceId, _message, onEvent) => {
      onEvent({
        type: 'proposal',
        proposal: {
          tool_call_id: 'tool-1',
          tool_name: 'create_page',
          permission: 'WRITE',
          arguments: { title: 'Draft' },
          expected_effect: 'Create page "Draft".',
        },
      })
      onEvent({ type: 'done', status: 'awaiting_approval' })
    })
    apiMocks.decideAgentProposal.mockResolvedValue({ status: 'completed' })
    render(<AssistantPanel workspaceId="workspace-1" onSelectPage={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Create a draft')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Create page "Draft".')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(apiMocks.decideAgentProposal).toHaveBeenCalledWith('workspace-1', 'tool-1', true)
    expect(await screen.findByText('Change applied.')).toBeInTheDocument()
  })

  it('aborts and cancels a running request', async () => {
    const user = userEvent.setup()
    let capturedSignal: AbortSignal | null = null
    apiMocks.streamAgentRun.mockImplementation((_workspaceId, _message, onEvent, signal) => {
      capturedSignal = signal
      onEvent({ type: 'run', run_id: 'run-1' })
      return new Promise<void>(() => undefined)
    })
    apiMocks.cancelAgentRun.mockResolvedValue(undefined)
    render(<AssistantPanel workspaceId="workspace-1" onSelectPage={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Long question')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(capturedSignal?.aborted).toBe(true))
    expect(apiMocks.cancelAgentRun).toHaveBeenCalledWith('run-1')
    expect(screen.getByText('Cancelled.')).toBeInTheDocument()
  })
})
