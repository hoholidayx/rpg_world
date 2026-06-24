'use client'

import { useQuery } from '@tanstack/react-query'
import { getCurrentScene } from '@/lib/api/scene'

export function useScene(workspace: string, sessionId: string) {
  return useQuery({
    queryKey: ['play-scene', workspace, sessionId],
    queryFn: () => getCurrentScene(workspace, sessionId),
  })
}
