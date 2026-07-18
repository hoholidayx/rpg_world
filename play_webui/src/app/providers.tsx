'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode, useState } from 'react'
import { ThemeProvider } from '@/components/theme/ThemeProvider'
import { PlayEventBridge } from '@/features/events/PlayEventBridge'

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <PlayEventBridge />
        {children}
      </QueryClientProvider>
    </ThemeProvider>
  )
}
