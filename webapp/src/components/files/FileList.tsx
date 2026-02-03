import { useEffect, useCallback } from 'react'
import { ChevronLeft, FolderPlus, RefreshCw } from 'lucide-react'
import { useFilesStore } from '../../stores/files'
import { useTelegram } from '../../hooks/useTelegram'
import { FileItem } from './FileItem'

export function FileList() {
  const {
    currentPath,
    items,
    isLoading,
    error,
    loadFiles,
    deleteFile,
    createDirectory,
  } = useFilesStore()
  const { showConfirm, hapticFeedback } = useTelegram()

  useEffect(() => {
    loadFiles()
  }, [currentPath])

  const handleNavigate = useCallback((path: string) => {
    hapticFeedback?.('light')
    loadFiles(path)
  }, [loadFiles, hapticFeedback])

  const handleBack = useCallback(() => {
    if (currentPath === '/') return
    const parts = currentPath.split('/')
    parts.pop()
    const parentPath = parts.join('/') || '/'
    handleNavigate(parentPath)
  }, [currentPath, handleNavigate])

  const handleDelete = useCallback(async (path: string) => {
    const confirmed = await showConfirm?.(`Delete ${path.split('/').pop()}?`) ?? confirm(`Delete ${path.split('/').pop()}?`)
    if (confirmed) {
      hapticFeedback?.('medium')
      await deleteFile(path)
    }
  }, [deleteFile, showConfirm, hapticFeedback])

  const handleCreateDir = useCallback(async () => {
    const name = prompt('Enter directory name:')
    if (name) {
      await createDirectory(name)
    }
  }, [createDirectory])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadFiles()
  }, [loadFiles, hapticFeedback])

  // Sort items: directories first, then files, alphabetically
  const sortedItems = [...items].sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === 'directory' ? -1 : 1
    }
    return a.name.localeCompare(b.name)
  })

  return (
    <div className="flex flex-col h-full">
      {/* Path navigation */}
      <div className="flex items-center gap-2 px-4 py-2 bg-[var(--tg-theme-secondary-bg-color)] border-b border-[var(--tg-theme-hint-color)]/10">
        {currentPath !== '/' && (
          <button
            onClick={handleBack}
            className="p-1 text-[var(--tg-theme-button-color)]"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        )}
        <span className="flex-1 text-sm text-[var(--tg-theme-text-color)] truncate font-mono">
          {currentPath}
        </span>
        <button
          onClick={handleCreateDir}
          className="p-1 text-[var(--tg-theme-button-color)]"
        >
          <FolderPlus className="w-5 h-5" />
        </button>
        <button
          onClick={handleRefresh}
          className="p-1 text-[var(--tg-theme-button-color)]"
          disabled={isLoading}
        >
          <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 text-red-500 text-sm">
          {error}
        </div>
      )}

      {/* File list */}
      <div className="flex-1 overflow-auto">
        {isLoading && items.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            Loading...
          </div>
        ) : sortedItems.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            Empty directory
          </div>
        ) : (
          sortedItems.map((item) => (
            <FileItem
              key={item.name}
              item={item}
              currentPath={currentPath}
              onNavigate={handleNavigate}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>
    </div>
  )
}
