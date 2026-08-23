import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { RetrievedSource } from '../../types/api'
import { WorkspaceSearch } from './WorkspaceSearch'

const apiMocks = vi.hoisted(() => ({ searchWorkspace: vi.fn() }))

vi.mock('../../api/workspaces', () => ({ searchWorkspace: apiMocks.searchWorkspace }))

function renderSearch(onOpenSource = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceSearch workspaceId="workspace-1" onOpenSource={onOpenSource} />
    </QueryClientProvider>,
  )
  return onOpenSource
}

async function submitSearch(query: string) {
  const user = userEvent.setup()
  await user.type(screen.getByRole('searchbox', { name: 'Search workspace' }), query)
  await user.click(screen.getByRole('button', { name: 'Search' }))
  return user
}

describe('WorkspaceSearch', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows hybrid results without technical metadata and opens block provenance', async () => {
    const blockSource: RetrievedSource = {
      kind: 'block',
      title: 'Local AI',
      snippet: 'Compare Ollama with llama.cpp for local inference.',
      page_id: 'page-1',
      block_id: 'block-1',
      file_id: null,
      score: 0.91,
    }
    apiMocks.searchWorkspace.mockResolvedValue({
      context: 'internal context',
      sources: [
        blockSource,
        { ...blockSource, kind: 'page', title: 'Runtime notes', snippet: 'Runtime configuration notes.', page_id: 'page-2', block_id: null },
      ],
    })
    const onOpenSource = renderSearch()
    const user = await submitSearch('How does local inference work?')

    expect(await screen.findByText('Compare Ollama with llama.cpp for local inference.')).toBeInTheDocument()
    expect(screen.getByText('In page')).toBeInTheDocument()
    expect(screen.getByText('Page')).toBeInTheDocument()
    expect(screen.queryByText(/0\.91|internal context|block-1/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Local AI/ }))
    expect(onOpenSource).toHaveBeenCalledWith(blockSource)
  })

  it('resolves empty results clearly', async () => {
    apiMocks.searchWorkspace.mockResolvedValue({ context: '', sources: [] })
    renderSearch()
    await submitSearch('missing topic')

    expect(await screen.findByText('No matching content found.')).toBeInTheDocument()
  })

  it('shows an error with a working retry action', async () => {
    apiMocks.searchWorkspace
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ context: '', sources: [] })
    renderSearch()
    const user = await submitSearch('notes')

    expect(await screen.findByRole('alert')).toHaveTextContent('Search is unavailable right now.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(apiMocks.searchWorkspace).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('No matching content found.')).toBeInTheDocument()
  })
})