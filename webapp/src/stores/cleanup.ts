import { create } from 'zustand'
import type { CleanupPlan, CleanupResult } from '../api/types'
import { api } from '../api/client'

type CleanupPhase = 'idle' | 'planning' | 'review' | 'executing' | 'completed' | 'failed'

interface CleanupState {
  phase: CleanupPhase
  rules: string
  rulesModified: string | null
  plan: CleanupPlan | null
  result: CleanupResult | null
  error: string | null
  feedbackText: string
  progressLogs: string[]
  isLoadingRules: boolean
  isSavingRules: boolean

  loadRules: () => Promise<void>
  saveRules: (content: string) => Promise<boolean>
  startPlanning: (feedback?: string) => Promise<void>
  executePlan: () => Promise<void>
  cancelCleanup: () => Promise<void>
  reset: () => void
  loadStatus: () => Promise<void>
  setFeedbackText: (text: string) => void
  handleWsUpdate: (data: Record<string, unknown>) => void
  handleWsProgress: (data: Record<string, unknown>) => void
}

export const useCleanupStore = create<CleanupState>((set, get) => ({
  phase: 'idle',
  rules: '',
  rulesModified: null,
  plan: null,
  result: null,
  error: null,
  feedbackText: '',
  progressLogs: [],
  isLoadingRules: false,
  isSavingRules: false,

  loadRules: async () => {
    set({ isLoadingRules: true })
    try {
      const resp = await api.getCleanupRules()
      set({ rules: resp.content, rulesModified: resp.modified_at || null, isLoadingRules: false })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load rules', isLoadingRules: false })
    }
  },

  saveRules: async (content: string) => {
    set({ isSavingRules: true })
    try {
      await api.updateCleanupRules(content)
      set({ rules: content, isSavingRules: false })
      return true
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to save rules', isSavingRules: false })
      return false
    }
  },

  startPlanning: async (feedback?: string) => {
    set({ phase: 'planning', error: null, plan: null, result: null, progressLogs: [] })
    try {
      await api.generateCleanupPlan(feedback)
      // Status will be updated via WebSocket
    } catch (e) {
      set({
        phase: 'failed',
        error: e instanceof Error ? e.message : 'Failed to start planning',
      })
    }
  },

  executePlan: async () => {
    const { plan } = get()
    if (!plan) return
    set({ phase: 'executing', error: null })
    try {
      const resp = await api.executeCleanup(plan.plan_id)
      set({
        phase: 'completed',
        result: resp.result || null,
      })
    } catch (e) {
      set({
        phase: 'failed',
        error: e instanceof Error ? e.message : 'Execution failed',
      })
    }
  },

  cancelCleanup: async () => {
    try {
      await api.cancelCleanup()
    } catch {
      // ignore
    }
    set({ phase: 'idle', plan: null, result: null, error: null, feedbackText: '', progressLogs: [] })
  },

  reset: () => {
    set({ phase: 'idle', plan: null, result: null, error: null, feedbackText: '', progressLogs: [] })
  },

  loadStatus: async () => {
    try {
      const resp = await api.getCleanupStatus()
      const phase = resp.status === 'ready' ? 'review' : resp.status as CleanupPhase
      set({
        phase,
        plan: resp.plan || null,
        result: resp.result || null,
        error: resp.error || null,
      })
    } catch {
      // ignore
    }
  },

  setFeedbackText: (text: string) => set({ feedbackText: text }),

  handleWsUpdate: (data: Record<string, unknown>) => {
    const status = data.status as string
    if (status === 'planning') {
      set({ phase: 'planning', progressLogs: [] })
    } else if (status === 'ready') {
      set({
        phase: 'review',
        plan: (data.plan as CleanupPlan) || null,
      })
    } else if (status === 'executing') {
      set({ phase: 'executing' })
    } else if (status === 'completed') {
      set({
        phase: 'completed',
        result: (data.result as CleanupResult) || null,
      })
    } else if (status === 'failed') {
      set({
        phase: 'failed',
        error: (data.error as string) || 'Planning failed',
      })
    } else if (status === 'idle') {
      set({ phase: 'idle', plan: null, result: null, error: null, progressLogs: [] })
    }
  },

  handleWsProgress: (data: Record<string, unknown>) => {
    const logs = data.logs as string[] | undefined
    if (logs) {
      set({ progressLogs: logs })
    } else {
      const message = data.message as string
      if (message) {
        set((state) => ({ progressLogs: [...state.progressLogs, message] }))
      }
    }
  },
}))
