import { Folder, File, FileText, Image, FileCode, FileArchive, Trash2, Download, ChevronRight } from 'lucide-react'
import type { FileItem as FileItemType } from '../../api/types'
import { api } from '../../api/client'

interface FileItemProps {
  item: FileItemType
  currentPath: string
  onNavigate: (path: string) => void
  onDelete: (path: string) => void
  isLast?: boolean
}

export function FileItem({ item, currentPath, onNavigate, onDelete, isLast = false }: FileItemProps) {
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
      return (
        <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
          <Folder className="w-5 h-5 text-blue-500" />
        </div>
      )
    }

    const ext = item.name.split('.').pop()?.toLowerCase() || ''

    const getIconByExt = () => {
      switch (ext) {
        case 'txt':
        case 'md':
        case 'doc':
        case 'docx':
        case 'pdf':
          return { icon: FileText, color: 'text-orange-500', bg: 'bg-orange-500/10' }
        case 'jpg':
        case 'jpeg':
        case 'png':
        case 'gif':
        case 'webp':
        case 'svg':
          return { icon: Image, color: 'text-green-500', bg: 'bg-green-500/10' }
        case 'js':
        case 'ts':
        case 'jsx':
        case 'tsx':
        case 'py':
        case 'json':
        case 'html':
        case 'css':
          return { icon: FileCode, color: 'text-purple-500', bg: 'bg-purple-500/10' }
        case 'zip':
        case 'rar':
        case '7z':
        case 'tar':
        case 'gz':
          return { icon: FileArchive, color: 'text-yellow-500', bg: 'bg-yellow-500/10' }
        default:
          return { icon: File, color: 'text-gray-500', bg: 'bg-gray-500/10' }
      }
    }

    const { icon: Icon, color, bg } = getIconByExt()
    return (
      <div className={`w-10 h-10 rounded-lg ${bg} flex items-center justify-center`}>
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
    )
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
      className={`flex items-center px-3 py-3 ${
        !isLast ? 'border-b border-[var(--tg-theme-hint-color)]/10' : ''
      } ${
        item.type === 'directory' ? 'cursor-pointer active:bg-[var(--tg-theme-hint-color)]/5' : ''
      } transition-colors`}
    >
      <div className="flex-shrink-0 mr-3">{getIcon()}</div>

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-[var(--tg-theme-text-color)] truncate">
          {item.name}
        </div>
        <div className="text-xs text-[var(--tg-theme-hint-color)] flex items-center gap-2 mt-0.5">
          {item.type === 'file' && item.size !== undefined && (
            <>
              <span>{formatSize(item.size)}</span>
              <span>·</span>
            </>
          )}
          <span>{formatDate(item.modified)}</span>
        </div>
      </div>

      <div className="flex items-center gap-1 ml-2">
        {item.type === 'file' && (
          <button
            onClick={handleDownload}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--tg-theme-hint-color)] active:bg-[var(--tg-theme-hint-color)]/10 transition-colors"
          >
            <Download className="w-4 h-4" />
          </button>
        )}
        <button
          onClick={handleDelete}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--tg-theme-hint-color)] active:bg-red-500/10 active:text-red-500 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
        {item.type === 'directory' && (
          <ChevronRight className="w-4 h-4 text-[var(--tg-theme-hint-color)]" />
        )}
      </div>
    </div>
  )
}
