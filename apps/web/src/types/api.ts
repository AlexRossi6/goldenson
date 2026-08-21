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
  storage_key: string
  mime_type: string
  size: number
  created_at: string
  updated_at: string
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
