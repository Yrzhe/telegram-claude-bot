import { useEffect } from 'react'
import { wsClient } from '../api/websocket'
import { useAuthStore } from '../stores/auth'
import { useFilesStore } from '../stores/files'
import { useTasksStore } from '../stores/tasks'
import { useSchedulesStore } from '../stores/schedules'
import type { TaskUpdateData, StorageUpdateData } from '../api/types'

export function useWebSocket() {
  const token = useAuthStore((state) => state.token)
  const updateStorage = useFilesStore((state) => state.updateStorage)
  const updateTask = useTasksStore((state) => state.updateTask)
  const addTask = useTasksStore((state) => state.addTask)
  const updateSchedule = useSchedulesStore((state) => state.updateSchedule)

  useEffect(() => {
    if (!token) return

    // Subscribe to task updates
    const unsubTaskUpdate = wsClient.subscribe('task_update', (data) => {
      const { task_id, status, result } = data as TaskUpdateData
      updateTask(task_id, {
        status: status as 'running' | 'completed' | 'failed' | 'cancelled',
        result_preview: result,
        completed_at: status !== 'running' ? new Date().toISOString() : undefined,
      })
    })

    // Subscribe to new tasks
    const unsubTaskCreated = wsClient.subscribe('task_created', (data) => {
      const task = data as {
        task_id: string
        description: string
      }
      addTask({
        task_id: task.task_id,
        description: task.description,
        status: 'running',
        created_at: new Date().toISOString(),
      })
    })

    // Subscribe to schedule executions
    const unsubScheduleExecuted = wsClient.subscribe('schedule_executed', (data) => {
      const { task_id, run_count, next_run } = data as {
        task_id: string
        run_count: number
        next_run: string
      }
      updateSchedule(task_id, {
        run_count,
        next_run,
        last_run: new Date().toISOString(),
      })
    })

    // Subscribe to storage updates
    const unsubStorageUpdate = wsClient.subscribe('storage_update', (data) => {
      const { used_bytes, quota_bytes } = data as StorageUpdateData
      updateStorage({ used_bytes, quota_bytes })
    })

    return () => {
      unsubTaskUpdate()
      unsubTaskCreated()
      unsubScheduleExecuted()
      unsubStorageUpdate()
    }
  }, [token, updateStorage, updateTask, addTask, updateSchedule])
}

export function useWebSocketSubscription<T>(
  eventType: string,
  handler: (data: T) => void
) {
  useEffect(() => {
    return wsClient.subscribe(eventType, handler as (data: unknown) => void)
  }, [eventType, handler])
}
