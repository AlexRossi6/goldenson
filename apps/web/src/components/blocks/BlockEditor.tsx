import { useMemo, useState } from 'react'

import type { Block } from '../../types/api'
import { BlockPicker } from './BlockPicker'
import { InlineEditableBlock } from './InlineEditableBlock'

type BlockPayload = {
  version: number
  type?: string
  position?: number
  content?: Record<string, unknown>
}

type BlockEditorProps = {
  blocks: Block[]
  loading?: boolean
  highlightedBlockId?: string | null
  onCreateBlock: (payload: { type: string; position: number; content: Record<string, unknown> }) => Promise<Block>
  onUpdateBlock: (blockId: string, payload: BlockPayload) => Promise<void>
  onDeleteBlock: (block: Block) => Promise<void>
  onReorderBlocks?: (blockIds: string[], versions: Record<string, number>) => Promise<void>
}

function generateId(): string {
  return `item-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function BlockEditor({ blocks, loading = false, highlightedBlockId = null, onCreateBlock, onUpdateBlock, onDeleteBlock, onReorderBlocks }: BlockEditorProps) {
  const sortedBlocks = useMemo(() => [...blocks].sort((a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at)), [blocks])
  const [creating, setCreating] = useState(false)
  const [draggedBlockId, setDraggedBlockId] = useState<string | null>(null)
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)

  const moveBlock = async (targetId: string) => {
    if (!draggedBlockId || draggedBlockId === targetId) return
    const next = [...sortedBlocks]
    const fromIndex = next.findIndex((block) => block.id === draggedBlockId)
    const targetIndex = next.findIndex((block) => block.id === targetId)
    if (fromIndex < 0 || targetIndex < 0) return
    const [moved] = next.splice(fromIndex, 1)
    next.splice(targetIndex, 0, moved)
    await onReorderBlocks?.(next.map((block) => block.id), Object.fromEntries(next.map((block) => [block.id, block.version])))
  }

  const addBlock = async (type: string) => {
    const content = type === 'todo' ? { title: '', items: [{ id: generateId(), text: '', completed: false }] } : type === 'code' ? { language: 'text', code: '' } : { text: '' }
    await onCreateBlock({ type, position: sortedBlocks.length, content })
    setCreating(false)
  }

  const createParagraphAfter = (content: Record<string, unknown>) => onCreateBlock({
    type: 'paragraph',
    position: Math.max(-1, ...sortedBlocks.map((block) => block.position)) + 1,
    content,
  })

  return (
    <section>
      {!loading && <div className="new-block-card">
          <BlockPicker key={creating ? 'open' : 'closed'} open={creating} onToggle={() => setCreating(!creating)} onSelect={addBlock} />
        </div>}
      {loading ? <p className="loading-copy" role="status">Loading page content...</p> : sortedBlocks.length === 0 ? <p className="empty-copy">A blank page is ready for your ideas.</p> : <ul className="block-list" aria-label="Page content">
        {sortedBlocks.map((block) => (
          <InlineEditableBlock
            key={block.id}
            block={block}
            highlighted={block.id === highlightedBlockId}
            dragging={block.id === draggedBlockId}
            dropTarget={block.id === dropTargetId}
            onDragStart={(event) => {
              if (!(event.target instanceof HTMLElement) || !event.target.closest('.block-drag-handle')) {
                event.preventDefault()
                return
              }
              setDraggedBlockId(block.id)
              event.dataTransfer.effectAllowed = 'move'
              event.dataTransfer.setData('text/plain', block.id)
            }}
            onDragEnd={() => { setDraggedBlockId(null); setDropTargetId(null) }}
            onDragOver={(event) => { event.preventDefault(); setDropTargetId(block.id) }}
            onDrop={(event) => { event.preventDefault(); void moveBlock(block.id).finally(() => { setDraggedBlockId(null); setDropTargetId(null) }) }}
            onCreateBlockAfter={createParagraphAfter}
            onUpdateBlock={onUpdateBlock}
            onDeleteBlock={onDeleteBlock}
          />
        ))}
      </ul>}
    </section>
  )
}
