import type { WorkspaceIndexHealth } from '../../types/api'

type IndexHealthProps = {
  health: WorkspaceIndexHealth | undefined
  loading: boolean
  retrying: boolean
  onRetryFailed: () => void
}

function pluralize(count: number, singular: string): string {
  return `${count} ${count === 1 ? singular : `${singular}s`}`
}

export function IndexHealth({ health, loading, retrying, onRetryFailed }: IndexHealthProps) {
  if (loading && !health) {
    return <p className="index-health-summary">Checking search readiness...</p>
  }
  if (!health) return null

  const failed = health.pages.failed + health.files.failed
  const pageSummary = health.pages.total === 0
    ? 'No pages yet'
    : health.pages.indexing > 0
      ? `${pluralize(health.pages.indexing, 'page')} preparing`
      : health.pages.failed > 0
        ? health.pages.failed === 1 ? '1 page needs attention' : `${health.pages.failed} pages need attention`
        : health.pages.stale > 0
          ? health.pages.stale === 1 ? '1 page needs refresh' : `${health.pages.stale} pages need refresh`
          : `${pluralize(health.pages.ready, 'page')} ready`
  const fileParts = []
  if (health.files.ready > 0) fileParts.push(`${pluralize(health.files.ready, 'file')} content-searchable`)
  if (health.files.metadata_only > 0) fileParts.push(`${pluralize(health.files.metadata_only, 'file')} stored; contents not searchable`)
  if (health.files.indexing > 0) fileParts.push(`${pluralize(health.files.indexing, 'file')} preparing`)
  if (health.files.failed > 0) fileParts.push(health.files.failed === 1 ? '1 file needs attention' : `${health.files.failed} files need attention`)

  return (
    <section className={`index-health is-${health.status}`} aria-label="Search readiness">
      <div className="index-health-heading">
        <p className="panel-label">Search readiness</p>
        <span>{health.status === 'indexing' ? 'Preparing' : health.status === 'ready' ? 'Ready' : 'Needs attention'}</span>
      </div>
      <p className="index-health-summary">Page search: {pageSummary}</p>
      {health.files.total > 0 && <p className="index-health-summary">File content: {fileParts.join(' · ')}</p>}
      {failed > 0 && (
        <button type="button" className="text-button" onClick={onRetryFailed} disabled={retrying}>
          {retrying ? 'Retrying...' : 'Retry failed indexing'}
        </button>
      )}
    </section>
  )
}
