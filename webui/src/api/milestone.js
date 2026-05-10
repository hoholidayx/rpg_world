import api from './index'

export function listEntries() {
  return api.get('/milestone/entries').then((r) => r.data.entries)
}

export function getEntry(name) {
  return api
    .get(`/milestone/entries/${encodeURIComponent(name)}`)
    .then((r) => r.data)
}

export function createEntry(data) {
  return api.post('/milestone/entries', data).then((r) => r.data.data)
}

export function updateEntry(name, data) {
  return api
    .put(`/milestone/entries/${encodeURIComponent(name)}`, data)
    .then((r) => r.data.data)
}

export function deleteEntry(name) {
  return api
    .delete(`/milestone/entries/${encodeURIComponent(name)}`)
    .then((r) => r.data)
}
