type QueryRefreshResult = {
  error?: unknown
  isError?: boolean
}

export function firstDreamRefreshError(results: unknown[]) {
  for (const result of results) {
    if (!result || typeof result !== 'object') continue
    const queryResult = result as QueryRefreshResult
    if (queryResult.isError) {
      return queryResult.error ?? new Error('Dream 状态刷新失败')
    }
  }
  return null
}
