export type UnindexedRuntimeCategory = 'runtime_directory' | 'status_csv'

export type UnindexedRuntimeItem = {
  category: UnindexedRuntimeCategory
  kind: string
  workspaceId: string
  storyId: string
  sessionId: string
  relativePath: string
  path: string
}

export type UnindexedRuntimeScanResponse = {
  items: UnindexedRuntimeItem[]
}

export type PlayDeleteConfirmationToken = {
  token: string
  expiresInSeconds: number
}
