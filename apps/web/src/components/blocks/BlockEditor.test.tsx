import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Block } from '../../types/api'
import { BlockEditor } from './BlockEditor'

const now = '2026-01-01T00:00:00.000000Z'

function makeBlock(input: Partial<Block> & Pick<Block, 'id' | 'page_id' | 'type'>): Block {
  return {
    id: input.id,
    page_id: input.page_id,
    type: input.type,
    position: input.position ?? 0,
    content: input.content ?? { text: 'Hello' },
    version: input.version ?? 1,
    created_at: input.created_at ?? now,
    updated_at: input.updated_at ?? now,
  }
}

describe('BlockEditor', () => {
  afterEach(cleanup)
  it('creates a first block when page is empty', async () => {
    const user = userEvent.setup()
    const onCreateBlock = vi.fn().mockResolvedValue(undefined)

    render(
      <BlockEditor
        blocks={[]}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: '+ Add block' }))
    await user.click(screen.getByRole('button', { name: 'Paragraph' }))

    expect(onCreateBlock).toHaveBeenCalledWith({
      type: 'paragraph',
      position: 0,
      content: { text: 'Start writing...' },
    })
  })

  it('renders existing blocks sorted by position', () => {
    render(
      <BlockEditor
        blocks={[
          makeBlock({ id: 'b2', page_id: 'p1', type: 'paragraph', position: 1 }),
          makeBlock({ id: 'b1', page_id: 'p1', type: 'heading', position: 0 }),
          makeBlock({ id: 'b3', page_id: 'p1', type: 'todo', position: 2, content: { text: 'Review notes', checked: false } }),
          makeBlock({ id: 'b4', page_id: 'p1', type: 'code', position: 3, content: { language: 'text', code: 'echo hello' } }),
        ]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Hello' })).toBeInTheDocument()
    expect(screen.getAllByText('Hello')).toHaveLength(2)
    expect(screen.getByText('Heading')).toBeInTheDocument()
    expect(screen.getByText('Paragraph')).toBeInTheDocument()
    expect(screen.getByText('Review notes')).toBeInTheDocument()
    expect(screen.getByText('echo hello')).toBeInTheDocument()
  })

  it('edits paragraph and heading text on click and saves on blur', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', content: { text: 'Draft' } }), makeBlock({ id: 'heading', page_id: 'p1', type: 'heading', position: 1, content: { text: 'Title' } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Edit paragraph' }))
    const paragraphInput = screen.getByRole('textbox', { name: 'paragraph content' })
    await user.clear(paragraphInput)
    await user.type(paragraphInput, 'Updated draft')
    await user.tab()

    await user.click(screen.getByRole('button', { name: 'Edit heading' }))
    const headingInput = screen.getByRole('textbox', { name: 'heading content' })
    await user.clear(headingInput)
    await user.type(headingInput, 'Updated title')
    await user.tab()

    expect(onUpdateBlock).toHaveBeenNthCalledWith(1, 'paragraph', { version: 1, content: { text: 'Updated draft' } })
    expect(onUpdateBlock).toHaveBeenNthCalledWith(2, 'heading', { version: 1, content: { text: 'Updated title' } })
  })

  it('edits todo text, toggles its checkbox, and saves both changes', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'todo', page_id: 'p1', type: 'todo', content: { text: 'Buy groceries', checked: false } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Edit todo' }))
    const todoInput = screen.getByRole('textbox', { name: 'To-do text' })
    await user.clear(todoInput)
    await user.type(todoInput, 'Buy tea')
    await user.tab()
    await user.click(screen.getByRole('checkbox', { name: 'Mark Buy groceries complete' }))

    expect(onUpdateBlock).toHaveBeenCalledWith('todo', { version: 1, content: { text: 'Buy tea', checked: false } })
    expect(onUpdateBlock).toHaveBeenLastCalledWith('todo', { version: 1, content: { text: 'Buy tea', checked: true } })
  })

  it('edits code and retains the editing state when saving conflicts', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockRejectedValue(new Error('CONCURRENCY_CONFLICT'))
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'code', page_id: 'p1', type: 'code', content: { language: 'python', code: 'print(1)' } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Edit code' }))
    const codeInput = screen.getByRole('textbox', { name: 'Code content' })
    await user.clear(codeInput)
    await user.type(codeInput, 'print(2)')
    await user.tab()

    expect(onUpdateBlock).toHaveBeenCalledWith('code', { version: 1, content: { language: 'python', code: 'print(2)' } })
    expect(screen.getByRole('textbox', { name: 'Code content' })).toBeInTheDocument()
  })
})
