export type DreamReturnTarget = {
  href: string
  label: string
}

export function buildDreamPageHref(sessionId: string, returnTo: string) {
  return `/session/${encodeURIComponent(sessionId)}/dream?returnTo=${encodeURIComponent(returnTo)}`
}

export function resolveDreamReturnTarget(
  returnTo: string | string[] | undefined,
  sessionId: string,
): DreamReturnTarget {
  const sessionHref = `/session/${encodeURIComponent(sessionId)}`
  if (typeof returnTo !== 'string') {
    return { href: sessionHref, label: '返回会话' }
  }
  if (returnTo === '/sessions' || returnTo.startsWith('/sessions?')) {
    return { href: returnTo, label: '返回会话中心' }
  }
  if (returnTo === sessionHref || returnTo.startsWith(`${sessionHref}?`)) {
    return { href: returnTo, label: '返回会话' }
  }
  return { href: sessionHref, label: '返回会话' }
}
