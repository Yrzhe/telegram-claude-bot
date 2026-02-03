import { FolderOpen, HardDrive } from 'lucide-react'
import { StorageBar } from '../components/files/StorageBar'
import { FileList } from '../components/files/FileList'
import { useFilesStore } from '../stores/files'

export function FilesPage() {
  const storage = useFilesStore((state) => state.storage)

  return (
    <div className="flex flex-col h-full bg-[var(--tg-theme-secondary-bg-color)]">
      {/* Header */}
      <header className="bg-[var(--tg-theme-bg-color)] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
              Files
            </h1>
            <p className="text-xs text-[var(--tg-theme-hint-color)]">
              Manage your files
            </p>
          </div>
          {storage && (
            <div className="flex items-center gap-1.5 text-xs text-[var(--tg-theme-hint-color)]">
              <HardDrive className="w-3.5 h-3.5" />
              <span>{((storage.used_bytes / storage.quota_bytes) * 100).toFixed(0)}%</span>
            </div>
          )}
        </div>
      </header>

      {/* Storage bar */}
      {storage && (
        <StorageBar usedBytes={storage.used_bytes} quotaBytes={storage.quota_bytes} />
      )}

      {/* File list */}
      <FileList />
    </div>
  )
}
