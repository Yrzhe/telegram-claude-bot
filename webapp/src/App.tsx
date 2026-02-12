import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { FilesPage } from './pages/FilesPage'
import { SchedulesPage } from './pages/SchedulesPage'
import { SubAgentsPage } from './pages/SubAgentsPage'
import { useTelegram } from './hooks/useTelegram'
import { useAuthStore } from './stores/auth'

function AuthWrapper({ children }: { children: React.ReactNode }) {
  const { isReady, initData, isDev } = useTelegram()
  const { token, isLoading, error, login, needsReauth, isHydrated } = useAuthStore()
  const [authAttempted, setAuthAttempted] = useState(false)

  useEffect(() => {
    // Reset authAttempted when needsReauth is triggered
    if (needsReauth) {
      setAuthAttempted(false)
    }
  }, [needsReauth])

  useEffect(() => {
    // Wait for both Telegram SDK and store hydration
    if (!isReady || !isHydrated || authAttempted) return

    const authenticate = async () => {
      setAuthAttempted(true)

      // If already have a valid token and not needing reauth, skip
      if (token && !needsReauth) {
        console.log('Using cached token, skipping authentication')
        return
      }

      // Dev mode bypass
      if (isDev) {
        console.log('Dev mode: skipping authentication')
        return
      }

      if (!initData) {
        console.error('No initData available')
        return
      }

      try {
        console.log('Authenticating with Telegram...')
        await login(initData)
      } catch (err) {
        console.error('Authentication failed:', err)
      }
    }

    authenticate()
  }, [isReady, isHydrated, initData, token, authAttempted, login, isDev, needsReauth])

  // Show loading state while initializing
  if (!isReady || !isHydrated || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color)]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full mx-auto" />
          <p className="mt-4 text-[var(--tg-theme-hint-color)]">Loading...</p>
        </div>
      </div>
    )
  }

  // Show error state
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
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthWrapper>
    </BrowserRouter>
  )
}

export default App
