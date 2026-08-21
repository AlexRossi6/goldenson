import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FileMetadata } from '../../types/api'
import { FileArea } from './FileArea'

const file: FileMetadata = {
  id: 'f1', workspace_id: 'w1', page_id: null, name: 'notes.md', mime_type: 'text/markdown', size: 2048,
  created_at: '2026-01-01T00:00:00.000000Z', updated_at: '2026-01-01T00:00:00.000000Z',
}

describe('FileArea', () => {
  afterEach(cleanup)
  it('renders file metadata and download action', () => {
    render(<FileArea files={[file]} loading={false} uploading={false} errorMessage={null} onUpload={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.getByRole('link', { name: 'notes.md' })).toHaveAttribute('href', '/api/files/f1/download')
    expect(screen.getByText('2 KB')).toBeInTheDocument()
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
})
