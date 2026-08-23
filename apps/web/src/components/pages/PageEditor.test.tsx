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

  it('renders and navigates related pages', async () => {
    const user = userEvent.setup()
    const onSelectPage = vi.fn()
    render(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} relatedPages={[{ page_id: 'p2', title: 'Local AI', reason: 'Similar topic' }]} onSelectPage={onSelectPage} onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Local AI' }))
    expect(onSelectPage).toHaveBeenCalledWith('p2')
    expect(screen.getByText('Similar topic')).toBeInTheDocument()
  })

  it('shows a retry action for stale knowledge', () => {
    const onRetryKnowledge = vi.fn()
    render(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} knowledge={{ status: 'stale', concepts: [] }} onRetryKnowledge={onRetryKnowledge} onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)

    expect(screen.getByText('Retry analysis')).toBeInTheDocument()
  })

  it.each([
    ['pending', 'Indexing...'],
    ['indexing', 'Indexing...'],
    ['ready', 'Ready'],
    ['failed', 'Retry analysis'],
  ] as const)('shows the %s knowledge state', (status, label) => {
    render(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} knowledge={{ status, concepts: [] }} onRetryKnowledge={vi.fn()} onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)

    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('shows related loading, error, and empty states', () => {
    const { rerender } = render(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} relatedLoading onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)
    expect(screen.getByText('Finding related pages...')).toBeInTheDocument()

    rerender(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} relatedError onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)
    expect(screen.getByText('Related pages unavailable')).toBeInTheDocument()

    rerender(<PageEditor page={page} blocks={[]} attachments={[]} attachmentsLoading={false} attachmentsUploading={false} attachmentsError={null} busy={false} errorMessage={null} knowledge={{ status: 'ready', concepts: [] }} onUpdatePage={vi.fn().mockResolvedValue(undefined)} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} onUploadAttachment={vi.fn().mockResolvedValue(undefined)} onDeleteAttachment={vi.fn()} />)
    expect(screen.getByText('No related pages yet.')).toBeInTheDocument()
  })
})
