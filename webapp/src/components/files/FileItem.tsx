import { Folder, File, FileText, Image, FileCode, FileArchive, Trash2, Download } from 'lucide-react'
import type { FileItem as FileItemType } from '../../api/types'
import { api } from '../../api/client'

interface FileItemProps {
  item: FileItemType
  currentPath: string
  onNavigate: (path: string) => void
  onDelete: (path: string) => void
}

export function FileItem({ item, currentPath, onNavigate, onDelete }: FileItemProps) {
  const fullPath = currentPath === '/' ? `/${item.name}` : `${currentPath}/${item.name}`

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } else if (days === 1) {
      return 'Yesterday'
    } else if (days < 7) {
      return date.toLocaleDateString([], { weekday: 'short' })
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
    }
  }

  const formatSize = (bytes?: number) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  const getIcon = () => {
    if (item.type === 'directory') {
      return <Folder className="w-5 h-5 text-[var(--tg-theme-button-color)]" />
    }

    const ext = item.name.split('.').pop()?.toLowerCase() || ''
    const iconClass = "w-5 h-5 text-[var(--tg-theme-hint-color)]"

    switch (ext) {
      case 'txt':
      case 'md':
      case 'doc':
      case 'docx':
      case 'pdf':
        return <FileText className={iconClass} />
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
      case 'webp':
      case 'svg':
        return <Image className={iconClass} />
      case 'js':
      case 'ts':
      case 'jsx':
      case 'tsx':
      case 'py':
      case 'json':
      case 'html':
      case 'css':
        return <FileCode className={iconClass} />
      case 'zip':
      case 'rar':
      case '7z':
      case 'tar':
      case 'gz':
        return <FileArchive className={iconClass} />
      default:
        return <File className={iconClass} />
    }
  }

  const handleClick = () => {
    if (item.type === 'directory') {
      onNavigate(fullPath)
    }
  }

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    window.open(api.getDownloadUrl(fullPath), '_blank')
  }

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete(fullPath)
  }

  return (
    <div
      onClick={handleClick}
      className={`flex items-center px-4 py-3 border-b border-[var(--tg-theme-hint-color)]/10 ${
        item.type === 'directory' ? 'cursor-pointer active:bg-[var(--tg-theme-hint-color)]/5' : ''
      }`}
    >
      <div className="flex-shrink-0 mr-3">{getIcon()}</div>

      <div className="flex-1 min-w-0">
        <div className="text-[var(--tg-theme-text-color)] truncate">{item.name}</div>
        <div className="text-xs text-[var(--tg-theme-hint-color)] flex items-center gap-2">
          {item.type === 'file' && item.size && <span>{formatSize(item.size)}</span>}
          <span>{formatDate(item.modified)}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 ml-2">
        {item.type === 'file' && (
          <button
            onClick={handleDownload}
            className="p-2 text-[var(--tg-theme-hint-color)] hover:text-[var(--tg-theme-button-color)] transition-colors"
          >
            <Download className="w-4 h-4" />
          </button>
        )}
        <button
          onClick={handleDelete}
          className="p-2 text-[var(--tg-theme-hint-color)] hover:text-red-500 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
