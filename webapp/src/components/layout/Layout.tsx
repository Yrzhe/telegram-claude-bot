import { Outlet } from 'react-router-dom'
import { TabBar } from './TabBar'
import { useWebSocket } from '../../hooks/useWebSocket'

export function Layout() {
  // Set up WebSocket subscriptions
  useWebSocket()

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] flex flex-col">
      <main className="flex-1 pb-14 overflow-auto">
        <Outlet />
      </main>
      <TabBar />
    </div>
  )
}
