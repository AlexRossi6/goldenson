import { useEffect, useRef } from 'react'

type ConfirmDialogProps = {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  onCancel: () => void
  onConfirm: () => void
  busy?: boolean
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onCancel,
  onConfirm,
  busy = false,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onCancel, open])

  if (!open) return null

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && !busy && onCancel()}>
      <section className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message">
        <p className="eyebrow">Please confirm</p>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p id="confirm-dialog-message" className="dialog-message">{message}</p>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="button button-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="button button-danger" onClick={onConfirm} disabled={busy}>{busy ? 'Deleting...' : confirmLabel}</button>
        </div>
      </section>
    </div>
  )
}
