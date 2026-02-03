import { create } from 'zustand'
import type { SubAgentTask, SubAgentHistoryItem } from '../api/types'
import { api } from '../api/client'

interface SubAgentsState {
  maxAgents: number
  activeCount: number
  availableSlots: number
  runningTasks: SubAgentTask[]
  history: SubAgentHistoryItem[]
  isLoading: boolean
  error: string | null

  loadStatus: () => Promise<void>
  loadHistory: (limit?: number) => Promise<void>
}

export const useSubAgentsStore = create<SubAgentsState>((set) => ({
  maxAgents: 10,
  activeCount: 0,
  availableSlots: 10,
  runningTasks: [],
  history: [],
  isLoading: false,
  error: null,

  loadStatus: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.getSubAgentStatus()
      set({
        maxAgents: response.max_agents,
        activeCount: response.active_count,
        availableSlots: response.available_slots,
        runningTasks: response.running_tasks,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load status',
        isLoading: false,
      })
    }
  },

  loadHistory: async (limit: number = 20) => {
    try {
      const response = await api.getSubAgentHistory(limit)
      set({ history: response.tasks })
    } catch (error) {
      console.error('Failed to load history:', error)
    }
  },
}))
