import { create } from 'zustand'
import type { FileItem, StorageInfo } from '../api/types'
import { api } from '../api/client'

interface SelectedItem {
  path: string
  name: string
  type: 'file' | 'directory'
}

interface FilesState {
  currentPath: string
  items: FileItem[]
  storage: StorageInfo | null
  isLoading: boolean
  error: string | null

  // Edit mode
  isEditMode: boolean
  selectedItems: SelectedItem[]

  // Toast state
  toastMessage: string | null
  toastVisible: boolean

  // Actions
  setPath: (path: string) => void
  loadFiles: (path?: string) => Promise<void>
  deleteFile: (path: string) => Promise<void>
  createDirectory: (name: string) => Promise<void>
  refreshStorage: () => Promise<void>
  updateStorage: (storage: Partial<StorageInfo>) => void

  // Edit mode actions
  setEditMode: (isEdit: boolean) => void
  toggleSelection: (item: SelectedItem) => void
  selectAll: () => void
  clearSelection: () => void

  // Batch actions
  batchDelete: () => Promise<void>
  batchDownload: () => Promise<void>

  // Toast actions
  showToast: (message: string) => void
  hideToast: () => void
}

export const useFilesStore = create<FilesState>((set, get) => ({
  currentPath: '/',
  items: [],
  storage: null,
  isLoading: false,
  error: null,

  isEditMode: false,
  selectedItems: [],

  toastMessage: null,
  toastVisible: false,

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
        // Clear selection when navigating
        selectedItems: [],
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

  // Edit mode actions
  setEditMode: (isEdit: boolean) => {
    set({
      isEditMode: isEdit,
      selectedItems: isEdit ? get().selectedItems : [],
    })
  },

  toggleSelection: (item: SelectedItem) => {
    const { selectedItems } = get()
    const exists = selectedItems.find(s => s.path === item.path)
    if (exists) {
      set({ selectedItems: selectedItems.filter(s => s.path !== item.path) })
    } else {
      set({ selectedItems: [...selectedItems, item] })
    }
  },

  selectAll: () => {
    const { items, currentPath } = get()
    const allItems: SelectedItem[] = items.map(item => ({
      path: currentPath === '/' ? `/${item.name}` : `${currentPath}/${item.name}`,
      name: item.name,
      type: item.type,
    }))
    set({ selectedItems: allItems })
  },

  clearSelection: () => {
    set({ selectedItems: [] })
  },

  // Batch actions
  batchDelete: async () => {
    const { selectedItems, loadFiles, showToast, setEditMode } = get()
    if (selectedItems.length === 0) return

    try {
      showToast('Deleting...')
      const paths = selectedItems.map(item => item.path)
      await api.batchDelete(paths)
      await loadFiles()
      setEditMode(false)
      showToast('Deleted successfully')
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete files',
      })
      showToast('Delete failed')
    }
  },

  batchDownload: async () => {
    const { selectedItems, showToast, setEditMode } = get()
    if (selectedItems.length === 0) return

    try {
      showToast('Sending to Telegram...')
      const paths = selectedItems.map(item => item.path)
      await api.batchDownload(paths)
      setEditMode(false)
      showToast('Sent to Telegram')
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to send files',
      })
      showToast('Send failed')
    }
  },

  // Toast actions
  showToast: (message: string) => {
    set({ toastMessage: message, toastVisible: true })
    setTimeout(() => {
      set({ toastVisible: false })
      setTimeout(() => set({ toastMessage: null }), 200)
    }, 2000)
  },

  hideToast: () => {
    set({ toastVisible: false })
    setTimeout(() => set({ toastMessage: null }), 200)
  },
}))
