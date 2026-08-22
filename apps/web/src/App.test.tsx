import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const apiMocks = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  listPages: vi.fn(),
  createPage: vi.fn(),
  getPage: vi.fn(),
  updatePage: vi.fn(),
  deletePage: vi.fn(),
  listBlocks: vi.fn(),
  createBlock: vi.fn(),
  updateBlock: vi.fn(),
  deleteBlock: vi.fn(),
  listFiles: vi.fn(),
  listPageFiles: vi.fn(),
  uploadFile: vi.fn(),
  deleteFile: vi.fn(),
}))

vi.mock('./api/workspaces', () => ({
  listWorkspaces: apiMocks.listWorkspaces,
  createWorkspace: apiMocks.createWorkspace,
}))
vi.mock('./api/pages', () => ({
  listPages: apiMocks.listPages,
  createPage: apiMocks.createPage,
  getPage: apiMocks.getPage,
  updatePage: apiMocks.updatePage,
  deletePage: apiMocks.deletePage,
}))
vi.mock('./api/blocks', () => ({
  listBlocks: apiMocks.listBlocks,
  createBlock: apiMocks.createBlock,
  updateBlock: apiMocks.updateBlock,
  deleteBlock: apiMocks.deleteBlock,
}))
vi.mock('./api/files', () => ({
  listFiles: apiMocks.listFiles,
  listPageFiles: apiMocks.listPageFiles,
  uploadFile: apiMocks.uploadFile,
  deleteFile: apiMocks.deleteFile,
}))
vi.mock('./components/assistant/AssistantPanel', () => ({
  AssistantPanel: ({
    onWorkspaceChanged,
  }: {
    onWorkspaceChanged: (change: {
      type: 'workspace_changed'
      tool_name: string
      result: Record<string, unknown>
    }) => void
  }) => (
    <button
      type="button"
      onClick={() => onWorkspaceChanged({
        type: 'workspace_changed',
        tool_name: 'create_page',
        result: { id: 'agent-page', workspace_id: 'workspace-1' },
      })}
    >
      Simulate agent create
    </button>
  ),
}))

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App product language', () => {
  beforeEach(() => {
    apiMocks.listPages.mockResolvedValue({ items: [] })
    apiMocks.listFiles.mockResolvedValue({ items: [] })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('describes first-run persistence without developer terminology', async () => {
    apiMocks.listWorkspaces.mockResolvedValue({ items: [] })
    renderApp()

    expect(await screen.findByText(/saved automatically on this computer/i)).toBeInTheDocument()
    expect(screen.queryByText(/REST API|persist.*API/i)).not.toBeInTheDocument()
  })

  it('uses workspace language and omits debug metadata', async () => {
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{
        id: 'workspace-1',
        name: 'My Workspace',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }],
    })
    renderApp()

    expect(await screen.findByRole('heading', { name: 'Your workspace' })).toBeInTheDocument()
    await waitFor(() => expect(apiMocks.listPages).toHaveBeenCalled())
    expect(screen.queryByText(/REST API|persist.*API/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Pages:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Selected:/)).not.toBeInTheDocument()
  })

  it('refetches the page tree after an approved agent mutation', async () => {
    const user = userEvent.setup()
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{
        id: 'workspace-1',
        name: 'My Workspace',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }],
    })
    apiMocks.listPages
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValue({
        items: [{
          id: 'agent-page',
          workspace_id: 'workspace-1',
          parent_page_id: null,
          title: 'Test Agent',
          position: 0,
          version: 1,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        }],
      })
    apiMocks.getPage.mockResolvedValue({
      id: 'agent-page',
      workspace_id: 'workspace-1',
      parent_page_id: null,
      title: 'Test Agent',
      position: 0,
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    apiMocks.listBlocks.mockResolvedValue({ items: [] })
    apiMocks.listPageFiles.mockResolvedValue({ items: [] })
    renderApp()

    await user.click(await screen.findByRole('button', { name: 'Simulate agent create' }))

    expect(await screen.findByRole('button', { name: 'Test Agent' })).toBeInTheDocument()
    expect(apiMocks.listPages).toHaveBeenCalledTimes(2)
  })
})