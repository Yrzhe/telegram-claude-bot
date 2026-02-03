import { useEffect, useState, useCallback } from 'react'
import WebApp from '@twa-dev/sdk'

interface TelegramUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  language_code?: string
}

interface ThemeParams {
  bg_color?: string
  text_color?: string
  hint_color?: string
  link_color?: string
  button_color?: string
  button_text_color?: string
  secondary_bg_color?: string
}

export function useTelegram() {
  const [isReady, setIsReady] = useState(false)
  const [user, setUser] = useState<TelegramUser | null>(null)
  const [initData, setInitData] = useState<string>('')
  const [themeParams, setThemeParams] = useState<ThemeParams>({})

  useEffect(() => {
    // Check if running in Telegram
    const isTelegram = Boolean(WebApp.initData)

    if (isTelegram) {
      WebApp.ready()
      WebApp.expand()

      setUser(WebApp.initDataUnsafe.user as TelegramUser | undefined ?? null)
      setInitData(WebApp.initData)
      setThemeParams(WebApp.themeParams)
      setIsReady(true)

      // Update theme params when they change
      WebApp.onEvent('themeChanged', () => {
        setThemeParams(WebApp.themeParams)
        applyTheme(WebApp.themeParams)
      })

      // Apply initial theme
      applyTheme(WebApp.themeParams)
    } else if (import.meta.env.DEV) {
      // Development mode mock
      console.log('Running in development mode with mock Telegram data')
      setUser({
        id: 123456789,
        first_name: 'Dev',
        last_name: 'User',
        username: 'dev_user',
      })
      setInitData('dev_mode_init_data')
      setThemeParams({
        bg_color: '#ffffff',
        text_color: '#000000',
        hint_color: '#999999',
        link_color: '#3390ec',
        button_color: '#3390ec',
        button_text_color: '#ffffff',
        secondary_bg_color: '#f1f1f1',
      })
      setIsReady(true)
    }
  }, [])

  const close = useCallback(() => {
    WebApp.close()
  }, [])

  const showBackButton = useCallback((onClick: () => void) => {
    WebApp.BackButton.show()
    WebApp.BackButton.onClick(onClick)
    return () => {
      WebApp.BackButton.hide()
      WebApp.BackButton.offClick(onClick)
    }
  }, [])

  const showMainButton = useCallback((text: string, onClick: () => void) => {
    WebApp.MainButton.setText(text)
    WebApp.MainButton.show()
    WebApp.MainButton.onClick(onClick)
    return () => {
      WebApp.MainButton.hide()
      WebApp.MainButton.offClick(onClick)
    }
  }, [])

  const showAlert = useCallback((message: string) => {
    WebApp.showAlert(message)
  }, [])

  const showConfirm = useCallback((message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      WebApp.showConfirm(message, resolve)
    })
  }, [])

  const hapticFeedback = useCallback((type: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => {
    WebApp.HapticFeedback.impactOccurred(type)
  }, [])

  return {
    isReady,
    user,
    initData,
    themeParams,
    close,
    showBackButton,
    showMainButton,
    showAlert,
    showConfirm,
    hapticFeedback,
    isDev: import.meta.env.DEV && !WebApp.initData,
  }
}

function applyTheme(params: ThemeParams) {
  const root = document.documentElement
  if (params.bg_color) {
    root.style.setProperty('--tg-theme-bg-color', params.bg_color)
  }
  if (params.text_color) {
    root.style.setProperty('--tg-theme-text-color', params.text_color)
  }
  if (params.hint_color) {
    root.style.setProperty('--tg-theme-hint-color', params.hint_color)
  }
  if (params.link_color) {
    root.style.setProperty('--tg-theme-link-color', params.link_color)
  }
  if (params.button_color) {
    root.style.setProperty('--tg-theme-button-color', params.button_color)
  }
  if (params.button_text_color) {
    root.style.setProperty('--tg-theme-button-text-color', params.button_text_color)
  }
  if (params.secondary_bg_color) {
    root.style.setProperty('--tg-theme-secondary-bg-color', params.secondary_bg_color)
  }
}
