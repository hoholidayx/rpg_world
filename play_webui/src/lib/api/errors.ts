type ApiErrorPayload = {
  detail?: unknown
}

type ApiErrorDetailItem = {
  msg?: unknown
  message?: unknown
}

type ApiErrorObject = {
  errorCode?: unknown
  message?: unknown
}

function isObject(item: unknown): item is Record<string, unknown> {
  return typeof item === 'object' && item !== null
}

function isApiErrorPayload(item: unknown): item is ApiErrorPayload {
  return isObject(item)
}

function isApiErrorDetailItem(item: unknown): item is ApiErrorDetailItem {
  return isObject(item)
}

export async function readApiError(response: Response, fallback = '请求失败') {
  try {
    const data: unknown = await response.json()
    if (!isApiErrorPayload(data)) return fallback

    if (typeof data?.detail === 'string') return data.detail
    if (isObject(data?.detail)) {
      const detail = data.detail as ApiErrorObject
      if (typeof detail.message === 'string') {
        return typeof detail.errorCode === 'string' && detail.errorCode
          ? `${detail.message} (${detail.errorCode})`
          : detail.message
      }
    }
    if (Array.isArray(data?.detail)) {
      return data.detail
        .map((item: unknown) => {
          if (!isApiErrorDetailItem(item)) return String(item)
          return item.msg ?? item.message ?? String(item)
        })
        .join('; ')
    }
  } catch {
    // Response may not contain JSON during early backend failures.
  }
  return fallback
}
