import { Header } from '../components/layout/Header'
import { TaskList } from '../components/tasks/TaskList'

export function TasksPage() {
  return (
    <div className="flex flex-col h-full">
      <Header title="Tasks" />
      <TaskList />
    </div>
  )
}
