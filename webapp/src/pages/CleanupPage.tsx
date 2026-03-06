import { useEffect, useCallback, useState } from 'react'
import {
  Trash2,
  Archive,
  ArrowRight,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Save,
  Play,
  MessageSquare,
  CheckCircle,
  XCircle,
  AlertTriangle,
} from 'lucide-react'
import { useCleanupStore } from '../stores/cleanup'
import { useTelegram } from '../hooks/useTelegram'
import { wsClient } from '../api/websocket'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const actionConfig = {
  delete: { icon: Trash2, color: '#ff3b30', label: 'Delete' },
  archive: { icon: Archive, color: '#ff9500', label: 'Archive' },
  move: { icon: ArrowRight, color: '#007aff', label: 'Move' },
}

export function CleanupPage() {
  const {
    phase,
    rules,
    plan,
    result,
    error,
    feedbackText,
    progressLogs,
    isLoadingRules,
    isSavingRules,
    loadRules,
    saveRules,
    startPlanning,
    executePlan,
    cancelCleanup,
    reset,
    loadStatus,
    setFeedbackText,
    handleWsUpdate,
    handleWsProgress,
  } = useCleanupStore()
  const { hapticFeedback } = useTelegram()

  const [rulesExpanded, setRulesExpanded] = useState(false)
  const [rulesText, setRulesText] = useState('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [confirmExecute, setConfirmExecute] = useState(false)

  // Load rules + status on mount
  useEffect(() => {
    loadRules()
    loadStatus()
  }, [loadRules, loadStatus])

  // Sync rules text when loaded
  useEffect(() => {
    if (rules) setRulesText(rules)
  }, [rules])

  // Subscribe to cleanup WebSocket updates
  useEffect(() => {
    const unsubUpdate = wsClient.subscribe('cleanup_update', (data) => {
      handleWsUpdate(data as Record<string, unknown>)
    })
    const unsubProgress = wsClient.subscribe('cleanup_progress', (data) => {
      handleWsProgress(data as Record<string, unknown>)
    })
    return () => {
      unsubUpdate()
      unsubProgress()
    }
  }, [handleWsUpdate, handleWsProgress])

  const handleSaveRules = useCallback(async () => {
    hapticFeedback?.('light')
    const success = await saveRules(rulesText)
    if (success) {
      setRulesExpanded(false)
    }
  }, [rulesText, saveRules, hapticFeedback])

  const handleStartPlanning = useCallback(() => {
    hapticFeedback?.('medium')
    startPlanning()
  }, [startPlanning, hapticFeedback])

  const handleReplan = useCallback(() => {
    hapticFeedback?.('medium')
    startPlanning(feedbackText)
    setShowFeedback(false)
    setFeedbackText('')
  }, [startPlanning, feedbackText, setFeedbackText, hapticFeedback])

  const handleExecute = useCallback(() => {
    hapticFeedback?.('heavy')
    setConfirmExecute(false)
    executePlan()
  }, [executePlan, hapticFeedback])

  const handleDone = useCallback(() => {
    hapticFeedback?.('light')
    reset()
  }, [reset, hapticFeedback])

  // --- Phase: Idle ---
  if (phase === 'idle') {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup</h1>
          <p className="page-subtitle">Intelligent file cleanup agent</p>
        </header>

        {/* Rules Card */}
        <div className="card mb-4">
          <button
            onClick={() => setRulesExpanded(!rulesExpanded)}
            className="list-item w-full text-left"
          >
            <div className="list-item-content">
              <div className="list-item-title">Cleanup Rules</div>
              <div className="list-item-subtitle">Define what to protect and clean</div>
            </div>
            {rulesExpanded ? (
              <ChevronUp className="w-5 h-5 text-[var(--tg-theme-hint-color)] flex-shrink-0" />
            ) : (
              <ChevronDown className="w-5 h-5 text-[var(--tg-theme-hint-color)] flex-shrink-0" />
            )}
          </button>

          {rulesExpanded && (
            <div className="px-4 pb-4">
              {isLoadingRules ? (
                <div className="flex justify-center py-4">
                  <div className="spinner" />
                </div>
              ) : (
                <>
                  <textarea
                    value={rulesText}
                    onChange={(e) => setRulesText(e.target.value)}
                    className="w-full rounded-lg p-3 text-[13px] leading-relaxed resize-none"
                    style={{
                      background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)',
                      color: 'var(--tg-theme-text-color, #e0e0e0)',
                      border: 'none',
                      outline: 'none',
                      minHeight: '200px',
                      fontFamily: 'monospace',
                    }}
                  />
                  <div className="flex justify-end mt-2">
                    <button
                      onClick={handleSaveRules}
                      disabled={isSavingRules || rulesText === rules}
                      className="btn-text flex items-center gap-2"
                      style={{
                        opacity: isSavingRules || rulesText === rules ? 0.5 : 1,
                      }}
                    >
                      <Save className="w-4 h-4" />
                      {isSavingRules ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="card mb-4 p-4">
            <p className="text-[15px]" style={{ color: 'var(--tg-theme-destructive-color, #ff3b30)' }}>
              {error}
            </p>
          </div>
        )}

        {/* Start Button */}
        <button
          onClick={handleStartPlanning}
          className="w-full py-3 rounded-xl text-[16px] font-semibold flex items-center justify-center gap-2"
          style={{
            background: 'var(--tg-theme-button-color, #3390ec)',
            color: 'var(--tg-theme-button-text-color, #fff)',
          }}
        >
          <Play className="w-5 h-5" />
          Start Cleanup Scan
        </button>
      </div>
    )
  }

  // --- Phase: Planning ---
  if (phase === 'planning') {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup</h1>
          <p className="page-subtitle">Analyzing your files...</p>
        </header>

        <div className="card mb-4">
          <div className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="spinner" />
              <div className="text-[15px] font-medium">Scanning Directory</div>
            </div>

            {/* Progress log */}
            {progressLogs.length > 0 && (
              <div
                className="rounded-lg p-3 space-y-1.5 max-h-[240px] overflow-auto"
                style={{ background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)' }}
              >
                {progressLogs.map((log, idx) => (
                  <div
                    key={idx}
                    className="text-[13px] leading-snug"
                    style={{
                      color: idx === progressLogs.length - 1
                        ? 'var(--tg-theme-text-color, #e0e0e0)'
                        : 'var(--tg-theme-hint-color, #999)',
                    }}
                  >
                    {log}
                  </div>
                ))}
              </div>
            )}

            {progressLogs.length === 0 && (
              <p className="text-[13px] text-[var(--tg-theme-hint-color)]">
                Waiting for agent to start...
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-center">
          <button onClick={cancelCleanup} className="btn-text">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // --- Phase: Review ---
  if (phase === 'review' && plan) {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup Plan</h1>
          <p className="page-subtitle">{plan.summary}</p>
        </header>

        {/* Stats */}
        <div className="card mb-4">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div className="text-center flex-1">
                <div className="text-[24px] font-bold" style={{ color: '#007aff' }}>
                  {plan.actions.length}
                </div>
                <div className="text-[12px] text-[var(--tg-theme-hint-color)]">Actions</div>
              </div>
              <div
                className="w-px h-8"
                style={{ background: 'var(--tg-theme-hint-color, #666)', opacity: 0.3 }}
              />
              <div className="text-center flex-1">
                <div className="text-[24px] font-bold" style={{ color: '#ff9500' }}>
                  {plan.total_items}
                </div>
                <div className="text-[12px] text-[var(--tg-theme-hint-color)]">Items</div>
              </div>
              <div
                className="w-px h-8"
                style={{ background: 'var(--tg-theme-hint-color, #666)', opacity: 0.3 }}
              />
              <div className="text-center flex-1">
                <div className="text-[24px] font-bold" style={{ color: '#ff3b30' }}>
                  {formatBytes(plan.total_size_bytes)}
                </div>
                <div className="text-[12px] text-[var(--tg-theme-hint-color)]">Size</div>
              </div>
            </div>
          </div>
        </div>

        {/* Actions list */}
        {plan.actions.length === 0 ? (
          <div className="card mb-4">
            <div className="empty-state">
              <div className="empty-state-icon">
                <CheckCircle />
              </div>
              <h3 className="empty-state-title">All Clean</h3>
              <p className="empty-state-description">No files need cleanup</p>
            </div>
          </div>
        ) : (
          <div className="card mb-4">
            {plan.actions.map((action, idx) => {
              const config = actionConfig[action.action] || actionConfig.delete
              const Icon = config.icon
              return (
                <div key={idx}>
                  <div className="list-item">
                    <div
                      className="list-item-icon"
                      style={{ background: `${config.color}20`, color: config.color }}
                    >
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="list-item-content">
                      <div className="list-item-title">{action.path}</div>
                      <div className="list-item-subtitle">
                        {config.label} · {formatBytes(action.size_bytes)} · {action.reason}
                      </div>
                    </div>
                  </div>
                  {idx < plan.actions.length - 1 && <div className="separator ml-[52px]" />}
                </div>
              )
            })}
          </div>
        )}

        {/* Feedback section */}
        {showFeedback && (
          <div className="card mb-4 p-4">
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="e.g., Don't delete the reports/ folder, archive it instead..."
              className="w-full rounded-lg p-3 text-[14px] leading-relaxed resize-none"
              style={{
                background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)',
                color: 'var(--tg-theme-text-color, #e0e0e0)',
                border: 'none',
                outline: 'none',
                minHeight: '80px',
              }}
            />
            <div className="flex gap-2 mt-2">
              <button
                onClick={handleReplan}
                disabled={!feedbackText.trim()}
                className="flex-1 py-2 rounded-lg text-[14px] font-medium flex items-center justify-center gap-2"
                style={{
                  background: 'var(--tg-theme-button-color, #3390ec)',
                  color: 'var(--tg-theme-button-text-color, #fff)',
                  opacity: feedbackText.trim() ? 1 : 0.5,
                }}
              >
                <RefreshCw className="w-4 h-4" />
                Re-plan
              </button>
              <button
                onClick={() => setShowFeedback(false)}
                className="py-2 px-4 rounded-lg text-[14px]"
                style={{ background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)' }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Action buttons */}
        {plan.actions.length > 0 && (
          <div className="space-y-2">
            {confirmExecute ? (
              <div className="flex gap-2">
                <button
                  onClick={handleExecute}
                  className="flex-1 py-3 rounded-xl text-[16px] font-semibold"
                  style={{
                    background: 'var(--tg-theme-destructive-color, #ff3b30)',
                    color: '#fff',
                  }}
                >
                  Confirm Execute
                </button>
                <button
                  onClick={() => setConfirmExecute(false)}
                  className="py-3 px-6 rounded-xl text-[16px]"
                  style={{ background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)' }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  hapticFeedback?.('medium')
                  setConfirmExecute(true)
                }}
                className="w-full py-3 rounded-xl text-[16px] font-semibold flex items-center justify-center gap-2"
                style={{
                  background: 'var(--tg-theme-button-color, #3390ec)',
                  color: 'var(--tg-theme-button-text-color, #fff)',
                }}
              >
                <Trash2 className="w-5 h-5" />
                Execute Plan
              </button>
            )}

            {!showFeedback && !confirmExecute && (
              <button
                onClick={() => {
                  hapticFeedback?.('light')
                  setShowFeedback(true)
                }}
                className="w-full py-3 rounded-xl text-[14px] flex items-center justify-center gap-2"
                style={{
                  background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)',
                  color: 'var(--tg-theme-text-color, #e0e0e0)',
                }}
              >
                <MessageSquare className="w-4 h-4" />
                Give Feedback
              </button>
            )}
          </div>
        )}

        {/* Cancel link */}
        <div className="mt-4 flex justify-center">
          <button onClick={cancelCleanup} className="btn-text">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // --- Phase: Executing ---
  if (phase === 'executing') {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup</h1>
          <p className="page-subtitle">Executing cleanup plan...</p>
        </header>

        <div className="card">
          <div className="empty-state">
            <div className="spinner" />
            <h3 className="empty-state-title mt-4">Cleaning Up</h3>
            <p className="empty-state-description">Deleting and archiving files...</p>
          </div>
        </div>
      </div>
    )
  }

  // --- Phase: Completed ---
  if (phase === 'completed' && result) {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup Complete</h1>
          <p className="page-subtitle">Your files have been cleaned up</p>
        </header>

        <div className="card mb-4">
          <div className="p-4">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle className="w-8 h-8" style={{ color: '#34c759' }} />
              <div>
                <div className="text-[17px] font-semibold">Success</div>
                <div className="text-[14px] text-[var(--tg-theme-hint-color)]">
                  Freed {formatBytes(result.freed_bytes)}
                </div>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="text-center flex-1">
                <div className="text-[20px] font-bold" style={{ color: '#34c759' }}>
                  {result.success_count}
                </div>
                <div className="text-[12px] text-[var(--tg-theme-hint-color)]">Succeeded</div>
              </div>
              {result.fail_count > 0 && (
                <div className="text-center flex-1">
                  <div className="text-[20px] font-bold" style={{ color: '#ff3b30' }}>
                    {result.fail_count}
                  </div>
                  <div className="text-[12px] text-[var(--tg-theme-hint-color)]">Failed</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {result.errors && result.errors.length > 0 && (
          <div className="card mb-4 p-4">
            <div className="text-[13px] font-medium text-[var(--tg-theme-hint-color)] mb-2">
              Errors
            </div>
            <div className="space-y-1">
              {result.errors.map((err, idx) => (
                <div key={idx} className="flex items-start gap-2 text-[13px]">
                  <AlertTriangle
                    className="w-3.5 h-3.5 flex-shrink-0 mt-0.5"
                    style={{ color: '#ff9500' }}
                  />
                  <span>{err}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={handleDone}
          className="w-full py-3 rounded-xl text-[16px] font-semibold"
          style={{
            background: 'var(--tg-theme-button-color, #3390ec)',
            color: 'var(--tg-theme-button-text-color, #fff)',
          }}
        >
          Done
        </button>
      </div>
    )
  }

  // --- Phase: Failed ---
  if (phase === 'failed') {
    return (
      <div className="page scrollbar-hide overflow-auto">
        <header className="page-header">
          <h1 className="page-title">Cleanup</h1>
          <p className="page-subtitle">Something went wrong</p>
        </header>

        <div className="card mb-4">
          <div className="empty-state">
            <div className="empty-state-icon">
              <XCircle style={{ color: 'var(--tg-theme-destructive-color, #ff3b30)' }} />
            </div>
            <h3 className="empty-state-title">Cleanup Failed</h3>
            <p className="empty-state-description">{error || 'An unexpected error occurred'}</p>
          </div>
        </div>

        <div className="space-y-2">
          <button
            onClick={() => {
              hapticFeedback?.('medium')
              startPlanning()
            }}
            className="w-full py-3 rounded-xl text-[16px] font-semibold flex items-center justify-center gap-2"
            style={{
              background: 'var(--tg-theme-button-color, #3390ec)',
              color: 'var(--tg-theme-button-text-color, #fff)',
            }}
          >
            <RefreshCw className="w-5 h-5" />
            Retry
          </button>
          <button
            onClick={cancelCleanup}
            className="w-full py-3 rounded-xl text-[14px]"
            style={{
              background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)',
              color: 'var(--tg-theme-text-color, #e0e0e0)',
            }}
          >
            Back
          </button>
        </div>
      </div>
    )
  }

  // Fallback (e.g. review without plan)
  return (
    <div className="page scrollbar-hide overflow-auto">
      <header className="page-header">
        <h1 className="page-title">Cleanup</h1>
      </header>
      <div className="card">
        <div className="empty-state">
          <div className="spinner" />
          <p className="empty-state-description mt-4">Loading...</p>
        </div>
      </div>
    </div>
  )
}
