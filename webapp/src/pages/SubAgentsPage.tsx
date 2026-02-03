import { useEffect, useCallback } from 'react'
import { RefreshCw, Bot, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react'
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
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
  }

  const formatTime = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  const usedPercent = maxAgents > 0 ? (activeCount / maxAgents) * 100 : 0

  return (
    <div className="page scrollbar-hide overflow-auto">
      {/* Header */}
      <header className="page-header">
        <h1 className="page-title">Agents</h1>
        <p className="page-subtitle">Parallel task execution</p>
      </header>

      {/* Pool status */}
      <div className="card mb-4">
        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[15px] font-medium">Agent Pool</span>
            <div className="flex items-baseline gap-1">
              <span className="text-[28px] font-bold" style={{ color: activeCount > 0 ? '#007aff' : '#8e8e93' }}>
                {activeCount}
              </span>
              <span className="text-[15px] text-[var(--tg-theme-hint-color)]">/ {maxAgents}</span>
            </div>
          </div>
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{
                width: `${usedPercent}%`,
                background: usedPercent > 80 ? '#ff9500' : '#007aff'
              }}
            />
          </div>
          <div className="flex justify-between mt-2 text-[13px] text-[var(--tg-theme-hint-color)]">
            <span>{availableSlots} slots available</span>
            <span>{Math.round(usedPercent)}% utilized</span>
          </div>
        </div>
      </div>

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

      {/* Loading */}
      {isLoading && runningTasks.length === 0 && history.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="spinner" />
            <p className="empty-state-description mt-4">Loading...</p>
          </div>
        </div>
      ) : (
        <>
          {/* Running agents */}
          {runningTasks.length > 0 ? (
            <>
              <div className="section-header">Running</div>
              <div className="card mb-4">
                {runningTasks.map((task) => (
                  <div key={task.task_id} className="list-item">
                    <div className="list-item-icon icon-blue">
                      <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                    <div className="list-item-content">
                      <div className="list-item-title">{task.task_id.slice(0, 8)}</div>
                      <div className="list-item-subtitle line-clamp-1">{task.description}</div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-[12px] text-[var(--tg-theme-hint-color)] flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDuration(task.elapsed_seconds)}
                        </span>
                        {task.retry_count !== undefined && task.retry_count > 0 && (
                          <span className="text-[12px] text-[#ff9500]">
                            Retry {task.retry_count}/{task.max_retries || 10}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="card mb-4">
              <div className="empty-state">
                <div className="empty-state-icon">
                  <Bot />
                </div>
                <h3 className="empty-state-title">No running agents</h3>
                <p className="empty-state-description">Agents will appear when tasks run</p>
              </div>
            </div>
          )}

          {/* History */}
          {history.length > 0 && (
            <>
              <div className="section-header">Recent</div>
              <div className="card">
                {history.map((item) => (
                  <div key={item.task_id} className="list-item">
                    <div className={`list-item-icon ${
                      item.status === 'completed' ? 'icon-green' : 'icon-red'
                    }`}>
                      {item.status === 'completed' ? (
                        <CheckCircle2 className="w-5 h-5" />
                      ) : (
                        <XCircle className="w-5 h-5" />
                      )}
                    </div>
                    <div className="list-item-content">
                      <div className="flex justify-between">
                        <span className="list-item-title">{item.task_id.slice(0, 8)}</span>
                        <span className="text-[13px] text-[var(--tg-theme-hint-color)]">
                          {formatTime(item.created_at)}
                        </span>
                      </div>
                      <div className="list-item-subtitle line-clamp-1">{item.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
