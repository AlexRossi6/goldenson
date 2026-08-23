import { apiRequest } from './client'
import type { RetrievalResult, Workspace, WorkspaceIndexHealth, WorkspaceListResponse } from '../types/api'

export function listWorkspaces(): Promise<WorkspaceListResponse> {
  return apiRequest<WorkspaceListResponse>('/workspaces')
}

export function createWorkspace(name: string): Promise<Workspace> {
  return apiRequest<Workspace>('/workspaces', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiRequest<Workspace>(`/workspaces/${workspaceId}`)
}

export function searchWorkspace(
  workspaceId: string,
  query: string,
  limit = 8,
): Promise<RetrievalResult> {
  const params = new URLSearchParams({ query, limit: String(limit) })
  return apiRequest<RetrievalResult>(`/workspaces/${workspaceId}/search?${params}`)
}

export function getWorkspaceIndexHealth(workspaceId: string): Promise<WorkspaceIndexHealth> {
  return apiRequest<WorkspaceIndexHealth>(`/workspaces/${workspaceId}/index-health`)
}

export function retryFailedWorkspaceIndexing(workspaceId: string): Promise<{ queued: number }> {
  return apiRequest<{ queued: number }>(`/workspaces/${workspaceId}/index/retry-failed`, { method: 'POST' })
}
