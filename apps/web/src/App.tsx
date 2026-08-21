import { useQuery } from '@tanstack/react-query'

import { fetchHealth } from './api/health'
import { useUiStore } from './store/ui'

function App() {
  const autoRefresh = useUiStore((state) => state.autoRefresh)
  const setAutoRefresh = useUiStore((state) => state.setAutoRefresh)

  const healthQuery = useQuery({
    queryKey: ['api-health'],
    queryFn: fetchHealth,
    refetchInterval: autoRefresh ? 15000 : false,
    retry: 1,
  })

  const lastChecked =
    healthQuery.dataUpdatedAt > 0
      ? new Date(healthQuery.dataUpdatedAt).toLocaleTimeString()
      : 'not checked yet'

  return (
    <div className="app-shell">
      <aside className="side-panel" aria-label="Navigation panel">
        <p className="panel-label">GoldenSon</p>
        <h2>Workspace Foundation</h2>
        <p className="panel-copy">Frontend scaffold with backend connectivity check.</p>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <p className="eyebrow">Local-first AI knowledge workspace</p>
          <h1>Frontend is running</h1>
          <p className="lead">Use the health card below to verify frontend to backend connectivity.</p>
        </header>

        <section className="card-grid">
          <article className="status-card">
            <div className="card-head">
              <h3>API Health</h3>
              <span className={`status-pill ${healthQuery.isError ? 'is-error' : 'is-ok'}`}>
                {healthQuery.isError ? 'unreachable' : 'ready'}
              </span>
            </div>

            <p className="card-copy">
              Endpoint: <strong>/api/health</strong>
            </p>
            <p className="card-copy">
              Response:{' '}
              <strong>{healthQuery.data?.status ?? (healthQuery.isError ? 'error' : 'pending')}</strong>
            </p>
            <p className="card-copy">Last checked: {lastChecked}</p>

            <div className="card-actions">
              <button
                className="action action-primary"
                type="button"
                onClick={() => healthQuery.refetch()}
                disabled={healthQuery.isFetching}
              >
                {healthQuery.isFetching ? 'Checking...' : 'Check backend health'}
              </button>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(event) => setAutoRefresh(event.target.checked)}
                />
                Auto refresh (15s)
              </label>
            </div>

            {healthQuery.isError && (
              <p className="error-note">Unable to reach API. Confirm the backend is running on port 8000.</p>
            )}
          </article>

          <article className="info-card">
            <h3>Current scope</h3>
            <ul>
              <li>Repository and tooling foundation</li>
              <li>Backend health endpoint</li>
              <li>Frontend connectivity verification</li>
            </ul>
          </article>
        </section>
      </main>
    </div>
  )
}

export default App
