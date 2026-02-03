import { useLocation, useNavigate } from 'react-router-dom'
import { FolderOpen, ListTodo, Clock, Bot } from 'lucide-react'

const tabs = [
  { path: '/', icon: FolderOpen, label: 'Files', color: 'from-blue-500 to-cyan-500' },
  { path: '/tasks', icon: ListTodo, label: 'Tasks', color: 'from-green-500 to-emerald-500' },
  { path: '/schedules', icon: Clock, label: 'Schedules', color: 'from-orange-500 to-amber-500' },
  { path: '/subagents', icon: Bot, label: 'Agents', color: 'from-purple-500 to-indigo-500' },
]

export function TabBar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-[var(--tg-theme-bg-color)] border-t border-[var(--tg-theme-hint-color)]/10 safe-area-pb z-50">
      <div className="flex justify-around items-center h-16 max-w-lg mx-auto">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path
          const Icon = tab.icon
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              className="flex flex-col items-center justify-center flex-1 h-full transition-all active:scale-95"
            >
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                isActive
                  ? `bg-gradient-to-br ${tab.color} shadow-lg`
                  : 'bg-transparent'
              }`}>
                <Icon className={`w-5 h-5 transition-colors ${
                  isActive ? 'text-white' : 'text-[var(--tg-theme-hint-color)]'
                }`} />
              </div>
              <span className={`text-[10px] mt-1 font-medium transition-colors ${
                isActive
                  ? 'text-[var(--tg-theme-text-color)]'
                  : 'text-[var(--tg-theme-hint-color)]'
              }`}>
                {tab.label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
