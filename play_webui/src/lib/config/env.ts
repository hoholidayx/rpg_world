export function getPlayApiBaseUrl() {
  return process.env.NEXT_PUBLIC_PLAY_API_BASE_URL ?? '/play-api/v1'
}
