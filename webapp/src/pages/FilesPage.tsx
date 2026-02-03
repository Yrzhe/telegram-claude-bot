import { useFilesStore } from '../stores/files'
import { FileList } from '../components/files/FileList'
import { FloatingActionBar } from '../components/files/FloatingActionBar'
import { Toast } from '../components/common/Toast'

export function FilesPage() {
  const isEditMode = useFilesStore((state) => state.isEditMode)
  const selectedItems = useFilesStore((state) => state.selectedItems)
  const setEditMode = useFilesStore((state) => state.setEditMode)
  const items = useFilesStore((state) => state.items)
  const storage = useFilesStore((state) => state.storage)

  const hasSelection = selectedItems.length > 0

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  return (
    <div className={`page scrollbar-hide overflow-auto ${hasSelection ? 'page-with-action-bar' : ''}`}>
      {/* Header */}
      <header className="page-header flex items-end justify-between">
        <div>
          <h1 className="page-title">Files</h1>
          {storage && (
            <p className="page-subtitle">
              {formatSize(storage.used_bytes)} of {formatSize(storage.quota_bytes)} used
            </p>
          )}
        </div>
        {items.length > 0 && (
          <button
            onClick={() => setEditMode(!isEditMode)}
            className="btn-text"
          >
            {isEditMode ? 'Done' : 'Edit'}
          </button>
        )}
      </header>

      {/* Storage progress */}
      {storage && !isEditMode && (
        <div className="progress-bar mt-2 mb-4">
          <div
            className="progress-bar-fill"
            style={{
              width: `${Math.min((storage.used_bytes / storage.quota_bytes) * 100, 100)}%`,
              background: storage.used_bytes / storage.quota_bytes > 0.9 ? '#ff3b30' : '#007aff'
            }}
          />
        </div>
      )}

      {/* Selection info */}
      {isEditMode && hasSelection && (
        <p className="page-subtitle mb-4">{selectedItems.length} selected</p>
      )}

      {/* File list */}
      <FileList />

      {/* Floating action bar */}
      {hasSelection && <FloatingActionBar />}

      {/* Toast */}
      <Toast />
    </div>
  )
}
