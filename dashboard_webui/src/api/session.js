import api from './index'

const DEFAULT_WORKSPACE = 'data/dashboard_api_default_workspace'

function _ws(workspace) {
  return encodeURIComponent(workspace || DEFAULT_WORKSPACE)
}

export function listSessions(workspace) {
  return api.get(`/workspaces/${_ws(workspace)}/sessions`).then((r) => r.data.sessions)
}

export function createSession(workspace, sessionId) {
  return api.post(`/workspaces/${_ws(workspace)}/sessions`, { session_id: sessionId }).then((r) => r.data)
}

export function deleteSession(workspace, sessionId) {
  return api.delete(`/workspaces/${_ws(workspace)}/sessions/${encodeURIComponent(sessionId)}`).then((r) => r.data)
}

export function cloneSession(workspace, source, target) {
  return api
    .post(`/workspaces/${_ws(workspace)}/sessions/${encodeURIComponent(source)}/clone`, {
      target_session_id: target,
    })
    .then((r) => r.data)
}
