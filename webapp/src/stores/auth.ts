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
  needsReauth: boolean
  isHydrated: boolean  // Track if store has been rehydrated

  login: (initData: string) => Promise<void>
  logout: () => void
  setError: (error: string | null) => void
  triggerReauth: () => void
  setHydrated: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isLoading: false,
      error: null,
      needsReauth: false,
      isHydrated: false,

      login: async (initData: string) => {
        set({ isLoading: true, error: null, needsReauth: false })
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
        set({ token: null, user: null, error: null, needsReauth: false })
      },

      setError: (error: string | null) => set({ error }),

      triggerReauth: () => {
        // Clear token and trigger re-authentication
        api.setToken(null)
        wsClient.disconnect()
        set({ token: null, user: null, needsReauth: true, error: null })
      },

      setHydrated: () => set({ isHydrated: true }),
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
        // Mark as hydrated
        useAuthStore.getState().setHydrated()
        // Set up 401 handler
        api.setOnUnauthorized(() => {
          useAuthStore.getState().triggerReauth()
        })
      },
    }
  )
)

// Set up 401 handler on initial load
api.setOnUnauthorized(() => {
  useAuthStore.getState().triggerReauth()
})
