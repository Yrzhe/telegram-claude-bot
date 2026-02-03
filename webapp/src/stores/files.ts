import { create } from 'zustand'
import type { FileItem, StorageInfo } from '../api/types'
import { api } from '../api/client'

interface FilesState {
  currentPath: string
  items: FileItem[]
  storage: StorageInfo | null
  isLoading: boolean
  error: string | null

  setPath: (path: string) => void
  loadFiles: (path?: string) => Promise<void>
  deleteFile: (path: string) => Promise<void>
  createDirectory: (name: string) => Promise<void>
  refreshStorage: () => Promise<void>
  updateStorage: (storage: Partial<StorageInfo>) => void
}

export const useFilesStore = create<FilesState>((set, get) => ({
  currentPath: '/',
  items: [],
  storage: null,
  isLoading: false,
  error: null,

  setPath: (path: string) => set({ currentPath: path }),

  loadFiles: async (path?: string) => {
    const targetPath = path ?? get().currentPath
    set({ isLoading: true, error: null })
    try {
      const response = await api.listFiles(targetPath)
      set({
        currentPath: response.path,
        items: response.items,
        storage: response.storage,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load files',
        isLoading: false,
      })
    }
  },

  deleteFile: async (path: string) => {
    try {
      await api.deleteFile(path)
      // Reload current directory
      await get().loadFiles()
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete file',
      })
    }
  },

  createDirectory: async (name: string) => {
    const { currentPath } = get()
    const fullPath = currentPath === '/' ? `/${name}` : `${currentPath}/${name}`
    try {
      await api.createDirectory(fullPath)
      await get().loadFiles()
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to create directory',
      })
    }
  },

  refreshStorage: async () => {
    try {
      const storage = await api.getStorageInfo()
      set({ storage })
    } catch (error) {
      console.error('Failed to refresh storage:', error)
    }
  },

  updateStorage: (storage: Partial<StorageInfo>) => {
    const current = get().storage
    if (current) {
      set({
        storage: {
          ...current,
          ...storage,
          used_percent: storage.used_bytes && storage.quota_bytes
            ? storage.used_bytes / storage.quota_bytes
            : current.used_percent,
        },
      })
    }
  },
}))
