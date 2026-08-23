import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FileMetadata } from '../../types/api'
import { FileArea } from './FileArea'

const file: FileMetadata = {
  id: 'f1', workspace_id: 'w1', page_id: null, name: 'notes.md', mime_type: 'text/markdown', size: 2048,
  index_status: 'ready', content_searchable: true, indexed_at: '2026-01-01T00:00:00.000000Z',
  created_at: '2026-01-01T00:00:00.000000Z', updated_at: '2026-01-01T00:00:00.000000Z',
}

describe('FileArea', () => {
  afterEach(cleanup)
  it('renders file metadata and download action', () => {
    render(<FileArea files={[file]} loading={false} uploading={false} errorMessage={null} onUpload={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.getByRole('link', { name: 'notes.md' })).toHaveAttribute('href', '/api/files/f1/download')
    expect(screen.getByText('2 KB')).toBeInTheDocument()
    expect(screen.getByText('Contents searchable')).toBeInTheDocument()
  })

  it('uploads a selected file and requests deletion through a callback', async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const onDelete = vi.fn()
    render(<FileArea files={[file]} loading={false} uploading={false} errorMessage={null} onUpload={onUpload} onDelete={onDelete} />)

    const input = document.querySelector('input[type="file"]')
    expect(input).not.toBeNull()
    await user.upload(input as HTMLInputElement, new File(['hello'], 'hello.txt', { type: 'text/plain' }))
    await user.click(screen.getByRole('button', { name: 'Delete notes.md' }))

    expect(onUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'hello.txt', type: 'text/plain' }))
    expect(onDelete).toHaveBeenCalledWith(file)
  })

  it('shows loading and empty states', () => {
    const { rerender } = render(<FileArea files={[]} loading={true} uploading={false} errorMessage={null} onUpload={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('Loading files...')).toBeInTheDocument()
    rerender(<FileArea files={[]} loading={false} uploading={false} errorMessage={null} onUpload={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('No files yet.')).toBeInTheDocument()
  })

  it('distinguishes stored-only files from recoverable failures', async () => {
    const user = userEvent.setup()
    const onRetryIndex = vi.fn()
    const pdf = { ...file, id: 'pdf', name: 'reference.pdf', mime_type: 'application/pdf', index_status: 'metadata_only' as const, content_searchable: false, indexed_at: null }
    const failed = { ...file, id: 'failed', name: 'broken.txt', index_status: 'failed' as const, content_searchable: false, indexed_at: null }
    render(<FileArea files={[pdf, failed]} loading={false} uploading={false} errorMessage={null} onDelete={vi.fn()} onRetryIndex={onRetryIndex} />)

    expect(screen.getByText('Stored · contents not yet searchable')).toBeInTheDocument()
    expect(screen.getByText('Contents not searchable')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetryIndex).toHaveBeenCalledWith(failed)
  })
})
