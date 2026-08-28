import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  it('shows loading state without empty-page or editing controls', () => {
    render(
      <BlockEditor
        blocks={[]}
        loading
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('Loading page content...')
    expect(screen.queryByText('A blank page is ready for your ideas.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Add block' })).not.toBeInTheDocument()
  })

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
    await user.click(screen.getByRole('option', { name: /Paragraph/ }))

    expect(onCreateBlock).toHaveBeenCalledWith({
      type: 'paragraph',
      position: 0,
      content: { text: '' },
    })
  })

  it('opens a searchable picker with the supported block types', async () => {
    const user = userEvent.setup()
    render(
      <BlockEditor
        blocks={[]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: '+ Add block' }))

    expect(screen.getByRole('dialog', { name: 'Add a block' })).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByRole('option', { name: /Paragraph/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /To-do/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Code/ })).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: 'Find a block' })).toHaveFocus()
  })

  it('filters block types immediately and shows an empty state for no matches', async () => {
    const user = userEvent.setup()
    render(
      <BlockEditor
        blocks={[]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: '+ Add block' }))
    const search = screen.getByRole('searchbox', { name: 'Find a block' })
    await user.type(search, 'task')
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByRole('option', { name: /To-do/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Paragraph/ })).not.toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'calendar')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(screen.getByText('No matching block types.')).toBeInTheDocument()
  })

  it('creates the selected block and closes the picker', async () => {
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
    await user.click(screen.getByRole('option', { name: /To-do/ }))

    expect(onCreateBlock).toHaveBeenCalledWith(expect.objectContaining({
      type: 'todo',
      position: 0,
      content: expect.objectContaining({ title: '', items: expect.any(Array) }),
    }))
    expect(screen.queryByRole('dialog', { name: 'Add a block' })).not.toBeInTheDocument()
  })

  it('dismisses the picker without creating a block', async () => {
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
    await user.keyboard('{Escape}')

    expect(onCreateBlock).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog', { name: 'Add a block' })).not.toBeInTheDocument()
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
    expect(screen.getByRole('textbox', { name: 'Paragraph content' })).toHaveTextContent('Hello')
    expect(screen.queryByText('Heading')).not.toBeInTheDocument()
    expect(screen.queryByText('Paragraph')).not.toBeInTheDocument()
    expect(screen.getByText('Review notes')).toBeInTheDocument()
    expect(screen.getByText('echo hello')).toBeInTheDocument()
  })

  it('keeps block controls contextual while preserving accessible actions', () => {
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph' })]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.queryByText('Paragraph')).not.toBeInTheDocument()
    const deleteAction = screen.getByRole('button', { name: 'Delete paragraph block' })
    expect(deleteAction).toHaveClass('block-delete')
    expect(deleteAction.parentElement).toHaveClass('block-context-actions')
  })

  it('reorders mixed blocks by their drag handle without changing block identity', async () => {
    const onReorderBlocks = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[
          makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', position: 0, content: { text: 'Paragraph' } }),
          makeBlock({ id: 'todo', page_id: 'p1', type: 'todo', position: 1, content: { title: 'Tasks', items: [] } }),
          makeBlock({ id: 'heading', page_id: 'p1', type: 'heading', position: 2, content: { text: 'Heading' } }),
        ]}
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
        onReorderBlocks={onReorderBlocks}
      />,
    )

    const handle = screen.getByRole('button', { name: 'Move todo block' })
    const listItems = screen.getAllByRole('listitem')
    fireEvent.dragStart(handle, { dataTransfer: { effectAllowed: '', setData: vi.fn() } })
    fireEvent.dragOver(listItems[0], { preventDefault: vi.fn() })
    fireEvent.drop(listItems[0], { preventDefault: vi.fn() })

    await waitFor(() => expect(onReorderBlocks).toHaveBeenCalledWith(
      ['todo', 'paragraph', 'heading'],
      { todo: 1, paragraph: 1, heading: 1 },
    ))
    expect(screen.getByRole('textbox', { name: 'Paragraph content' })).toHaveTextContent('Paragraph')
    expect(screen.getByRole('textbox', { name: 'Heading content' })).toHaveTextContent('Heading')

    fireEvent.dragStart(screen.getByRole('textbox', { name: 'Paragraph content' }), {
      dataTransfer: { effectAllowed: '', setData: vi.fn() },
    })
    expect(onReorderBlocks).toHaveBeenCalledTimes(1)
  })

  it('highlights the originating block selected from a source', () => {
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'source-block', page_id: 'p1', type: 'paragraph' })]}
        highlightedBlockId="source-block"
        onCreateBlock={vi.fn().mockResolvedValue(undefined)}
        onUpdateBlock={vi.fn().mockResolvedValue(undefined)}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByRole('listitem')).toHaveClass('is-highlighted')
    expect(screen.getByRole('listitem')).toHaveAttribute('data-block-id', 'source-block')
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
    const paragraphInput = screen.getByRole('textbox', { name: 'Paragraph content' })
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

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph content' })
    expect(paragraph).toBeEmptyDOMElement()
    expect(paragraph).toHaveAttribute('data-placeholder', 'Start writing...')
  })

  it('inserts a line break in the same paragraph with Shift+Enter', async () => {
    const user = userEvent.setup()
    const onCreateBlock = vi.fn().mockResolvedValue(makeBlock({ id: 'next', page_id: 'p1', type: 'paragraph', position: 1, content: { text: '' } }))
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', content: { text: 'FirstSecond' } })]}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph content' })
    await user.click(paragraph)
    const selection = window.getSelection()
    const range = document.createRange()
    range.setStart(paragraph.firstChild as Text, 5)
    range.collapse(true)
    selection?.removeAllRanges()
    selection?.addRange(range)
    fireEvent.keyDown(paragraph, { key: 'Enter', shiftKey: true })
    const caretRange = document.createRange()
    caretRange.selectNodeContents(paragraph)
    caretRange.setEnd(
      window.getSelection()?.anchorNode as Node,
      window.getSelection()?.anchorOffset ?? 0,
    )
    expect(caretRange.toString().length).toBe(6)
    fireEvent.blur(paragraph)

    expect(onUpdateBlock).toHaveBeenCalledWith('paragraph', {
      version: 1,
      content: { text: 'First\nSecond' },
    })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(paragraph.querySelector('br')).not.toBeNull()
    expect(onCreateBlock).not.toHaveBeenCalled()
  })

  it('finishes the paragraph and creates exactly one new block with Enter', async () => {
    const onCreateBlock = vi.fn().mockResolvedValue(makeBlock({ id: 'next', page_id: 'p1', type: 'paragraph', position: 1, content: { text: 'Second' } }))
    const onUpdateBlock = vi.fn().mockResolvedValue(undefined)
    render(
      <BlockEditor
        blocks={[makeBlock({ id: 'paragraph', page_id: 'p1', type: 'paragraph', content: { text: 'FirstSecond' } })]}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph content' })
    const range = document.createRange()
    range.setStart(paragraph.firstChild as Text, 5)
    range.collapse(true)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    fireEvent.keyDown(paragraph, { key: 'Enter' })

    await waitFor(() => expect(onCreateBlock).toHaveBeenCalledTimes(1))
    expect(onUpdateBlock).toHaveBeenCalledWith('paragraph', {
      version: 1,
      content: { text: 'First' },
    })
    expect(onCreateBlock).toHaveBeenCalledWith({
      type: 'paragraph',
      position: 1,
      content: { text: 'Second' },
    })
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

    const paragraph = screen.getByRole('textbox', { name: 'Paragraph content' })
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
      version: 2,
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
      version: 3,
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

  it('edits code directly on its rendered surface and retains it when saving conflicts', async () => {
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

    const codeInput = screen.getByRole('textbox', { name: 'Code content' })
    expect(codeInput.tagName).toBe('CODE')
    expect(codeInput).toHaveAttribute('contenteditable', 'true')
    expect(screen.queryByRole('button', { name: 'Edit code' })).not.toBeInTheDocument()
    await user.clear(codeInput)
    await user.type(codeInput, 'print(2)')
    await user.tab()

    expect(onUpdateBlock).toHaveBeenCalledWith('code', { version: 1, content: { language: 'python', code: 'print(2)' } })
    expect(screen.getByRole('textbox', { name: 'Code content' })).toBeInTheDocument()
  })
})
