import { useEffect, useCallback } from 'react'
import { ChevronLeft, FolderPlus, RefreshCw, FolderOpen } from 'lucide-react'
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
    createDirectory,
    isEditMode,
    selectedItems,
    toggleSelection,
  } = useFilesStore()
  const { hapticFeedback } = useTelegram()

  useEffect(() => {
    loadFiles()
  }, [currentPath, loadFiles])

  const handleNavigate = useCallback((path: string) => {
    if (isEditMode) return
    hapticFeedback?.('light')
    loadFiles(path)
  }, [loadFiles, hapticFeedback, isEditMode])

  const handleBack = useCallback(() => {
    if (currentPath === '/' || isEditMode) return
    const parts = currentPath.split('/')
    parts.pop()
    const parentPath = parts.join('/') || '/'
    handleNavigate(parentPath)
  }, [currentPath, handleNavigate, isEditMode])

  const handleCreateDir = useCallback(async () => {
    const name = prompt('Enter folder name:')
    if (name) {
      await createDirectory(name)
    }
  }, [createDirectory])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadFiles()
  }, [loadFiles, hapticFeedback])

  const handleItemClick = useCallback((item: typeof items[0]) => {
    const fullPath = currentPath === '/' ? `/${item.name}` : `${currentPath}/${item.name}`

    if (isEditMode) {
      hapticFeedback?.('light')
      toggleSelection({
        path: fullPath,
        name: item.name,
        type: item.type,
      })
    } else if (item.type === 'directory') {
      handleNavigate(fullPath)
    }
  }, [isEditMode, currentPath, toggleSelection, handleNavigate, hapticFeedback])

  const isItemSelected = useCallback((itemName: string) => {
    const fullPath = currentPath === '/' ? `/${itemName}` : `${currentPath}/${itemName}`
    return selectedItems.some(s => s.path === fullPath)
  }, [selectedItems, currentPath])

  const sortedItems = [...items].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return (
    <div>
      {/* Path bar */}
      {!isEditMode && (
        <div className="card mb-4">
          <div className="list-item">
            {currentPath !== '/' && (
              <button onClick={handleBack} className="list-item-icon icon-blue">
                <ChevronLeft className="w-5 h-5" />
              </button>
            )}
            <div className="list-item-content" style={{ borderBottom: 'none' }}>
              <span className="list-item-title font-mono text-[15px]">{currentPath}</span>
            </div>
            <button onClick={handleCreateDir} className="list-item-icon icon-blue ml-2">
              <FolderPlus className="w-4 h-4" />
            </button>
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="list-item-icon icon-blue ml-2"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card mb-4 p-4">
          <p className="text-[15px] text-[var(--tg-theme-destructive-color)]">{error}</p>
        </div>
      )}

      {/* File list */}
      {isLoading && items.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="spinner" />
            <p className="empty-state-description mt-4">Loading...</p>
          </div>
        </div>
      ) : sortedItems.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">
              <FolderOpen />
            </div>
            <h3 className="empty-state-title">Empty folder</h3>
            <p className="empty-state-description">Upload files or create a folder</p>
          </div>
        </div>
      ) : (
        <div className="card">
          {sortedItems.map((item) => (
            <FileItem
              key={item.name}
              item={item}
              isEditMode={isEditMode}
              isSelected={isItemSelected(item.name)}
              onClick={() => handleItemClick(item)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
