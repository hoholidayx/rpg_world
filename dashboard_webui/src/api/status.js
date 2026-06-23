import api from './index'

// ============================================================================
// Type CRUD
// ============================================================================

export function listTypes(sessionId = 'default') {
  return api.get('/status/types', { params: { session_id: sessionId } }).then((r) => r.data.types)
}

export function createType(name, sessionId = 'default') {
  return api.post('/status/types', { name }, { params: { session_id: sessionId } }).then((r) => r.data)
}

export function renameType(oldName, newName, sessionId = 'default') {
  return api
    .put(`/status/types/${encodeURIComponent(oldName)}`, { name: newName }, { params: { session_id: sessionId } })
    .then((r) => r.data)
}

export function deleteType(name, sessionId = 'default') {
  return api
    .delete(`/status/types/${encodeURIComponent(name)}`, { params: { session_id: sessionId } })
    .then((r) => r.data)
}

// ============================================================================
// Table CRUD
// ============================================================================

export function listTables(typeName, sessionId = 'default') {
  return api
    .get(`/status/types/${encodeURIComponent(typeName)}/tables`, { params: { session_id: sessionId } })
    .then((r) => r.data.tables)
}

export function createTable(typeName, data, sessionId = 'default') {
  return api
    .post(`/status/types/${encodeURIComponent(typeName)}/tables`, data, { params: { session_id: sessionId } })
    .then((r) => r.data.data)
}

export function getTable(typeName, tableName, sessionId = 'default') {
  return api
    .get(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`,
      { params: { session_id: sessionId } }
    )
    .then((r) => r.data)
}

export function saveTable(typeName, tableName, data, sessionId = 'default') {
  return api
    .put(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`,
      data,
      { params: { session_id: sessionId } }
    )
    .then((r) => r.data.data)
}

export function renameTable(typeName, oldName, newName, sessionId = 'default') {
  return api
    .put(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(oldName)}/rename`,
      { name: newName },
      { params: { session_id: sessionId } }
    )
    .then((r) => r.data.data)
}

export function deleteTable(typeName, tableName, sessionId = 'default') {
  return api
    .delete(
      `/status/types/${encodeURIComponent(typeName)}/tables/${encodeURIComponent(tableName)}`,
      { params: { session_id: sessionId } }
    )
    .then((r) => r.data)
}
