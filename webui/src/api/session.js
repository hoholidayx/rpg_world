import api from './index'

export function listSessions() {
  return api.get('/workspaces/active/sessions').then((r) => r.data.sessions)
}

export function createSession(sessionId) {
  return api.post('/workspaces/active/sessions', { session_id: sessionId }).then((r) => r.data)
}

export function deleteSession(sessionId) {
  return api.delete(`/workspaces/active/sessions/${encodeURIComponent(sessionId)}`).then((r) => r.data)
}

export function cloneSession(source, target) {
  return api
    .post(`/workspaces/active/sessions/${encodeURIComponent(source)}/clone`, {
      target_session_id: target,
    })
    .then((r) => r.data)
}
