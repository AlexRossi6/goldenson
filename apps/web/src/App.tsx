import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createBlock, deleteBlock, listBlocks, updateBlock } from './api/blocks'
import { deleteFile, listFiles, listPageFiles, uploadFile } from './api/files'
import { createPage, deletePage, getPage, listPages, updatePage } from './api/pages'
import { createWorkspace, listWorkspaces } from './api/workspaces'
import { PageEditor } from './components/pages/PageEditor'
import { MovePageDialog } from './components/pages/MovePageDialog'
import { PageTree } from './components/sidebar/PageTree'
import { FileArea } from './components/files/FileArea'
import { NewPageForm } from './components/sidebar/NewPageForm'
import { ConfirmDialog } from './components/ui/ConfirmDialog'
import { InlineNotice } from './components/ui/InlineNotice'
import { useUiStore } from './stores/ui'
import { ApiClientError, type Block, type FileMetadata, type Page } from './types/api'

function App() {
  const queryClient = useQueryClient()
  const [workspaceDraft, setWorkspaceDraft] = useState('')
  const [pageDraftTitle, setPageDraftTitle] = useState('')
  const [pageDraftParentId, setPageDraftParentId] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [moveDialogOpen, setMoveDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ kind: 'page' | 'block' | 'file'; page?: Page; block?: Block; file?: FileMetadata } | null>(null)

  const selectedPageId = useUiStore((state) => state.selectedPageId)
  const sidebarOpen = useUiStore((state) => state.sidebarOpen)
  const expandedPages = useUiStore((state) => state.expandedPages)
  const setSelectedPageId = useUiStore((state) => state.setSelectedPageId)
  const setSidebarOpen = useUiStore((state) => state.setSidebarOpen)
  const setPageExpanded = useUiStore((state) => state.setPageExpanded)
  const togglePageExpanded = useUiStore((state) => state.togglePageExpanded)

  const workspaceQuery = useQuery({
    queryKey: ['workspaces'],
    queryFn: listWorkspaces,
  })

  const workspace = workspaceQuery.data?.items[0] ?? null
  const workspaceId = workspace?.id ?? null

  const pagesQuery = useQuery({
    queryKey: ['pages', workspaceId],
    queryFn: () => listPages(workspaceId ?? ''),
    enabled: Boolean(workspaceId),
  })

  const pageList = useMemo(() => pagesQuery.data?.items ?? [], [pagesQuery.data?.items])

  const filesQuery = useQuery({
    queryKey: ['files', workspaceId],
    queryFn: () => listFiles(workspaceId ?? ''),
    enabled: Boolean(workspaceId),
  })

  const pageFilesQuery = useQuery({
    queryKey: ['page-files', selectedPageId],
    queryFn: () => listPageFiles(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
  })

  const pageQuery = useQuery({
    queryKey: ['page', selectedPageId],
    queryFn: () => getPage(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
  })

  const blocksQuery = useQuery({
    queryKey: ['blocks', selectedPageId],
    queryFn: () => listBlocks(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
  })

  const createWorkspaceMutation = useMutation({
    mutationFn: createWorkspace,
    onSuccess: async () => {
      setWorkspaceDraft('')
      await queryClient.invalidateQueries({ queryKey: ['workspaces'] })
    },
  })

  const createPageMutation = useMutation({
    mutationFn: ({
      workspaceId: nextWorkspaceId,
      title,
      parentId,
      position,
    }: {
      workspaceId: string
      title: string
      parentId: string | null
      position: number
    }) =>
      createPage(nextWorkspaceId, {
        title,
        parent_page_id: parentId,
        position,
      }),
    onSuccess: async (createdPage) => {
      await queryClient.invalidateQueries({ queryKey: ['pages', createdPage.workspace_id] })
      setSelectedPageId(createdPage.id)
      setPageExpanded(createdPage.id, true)
      setPageDraftTitle('')
      setPageDraftParentId(null)
    },
    onError: (error) => {
      setErrorMessage(error instanceof ApiClientError ? error.message : 'Failed to create page.')
    },
  })

  const updatePageMutation = useMutation({
    mutationFn: ({ pageId, payload }: { pageId: string; payload: Parameters<typeof updatePage>[1] }) =>
      updatePage(pageId, payload),
    onSuccess: async (updatedPage) => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ['pages', updatedPage.workspace_id] })
      await queryClient.invalidateQueries({ queryKey: ['page', updatedPage.id] })
    },
    onError: async (error) => {
      if (error instanceof ApiClientError && error.code === 'CONCURRENCY_CONFLICT') {
        setErrorMessage('This page changed elsewhere. Latest data has been reloaded.')
      } else {
        setErrorMessage('Failed to update page.')
      }
      await queryClient.invalidateQueries({ queryKey: ['page', selectedPageId] })
      await queryClient.invalidateQueries({ queryKey: ['pages', workspaceId] })
    },
  })

  const deletePageMutation = useMutation({
    mutationFn: deletePage,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['pages', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['files', workspaceId] })
      setSelectedPageId(null)
      setErrorMessage(null)
    },
    onError: (error) => {
      if (error instanceof ApiClientError) {
        setErrorMessage(error.message)
        return
      }
      setErrorMessage('Failed to delete page.')
    },
  })

  const createBlockMutation = useMutation({
    mutationFn: ({
      pageId,
      payload,
    }: {
      pageId: string
      payload: Parameters<typeof createBlock>[1]
    }) => createBlock(pageId, payload),
    onSuccess: async (createdBlock) => {
      await queryClient.invalidateQueries({ queryKey: ['blocks', createdBlock.page_id] })
      await queryClient.invalidateQueries({ queryKey: ['page', createdBlock.page_id] })
      setErrorMessage(null)
    },
    onError: (error) => {
      if (error instanceof ApiClientError) {
        setErrorMessage(error.message)
        return
      }
      setErrorMessage('Failed to create block.')
    },
  })

  const updateBlockMutation = useMutation({
    mutationFn: ({
      blockId,
      payload,
    }: {
      blockId: string
      payload: Parameters<typeof updateBlock>[1]
    }) => updateBlock(blockId, payload),
    onSuccess: async (updatedBlock) => {
      await queryClient.invalidateQueries({ queryKey: ['blocks', updatedBlock.page_id] })
      setErrorMessage(null)
    },
    onError: async (error) => {
      if (error instanceof ApiClientError && error.code === 'CONCURRENCY_CONFLICT') {
        setErrorMessage('This block changed elsewhere. Latest block data has been reloaded.')
      } else {
        setErrorMessage('Failed to update block.')
      }
      await queryClient.invalidateQueries({ queryKey: ['blocks', selectedPageId] })
    },
  })

  const deleteBlockMutation = useMutation({
    mutationFn: deleteBlock,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['blocks', selectedPageId] })
      setErrorMessage(null)
    },
    onError: (error) => {
      if (error instanceof ApiClientError) {
        setErrorMessage(error.message)
        return
      }
      setErrorMessage('Failed to delete block.')
    },
  })

  const uploadFileMutation = useMutation({
    mutationFn: ({ file, pageId }: { file: File; pageId: string | null }) => uploadFile(workspaceId ?? '', file, pageId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['files', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['page-files', selectedPageId] })
      setErrorMessage(null)
    },
    onError: (error) => setErrorMessage(error instanceof ApiClientError ? error.message : 'Could not add this file.'),
  })

  const deleteFileMutation = useMutation({
    mutationFn: deleteFile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['files', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['page-files', selectedPageId] })
      setDeleteTarget(null)
      setErrorMessage(null)
    },
    onError: (error) => setErrorMessage(error instanceof ApiClientError ? error.message : 'Could not delete this file.'),
  })

  useEffect(() => {
    if (!workspaceId) {
      return
    }

    if (pageList.length === 0) {
      setSelectedPageId(null)
      return
    }

    const selectedStillExists = pageList.some((page) => page.id === selectedPageId)
    if (!selectedStillExists) {
      setSelectedPageId(pageList[0].id)
    }
  }, [pageList, selectedPageId, setSelectedPageId, workspaceId])

  const selectedPage = pageQuery.data ?? null
  const selectedBlocks = useMemo(() => blocksQuery.data?.items ?? [], [blocksQuery.data?.items])
  const pageLookup = useMemo(() => new Map(pageList.map((page) => [page.id, page])), [pageList])

  const createRootPage = async () => {
    if (!workspaceId || !pageDraftTitle.trim()) {
      return
    }

    const nextPosition = pageList.filter((page) => page.parent_page_id === pageDraftParentId).length
    await createPageMutation.mutateAsync({
      workspaceId,
      title: pageDraftTitle.trim(),
      parentId: pageDraftParentId,
      position: nextPosition,
    })
  }

  const createChildPage = async (parentId: string | null) => {
    if (!workspaceId) {
      return
    }
    const baseTitle = parentId ? 'New child page' : 'New page'
    const siblingCount = pageList.filter((page) => page.parent_page_id === parentId).length
    await createPageMutation.mutateAsync({
      workspaceId,
      title: baseTitle,
      parentId,
      position: siblingCount,
    })
  }

  const removePage = async (page: Page) => {
    await deletePageMutation.mutateAsync(page.id)
  }

  const updateCurrentPage = async (
    pageId: string,
    payload: { version: number; title?: string; parent_page_id?: string | null; position?: number },
  ) => {
    await updatePageMutation.mutateAsync({ pageId, payload })
  }

  const createBlockForPage = async (payload: {
    type: string
    position: number
    content: Record<string, unknown>
  }) => {
    if (!selectedPageId) {
      return
    }
    await createBlockMutation.mutateAsync({ pageId: selectedPageId, payload })
  }

  const updateExistingBlock = async (
    blockId: string,
    payload: {
      version: number
      type?: string
      position?: number
      content?: Record<string, unknown>
    },
  ) => {
    await updateBlockMutation.mutateAsync({ blockId, payload })
  }

  const removeBlock = async (block: Block) => {
    await deleteBlockMutation.mutateAsync(block.id)
  }

  const requestDeletePage = (page: Page) => setDeleteTarget({ kind: 'page', page })
  const requestDeleteBlock = (block: Block) => setDeleteTarget({ kind: 'block', block })
  const requestDeleteFile = (file: FileMetadata) => setDeleteTarget({ kind: 'file', file })
  const confirmDelete = async () => {
    if (!deleteTarget) return
    if (deleteTarget.kind === 'page' && deleteTarget.page) await removePage(deleteTarget.page)
    if (deleteTarget.kind === 'block' && deleteTarget.block) await removeBlock(deleteTarget.block)
    if (deleteTarget.kind === 'file' && deleteTarget.file) await deleteFileMutation.mutateAsync(deleteTarget.file.id)
    setDeleteTarget(null)
  }

  const addFile = async (file: File) => {
    await uploadFileMutation.mutateAsync({ file, pageId: selectedPageId })
  }

  const moveCurrentPage = async (parentPageId: string | null, position: number) => {
    if (!selectedPage) return
    await updateCurrentPage(selectedPage.id, { version: selectedPage.version, parent_page_id: parentPageId, position })
    setMoveDialogOpen(false)
  }

  if (workspaceQuery.isLoading) {
    return <div className="loading-screen">Loading workspace...</div>
  }

  if (workspaceQuery.isError) {
    return (
      <div className="loading-screen">
        <InlineNotice tone="error" message="Could not load workspaces. Check backend connection." />
      </div>
    )
  }

  if (!workspace) {
    return (
      <div className="empty-workspace-screen">
        <article className="empty-card">
          <p className="eyebrow">Workspace setup</p>
          <h1>Create your first workspace</h1>
          <p className="lead">Start by creating a local workspace. Your pages and blocks persist via the REST API.</p>
          <div className="create-workspace-row">
            <input
              aria-label="Workspace name"
              placeholder="Workspace name"
              value={workspaceDraft}
              onChange={(event) => setWorkspaceDraft(event.target.value)}
            />
            <button
              type="button"
              className="button button-primary"
              onClick={() => createWorkspaceMutation.mutate(workspaceDraft.trim())}
              disabled={!workspaceDraft.trim() || createWorkspaceMutation.isPending}
            >
              {createWorkspaceMutation.isPending ? 'Creating...' : 'Create workspace'}
            </button>
          </div>
        </article>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className={`side-panel ${sidebarOpen ? 'is-open' : 'is-collapsed'}`} aria-label="Navigation panel">
        <div className="sidebar-header">
          <div>
            <p className="panel-label">Workspace</p>
            <h2>{workspace.name}</h2>
          </div>
          <button
            type="button"
            className="tree-icon"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? '⟨' : '⟩'}
          </button>
        </div>

        {sidebarOpen && (
          <>
            <NewPageForm
              pages={pageList}
              title={pageDraftTitle}
              parentId={pageDraftParentId}
              pending={createPageMutation.isPending}
              onTitleChange={setPageDraftTitle}
              onParentChange={setPageDraftParentId}
              onSubmit={() => void createRootPage()}
            />

            <PageTree
              pages={pageList}
              selectedPageId={selectedPageId}
              expandedPages={expandedPages}
              onToggleExpand={togglePageExpanded}
              onSelectPage={setSelectedPageId}
              onCreateChild={createChildPage}
              onDeletePage={requestDeletePage}
            />
            <FileArea
              title="Workspace files"
              files={filesQuery.data?.items ?? []}
              loading={filesQuery.isLoading}
              uploading={false}
              errorMessage={filesQuery.isError ? 'Files could not be loaded.' : null}
              onDelete={requestDeleteFile}
            />
          </>
        )}
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <p className="eyebrow">Local-first AI knowledge workspace</p>
          <h1>Workspace editor</h1>
          <p className="lead">
            Navigate pages, create nested content, edit blocks, and persist every change through the API.
          </p>
        </header>

        {errorMessage && <InlineNotice tone="error" message={errorMessage} />}

        {!selectedPageId && (
          <article className="empty-card">
            <h3>No page selected</h3>
            <p className="lead">Choose a page from the sidebar or create a new page to begin editing.</p>
          </article>
        )}

        {selectedPageId && pageQuery.isLoading && <p className="loading-copy">Loading selected page...</p>}

        {selectedPageId && pageQuery.isError && (
          <InlineNotice tone="error" message="Could not load page details. Try selecting the page again." />
        )}

        {selectedPage && (
          <PageEditor
            key={selectedPage.id}
            page={selectedPage}
            blocks={selectedBlocks}
            attachments={pageFilesQuery.data?.items ?? []}
            attachmentsLoading={pageFilesQuery.isLoading}
            attachmentsUploading={uploadFileMutation.isPending}
            attachmentsError={pageFilesQuery.isError ? 'Attachments could not be loaded.' : null}
            busy={updatePageMutation.isPending}
            errorMessage={errorMessage}
            onUpdatePage={updateCurrentPage}
            onCreateBlock={createBlockForPage}
            onUpdateBlock={updateExistingBlock}
            onDeleteBlock={requestDeleteBlock}
            onRequestMove={() => setMoveDialogOpen(true)}
            onRequestDelete={() => requestDeletePage(selectedPage)}
            onUploadAttachment={addFile}
            onDeleteAttachment={requestDeleteFile}
          />
        )}

        <footer className="bottom-meta">
          <span>Pages: {pageList.length}</span>
          <span>Selected: {selectedPageId ? pageLookup.get(selectedPageId)?.title ?? 'Unknown' : 'None'}</span>
        </footer>
      </main>
      {selectedPage && <MovePageDialog key={`${selectedPage.id}-${moveDialogOpen}`} page={selectedPage} pages={pageList} open={moveDialogOpen} busy={updatePageMutation.isPending} onCancel={() => setMoveDialogOpen(false)} onMove={moveCurrentPage} />}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget?.kind === 'page' ? 'Delete page?' : deleteTarget?.kind === 'file' ? 'Remove file?' : 'Delete block?'}
        message={deleteTarget?.kind === 'page' && deleteTarget.page ? `This will permanently delete “${deleteTarget.page.title}” and all of its child pages and blocks.` : deleteTarget?.kind === 'file' && deleteTarget.file ? `This will permanently remove “${deleteTarget.file.name}” from your workspace.` : 'This will permanently remove this piece of content.'}
        confirmLabel={deleteTarget?.kind === 'page' ? 'Delete page' : deleteTarget?.kind === 'file' ? 'Remove file' : 'Delete block'}
        busy={deletePageMutation.isPending || deleteBlockMutation.isPending || deleteFileMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  )
}

export default App
