import { useEffect, useCallback } from 'react'
import { RefreshCw, Bot, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { Header } from '../components/layout/Header'
import { useSubAgentsStore } from '../stores/subagents'
import { useTelegram } from '../hooks/useTelegram'

export function SubAgentsPage() {
  const {
    maxAgents,
    activeCount,
    availableSlots,
    runningTasks,
    history,
    isLoading,
    error,
    loadStatus,
    loadHistory,
  } = useSubAgentsStore()
  const { hapticFeedback } = useTelegram()

  useEffect(() => {
    loadStatus()
    loadHistory(10)
  }, [])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadStatus()
    loadHistory(10)
  }, [loadStatus, loadHistory, hapticFeedback])

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    if (mins > 0) {
      return `${mins}m ${secs}s`
    }
    return `${secs}s`
  }

  const usedPercent = (activeCount / maxAgents) * 100

  return (
    <div className="flex flex-col h-full">
      <Header title="Sub Agents" />

      {/* Pool status */}
      <div className="px-4 py-3 bg-[var(--tg-theme-secondary-bg-color)]">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-[var(--tg-theme-hint-color)]">Agent Pool</span>
          <span className="text-[var(--tg-theme-text-color)]">
            {activeCount} / {maxAgents} active
          </span>
        </div>
        <div className="h-2 bg-[var(--tg-theme-hint-color)]/20 rounded-full overflow-hidden">
          <div
            className="h-full bg-[var(--tg-theme-button-color)] rounded-full transition-all"
            style={{ width: `${usedPercent}%` }}
          />
        </div>
        <div className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
          {availableSlots} slots available
        </div>
      </div>

      {/* Refresh button */}
      <div className="flex justify-end px-4 py-2 border-b border-[var(--tg-theme-hint-color)]/10">
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

      {/* Content */}
      <div className="flex-1 overflow-auto py-2">
        {isLoading && runningTasks.length === 0 && history.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--tg-theme-hint-color)]">
            Loading...
          </div>
        ) : (
          <>
            {/* Running agents */}
            {runningTasks.length > 0 && (
              <>
                <div className="px-4 py-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Running ({runningTasks.length})
                </div>
                {runningTasks.map((task) => (
                  <div
                    key={task.task_id}
                    className="bg-[var(--tg-theme-secondary-bg-color)] rounded-lg p-3 mx-4 mb-2"
                  >
                    <div className="flex items-start gap-3">
                      <Loader2 className="w-5 h-5 text-[var(--tg-theme-button-color)] animate-spin flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Bot className="w-4 h-4 text-[var(--tg-theme-hint-color)]" />
                          <span className="text-xs text-[var(--tg-theme-hint-color)] font-mono">
                            {task.task_id.slice(0, 8)}
                          </span>
                        </div>
                        <div className="text-[var(--tg-theme-text-color)] text-sm mt-1 line-clamp-2">
                          {task.description}
                        </div>
                        <div className="flex items-center gap-4 text-xs text-[var(--tg-theme-hint-color)] mt-2">
                          <span>Running: {formatDuration(task.elapsed_seconds)}</span>
                          {task.retry_count !== undefined && (
                            <span>
                              Retry: {task.retry_count}/{task.max_retries || 10}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* No running tasks message */}
            {runningTasks.length === 0 && (
              <div className="px-4 py-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                No Running Agents
              </div>
            )}

            {/* History */}
            {history.length > 0 && (
              <>
                <div className="px-4 py-2 mt-2 text-xs font-medium text-[var(--tg-theme-hint-color)] uppercase">
                  Recent Completed ({history.length})
                </div>
                {history.map((item) => (
                  <div
                    key={item.task_id}
                    className="bg-[var(--tg-theme-secondary-bg-color)] rounded-lg p-3 mx-4 mb-2"
                  >
                    <div className="flex items-start gap-3">
                      {item.status === 'completed' ? (
                        <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Bot className="w-4 h-4 text-[var(--tg-theme-hint-color)]" />
                          <span className="text-xs text-[var(--tg-theme-hint-color)] font-mono">
                            {item.task_id.slice(0, 8)}
                          </span>
                        </div>
                        <div className="text-[var(--tg-theme-text-color)] text-sm mt-1 line-clamp-2">
                          {item.description}
                        </div>
                        <div className="flex items-center gap-4 text-xs text-[var(--tg-theme-hint-color)] mt-2">
                          <span>Duration: {formatDuration(item.duration_seconds)}</span>
                          <span>Attempts: {item.attempts}</span>
                        </div>
                        {item.result_preview && (
                          <div className="text-xs text-[var(--tg-theme-hint-color)] mt-2 line-clamp-2 italic">
                            {item.result_preview}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
