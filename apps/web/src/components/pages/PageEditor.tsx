import { useState } from 'react'

import type { Block, FileMetadata, Page } from '../../types/api'
import type { PageKnowledge, RelatedPage } from '../../api/knowledge'
import { BlockEditor } from '../blocks/BlockEditor'
import { FileArea } from '../files/FileArea'

type PageEditorProps = {
  page: Page
  blocks: Block[]
  blocksLoading?: boolean
  attachments: FileMetadata[]
  attachmentsLoading: boolean
  attachmentsUploading: boolean
  attachmentsError: string | null
  busy: boolean
  errorMessage: string | null
  onRequestMove: () => void
  onRequestDelete: () => void
  onUpdatePage: (
    pageId: string,
    payload: { version: number; title?: string; parent_page_id?: string | null; position?: number },
  ) => Promise<void>
  onCreateBlock: (payload: {
    type: string
    position: number
    content: Record<string, unknown>
  }) => Promise<Block>
  onUpdateBlock: (
    blockId: string,
    payload: {
      version: number
      type?: string
      position?: number
      content?: Record<string, unknown>
    },
  ) => Promise<void>
  onDeleteBlock: (block: Block) => void | Promise<void>
  onUploadAttachment: (file: File) => Promise<void>
  onDeleteAttachment: (file: FileMetadata) => void
  relatedPages?: RelatedPage[]
  relatedLoading?: boolean
  relatedError?: boolean
  knowledge?: PageKnowledge
  onRetryKnowledge?: () => void
  onRetryRelated?: () => void
  onSelectPage?: (pageId: string) => void
}

export function PageEditor({
  page,
  blocks,
  blocksLoading = false,
  attachments,
  attachmentsLoading,
  attachmentsUploading,
  attachmentsError,
  busy,
  onUpdatePage,
  onCreateBlock,
  onUpdateBlock,
  onDeleteBlock,
  onRequestMove,
  onRequestDelete,
  onUploadAttachment,
  onDeleteAttachment,
  relatedPages = [],
  relatedLoading = false,
  relatedError = false,
  knowledge,
  onRetryKnowledge,
  onRetryRelated,
  onSelectPage,
}: PageEditorProps) {
  const [titleDraft, setTitleDraft] = useState(page.title)
  const [titleStatus, setTitleStatus] = useState<'saved' | 'unsaved' | 'saving'>('saved')

  const syncWithPage = () => {
    setTitleDraft(page.title)
    setTitleStatus('saved')
  }

  const saveTitle = async () => {
    if (!titleDraft.trim() || titleDraft.trim() === page.title) {
      syncWithPage()
      return
    }
    setTitleStatus('saving')
    try {
      await onUpdatePage(page.id, {
        title: titleDraft.trim(),
        version: page.version,
      })
      setTitleStatus('saved')
    } catch {
      setTitleStatus('unsaved')
    }
  }

  return (
    <section className="editor-shell" aria-label="Page editor">
      <header className="editor-head">
        <div className="title-row">
          <input
            className="title-input"
            aria-label="Page title"
            value={titleDraft}
            onChange={(event) => { setTitleDraft(event.target.value); setTitleStatus('unsaved') }}
            onBlur={() => void saveTitle()}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.currentTarget.blur() } }}
            disabled={busy}
          />
          <span className="save-status" aria-live="polite">{titleStatus === 'saving' ? 'Saving...' : titleStatus === 'unsaved' ? 'Unsaved' : 'Saved'}</span>
        </div>
        <div className="page-actions">
          <button type="button" className="button button-secondary" onClick={onRequestMove} disabled={busy}>Move page</button>
          <button type="button" className="button button-danger" onClick={onRequestDelete} disabled={busy}>Delete page</button>
        </div>
      </header>

      {(knowledge?.status === 'ready' || knowledge?.status === 'pending' || knowledge?.status === 'indexing' || knowledge?.status === 'failed' || knowledge?.status === 'stale' || relatedPages.length > 0 || relatedLoading || relatedError) && (
        <aside className="knowledge-strip" aria-label="Page knowledge">
          <div>
            <h3>Related</h3>
            {knowledge?.status === 'pending' && <span className="knowledge-status">Indexing...</span>}
            {knowledge?.status === 'indexing' && <span className="knowledge-status">Indexing...</span>}
            {knowledge?.status === 'ready' && <span className="knowledge-status">Ready</span>}
            {relatedLoading && <span className="knowledge-status">Finding related pages...</span>}
            {relatedError && <>
              <span className="knowledge-status">Related pages unavailable.</span>
              <button type="button" className="knowledge-retry" onClick={onRetryRelated}>Try again</button>
            </>}
            {(knowledge?.status === 'failed' || knowledge?.status === 'stale') && (
              <div className="knowledge-recovery">
                <span className="knowledge-status">{knowledge.status === 'failed' ? 'Page analysis failed.' : 'Page analysis is out of date.'}</span>
                <button type="button" className="knowledge-retry" onClick={onRetryKnowledge}>Retry analysis</button>
              </div>
            )}
            {knowledge?.status === 'ready' && knowledge.concepts.length > 0 && (
              <div className="concept-list" aria-label="Concepts">
                {knowledge.concepts.map((concept) => <span className="concept-pill" key={concept}>{concept}</span>)}
              </div>
            )}
          </div>
          {relatedPages.length > 0 && (
            <ul className="related-list">
              {relatedPages.map((related) => (
                <li key={related.page_id}>
                  <button type="button" onClick={() => onSelectPage?.(related.page_id)}>{related.title}</button>
                  <span>{related.reason}</span>
                </li>
              ))}
            </ul>
          )}
          {!relatedLoading && !relatedError && knowledge?.status === 'ready' && relatedPages.length === 0 && (
            <span className="knowledge-status">No related pages yet.</span>
          )}
        </aside>
      )}

      <BlockEditor
        blocks={blocks}
        loading={blocksLoading}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={async (block) => onDeleteBlock(block)}
      />

      <FileArea
        title="Attachments"
        files={attachments}
        loading={attachmentsLoading}
        uploading={attachmentsUploading}
        errorMessage={attachmentsError}
        onUpload={onUploadAttachment}
        onDelete={onDeleteAttachment}
      />
    </section>
  )
}
