import { describe, expect, it } from 'vitest'

import type { Page } from '../../types/api'
import { buildPageTree, getDescendantIds } from './tree'

const now = '2026-01-01T00:00:00.000000Z'

function makePage(input: Partial<Page> & Pick<Page, 'id' | 'workspace_id' | 'title'>): Page {
  return {
    id: input.id,
    workspace_id: input.workspace_id,
    parent_page_id: input.parent_page_id ?? null,
    title: input.title,
    position: input.position ?? 0,
    version: input.version ?? 1,
    created_at: input.created_at ?? now,
    updated_at: input.updated_at ?? now,
  }
}

describe('page tree helpers', () => {
  it('builds a nested tree sorted by position', () => {
    const pages: Page[] = [
      makePage({ id: 'root-b', workspace_id: 'w1', title: 'Root B', position: 1 }),
      makePage({ id: 'child-a2', workspace_id: 'w1', title: 'Child A2', parent_page_id: 'root-a', position: 1 }),
      makePage({ id: 'root-a', workspace_id: 'w1', title: 'Root A', position: 0 }),
      makePage({ id: 'child-a1', workspace_id: 'w1', title: 'Child A1', parent_page_id: 'root-a', position: 0 }),
    ]

    const tree = buildPageTree(pages)

    expect(tree).toHaveLength(2)
    expect(tree[0].page.id).toBe('root-a')
    expect(tree[0].children.map((node) => node.page.id)).toEqual(['child-a1', 'child-a2'])
    expect(tree[1].page.id).toBe('root-b')
  })

  it('collects descendants recursively', () => {
    const pages: Page[] = [
      makePage({ id: 'a', workspace_id: 'w1', title: 'A' }),
      makePage({ id: 'b', workspace_id: 'w1', title: 'B', parent_page_id: 'a' }),
      makePage({ id: 'c', workspace_id: 'w1', title: 'C', parent_page_id: 'b' }),
      makePage({ id: 'd', workspace_id: 'w1', title: 'D', parent_page_id: 'a' }),
    ]

    const descendants = getDescendantIds(pages, 'a')

    expect(descendants.has('b')).toBe(true)
    expect(descendants.has('c')).toBe(true)
    expect(descendants.has('d')).toBe(true)
    expect(descendants.has('a')).toBe(false)
  })
})
