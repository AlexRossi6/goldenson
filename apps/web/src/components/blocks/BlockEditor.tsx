import { useMemo, useState } from 'react'

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

function generateId(): string {
  return `item-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
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
          <button type="button" className="text-button add-block-toggle" onClick={() => setCreating(!creating)}>{creating ? 'Close' : '+ Add block'}</button>
          {creating && <>
            <button type="button" className="text-button block-type-option" onClick={() => void addBlock('paragraph')}>Paragraph</button>
            <button type="button" className="text-button block-type-option" onClick={() => void addBlock('todo')}>To-do</button>
            <button type="button" className="text-button block-type-option" onClick={() => void addBlock('code')}>Code</button>
          </>}
        </div>
      </div>
      {sortedBlocks.length === 0 ? <p className="empty-copy">A blank page is ready for your ideas.</p> : <ul className="block-list" aria-label="Page content">
        {sortedBlocks.map((block) => (
          <InlineEditableBlock key={block.id} block={block} onUpdateBlock={onUpdateBlock} onDeleteBlock={onDeleteBlock} />
        ))}
      </ul>}
    </section>
  )
}
