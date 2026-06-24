import axios from 'axios'

// Injected at build time by vite.config.js ← webui/settings.json
// `__DASHBOARD_API_HOST__` and `__DASHBOARD_API_PORT__` are replaced at compile time.
// During dev, the Vite proxy handles /dashboard_api → backend, so we use `/dashboard_api/v1`.
// For production builds, we construct the full URL.
const baseURL = import.meta.env.DEV
  ? '/dashboard_api/v1'
  : `http://${__DASHBOARD_API_HOST__}:${__DASHBOARD_API_PORT__}/dashboard_api/v1`

const api = axios.create({
  baseURL,
  timeout: 10000,
})

export function extractApiError(error, fallback = '请求失败') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item?.msg || item?.message || String(item)).join('; ')
  }
  const msg = error?.message
  if (typeof msg === 'string' && msg.trim()) return msg
  return fallback
}

// ── Workspace auto-injection ────────────────────────────────────────
// Extracts the current workspace from the URL hash (e.g.
// /#/overview?workspace=data/非公开行程) and injects it into every
// request.  This avoids per-file plumbing and circular import issues
// with the router / Pinia stores.

function _getCurrentWorkspace() {
  const hash = window.location.hash
  const qsIdx = hash.indexOf('?')
  if (qsIdx === -1) return ''
  const qs = hash.slice(qsIdx + 1)
  const params = new URLSearchParams(qs)
  return params.get('workspace') || ''
}

api.interceptors.request.use((config) => {
  const workspace = _getCurrentWorkspace()
  if (workspace) {
    config.params = { workspace, ...config.params }
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = extractApiError(err)
    return Promise.reject(new Error(msg))
  },
)

export default api
