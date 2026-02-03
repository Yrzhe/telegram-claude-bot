import { ListTodo } from 'lucide-react'
import { TaskList } from '../components/tasks/TaskList'
import { useTasksStore } from '../stores/tasks'

export function TasksPage() {
  const { stats } = useTasksStore()

  return (
    <div className="flex flex-col h-full bg-[var(--tg-theme-secondary-bg-color)]">
      {/* Header */}
      <header className="bg-[var(--tg-theme-bg-color)] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center">
            <ListTodo className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
              Tasks
            </h1>
            <p className="text-xs text-[var(--tg-theme-hint-color)]">
              Background operations
            </p>
          </div>
          {stats.running > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/10">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-xs font-medium text-green-500">{stats.running}</span>
            </div>
          )}
        </div>
      </header>

      {/* Task list */}
      <TaskList />
    </div>
  )
}
