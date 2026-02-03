import { useSchedulesStore } from '../stores/schedules'
import { ScheduleList } from '../components/schedules/ScheduleList'

export function SchedulesPage() {
  const { schedules, timezone } = useSchedulesStore()
  const activeCount = schedules.filter(s => s.enabled).length
  const pausedCount = schedules.filter(s => !s.enabled).length

  return (
    <div className="page scrollbar-hide overflow-auto">
      {/* Header */}
      <header className="page-header">
        <h1 className="page-title">Schedules</h1>
        <p className="page-subtitle">{timezone || 'Loading timezone...'}</p>
      </header>

      {/* Stats */}
      <div className="card mb-4">
        <div className="stats-row">
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#ff9500' }}>{activeCount}</div>
            <div className="stat-label">Active</div>
          </div>
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#8e8e93' }}>{pausedCount}</div>
            <div className="stat-label">Paused</div>
          </div>
        </div>
      </div>

      {/* Schedule list */}
      <ScheduleList />
    </div>
  )
}
