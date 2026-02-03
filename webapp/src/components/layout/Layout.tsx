import { Outlet } from 'react-router-dom'
import { TabBar } from './TabBar'
import { useWebSocket } from '../../hooks/useWebSocket'

export function Layout() {
  useWebSocket()

  return (
    <div className="min-h-screen bg-[var(--tg-theme-secondary-bg-color)]">
      <Outlet />
      <TabBar />
    </div>
  )
}
