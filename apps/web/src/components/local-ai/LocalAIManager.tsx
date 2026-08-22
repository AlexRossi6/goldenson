import { useEffect, useRef, useState } from 'react'

import {
  cancelModelInstallation,
  getLocalAIStatus,
  installLocalModel,
  installLocalRuntime,
  removeLocalModel,
  selectLocalModel,
  startLocalRuntime,
  type InstallProgressEvent,
  type LocalAIStatus,
  type LocalModelStatus,
  type RuntimeInstallProgressEvent,
} from '../../api/localAi'

type LocalAIManagerProps = {
  onReadyChange: (ready: boolean) => void
}

type Confirmation = { kind: 'install' | 'remove'; model: LocalModelStatus }

function formatBytes(bytes: number | null): string {
  if (bytes === null) return 'Unknown'
  const gib = bytes / 1024 ** 3
  return `${gib >= 10 ? gib.toFixed(0) : gib.toFixed(1)} GB`
}

function progressLabel(model: LocalModelStatus): string {
  if (model.progress === null) return model.state
  return `${Math.round(model.progress * 100)}%`
}

export function LocalAIManager({ onReadyChange }: LocalAIManagerProps) {
  const [status, setStatus] = useState<LocalAIStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [startingRuntime, setStartingRuntime] = useState(false)
  const [runtimeConfirmation, setRuntimeConfirmation] = useState(false)
  const [runtimeInstall, setRuntimeInstall] = useState<RuntimeInstallProgressEvent | null>(null)
  const [installMessages, setInstallMessages] = useState<Record<string, string>>({})
  const controllerRef = useRef<AbortController | null>(null)
  const firstRunHandled = useRef(false)

  const refresh = async () => {
    try {
      const next = await getLocalAIStatus()
      setStatus(next)
      setError(null)
      const selectedModel = next.models.find((model) => model.selected)
      if (!firstRunHandled.current && (!next.runtime.usable || selectedModel?.state !== 'ready')) {
        setOpen(true)
        firstRunHandled.current = true
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Local AI status is unavailable.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    queueMicrotask(() => {
      if (active) void refresh()
    })
    return () => {
      active = false
    }
  }, [])

  const selected = status?.models.find((model) => model.selected) ?? null
  const ready = Boolean(status?.runtime.usable && selected?.state === 'ready')

  useEffect(() => {
    onReadyChange(ready)
  }, [onReadyChange, ready])

  const updateProgress = (event: InstallProgressEvent) => {
    if (event.message) {
      setInstallMessages((current) => ({ ...current, [event.model_id]: event.message! }))
    }
    setStatus((current) => current ? {
      ...current,
      models: current.models.map((model) => model.id === event.model_id ? {
        ...model,
        state: event.state,
        progress: event.progress,
        downloaded_bytes: event.downloaded_bytes,
        total_bytes: event.total_bytes,
        error: event.state === 'failed' ? event.message : null,
      } : model),
    } : current)
  }

  const install = async (model: LocalModelStatus) => {
    setConfirmation(null)
    setError(null)
    setInstallMessages((current) => ({ ...current, [model.id]: 'Starting download...' }))
    setStatus((current) => current ? {
      ...current,
      models: current.models.map((item) => item.id === model.id ? {
        ...item,
        state: 'checking',
        progress: null,
        downloaded_bytes: null,
        total_bytes: null,
        error: null,
      } : item),
    } : current)
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      await installLocalModel(model.id, updateProgress, controller.signal)
      await refresh()
    } catch (installError) {
      if (!(installError instanceof DOMException && installError.name === 'AbortError')) {
        setError(installError instanceof Error ? installError.message : 'Model installation failed.')
      }
    } finally {
      controllerRef.current = null
    }
  }

  const cancel = async (model: LocalModelStatus) => {
    controllerRef.current?.abort()
    try {
      await cancelModelInstallation(model.id)
    } catch {
      // The stream may have reached a terminal state before cancellation arrived.
    }
    setStatus((current) => current ? {
      ...current,
      models: current.models.map((item) => item.id === model.id ? {
        ...item,
        state: 'cancelled',
        error: null,
      } : item),
    } : current)
  }

  const select = async (modelId: string) => {
    try {
      setStatus(await selectLocalModel(modelId))
      setError(null)
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : 'Model selection failed.')
    }
  }

  const remove = async (model: LocalModelStatus) => {
    setConfirmation(null)
    try {
      setStatus(await removeLocalModel(model.id))
      setError(null)
    } catch (removalError) {
      setError(removalError instanceof Error ? removalError.message : 'Model removal failed.')
    }
  }

  const startRuntime = async () => {
    setStartingRuntime(true)
    try {
      const runtime = await startLocalRuntime()
      if (!runtime.reachable) setError(runtime.error ?? 'Ollama could not be started.')
      await refresh()
    } finally {
      setStartingRuntime(false)
    }
  }

  const installRuntime = async () => {
    setRuntimeConfirmation(false)
    setError(null)
    setRuntimeInstall({
      state: 'downloading',
      progress: null,
      downloaded_bytes: null,
      total_bytes: null,
      message: 'Starting Ollama download...',
    })
    const controller = new AbortController()
    try {
      await installLocalRuntime(setRuntimeInstall, controller.signal)
      const runtime = await startLocalRuntime()
      if (!runtime.reachable) setError(runtime.error ?? 'Ollama was installed but could not start.')
      await refresh()
    } catch (installError) {
      setError(installError instanceof Error ? installError.message : 'Ollama installation failed.')
    }
  }

  const activeInstall = status?.models.find((model) =>
    ['checking', 'downloading', 'installing'].includes(model.state)) ?? null
  const installed = status?.models.filter((model) => model.state === 'ready') ?? []
  const available = status?.models.filter((model) => model.state !== 'ready') ?? []
  const recommended = status?.models.find((model) => model.recommended) ?? status?.models[0]

  return (
    <>
      <section className="local-ai-summary" aria-label="Local AI status">
        <div>
          <span className={`status-dot ${ready ? 'is-ready' : ''}`} aria-hidden="true" />
          <span>{loading ? 'Checking local AI...' : ready && selected ? `${selected.name} · Ready` : 'Local AI setup required'}</span>
        </div>
        <button type="button" className="text-button" onClick={() => setOpen(true)}>Models</button>
      </section>

      {open && (
        <div className="dialog-backdrop local-ai-backdrop" role="presentation">
          <section className="dialog local-ai-dialog" role="dialog" aria-modal="true" aria-labelledby="local-ai-title">
            <header className="local-ai-dialog-header">
              <div>
                <p className="eyebrow">Private, on-device inference</p>
                <h2 id="local-ai-title">Local AI</h2>
              </div>
              <button type="button" className="tree-icon" aria-label="Close Local AI" onClick={() => setOpen(false)}>×</button>
            </header>

            {error && <p className="assistant-error" role="alert">{error}</p>}

            {status && !status.runtime.reachable && (
              <section className="runtime-callout">
                <h3>{status.runtime.installed ? 'Ollama is not running' : 'Ollama is required'}</h3>
                <p>{status.runtime.error}</p>
                {status.runtime.installed ? (
                  <button type="button" className="button button-primary" onClick={() => void startRuntime()} disabled={startingRuntime}>
                    {startingRuntime ? 'Starting...' : 'Start Ollama'}
                  </button>
                ) : (
                  <>
                    <p className="local-ai-note">Ollama is the local engine that runs Qwen, Llama, and Gemma. GoldenSon never falls back to cloud AI.</p>
                    <button type="button" className="button button-primary" disabled={runtimeInstall !== null && runtimeInstall.state !== 'failed'} onClick={() => setRuntimeConfirmation(true)}>
                      {runtimeInstall !== null && runtimeInstall.state !== 'failed' ? 'Installing Ollama...' : 'Install Ollama'}
                    </button>
                  </>
                )}
                {runtimeInstall && (
                  <div className="runtime-progress" aria-live="polite">
                    <progress max={1} value={runtimeInstall.progress ?? undefined} aria-label="Installing Ollama" />
                    <span>{runtimeInstall.message}</span>
                    {runtimeInstall.downloaded_bytes !== null && runtimeInstall.total_bytes !== null && (
                      <strong>{Math.round((runtimeInstall.progress ?? 0) * 100)}% · {formatBytes(runtimeInstall.downloaded_bytes)} / {formatBytes(runtimeInstall.total_bytes)}</strong>
                    )}
                  </div>
                )}
                <button type="button" className="button button-secondary" onClick={() => void refresh()}>Check again</button>
              </section>
            )}

            {status?.runtime.reachable && !status.selected_model && recommended && (
              <section className="first-run-model">
                <p className="panel-label">Recommended for this computer</p>
                <h3>Set up your local AI</h3>
                <p>GoldenSon can run AI entirely on your computer. Workspace content and prompts stay local.</p>
                <strong>{recommended.name}</strong>
                <span>{formatBytes(recommended.size_bytes)} download · {recommended.role}</span>
                <button type="button" className="button button-primary" onClick={() => setConfirmation({ kind: 'install', model: recommended })}>
                  Install model
                </button>
              </section>
            )}

            {status && (
              <div className="model-sections">
                <section>
                  <h3>Current model</h3>
                  <div className="current-model-row">
                    <span>{selected?.name ?? 'None selected'}</span>
                    <strong>{ready ? 'Ready' : 'Setup required'}</strong>
                  </div>
                </section>

                <section>
                  <h3>Installed models</h3>
                  {installed.length === 0 ? <p className="panel-copy">No models installed from the supported catalog.</p> : (
                    <ul className="model-list">
                      {installed.map((model) => (
                        <li key={model.id} className="model-row">
                          <div><strong>{model.name}</strong><span>{model.role}</span></div>
                          <span>{formatBytes(model.installed_size_bytes ?? model.size_bytes)}</span>
                          {model.selected ? <span className="ready-label">Selected</span> : (
                            <button type="button" className="button button-secondary" onClick={() => void select(model.id)}>Use</button>
                          )}
                          <button type="button" className="text-button danger-link" disabled={model.selected} onClick={() => setConfirmation({ kind: 'remove', model })}>Remove</button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section>
                  <h3>Available models</h3>
                  <ul className="model-list">
                    {available.map((model) => {
                      const active = ['checking', 'downloading', 'installing'].includes(model.state)
                      return (
                        <li key={model.id} className="model-row">
                          <div>
                            <strong>{model.name}{model.recommended ? ' · Recommended' : ''}</strong>
                            <span>{model.role}</span>
                            {active && (
                              <div className="model-progress">
                                <progress max={1} value={model.progress ?? undefined} aria-label={`Installing ${model.name}`} />
                                <span className="model-progress-message">{installMessages[model.id] ?? progressLabel(model)}</span>
                                {model.downloaded_bytes !== null && model.total_bytes !== null && (
                                  <span className="model-progress-detail">{progressLabel(model)} · {formatBytes(model.downloaded_bytes)} / {formatBytes(model.total_bytes)}</span>
                                )}
                              </div>
                            )}
                            {model.error && <span className="model-error">{model.error}</span>}
                          </div>
                          <span>{formatBytes(model.size_bytes)}</span>
                          {active ? (
                            <button type="button" className="button button-secondary" onClick={() => void cancel(model)}>Cancel</button>
                          ) : (
                            <button type="button" className="button button-secondary" disabled={!status.runtime.reachable} onClick={() => setConfirmation({ kind: 'install', model })}>
                              {!status.runtime.reachable ? 'Requires Ollama' : model.state === 'failed' || model.state === 'cancelled' ? 'Retry' : 'Install'}
                            </button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </section>

                <footer className="local-ai-storage">
                  <span>Available disk space</span>
                  <strong>{formatBytes(status.disk_free_bytes)}</strong>
                </footer>
              </div>
            )}

            {confirmation && (
              <section className="model-confirmation" role="alertdialog" aria-modal="true" aria-label={`${confirmation.kind === 'install' ? 'Install' : 'Remove'} ${confirmation.model.name}`}>
                <h3>{confirmation.kind === 'install' ? `Install ${confirmation.model.name}?` : `Remove ${confirmation.model.name}?`}</h3>
                {confirmation.kind === 'install' ? (
                  <p>Download size: approximately {formatBytes(confirmation.model.size_bytes)}. Required disk space: approximately {formatBytes(confirmation.model.required_disk_bytes)}. This model runs entirely on your computer.</p>
                ) : (
                  <p>This will free approximately {formatBytes(confirmation.model.installed_size_bytes ?? confirmation.model.size_bytes)} of disk space.</p>
                )}
                <div className="dialog-actions">
                  <button type="button" className="button button-secondary" onClick={() => setConfirmation(null)}>Cancel</button>
                  <button type="button" className={confirmation.kind === 'remove' ? 'button button-danger' : 'button button-primary'} onClick={() => confirmation.kind === 'install' ? void install(confirmation.model) : void remove(confirmation.model)}>
                    {confirmation.kind === 'install' ? 'Install' : 'Remove'}
                  </button>
                </div>
              </section>
            )}

            {runtimeConfirmation && (
              <section className="model-confirmation" role="alertdialog" aria-modal="true" aria-label="Install Ollama">
                <h3>Install Ollama?</h3>
                <p>GoldenSon will download the official signed Ollama application from ollama.com and install it only in GoldenSon's local runtime folder. This requires an internet connection and does not install a model yet.</p>
                <div className="dialog-actions">
                  <button type="button" className="button button-secondary" onClick={() => setRuntimeConfirmation(false)}>Cancel</button>
                  <button type="button" className="button button-primary" onClick={() => void installRuntime()}>Install Ollama</button>
                </div>
              </section>
            )}

            {activeInstall && !confirmation && <span className="visually-hidden">Installation in progress</span>}
          </section>
        </div>
      )}
    </>
  )
}
