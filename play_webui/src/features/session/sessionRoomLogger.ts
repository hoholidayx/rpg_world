type LogFields = Record<string, unknown>

function normalizeError(error: unknown) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
    }
  }
  return error ? String(error) : undefined
}

function payload(sessionId: string, action: string, fields: LogFields = {}) {
  const { error, ...rest } = fields
  return {
    sessionId,
    action,
    ...rest,
    ...(error === undefined ? {} : { error: normalizeError(error) }),
  }
}

export function createSessionRoomLogger(sessionId: string) {
  return {
    info(action: string, fields?: LogFields) {
      console.info('[SessionRoom]', payload(sessionId, action, fields))
    },
    warn(action: string, fields?: LogFields) {
      console.warn('[SessionRoom]', payload(sessionId, action, fields))
    },
    error(action: string, fields?: LogFields) {
      console.error('[SessionRoom]', payload(sessionId, action, fields))
    },
  }
}

export type SessionRoomLogger = ReturnType<typeof createSessionRoomLogger>
