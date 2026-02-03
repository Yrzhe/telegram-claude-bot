import { useEffect, useCallback } from 'react'
import { RefreshCw, History, Clock, Loader2, AlertCircle, Play, Pause, Calendar, Timer } from 'lucide-react'
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
    <div className="bg-[var(--tg-theme-bg-color)] rounded-xl p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
          schedule.enabled ? 'bg-orange-500/10' : 'bg-gray-500/10'
        }`}>
          <Icon className={`w-5 h-5 ${schedule.enabled ? 'text-orange-500' : 'text-gray-500'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-[var(--tg-theme-text-color)]">
              {schedule.name}
            </span>
            {schedule.enabled ? (
              <Play className="w-3 h-3 text-green-500" />
            ) : (
              <Pause className="w-3 h-3 text-gray-500" />
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--tg-theme-hint-color)]">
            <span className="px-1.5 py-0.5 rounded bg-[var(--tg-theme-secondary-bg-color)]">
              {getScheduleTypeLabel()}
            </span>
            {schedule.time && (
              <span>{schedule.time}</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-2 text-xs text-[var(--tg-theme-hint-color)]">
            <span>Runs: {schedule.run_count}{schedule.max_runs ? `/${schedule.max_runs}` : ''}</span>
            {schedule.next_run && (
              <span>Next: {schedule.next_run}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ExecutionLogItem({ log }: { log: ScheduleLog }) {
  const formatTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp)
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return timestamp
    }
  }

  const getActionColor = () => {
    switch (log.action) {
      case 'execute': return 'text-green-500'
      case 'create': return 'text-blue-500'
      case 'delete': return 'text-red-500'
      case 'enable': return 'text-green-500'
      case 'disable': return 'text-orange-500'
      default: return 'text-[var(--tg-theme-hint-color)]'
    }
  }

  return (
    <div className="flex items-center gap-3 px-3 py-2 border-b border-[var(--tg-theme-hint-color)]/10 last:border-0">
      <span className="text-xs text-[var(--tg-theme-hint-color)]">
        {formatTime(log.timestamp)}
      </span>
      <span className={`text-xs font-medium ${getActionColor()}`}>
        {log.action}
      </span>
      <span className="text-xs text-[var(--tg-theme-hint-color)] truncate flex-1">
        {log.task_id.slice(0, 8)}
      </span>
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

  const activeSchedules = schedules.filter((s) => s.enabled)
  const inactiveSchedules = schedules.filter((s) => !s.enabled)

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Stats card */}
      <div className="mx-4 mt-4 p-4 bg-[var(--tg-theme-bg-color)] rounded-xl shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex gap-4">
            <div className="text-center">
              <div className="text-xl font-bold text-orange-500">{activeSchedules.length}</div>
              <div className="text-xs text-[var(--tg-theme-hint-color)]">Active</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-[var(--tg-theme-hint-color)]">{inactiveSchedules.length}</div>
              <div className="text-xs text-[var(--tg-theme-hint-color)]">Paused</div>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="w-10 h-10 rounded-full bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center active:scale-95 transition-transform"
          >
            <RefreshCw className={`w-5 h-5 text-[var(--tg-theme-button-color)] ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="mx-4 mt-3 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span className="text-sm text-red-500">{error}</span>
        </div>
      )}

      {/* Schedule list */}
      <div className="flex-1 overflow-auto px-4 py-4 pb-20">
        {isLoading && schedules.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40">
            <Loader2 className="w-8 h-8 text-[var(--tg-theme-button-color)] animate-spin mb-3" />
            <span className="text-sm text-[var(--tg-theme-hint-color)]">Loading schedules...</span>
          </div>
        ) : schedules.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 bg-[var(--tg-theme-bg-color)] rounded-xl">
            <div className="w-16 h-16 rounded-full bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center mb-3">
              <Clock className="w-8 h-8 text-[var(--tg-theme-hint-color)]" />
            </div>
            <p className="text-sm font-medium text-[var(--tg-theme-text-color)]">No scheduled tasks</p>
            <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
              Create schedules via the bot
            </p>
          </div>
        ) : (
          <>
            {/* Active schedules */}
            {activeSchedules.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-orange-500" />
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">Active</h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {activeSchedules.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {activeSchedules.map((schedule) => (
                    <ScheduleCard key={schedule.task_id} schedule={schedule} />
                  ))}
                </div>
              </div>
            )}

            {/* Inactive schedules */}
            {inactiveSchedules.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">Paused</h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {inactiveSchedules.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {inactiveSchedules.map((schedule) => (
                    <ScheduleCard key={schedule.task_id} schedule={schedule} />
                  ))}
                </div>
              </div>
            )}

            {/* Execution history */}
            {logs.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <History className="w-4 h-4 text-[var(--tg-theme-hint-color)]" />
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">Recent Activity</h2>
                </div>
                <div className="bg-[var(--tg-theme-bg-color)] rounded-xl overflow-hidden shadow-sm">
                  {logs.map((log, index) => (
                    <ExecutionLogItem key={`${log.timestamp}-${index}`} log={log} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
