import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Page } from '../../types/api'
import { MovePageDialog } from './MovePageDialog'

const now = '2026-01-01T00:00:00.000000Z'
const page = (id: string, title: string, parent_page_id: string | null = null): Page => ({ id, title, parent_page_id, workspace_id: 'w1', position: 0, version: 1, created_at: now, updated_at: now })

describe('MovePageDialog', () => {
  it('moves to a friendly destination and position', async () => {
    const user = userEvent.setup()
    const onMove = vi.fn().mockResolvedValue(undefined)
    render(<MovePageDialog page={page('p1', 'Notes')} pages={[page('p1', 'Notes'), page('p2', 'Projects')]} open onCancel={vi.fn()} onMove={onMove} />)

    await user.selectOptions(screen.getByLabelText('Move to'), 'p2')
    await user.clear(screen.getByLabelText('Place it at'))
    await user.type(screen.getByLabelText('Place it at'), '2')
    await user.click(screen.getByRole('button', { name: 'Move page' }))

    expect(onMove).toHaveBeenCalledWith('p2', 1)
  })
})
