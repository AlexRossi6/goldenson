type EvidenceResultProps = {
  label: string
  title: string
  preview: string
  onOpen: () => void
  disabled?: boolean
}

export function EvidenceResult({ label, title, preview, onOpen, disabled = false }: EvidenceResultProps) {
  return (
    <button
      type="button"
      className="evidence-result"
      aria-label={title}
      onClick={onOpen}
      disabled={disabled}
    >
      <span className="evidence-result-meta">{label}</span>
      <strong>{title}</strong>
      <span className="evidence-result-preview">{preview}</span>
    </button>
  )
}