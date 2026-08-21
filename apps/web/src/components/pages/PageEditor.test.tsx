import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Page } from '../../types/api'
import { PageEditor } from './PageEditor'

const page: Page = {
  id: 'p1', workspace_id: 'w1', parent_page_id: null, title: 'Notes', position: 0, version: 1,
  created_at: '2026-01-01T00:00:00.000000Z', updated_at: '2026-01-01T00:00:00.000000Z',
}

describe('PageEditor', () => {
  it('saves a changed title when the title leaves focus', async () => {
    const user = userEvent.setup()
    const onUpdatePage = vi.fn().mockResolvedValue(undefined)
    render(<PageEditor page={page} blocks={[]} busy={false} errorMessage={null} onUpdatePage={onUpdatePage} onCreateBlock={vi.fn().mockResolvedValue(undefined)} onUpdateBlock={vi.fn().mockResolvedValue(undefined)} onDeleteBlock={vi.fn()} onRequestMove={vi.fn()} onRequestDelete={vi.fn()} />)

    const title = screen.getByRole('textbox', { name: 'Page title' })
    await user.clear(title)
    await user.type(title, 'Daily notes')
    await user.tab()

    expect(onUpdatePage).toHaveBeenCalledWith('p1', { title: 'Daily notes', version: 1 })
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })
})
