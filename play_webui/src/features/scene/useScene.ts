'use client'

import { useQuery } from '@tanstack/react-query'
import { getCurrentScene } from '@/lib/api/scene'

export function useScene(workspace: string, storyId: number, sessionId: string) {
  return useQuery({
    queryKey: ['play-scene', workspace, storyId, sessionId],
    queryFn: () => getCurrentScene(workspace, storyId, sessionId),
  })
}
