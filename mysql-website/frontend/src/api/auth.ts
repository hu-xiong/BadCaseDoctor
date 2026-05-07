import apiClient from './axios'

export const login = (credentials: { username: string; password: string }) => {
  return apiClient.post('/auth/login', credentials)
}

export const register = (userData: { username: string; email: string; password: string }) => {
  return apiClient.post('/auth/register', userData)
}

export const logout = () => {
  return apiClient.post('/auth/logout')
}

export const getCurrentUser = () => {
  return apiClient.get('/auth/me')
}
