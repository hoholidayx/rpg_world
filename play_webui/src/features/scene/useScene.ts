'use client'

import { useQuery } from '@tanstack/react-query'
import { getCurrentScene } from '@/lib/api/scene'

export function useScene(sessionId: string) {
  return useQuery({
    queryKey: ['play-scene', sessionId],
    queryFn: () => getCurrentScene(sessionId),
  })
}
