import { useEffect, useCallback } from 'react'
import { RefreshCw, ListTodo, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useTasksStore } from '../../stores/tasks'
import { useTelegram } from '../../hooks/useTelegram'

export function TaskList() {
  const { running, recentCompleted, isLoading, error, loadTasks, cancelTask } = useTasksStore()
  const { showConfirm, hapticFeedback } = useTelegram()

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  const handleCancel = useCallback(async (taskId: string) => {
    const confirmed = await showConfirm?.('Cancel this task?') ?? confirm('Cancel this task?')
    if (confirmed) {
      hapticFeedback?.('medium')
      await cancelTask(taskId)
    }
  }, [cancelTask, showConfirm, hapticFeedback])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadTasks()
  }, [loadTasks, hapticFeedback])

  const formatTime = (dateStr?: string) => {
    if (!dateStr) return ''
    try {
      return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  if (isLoading && running.length === 0 && recentCompleted.length === 0) {
    return (
      <div className="card">
        <div className="empty-state">
          <div className="spinner" />
          <p className="empty-state-description mt-4">Loading...</p>
        </div>
      </div>
    )
  }

  if (running.length === 0 && recentCompleted.length === 0) {
    return (
      <div className="card">
        <div className="empty-state">
          <div className="empty-state-icon">
            <ListTodo />
          </div>
          <h3 className="empty-state-title">No tasks</h3>
          <p className="empty-state-description">Tasks will appear here when running</p>
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

      {/* Running tasks */}
      {running.length > 0 && (
        <>
          <div className="section-header">Running</div>
          <div className="card mb-4">
            {running.map((task) => (
              <div key={task.task_id} className="list-item">
                <div className="list-item-icon icon-blue">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
                <div className="list-item-content">
                  <div className="list-item-title">{task.task_id.slice(0, 8)}</div>
                  <div className="list-item-subtitle line-clamp-1">{task.description}</div>
                  {task.progress !== undefined && (
                    <div className="progress-bar mt-2">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${task.progress}%`, background: '#007aff' }}
                      />
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleCancel(task.task_id)}
                  className="btn-text-destructive text-[15px]"
                >
                  Cancel
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Completed tasks */}
      {recentCompleted.length > 0 && (
        <>
          <div className="section-header">Recent</div>
          <div className="card">
            {recentCompleted.map((task) => (
              <div key={task.task_id} className="list-item">
                <div className={`list-item-icon ${
                  task.status === 'completed' ? 'icon-green' : 'icon-red'
                }`}>
                  {task.status === 'completed' ? (
                    <CheckCircle2 className="w-5 h-5" />
                  ) : (
                    <XCircle className="w-5 h-5" />
                  )}
                </div>
                <div className="list-item-content">
                  <div className="flex justify-between">
                    <span className="list-item-title">{task.task_id.slice(0, 8)}</span>
                    <span className="text-[13px] text-[var(--tg-theme-hint-color)]">
                      {formatTime(task.completed_at)}
                    </span>
                  </div>
                  <div className="list-item-subtitle line-clamp-1">{task.description}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
