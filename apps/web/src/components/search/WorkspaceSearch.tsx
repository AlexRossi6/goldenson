import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { searchWorkspace } from '../../api/workspaces'
import type { RetrievedSource } from '../../types/api'
import { EvidenceResult } from '../ui/EvidenceResult'

type WorkspaceSearchProps = {
  workspaceId: string
  onOpenSource: (source: RetrievedSource) => void
}

function sourceLabel(source: RetrievedSource): string {
  if (source.kind === 'block') return 'In page'
  if (source.kind === 'file') return 'File'
  return 'Page'
}

export function WorkspaceSearch({ workspaceId, onOpenSource }: WorkspaceSearchProps) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const resultsQuery = useQuery({
    queryKey: ['workspace-search', workspaceId, query],
    queryFn: () => searchWorkspace(workspaceId, query),
    enabled: Boolean(query),
    retry: false,
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setQuery(draft.trim())
  }

  const clear = () => {
    setDraft('')
    setQuery('')
  }

  return (
    <section className="workspace-search" aria-label="Workspace search">
      <form className="search-form" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="workspace-search-input">Search workspace</label>
        <input
          id="workspace-search-input"
          type="search"
          placeholder="Search workspace"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" className="button button-secondary" disabled={!draft.trim()}>Search</button>
      </form>

      {query && (
        <div className="search-results">
          <div className="search-results-header">
            <p className="panel-label">Results</p>
            <button type="button" className="text-button" onClick={clear}>Clear</button>
          </div>
          {resultsQuery.isLoading && <p className="search-state" role="status">Searching your workspace...</p>}
          {resultsQuery.isError && (
            <div className="search-state" role="alert">
              <p>Search is unavailable right now.</p>
              <button type="button" className="text-button" onClick={() => void resultsQuery.refetch()}>Try again</button>
            </div>
          )}
          {resultsQuery.isSuccess && resultsQuery.data.sources.length === 0 && (
            <p className="search-state">No matching content found.</p>
          )}
          {resultsQuery.isSuccess && resultsQuery.data.sources.length > 0 && (
            <ul className="search-result-list">
              {resultsQuery.data.sources.map((source) => (
                <li key={`${source.kind}-${source.block_id ?? source.file_id ?? source.page_id}`}>
                  <EvidenceResult
                    label={sourceLabel(source)}
                    title={source.title}
                    preview={source.snippet}
                    onOpen={() => onOpenSource(source)}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}