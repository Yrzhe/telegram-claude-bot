import { useEffect, useCallback } from 'react'
import { RefreshCw, Clock, Play, Pause, Calendar, Timer, History } from 'lucide-react'
import { useSchedulesStore } from '../../stores/schedules'
import { useTelegram } from '../../hooks/useTelegram'
import type { ScheduleItem, ScheduleLog } from '../../api/types'

function ScheduleCard({ schedule }: { schedule: ScheduleItem }) {
  const getScheduleTypeLabel = () => {
    switch (schedule.schedule_type) {
      case 'once': return 'One-time'
      case 'daily': return 'Daily'
      case 'weekly': return 'Weekly'
      case 'interval': return `Every ${schedule.interval_minutes}m`
      default: return schedule.schedule_type
    }
  }

  const getScheduleIcon = () => {
    switch (schedule.schedule_type) {
      case 'once': return Calendar
      case 'interval': return Timer
      default: return Clock
    }
  }

  const Icon = getScheduleIcon()

  return (
    <div className="list-item">
      <div className={`list-item-icon ${schedule.enabled ? 'icon-orange' : 'icon-gray'}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="list-item-content">
        <div className="flex items-center gap-2">
          <span className="list-item-title">{schedule.name}</span>
          {schedule.enabled ? (
            <Play className="w-3 h-3 text-[#34c759]" />
          ) : (
            <Pause className="w-3 h-3 text-[#8e8e93]" />
          )}
        </div>
        <div className="list-item-subtitle">
          {getScheduleTypeLabel()}
          {schedule.time && ` · ${schedule.time}`}
          {schedule.next_run && ` · Next: ${schedule.next_run}`}
        </div>
      </div>
      <span className="list-item-value text-[13px]">
        {schedule.run_count}{schedule.max_runs ? `/${schedule.max_runs}` : ''} runs
      </span>
    </div>
  )
}

function LogItem({ log }: { log: ScheduleLog }) {
  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return timestamp
    }
  }

  const getActionColor = () => {
    switch (log.action) {
      case 'execute': return '#34c759'
      case 'create': return '#007aff'
      case 'delete': return '#ff3b30'
      case 'enable': return '#34c759'
      case 'disable': return '#ff9500'
      default: return '#8e8e93'
    }
  }

  return (
    <div className="list-item" style={{ minHeight: '44px' }}>
      <div className="list-item-content" style={{ padding: '8px 0' }}>
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-[var(--tg-theme-hint-color)]">
            {formatTime(log.timestamp)}
          </span>
          <span className="text-[13px] font-medium" style={{ color: getActionColor() }}>
            {log.action}
          </span>
          <span className="text-[13px] text-[var(--tg-theme-hint-color)] truncate">
            {log.task_id.slice(0, 8)}
          </span>
        </div>
      </div>
    </div>
  )
}

export function ScheduleList() {
  const { schedules, logs, isLoading, error, loadSchedules, loadLogs } = useSchedulesStore()
  const { hapticFeedback } = useTelegram()

  useEffect(() => {
    loadSchedules()
    loadLogs(10)
  }, [loadSchedules, loadLogs])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadSchedules()
    loadLogs(10)
  }, [loadSchedules, loadLogs, hapticFeedback])

  const activeSchedules = schedules.filter(s => s.enabled)
  const pausedSchedules = schedules.filter(s => !s.enabled)

  if (isLoading && schedules.length === 0) {
    return (
      <div className="card">
        <div className="empty-state">
          <div className="spinner" />
          <p className="empty-state-description mt-4">Loading...</p>
        </div>
      </div>
    )
  }

  if (schedules.length === 0) {
    return (
      <div className="card">
        <div className="empty-state">
          <div className="empty-state-icon">
            <Clock />
          </div>
          <h3 className="empty-state-title">No schedules</h3>
          <p className="empty-state-description">Create schedules via the bot</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Refresh button */}
      <div className="flex justify-end mb-3">
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="btn-text flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="card mb-4 p-4">
          <p className="text-[15px] text-[var(--tg-theme-destructive-color)]">{error}</p>
        </div>
      )}

      {/* Active schedules */}
      {activeSchedules.length > 0 && (
        <>
          <div className="section-header">Active</div>
          <div className="card mb-4">
            {activeSchedules.map(schedule => (
              <ScheduleCard key={schedule.task_id} schedule={schedule} />
            ))}
          </div>
        </>
      )}

      {/* Paused schedules */}
      {pausedSchedules.length > 0 && (
        <>
          <div className="section-header">Paused</div>
          <div className="card mb-4">
            {pausedSchedules.map(schedule => (
              <ScheduleCard key={schedule.task_id} schedule={schedule} />
            ))}
          </div>
        </>
      )}

      {/* Recent activity */}
      {logs.length > 0 && (
        <>
          <div className="section-header flex items-center gap-2">
            <History className="w-4 h-4" />
            Recent Activity
          </div>
          <div className="card">
            {logs.map((log, index) => (
              <LogItem key={`${log.timestamp}-${index}`} log={log} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
