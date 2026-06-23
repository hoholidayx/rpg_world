import api from './index'

export function listCharacters() {
  return api.get('/characters').then((r) => r.data.characters)
}

export function getCharacter(name) {
  return api.get(`/characters/${encodeURIComponent(name)}`).then((r) => r.data)
}

export function createCharacter(data) {
  return api.post('/characters', data).then((r) => r.data.data)
}

export function updateCharacter(name, data) {
  return api
    .put(`/characters/${encodeURIComponent(name)}`, data)
    .then((r) => r.data.data)
}

export function deleteCharacter(name) {
  return api
    .delete(`/characters/${encodeURIComponent(name)}`)
    .then((r) => r.data)
}

// --- L2 Detail APIs ---

export function listDetails(characterName) {
  return api
    .get(`/characters/${encodeURIComponent(characterName)}/details`)
    .then((r) => r.data.details)
}

export function getDetail(characterName, detailName) {
  return api
    .get(
      `/characters/${encodeURIComponent(characterName)}/details/${encodeURIComponent(detailName)}`
    )
    .then((r) => r.data)
}

export function createDetail(characterName, data) {
  return api
    .post(`/characters/${encodeURIComponent(characterName)}/details`, data)
    .then((r) => r.data.data)
}

export function updateDetail(characterName, detailName, data) {
  return api
    .put(
      `/characters/${encodeURIComponent(characterName)}/details/${encodeURIComponent(detailName)}`,
      data
    )
    .then((r) => r.data.data)
}

export function deleteDetail(characterName, detailName) {
  return api
    .delete(
      `/characters/${encodeURIComponent(characterName)}/details/${encodeURIComponent(detailName)}`
    )
    .then((r) => r.data)
}
