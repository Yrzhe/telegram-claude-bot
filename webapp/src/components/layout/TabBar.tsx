import { useLocation, useNavigate } from 'react-router-dom'
import { FolderOpen, Clock, Bot, Sparkles, Trash2 } from 'lucide-react'

const tabs = [
  { path: '/', icon: FolderOpen, label: 'Files' },
  { path: '/schedules', icon: Clock, label: 'Schedules' },
  { path: '/subagents', icon: Bot, label: 'Agents' },
  { path: '/skills', icon: Sparkles, label: 'Skills' },
  { path: '/cleanup', icon: Trash2, label: 'Cleanup' },
]

export function TabBar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav className="tabbar">
      {tabs.map((tab) => {
        const isActive = location.pathname === tab.path
        const Icon = tab.icon
        return (
          <button
            key={tab.path}
            onClick={() => navigate(tab.path)}
            className={`tabbar-item ${isActive ? 'active' : ''}`}
          >
            <Icon />
            <span>{tab.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
