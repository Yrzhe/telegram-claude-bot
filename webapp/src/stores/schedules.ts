import { create } from 'zustand'
import type { ScheduleItem, ScheduleLog } from '../api/types'
import { api } from '../api/client'

interface SchedulesState {
  timezone: string
  schedules: ScheduleItem[]
  logs: ScheduleLog[]
  isLoading: boolean
  error: string | null

  loadSchedules: () => Promise<void>
  loadLogs: (limit?: number) => Promise<void>
  updateSchedule: (taskId: string, updates: Partial<ScheduleItem>) => void
}

export const useSchedulesStore = create<SchedulesState>((set, get) => ({
  timezone: 'UTC',
  schedules: [],
  logs: [],
  isLoading: false,
  error: null,

  loadSchedules: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.listSchedules()
      set({
        timezone: response.timezone,
        schedules: response.tasks,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load schedules',
        isLoading: false,
      })
    }
  },

  loadLogs: async (limit: number = 20) => {
    try {
      const response = await api.getScheduleLogs(limit)
      set({ logs: response.logs })
    } catch (error) {
      console.error('Failed to load schedule logs:', error)
    }
  },

  updateSchedule: (taskId: string, updates: Partial<ScheduleItem>) => {
    const { schedules } = get()
    const index = schedules.findIndex((s) => s.task_id === taskId)
    if (index >= 0) {
      const newSchedules = [...schedules]
      newSchedules[index] = { ...newSchedules[index], ...updates }
      set({ schedules: newSchedules })
    }
  },
}))
