import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentEvent } from '../../api/agent'
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
    const onOpenSource = vi.fn()
    apiMocks.streamAgentRun.mockImplementation(async (_workspaceId, _message, onEvent) => {
      onEvent({ type: 'run', run_id: 'run-1' })
      onEvent({ type: 'activity', message: 'Searching your workspace...' })
      onEvent({
        type: 'sources',
        sources: [{
          kind: 'block',
          title: 'Local AI',
          snippet: 'Ollama notes',
          page_id: 'page-1',
          block_id: 'block-1',
          file_id: null,
          score: 1,
        }],
      })
      onEvent({ type: 'text', content: 'You are comparing ' })
      onEvent({ type: 'text', content: 'Ollama and llama.cpp.' })
      onEvent({ type: 'done', status: 'completed' })
    })
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={onOpenSource} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'What am I working on?')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(screen.getByText('What am I working on?')).toBeInTheDocument()
    expect(screen.getByText('You are comparing Ollama and llama.cpp.')).toBeInTheDocument()
    expect(screen.getByText('In page')).toBeInTheDocument()
    expect(screen.getByText('Ollama notes')).toBeInTheDocument()
    expect(question).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Local AI' }))
    expect(onOpenSource).toHaveBeenCalledWith(expect.objectContaining({
      page_id: 'page-1',
      block_id: 'block-1',
    }))
  })

  it('shows a proposed change and sends approval explicitly', async () => {
    const user = userEvent.setup()
    const onWorkspaceChanged = vi.fn()
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
    apiMocks.decideAgentProposal.mockImplementation(
      async (_workspaceId, _toolCallId, _approved, onEvent) => {
        onEvent({ type: 'activity', message: 'Approved, continuing...' })
        onEvent({
          type: 'workspace_changed',
          tool_name: 'create_page',
          result: { id: 'page-2', title: 'Draft' },
        })
        onEvent({ type: 'text', content: 'Draft created.' })
        onEvent({ type: 'done', status: 'completed' })
      },
    )
    render(
      <AssistantPanel
        workspaceId="workspace-1"
        onOpenSource={vi.fn()}
        onWorkspaceChanged={onWorkspaceChanged}
      />,
    )

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Create a draft')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Create page "Draft".')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(apiMocks.decideAgentProposal).toHaveBeenCalledWith(
      'workspace-1',
      'tool-1',
      true,
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(screen.getByText('Create a draft')).toBeInTheDocument()
    expect(screen.getByText('Draft created.')).toBeInTheDocument()
    expect(onWorkspaceChanged).toHaveBeenCalledWith({
      type: 'workspace_changed',
      tool_name: 'create_page',
      result: { id: 'page-2', title: 'Draft' },
    })
  })

  it('aborts and cancels a running request', async () => {
    const user = userEvent.setup()
    let capturedSignal: AbortSignal | null = null
    apiMocks.streamAgentRun.mockImplementation((_workspaceId, _message, onEvent, signal) => {
      capturedSignal = signal
      onEvent({ type: 'run', run_id: 'run-1' })
      onEvent({
        type: 'sources',
        sources: [{
          kind: 'block', title: 'Local AI', snippet: 'Ollama notes', page_id: 'page-1',
          block_id: 'block-1', file_id: null, score: 1,
        }],
      })
      return new Promise<void>(() => undefined)
    })
    apiMocks.cancelAgentRun.mockResolvedValue(undefined)
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Long question')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(capturedSignal?.aborted).toBe(true))
    expect(apiMocks.cancelAgentRun).toHaveBeenCalledWith('workspace-1', 'run-1')
    expect(screen.getByText('Cancelled.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument()
  })

  it('marks a partial answer as cancelled instead of leaving it looking complete', async () => {
    const user = userEvent.setup()
    apiMocks.streamAgentRun.mockImplementation((_workspaceId, _message, onEvent) => {
      onEvent({ type: 'run', run_id: 'run-1' })
      onEvent({ type: 'text', content: 'Based on the available notes,' })
      return new Promise<void>(() => undefined)
    })
    apiMocks.cancelAgentRun.mockResolvedValue(undefined)
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Long summary')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(screen.getByText(/Based on the available notes,\s+Response cancelled\./)).toBeInTheDocument()
  })

  it('shows active progress while the local model is preparing an answer', async () => {
    const user = userEvent.setup()
    const callback: { send?: (event: AgentEvent) => void } = {}
    apiMocks.streamAgentRun.mockImplementation((_workspaceId, _message, onEvent) => {
      callback.send = onEvent
      onEvent({ type: 'activity', message: 'Searching your workspace...' })
      return new Promise<void>(() => undefined)
    })
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Summarize my notes')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Searching your workspace')
    callback.send?.({
      type: 'sources',
      sources: [{
        kind: 'block', title: 'Local AI', snippet: 'Ollama notes', page_id: 'page-1',
        block_id: 'block-1', file_id: null, score: 1,
      }],
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Thinking')
    expect(screen.queryByRole('button', { name: 'Local AI' })).not.toBeInTheDocument()
    callback.send?.({ type: 'text', content: 'The notes compare local runtimes.' })
    expect(await screen.findByRole('button', { name: 'Local AI' })).toBeInTheDocument()
  })

  it('shows a safe error and remains ready for another question', async () => {
    const user = userEvent.setup()
    apiMocks.streamAgentRun.mockImplementation(async (_workspaceId, _message, onEvent) => {
      onEvent({ type: 'error', message: 'The local agent could not complete this request.' })
      onEvent({ type: 'done', status: 'failed' })
    })
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, 'Summarize my notes')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The local agent could not complete this request.',
    )
    expect(question).toBeEnabled()
  })

  it('does not submit while an input method is composing text', async () => {
    const user = userEvent.setup()
    apiMocks.streamAgentRun.mockResolvedValue(undefined)
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const question = screen.getByLabelText('Ask the workspace assistant')
    await waitFor(() => expect(question).toBeEnabled())
    await user.type(question, '未確定')
    fireEvent.keyDown(question, { key: 'Enter', isComposing: true })

    expect(apiMocks.streamAgentRun).not.toHaveBeenCalled()
    expect(question).toHaveValue('未確定')
  })

  it('collapses and expands the responsive assistant content', async () => {
    const user = userEvent.setup()
    render(<AssistantPanel workspaceId="workspace-1" onOpenSource={vi.fn()} />)

    const collapse = screen.getByRole('button', { name: 'Collapse assistant' })
    expect(collapse).toHaveAttribute('aria-expanded', 'true')
    await user.click(collapse)

    const expand = screen.getByRole('button', { name: 'Expand assistant' })
    expect(expand).toHaveAttribute('aria-expanded', 'false')
    await user.click(expand)
    expect(screen.getByRole('button', { name: 'Collapse assistant' })).toBeInTheDocument()
  })
})
