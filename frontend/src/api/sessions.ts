import api from './index'

export function getSessions() {
  return api.get('/sessions')
}

export function createSession(title?: string, modelId?: string) {
  return api.post('/sessions', { title, model_id: modelId })
}

export function getSession(id: string) {
  return api.get(`/sessions/${id}`)
}

export function updateSession(id: string, data: { title?: string; model_id?: string }) {
  return api.patch(`/sessions/${id}`, data)
}

export function deleteSession(id: string) {
  return api.delete(`/sessions/${id}`)
}

export function getModels() {
  return api.get('/models')
}

export function getUsage() {
  return api.get('/usage')
}

export function getMcpServers() {
  return api.get('/mcp/servers')
}

export function getUserKeys() {
  return api.get('/keys')
}

export function saveUserKey(provider: string, apiKey: string, baseUrl: string) {
  return api.put(`/keys/${provider}`, { provider, api_key: apiKey, base_url: baseUrl })
}

export function deleteUserKey(provider: string) {
  return api.delete(`/keys/${provider}`)
}
