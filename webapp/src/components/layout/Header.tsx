import { useFilesStore } from '../../stores/files'

interface HeaderProps {
  title: string
  showStorage?: boolean
}

export function Header({ title, showStorage = false }: HeaderProps) {
  const storage = useFilesStore((state) => state.storage)

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  return (
    <header className="sticky top-0 bg-[var(--tg-theme-bg-color)] border-b border-[var(--tg-theme-hint-color)]/20 z-10">
      <div className="flex items-center justify-between px-4 h-12">
        <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
          {title}
        </h1>
        {showStorage && storage && (
          <span className="text-sm text-[var(--tg-theme-hint-color)]">
            {formatSize(storage.used_bytes)}
          </span>
        )}
      </div>
    </header>
  )
}
