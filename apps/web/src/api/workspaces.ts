import { apiRequest } from './client'
import type { Workspace, WorkspaceListResponse } from '../types/api'

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
