export type SummaryKind = 'overall' | 'batch'

export type SummaryPreview = {
  kind: SummaryKind
  batchId: number | null
  lastBatchId: number | null
  title: string
  excerpt: string
  time: string | null
  location: string | null
  characters: string[]
  turnStart: number | null
  turnEnd: number | null
  updatedAt: string | null
}

export type SummaryDetail = SummaryPreview & {
  markdown: string
}

export type SummaryIndex = {
  overall: SummaryPreview | null
  batches: SummaryPreview[]
}
