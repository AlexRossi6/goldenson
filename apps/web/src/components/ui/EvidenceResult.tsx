type EvidenceResultProps = {
  label: string
  title: string
  preview: string
  onOpen: () => void
}

export function EvidenceResult({ label, title, preview, onOpen }: EvidenceResultProps) {
  return (
    <button type="button" className="evidence-result" aria-label={title} onClick={onOpen}>
      <span className="evidence-result-meta">{label}</span>
      <strong>{title}</strong>
      <span className="evidence-result-preview">{preview}</span>
    </button>
  )
}