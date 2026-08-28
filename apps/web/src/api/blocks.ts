import { apiRequest } from './client'
import type { Block, BlockListResponse } from '../types/api'

export type CreateBlockPayload = {
  type: string
  position: number
  content: Record<string, unknown>
}

export type UpdateBlockPayload = {
  version: number
  type?: string
  position?: number
  content?: Record<string, unknown>
}

export type ReorderBlocksPayload = {
  block_ids: string[]
  versions: Record<string, number>
}

export function listBlocks(pageId: string): Promise<BlockListResponse> {
  return apiRequest<BlockListResponse>(`/pages/${pageId}/blocks`)
}

export function createBlock(pageId: string, payload: CreateBlockPayload): Promise<Block> {
  return apiRequest<Block>(`/pages/${pageId}/blocks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateBlock(blockId: string, payload: UpdateBlockPayload): Promise<Block> {
  return apiRequest<Block>(`/blocks/${blockId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function reorderBlocks(pageId: string, payload: ReorderBlocksPayload): Promise<BlockListResponse> {
  return apiRequest<BlockListResponse>(`/pages/${pageId}/blocks/reorder`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteBlock(blockId: string): Promise<null> {
  return apiRequest<null>(`/blocks/${blockId}`, {
    method: 'DELETE',
  })
}
