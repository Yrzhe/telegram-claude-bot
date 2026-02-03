import { Calendar, Clock, Timer } from 'lucide-react'
import type { ScheduleItem as ScheduleItemType } from '../../api/types'

interface ScheduleCardProps {
  schedule: ScheduleItemType
}

export function ScheduleCard({ schedule }: ScheduleCardProps) {
  const getScheduleDescription = () => {
    switch (schedule.schedule_type) {
      case 'daily':
        return `Every day at ${schedule.time}`
      case 'weekly':
        const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        const weekdays = schedule.weekdays?.map((d) => days[d]).join(', ')
        return `${weekdays} at ${schedule.time}`
      case 'interval':
        const mins = schedule.interval_minutes || 0
        if (mins < 60) return `Every ${mins} minutes`
        if (mins < 1440) return `Every ${Math.floor(mins / 60)} hours`
        return `Every ${Math.floor(mins / 1440)} days`
      case 'once':
        return `Once at ${schedule.time}`
      default:
        return ''
    }
  }

  const formatTime = (dateStr?: string) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) {
      return `Today ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    } else if (days === 1) {
      return 'Yesterday'
    } else if (days < 7) {
      return date.toLocaleDateString([], { weekday: 'short' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const formatNextRun = (dateStr?: string) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    const now = new Date()
    const diff = date.getTime() - now.getTime()

    if (diff < 0) return 'Overdue'

    const mins = Math.floor(diff / 60000)
    const hours = Math.floor(mins / 60)
    const days = Math.floor(hours / 24)

    if (mins < 60) return `in ${mins}m`
    if (hours < 24) return `in ${hours}h`
    if (days === 1) return 'Tomorrow'
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const getIcon = () => {
    switch (schedule.schedule_type) {
      case 'daily':
        return <Calendar className="w-5 h-5 text-[var(--tg-theme-button-color)]" />
      case 'weekly':
        return <Calendar className="w-5 h-5 text-purple-500" />
      case 'interval':
        return <Timer className="w-5 h-5 text-orange-500" />
      default:
        return <Clock className="w-5 h-5 text-[var(--tg-theme-hint-color)]" />
    }
  }

  return (
    <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-lg p-3 mx-4 mb-2">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div className="text-[var(--tg-theme-text-color)] text-sm font-medium truncate">
              {schedule.name}
            </div>
            <div
              className={`px-2 py-0.5 text-xs rounded-full ${
                schedule.enabled
                  ? 'bg-green-500/20 text-green-500'
                  : 'bg-[var(--tg-theme-hint-color)]/20 text-[var(--tg-theme-hint-color)]'
              }`}
            >
              {schedule.enabled ? 'ON' : 'OFF'}
            </div>
          </div>
          <div className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
            {getScheduleDescription()}
          </div>
          <div className="flex items-center gap-4 text-xs text-[var(--tg-theme-hint-color)] mt-2">
            <span>Last: {formatTime(schedule.last_run)}</span>
            <span>({schedule.run_count} runs)</span>
          </div>
          {schedule.enabled && schedule.next_run && (
            <div className="text-xs text-[var(--tg-theme-button-color)] mt-1">
              Next: {formatNextRun(schedule.next_run)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
