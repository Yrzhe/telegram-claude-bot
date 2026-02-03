import { Folder, File, FileText, Image, FileCode, FileArchive, ChevronRight, Check } from 'lucide-react'
import type { FileItem as FileItemType } from '../../api/types'

interface FileItemProps {
  item: FileItemType
  isEditMode: boolean
  isSelected: boolean
  onClick: () => void
}

export function FileItem({ item, isEditMode, isSelected, onClick }: FileItemProps) {
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    if (days === 1) return 'Yesterday'
    if (days < 7) return date.toLocaleDateString([], { weekday: 'short' })
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const formatSize = (bytes?: number) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  const getIconConfig = () => {
    if (item.type === 'directory') {
      return { icon: Folder, colorClass: 'icon-blue' }
    }

    const ext = item.name.split('.').pop()?.toLowerCase() || ''

    switch (ext) {
      case 'txt': case 'md': case 'doc': case 'docx': case 'pdf':
        return { icon: FileText, colorClass: 'icon-orange' }
      case 'jpg': case 'jpeg': case 'png': case 'gif': case 'webp': case 'svg':
        return { icon: Image, colorClass: 'icon-green' }
      case 'js': case 'ts': case 'jsx': case 'tsx': case 'py': case 'json': case 'html': case 'css':
        return { icon: FileCode, colorClass: 'icon-purple' }
      case 'zip': case 'rar': case '7z': case 'tar': case 'gz':
        return { icon: FileArchive, colorClass: 'icon-orange' }
      default:
        return { icon: File, colorClass: 'icon-gray' }
    }
  }

  const { icon: Icon, colorClass } = getIconConfig()
  const isClickable = isEditMode || item.type === 'directory'

  return (
    <div
      onClick={onClick}
      className={`list-item ${isClickable ? 'cursor-pointer' : ''}`}
    >
      {/* Checkbox */}
      {isEditMode && (
        <div className={`checkbox ${isSelected ? 'checked' : ''}`}>
          <Check className="w-4 h-4" />
        </div>
      )}

      {/* Icon */}
      <div className={`list-item-icon ${colorClass}`}>
        <Icon className="w-5 h-5" />
      </div>

      {/* Content */}
      <div className="list-item-content">
        <div className="list-item-title">{item.name}</div>
        <div className="list-item-subtitle">
          {item.type === 'file' && item.size !== undefined && `${formatSize(item.size)} · `}
          {formatDate(item.modified)}
        </div>
      </div>

      {/* Accessory */}
      {item.type === 'directory' && !isEditMode && (
        <ChevronRight className="list-item-accessory w-5 h-5" />
      )}
    </div>
  )
}
