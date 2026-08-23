import { useEffect, useRef, useState, type FormEvent } from 'react'

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

type ConversationMessage = {
  role: 'user' | 'assistant'
  content: string
  sources?: AgentSource[]
}

export function AssistantPanel({ workspaceId, onSelectPage, onWorkspaceChanged }: AssistantPanelProps) {
  const [question, setQuestion] = useState('')
  const [conversation, setConversation] = useState<ConversationMessage[]>([])
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [progressMessage, setProgressMessage] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [localAIReady, setLocalAIReady] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript && (stickToBottomRef.current || proposal)) {
      transcript.scrollTop = transcript.scrollHeight
    }
  }, [conversation, error, progressMessage, proposal])

  const handleEvent = (event: AgentEvent) => {
    if (event.type === 'run') setRunId(event.run_id)
    if (event.type === 'activity') {
      setProgressMessage(event.message.replace(/\.{3}$/, ''))
    }
    if (event.type === 'sources') {
      setProgressMessage('Thinking')
      setConversation((current) => {
        const last = current[current.length - 1]
        if (!last || last.role !== 'assistant') return current
        return [...current.slice(0, -1), { ...last, sources: event.sources }]
      })
    }
    if (event.type === 'text') {
      setProgressMessage(null)
      setConversation((current) => {
        const last = current[current.length - 1]
        if (!last || last.role !== 'assistant') return current
        return [...current.slice(0, -1), { ...last, content: last.content + event.content }]
      })
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
    stickToBottomRef.current = true
    setQuestion('')
    setConversation((current) => [...current, { role: 'user', content: message }, { role: 'assistant', content: '' }])
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
    if (runId && workspaceId) void cancelAgentRun(workspaceId, runId).catch(() => undefined)
    setRunning(false)
    setProgressMessage(null)
    setConversation((current) => {
      const last = current[current.length - 1]
      if (!last || last.role !== 'assistant' || last.content) return current
      return [...current.slice(0, -1), { ...last, content: 'Cancelled.' }]
    })
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

      <div
        className="assistant-transcript"
        aria-live="polite"
        ref={transcriptRef}
        onScroll={(event) => {
          const transcript = event.currentTarget
          stickToBottomRef.current = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 48
        }}
      >
        {running && progressMessage && (
          <p className="assistant-progress" role="status">{progressMessage}</p>
        )}
        {conversation.map((message, index) => (
          <article className={`assistant-message assistant-message-${message.role}`} key={`${message.role}-${index}`}>
            <span className="assistant-message-label">{message.role === 'user' ? 'You' : 'Assistant'}</span>
            {message.content && <p>{message.content}</p>}
            {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
              <section className="assistant-sources" aria-label="Sources">
                <h3>Sources</h3>
                <ul>
                  {message.sources.map((source) => (
                    <li key={`${source.kind}-${source.block_id ?? source.file_id ?? source.page_id}`}>
                      <button type="button" className="source-link" disabled={!source.page_id} onClick={() => source.page_id && onSelectPage(source.page_id)}>
                        {source.title}
                      </button>
                      <span>{source.kind === 'block' ? 'Block' : source.kind === 'file' ? 'File' : 'Page'} · {source.snippet}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </article>
        ))}
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
