import api from './index'

export function listWorkspaces() {
  return api.get('/workspaces').then((r) => r.data)
}

export function createWorkspace(name) {
  return api.post('/workspaces', { name }).then((r) => r.data)
}

export function renameWorkspace(workspace, newName) {
  return api.put(`/workspaces/${encodeURIComponent(workspace)}`, { name: newName }).then((r) => r.data)
}

export function deleteWorkspace(workspace) {
  return api.delete(`/workspaces/${encodeURIComponent(workspace)}`).then((r) => r.data)
}
