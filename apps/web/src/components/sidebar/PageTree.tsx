import type { Page } from '../../types/api'
import { buildPageTree, type PageTreeNode } from '../pages/tree'

type PageTreeProps = {
  pages: Page[]
  selectedPageId: string | null
  expandedPages: Record<string, boolean>
  onToggleExpand: (pageId: string) => void
  onSelectPage: (pageId: string) => void
  onCreateChild: (parentId: string | null) => void
  onDeletePage: (page: Page) => void
}

type PageTreeItemProps = {
  node: PageTreeNode
  level: number
  selectedPageId: string | null
  expandedPages: Record<string, boolean>
  onToggleExpand: (pageId: string) => void
  onSelectPage: (pageId: string) => void
  onCreateChild: (parentId: string | null) => void
  onDeletePage: (page: Page) => void
}

function PageTreeItem({
  node,
  level,
  selectedPageId,
  expandedPages,
  onToggleExpand,
  onSelectPage,
  onCreateChild,
  onDeletePage,
}: PageTreeItemProps) {
  const hasChildren = node.children.length > 0
  const expanded = expandedPages[node.page.id] ?? true

  return (
    <li>
      <div className="tree-row" style={{ paddingLeft: `${level * 16}px` }}>
        {hasChildren ? (
          <button
            type="button"
            className="tree-expand"
            onClick={() => onToggleExpand(node.page.id)}
            aria-label={expanded ? 'Collapse page' : 'Expand page'}
          >
            {expanded ? '▾' : '▸'}
          </button>
        ) : (
          <span className="tree-spacer" aria-hidden="true" />
        )}

        <button
          type="button"
          className={`tree-page ${selectedPageId === node.page.id ? 'is-selected' : ''}`}
          onClick={() => onSelectPage(node.page.id)}
        >
          {node.page.title}
        </button>

        <button type="button" className="tree-icon" onClick={() => onCreateChild(node.page.id)}>
          +
        </button>
        <button type="button" className="tree-icon" onClick={() => onDeletePage(node.page)}>
          ×
        </button>
      </div>

      {hasChildren && expanded && (
        <ul className="tree-list" aria-label={`Children of ${node.page.title}`}>
          {node.children.map((child) => (
            <PageTreeItem
              key={child.page.id}
              node={child}
              level={level + 1}
              selectedPageId={selectedPageId}
              expandedPages={expandedPages}
              onToggleExpand={onToggleExpand}
              onSelectPage={onSelectPage}
              onCreateChild={onCreateChild}
              onDeletePage={onDeletePage}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

export function PageTree({
  pages,
  selectedPageId,
  expandedPages,
  onToggleExpand,
  onSelectPage,
  onCreateChild,
  onDeletePage,
}: PageTreeProps) {
  const tree = buildPageTree(pages)

  if (tree.length === 0) {
    return (
      <div className="empty-box">
        <p>This workspace has no pages yet.</p>
        <button type="button" className="button button-primary" onClick={() => onCreateChild(null)}>
          Create first page
        </button>
      </div>
    )
  }

  return (
    <ul className="tree-list" aria-label="Page tree">
      {tree.map((node) => (
        <PageTreeItem
          key={node.page.id}
          node={node}
          level={0}
          selectedPageId={selectedPageId}
          expandedPages={expandedPages}
          onToggleExpand={onToggleExpand}
          onSelectPage={onSelectPage}
          onCreateChild={onCreateChild}
          onDeletePage={onDeletePage}
        />
      ))}
    </ul>
  )
}
