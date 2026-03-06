import { useEffect, useCallback, useState } from 'react'
import { RefreshCw, Sparkles, ChevronRight, Trash2, FileText, ChevronDown } from 'lucide-react'
import { useSkillsStore } from '../stores/skills'
import { useTelegram } from '../hooks/useTelegram'

export function SkillsPage() {
  const {
    skills,
    selectedSkill,
    isLoading,
    error,
    loadSkills,
    loadSkill,
    deleteSkill,
    clearSelected,
  } = useSkillsStore()
  const { hapticFeedback } = useTelegram()

  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  useEffect(() => {
    loadSkills()
  }, [loadSkills])

  const handleRefresh = useCallback(() => {
    hapticFeedback?.('light')
    loadSkills()
    setExpandedSkill(null)
    clearSelected()
  }, [loadSkills, clearSelected, hapticFeedback])

  const handleToggleSkill = useCallback((name: string) => {
    hapticFeedback?.('light')
    if (expandedSkill === name) {
      setExpandedSkill(null)
      clearSelected()
    } else {
      setExpandedSkill(name)
      loadSkill(name)
    }
  }, [expandedSkill, loadSkill, clearSelected, hapticFeedback])

  const handleDelete = useCallback(async (name: string) => {
    hapticFeedback?.('medium')
    const success = await deleteSkill(name)
    if (success) {
      setExpandedSkill(null)
      setConfirmDelete(null)
    }
  }, [deleteSkill, hapticFeedback])

  return (
    <div className="page scrollbar-hide overflow-auto">
      {/* Header */}
      <header className="page-header">
        <h1 className="page-title">Skills</h1>
        <p className="page-subtitle">Installed Claude skills</p>
      </header>

      {/* Count card */}
      <div className="card mb-4">
        <div className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-medium">Installed Skills</span>
            <span
              className="text-[28px] font-bold"
              style={{ color: skills.length > 0 ? '#007aff' : '#8e8e93' }}
            >
              {skills.length}
            </span>
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
      {isLoading && skills.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="spinner" />
            <p className="empty-state-description mt-4">Loading...</p>
          </div>
        </div>
      ) : skills.length === 0 ? (
        /* Empty state */
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">
              <Sparkles />
            </div>
            <h3 className="empty-state-title">No skills installed</h3>
            <p className="empty-state-description">
              Upload skill zip files via the Telegram bot to install
            </p>
          </div>
        </div>
      ) : (
        /* Skills list */
        <div className="card">
          {skills.map((skill, idx) => (
            <div key={skill.name}>
              {/* Skill row */}
              <button
                onClick={() => handleToggleSkill(skill.name)}
                className="list-item w-full text-left"
              >
                <div className="list-item-icon icon-blue">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div className="list-item-content">
                  <div className="list-item-title">{skill.name}</div>
                  {skill.description && (
                    <div className="list-item-subtitle line-clamp-1">{skill.description}</div>
                  )}
                </div>
                {expandedSkill === skill.name ? (
                  <ChevronDown className="w-5 h-5 text-[var(--tg-theme-hint-color)] flex-shrink-0" />
                ) : (
                  <ChevronRight className="w-5 h-5 text-[var(--tg-theme-hint-color)] flex-shrink-0" />
                )}
              </button>

              {/* Expanded detail */}
              {expandedSkill === skill.name && (
                <div className="px-4 pb-4 pt-0">
                  {isLoading && !selectedSkill ? (
                    <div className="flex justify-center py-4">
                      <div className="spinner" />
                    </div>
                  ) : selectedSkill?.name === skill.name ? (
                    <div className="space-y-3">
                      {/* SKILL.md content */}
                      {selectedSkill.content && (
                        <div
                          className="rounded-lg p-3 text-[13px] leading-relaxed overflow-auto max-h-[300px]"
                          style={{
                            background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                          }}
                        >
                          {selectedSkill.content}
                        </div>
                      )}

                      {/* File tree */}
                      {selectedSkill.files.length > 0 && (
                        <div>
                          <div className="text-[13px] font-medium text-[var(--tg-theme-hint-color)] mb-2">
                            Files ({selectedSkill.files.length})
                          </div>
                          <div
                            className="rounded-lg p-3 space-y-1"
                            style={{ background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)' }}
                          >
                            {selectedSkill.files.map((file) => (
                              <div key={file} className="flex items-center gap-2 text-[13px]">
                                <FileText className="w-3.5 h-3.5 text-[var(--tg-theme-hint-color)] flex-shrink-0" />
                                <span className="truncate">{file}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Delete button */}
                      <div className="pt-1">
                        {confirmDelete === skill.name ? (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleDelete(skill.name)}
                              className="flex-1 py-2 rounded-lg text-[14px] font-medium"
                              style={{
                                background: 'var(--tg-theme-destructive-color, #ff3b30)',
                                color: '#fff',
                              }}
                            >
                              Confirm Delete
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              className="py-2 px-4 rounded-lg text-[14px]"
                              style={{ background: 'var(--tg-theme-secondary-bg-color, #1e1e2e)' }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              hapticFeedback?.('light')
                              setConfirmDelete(skill.name)
                            }}
                            className="flex items-center gap-2 text-[14px]"
                            style={{ color: 'var(--tg-theme-destructive-color, #ff3b30)' }}
                          >
                            <Trash2 className="w-4 h-4" />
                            Delete skill
                          </button>
                        )}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}

              {/* Separator */}
              {idx < skills.length - 1 && (
                <div className="separator ml-[52px]" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
