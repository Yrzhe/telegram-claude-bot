import { Clock } from 'lucide-react'
import { ScheduleList } from '../components/schedules/ScheduleList'
import { useSchedulesStore } from '../stores/schedules'

export function SchedulesPage() {
  const { schedules, timezone } = useSchedulesStore()
  const activeCount = schedules.filter(s => s.enabled).length

  return (
    <div className="flex flex-col h-full bg-[var(--tg-theme-secondary-bg-color)]">
      {/* Header */}
      <header className="bg-[var(--tg-theme-bg-color)] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center">
            <Clock className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
              Schedules
            </h1>
            <p className="text-xs text-[var(--tg-theme-hint-color)]">
              {timezone || 'Loading...'}
            </p>
          </div>
          {activeCount > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-orange-500/10">
              <span className="text-xs font-medium text-orange-500">{activeCount} active</span>
            </div>
          )}
        </div>
      </header>

      {/* Schedule list */}
      <ScheduleList />
    </div>
  )
}
