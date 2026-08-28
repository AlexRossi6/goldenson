import { useState } from 'react'

import type { Block, FileMetadata, Page } from '../../types/api'
import type { PageKnowledge, RelatedPage } from '../../api/knowledge'
import { BlockEditor } from '../blocks/BlockEditor'
import { FileArea } from '../files/FileArea'
import { EvidenceResult } from '../ui/EvidenceResult'

type PageEditorProps = {
  page: Page
  blocks: Block[]
  blocksLoading?: boolean
  highlightedBlockId?: string | null
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
  onReorderBlocks?: (blockIds: string[], versions: Record<string, number>) => Promise<void>
  onDeleteBlock: (block: Block) => void | Promise<void>
  onUploadAttachment: (file: File) => Promise<void>
  onDeleteAttachment: (file: FileMetadata) => void
  onRetryAttachmentIndex?: (file: FileMetadata) => void
  retryingFileId?: string | null
  relatedPages?: RelatedPage[]
  relatedLoading?: boolean
  relatedError?: boolean
  knowledge?: PageKnowledge
  onRetryKnowledge?: () => void
  onRetryRelated?: () => void
  onSelectPage?: (pageId: string, blockId?: string | null) => void
}

export function PageEditor({
  page,
  blocks,
  blocksLoading = false,
  highlightedBlockId = null,
  attachments,
  attachmentsLoading,
  attachmentsUploading,
  attachmentsError,
  busy,
  onUpdatePage,
  onCreateBlock,
  onUpdateBlock,
  onReorderBlocks,
  onDeleteBlock,
  onRequestMove,
  onRequestDelete,
  onUploadAttachment,
  onDeleteAttachment,
  onRetryAttachmentIndex,
  retryingFileId,
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

      {(knowledge || relatedPages.length > 0 || relatedLoading || relatedError) && (
        <aside className="related-content" aria-label="Related content">
          <div>
            <h3>Related content</h3>
            {relatedLoading && <span className="knowledge-status">Finding related content...</span>}
            {relatedError && <>
              <span className="knowledge-status">Related content could not be loaded.</span>
              <button type="button" className="knowledge-retry" onClick={onRetryRelated}>Try again</button>
            </>}
            {(knowledge?.status === 'failed' || knowledge?.status === 'stale') && (
              <div className="knowledge-recovery">
                <span className="knowledge-status">Some connections may be missing.</span>
                <button type="button" className="knowledge-retry" onClick={onRetryKnowledge}>Refresh</button>
              </div>
            )}
            {(knowledge?.status === 'pending' || knowledge?.status === 'indexing') && !relatedLoading && (
              <span className="knowledge-status">Connections are updating.</span>
            )}
          </div>
          {relatedPages.length > 0 && (
            <ul className="related-list">
              {relatedPages.map((related) => (
                <li key={related.page_id}>
                  <EvidenceResult
                    label={related.block_id ? 'Connected passage' : 'Related page'}
                    title={related.title}
                    preview={related.snippet}
                    onOpen={() => onSelectPage?.(related.page_id, related.block_id)}
                  />
                </li>
              ))}
            </ul>
          )}
          {!relatedLoading && !relatedError && relatedPages.length === 0 && (
            <span className="knowledge-status">No related content found.</span>
          )}
        </aside>
      )}

      <BlockEditor
        blocks={blocks}
        loading={blocksLoading}
        highlightedBlockId={highlightedBlockId}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={onUpdateBlock}
        onReorderBlocks={onReorderBlocks}
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
        onRetryIndex={onRetryAttachmentIndex}
        retryingFileId={retryingFileId}
      />
    </section>
  )
}
