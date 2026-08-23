export type ApiErrorShape = {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

export type Workspace = {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export type Page = {
  id: string
  workspace_id: string
  parent_page_id: string | null
  title: string
  position: number
  version: number
  created_at: string
  updated_at: string
}

export type Block = {
  id: string
  page_id: string
  type: string
  position: number
  content: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

export type FileMetadata = {
  id: string
  workspace_id: string
  page_id: string | null
  name: string
  mime_type: string
  size: number
  index_status: 'pending' | 'indexing' | 'ready' | 'stale' | 'failed' | 'metadata_only'
  content_searchable: boolean
  indexed_at: string | null
  created_at: string
  updated_at: string
}

export type RetrievedSource = {
  kind: 'page' | 'block' | 'file'
  title: string
  snippet: string
  page_id: string | null
  block_id: string | null
  file_id: string | null
  score: number
}

export type RetrievalResult = {
  context: string
  sources: RetrievedSource[]
}

export type IndexCounts = {
  total: number
  ready: number
  indexing: number
  stale: number
  failed: number
}

export type WorkspaceIndexHealth = {
  status: 'ready' | 'indexing' | 'stale' | 'failed'
  pages: IndexCounts
  files: IndexCounts & { metadata_only: number }
}

export type WorkspaceListResponse = {
  items: Workspace[]
}

export type PageListResponse = {
  items: Page[]
}

export type BlockListResponse = {
  items: Block[]
}

export type FileListResponse = {
  items: FileMetadata[]
}

export class ApiClientError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = code
    this.details = details
  }
}
