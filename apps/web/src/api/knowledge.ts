import { apiRequest } from './client'

export type RelatedPage = {
  page_id: string
  title: string
  snippet: string
  block_id: string | null
}
export type PageKnowledge = { status: 'pending' | 'indexing' | 'stale' | 'ready' | 'failed'; concepts: string[]; indexed_at?: string }

export function getRelatedPages(pageId: string): Promise<{ items: RelatedPage[] }> {
  return apiRequest<{ items: RelatedPage[] }>(`/pages/${pageId}/related`, {
    signal: AbortSignal.timeout(10000),
  })
}

export function getPageKnowledge(pageId: string): Promise<PageKnowledge> {
  return apiRequest<PageKnowledge>(`/pages/${pageId}/knowledge`)
}

export function reindexPage(pageId: string): Promise<{ status: string }> {
  return apiRequest<{ status: string }>(`/pages/${pageId}/knowledge/reindex`, { method: 'POST' })
}