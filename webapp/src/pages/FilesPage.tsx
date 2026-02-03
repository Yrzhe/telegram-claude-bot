import { Header } from '../components/layout/Header'
import { StorageBar } from '../components/files/StorageBar'
import { FileList } from '../components/files/FileList'
import { useFilesStore } from '../stores/files'

export function FilesPage() {
  const storage = useFilesStore((state) => state.storage)

  return (
    <div className="flex flex-col h-full">
      <Header title="Files" showStorage />
      {storage && (
        <StorageBar usedBytes={storage.used_bytes} quotaBytes={storage.quota_bytes} />
      )}
      <FileList />
    </div>
  )
}
