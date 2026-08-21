import type { FormEvent } from 'react'

import type { Page } from '../../types/api'

type NewPageFormProps = {
  pages: Page[]
  title: string
  parentId: string | null
  pending: boolean
  onTitleChange: (title: string) => void
  onParentChange: (parentId: string | null) => void
  onSubmit: () => void
}

export function NewPageForm({ pages, title, parentId, pending, onTitleChange, onParentChange, onSubmit }: NewPageFormProps) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (title.trim() && !pending) onSubmit()
  }

  return (
    <form className="create-row" onSubmit={submit}>
      <input
        aria-label="New page title"
        placeholder="New page title"
        value={title}
        onChange={(event) => onTitleChange(event.target.value)}
      />
      <select aria-label="Optional parent page" value={parentId ?? ''} onChange={(event) => onParentChange(event.target.value || null)}>
        <option value="">Root page</option>
        {pages.map((page) => <option key={page.id} value={page.id}>{page.title}</option>)}
      </select>
      <button type="submit" className="button button-primary" disabled={!title.trim() || pending}>
        {pending ? 'Creating...' : 'Create page'}
      </button>
    </form>
  )
}
