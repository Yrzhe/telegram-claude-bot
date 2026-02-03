import { useEffect, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'
import { useTasksStore } from '../../stores/tasks'
import { useTelegram } from '../../hooks/useTelegram'
import { TaskCard } from './TaskCard'

export function TaskList() {
  const { running, recentCompleted, stats, isLoading, error, loadTasks, cancelTask } = useTasksStore()
  const { showConfirm, hapticFeedback } = useTelegram()

  useEffect(() => {
    loadTasks()
  }, [])

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

  return (
    <div className="flex flex-col h-full">
      {/* Stats bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[var(--tg-theme-secondary-bg-color)] border-b border-[var(--tg-theme-hint-color)]/10">
        <div className="flex gap-3 text-xs">
          <span className="text-[var(--tg-theme-button-color)]">
            {stats.running} running
          </span>
          <span className="text-green-500">{stats.completed} done</span>
          {stats.failed > 0 && (
            <span className="text-red-500">{stats.failed} failed</span>
          )}
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

      {/* Task list */}
      <div className="flex-1 overflow-auto py-2">
        {isLoading && running.length === 0 && recentCompleted.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            Loading...
          </div>
        ) : running.length === 0 && recentCompleted.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            No tasks yet
          </div>
        ) : (
          <>
            {/* Running tasks */}
            {running.length > 0 && (
              <>
                <div className="px-4 py-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Running ({running.length})
                </div>
                {running.map((task) => (
                  <TaskCard
                    key={task.task_id}
                    task={task}
                    onCancel={() => handleCancel(task.task_id)}
                  />
                ))}
              </>
            )}

            {/* Completed tasks */}
            {recentCompleted.length > 0 && (
              <>
                <div className="px-4 py-2 mt-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Recent ({recentCompleted.length})
                </div>
                {recentCompleted.map((task) => (
                  <TaskCard key={task.task_id} task={task} />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
