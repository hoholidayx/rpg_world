export type StorySummary = {
  id: number
  workspace: string
  title: string
  summary?: string | null
  storyPrompt: string
  firstMessage: string
  createdAt?: string | null
  updatedAt?: string | null
}
