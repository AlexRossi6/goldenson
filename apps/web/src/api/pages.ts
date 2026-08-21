import { apiRequest } from './client'
import type { Page, PageListResponse } from '../types/api'

export type CreatePagePayload = {
  title: string
  parent_page_id: string | null
  position: number
}

export type UpdatePagePayload = {
  version: number
  title?: string
  parent_page_id?: string | null
  position?: number
}

export function listPages(workspaceId: string): Promise<PageListResponse> {
  return apiRequest<PageListResponse>(`/workspaces/${workspaceId}/pages`)
}

export function createPage(workspaceId: string, payload: CreatePagePayload): Promise<Page> {
  return apiRequest<Page>(`/workspaces/${workspaceId}/pages`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getPage(pageId: string): Promise<Page> {
  return apiRequest<Page>(`/pages/${pageId}`)
}

export function updatePage(pageId: string, payload: UpdatePagePayload): Promise<Page> {
  return apiRequest<Page>(`/pages/${pageId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deletePage(pageId: string): Promise<null> {
  return apiRequest<null>(`/pages/${pageId}`, {
    method: 'DELETE',
  })
}
