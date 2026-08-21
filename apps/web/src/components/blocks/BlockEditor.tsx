import { useMemo, useState, type KeyboardEvent } from 'react'

import type { Block } from '../../types/api'

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

function BlockRow({ block, onUpdateBlock, onDeleteBlock }: BlockRowProps) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(getText(block))
  const [code, setCode] = useState(typeof block.content.code === 'string' ? block.content.code : '')
  const [checked, setChecked] = useState(block.content.checked === true)
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
    setChecked(block.content.checked === true)
    setEditing(false)
  }

  const startEditing = () => {
    if (!busy) setEditing(true)
  }

  const persist = (content: Record<string, unknown>) => {
    void save(content).catch(() => undefined)
  }

  const handleTextKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
    if (event.key === 'Enter') {
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

  const displayText = block.type === 'heading' ? <h4>{getText(block) || 'Untitled heading'}</h4> : <p>{getText(block) || 'Empty paragraph'}</p>

  return (
    <li className={`block-card ${editing ? 'is-editing' : ''}`}>
      <div className="block-meta">
        <span>{block.type === 'todo' ? 'Task' : block.type === 'code' ? 'Code' : block.type === 'heading' ? 'Heading' : 'Paragraph'}</span>
        <button type="button" className="text-button danger-link" onClick={() => void onDeleteBlock(block)} disabled={busy}>Delete</button>
      </div>
      <div className="block-content">
        {block.type === 'todo' ? (
          <div className="todo-row">
            <input
              type="checkbox"
              aria-label={`Mark ${getText(block) || 'task'} complete`}
              checked={checked}
              disabled={busy}
              onChange={(event) => {
                setChecked(event.target.checked)
                persist({ ...block.content, text, checked: event.target.checked })
              }}
            />
            {editing ? (
              <input
                className="block-edit-input"
                aria-label="To-do text"
                value={text}
                onChange={(event) => setText(event.target.value)}
                onBlur={() => persist({ ...block.content, text })}
                onKeyDown={handleTextKeyDown}
                autoFocus
              />
            ) : (
              <button type="button" className="block-display" aria-label="Edit todo" onClick={startEditing}>{getText(block) || 'Untitled task'}</button>
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
          ) : (
            <input
              className="block-edit-input"
              aria-label={`${block.type} content`}
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
    const content = type === 'todo' ? { text: 'New task', checked: false } : type === 'code' ? { language: 'text', code: '' } : { text: type === 'heading' ? 'New heading' : 'Start writing...' }
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
            <button type="button" className="button button-secondary" onClick={() => void addBlock('heading')}>Heading</button>
            <button type="button" className="button button-secondary" onClick={() => void addBlock('todo')}>To-do</button>
            <button type="button" className="button button-secondary" onClick={() => void addBlock('code')}>Code</button>
          </>}
        </div>
      </div>
      {sortedBlocks.length === 0 ? <p className="empty-copy">A blank page is ready for your ideas.</p> : <ul className="block-list" aria-label="Page content">
        {sortedBlocks.map((block) => <BlockRow key={block.id} block={block} onUpdateBlock={onUpdateBlock} onDeleteBlock={onDeleteBlock} />)}
      </ul>}
    </section>
  )
}
