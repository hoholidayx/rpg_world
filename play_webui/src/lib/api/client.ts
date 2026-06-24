import { getPlayApiBaseUrl } from '@/lib/config/env'
import { readApiError } from './errors'

export async function playApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getPlayApiBaseUrl()}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) throw new Error(await readApiError(response))
  return response.json() as Promise<T>
}

export function withWorkspace(path: string, workspace: string) {
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}workspace=${encodeURIComponent(workspace)}`
}
