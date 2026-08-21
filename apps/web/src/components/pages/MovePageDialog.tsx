import { useEffect, useMemo, useRef, useState } from 'react'

import type { Page } from '../../types/api'
import { getDescendantIds } from './tree'

type MovePageDialogProps = {
  page: Page
  pages: Page[]
  open: boolean
  busy?: boolean
  onCancel: () => void
  onMove: (parentPageId: string | null, position: number) => Promise<void>
}

export function MovePageDialog({ page, pages, open, busy = false, onCancel, onMove }: MovePageDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const [parentId, setParentId] = useState<string | null>(page.parent_page_id)
  const [position, setPosition] = useState(String(page.position + 1))
  const descendants = useMemo(() => getDescendantIds(pages, page.id), [page.id, pages])
  const options = pages.filter((candidate) => candidate.id !== page.id && !descendants.has(candidate.id)).sort((a, b) => a.title.localeCompare(b.title))

  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && !busy && onCancel()
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onCancel, open])

  if (!open) return null

  const submit = async () => {
    const parsedPosition = Number(position)
    await onMove(parentId, Number.isFinite(parsedPosition) && parsedPosition > 0 ? parsedPosition - 1 : page.position)
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="move-dialog-title">
        <p className="eyebrow">Page actions</p>
        <h2 id="move-dialog-title">Move “{page.title}”</h2>
        <p className="dialog-message">Choose where this page should live in your workspace.</p>
        <label>Move to
          <select value={parentId ?? ''} onChange={(event) => setParentId(event.target.value || null)}>
            <option value="">Workspace root</option>
            {options.map((option) => <option key={option.id} value={option.id}>{option.title}</option>)}
          </select>
        </label>
        <label>Place it at
          <input type="number" min={1} value={position} onChange={(event) => setPosition(event.target.value)} />
        </label>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="button button-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="button button-primary" onClick={submit} disabled={busy}>{busy ? 'Moving...' : 'Move page'}</button>
        </div>
      </section>
    </div>
  )
}
