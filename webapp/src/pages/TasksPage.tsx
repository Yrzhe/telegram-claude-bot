import { useTasksStore } from '../stores/tasks'
import { TaskList } from '../components/tasks/TaskList'

export function TasksPage() {
  const { stats } = useTasksStore()

  return (
    <div className="page scrollbar-hide overflow-auto">
      {/* Header */}
      <header className="page-header">
        <h1 className="page-title">Tasks</h1>
        <p className="page-subtitle">Background operations</p>
      </header>

      {/* Stats */}
      <div className="card mb-4">
        <div className="stats-row">
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#007aff' }}>{stats.running}</div>
            <div className="stat-label">Running</div>
          </div>
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#34c759' }}>{stats.completed}</div>
            <div className="stat-label">Completed</div>
          </div>
          {stats.failed > 0 && (
            <div className="stat-item">
              <div className="stat-value" style={{ color: '#ff3b30' }}>{stats.failed}</div>
              <div className="stat-label">Failed</div>
            </div>
          )}
        </div>
      </div>

      {/* Task list */}
      <TaskList />
    </div>
  )
}
