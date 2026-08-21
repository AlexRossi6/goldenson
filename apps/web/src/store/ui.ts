import { create } from 'zustand'

type UiState = {
  autoRefresh: boolean
  setAutoRefresh: (value: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  autoRefresh: false,
  setAutoRefresh: (value: boolean) => set({ autoRefresh: value }),
}))
