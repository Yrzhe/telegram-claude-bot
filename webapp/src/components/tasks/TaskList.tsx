import { useEffect, useCallback } from 'react'
import { RefreshCw, Loader2, ListTodo, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import { useTasksStore } from '../../stores/tasks'
import { useTelegram } from '../../hooks/useTelegram'

export function TaskList() {
  const { running, recentCompleted, stats, isLoading, error, loadTasks, cancelTask } = useTasksStore()
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
      const date = new Date(dateStr)
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Stats card */}
      <div className="mx-4 mt-4 p-4 bg-[var(--tg-theme-bg-color)] rounded-xl shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex gap-4">
            <div className="text-center">
              <div className="text-xl font-bold text-[var(--tg-theme-button-color)]">{stats.running}</div>
              <div className="text-xs text-[var(--tg-theme-hint-color)]">Running</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-green-500">{stats.completed}</div>
              <div className="text-xs text-[var(--tg-theme-hint-color)]">Done</div>
            </div>
            {stats.failed > 0 && (
              <div className="text-center">
                <div className="text-xl font-bold text-red-500">{stats.failed}</div>
                <div className="text-xs text-[var(--tg-theme-hint-color)]">Failed</div>
              </div>
            )}
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

      {/* Task list */}
      <div className="flex-1 overflow-auto px-4 py-4 pb-20">
        {isLoading && running.length === 0 && recentCompleted.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40">
            <Loader2 className="w-8 h-8 text-[var(--tg-theme-button-color)] animate-spin mb-3" />
            <span className="text-sm text-[var(--tg-theme-hint-color)]">Loading tasks...</span>
          </div>
        ) : running.length === 0 && recentCompleted.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 bg-[var(--tg-theme-bg-color)] rounded-xl">
            <div className="w-16 h-16 rounded-full bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center mb-3">
              <ListTodo className="w-8 h-8 text-[var(--tg-theme-hint-color)]" />
            </div>
            <p className="text-sm font-medium text-[var(--tg-theme-text-color)]">No tasks yet</p>
            <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
              Tasks will appear here when running
            </p>
          </div>
        ) : (
          <>
            {/* Running tasks */}
            {running.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">Running</h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {running.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {running.map((task) => (
                    <div
                      key={task.task_id}
                      className="bg-[var(--tg-theme-bg-color)] rounded-xl p-4 shadow-sm border-l-4 border-[var(--tg-theme-button-color)]"
                    >
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-lg bg-[var(--tg-theme-button-color)]/10 flex items-center justify-center flex-shrink-0">
                          <Loader2 className="w-5 h-5 text-[var(--tg-theme-button-color)] animate-spin" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-mono text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-secondary-bg-color)] px-2 py-0.5 rounded">
                              {task.task_id.slice(0, 8)}
                            </span>
                          </div>
                          <p className="text-sm text-[var(--tg-theme-text-color)] line-clamp-2">
                            {task.description}
                          </p>
                          {task.progress !== undefined && (
                            <div className="mt-2">
                              <div className="h-1.5 bg-[var(--tg-theme-hint-color)]/10 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-[var(--tg-theme-button-color)] rounded-full transition-all"
                                  style={{ width: `${task.progress}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => handleCancel(task.task_id)}
                          className="px-3 py-1.5 text-xs text-red-500 bg-red-500/10 rounded-lg active:bg-red-500/20 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Completed tasks */}
            {recentCompleted.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">Recent</h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {recentCompleted.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {recentCompleted.map((task) => (
                    <div
                      key={task.task_id}
                      className="bg-[var(--tg-theme-bg-color)] rounded-xl p-3 shadow-sm"
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          task.status === 'completed'
                            ? 'bg-green-500/10'
                            : task.status === 'cancelled'
                            ? 'bg-gray-500/10'
                            : 'bg-red-500/10'
                        }`}>
                          {task.status === 'completed' ? (
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                          ) : (
                            <XCircle className={`w-4 h-4 ${task.status === 'cancelled' ? 'text-gray-500' : 'text-red-500'}`} />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-mono text-[var(--tg-theme-hint-color)]">
                              {task.task_id.slice(0, 8)}
                            </span>
                            <span className="text-xs text-[var(--tg-theme-hint-color)]">
                              {formatTime(task.completed_at)}
                            </span>
                          </div>
                          <p className="text-sm text-[var(--tg-theme-text-color)] line-clamp-1">
                            {task.description}
                          </p>
                          {task.result_preview && (
                            <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1 line-clamp-1 italic">
                              {task.result_preview}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
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
