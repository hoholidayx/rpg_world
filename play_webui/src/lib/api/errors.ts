export async function readApiError(response: Response, fallback = '请求失败') {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) {
      return data.detail.map((item) => item?.msg ?? item?.message ?? String(item)).join('; ')
    }
  } catch {
    // Response may not contain JSON in early mock endpoints.
  }
  return fallback
}
