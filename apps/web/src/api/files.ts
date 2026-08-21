import { apiRequest } from './client'
import type { FileListResponse, FileMetadata } from '../types/api'

export function listFiles(workspaceId: string): Promise<FileListResponse> {
  return apiRequest<FileListResponse>(`/workspaces/${workspaceId}/files`)
}

export function getFile(fileId: string): Promise<FileMetadata> {
  return apiRequest<FileMetadata>(`/files/${fileId}`)
}
