import { useLocation, useNavigate } from 'react-router-dom'
import { FolderOpen, ListTodo, Clock, Bot } from 'lucide-react'

const tabs = [
  { path: '/', icon: FolderOpen, label: 'Files' },
  { path: '/tasks', icon: ListTodo, label: 'Tasks' },
  { path: '/schedules', icon: Clock, label: 'Schedules' },
  { path: '/subagents', icon: Bot, label: 'Agents' },
]

export function TabBar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-[var(--tg-theme-bg-color)] border-t border-[var(--tg-theme-hint-color)]/20 safe-area-pb">
      <div className="flex justify-around items-center h-14">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path
          const Icon = tab.icon
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              className={`flex flex-col items-center justify-center flex-1 h-full transition-colors ${
                isActive
                  ? 'text-[var(--tg-theme-button-color)]'
                  : 'text-[var(--tg-theme-hint-color)]'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="text-xs mt-1">{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
