import { useMemo, useState, type KeyboardEvent } from 'react'

import type { Block } from '../../types/api'
import { InlineEditableBlock } from './InlineEditableBlock'

type BlockPayload = {
  version: number
  type?: string
  position?: number
  content?: Record<string, unknown>
}

type BlockEditorProps = {
  blocks: Block[]
  onCreateBlock: (payload: { type: string; position: number; content: Record<string, unknown> }) => Promise<void>
  onUpdateBlock: (blockId: string, payload: BlockPayload) => Promise<void>
  onDeleteBlock: (block: Block) => Promise<void>
}

type BlockRowProps = Omit<BlockEditorProps, 'blocks' | 'onCreateBlock'> & { block: Block }

function getText(block: Block): string {
  return typeof block.content.text === 'string' ? block.content.text : ''
}

function getHeadingLevel(text: string): number {
  const match = text.match(/^(#{1,3})\s+/)
  if (!match) return 0
  return match[1].length
}

function getHeadingContent(text: string): string {
  return text.replace(/^#{1,3}\s+/, '')
}

function renderHeading(text: string, level: number): React.ReactNode {
  const content = getHeadingContent(text)
  const isEmpty = !content.trim()
  if (level === 1) return <h2 style={{ fontSize: '1.8rem', marginBottom: '0.5rem' }}>{isEmpty ? 'Untitled heading' : content}</h2>
  if (level === 2) return <h3 style={{ fontSize: '1.4rem', marginBottom: '0.35rem' }}>{isEmpty ? 'Untitled heading' : content}</h3>
  if (level === 3) return <h4 style={{ fontSize: '1.1rem', marginBottom: '0.3rem' }}>{isEmpty ? 'Untitled heading' : content}</h4>
  return <h4>{isEmpty ? 'Untitled heading' : content}</h4>
}

function renderParagraphWithMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  return lines.map((line, idx) => {
    const level = getHeadingLevel(line)
    if (level > 0) {
      return (
        <div key={idx}>
          {renderHeading(line, level)}
        </div>
      )
    }
    return (
      <div key={idx}>
        <p style={{ margin: '0.3rem 0' }}>{line || '\u00a0'}</p>
      </div>
    )
  })
}

type TodoItem = { id: string; text: string; completed: boolean }
type TodoContent = {
  title?: string
  items?: TodoItem[]
  text?: string
  checked?: boolean
}

function normalizeTodoContent(content: Record<string, unknown>): TodoContent {
  if (Array.isArray(content.items)) {
    return { title: content.title as string | undefined, items: content.items as TodoItem[] }
  }
  // Legacy format: convert to new format
  return { items: [{ id: 'legacy', text: content.text as string || '', completed: content.checked === true }] }
}

function generateId(): string {
  return `item-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function BlockRow({ block, onUpdateBlock, onDeleteBlock }: BlockRowProps) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(getText(block) || '')
  const [code, setCode] = useState(typeof block.content.code === 'string' ? block.content.code : '')
  const [todoContent, setTodoContent] = useState<TodoContent>(() => normalizeTodoContent(block.content))
  const [busy, setBusy] = useState(false)

  const save = async (content: Record<string, unknown>) => {
    if (JSON.stringify(content) === JSON.stringify(block.content)) {
      setEditing(false)
      return
    }
    setBusy(true)
    try {
      await onUpdateBlock(block.id, { version: block.version, content })
      setEditing(false)
    } finally {
      setBusy(false)
    }
  }

  const cancelEditing = () => {
    setText(getText(block))
    setCode(typeof block.content.code === 'string' ? block.content.code : '')
    setTodoContent(normalizeTodoContent(block.content))
    setEditing(false)
  }

  const startEditing = () => {
    if (!busy) setEditing(true)
  }

  const persist = (content: Record<string, unknown>) => {
    void save(content).catch(() => undefined)
  }

  const handleTextKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
    // For single-line inputs (todo), prevent default Enter
    // For textarea (paragraph), allow Enter to create new lines
    if (event.key === 'Enter' && !(event.currentTarget instanceof HTMLTextAreaElement)) {
      event.preventDefault()
      event.currentTarget.blur()
    }
  }

  const handleCodeKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
  }

  const handleTodoItemKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      // Add a new item
      const newItem: TodoItem = { id: generateId(), text: '', completed: false }
      const newItems = [...(todoContent.items || [])]
      newItems.splice(index + 1, 0, newItem)
      const updatedContent = { ...todoContent, items: newItems }
      setTodoContent(updatedContent)
      // Persist immediately
      persist({
        title: updatedContent.title,
        items: updatedContent.items
      })
      // Schedule focus on next item
      setTimeout(() => {
        const inputs = document.querySelectorAll('[data-todo-item]')
        if (inputs[index + 1]) {
          (inputs[index + 1] as HTMLInputElement).focus()
        }
      }, 0)
    }
    if (event.key === 'Backspace') {
      // If the item is empty and there are other items, remove this one
      const currentItem = todoContent.items?.[index]
      if (currentItem?.text === '' && (todoContent.items?.length ?? 0) > 1) {
        event.preventDefault()
        const newItems = (todoContent.items || []).filter((_, i) => i !== index)
        const updatedContent = { ...todoContent, items: newItems }
        setTodoContent(updatedContent)
        persist({
          title: updatedContent.title,
          items: updatedContent.items
        })
      }
    }
  }

  const updateTodoItem = (itemId: string, text: string) => {
    const newItems = (todoContent.items || []).map(item => item.id === itemId ? { ...item, text } : item)
    setTodoContent({ ...todoContent, items: newItems })
  }

  const toggleTodoItem = (itemId: string) => {
    const newItems = (todoContent.items || []).map(item => item.id === itemId ? { ...item, completed: !item.completed } : item)
    setTodoContent({ ...todoContent, items: newItems })
  }

  const removeTodoItem = (itemId: string) => {
    const newItems = (todoContent.items || []).filter(item => item.id !== itemId)
    setTodoContent({ ...todoContent, items: newItems })
  }

  const saveTodoContent = () => {
    const content: Record<string, unknown> = {
      title: todoContent.title,
      items: todoContent.items
    }
    persist(content)
  }

  const displayText = block.type === 'heading' ? <h4>{getText(block) || 'Untitled heading'}</h4> : block.type === 'paragraph' ? (() => {
    const level = getHeadingLevel(getText(block))
    if (level > 0) return renderHeading(getText(block), level)
    const content = getText(block)
    return <p>{content || 'Empty paragraph'}</p>
  })() : <p>{getText(block) || 'Empty paragraph'}</p>

  return (
    <li className={`block-card ${editing ? 'is-editing' : ''}`}>
      <div className="block-meta">
        <span>{block.type === 'todo' ? 'Task' : block.type === 'code' ? 'Code' : block.type === 'heading' ? 'Heading' : 'Paragraph'}</span>
        <button type="button" className="text-button danger-link" onClick={() => void onDeleteBlock(block)} disabled={busy}>Delete</button>
      </div>
      <div className="block-content">
        {block.type === 'todo' ? (
          <div className="todo-block" onClick={() => !editing && !busy && startEditing()}>
            {editing ? (
              <>
                <div style={{ marginBottom: '0.6rem' }}>
                  <input
                    className="block-edit-input"
                    aria-label="Todo title"
                    placeholder="Task list title..."
                    value={todoContent.title || ''}
                    onChange={(event) => setTodoContent({ ...todoContent, title: event.target.value })}
                    onBlur={saveTodoContent}
                    onClick={(e) => e.stopPropagation()}
                    style={{ marginBottom: '0.5rem', fontWeight: 'bold' }}
                    autoFocus={!todoContent.title ? true : undefined}
                  />
                </div>
                {(todoContent.items || []).map((item, index) => (
                  <div key={item.id} className="todo-row">
                    <input
                      type="checkbox"
                      aria-label={`Mark ${item.text || 'task'} complete`}
                      checked={item.completed}
                      disabled={busy}
                      onChange={() => {
                        toggleTodoItem(item.id)
                        saveTodoContent()
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <input
                      className="block-edit-input"
                      aria-label={`Todo item ${index + 1}`}
                      placeholder="What needs to be done?"
                      value={item.text}
                      onChange={(event) => updateTodoItem(item.id, event.target.value)}
                      onBlur={saveTodoContent}
                      onKeyDown={(event) => handleTodoItemKeyDown(event, index)}
                      onClick={(e) => e.stopPropagation()}
                      data-todo-item="true"
                      style={{ flex: 1 }}
                      autoFocus={index === 0 && !!todoContent.title}
                    />
                    {item.text === '' && (todoContent.items?.length ?? 0) > 1 && (
                      <button
                        type="button"
                        className="text-button danger-link"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeTodoItem(item.id)
                          saveTodoContent()
                        }}
                        disabled={busy}
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </>
            ) : (
              <div style={{ width: '100%', textAlign: 'left' }}>
                {todoContent.title && <div style={{ fontWeight: 'bold', marginBottom: '0.35rem' }}>{todoContent.title}</div>}
                <div style={{ display: 'grid', gap: '0.3rem' }}>
                  {(todoContent.items || []).map((item) => (
                    <div key={item.id} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="checkbox"
                        checked={item.completed}
                        onChange={(e) => {
                          e.stopPropagation()
                          startEditing()
                          toggleTodoItem(item.id)
                          saveTodoContent()
                        }}
                      />
                      <span style={{ flex: 1, textDecoration: item.completed ? 'line-through' : 'none' }}>{item.text || 'Empty task'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : editing ? (
          block.type === 'code' ? (
            <textarea
              className="block-edit-input code-editor"
              aria-label="Code content"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              onBlur={() => persist({ ...block.content, code })}
              onKeyDown={handleCodeKeyDown}
              autoFocus
            />
          ) : block.type === 'paragraph' ? (
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              <div className="markdown-preview" style={{ minHeight: '60px', padding: '0.35rem', borderRadius: '2px', backgroundColor: 'rgba(0,0,0,0.02)', lineHeight: 1.5 }}>
                {renderParagraphWithMarkdown(text)}
              </div>
              <textarea
                className="block-edit-input"
                aria-label="paragraph content"
                placeholder="Start writing... (or use # for headings)"
                value={text}
                onChange={(event) => setText(event.target.value)}
                onBlur={() => persist({ ...block.content, text })}
                onKeyDown={handleTextKeyDown}
                autoFocus
                style={{ minHeight: '60px', resize: 'vertical', fontFamily: 'monospace', fontSize: '0.95rem' }}
              />
            </div>
          ) : (
            <input
              className="block-edit-input"
              aria-label={`${block.type} content`}
              placeholder="Enter text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onBlur={() => persist({ ...block.content, text })}
              onKeyDown={handleTextKeyDown}
              autoFocus
            />
          )
        ) : (
          <button type="button" className="block-display" onClick={startEditing} aria-label={`Edit ${block.type}`}>
            {block.type === 'code' ? <pre>{typeof block.content.code === 'string' ? block.content.code : ''}</pre> : displayText}
          </button>
        )}
      </div>
    </li>
  )
}

export function BlockEditor({ blocks, onCreateBlock, onUpdateBlock, onDeleteBlock }: BlockEditorProps) {
  const sortedBlocks = useMemo(() => [...blocks].sort((a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at)), [blocks])
  const [creating, setCreating] = useState(false)

  const addBlock = async (type: string) => {
    const content = type === 'todo' ? { title: '', items: [{ id: generateId(), text: '', completed: false }] } : type === 'code' ? { language: 'text', code: '' } : { text: '' }
    await onCreateBlock({ type, position: sortedBlocks.length, content })
    setCreating(false)
  }

  return (
    <section>
      <div className="new-block-card">
        <div className="block-type-picker">
          <button type="button" className="button button-primary" onClick={() => setCreating(!creating)}>{creating ? 'Close' : '+ Add block'}</button>
          {creating && <>
            <button type="button" className="button button-secondary" onClick={() => void addBlock('paragraph')}>Paragraph</button>
            <button type="button" className="button button-secondary" onClick={() => void addBlock('todo')}>To-do</button>
            <button type="button" className="button button-secondary" onClick={() => void addBlock('code')}>Code</button>
          </>}
        </div>
      </div>
      {sortedBlocks.length === 0 ? <p className="empty-copy">A blank page is ready for your ideas.</p> : <ul className="block-list" aria-label="Page content">
        {sortedBlocks.map((block) => block.type === 'code' ? (
          <BlockRow key={block.id} block={block} onUpdateBlock={onUpdateBlock} onDeleteBlock={onDeleteBlock} />
        ) : (
          <InlineEditableBlock key={block.id} block={block} onUpdateBlock={onUpdateBlock} onDeleteBlock={onDeleteBlock} />
        ))}
      </ul>}
    </section>
  )
}
