import type { Page } from '../../types/api'

export type PageTreeNode = {
  page: Page
  children: PageTreeNode[]
}

export function buildPageTree(pages: Page[]): PageTreeNode[] {
  const byId = new Map<string, PageTreeNode>()
  const roots: PageTreeNode[] = []

  for (const page of pages) {
    byId.set(page.id, { page, children: [] })
  }

  for (const page of pages) {
    const node = byId.get(page.id)
    if (!node) {
      continue
    }

    if (page.parent_page_id) {
      const parent = byId.get(page.parent_page_id)
      if (parent) {
        parent.children.push(node)
        continue
      }
    }

    roots.push(node)
  }

  const sortNodes = (items: PageTreeNode[]): void => {
    items.sort((a, b) => {
      if (a.page.position !== b.page.position) {
        return a.page.position - b.page.position
      }
      return a.page.created_at.localeCompare(b.page.created_at)
    })

    for (const item of items) {
      sortNodes(item.children)
    }
  }

  sortNodes(roots)
  return roots
}

export function getDescendantIds(pages: Page[], pageId: string): Set<string> {
  const childrenByParent = new Map<string, string[]>()

  for (const page of pages) {
    if (!page.parent_page_id) {
      continue
    }
    const children = childrenByParent.get(page.parent_page_id) ?? []
    children.push(page.id)
    childrenByParent.set(page.parent_page_id, children)
  }

  const descendants = new Set<string>()
  const stack: string[] = [pageId]

  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) {
      continue
    }

    const children = childrenByParent.get(current) ?? []
    for (const childId of children) {
      if (!descendants.has(childId)) {
        descendants.add(childId)
        stack.push(childId)
      }
    }
  }

  return descendants
}
