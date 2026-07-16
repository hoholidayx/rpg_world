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

export class ApiError extends Error {
  constructor(
    message: string,
    readonly errorCode: string,
    readonly statusCode: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
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

async function parseApiError(response: Response, fallback: string) {
  let message = fallback
  let errorCode = ''
  try {
    const data: unknown = await response.json()
    if (!isApiErrorPayload(data)) return { message, errorCode }

    if (typeof data?.detail === 'string') return { message: data.detail, errorCode }
    if (isObject(data?.detail)) {
      const detail = data.detail as ApiErrorObject
      if (typeof detail.message === 'string') {
        message = detail.message
        errorCode = typeof detail.errorCode === 'string' ? detail.errorCode : ''
        return { message, errorCode }
      }
    }
    if (Array.isArray(data?.detail)) {
      message = data.detail
        .map((item: unknown) => {
          if (!isApiErrorDetailItem(item)) return String(item)
          return item.msg ?? item.message ?? String(item)
        })
        .join('; ')
    }
  } catch {
    // Response may not contain JSON during early backend failures.
  }
  return { message, errorCode }
}

export async function createApiError(response: Response, fallback = '请求失败') {
  const parsed = await parseApiError(response, fallback)
  const displayMessage = parsed.errorCode
    ? `${parsed.message} (${parsed.errorCode})`
    : parsed.message
  return new ApiError(displayMessage, parsed.errorCode, response.status)
}

export async function readApiError(response: Response, fallback = '请求失败') {
  return (await createApiError(response, fallback)).message
}
