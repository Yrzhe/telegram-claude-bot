import { create } from 'zustand'
import type { TaskItem } from '../api/types'
import { api } from '../api/client'

interface TasksState {
  running: TaskItem[]
  recentCompleted: TaskItem[]
  stats: {
    pending: number
    running: number
    completed: number
    failed: number
    cancelled: number
  }
  isLoading: boolean
  error: string | null

  loadTasks: () => Promise<void>
  cancelTask: (taskId: string) => Promise<void>
  updateTask: (taskId: string, updates: Partial<TaskItem>) => void
  addTask: (task: TaskItem) => void
}

export const useTasksStore = create<TasksState>((set, get) => ({
  running: [],
  recentCompleted: [],
  stats: {
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  },
  isLoading: false,
  error: null,

  loadTasks: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.listTasks()
      set({
        running: response.running,
        recentCompleted: response.recent_completed,
        stats: response.stats,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load tasks',
        isLoading: false,
      })
    }
  },

  cancelTask: async (taskId: string) => {
    try {
      await api.cancelTask(taskId)
      // Update local state
      const { running, stats } = get()
      const task = running.find((t) => t.task_id === taskId)
      if (task) {
        set({
          running: running.filter((t) => t.task_id !== taskId),
          recentCompleted: [
            { ...task, status: 'cancelled', completed_at: new Date().toISOString() },
            ...get().recentCompleted,
          ],
          stats: {
            ...stats,
            running: stats.running - 1,
            cancelled: stats.cancelled + 1,
          },
        })
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to cancel task',
      })
    }
  },

  updateTask: (taskId: string, updates: Partial<TaskItem>) => {
    const { running, recentCompleted, stats } = get()

    // Check if task is in running
    const runningIndex = running.findIndex((t) => t.task_id === taskId)
    if (runningIndex >= 0) {
      const task = { ...running[runningIndex], ...updates }

      if (updates.status && updates.status !== 'running') {
        // Task completed, move to recent
        set({
          running: running.filter((t) => t.task_id !== taskId),
          recentCompleted: [task, ...recentCompleted].slice(0, 20),
          stats: {
            ...stats,
            running: stats.running - 1,
            [updates.status]: (stats[updates.status as keyof typeof stats] as number) + 1,
          },
        })
      } else {
        // Update in place
        const newRunning = [...running]
        newRunning[runningIndex] = task
        set({ running: newRunning })
      }
    }
  },

  addTask: (task: TaskItem) => {
    const { running, stats } = get()
    set({
      running: [task, ...running],
      stats: {
        ...stats,
        running: stats.running + 1,
      },
    })
  },
}))
