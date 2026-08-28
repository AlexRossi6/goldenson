import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createBlock, deleteBlock, listBlocks, reorderBlocks, updateBlock } from './api/blocks'
import { deleteFile, getFileDownloadUrl, listFiles, listPageFiles, retryFileIndex, uploadFile } from './api/files'
import { createPage, deletePage, getPage, listPages, updatePage } from './api/pages'
import { createWorkspace, getWorkspaceIndexHealth, listWorkspaces, retryFailedWorkspaceIndexing } from './api/workspaces'
import { getPageKnowledge, getRelatedPages, reindexPage } from './api/knowledge'
import type { AgentWorkspaceChange } from './api/agent'
import { AssistantPanel } from './components/assistant/AssistantPanel'
import { PageEditor } from './components/pages/PageEditor'
import { MovePageDialog } from './components/pages/MovePageDialog'
import { PageTree } from './components/sidebar/PageTree'
import { FileArea } from './components/files/FileArea'
import { NewPageForm } from './components/sidebar/NewPageForm'
import { WorkspaceSearch } from './components/search/WorkspaceSearch'
import { IndexHealth } from './components/search/IndexHealth'
import { ConfirmDialog } from './components/ui/ConfirmDialog'
import { InlineNotice } from './components/ui/InlineNotice'
import { useUiStore } from './stores/ui'
import { ApiClientError, type Block, type FileMetadata, type Page, type RetrievedSource } from './types/api'

function App() {
  const queryClient = useQueryClient()
  const [workspaceDraft, setWorkspaceDraft] = useState('')
  const [pageDraftTitle, setPageDraftTitle] = useState('')
  const [pageDraftParentId, setPageDraftParentId] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [targetBlockId, setTargetBlockId] = useState<string | null>(null)
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
  const invalidateWorkspaceSearch = () => queryClient.invalidateQueries({
    queryKey: ['workspace-search', workspaceId],
  })
  const invalidateRelatedContent = () => queryClient.invalidateQueries({
    queryKey: ['related-pages'],
  })

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
    refetchInterval: (query) => query.state.data?.items.some(
      (file) => file.index_status === 'pending' || file.index_status === 'indexing',
    ) ? 1000 : false,
  })

  const indexHealthQuery = useQuery({
    queryKey: ['index-health', workspaceId],
    queryFn: () => getWorkspaceIndexHealth(workspaceId ?? ''),
    enabled: Boolean(workspaceId),
    refetchInterval: (query) => {
      const health = query.state.data
      return health && health.pages.indexing + health.files.indexing > 0 ? 1000 : false
    },
  })

  const pageFilesQuery = useQuery({
    queryKey: ['page-files', selectedPageId],
    queryFn: () => listPageFiles(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
    refetchInterval: (query) => query.state.data?.items.some(
      (file) => file.index_status === 'pending' || file.index_status === 'indexing',
    ) ? 1000 : false,
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

  const knowledgeQuery = useQuery({
    queryKey: ['page-knowledge', selectedPageId],
    queryFn: () => getPageKnowledge(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
    refetchInterval: (query) => ['pending', 'indexing'].includes(query.state.data?.status ?? '') ? 1000 : false,
  })

  const relatedQuery = useQuery({
    queryKey: ['related-pages', selectedPageId],
    queryFn: () => getRelatedPages(selectedPageId ?? ''),
    enabled: Boolean(selectedPageId),
    retry: false,
    refetchInterval: () => ['pending', 'indexing'].includes(knowledgeQuery.data?.status ?? '') ? 1000 : false,
  })

  useEffect(() => {
    if (!selectedPageId || !knowledgeQuery.data) return
    if (!['ready', 'failed', 'stale'].includes(knowledgeQuery.data.status)) return
    void queryClient.invalidateQueries({ queryKey: ['related-pages', selectedPageId] })
  }, [knowledgeQuery.data, queryClient, selectedPageId])

  const reindexMutation = useMutation({
    mutationFn: reindexPage,
    onSuccess: async (_, pageId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page-knowledge', pageId] }),
        queryClient.invalidateQueries({ queryKey: ['related-pages', pageId] }),
        queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] }),
      ])
    },
  })

  const retryFailedIndexingMutation = useMutation({
    mutationFn: () => retryFailedWorkspaceIndexing(workspaceId ?? ''),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['files', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['page-files'] }),
        queryClient.invalidateQueries({ queryKey: ['page-knowledge'] }),
        invalidateRelatedContent(),
      ])
    },
  })

  const retryFileIndexMutation = useMutation({
    mutationFn: retryFileIndex,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['files', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['page-files'] }),
        queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] }),
        invalidateRelatedContent(),
      ])
    },
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
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['pages', createdPage.workspace_id] }),
        queryClient.invalidateQueries({ queryKey: ['index-health', createdPage.workspace_id] }),
        invalidateWorkspaceSearch(),
        invalidateRelatedContent(),
      ])
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
      queryClient.setQueryData(['page-knowledge', updatedPage.id], { status: 'pending', concepts: [] })
      await queryClient.invalidateQueries({ queryKey: ['pages', updatedPage.workspace_id] })
      await queryClient.invalidateQueries({ queryKey: ['page', updatedPage.id] })
      await queryClient.invalidateQueries({ queryKey: ['page-knowledge', updatedPage.id] })
      await invalidateRelatedContent()
      await queryClient.invalidateQueries({ queryKey: ['index-health', updatedPage.workspace_id] })
      await invalidateWorkspaceSearch()
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
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
      await invalidateWorkspaceSearch()
      await invalidateRelatedContent()
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
      queryClient.setQueryData(['page-knowledge', createdBlock.page_id], { status: 'pending', concepts: [] })
      await queryClient.invalidateQueries({ queryKey: ['blocks', createdBlock.page_id] })
      await queryClient.invalidateQueries({ queryKey: ['page', createdBlock.page_id] })
      await queryClient.invalidateQueries({ queryKey: ['page-knowledge', createdBlock.page_id] })
      await invalidateRelatedContent()
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
      await invalidateWorkspaceSearch()
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
      queryClient.setQueryData(['page-knowledge', updatedBlock.page_id], { status: 'pending', concepts: [] })
      await queryClient.invalidateQueries({ queryKey: ['blocks', updatedBlock.page_id] })
      await queryClient.invalidateQueries({ queryKey: ['page-knowledge', updatedBlock.page_id] })
      await invalidateRelatedContent()
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
      await invalidateWorkspaceSearch()
      setErrorMessage(null)
    },
    onError: async (error) => {
      if (error instanceof ApiClientError && error.code === 'CONCURRENCY_CONFLICT') {
        setErrorMessage('This block changed elsewhere. Latest block data has been reloaded.')
      } else {
        setErrorMessage('Failed to update block.')
      }
      await queryClient.invalidateQueries({ queryKey: ['blocks', selectedPageId] })
      await queryClient.invalidateQueries({ queryKey: ['page-knowledge', selectedPageId] })
      await invalidateRelatedContent()
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
    },
  })

  const reorderBlocksMutation = useMutation({
    mutationFn: ({ pageId, blockIds, versions }: { pageId: string; blockIds: string[]; versions: Record<string, number> }) =>
      reorderBlocks(pageId, { block_ids: blockIds, versions }),
    onSuccess: async (result) => {
      const pageId = result.items[0]?.page_id
      if (!pageId) return
      queryClient.setQueryData(['page-knowledge', pageId], { status: 'pending', concepts: [] })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['blocks', pageId] }),
        queryClient.invalidateQueries({ queryKey: ['page-knowledge', pageId] }),
        queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] }),
        invalidateWorkspaceSearch(),
        invalidateRelatedContent(),
      ])
      setErrorMessage(null)
    },
    onError: async (error) => {
      if (error instanceof ApiClientError && error.code === 'CONCURRENCY_CONFLICT') {
        setErrorMessage('This block changed elsewhere. Latest block data has been reloaded.')
      } else {
        setErrorMessage('Failed to move block.')
      }
      await queryClient.invalidateQueries({ queryKey: ['blocks', selectedPageId] })
    },
  })

  const deleteBlockMutation = useMutation({
    mutationFn: deleteBlock,
    onSuccess: async () => {
      if (selectedPageId) queryClient.setQueryData(['page-knowledge', selectedPageId], { status: 'pending', concepts: [] })
      await queryClient.invalidateQueries({ queryKey: ['blocks', selectedPageId] })
      await queryClient.invalidateQueries({ queryKey: ['page-knowledge', selectedPageId] })
      await invalidateRelatedContent()
      await invalidateWorkspaceSearch()
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
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
      await invalidateWorkspaceSearch()
      await invalidateRelatedContent()
      setErrorMessage(null)
    },
    onError: (error) => setErrorMessage(error instanceof ApiClientError ? error.message : 'Could not add this file.'),
  })

  const deleteFileMutation = useMutation({
    mutationFn: deleteFile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['files', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['page-files', selectedPageId] })
      await queryClient.invalidateQueries({ queryKey: ['index-health', workspaceId] })
      await invalidateWorkspaceSearch()
      await invalidateRelatedContent()
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

  useEffect(() => {
    if (!targetBlockId || blocksQuery.isLoading) return
    const block = document.querySelector<HTMLElement>(`[data-block-id="${targetBlockId}"]`)
    if (!block) return
    block.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    const timer = window.setTimeout(() => setTargetBlockId(null), 2400)
    return () => window.clearTimeout(timer)
  }, [blocksQuery.data, blocksQuery.isLoading, targetBlockId])

  const selectedPage = pageQuery.data ?? null
  const selectedBlocks = useMemo(() => blocksQuery.data?.items ?? [], [blocksQuery.data?.items])
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
      throw new Error('Cannot create a block without a selected page.')
    }
    return await createBlockMutation.mutateAsync({ pageId: selectedPageId, payload })
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

  const selectPage = (pageId: string) => {
    setTargetBlockId(null)
    setSelectedPageId(pageId)
  }

  const openRelated = (pageId: string, blockId?: string | null) => {
    setTargetBlockId(blockId ?? null)
    setSelectedPageId(pageId)
  }

  const openSource = (source: RetrievedSource) => {
    if (source.page_id) {
      setTargetBlockId(source.block_id)
      setSelectedPageId(source.page_id)
      return
    }
    if (source.file_id) window.open(getFileDownloadUrl(source.file_id), '_blank', 'noopener,noreferrer')
  }

  const refreshAfterAgentMutation = async (change: AgentWorkspaceChange) => {
    const resultId = typeof change.result.id === 'string' ? change.result.id : null
    const resultPageId = typeof change.result.page_id === 'string' ? change.result.page_id : null
    const pageTools = new Set(['create_page', 'update_page', 'move_page', 'delete_page'])

    if (pageTools.has(change.tool_name)) {
      await queryClient.invalidateQueries({ queryKey: ['pages', workspaceId] })
      const affectedPageId = change.tool_name === 'delete_page' ? resultPageId : resultId
      if (affectedPageId) {
        if (change.tool_name === 'delete_page' && selectedPageId === affectedPageId) {
          setSelectedPageId(null)
        } else {
          await queryClient.invalidateQueries({ queryKey: ['page', affectedPageId] })
        }
      }
    }

    if (change.tool_name === 'create_task' && resultPageId) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['blocks', resultPageId] }),
        queryClient.invalidateQueries({ queryKey: ['page', resultPageId] }),
      ])
    }

    if (change.tool_name === 'create_file') {
      const invalidations = [
        queryClient.invalidateQueries({ queryKey: ['files', workspaceId] }),
      ]
      if (resultPageId) {
        invalidations.push(
          queryClient.invalidateQueries({ queryKey: ['page-files', resultPageId] }),
        )
      }
      await Promise.all(invalidations)
    }
    await invalidateWorkspaceSearch()
    await invalidateRelatedContent()
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
          <p className="lead">Start with a private workspace. Your pages and notes are saved automatically on this computer.</p>
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
            <WorkspaceSearch workspaceId={workspace.id} onOpenSource={openSource} />
            <IndexHealth
              health={indexHealthQuery.data}
              loading={indexHealthQuery.isLoading}
              retrying={retryFailedIndexingMutation.isPending}
              onRetryFailed={() => retryFailedIndexingMutation.mutate()}
            />
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
              onSelectPage={selectPage}
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
              onRetryIndex={(file) => retryFileIndexMutation.mutate(file.id)}
              retryingFileId={retryFileIndexMutation.isPending ? retryFileIndexMutation.variables : null}
            />
          </>
        )}
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">GoldenSon</p>
            <h1>{workspace.name}</h1>
          </div>
          <p className="lead">Private knowledge workspace</p>
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
            blocksLoading={blocksQuery.isLoading}
            highlightedBlockId={targetBlockId}
            attachments={pageFilesQuery.data?.items ?? []}
            attachmentsLoading={pageFilesQuery.isLoading}
            attachmentsUploading={uploadFileMutation.isPending}
            attachmentsError={pageFilesQuery.isError ? 'Attachments could not be loaded.' : null}
            busy={updatePageMutation.isPending}
            errorMessage={errorMessage}
            onUpdatePage={updateCurrentPage}
            onCreateBlock={createBlockForPage}
            onUpdateBlock={updateExistingBlock}
            onReorderBlocks={(blockIds, versions) => reorderBlocksMutation.mutateAsync({ pageId: selectedPage.id, blockIds, versions }).then(() => undefined)}
            onDeleteBlock={requestDeleteBlock}
            onRequestMove={() => setMoveDialogOpen(true)}
            onRequestDelete={() => requestDeletePage(selectedPage)}
            onUploadAttachment={addFile}
            onDeleteAttachment={requestDeleteFile}
            onRetryAttachmentIndex={(file) => retryFileIndexMutation.mutate(file.id)}
            retryingFileId={retryFileIndexMutation.isPending ? retryFileIndexMutation.variables : null}
            relatedPages={relatedQuery.data?.items ?? []}
            relatedLoading={relatedQuery.isLoading}
            relatedError={relatedQuery.isError}
            knowledge={knowledgeQuery.data}
            onRetryKnowledge={() => reindexMutation.mutate(selectedPage.id)}
            onRetryRelated={() => void relatedQuery.refetch()}
            onSelectPage={openRelated}
          />
        )}

      </main>
      <AssistantPanel
        workspaceId={workspace.id}
        onOpenSource={openSource}
        onWorkspaceChanged={(change) => void refreshAfterAgentMutation(change)}
      />
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
