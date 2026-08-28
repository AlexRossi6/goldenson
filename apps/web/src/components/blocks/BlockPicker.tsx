import { useEffect, useMemo, useRef, useState } from 'react'

import { BLOCK_TYPES } from './blockTypes'

type BlockPickerProps = {
  open: boolean
  onToggle: () => void
  onSelect: (type: string) => Promise<void>
}

export function BlockPicker({ open, onToggle, onSelect }: BlockPickerProps) {
  const pickerRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selecting, setSelecting] = useState(false)
  const normalizedQuery = query.trim().toLowerCase()
  const filteredTypes = useMemo(() => BLOCK_TYPES.filter((blockType) => {
    if (!normalizedQuery) return true
    return [blockType.name, blockType.description, ...(blockType.keywords ?? [])]
      .some((value) => value.toLowerCase().includes(normalizedQuery))
  }), [normalizedQuery])

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !selecting) onToggle()
    }
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !pickerRef.current?.contains(event.target) && !selecting) onToggle()
    }
    window.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [onToggle, open, selecting])

  const select = async (type: string) => {
    setSelecting(true)
    try {
      await onSelect(type)
    } finally {
      setSelecting(false)
    }
  }

  return (
    <div ref={pickerRef} className="block-type-picker">
      <button type="button" className="text-button add-block-toggle" aria-expanded={open} aria-haspopup="dialog" onClick={onToggle}>
        {open ? 'Close' : '+ Add block'}
      </button>
      {open && (
        <div className="block-picker-popover" role="dialog" aria-label="Add a block">
          <label className="block-picker-search-label" htmlFor="block-picker-search">Find a block</label>
          <input
            ref={searchRef}
            id="block-picker-search"
            className="block-picker-search"
            type="search"
            placeholder="Search block types"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="block-picker-options" role="listbox" aria-label="Available block types">
            {filteredTypes.length > 0 ? filteredTypes.map((blockType) => (
              <button
                key={blockType.type}
                type="button"
                className="block-picker-option"
                role="option"
                aria-selected="false"
                disabled={selecting}
                onClick={() => void select(blockType.type)}
              >
                <span className="block-picker-option-name">{blockType.name}</span>
                <span className="block-picker-option-description">{blockType.description}</span>
              </button>
            )) : <p className="block-picker-empty">No matching block types.</p>}
          </div>
        </div>
      )}
    </div>
  )
}