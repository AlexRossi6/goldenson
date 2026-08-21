import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Page } from '../../types/api'
import { PageTree } from './PageTree'

const now = '2026-01-01T00:00:00.000000Z'

function makePage(input: Partial<Page> & Pick<Page, 'id' | 'workspace_id' | 'title'>): Page {
  return {
    id: input.id,
    workspace_id: input.workspace_id,
    parent_page_id: input.parent_page_id ?? null,
    title: input.title,
    position: input.position ?? 0,
    version: input.version ?? 1,
    created_at: input.created_at ?? now,
    updated_at: input.updated_at ?? now,
  }
}

describe('PageTree', () => {
  it('renders pages and selects one via callback', async () => {
    const user = userEvent.setup()
    const onSelectPage = vi.fn()

    render(
      <PageTree
        pages={[
          makePage({ id: 'p1', workspace_id: 'w1', title: 'Root' }),
          makePage({ id: 'p2', workspace_id: 'w1', title: 'Child', parent_page_id: 'p1' }),
        ]}
        selectedPageId={null}
        expandedPages={{ p1: true }}
        onToggleExpand={vi.fn()}
        onSelectPage={onSelectPage}
        onCreateChild={vi.fn()}
        onDeletePage={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Child' }))
    expect(onSelectPage).toHaveBeenCalledWith('p2')
  })

  it('shows empty state action when no pages exist', async () => {
    const user = userEvent.setup()
    const onCreateChild = vi.fn()

    render(
      <PageTree
        pages={[]}
        selectedPageId={null}
        expandedPages={{}}
        onToggleExpand={vi.fn()}
        onSelectPage={vi.fn()}
        onCreateChild={onCreateChild}
        onDeletePage={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Create first page' }))
    expect(onCreateChild).toHaveBeenCalledWith(null)
  })
})
