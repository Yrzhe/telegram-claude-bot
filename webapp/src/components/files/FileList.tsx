import { useEffect, useCallback } from 'react'
import { ChevronLeft, FolderPlus, RefreshCw, FolderOpen, Loader2 } from 'lucide-react'
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
  }, [currentPath, loadFiles])

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
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Path navigation */}
      <div className="flex items-center gap-2 px-4 py-3 bg-[var(--tg-theme-bg-color)] mx-4 mt-3 rounded-xl shadow-sm">
        {currentPath !== '/' && (
          <button
            onClick={handleBack}
            className="w-8 h-8 rounded-lg bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center active:scale-95 transition-transform"
          >
            <ChevronLeft className="w-5 h-5 text-[var(--tg-theme-button-color)]" />
          </button>
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm text-[var(--tg-theme-text-color)] truncate block font-mono">
            {currentPath}
          </span>
        </div>
        <button
          onClick={handleCreateDir}
          className="w-8 h-8 rounded-lg bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center active:scale-95 transition-transform"
        >
          <FolderPlus className="w-4 h-4 text-[var(--tg-theme-button-color)]" />
        </button>
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="w-8 h-8 rounded-lg bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center active:scale-95 transition-transform"
        >
          <RefreshCw className={`w-4 h-4 text-[var(--tg-theme-button-color)] ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="mx-4 mt-3 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-500">
          {error}
        </div>
      )}

      {/* File list */}
      <div className="flex-1 overflow-auto px-4 py-3 pb-20">
        {isLoading && items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40">
            <Loader2 className="w-8 h-8 text-[var(--tg-theme-button-color)] animate-spin mb-3" />
            <span className="text-sm text-[var(--tg-theme-hint-color)]">Loading files...</span>
          </div>
        ) : sortedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 bg-[var(--tg-theme-bg-color)] rounded-xl">
            <div className="w-16 h-16 rounded-full bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center mb-3">
              <FolderOpen className="w-8 h-8 text-[var(--tg-theme-hint-color)]" />
            </div>
            <p className="text-sm font-medium text-[var(--tg-theme-text-color)]">Empty folder</p>
            <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
              Upload files or create a folder
            </p>
          </div>
        ) : (
          <div className="bg-[var(--tg-theme-bg-color)] rounded-xl overflow-hidden shadow-sm">
            {sortedItems.map((item, index) => (
              <FileItem
                key={item.name}
                item={item}
                currentPath={currentPath}
                onNavigate={handleNavigate}
                onDelete={handleDelete}
                isLast={index === sortedItems.length - 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
