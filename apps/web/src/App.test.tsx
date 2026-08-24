import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { useUiStore } from './stores/ui'

const apiMocks = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  searchWorkspace: vi.fn(),
  getWorkspaceIndexHealth: vi.fn(),
  retryFailedWorkspaceIndexing: vi.fn(),
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
  retryFileIndex: vi.fn(),
  getRelatedPages: vi.fn(),
  getPageKnowledge: vi.fn(),
  reindexPage: vi.fn(),
}))

vi.mock('./api/workspaces', () => ({
  listWorkspaces: apiMocks.listWorkspaces,
  createWorkspace: apiMocks.createWorkspace,
  searchWorkspace: apiMocks.searchWorkspace,
  getWorkspaceIndexHealth: apiMocks.getWorkspaceIndexHealth,
  retryFailedWorkspaceIndexing: apiMocks.retryFailedWorkspaceIndexing,
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
  retryFileIndex: apiMocks.retryFileIndex,
  getFileDownloadUrl: (fileId: string) => `/api/files/${fileId}/download`,
}))
vi.mock('./api/knowledge', () => ({
  getRelatedPages: apiMocks.getRelatedPages,
  getPageKnowledge: apiMocks.getPageKnowledge,
  reindexPage: apiMocks.reindexPage,
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
    useUiStore.setState({ selectedPageId: null, sidebarOpen: true, expandedPages: {} })
    apiMocks.listPages.mockResolvedValue({ items: [] })
    apiMocks.listFiles.mockResolvedValue({ items: [] })
    apiMocks.getWorkspaceIndexHealth.mockResolvedValue({
      status: 'ready',
      pages: { total: 0, ready: 0, indexing: 0, stale: 0, failed: 0 },
      files: { total: 0, ready: 0, indexing: 0, stale: 0, failed: 0, metadata_only: 0 },
    })
    apiMocks.retryFailedWorkspaceIndexing.mockResolvedValue({ queued: 0 })
    apiMocks.retryFileIndex.mockResolvedValue({ status: 'pending' })
    apiMocks.getRelatedPages.mockResolvedValue({ items: [] })
    apiMocks.getPageKnowledge.mockResolvedValue({ status: 'ready', concepts: [] })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
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

    expect(await screen.findByRole('heading', { name: 'My Workspace', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('GoldenSon')).toBeInTheDocument()
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

  it('opens and highlights a block result from workspace search', async () => {
    const user = userEvent.setup()
    const pages = [
      {
        id: 'page-1', workspace_id: 'workspace-1', parent_page_id: null, title: 'First page', position: 0, version: 1,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'page-2', workspace_id: 'workspace-1', parent_page_id: null, title: 'Second page', position: 1, version: 1,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      },
    ]
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{ id: 'workspace-1', name: 'My Workspace', created_at: pages[0].created_at, updated_at: pages[0].updated_at }],
    })
    apiMocks.listPages.mockResolvedValue({ items: pages })
    apiMocks.getPage.mockImplementation((pageId: string) => Promise.resolve(pages.find((page) => page.id === pageId)))
    apiMocks.listBlocks.mockImplementation((pageId: string) => Promise.resolve({
      items: pageId === 'page-2' ? [{
        id: 'block-2', page_id: 'page-2', type: 'paragraph', position: 0,
        content: { text: 'Matching paragraph' }, version: 1,
        created_at: pages[0].created_at, updated_at: pages[0].updated_at,
      }] : [],
    }))
    apiMocks.listPageFiles.mockResolvedValue({ items: [] })
    apiMocks.searchWorkspace.mockResolvedValue({
      context: '',
      sources: [{
        kind: 'block', title: 'Second page', snippet: 'Matching paragraph', page_id: 'page-2',
        block_id: 'block-2', file_id: null, score: 0.9,
      }],
    })
    renderApp()

    await user.type(await screen.findByRole('searchbox', { name: 'Search workspace' }), 'matching paragraph')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    const search = await screen.findByRole('region', { name: 'Workspace search' })
    await user.click(await within(search).findByRole('button', { name: 'Second page' }))

    expect(search).toBeInTheDocument()
    expect(await screen.findByRole('textbox', { name: 'Page title' })).toHaveValue('Second page')
    const pageContent = await screen.findByRole('list', { name: 'Page content' })
    expect(within(pageContent).getByRole('listitem')).toHaveClass('is-highlighted')
    expect(within(pageContent).getByRole('listitem')).toHaveAttribute('data-block-id', 'block-2')
  })

  it('keeps related exploration on the current page during rapid navigation', async () => {
    const user = userEvent.setup()
    const pages = [
      {
        id: 'page-a', workspace_id: 'workspace-1', parent_page_id: null, title: 'Page A', position: 0, version: 1,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'page-b', workspace_id: 'workspace-1', parent_page_id: null, title: 'Page B', position: 1, version: 1,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'page-c', workspace_id: 'workspace-1', parent_page_id: null, title: 'Page C', position: 2, version: 1,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      },
    ]
    let resolvePageA: ((value: { items: Array<{ page_id: string; title: string; snippet: string; block_id: string | null }> }) => void) | undefined
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{ id: 'workspace-1', name: 'My Workspace', created_at: pages[0].created_at, updated_at: pages[0].updated_at }],
    })
    apiMocks.listPages.mockResolvedValue({ items: pages })
    apiMocks.getPage.mockImplementation((pageId: string) => Promise.resolve(pages.find((page) => page.id === pageId)))
    apiMocks.listBlocks.mockImplementation((pageId: string) => Promise.resolve({
      items: pageId === 'page-c' ? [{
        id: 'block-c', page_id: 'page-c', type: 'paragraph', position: 0,
        content: { text: 'Evidence on page C' }, version: 1,
        created_at: pages[0].created_at, updated_at: pages[0].updated_at,
      }] : [],
    }))
    apiMocks.listPageFiles.mockResolvedValue({ items: [] })
    apiMocks.getRelatedPages.mockImplementation((pageId: string) => {
      if (pageId === 'page-a') {
        return new Promise((resolve) => { resolvePageA = resolve })
      }
      if (pageId === 'page-b') {
        return Promise.resolve({
          items: [{ page_id: 'page-c', title: 'Page C', snippet: 'Evidence on page C', block_id: 'block-c' }],
        })
      }
      return Promise.resolve({
        items: [{ page_id: 'page-a', title: 'Page A', snippet: 'Evidence on page A', block_id: null }],
      })
    })
    renderApp()

    expect(await screen.findByRole('textbox', { name: 'Page title' })).toHaveValue('Page A')
    await waitFor(() => expect(resolvePageA).toBeTypeOf('function'))
    await user.click(screen.getByRole('button', { name: 'Page B' }))
    expect(await screen.findByRole('textbox', { name: 'Page title' })).toHaveValue('Page B')
    const related = await screen.findByRole('complementary', { name: 'Related content' })
    expect(await within(related).findByRole('button', { name: 'Page C' })).toBeInTheDocument()

    resolvePageA?.({
      items: [{ page_id: 'stale-page', title: 'Stale A result', snippet: 'Old evidence', block_id: null }],
    })
    await waitFor(() => expect(screen.queryByText('Stale A result')).not.toBeInTheDocument())

    await user.click(within(related).getByRole('button', { name: 'Page C' }))
    expect(await screen.findByRole('textbox', { name: 'Page title' })).toHaveValue('Page C')
    const pageContent = await screen.findByRole('list', { name: 'Page content' })
    expect(within(pageContent).getByRole('listitem')).toHaveClass('is-highlighted')
    expect(await within(screen.getByRole('complementary', { name: 'Related content' })).findByRole('button', { name: 'Page A' })).toBeInTheDocument()
  })

  it('opens a file result through its constrained download URL', async () => {
    const user = userEvent.setup()
    const openFile = vi.fn()
    vi.stubGlobal('open', openFile)
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{
        id: 'workspace-1', name: 'My Workspace',
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      }],
    })
    apiMocks.searchWorkspace.mockResolvedValue({
      context: '',
      sources: [{
        kind: 'file', title: 'Research notes.pdf', snippet: 'Local inference benchmarks',
        page_id: null, block_id: null, file_id: 'file-1', score: 0.8,
      }],
    })
    renderApp()

    await user.type(await screen.findByRole('searchbox', { name: 'Search workspace' }), 'benchmarks')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await user.click(await screen.findByRole('button', { name: /Research notes\.pdf/ }))

    expect(openFile).toHaveBeenCalledWith(
      '/api/files/file-1/download',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('removes stale active search results after deleting a file', async () => {
    const user = userEvent.setup()
    const file = {
      id: 'file-1',
      workspace_id: 'workspace-1',
      page_id: null,
      name: 'temporary.txt',
      mime_type: 'text/plain',
      size: 12,
      index_status: 'ready',
      index_error: null,
      content_searchable: true,
      indexed_at: '2026-01-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
    }
    apiMocks.listWorkspaces.mockResolvedValue({
      items: [{
        id: 'workspace-1', name: 'My Workspace',
        created_at: file.created_at, updated_at: file.created_at,
      }],
    })
    apiMocks.listFiles.mockResolvedValueOnce({ items: [file] }).mockResolvedValue({ items: [] })
    apiMocks.deleteFile.mockResolvedValue(undefined)
    apiMocks.searchWorkspace
      .mockResolvedValueOnce({
        context: '',
        sources: [{
          kind: 'file', title: file.name, snippet: 'temporary content',
          page_id: null, block_id: null, file_id: file.id, score: 0.8,
        }],
      })
      .mockResolvedValue({ context: '', sources: [] })
    renderApp()

    await user.type(await screen.findByRole('searchbox', { name: 'Search workspace' }), 'temporary')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByRole('button', { name: 'temporary.txt' })).toBeInTheDocument()
    const files = screen.getByRole('region', { name: 'Workspace files' })
    await user.click(await within(files).findByRole('button', { name: 'Delete temporary.txt' }))
    await user.click(await screen.findByRole('button', { name: 'Remove file' }))

    await waitFor(() => expect(apiMocks.searchWorkspace).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('No matching content found.')).toBeInTheDocument()
  })
})