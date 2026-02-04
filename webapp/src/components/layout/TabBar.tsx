import { useLocation, useNavigate } from 'react-router-dom'
import { FolderOpen, Clock, Bot } from 'lucide-react'

const tabs = [
  { path: '/', icon: FolderOpen, label: 'Files' },
  { path: '/schedules', icon: Clock, label: 'Schedules' },
  { path: '/subagents', icon: Bot, label: 'Agents' },
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
