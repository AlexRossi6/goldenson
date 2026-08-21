import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('cancels with Escape and confirms with the destructive action', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onConfirm = vi.fn()

    render(<ConfirmDialog open title="Delete page?" message="This cannot be undone." confirmLabel="Delete page" onCancel={onCancel} onConfirm={onConfirm} />)

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Delete page' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
