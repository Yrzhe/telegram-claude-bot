import { create } from 'zustand'
import type { SkillItem, SkillDetailResponse } from '../api/types'
import { api } from '../api/client'

interface SkillsState {
  skills: SkillItem[]
  selectedSkill: SkillDetailResponse | null
  isLoading: boolean
  error: string | null

  loadSkills: () => Promise<void>
  loadSkill: (name: string) => Promise<void>
  deleteSkill: (name: string) => Promise<boolean>
  clearSelected: () => void
}

export const useSkillsStore = create<SkillsState>((set) => ({
  skills: [],
  selectedSkill: null,
  isLoading: false,
  error: null,

  loadSkills: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.getSkills()
      set({ skills: response.skills, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load skills',
        isLoading: false,
      })
    }
  },

  loadSkill: async (name: string) => {
    set({ isLoading: true, error: null })
    try {
      const detail = await api.getSkill(name)
      set({ selectedSkill: detail, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load skill',
        isLoading: false,
      })
    }
  },

  deleteSkill: async (name: string) => {
    try {
      await api.deleteSkill(name)
      set((state) => ({
        skills: state.skills.filter((s) => s.name !== name),
        selectedSkill: state.selectedSkill?.name === name ? null : state.selectedSkill,
      }))
      return true
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete skill',
      })
      return false
    }
  },

  clearSelected: () => set({ selectedSkill: null }),
}))
