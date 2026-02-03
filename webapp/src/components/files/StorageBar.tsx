interface StorageBarProps {
  usedBytes: number
  quotaBytes: number
}

export function StorageBar({ usedBytes, quotaBytes }: StorageBarProps) {
  const usedPercent = (usedBytes / quotaBytes) * 100
  const isWarning = usedPercent > 80
  const isDanger = usedPercent > 95

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(0)} KB`
    }
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  return (
    <div className="mx-4 mt-3 p-3 bg-[var(--tg-theme-bg-color)] rounded-xl shadow-sm">
      <div className="flex justify-between items-center mb-2">
        <span className="text-sm font-medium text-[var(--tg-theme-text-color)]">Storage</span>
        <span className="text-sm text-[var(--tg-theme-hint-color)]">
          {formatSize(usedBytes)} / {formatSize(quotaBytes)}
        </span>
      </div>
      <div className="h-2 bg-[var(--tg-theme-hint-color)]/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(usedPercent, 100)}%`,
            background: isDanger
              ? 'linear-gradient(90deg, #ef4444, #dc2626)'
              : isWarning
              ? 'linear-gradient(90deg, #f59e0b, #d97706)'
              : 'linear-gradient(90deg, #3b82f6, #06b6d4)'
          }}
        />
      </div>
      <div className="flex justify-between mt-1.5 text-xs text-[var(--tg-theme-hint-color)]">
        <span>{usedPercent.toFixed(1)}% used</span>
        <span>{formatSize(quotaBytes - usedBytes)} free</span>
      </div>
    </div>
  )
}
