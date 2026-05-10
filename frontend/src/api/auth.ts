import api from './index'

export function login(username: string, password: string) {
  return api.post('/auth/login', { username, password })
}

export function register(username: string, password: string) {
  return api.post('/auth/register', { username, password })
}

export function getMe() {
  return api.get('/auth/me')
}
