import { cleanup, render, screen, waitFor } from '@testing-library/react'
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
      content: { text: '' },
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

    expect(screen.getByRole('textbox', { name: 'Heading content' })).toHaveTextContent('Hello')
    expect(screen.getByRole('textbox', { name: 'Paragraph line 1' })).toHaveTextContent('Hello')
    expect(screen.getByText('Heading')).toBeInTheDocument()
    expect(screen.getByText('Paragraph')).toBeInTheDocument()
    expect(screen.getByText('Review notes')).toBeInTheDocument()
    expect(screen.getByText('echo hello')).toBeInTheDocument()
  })

  it('edits paragraph and heading text directly in rendered content and persists on blur', async () => {
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

    expect(screen.queryByRole('button', { name: 'Edit paragraph' })).not.toBeInTheDocument()
    const paragraphInput = screen.getByRole('textbox', { name: 'Paragraph line 1' })
    await user.click(paragraphInput)
    await user.clear(paragraphInput)
    await user.type(paragraphInput, 'Updated draft')
    await user.tab()

    const headingInput = screen.getByRole('textbox', { name: 'Heading content' })
    expect(headingInput).toHaveClass('markdown-level-2')
    await user.click(headingInput)
    await user.clear(headingInput)
    await user.type(headingInput, 'Updated title')
    await user.tab()

    expect(onUpdateBlock).toHaveBeenNthCalledWith(1, 'paragraph', { version: 1, content: { text: 'Updated draft' } })
    expect(onUpdateBlock).toHaveBeenNthCalledWith(2, 'heading', { version: 1, content: { text: 'Updated title' } })
  })

  it('renders a true paragraph placeholder without storing it as content', () => {
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', content: { text: '' } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph line 1' })
    expect(paragraph).toBeEmptyDOMElement()
    expect(paragraph).toHaveAttribute('data-placeholder', 'Start writing...')
  })

  it('renders Markdown headings live on the same editable surface and persists the source syntax', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', content: { text: '' } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph line 1' })
    await user.click(paragraph)
    await user.type(paragraph, '## Test')

    await waitFor(() => {
      expect(paragraph).toHaveClass('markdown-level-2')
    })
    expect(paragraph).toHaveTextContent('Test')
    expect(screen.queryByText('## Test')).not.toBeInTheDocument()

    await user.tab()
    expect(onUpdateBlock).toHaveBeenCalledWith('paragraph', { version: 1, content: { text: '## Test' } })
  })

  it('edits todo titles and items inline and persists their values', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'todo', page_id: 'p1', type: 'todo', content: { title: '', items: [{ id: 'item1', text: '', completed: false }] } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const title = screen.getByRole('textbox', { name: 'Todo title' })
    const item = screen.getByRole('textbox', { name: 'Todo item 1' })
    expect(title).toBeEmptyDOMElement()
    expect(title).toHaveAttribute('data-placeholder', 'Task list title...')
    expect(item).toBeEmptyDOMElement()
    expect(item).toHaveAttribute('data-placeholder', 'What needs to be done?')

    await user.click(title)
    await user.type(title, 'Research local AI')
    await user.click(item)
    await user.type(item, 'Compare Ollama')
    await user.tab()

    expect(title).toHaveTextContent('Research local AI')
    expect(item).toHaveTextContent('Compare Ollama')
    expect(onUpdateBlock).toHaveBeenLastCalledWith('todo', {
      version: 1,
      content: { title: 'Research local AI', items: [{ id: 'item1', text: 'Compare Ollama', completed: false }] },
    })
  })

  it('creates and focuses another todo item with Enter', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'todo', page_id: 'p1', type: 'todo', content: { title: 'Research', items: [{ id: 'item1', text: 'Compare Ollama', completed: false }] } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const firstItem = screen.getByRole('textbox', { name: 'Todo item 1' })
    await user.click(firstItem)
    await user.keyboard('{End}{Enter}')

    const secondItem = await screen.findByRole('textbox', { name: 'Todo item 2' })
    await waitFor(() => expect(secondItem).toHaveFocus())
    await user.type(secondItem, 'Compare llama.cpp')
    await user.tab()

    expect(secondItem).toHaveTextContent('Compare llama.cpp')
    expect(onUpdateBlock).toHaveBeenLastCalledWith('todo', {
      version: 1,
      content: {
        title: 'Research',
        items: [
          { id: 'item1', text: 'Compare Ollama', completed: false },
          expect.objectContaining({ text: 'Compare llama.cpp', completed: false }),
        ],
      },
    })
  })

  it('removes an empty todo item with Backspace and focuses the previous item', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({
          id: 'todo',
          page_id: 'p1',
          type: 'todo',
          content: {
            title: 'Research',
            items: [
              { id: 'item1', text: 'Compare Ollama', completed: false },
              { id: 'item2', text: '', completed: false },
            ],
          },
        })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const firstItem = screen.getByRole('textbox', { name: 'Todo item 1' })
    const emptyItem = screen.getByRole('textbox', { name: 'Todo item 2' })
    await user.click(emptyItem)
    await user.keyboard('{Backspace}')

    expect(screen.queryByRole('textbox', { name: 'Todo item 2' })).not.toBeInTheDocument()
    await waitFor(() => expect(firstItem).toHaveFocus())
    expect(onUpdateBlock).toHaveBeenCalledWith('todo', {
      version: 1,
      content: { title: 'Research', items: [{ id: 'item1', text: 'Compare Ollama', completed: false }] },
    })
  })

  it('toggles a todo checkbox without changing editing surfaces', async () => {
    const user = userEvent.setup()
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'todo', page_id: 'p1', type: 'todo', content: { title: 'Research', items: [{ id: 'item1', text: 'Test embeddings', completed: false }] } })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const checkbox = screen.getByRole('checkbox', { name: 'Mark Test embeddings complete' })
    const item = screen.getByRole('textbox', { name: 'Todo item 1' })
    await user.click(checkbox)

    expect(checkbox).toBeChecked()
    expect(item).toHaveClass('is-completed')
    expect(screen.getByRole('textbox', { name: 'Todo title' })).toBeInTheDocument()
    expect(onUpdateBlock).toHaveBeenCalledWith('todo', {
      version: 1,
      content: { title: 'Research', items: [{ id: 'item1', text: 'Test embeddings', completed: true }] },
    })
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
