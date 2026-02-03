import { useEffect, useCallback } from 'react'
import { RefreshCw, History } from 'lucide-react'
import { useSchedulesStore } from '../../stores/schedules'
import { useTelegram } from '../../hooks/useTelegram'
import { ScheduleCard } from './ScheduleCard'
import { ExecutionLog } from './ExecutionLog'

export function ScheduleList() {
  const { timezone, schedules, logs, isLoading, error, loadSchedules, loadLogs } = useSchedulesStore()
  const { hapticFeedback } = useTelegram()

  useEffect(() => {
    loadSchedules()
    loadLogs(10)
  }, [])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadSchedules()
    loadLogs(10)
  }, [loadSchedules, loadLogs, hapticFeedback])

  const activeSchedules = schedules.filter((s) => s.enabled)
  const inactiveSchedules = schedules.filter((s) => !s.enabled)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-[var(--tg-theme-secondary-bg-color)] border-b border-[var(--tg-theme-hint-color)]/10">
        <div className="text-xs text-[var(--tg-theme-hint-color)]">
          Timezone: {timezone}
        </div>
        <button
          onClick={handleRefresh}
          className="p-1 text-[var(--tg-theme-button-color)]"
          disabled={isLoading}
        >
          <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 text-red-500 text-sm">
          {error}
        </div>
      )}

      {/* Schedule list */}
      <div className="flex-1 overflow-auto py-2">
        {isLoading && schedules.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            Loading...
          </div>
        ) : schedules.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            No scheduled tasks
          </div>
        ) : (
          <>
            {/* Active schedules */}
            {activeSchedules.length > 0 && (
              <>
                <div className="px-4 py-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Active ({activeSchedules.length})
                </div>
                {activeSchedules.map((schedule) => (
                  <ScheduleCard key={schedule.task_id} schedule={schedule} />
                ))}
              </>
            )}

            {/* Inactive schedules */}
            {inactiveSchedules.length > 0 && (
              <>
                <div className="px-4 py-2 mt-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Inactive ({inactiveSchedules.length})
                </div>
                {inactiveSchedules.map((schedule) => (
                  <ScheduleCard key={schedule.task_id} schedule={schedule} />
                ))}
              </>
            )}

            {/* Execution history */}
            {logs.length > 0 && (
              <>
                <div className="px-4 py-2 mt-4 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase flex items-center gap-2">
                  <History className="w-4 h-4" />
                  Recent Activity
                </div>
                <div className="mx-4 bg-[var(--tg-theme-secondary-bg-color)] rounded-lg overflow-hidden">
                  {logs.map((log, index) => (
                    <ExecutionLog key={`${log.timestamp}-${index}`} log={log} />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
