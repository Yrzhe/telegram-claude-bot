import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../api/types'
import { api } from '../api/client'
import { wsClient } from '../api/websocket'

interface AuthState {
  token: string | null
  user: User | null
  isLoading: boolean
  error: string | null

  login: (initData: string) => Promise<void>
  logout: () => void
  setError: (error: string | null) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isLoading: false,
      error: null,

      login: async (initData: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await api.authenticate(initData)
          api.setToken(response.token)
          wsClient.connect(response.token)
          set({
            token: response.token,
            user: response.user,
            isLoading: false,
          })
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Authentication failed',
            isLoading: false,
          })
          throw error
        }
      },

      logout: () => {
        api.setToken(null)
        wsClient.disconnect()
        set({ token: null, user: null, error: null })
      },

      setError: (error: string | null) => set({ error }),
    }),
    {
      name: 'telegram-miniapp-auth',
      partialize: (state) => ({ token: state.token, user: state.user }),
      onRehydrateStorage: () => (state) => {
        // Restore API client token on rehydration
        if (state?.token) {
          api.setToken(state.token)
          wsClient.connect(state.token)
        }
      },
    }
  )
)
