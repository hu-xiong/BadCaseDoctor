import type { AxiosResponse } from 'axios'

export interface ApiEnvelope<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PaginatedList<T> {
  list: T[]
  total: number
  page: number
  page_size: number
}

export function unwrapData<T>(response: AxiosResponse<ApiEnvelope<T>>): T {
  return response.data.data
}
