interface StorageBarProps {
  usedBytes: number
  quotaBytes: number
}

export function StorageBar({ usedBytes, quotaBytes }: StorageBarProps) {
  const usedPercent = (usedBytes / quotaBytes) * 100
  const isWarning = usedPercent > 80
  const isDanger = usedPercent > 95

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  return (
    <div className="px-4 py-3 bg-[var(--tg-theme-secondary-bg-color)]">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-[var(--tg-theme-hint-color)]">Storage</span>
        <span className="text-[var(--tg-theme-text-color)]">
          {formatSize(usedBytes)} / {formatSize(quotaBytes)}
        </span>
      </div>
      <div className="h-2 bg-[var(--tg-theme-hint-color)]/20 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            isDanger
              ? 'bg-red-500'
              : isWarning
              ? 'bg-yellow-500'
              : 'bg-[var(--tg-theme-button-color)]'
          }`}
          style={{ width: `${Math.min(usedPercent, 100)}%` }}
        />
      </div>
      <div className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
        {usedPercent.toFixed(1)}% used
      </div>
    </div>
  )
}
