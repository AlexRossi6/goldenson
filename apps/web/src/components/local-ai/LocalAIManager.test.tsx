import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LocalAIManager } from './LocalAIManager'

const apiMocks = vi.hoisted(() => ({
  getLocalAIStatus: vi.fn(),
  startLocalRuntime: vi.fn(),
  selectLocalModel: vi.fn(),
  removeLocalModel: vi.fn(),
  cancelModelInstallation: vi.fn(),
  installLocalModel: vi.fn(),
  installLocalRuntime: vi.fn(),
}))

vi.mock('../../api/localAi', () => apiMocks)

const availableStatus = {
  runtime: { installed: true, reachable: true, usable: true, version: '1.0', error: null },
  selected_model: null,
  disk_free_bytes: 20_000_000_000,
  models: [{
    id: 'llama3.2:3b',
    name: 'Llama 3.2 3B',
    size_bytes: 2_000_000_000,
    installed_size_bytes: null,
    required_disk_bytes: 3_000_000_000,
    role: 'Fast general assistant',
    state: 'available',
    selected: false,
    recommended: true,
    progress: null,
    downloaded_bytes: null,
    total_bytes: null,
    error: null,
  }],
}

const readyStatus = {
  ...availableStatus,
  selected_model: 'llama3.2:3b',
  models: [{
    ...availableStatus.models[0],
    installed_size_bytes: 2_000_000_000,
    state: 'ready',
    selected: true,
  }],
}

const unavailableStatus = {
  ...availableStatus,
  runtime: {
    installed: false,
    reachable: false,
    usable: false,
    version: null,
    error: 'Ollama is not installed.',
  },
}

describe('LocalAIManager', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('opens first-run setup and confirms the local model download', async () => {
    const user = userEvent.setup()
    apiMocks.getLocalAIStatus.mockResolvedValue(availableStatus)

    render(<LocalAIManager onReadyChange={vi.fn()} />)

    expect(await screen.findByRole('dialog', { name: 'Local AI' })).toBeInTheDocument()
    expect(screen.getByText('Set up your local AI')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Install model' }))

    const confirmation = screen.getByRole('alertdialog', { name: 'Install Llama 3.2 3B' })
    expect(within(confirmation).getByText(/runs entirely on your computer/i)).toBeInTheDocument()
    expect(within(confirmation).getByText(/required disk space/i)).toBeInTheDocument()
  })

  it('reports a selected ready model to the assistant', async () => {
    const onReadyChange = vi.fn()
    apiMocks.getLocalAIStatus.mockResolvedValue(readyStatus)

    render(<LocalAIManager onReadyChange={onReadyChange} />)

    expect(await screen.findByText('Llama 3.2 3B · Ready')).toBeInTheDocument()
    await waitFor(() => expect(onReadyChange).toHaveBeenLastCalledWith(true))
    expect(screen.queryByRole('dialog', { name: 'Local AI' })).not.toBeInTheDocument()
  })

  it('prevents a model install when Ollama is unavailable', async () => {
    apiMocks.getLocalAIStatus.mockResolvedValue(unavailableStatus)

    render(<LocalAIManager onReadyChange={vi.fn()} />)

    expect(await screen.findByText('Ollama is required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Requires Ollama' })).toBeDisabled()
  })

  it('confirms Ollama installation and shows streamed download progress', async () => {
    const user = userEvent.setup()
    let finishInstallation: (() => void) | undefined
    apiMocks.getLocalAIStatus
      .mockResolvedValueOnce(unavailableStatus)
      .mockResolvedValueOnce(readyStatus)
    apiMocks.startLocalRuntime.mockResolvedValue(readyStatus.runtime)
    apiMocks.installLocalRuntime.mockImplementation(async (onProgress) => {
      onProgress({
        state: 'downloading',
        progress: 0.5,
        downloaded_bytes: 90_000_000,
        total_bytes: 180_000_000,
        message: 'Downloading Ollama...',
      })
      await new Promise<void>((resolve) => {
        finishInstallation = resolve
      })
    })

    render(<LocalAIManager onReadyChange={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'Install Ollama' }))
    const confirmation = screen.getByRole('alertdialog', { name: 'Install Ollama' })
    expect(within(confirmation).getByText(/official signed Ollama application/i)).toBeInTheDocument()
    await user.click(within(confirmation).getByRole('button', { name: 'Install Ollama' }))

    expect(await screen.findByRole('progressbar', { name: 'Installing Ollama' })).toHaveAttribute('value', '0.5')
    expect(screen.getByText('Downloading Ollama...')).toBeInTheDocument()
    expect(screen.getByText(/50%/)).toBeInTheDocument()
    finishInstallation?.()
    expect(await screen.findByText('Llama 3.2 3B · Ready')).toBeInTheDocument()
    expect(apiMocks.startLocalRuntime).toHaveBeenCalledOnce()
  })

  it('shows streamed progress and cancels an installation', async () => {
    const user = userEvent.setup()
    apiMocks.getLocalAIStatus.mockResolvedValue(availableStatus)
    apiMocks.installLocalModel.mockImplementation(async (_modelId, onProgress) => {
      onProgress({
        state: 'downloading',
        model_id: 'llama3.2:3b',
        progress: 0.5,
        downloaded_bytes: 1_000_000_000,
        total_bytes: 2_000_000_000,
        message: 'Downloading model layers...',
      })
      await new Promise(() => undefined)
    })
    apiMocks.cancelModelInstallation.mockResolvedValue(undefined)

    render(<LocalAIManager onReadyChange={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'Install model' }))
    const confirmation = screen.getByRole('alertdialog', { name: 'Install Llama 3.2 3B' })
    await user.click(within(confirmation).getByRole('button', { name: 'Install' }))

    expect(await screen.findByText('Downloading model layers...')).toBeInTheDocument()
    expect(screen.getByText(/50%/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(apiMocks.cancelModelInstallation).toHaveBeenCalledWith('llama3.2:3b')
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
