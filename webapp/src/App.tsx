import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { FilesPage } from './pages/FilesPage'
import { SchedulesPage } from './pages/SchedulesPage'
import { SubAgentsPage } from './pages/SubAgentsPage'
import { SkillsPage } from './pages/SkillsPage'
import { CleanupPage } from './pages/CleanupPage'
import { useTelegram } from './hooks/useTelegram'
import { useAuthStore } from './stores/auth'

function AuthWrapper({ children }: { children: React.ReactNode }) {
  const { isReady, initData, isDev } = useTelegram()
  const { isLoading, error, login, token } = useAuthStore()
  const [telegramTimeout, setTelegramTimeout] = useState(false)

  // Timeout: if Telegram SDK never becomes ready, show diagnostic
  useEffect(() => {
    if (isReady) return
    const timer = setTimeout(() => setTelegramTimeout(true), 5000)
    return () => clearTimeout(timer)
  }, [isReady])

  // Auth: when Telegram SDK is ready, authenticate immediately
  useEffect(() => {
    if (!isReady) return

    if (isDev) {
      console.log('Dev mode: skipping authentication')
      return
    }

    if (!initData) {
      console.error('No initData available')
      return
    }

    console.log('Authenticating with Telegram...')
    login(initData).catch((err) => {
      console.error('Authentication failed:', err)
    })
  }, [isReady, initData, isDev, login])

  // Telegram SDK timeout - not opened from Telegram
  if (telegramTimeout && !isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#1a1a2e)] p-4">
        <div className="text-center">
          <div className="text-4xl mb-4">🔗</div>
          <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color,#e0e0e0)]">
            Cannot Connect to Telegram
          </h1>
          <p className="mt-2 text-[var(--tg-theme-hint-color,#999)]">
            Please open this app from the Telegram bot menu.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-[var(--tg-theme-button-color,#3390ec)] text-[var(--tg-theme-button-text-color,#fff)] rounded-lg"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // Loading state
  if (!isReady || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color)]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full mx-auto" />
          <p className="mt-4 text-[var(--tg-theme-hint-color)]">Loading...</p>
        </div>
      </div>
    )
  }

  // Auth error
  if (error && !token && !isDev) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color)] p-4">
        <div className="text-center">
          <div className="text-red-500 text-4xl mb-4">⚠️</div>
          <h1 className="text-lg font-semibold text-[var(--tg-theme-text-color)]">
            Authentication Failed
          </h1>
          <p className="mt-2 text-[var(--tg-theme-hint-color)]">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] rounded-lg"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <AuthWrapper>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<FilesPage />} />
            <Route path="schedules" element={<SchedulesPage />} />
            <Route path="subagents" element={<SubAgentsPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="cleanup" element={<CleanupPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthWrapper>
    </BrowserRouter>
  )
}

export default App
