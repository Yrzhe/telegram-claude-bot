import { Download, Trash2 } from 'lucide-react'
import { useFilesStore } from '../../stores/files'
import { useTelegram } from '../../hooks/useTelegram'

export function FloatingActionBar() {
  const selectedItems = useFilesStore((state) => state.selectedItems)
  const batchDelete = useFilesStore((state) => state.batchDelete)
  const batchDownload = useFilesStore((state) => state.batchDownload)
  const { showConfirm, hapticFeedback } = useTelegram()

  const handleDownload = async () => {
    hapticFeedback?.('medium')
    await batchDownload()
  }

  const handleDelete = async () => {
    const count = selectedItems.length
    const message = count === 1
      ? `Delete "${selectedItems[0].name}"?`
      : `Delete ${count} items?`

    const confirmed = await showConfirm?.(message) ?? confirm(message)
    if (confirmed) {
      hapticFeedback?.('medium')
      await batchDelete()
    }
  }

  return (
    <div className="action-bar">
      <span className="text-[15px] text-[var(--tg-theme-hint-color)]">
        {selectedItems.length} selected
      </span>
      <div className="flex gap-3">
        <button onClick={handleDownload} className="btn btn-primary">
          <Download className="w-5 h-5" />
          <span>Download</span>
        </button>
        <button onClick={handleDelete} className="btn btn-destructive">
          <Trash2 className="w-5 h-5" />
          <span>Delete</span>
        </button>
      </div>
    </div>
  )
}
