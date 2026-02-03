import { Play, Plus, Edit3, Trash2, Power, PowerOff } from 'lucide-react'
import type { ScheduleLog } from '../../api/types'

interface ExecutionLogProps {
  log: ScheduleLog
}

export function ExecutionLog({ log }: ExecutionLogProps) {
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const getIcon = () => {
    switch (log.action) {
      case 'execute':
        return <Play className="w-3 h-3 text-green-500" />
      case 'create':
        return <Plus className="w-3 h-3 text-[var(--tg-theme-button-color)]" />
      case 'update':
        return <Edit3 className="w-3 h-3 text-yellow-500" />
      case 'delete':
        return <Trash2 className="w-3 h-3 text-red-500" />
      case 'enable':
        return <Power className="w-3 h-3 text-green-500" />
      case 'disable':
        return <PowerOff className="w-3 h-3 text-[var(--tg-theme-hint-color)]" />
      default:
        return null
    }
  }

  const getActionText = () => {
    switch (log.action) {
      case 'execute':
        return 'executed'
      case 'create':
        return 'created'
      case 'update':
        return 'updated'
      case 'delete':
        return 'deleted'
      case 'enable':
        return 'enabled'
      case 'disable':
        return 'disabled'
      default:
        return log.action
    }
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--tg-theme-hint-color)]/10 last:border-b-0">
      <div className="flex-shrink-0">{getIcon()}</div>
      <div className="flex-1 text-xs">
        <span className="text-[var(--tg-theme-hint-color)]">{formatTime(log.timestamp)}</span>
        <span className="mx-1 text-[var(--tg-theme-text-color)]">{log.task_id}</span>
        <span className="text-[var(--tg-theme-hint-color)]">{getActionText()}</span>
      </div>
      <div className="text-xs text-[var(--tg-theme-hint-color)]">
        {formatDate(log.timestamp)}
      </div>
    </div>
  )
}
