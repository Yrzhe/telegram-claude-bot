import { Loader2, CheckCircle2, XCircle, Ban, Clock } from 'lucide-react'
import type { TaskItem as TaskItemType } from '../../api/types'

interface TaskCardProps {
  task: TaskItemType
  onCancel?: () => void
}

export function TaskCard({ task, onCancel }: TaskCardProps) {
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    if (days === 1) return 'Yesterday'
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const getStatusIcon = () => {
    switch (task.status) {
      case 'running':
        return <Loader2 className="w-5 h-5 text-[var(--tg-theme-button-color)] animate-spin" />
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />
      case 'cancelled':
        return <Ban className="w-5 h-5 text-[var(--tg-theme-hint-color)]" />
      case 'pending':
        return <Clock className="w-5 h-5 text-yellow-500" />
      default:
        return null
    }
  }

  const getStatusText = () => {
    switch (task.status) {
      case 'running':
        return `Started ${formatTime(task.created_at)}`
      case 'completed':
        return `Completed ${formatTime(task.completed_at || task.created_at)}`
      case 'failed':
        return `Failed ${formatTime(task.completed_at || task.created_at)}`
      case 'cancelled':
        return `Cancelled ${formatTime(task.completed_at || task.created_at)}`
      case 'pending':
        return `Pending since ${formatTime(task.created_at)}`
      default:
        return formatTime(task.created_at)
    }
  }

  return (
    <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-lg p-3 mx-4 mb-2">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">{getStatusIcon()}</div>
        <div className="flex-1 min-w-0">
          <div className="text-[var(--tg-theme-text-color)] text-sm line-clamp-2">
            {task.description}
          </div>
          <div className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
            {getStatusText()}
          </div>
          {task.result_preview && task.status !== 'running' && (
            <div className="text-xs text-[var(--tg-theme-hint-color)] mt-2 line-clamp-2 italic">
              {task.result_preview}
            </div>
          )}
        </div>
        {task.status === 'running' && onCancel && (
          <button
            onClick={onCancel}
            className="px-3 py-1 text-xs text-red-500 border border-red-500 rounded hover:bg-red-500/10 transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}
