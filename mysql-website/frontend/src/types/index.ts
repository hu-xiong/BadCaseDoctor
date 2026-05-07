// Global type definitions

export interface User {
  id: number
  username: string
  email: string
  avatar?: string
  createdAt?: string
}

export interface ApiResponse<T = any> {
  success: boolean
  message?: string
  data: T
}

export interface PaginationParams {
  page: number
  limit: number
  total?: number
}

export interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
}
