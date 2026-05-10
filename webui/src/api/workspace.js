import api from './index'

export function listWorkspaces() {
  return api.get('/workspaces').then((r) => r.data.workspaces)
}

export function getActiveWorkspace() {
  return api.get('/workspaces/active').then((r) => r.data)
}

export function setActiveWorkspace(name) {
  return api.put('/workspaces/active', { workspace: name }).then((r) => r.data)
}
