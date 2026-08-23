import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceIndexHealth } from '../../types/api'
import { IndexHealth } from './IndexHealth'

const readyHealth: WorkspaceIndexHealth = {
  status: 'ready',
  pages: { total: 2, ready: 2, indexing: 0, stale: 0, failed: 0 },
  files: { total: 2, ready: 1, indexing: 0, stale: 0, failed: 0, metadata_only: 1 },
}

describe('IndexHealth', () => {
  afterEach(cleanup)

  it('keeps page readiness separate from file content searchability', () => {
    render(<IndexHealth health={readyHealth} loading={false} retrying={false} onRetryFailed={vi.fn()} />)

    expect(screen.getByText('Page search: 2 pages ready')).toBeInTheDocument()
    expect(screen.getByText(/1 file content-searchable/)).toBeInTheDocument()
    expect(screen.getByText(/1 file stored; contents not searchable/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry failed indexing' })).not.toBeInTheDocument()
  })

  it('resolves terminal failure into a retry action', async () => {
    const user = userEvent.setup()
    const onRetryFailed = vi.fn()
    const failedHealth: WorkspaceIndexHealth = {
      ...readyHealth,
      status: 'failed',
      pages: { ...readyHealth.pages, ready: 1, failed: 1 },
    }
    render(<IndexHealth health={failedHealth} loading={false} retrying={false} onRetryFailed={onRetryFailed} />)

    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry failed indexing' }))
    expect(onRetryFailed).toHaveBeenCalledOnce()
  })

  it('shows active work without an indefinite generic loader', () => {
    const indexing: WorkspaceIndexHealth = {
      ...readyHealth,
      status: 'indexing',
      pages: { ...readyHealth.pages, ready: 1, indexing: 1 },
    }
    render(<IndexHealth health={indexing} loading={false} retrying={false} onRetryFailed={vi.fn()} />)

    expect(screen.getByText('Preparing')).toBeInTheDocument()
    expect(screen.getByText('Page search: 1 page preparing')).toBeInTheDocument()
  })
})
