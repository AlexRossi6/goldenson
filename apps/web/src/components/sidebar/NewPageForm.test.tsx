import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NewPageForm } from './NewPageForm'

describe('NewPageForm', () => {
  afterEach(cleanup)
  it('submits a non-empty title with Enter and ignores empty titles', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<NewPageForm pages={[]} title="" parentId={null} pending={false} onTitleChange={vi.fn()} onParentChange={vi.fn()} onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox', { name: 'New page title' })
    await user.click(input)
    await user.keyboard('{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()

    const onTitleChange = vi.fn()
    render(<NewPageForm pages={[]} title="Project notes" parentId={null} pending={false} onTitleChange={onTitleChange} onParentChange={vi.fn()} onSubmit={onSubmit} />)
    await user.click(screen.getAllByRole('textbox', { name: 'New page title' })[1])
    await user.keyboard('{Enter}')
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('disables submission while a page is being created', () => {
    render(<NewPageForm pages={[]} title="Project notes" parentId={null} pending onTitleChange={vi.fn()} onParentChange={vi.fn()} onSubmit={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Creating...' })).toBeDisabled()
  })
})