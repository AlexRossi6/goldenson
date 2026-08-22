import { useRef, useState, type FormEvent } from 'react'

import {
  cancelAgentRun,
  decideAgentProposal,
  streamAgentRun,
  type AgentEvent,
  type AgentProposal,
  type AgentSource,
  type AgentWorkspaceChange,
} from '../../api/agent'
import { LocalAIManager } from '../local-ai/LocalAIManager'

type AssistantPanelProps = {
  workspaceId: string
  onSelectPage: (pageId: string) => void
  onWorkspaceChanged?: (change: AgentWorkspaceChange) => void
}

export function AssistantPanel({ workspaceId, onSelectPage, onWorkspaceChanged }: AssistantPanelProps) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [activity, setActivity] = useState<string[]>([])
  const [sources, setSources] = useState<AgentSource[]>([])
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [progressMessage, setProgressMessage] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [localAIReady, setLocalAIReady] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  const handleEvent = (event: AgentEvent) => {
    if (event.type === 'run') setRunId(event.run_id)
    if (event.type === 'activity') {
      setActivity((current) => [...current, event.message])
      setProgressMessage(event.message.replace(/\.{3}$/, ''))
    }
    if (event.type === 'sources') {
      setSources(event.sources)
      setProgressMessage('Thinking')
    }
    if (event.type === 'text') {
      setProgressMessage(null)
      setAnswer((current) => current + event.content)
    }
    if (event.type === 'proposal') {
      setProgressMessage(null)
      setProposal(event.proposal)
    }
    if (event.type === 'workspace_changed') onWorkspaceChanged?.(event)
    if (event.type === 'error') {
      setProgressMessage(null)
      setError(event.message)
    }
    if (event.type === 'done') {
      setProgressMessage(null)
      setRunning(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const message = question.trim()
    if (!message || running) return

    const controller = new AbortController()
    controllerRef.current = controller
    setAnswer('')
    setActivity([])
    setSources([])
    setProposal(null)
    setError(null)
    setRunId(null)
    setRunning(true)
    setProgressMessage('Preparing answer')

    try {
      await streamAgentRun(workspaceId, message, handleEvent, controller.signal)
    } catch (streamError) {
      if (!(streamError instanceof DOMException && streamError.name === 'AbortError')) {
        setError(streamError instanceof Error ? streamError.message : 'The assistant could not complete this request.')
      }
    } finally {
      setRunning(false)
      controllerRef.current = null
    }
  }

  const cancel = () => {
    controllerRef.current?.abort()
    if (runId) void cancelAgentRun(runId).catch(() => undefined)
    setRunning(false)
    setProgressMessage(null)
    setActivity((current) => [...current, 'Cancelled.'])
  }

  const decide = async (approved: boolean) => {
    if (!proposal) return
    const decidedProposal = proposal
    const controller = new AbortController()
    controllerRef.current = controller
    setError(null)
    setProposal(null)
    setRunning(true)
    setProgressMessage(approved ? 'Approved, continuing' : 'Rejected, continuing')
    try {
      await decideAgentProposal(
        workspaceId,
        decidedProposal.tool_call_id,
        approved,
        handleEvent,
        controller.signal,
      )
    } catch (decisionError) {
      if (!(decisionError instanceof DOMException && decisionError.name === 'AbortError')) {
        setProposal(decidedProposal)
        setError(decisionError instanceof Error ? decisionError.message : 'Could not record decision.')
      }
    } finally {
      setRunning(false)
      setProgressMessage(null)
      controllerRef.current = null
    }
  }

  return (
    <aside className={`assistant-panel${expanded ? '' : ' is-collapsed'}`} aria-label="Workspace assistant">
      <header className="assistant-header">
        <div>
          <p className="panel-label">Private workspace AI</p>
          <h2>Assistant</h2>
        </div>
        <button
          type="button"
          className="assistant-toggle tree-icon"
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse assistant' : 'Expand assistant'}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? '⌄' : '⌃'}
        </button>
      </header>
      <LocalAIManager onReadyChange={setLocalAIReady} />

      <div className="assistant-transcript" aria-live="polite">
        {running && progressMessage && (
          <p className="assistant-progress" role="status">{progressMessage}</p>
        )}
        {activity.length > 0 && (
          <ol className="assistant-activity" aria-label="Agent activity">
            {activity.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ol>
        )}

        {answer && <div className="assistant-answer">{answer}</div>}
        {error && <p className="assistant-error" role="alert">{error}</p>}

        {proposal && (
          <section className="assistant-proposal" aria-label="Proposed change">
            <span className={`permission-label permission-${proposal.permission.toLowerCase()}`}>
              {proposal.permission}
            </span>
            <p>{proposal.expected_effect}</p>
            <div className="assistant-actions">
              <button type="button" className="button button-primary" onClick={() => void decide(true)}>Approve</button>
              <button type="button" className="button button-secondary" onClick={() => void decide(false)}>Reject</button>
            </div>
          </section>
        )}

        {sources.length > 0 && (
          <section className="assistant-sources" aria-label="Sources">
            <h3>Sources</h3>
            <ul>
              {sources.map((source) => (
                <li key={`${source.kind}-${source.block_id ?? source.file_id ?? source.page_id}`}>
                  <button
                    type="button"
                    className="source-link"
                    disabled={!source.page_id}
                    onClick={() => source.page_id && onSelectPage(source.page_id)}
                  >
                    {source.title}
                  </button>
                  <span>{source.kind}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <form className="assistant-compose" onSubmit={(event) => void submit(event)}>
        <label htmlFor="assistant-question" className="visually-hidden">Ask the workspace assistant</label>
        <textarea
          id="assistant-question"
          placeholder={localAIReady ? 'Ask about this workspace...' : 'Set up Local AI to use the assistant'}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          disabled={running || !localAIReady}
        />
        <div className="assistant-actions">
          <button type="submit" className="button button-primary" disabled={!question.trim() || running || !localAIReady}>Send</button>
          {running && <button type="button" className="button button-secondary" onClick={cancel}>Cancel</button>}
        </div>
      </form>
    </aside>
  )
}
