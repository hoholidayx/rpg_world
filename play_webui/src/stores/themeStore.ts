'use client'

import { create } from 'zustand'

export type ThemePreference = 'light' | 'dark' | 'system'

const THEME_STORAGE_KEY = 'rpg-world-play-theme'

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readStoredTheme(): ThemePreference {
  if (typeof window === 'undefined') return 'system'
  const value = window.localStorage.getItem(THEME_STORAGE_KEY)
  return isThemePreference(value) ? value : 'system'
}

function resolveTheme(preference: ThemePreference) {
  if (preference !== 'system') return preference
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(preference: ThemePreference) {
  if (typeof document === 'undefined') return
  const resolvedTheme = resolveTheme(preference)
  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  document.documentElement.dataset.theme = preference
  document.documentElement.style.colorScheme = resolvedTheme
}

type ThemeStore = {
  theme: ThemePreference
  setTheme: (theme: ThemePreference) => void
  syncTheme: () => void
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: 'system',
  setTheme: (theme) => {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    applyTheme(theme)
    set({ theme })
  },
  syncTheme: () => {
    const theme = readStoredTheme()
    applyTheme(theme)
    if (get().theme !== theme) set({ theme })
  },
}))

export function syncResolvedTheme(preference: ThemePreference) {
  applyTheme(preference)
}
