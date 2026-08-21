import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Page } from '../../types/api'
import { PageEditor } from './PageEditor'

const page: Page = {
  id: 'p1', workspace_id: 'w1', parent_page_id: null, title: 'Notes', position: 0, version: 1,
  created_at: '2026-01-01T00:00:00.000000Z', updated_at: '2026-01-01T00:00:00.000000Z',
}

describe('PageEditor', () => {
  afterEach(cleanup)
  it('saves a changed title when the title leaves focus', async () => {
    const user = userEvent.setup()
    const onUpdatePage = vi.fn().mockResolvedValue(undefined)
    render(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} onUpdatePage={onUpdatePage} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)

    const title = screen.getByRole('textbox', { name: 'Page title' })
    await user.clear(title)
    await user.type(title, 'Daily notes')
    await user.tab()

    expect(onUpdatePage).toHaveBeenCalledWith('p1', { title: 'Daily notes', version: 1 })
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('renders page attachments with an in-document add-file action', async () => {
    const user = userEvent.setup()
    const onUploadAttachment = vi.fn().mockResolvedValue(undefined)
    render(<PageEditor page={page} blocks={[]} attachments={[{ id: 'f1', workspace_id: 'w1', page_id: 'p1', name: 'architecture.md', mime_type: 'text/markdown', size: 1024, created_at: page.created_at, updated_at: page.updated_at }]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={onUploadAttachment} onDeleteAttachment={vi.fn()} />)

    expect(screen.getByRole('region', { name: 'Page editor' })).toBeInTheDocument()
    expect(screen.getByText('Attachments')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'architecture.md' })).toHaveAttribute('href', '/api/files/f1/download')
    await user.click(screen.getByRole('button', { name: 'Add file' }))
    expect(screen.getByLabelText('Add file')).toBeInTheDocument()
  })
})
