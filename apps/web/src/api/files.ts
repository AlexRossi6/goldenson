import { apiRequest } from './client'
import type { FileListResponse, FileMetadata } from '../types/api'

export function listFiles(workspaceId: string): Promise<FileListResponse> {
  return apiRequest<FileListResponse>(`/workspaces/${workspaceId}/files`)
}

export function listPageFiles(pageId: string): Promise<FileListResponse> {
  return apiRequest<FileListResponse>(`/pages/${pageId}/files`)
}

export function getFile(fileId: string): Promise<FileMetadata> {
  return apiRequest<FileMetadata>(`/files/${fileId}`)
}

export function uploadFile(workspaceId: string, file: File, pageId: string | null): Promise<FileMetadata> {
  const form = new FormData()
  form.append('upload', file)
  if (pageId) form.append('page_id', pageId)
  return apiRequest<FileMetadata>(`/workspaces/${workspaceId}/files`, { method: 'POST', body: form })
}

export function getFileDownloadUrl(fileId: string): string {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api'
  return `${baseUrl}/files/${fileId}/download`
}

export function deleteFile(fileId: string): Promise<null> {
  return apiRequest<null>(`/files/${fileId}`, { method: 'DELETE' })
}

export function retryFileIndex(fileId: string): Promise<{ status: string }> {
  return apiRequest<{ status: string }>(`/files/${fileId}/index/retry`, { method: 'POST' })
}
