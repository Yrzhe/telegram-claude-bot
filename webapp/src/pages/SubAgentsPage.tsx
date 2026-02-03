import { useEffect, useCallback } from 'react'
import { RefreshCw, Bot, Loader2, CheckCircle2, XCircle, AlertCircle, Clock } from 'lucide-react'
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
  }, [loadStatus, loadHistory])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadStatus()
    loadHistory(10)
  }, [loadStatus, loadHistory, hapticFeedback])

  const formatDuration = (seconds?: number) => {
    if (seconds === undefined || seconds === null) return '--'
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    if (mins > 0) {
      return `${mins}m ${secs}s`
    }
    return `${secs}s`
  }

  const formatTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr)
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  const usedPercent = maxAgents > 0 ? (activeCount / maxAgents) * 100 : 0

  return (
    <div className="flex flex-col h-full bg-[var(--tg-theme-secondary-bg-color)]">
      {/* Header */}
      <header className="bg-[var(--tg-theme-bg-color)] px-4 py-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
                Sub Agents
              </h1>
              <p className="text-xs text-[var(--tg-theme-hint-color)]">
                Parallel task execution
              </p>
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
      </header>

      {/* Pool Status Card */}
      <div className="mx-4 mt-4 p-4 bg-[var(--tg-theme-bg-color)] rounded-2xl shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-[var(--tg-theme-text-color)]">Agent Pool</span>
          <div className="flex items-center gap-2">
            <span className={`text-2xl font-bold ${activeCount > 0 ? 'text-[var(--tg-theme-button-color)]' : 'text-[var(--tg-theme-hint-color)]'}`}>
              {activeCount}
            </span>
            <span className="text-sm text-[var(--tg-theme-hint-color)]">/ {maxAgents}</span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-[var(--tg-theme-hint-color)]/10 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${usedPercent}%`,
              background: usedPercent > 80
                ? 'linear-gradient(90deg, #f59e0b, #ef4444)'
                : 'linear-gradient(90deg, #3b82f6, #8b5cf6)'
            }}
          />
        </div>

        <div className="flex justify-between mt-2">
          <span className="text-xs text-[var(--tg-theme-hint-color)]">
            {availableSlots} slots available
          </span>
          <span className="text-xs text-[var(--tg-theme-hint-color)]">
            {Math.round(usedPercent)}% utilized
          </span>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span className="text-sm text-red-500">{error}</span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto px-4 py-4 pb-20">
        {isLoading && runningTasks.length === 0 && history.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-[var(--tg-theme-hint-color)]">
            <Loader2 className="w-8 h-8 animate-spin mb-3" />
            <span className="text-sm">Loading agents...</span>
          </div>
        ) : (
          <>
            {/* Running agents section */}
            {runningTasks.length > 0 ? (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">
                    Running
                  </h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {runningTasks.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {runningTasks.map((task) => (
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
                          <div className="flex items-center gap-4 mt-2">
                            <div className="flex items-center gap-1 text-xs text-[var(--tg-theme-hint-color)]">
                              <Clock className="w-3 h-3" />
                              <span>{formatDuration(task.elapsed_seconds)}</span>
                            </div>
                            {task.retry_count !== undefined && task.retry_count > 0 && (
                              <span className="text-xs text-orange-500">
                                Retry {task.retry_count}/{task.max_retries || 10}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mb-6 p-6 bg-[var(--tg-theme-bg-color)] rounded-xl text-center">
                <div className="w-16 h-16 rounded-full bg-[var(--tg-theme-secondary-bg-color)] flex items-center justify-center mx-auto mb-3">
                  <Bot className="w-8 h-8 text-[var(--tg-theme-hint-color)]" />
                </div>
                <p className="text-sm font-medium text-[var(--tg-theme-text-color)]">No Running Agents</p>
                <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1">
                  Agents will appear here when tasks are running
                </p>
              </div>
            )}

            {/* History section */}
            {history.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">
                    Recent History
                  </h2>
                  <span className="text-xs text-[var(--tg-theme-hint-color)] bg-[var(--tg-theme-bg-color)] px-2 py-0.5 rounded-full">
                    {history.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {history.map((item) => (
                    <div
                      key={item.task_id}
                      className="bg-[var(--tg-theme-bg-color)] rounded-xl p-3 shadow-sm"
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          item.status === 'completed'
                            ? 'bg-green-500/10'
                            : item.status === 'cancelled'
                            ? 'bg-gray-500/10'
                            : 'bg-red-500/10'
                        }`}>
                          {item.status === 'completed' ? (
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                          ) : item.status === 'cancelled' ? (
                            <XCircle className="w-4 h-4 text-gray-500" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-500" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-mono text-[var(--tg-theme-hint-color)]">
                              {item.task_id.slice(0, 8)}
                            </span>
                            <span className="text-xs text-[var(--tg-theme-hint-color)]">
                              {formatTime(item.created_at)}
                            </span>
                          </div>
                          <p className="text-sm text-[var(--tg-theme-text-color)] line-clamp-1">
                            {item.description}
                          </p>
                          {item.result_preview && (
                            <p className="text-xs text-[var(--tg-theme-hint-color)] mt-1 line-clamp-1 italic">
                              {item.result_preview}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty history state */}
            {history.length === 0 && runningTasks.length === 0 && (
              <div className="text-center py-8">
                <p className="text-sm text-[var(--tg-theme-hint-color)]">
                  No agent history yet
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
