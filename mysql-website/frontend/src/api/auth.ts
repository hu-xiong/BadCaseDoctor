import apiClient from './axios'
import { unwrapData } from './response'

export interface AuthUser {
  id: number
  email: string
  username: string
  avatar?: string
  status?: number
  created_at?: string
}

export interface AuthPayload {
  user: AuthUser
  token: string
}

export const login = async (credentials: { email: string; password: string }) => {
  const response = await apiClient.post('/auth/login', credentials)
  return unwrapData<AuthPayload>(response)
}

export const register = async (userData: { username: string; email: string; password: string }) => {
  const response = await apiClient.post('/auth/register', userData)
  return unwrapData<AuthPayload>(response)
}

export const logout = () => {
  return apiClient.post('/auth/logout')
}

export const getCurrentUser = async () => {
  const response = await apiClient.get('/auth/me')
  return unwrapData<AuthUser>(response)
}
