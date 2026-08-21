import { useState } from 'react'

import type { Block, Page } from '../../types/api'
import { BlockEditor } from '../blocks/BlockEditor'
import { InlineNotice } from '../ui/InlineNotice'

type PageEditorProps = {
  page: Page
  blocks: Block[]
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
  }) => Promise<void>
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
}

export function PageEditor({
  page,
  blocks,
  busy,
  errorMessage,
  onUpdatePage,
  onCreateBlock,
  onUpdateBlock,
  onDeleteBlock,
  onRequestMove,
  onRequestDelete,
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
    await onUpdatePage(page.id, {
      title: titleDraft.trim(),
      version: page.version,
    })
    setTitleStatus('saved')
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
          />
          <span className="save-status" aria-live="polite">{titleStatus === 'saving' ? 'Saving...' : titleStatus === 'unsaved' ? 'Unsaved' : 'Saved'}</span>
        </div>
        <div className="page-actions">
          <button type="button" className="button button-secondary" onClick={onRequestMove} disabled={busy}>Move page</button>
          <button type="button" className="button button-danger" onClick={onRequestDelete} disabled={busy}>Delete page</button>
        </div>
      </header>

      {errorMessage && <InlineNotice tone="error" message={errorMessage} />}

      <BlockEditor
        blocks={blocks}
        onCreateBlock={onCreateBlock}
        onUpdateBlock={onUpdateBlock}
        onDeleteBlock={async (block) => onDeleteBlock(block)}
      />
    </section>
  )
}
