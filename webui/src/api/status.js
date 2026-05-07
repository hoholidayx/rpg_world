import api from './index'

// ============================================================================
// Type CRUD
// ============================================================================

export function listTypes() {
  return api.get('/status/types').then((r) => r.data.types)
}

export function createType(name) {
  return api.post('/status/types', { name }).then((r) => r.data)
}

export function renameType(oldName, newName) {
  return api
    .put(`/status/types/${encodeURIComponent(oldName)}`, { name: newName })
    .then((r) => r.data)
}

export function deleteType(name) {
  return api
    .delete(`/status/types/${encodeURIComponent(name)}`)
    .then((r) => r.data)
}

// ============================================================================
// Table CRUD
// ============================================================================

export function listTables(typeName) {
  return api
    .get(`/status/types/${encodeURIComponent(typeName)}/tables`)
    .then((r) => r.data.tables)
}

export function createTable(typeName, data) {
  return api
    .post(`/status/types/${encodeURIComponent(typeName)}/tables`, data)
    .then((r) => r.data.data)
}

export function getTable(typeName, tableName) {
  return api
    .get(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`
    )
    .then((r) => r.data)
}

export function saveTable(typeName, tableName, data) {
  return api
    .put(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`,
      data
    )
    .then((r) => r.data.data)
}

export function renameTable(typeName, oldName, newName) {
  return api
    .put(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(oldName)}/rename`,
      { name: newName }
    )
    .then((r) => r.data.data)
}

export function deleteTable(typeName, tableName) {
  return api
    .delete(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`
    )
    .then((r) => r.data)
}
