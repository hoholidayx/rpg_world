'use client'

import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { syncResolvedTheme, useThemeStore } from '@/stores/themeStore'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useThemeStore((state) => state.theme)
  const syncTheme = useThemeStore((state) => state.syncTheme)

  useEffect(() => {
    syncTheme()
  }, [syncTheme])

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => syncResolvedTheme(theme)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme])

  return children
}
