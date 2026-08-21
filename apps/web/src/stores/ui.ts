import { create } from 'zustand'

type UiState = {
  selectedPageId: string | null
  sidebarOpen: boolean
  expandedPages: Record<string, boolean>
  setSelectedPageId: (pageId: string | null) => void
  setSidebarOpen: (isOpen: boolean) => void
  togglePageExpanded: (pageId: string) => void
  setPageExpanded: (pageId: string, expanded: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedPageId: null,
  sidebarOpen: true,
  expandedPages: {},
  setSelectedPageId: (pageId) => set({ selectedPageId: pageId }),
  setSidebarOpen: (isOpen) => set({ sidebarOpen: isOpen }),
  togglePageExpanded: (pageId) =>
    set((state) => ({
      expandedPages: {
        ...state.expandedPages,
        [pageId]: !state.expandedPages[pageId],
      },
    })),
  setPageExpanded: (pageId, expanded) =>
    set((state) => ({
      expandedPages: {
        ...state.expandedPages,
        [pageId]: expanded,
      },
    })),
}))
