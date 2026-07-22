'use client'

import { useEffect, useState } from 'react'

type StorySelectionItem = {
  id: number
}

function requestedStoryId() {
  const raw = new URLSearchParams(window.location.search).get('storyId')
  if (!raw) return null
  const value = Number(raw)
  return Number.isSafeInteger(value) && value > 0 ? value : null
}

export function useStorySelection(stories: readonly StorySelectionItem[]) {
  const [storyId, setStoryId] = useState<number | null>(null)
  const [requestedId, setRequestedId] = useState<number | null | undefined>(undefined)

  useEffect(() => {
    setRequestedId(requestedStoryId())
  }, [])

  useEffect(() => {
    if (requestedId === undefined) return
    if (!stories.length) {
      setStoryId(null)
      return
    }

    if (requestedId !== null && stories.some((story) => story.id === requestedId)) {
      setStoryId(requestedId)
      setRequestedId(null)
      return
    }

    if (storyId === null || !stories.some((story) => story.id === storyId)) {
      setStoryId(stories[0].id)
    }
    if (requestedId !== null) setRequestedId(null)
  }, [requestedId, stories, storyId])

  return [storyId, setStoryId] as const
}
